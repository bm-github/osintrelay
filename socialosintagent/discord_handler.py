"""
Discord ChatOps entrypoint: drive SocialOSINTAgent from a Discord bot.

Environment:
    DISCORD_BOT_TOKEN -- from the Discord Developer Portal

Run:
    python -m socialosintagent.discord_handler

Commands:
    /analyze <platform>/<username> -- default OSINT query, reply with Markdown
    /analyze <platform>/<username> <custom query> -- custom query analysis
    /refresh <platform>/<username> -- force refresh and analyze
    /monitor <platform>/<username> for keywords "crypto, wallet" -- continuous monitoring
    /listmonitors -- list active monitoring rules
    /stopmonitor <rule_id> -- stop a monitoring rule
    /contacts <platform>/<username> -- extract network contacts
    /status -- bot health and platform status
    /sessions -- list active sessions
    /help -- usage
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands as dcommands
from dotenv import load_dotenv

from socialosintagent.analyzer import SocialOSINTAgent
from socialosintagent.cache import CacheManager
from socialosintagent.chatops import build_agent as chatops_build_agent
from socialosintagent.client_manager import ClientManager
from socialosintagent.llm import LLMAnalyzer
from socialosintagent.platforms import FETCHERS
from socialosintagent.session_manager import SessionManager
from socialosintagent.utils import sanitize_username

logger = logging.getLogger("SocialOSINTAgent.discord")

DISCORD_MAX_LEN = 1900

DEFAULT_ANALYSIS_QUERY = (
    "Provide a structured OSINT analysis of this user: summarize public persona, "
    "recurring topics, communication style, and any notable patterns visible in "
    "the collected posts and profile. Use clear Markdown headings."
)


def chunk_discord_text(text: str, max_len: int = DISCORD_MAX_LEN) -> List[str]:
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


def parse_analyze_command(text: str) -> Optional[Tuple[str, str, Optional[str]]]:
    parts = (text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None
    arg = parts[1].strip()
    if "/" not in arg:
        return None

    # Split by "/" once to get platform
    platform_raw, rest = arg.split("/", 1)
    platform = platform_raw.lower().strip()

    # Split rest by space to get username and optional query
    rest_parts = rest.split(maxsplit=1)
    username_raw = rest_parts[0].strip()
    query = rest_parts[1].strip() if len(rest_parts) > 1 else None

    if not platform or not username_raw:
        return None

    username = sanitize_username(username_raw)
    if not username:
        return None

    return platform, username, query


def _strip_outer_quotes(text: str) -> str:
    t = (text or "").strip()
    if len(t) >= 2 and ((t[0] == t[-1] == '"') or (t[0] == t[-1] == "'")):
        return t[1:-1].strip()
    return t


def parse_monitor_command(text: str) -> Optional[Tuple[str, str, List[str], str]]:
    raw = (text or "").strip()
    if not raw.startswith("/monitor"):
        return None

    parts = raw.split(maxsplit=3)
    if len(parts) < 4:
        return None

    arg_platform_user = parts[1]
    if "/" not in arg_platform_user:
        return None
    platform_raw, user_raw = arg_platform_user.split("/", 1)
    platform = platform_raw.lower().strip()
    username = sanitize_username(user_raw.strip())
    if not platform or not username:
        return None

    remaining = parts[3].strip()
    if not remaining.lower().startswith("keywords"):
        return None

    keywords_raw = remaining[len("keywords") :].strip()
    keywords_raw = _strip_outer_quotes(keywords_raw)

    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    if not keywords:
        return None

    condition = f"keywords: {', '.join(keywords)}"
    return platform, username, keywords, condition


def build_agent() -> SocialOSINTAgent:
    """Build agent using shared chatops factory (DRY)."""
    return chatops_build_agent(offline=False)


def run_setup_logging() -> None:
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / "discord_chatops.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stderr),
        ],
    )
    logging.getLogger("SocialOSINTAgent").setLevel(logging.INFO)


class DiscordChatOpsBot(dcommands.Bot):
    def __init__(self, agent: SocialOSINTAgent, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix="?", intents=intents, help_command=None, **kwargs
        )
        self.agent = agent
        self.start_time = datetime.now(timezone.utc)

    async def on_ready(self) -> None:
        logger.info(f"Bot logged in as {self.user} (ID: {self.user.id})")

    async def setup_hook(self) -> None:
        await self.add_cog(AnalyzeCog(self))
        await self.add_cog(RefreshCog(self))
        await self.add_cog(MonitorCog(self))
        await self.add_cog(MonitorControlCog(self))
        await self.add_cog(ContactsCog(self))
        await self.add_cog(StatusCog(self))
        await self.add_cog(SessionsCog(self))
        await self.add_cog(HelpCog(self))
        await self.tree.sync()


class HelpCog(dcommands.Cog):
    def __init__(self, bot: DiscordChatOpsBot):
        self.bot = bot

    async def _send_help(
        self, target_obj: discord.Message | discord.Interaction
    ) -> None:
        send = (
            target_obj.followup.send
            if isinstance(target_obj, discord.Interaction)
            else target_obj.channel.send
        )
        msg = (
            "**OSINT ChatOps bot (Slash Command Edition)**\n\n"
            "**Analysis Commands:**\n"
            "`/analyze platform username [query]` — default or custom OSINT query\n"
            "`/refresh platform username [query]` — force refresh + analyze\n"
            "`/contacts platform username` — extract network contacts\n\n"
            "**Monitoring Commands:**\n"
            '`/monitor platform username keywords="crypto, wallet"`\n'
            "`/listmonitors` — list active monitoring rules\n"
            "`/stopmonitor rule_id` — stop a monitoring rule\n\n"
            "**Management Commands:**\n"
            "`/status` — bot health and platform status\n"
            "`/sessions` — list active sessions\n\n"
            "Supported platforms: "
            f"{', '.join(sorted(FETCHERS.keys()))}\n\n"
            "Same engine as the CLI; ensure LLM and platform credentials are in `.env`."
        )
        await send(msg)

    @dcommands.command(name="help", description="Show usage instructions")
    async def help_command(self, ctx: dcommands.Context) -> None:
        await self._send_help(ctx.message)

    @app_commands.command(name="help", description="Show usage instructions")
    async def help_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._send_help(interaction)


class AnalyzeCog(dcommands.Cog):
    def __init__(self, bot: DiscordChatOpsBot):
        self.bot = bot

    def _build_vision_error_summary(self, vision_stats: Dict[str, Any]) -> str:
        """Build user-friendly error summary for Discord."""
        total = vision_stats.get("total", 0)
        analyzed = vision_stats.get("analyzed", 0)
        failed = vision_stats.get("failed", 0)
        skipped = vision_stats.get("skipped", 0)
        error_summaries = vision_stats.get("error_summaries", [])

        msg = "📸 **Image Analysis Summary:**\n\n"
        msg += f"✅ {analyzed}/{total} images analyzed successfully\n"

        if failed > 0:
            msg += f"❌ {failed} images failed\n"
        if skipped > 0:
            msg += f"⏭️ {skipped} images skipped\n"

        if error_summaries:
            msg += "\n**Issues:**\n"
            for summary in error_summaries[:5]:  # Limit to top 5 to avoid spam
                msg += f"• {summary}\n"
            if len(error_summaries) > 5:
                msg += f"\n... and {len(error_summaries) - 5} more issues. Check logs for details.\n"

        return msg

    async def _perform_analysis(
        self,
        target_message: discord.Message | discord.Interaction,
        platform: str,
        username: str,
        query: Optional[str],
        force_refresh: bool = False,
    ) -> None:
        # Determine sender functions
        if isinstance(target_message, discord.Interaction):
            send = target_message.followup.send
            edit = target_message.edit_original_response
        else:
            send = target_message.channel.send
            edit = target_message.edit

        if platform not in FETCHERS:
            await send(
                f"Unknown platform `{platform}`. "
                f"Known: {', '.join(sorted(FETCHERS.keys()))}"
            )
            return

        available = self.bot.agent.client_manager.get_available_platforms(
            check_creds=True
        )
        if platform not in available:
            await send(
                f"Platform `{platform}` is not configured (missing credentials). "
                f"Configured: {', '.join(available) or 'none'}"
            )
            return

        # Status message
        content = (
            f"Running analysis for `{platform}/{username}`... (this may take a minute)"
        )
        if isinstance(target_message, discord.Interaction):
            status_msg = await target_message.original_response()
            await edit(content=content)
        else:
            status_msg = await send(content)

        def run_analysis():
            return self.bot.agent.analyze(
                {platform: [username]},
                query or DEFAULT_ANALYSIS_QUERY,
                force_refresh=force_refresh,
                fetch_options={"default_count": 50},
            )

        try:
            result = await asyncio.to_thread(run_analysis)
        except Exception as e:
            logger.exception("analyze failed: %s", e)
            await edit(content=f"Analysis crashed: `{type(e).__name__}: {e}`")
            return

        if result.get("error"):
            report = result.get("report", "Unknown error")
            if "rate limit" in report.lower():
                await edit(
                    content="⚠️ **Rate Limit Hit:** The analysis was rate-limited. Please wait a few minutes and try again."
                )
            else:
                await edit(
                    content=f"Analysis failed:\n\n{report[: DISCORD_MAX_LEN - 100]}"
                )
            return

        report = result.get("report") or ""
        chunks = chunk_discord_text(report)
        for i, chunk in enumerate(chunks):
            prefix = f"(part {i + 1}/{len(chunks)})\n\n" if len(chunks) > 1 else ""
            await send(prefix + chunk)

        # Send image processing error summary if there were failures
        vision_stats = result.get("metadata", {}).get("vision_stats", {})
        if vision_stats.get("failed", 0) > 0 or vision_stats.get("skipped", 0) > 0:
            error_msg = self._build_vision_error_summary(vision_stats)
            await send(error_msg)

    @dcommands.command(name="analyze", description="Run OSINT analysis on a target")
    async def analyze_command(self, ctx: dcommands.Context, *, args: str = "") -> None:
        full_text = f"/analyze {args}" if args else "/analyze"
        parsed = parse_analyze_command(full_text)
        if not parsed:
            await ctx.send(
                "Usage: `/analyze <platform> <username>`\n"
                "Example: `/analyze twitter username`"
            )
            return

        platform, username, query = parsed
        await self._perform_analysis(ctx.message, platform, username, query, False)

    @app_commands.command(name="analyze", description="Run OSINT analysis on a target")
    @app_commands.describe(
        platform="Platform (e.g. bluesky, reddit, twitter)",
        username="Username to analyze",
        query="Specific question or custom query for the LLM (optional)",
    )
    async def analyze_slash(
        self,
        interaction: discord.Interaction,
        platform: str,
        username: str,
        query: Optional[str] = None,
    ) -> None:
        await interaction.response.defer()
        await self._perform_analysis(interaction, platform, username, query, False)

    @analyze_slash.autocomplete("platform")
    async def platform_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        available = self.bot.agent.client_manager.get_available_platforms(
            check_creds=True
        )
        return [
            app_commands.Choice(name=p.capitalize(), value=p)
            for p in available
            if current.lower() in p.lower()
        ][:25]


class RefreshCog(dcommands.Cog):
    def __init__(self, bot: DiscordChatOpsBot):
        self.bot = bot

    @dcommands.command(name="refresh", description="Force refresh and analyze a target")
    async def refresh_command(self, ctx: dcommands.Context, *, args: str = "") -> None:
        full_text = f"/refresh {args}" if args else "/refresh"
        parsed = parse_analyze_command(full_text)
        if not parsed:
            await ctx.send(
                "Usage: `/refresh <platform> <username>`\n"
                "Example: `/refresh twitter username`"
            )
            return

        platform, username, query = parsed
        analyze_cog = self.bot.get_cog("AnalyzeCog")
        if analyze_cog:
            await analyze_cog._perform_analysis(
                ctx.message, platform, username, query, True
            )
        else:
            await ctx.send("AnalyzeCog not found.")

    @app_commands.command(
        name="refresh", description="Force refresh and analyze a target"
    )
    @app_commands.describe(
        platform="Platform (e.g. bluesky, reddit, twitter)",
        username="Username to analyze",
        query="Specific question or custom query for the LLM (optional)",
    )
    async def refresh_slash(
        self,
        interaction: discord.Interaction,
        platform: str,
        username: str,
        query: Optional[str] = None,
    ) -> None:
        await interaction.response.defer()
        analyze_cog = self.bot.get_cog("AnalyzeCog")
        if analyze_cog:
            await analyze_cog._perform_analysis(
                interaction, platform, username, query, True
            )
        else:
            await interaction.followup.send("AnalyzeCog not found.")

    @refresh_slash.autocomplete("platform")
    async def platform_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        available = self.bot.agent.client_manager.get_available_platforms(
            check_creds=True
        )
        return [
            app_commands.Choice(name=p.capitalize(), value=p)
            for p in available
            if current.lower() in p.lower()
        ][:25]


class MonitorCog(dcommands.Cog):
    def __init__(self, bot: DiscordChatOpsBot):
        self.bot = bot

    async def _perform_monitor(
        self,
        target_obj: discord.Message | discord.Interaction,
        platform: str,
        username: str,
        keywords: List[str],
        condition: str,
    ) -> None:
        send = (
            target_obj.followup.send
            if isinstance(target_obj, discord.Interaction)
            else target_obj.channel.send
        )

        if platform not in FETCHERS:
            await send(
                f"Unknown platform `{platform}`. "
                f"Known: {', '.join(sorted(FETCHERS.keys()))}"
            )
            return

        available = self.bot.agent.client_manager.get_available_platforms(
            check_creds=True
        )
        if platform not in available:
            await send(
                f"Platform `{platform}` is not configured (missing credentials). "
                f"Configured: {', '.join(available) or 'none'}"
            )
            return

        session_manager = SessionManager(Path("data"))
        channel_id = (
            target_obj.channel_id
            if isinstance(target_obj, discord.Interaction)
            else target_obj.channel.id
        )
        target = f"{platform}/{username}"
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            for path in session_manager.sessions_dir.glob("*.json"):
                session = session_manager.load(path.stem)
                if not session or not session.monitoring_rules:
                    continue
                for rule in session.monitoring_rules:
                    if (
                        rule.get("alert_type") == "discord_channel"
                        and rule.get("alert_channel") == channel_id
                        and rule.get("target") == target
                        and rule.get("condition") == condition
                    ):
                        await send(
                            f"Already monitoring `{target}` for `{condition}` in this channel."
                        )
                        return
        except Exception:
            logger.exception("De-duplication scan failed; proceeding.")

        session = session_manager.create(
            name=f"Discord Monitor: {target}",
            platforms={platform: [username]},
            fetch_options={"default_count": 50, "targets": {}},
        )

        rule = {
            "rule_id": uuid.uuid4().hex[:8],
            "session_id": session.session_id,
            "target": target,
            "condition": condition,
            "alert_type": "discord_channel",
            "alert_channel": channel_id,
            "enabled": True,
            "created_at": now_iso,
            "last_seen_post_created_at": now_iso,
        }
        session.monitoring_rules.append(rule)
        session_manager.save(session)

        await send(
            "Monitoring enabled.\n"
            f"Target: `{target}`\n"
            f"Keywords: `{', '.join(keywords)}`\n"
            f"Rule ID: `{rule['rule_id']}`\n"
            "I will check for new posts in the background and only alert you on matches."
        )

    @dcommands.command(
        name="monitor",
        description="Start continuous monitoring for keywords",
    )
    async def monitor_command(self, ctx: dcommands.Context, *, args: str = "") -> None:
        full_text = f"/monitor {args}" if args else "/monitor"
        parsed = parse_monitor_command(full_text)
        if not parsed:
            await ctx.send(
                "Usage: `/monitor <platform> <username> <keywords>`\n"
                "Example: `/monitor bluesky username crypto, wallet`"
            )
            return

        platform, username, keywords, condition = parsed
        await self._perform_monitor(
            ctx.message, platform, username, keywords, condition
        )

    @app_commands.command(
        name="monitor",
        description="Start continuous monitoring for keywords",
    )
    @app_commands.describe(
        platform="Platform (e.g. bluesky, reddit, twitter)",
        username="Username to monitor",
        keywords="Comma-separated keywords (e.g. crypto, wallet)",
    )
    async def monitor_slash(
        self,
        interaction: discord.Interaction,
        platform: str,
        username: str,
        keywords: str,
    ) -> None:
        await interaction.response.defer()
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        if not keyword_list:
            await interaction.followup.send("Please provide at least one keyword.")
            return

        condition = f"keywords: {', '.join(keyword_list)}"
        username = sanitize_username(username.strip())
        await self._perform_monitor(
            interaction, platform.lower().strip(), username, keyword_list, condition
        )

    @monitor_slash.autocomplete("platform")
    async def platform_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        available = self.bot.agent.client_manager.get_available_platforms(
            check_creds=True
        )
        return [
            app_commands.Choice(name=p.capitalize(), value=p)
            for p in available
            if current.lower() in p.lower()
        ][:25]


class MonitorControlCog(dcommands.Cog):
    def __init__(self, bot: DiscordChatOpsBot):
        self.bot = bot

    async def _list_monitors(
        self, target_obj: discord.Message | discord.Interaction
    ) -> None:
        send = (
            target_obj.followup.send
            if isinstance(target_obj, discord.Interaction)
            else target_obj.channel.send
        )
        session_manager = SessionManager(Path("data"))
        rules = []
        try:
            for path in session_manager.sessions_dir.glob("*.json"):
                session = session_manager.load(path.stem)
                if not session or not session.monitoring_rules:
                    continue
                for rule in session.monitoring_rules:
                    if rule.get("enabled"):
                        rules.append(rule)
        except Exception:
            logger.exception("Failed to list monitoring rules")
            await send("Error listing monitoring rules.")
            return

        if not rules:
            await send("No active monitoring rules.")
            return

        msg = "**Active Monitoring Rules:**\n\n"
        for rule in rules:
            msg += (
                f"• `{rule['rule_id']}` — Target: `{rule.get('target', '?')}`\n"
                f"  Condition: `{rule.get('condition', '?')}`\n"
                f"  Channel: `{rule.get('alert_channel', '?')}`\n"
                f"  Created: `{rule.get('created_at', '?')[:19]}`\n\n"
            )
        await send(msg)

    @dcommands.command(name="listmonitors", description="List active monitoring rules")
    async def listmonitors_command(self, ctx: dcommands.Context) -> None:
        await self._list_monitors(ctx.message)

    @app_commands.command(
        name="listmonitors", description="List active monitoring rules"
    )
    async def listmonitors_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._list_monitors(interaction)

    async def _stop_monitor(
        self, target_obj: discord.Message | discord.Interaction, rule_id: str
    ) -> None:
        send = (
            target_obj.followup.send
            if isinstance(target_obj, discord.Interaction)
            else target_obj.channel.send
        )
        if not rule_id.strip():
            await send(
                "Usage: `/stopmonitor <rule_id>`\nUse `/listmonitors` to find rule IDs."
            )
            return

        rule_id = rule_id.strip()
        session_manager = SessionManager(Path("data"))
        found = False

        try:
            for path in session_manager.sessions_dir.glob("*.json"):
                session = session_manager.load(path.stem)
                if not session or not session.monitoring_rules:
                    continue
                for rule in session.monitoring_rules:
                    if rule.get("rule_id") == rule_id:
                        rule["enabled"] = False
                        session_manager.save(session)
                        found = True
                        break
                if found:
                    break
        except Exception:
            logger.exception("Failed to stop monitoring rule %s", rule_id)
            await send(f"Error stopping rule `{rule_id}`.")
            return

        if found:
            await send(f"Monitoring rule `{rule_id}` stopped.")
        else:
            await send(f"Rule `{rule_id}` not found.")

    @dcommands.command(name="stopmonitor", description="Stop a monitoring rule by ID")
    async def stopmonitor_command(
        self, ctx: dcommands.Context, *, rule_id: str = ""
    ) -> None:
        await self._stop_monitor(ctx.message, rule_id)

    @app_commands.command(
        name="stopmonitor", description="Stop a monitoring rule by ID"
    )
    @app_commands.describe(rule_id="The 8-character ID of the rule to stop")
    async def stopmonitor_slash(
        self, interaction: discord.Interaction, rule_id: str
    ) -> None:
        await interaction.response.defer()
        await self._stop_monitor(interaction, rule_id)


class ContactsCog(dcommands.Cog):
    def __init__(self, bot: DiscordChatOpsBot):
        self.bot = bot

    async def _perform_contacts(
        self,
        target_obj: discord.Message | discord.Interaction,
        platform: str,
        username: str,
    ) -> None:
        send = (
            target_obj.followup.send
            if isinstance(target_obj, discord.Interaction)
            else target_obj.channel.send
        )

        if platform not in FETCHERS:
            await send(
                f"Unknown platform `{platform}`. "
                f"Known: {', '.join(sorted(FETCHERS.keys()))}"
            )
            return

        # Status message
        content = f"Extracting contacts for `{platform}/{username}`..."
        if isinstance(target_obj, discord.Interaction):
            await target_obj.edit_original_response(content=content)
        else:
            status_msg = await send(content)

        def run_contacts():
            return self.bot.agent.get_contacts({platform: [username]})

        try:
            contacts = await asyncio.to_thread(run_contacts)
        except Exception as e:
            logger.exception("contacts extraction failed: %s", e)
            error_msg = f"Contact extraction failed: `{type(e).__name__}: {e}`"
            if isinstance(target_obj, discord.Interaction):
                await target_obj.edit_original_response(content=error_msg)
            else:
                await status_msg.edit(content=error_msg)
            return

        if not contacts:
            msg = f"No contacts found for `{platform}/{username}`."
            if isinstance(target_obj, discord.Interaction):
                await target_obj.edit_original_response(content=msg)
            else:
                await status_msg.edit(content=msg)
            return

        msg = f"**Network Contacts for `{platform}/{username}`:**\n\n"
        for contact in contacts[:20]:
            msg += (
                f"• `{contact.platform}/{contact.username}` — "
                f"Weight: `{contact.weight}` — "
                f"Types: `{', '.join(contact.interaction_types)}`\n"
            )
        if len(contacts) > 20:
            msg += f"\n... and {len(contacts) - 20} more contacts."

        if isinstance(target_obj, discord.Interaction):
            await target_obj.edit_original_response(content="Contacts extracted.")

        chunks = chunk_discord_text(msg)
        for chunk in chunks:
            await send(chunk)

    @dcommands.command(
        name="contacts", description="Extract network contacts for a target"
    )
    async def contacts_command(self, ctx: dcommands.Context, *, args: str = "") -> None:
        full_text = f"/contacts {args}" if args else "/contacts"
        parsed = parse_analyze_command(full_text)
        if not parsed:
            await ctx.send(
                "Usage: `/contacts <platform> <username>`\n"
                "Example: `/contacts twitter username`"
            )
            return

        platform, username, _ = parsed
        await self._perform_contacts(ctx.message, platform, username)

    @app_commands.command(
        name="contacts", description="Extract network contacts for a target"
    )
    @app_commands.describe(
        platform="Platform (e.g. bluesky, reddit, twitter)",
        username="Username to extract contacts for",
    )
    async def contacts_slash(
        self, interaction: discord.Interaction, platform: str, username: str
    ) -> None:
        await interaction.response.defer()
        await self._perform_contacts(
            interaction, platform.lower().strip(), sanitize_username(username.strip())
        )

    @contacts_slash.autocomplete("platform")
    async def platform_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        available = list(FETCHERS.keys())
        return [
            app_commands.Choice(name=p.capitalize(), value=p)
            for p in available
            if current.lower() in p.lower()
        ][:25]


class StatusCog(dcommands.Cog):
    def __init__(self, bot: DiscordChatOpsBot):
        self.bot = bot

    async def _send_status(
        self, target_obj: discord.Message | discord.Interaction
    ) -> None:
        send = (
            target_obj.followup.send
            if isinstance(target_obj, discord.Interaction)
            else target_obj.channel.send
        )
        try:
            available = self.bot.agent.client_manager.get_available_platforms(
                check_creds=True
            )
            unavailable = [p for p in FETCHERS if p not in available]

            msg = "**Bot Status:**\n\n"
            msg += f"• **Bot:** Online\n"
            msg += f"• **Latency:** {round(self.bot.latency * 1000)}ms\n"
            msg += f"• **Configured Platforms:** {', '.join(sorted(available)) or 'none'}\n"
            if unavailable:
                msg += f"• **Unconfigured:** {', '.join(sorted(unavailable))}\n"

            msg += f"\n**Supported Platforms:** {', '.join(sorted(FETCHERS.keys()))}\n"

            await send(msg)
        except Exception as e:
            logger.exception("status command failed: %s", e)
            await send(f"Status check failed: `{type(e).__name__}: {e}`")

    @dcommands.command(name="status", description="Bot health and platform status")
    async def status_command(self, ctx: dcommands.Context) -> None:
        await self._send_status(ctx.message)

    @app_commands.command(name="status", description="Bot health and platform status")
    async def status_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._send_status(interaction)


class SessionsCog(dcommands.Cog):
    def __init__(self, bot: DiscordChatOpsBot):
        self.bot = bot

    async def _send_sessions(
        self, target_obj: discord.Message | discord.Interaction
    ) -> None:
        send = (
            target_obj.followup.send
            if isinstance(target_obj, discord.Interaction)
            else target_obj.channel.send
        )
        session_manager = SessionManager(Path("data"))
        try:
            sessions = session_manager.list_all()
        except Exception as e:
            logger.exception("sessions list failed: %s", e)
            await send(f"Failed to list sessions: `{type(e).__name__}: {e}`")
            return

        if not sessions:
            await send("No active sessions.")
            return

        msg = "**Active Sessions:**\n\n"
        for s in sessions[:10]:
            msg += (
                f"• `{s['session_id'][:8]}` — **{s['name']}**\n"
                f"  Targets: `{s['target_count']}` — "
                f"Queries: `{s['query_count']}`\n"
                f"  Updated: `{s['updated_at'][:19]}`\n\n"
            )
        if len(sessions) > 10:
            msg += f"... and {len(sessions) - 10} more sessions."

        await send(msg)

    @dcommands.command(name="sessions", description="List active sessions")
    async def sessions_command(self, ctx: dcommands.Context) -> None:
        await self._send_sessions(ctx.message)

    @app_commands.command(name="sessions", description="List active sessions")
    async def sessions_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._send_sessions(interaction)


async def send_discord_channel_alert(
    bot: dcommands.Bot,
    channel_id: int,
    text: str,
) -> None:
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            logger.exception("Failed to fetch Discord channel %s", channel_id)
            return
    if not hasattr(channel, "send"):
        return
    for chunk in chunk_discord_text(text):
        try:
            await channel.send(chunk)
        except Exception:
            logger.exception("Failed to send Discord channel alert to %s", channel_id)


async def main_async() -> None:
    load_dotenv()
    run_setup_logging()

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN is not set.")
        sys.exit(1)

    try:
        agent = build_agent()
    except RuntimeError as e:
        logger.error("%s", e)
        sys.exit(1)

    bot = DiscordChatOpsBot(agent)
    logger.info("Starting Discord bot…")
    async with bot:
        await bot.start(token)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
