"""Lightweight ChatOps entrypoint module for SocialOSINTAgent.

This module provides a minimal API for driving analysis from bot frameworks
or external orchestrators (Discord/Telegram/Webhooks), without the interactive
CLI or full web dashboard code.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .analyzer import SocialOSINTAgent
from .cache import CacheManager
from .client_manager import ClientManager
from .llm import LLMAnalyzer
from .platforms import FETCHERS
from .utils import sanitize_username

logger = logging.getLogger("SocialOSINTAgent.chatops")

DEFAULT_ANALYSIS_QUERY = (
    "Provide a structured OSINT analysis of this user: summarize public persona, "
    "recurring topics, communication style, and any notable patterns visible in "
    "the collected posts and profile. Use clear Markdown headings."
)


def build_agent(offline: bool = False) -> SocialOSINTAgent:
    args = argparse.Namespace(
        offline=offline,
        no_auto_save=True,
        format="markdown",
        unsafe_allow_external_media=False,
    )

    base_dir = Path("data")
    cache_manager = CacheManager(base_dir, args.offline)
    llm_analyzer = LLMAnalyzer(args.offline)
    client_manager = ClientManager(args.offline)
    return SocialOSINTAgent(args, cache_manager, llm_analyzer, client_manager)


def analyze_target(
    agent: SocialOSINTAgent,
    platform: str,
    username: str,
    query: Optional[str] = None,
    force_refresh: bool = False,
    fetch_options: Optional[Dict[str, Dict[str, int]]] = None,
) -> Dict[str, object]:
    platform = platform.lower().strip()
    username = sanitize_username(username.strip())

    if not platform or not username:
        raise ValueError("platform and username must be non-empty")

    available = agent.client_manager.get_available_platforms(check_creds=True)
    if platform not in available:
        raise RuntimeError(
            f"Platform {platform!r} is not available, configured platforms: "
            f"{', '.join(sorted(available))}"
        )

    if platform not in FETCHERS:
        raise RuntimeError(
            f"Platform {platform!r} is not currently supported by fetchers"
        )

    query_text = (query or DEFAULT_ANALYSIS_QUERY).strip()
    if not query_text:
        raise ValueError("query must be non-empty")

    target_spec = {platform: [username]}
    result = agent.analyze(target_spec, query_text, force_refresh, fetch_options)
    return result


def main():
    parser = argparse.ArgumentParser(description="Lightweight SocialOSINTAgent ChatOps CLI")
    parser.add_argument("--platform", required=True, help="Platform name (e.g. twitter)")
    parser.add_argument("--username", required=True, help="Username to analyze")
    parser.add_argument("--query", default=DEFAULT_ANALYSIS_QUERY, help="NL query for analysis")
    parser.add_argument("--offline", action="store_true", help="Use offline cache only")
    parser.add_argument("--force-refresh", action="store_true", help="Force API fetch even if cache exists")
    parser.add_argument("--fetch-count", type=int, default=50, help="Default number of posts to fetch")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    agent = build_agent(offline=args.offline)
    fetch_options = {"default_count": max(1, args.fetch_count), "targets": {}}

    try:
        result = analyze_target(
            agent,
            args.platform,
            args.username,
            query=args.query,
            force_refresh=args.force_refresh,
            fetch_options=fetch_options,
        )

        if result.get("error"):
            logger.error("Analysis completed with error: %s", result.get("report"))
            sys.stderr.write(result.get("report", "") + "\n")
            sys.exit(2)

        print(result.get("report", ""))
        sys.exit(0)

    except Exception as exc:
        logger.critical("ChatOps analysis failed: %s", exc, exc_info=True)
        sys.stderr.write(str(exc) + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
