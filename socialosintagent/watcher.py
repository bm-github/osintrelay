"""
Background watcher (Phase 3): continuous monitoring + keyword-triggered alerts.

The watcher:
  - Loads persisted monitoring rules from SessionManager (data/sessions/*.json)
  - Every X seconds, fetches recently updated posts for each monitored target
  - Runs the cheap triage router (LLMAnalyzer.run_triage_evaluation)
  - Sends chat alerts only when a match occurs (or when injection is quarantined)

Supported alert channels:
  - telegram:    aiogram Bot -> chat_id
  - discord_channel: discord.py Bot -> channel_id
  - discord:     outbound webhook URL (legacy /monitor_discord rules)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .llm import LLMAnalyzer
from .platforms import FETCHERS
from .session_manager import SessionManager
from .utils import get_sort_key

logger = logging.getLogger("SocialOSINTAgent.watcher")

TELEGRAM_MAX_LEN = 4000
DISCORD_MAX_LEN = 1900


def _chunk_text(text: str, max_len: int = TELEGRAM_MAX_LEN) -> List[str]:
    if len(text) <= max_len:
        return [text]
    chunks: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        window = remaining[:max_len]
        split_at = window.rfind("\n\n")
        if split_at < max_len // 2:
            split_at = window.rfind("\n")
        if split_at < max_len // 2:
            split_at = max_len
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


def _parse_target(target: str) -> Tuple[str, str]:
    if not target or "/" not in target:
        raise ValueError(
            f"Invalid target format: {target!r}. Expected platform/username."
        )
    platform, username = target.split("/", 1)
    return platform.lower().strip(), username.strip()


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


class MonitoringWatcher:
    def __init__(
        self,
        *,
        agent: Any,
        session_manager: SessionManager,
        telegram_bot: Any = None,
        discord_bot: Any = None,
        poll_interval_seconds: int,
        fetch_limit: int,
        triage_post_limit: int,
    ):
        self.agent = agent
        self.session_manager = session_manager
        self.telegram_bot = telegram_bot
        self.discord_bot = discord_bot
        self.poll_interval_seconds = poll_interval_seconds
        self.fetch_limit = fetch_limit
        self.triage_post_limit = triage_post_limit
        self.last_periodic_status_at: Optional[datetime] = None
        self.startup_check_sent = False

    def _get_platform_status_text(self) -> str:
        """Shared logic to build the platform status list."""
        available = self.agent.client_manager.get_available_platforms(check_creds=True)
        status_text = ""
        for p in sorted(FETCHERS.keys()):
            icon = "✅" if p in available else "❌"
            status_text += f"{icon} {p.capitalize()}\n"
        return status_text

    async def send_telegram_alert(self, chat_id: int, text: str) -> None:
        if self.telegram_bot is None:
            logger.warning(
                "Telegram bot not configured; dropping alert to chat %s", chat_id
            )
            return
        for chunk in _chunk_text(text):
            await self.telegram_bot.send_message(chat_id=chat_id, text=chunk)

    async def send_discord_webhook_alert(self, webhook_url: str, text: str) -> None:
        chunks = _chunk_text(text, max_len=DISCORD_MAX_LEN)
        async with httpx.AsyncClient(timeout=20.0) as client:
            for chunk in chunks:
                try:
                    await client.post(
                        webhook_url,
                        json={"content": chunk},
                        headers={"User-Agent": "SocialOSINTAgent"},
                    )
                except Exception:
                    logger.exception("Failed to send Discord webhook alert.")

    async def send_discord_channel_alert(self, channel_id: int, text: str) -> None:
        if self.discord_bot is None:
            logger.warning(
                "Discord bot not configured; dropping alert to channel %s", channel_id
            )
            return
        from .discord_handler import send_discord_channel_alert as _send

        if isinstance(text, (str, bytes)):
            await _send(self.discord_bot, channel_id, text)
        else:
            # Assume it's an embed
            channel = self.discord_bot.get_channel(channel_id)
            if channel is None:
                channel = await self.discord_bot.fetch_channel(channel_id)
            await channel.send(embed=text)

    async def send_rule_alert(self, rule: Dict[str, Any], text: str) -> None:
        alert_type = rule.get("alert_type")
        alert_channel = rule.get("alert_channel")

        if alert_type is None:
            if isinstance(alert_channel, int) or (
                isinstance(alert_channel, str) and alert_channel.isdigit()
            ):
                alert_type = "telegram"
            elif isinstance(alert_channel, str) and alert_channel.startswith("http"):
                alert_type = "discord"
            else:
                alert_type = "discord_channel"

        if alert_type == "telegram":
            if alert_channel is None:
                logger.warning("Telegram alert_channel is None; dropping.")
                return
            chat_id = int(alert_channel)
            await self.send_telegram_alert(chat_id, text)
        elif alert_type == "discord_channel":
            if alert_channel is None:
                logger.warning("Discord channel alert_channel is None; dropping.")
                return
            channel_id = int(alert_channel)
            await self.send_discord_channel_alert(channel_id, text)
        elif alert_type == "discord":
            if alert_channel is None:
                logger.warning("Discord webhook alert_channel is None; dropping.")
                return
            webhook_url = str(alert_channel)
            await self.send_discord_webhook_alert(webhook_url, text)
        else:
            logger.warning("Unknown alert_type=%r; dropping alert.", alert_type)

    def _fetch_target_posts(
        self,
        platform: str,
        username: str,
    ) -> Optional[Dict[str, Any]]:
        if not (fetcher := FETCHERS.get(platform)):
            return None

        client = None
        try:
            client = self.agent.client_manager.get_platform_client(platform)
        except Exception:
            logger.exception(
                "Failed to initialize platform client for %s/%s", platform, username
            )
            return None

        kwargs: Dict[str, Any] = {
            "username": username,
            "cache": self.agent.cache,
            "force_refresh": True,
            "fetch_limit": self.fetch_limit,
            "allow_external_media": getattr(
                self.agent.args, "unsafe_allow_external_media", False
            ),
        }

        platforms_requiring_client = ["twitter", "reddit", "bluesky"]
        if platform == "mastodon":
            kwargs["clients"], kwargs["default_client"] = client
        elif platform in platforms_requiring_client:
            kwargs["client"] = client

        return fetcher(**kwargs)

    async def _evaluate_rule(
        self, session_id: str, session_name: str, rule: Dict[str, Any]
    ) -> bool:
        enabled = bool(rule.get("enabled", True))
        if not enabled:
            return False

        target = str(rule.get("target", "")).strip()
        condition = str(rule.get("condition", "")).strip()
        alert_channel = rule.get("alert_channel")
        if not target or not condition or alert_channel is None:
            return False

        try:
            platform, username = _parse_target(target)
        except ValueError:
            return False

        last_seen = _parse_dt(
            rule.get("last_seen_post_created_at") or rule.get("created_at")
        )

        user_data = await asyncio.to_thread(
            self._fetch_target_posts, platform, username
        )
        if not user_data:
            return False

        posts: List[Dict[str, Any]] = user_data.get("posts", []) or []
        if not posts:
            return False

        new_posts = [p for p in posts if get_sort_key(p, "created_at") > last_seen]
        if not new_posts:
            return False

        new_posts_for_triage = new_posts[: self.triage_post_limit]
        for p in new_posts_for_triage:
            p["platform"] = platform

        triage_posts_ts = max(get_sort_key(p, "created_at") for p in new_posts)
        triage_posts_ts_iso = triage_posts_ts.isoformat()

        match, details = await asyncio.to_thread(
            self.agent.llm.run_triage_evaluation,
            new_posts_for_triage,
            condition,
        )

        rule["last_seen_post_created_at"] = triage_posts_ts_iso
        rule["last_checked_at"] = datetime.now(timezone.utc).isoformat()

        if details.get("quarantined"):
            warnings_preview = details.get("security_warnings") or []
            warn_excerpt = (
                warnings_preview[0] if warnings_preview else "injected content detected"
            )
            msg = (
                "\u26a0\ufe0f Prompt Injection attempt detected in monitored evidence.\n"
                f"Target: {target}\n"
                f"Condition: {condition}\n"
                f"Reason: {details.get('reason', '')}\n"
                f"Example: {warn_excerpt}\n"
            )
            logger.info("Quarantined monitoring rule alert sent for %s", target)
            await self.send_rule_alert(rule=rule, text=msg)
            return True

        if not match:
            return True

        matched_keywords = details.get("matched_keywords") or []
        matched_keywords_str = (
            ", ".join(matched_keywords) if matched_keywords else "n/a"
        )

        snippet_lines: List[str] = []
        for p in new_posts_for_triage[:3]:
            created = get_sort_key(p, "created_at").strftime("%Y-%m-%d %H:%M UTC")
            post_id = str(p.get("id") or "")
            text = (p.get("text") or "").strip().replace("\n", " ")[:180]
            snippet_lines.append(f"- {created} {post_id}: {text}")

        msg = (
            "\U0001f50e OSINT Monitoring match\n"
            f"Target: {target}\n"
            f"Condition: {condition}\n"
            f"Reason: {details.get('reason', '')}\n"
            f"Matched keywords: {matched_keywords_str}\n"
            "\n"
            "Matched evidence snippets:\n" + "\n".join(snippet_lines) + "\n"
        )
        logger.info("Monitoring match alert sent for %s", target)
        await self.send_rule_alert(rule=rule, text=msg)
        return True

    async def run_forever(self) -> None:
        # Start startup health check as a background task so it doesn't block evaluation
        asyncio.create_task(self._send_startup_health_checks())

        while True:
            try:
                await self._run_once()
            except Exception as e:
                logger.exception("Watcher iteration failed: %s", e)
            await asyncio.sleep(self.poll_interval_seconds)

    async def _send_startup_health_checks(self) -> None:
        """Unified startup health check for all active bots."""
        if self.startup_check_sent:
            return
            
        # 1. Handle Telegram (can send immediately)
        health_telegram = os.getenv("TELEGRAM_HEALTH_CHECK_CHAT_ID")
        if health_telegram and self.telegram_bot:
            try:
                status = self._get_platform_status_text()
                msg = f"🟢 **OSINT Relay Online (Telegram)**\n\n**Platforms:**\n{status}\n**System:**\n• Version: 1.0.0"
                await self.send_telegram_alert(int(health_telegram), msg)
                logger.info("Sent Telegram startup health check.")
            except Exception as e:
                logger.warning(f"Failed to send Telegram startup check: {e}")

        # 2. Handle Discord (must wait for bot to be ready)
        health_discord = os.getenv("DISCORD_HEALTH_CHECK_CHANNEL_ID")
        if health_discord and self.discord_bot:
            try:
                # Wait up to 30 seconds for Discord to connect
                for _ in range(30):
                    if getattr(self.discord_bot, "is_ready", lambda: False)():
                        break
                    await asyncio.sleep(1)
                
                if self.discord_bot.is_ready():
                    import discord
                    status = self._get_platform_status_text()
                    embed = discord.Embed(
                        title="🟢 OSINT Relay Online (Discord)",
                        description="Bot has started and is ready for commands.",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.add_field(name="Platforms", value=status, inline=True)
                    embed.add_field(name="System", value=f"**Latency:** {round(self.discord_bot.latency * 1000)}ms\n**Version:** 1.0.0", inline=True)
                    
                    await self.send_discord_channel_alert(int(health_discord), embed)
                    logger.info("Sent Discord startup health check.")
            except Exception as e:
                logger.warning(f"Failed to send Discord startup check: {e}")

        self.startup_check_sent = True

    async def _send_periodic_status(self) -> None:
        """Send a periodic 'Bot is online' status message."""
        now = datetime.now(timezone.utc)
        
        # Check if 30 minutes (1800 seconds) have passed
        if self.last_periodic_status_at and (now - self.last_periodic_status_at).total_seconds() < 1800:
            return
            
        self.last_periodic_status_at = now
        
        status_msg = f"⏱ **Periodic Status Check**\nBot is online and monitoring. Next check in 30 minutes.\nTimestamp: `{now.strftime('%Y-%m-%d %H:%M:%S UTC')}`"
        
        # Discord Channel notification
        health_discord = os.getenv("DISCORD_HEALTH_CHECK_CHANNEL_ID")
        if health_discord and self.discord_bot:
            try:
                await self.send_discord_channel_alert(int(health_discord), status_msg)
                logger.info("Sent periodic status check to Discord.")
            except Exception as e:
                logger.warning(f"Failed to send periodic status to Discord: {e}")
                
        # Telegram notification
        health_telegram = os.getenv("TELEGRAM_HEALTH_CHECK_CHAT_ID")
        if health_telegram and self.telegram_bot:
            try:
                await self.send_telegram_alert(int(health_telegram), status_msg)
                logger.info("Sent periodic status check to Telegram.")
            except Exception as e:
                logger.warning(f"Failed to send periodic status to Telegram: {e}")

    async def _run_once(self) -> None:
        # Periodic status check
        await self._send_periodic_status()

        any_updates = 0
        for path in self.session_manager.sessions_dir.glob("*.json"):
            session_id = path.stem
            session = self.session_manager.load(session_id)
            if not session:
                continue

            if not session.monitoring_rules:
                continue

            session_changed = False
            for rule in session.monitoring_rules:
                updated = await self._evaluate_rule(session_id, session.name, rule)
                if updated:
                    session_changed = True
                    any_updates += 1

            if session_changed:
                self.session_manager.save(session)

        if any_updates:
            logger.debug("Watcher advanced %s monitoring rule(s)", any_updates)


async def run_watcher_forever(
    *,
    agent: Any,
    session_manager: SessionManager,
    telegram_bot: Any = None,
    discord_bot: Any = None,
    poll_interval_seconds: Optional[int] = None,
    fetch_limit: Optional[int] = None,
    triage_post_limit: Optional[int] = None,
) -> None:
    interval = poll_interval_seconds or int(
        os.getenv("OSINT_WATCH_INTERVAL_SECONDS", "300")
    )
    f_limit = fetch_limit or int(os.getenv("OSINT_WATCH_FETCH_LIMIT", "20"))
    t_limit = triage_post_limit or int(os.getenv("OSINT_WATCH_TRIAGE_POST_LIMIT", "8"))

    watcher = MonitoringWatcher(
        agent=agent,
        session_manager=session_manager,
        telegram_bot=telegram_bot,
        discord_bot=discord_bot,
        poll_interval_seconds=interval,
        fetch_limit=f_limit,
        triage_post_limit=t_limit,
    )
    await watcher.run_forever()
