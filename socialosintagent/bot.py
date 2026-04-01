"""
ChatOps daemon entrypoint (Phases 3-4).

Runs:
  - aiogram polling for Telegram commands (/analyze, /monitor, /help)
  - discord.py bot for Discord commands (/analyze, /monitor, /help)
  - the background monitoring watcher loop

At least one of TELEGRAM_BOT_TOKEN or DISCORD_BOT_TOKEN must be set.
Both can run simultaneously in the same process.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from .telegram_handler import build_agent, run_setup_logging, _register_handlers
from .session_manager import SessionManager
from .watcher import run_watcher_forever

logger = logging.getLogger("SocialOSINTAgent.bot")


def _build_agent():
    return build_agent()


async def _run_telegram(agent, session_manager: SessionManager) -> None:
    from aiogram import Bot, Dispatcher

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return

    bot = Bot(token=token)
    dp = Dispatcher()
    _register_handlers(dp, agent)

    watcher_task = asyncio.create_task(
        run_watcher_forever(
            agent=agent,
            session_manager=session_manager,
            telegram_bot=bot,
        )
    )

    try:
        logger.info("Starting Telegram polling + background watcher.")
        await dp.start_polling(bot)
    finally:
        watcher_task.cancel()
        with suppress(asyncio.CancelledError):
            await watcher_task


async def _run_discord(agent, session_manager: SessionManager) -> None:
    from .discord_handler import DiscordChatOpsBot, send_discord_channel_alert

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        return

    discord_bot = DiscordChatOpsBot(agent)

    watcher_task = asyncio.create_task(
        run_watcher_forever(
            agent=agent,
            session_manager=session_manager,
            discord_bot=discord_bot,
        )
    )

    try:
        logger.info("Starting Discord bot + background watcher.")
        async with discord_bot:
            await discord_bot.start(token)
    finally:
        watcher_task.cancel()
        with suppress(asyncio.CancelledError):
            await watcher_task


async def main_async() -> None:
    load_dotenv()
    run_setup_logging()

    has_telegram = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    has_discord = bool(os.getenv("DISCORD_BOT_TOKEN"))

    if not has_telegram and not has_discord:
        logger.error(
            "At least one of TELEGRAM_BOT_TOKEN or DISCORD_BOT_TOKEN must be set."
        )
        sys.exit(1)

    agent = _build_agent()
    session_manager = SessionManager(Path("data"))

    tasks = []
    if has_telegram:
        tasks.append(asyncio.create_task(_run_telegram(agent, session_manager)))
    if has_discord:
        tasks.append(asyncio.create_task(_run_discord(agent, session_manager)))

    await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
