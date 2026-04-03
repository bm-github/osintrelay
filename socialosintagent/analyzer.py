"""
Improved analyzer module with unified fetch/rate handling and resilient image processing.

Key improvements:
- Uses new ImageProcessor for resilient image handling
- Better error aggregation and reporting
- Graceful degradation when individual operations fail
- More detailed progress tracking
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .cache import CacheManager
from .client_manager import ClientManager
from .exceptions import AccessForbiddenError, RateLimitExceededError, UserNotFoundError
from .llm import LLMAnalyzer
from .platforms import FETCHERS
from .utils import (
    SUPPORTED_IMAGE_EXTENSIONS,
    UserData,
    handle_rate_limit,
    sanitize_username,
    download_media_async,
)
from .image_processor import ImageProcessor, ProcessingStatus

logger = logging.getLogger("SocialOSINTAgent.analyzer")


@dataclass
class ImageProcessingError:
    """Detailed error information for failed image processing."""

    url: str
    stage: str
    error_type: str
    error_message: str
    context: str
    timestamp: str


class FetchResult:
    """Container for fetch operation results with detailed error tracking."""

    def __init__(self):
        self.successful: List[tuple] = []  # (platform, username, data)
        self.failed: List[tuple] = []  # (platform, username, error_type, message)
        self.rate_limited: List[tuple] = []  # (platform, username)

    def add_success(self, platform: str, username: str, data: UserData):
        """Record a successful fetch."""
        self.successful.append((platform, username, data))

    def add_failure(self, platform: str, username: str, error_type: str, message: str):
        """Record a failed fetch."""
        self.failed.append((platform, username, error_type, message))

    def add_rate_limit(self, platform: str, username: str):
        """Record a rate-limited fetch."""
        self.rate_limited.append((platform, username))

    @property
    def has_any_data(self) -> bool:
        """Check if any fetch succeeded."""
        return len(self.successful) > 0

    def get_summary(self) -> str:
        """Get a summary of fetch results."""
        parts = []
        if self.successful:
            parts.append(f"{len(self.successful)} successful")
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        if self.rate_limited:
            parts.append(f"{len(self.rate_limited)} rate-limited")
        return ", ".join(parts) if parts else "no results"


class SocialOSINTAgent:
    """
    Improved OSINT agent with unified fetch/rate handling and resilient image processing.
    """

    def __init__(
        self,
        args,
        cache_manager: CacheManager,
        llm_analyzer: LLMAnalyzer,
        client_manager: ClientManager,
    ):
        """
        Initializes the SocialOSINTAgent.

        Args:
            args: Command-line arguments namespace.
            cache_manager: An instance of CacheManager for data caching.
            llm_analyzer: An instance of LLMAnalyzer for AI-powered analysis.
            client_manager: An instance of ClientManager for API client handling.
        """
        self.args = args
        self.base_dir = Path("data")
        self.cache = cache_manager
        self.llm = llm_analyzer
        self.client_manager = client_manager
        self.image_processor = ImageProcessor()
        self._setup_directories()
        self._verify_env_vars()

    def _verify_env_vars(self):
        """Verifies that all necessary environment variables are set."""
        required_llm = [
            "LLM_API_KEY",
            "LLM_API_BASE_URL",
            "IMAGE_ANALYSIS_MODEL",
            "ANALYSIS_MODEL",
        ]
        if any(not os.getenv(k) for k in required_llm):
            raise RuntimeError(
                "Missing one or more critical LLM environment variables."
            )
        if not self.client_manager.get_available_platforms(check_creds=True):
            logger.warning(
                "No platform API credentials found. Only HackerNews and GitHub may be available."
            )

    def _setup_directories(self):
        """Ensures that all required data directories exist."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        for dir_name in ["cache", "media", "outputs"]:
            (self.base_dir / dir_name).mkdir(parents=True, exist_ok=True)

    def analyze(
        self,
        platforms: Dict[str, List[str]],
        query: str,
        force_refresh: bool = False,
        fetch_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Orchestrates the entire OSINT analysis process with improved error handling.

        Args:
            platforms: A dictionary mapping platform names to lists of usernames.
            query: The user's natural language query for the analysis.
            force_refresh: If True, bypasses the cache for API data.
            fetch_options: A dictionary to control fetch counts.

        Returns:
            A dictionary containing the analysis report and metadata (plain-text /
            Markdown in ``report``; no Rich markup).
        """
        fetch_result = self._fetch_all_platform_data(
            platforms, force_refresh, fetch_options
        )

        if not fetch_result.has_any_data:
            return {
                "metadata": {},
                "report": "Data collection failed for all targets.",
                "error": True,
            }

        vision_stats: Dict[str, Any] = {}
        if not self.args.offline:
            vision_stats = self._perform_vision_analysis(fetch_result.successful)

        return self._generate_analysis_report(fetch_result, query, vision_stats)

    async def analyze_async(
        self,
        platforms: Dict[str, List[str]],
        query: str,
        force_refresh: bool = False,
        fetch_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Async version of analyze for use in async contexts (e.g., web server).

        Orchestrates the entire OSINT analysis process with async vision analysis.

        Args:
            platforms: A dictionary mapping platform names to lists of usernames.
            query: The user's natural language query for the analysis.
            force_refresh: If True, bypasses the cache for API data.
            fetch_options: A dictionary to control fetch counts.

        Returns:
            A dictionary containing the analysis report and metadata.
        """
        fetch_result = self._fetch_all_platform_data(
            platforms, force_refresh, fetch_options
        )

        if not fetch_result.has_any_data:
            return {
                "metadata": {},
                "report": "Data collection failed for all targets.",
                "error": True,
            }

        vision_stats: Dict[str, Any] = {}
        if not self.args.offline:
            vision_stats = await self._perform_vision_analysis_async(
                fetch_result.successful
            )

        return self._generate_analysis_report(fetch_result, query, vision_stats)

    def _fetch_all_platform_data(
        self,
        platforms: Dict[str, List[str]],
        force_refresh: bool,
        fetch_options: Optional[Dict[str, Any]],
    ) -> FetchResult:
        """
        Fetch data from all platforms with unified error handling.

        Returns:
            FetchResult object with detailed success/failure tracking
        """
        result = FetchResult()
        fetch_options = fetch_options or {}
        default_count = fetch_options.get("default_count", 50)

        for platform, usernames in platforms.items():
            if not (fetcher := FETCHERS.get(platform)):
                for username in usernames:
                    result.add_failure(
                        platform,
                        username,
                        "NotImplemented",
                        "Fetcher not implemented",
                    )
                continue

            for username in usernames:
                logger.info("Fetching %s/%s", platform, username)
                try:
                    client = self.client_manager.get_platform_client(platform)

                    limit = (
                        fetch_options.get("targets", {})
                        .get(f"{platform}:{username}", {})
                        .get("count", default_count)
                    )

                    kwargs = {
                        "username": username,
                        "cache": self.cache,
                        "force_refresh": force_refresh,
                        "fetch_limit": limit,
                        "allow_external_media": self.args.unsafe_allow_external_media,
                    }

                    platforms_requiring_client = ["twitter", "reddit", "bluesky"]
                    if platform == "mastodon":
                        kwargs["clients"], kwargs["default_client"] = client
                    elif platform in platforms_requiring_client:
                        kwargs["client"] = client

                    data = fetcher(**kwargs)

                    if data:
                        result.add_success(platform, username, data)
                    else:
                        result.add_failure(
                            platform,
                            username,
                            "NoData",
                            "Fetcher returned no data",
                        )

                except RateLimitExceededError as e:
                    result.add_rate_limit(platform, username)
                    handle_rate_limit(
                        f"{platform.capitalize()} Fetch",
                        e,
                        should_raise=False,
                    )

                except UserNotFoundError as e:
                    result.add_failure(platform, username, "NotFound", str(e))

                except AccessForbiddenError as e:
                    result.add_failure(platform, username, "Forbidden", str(e))

                except Exception as e:
                    logger.error(
                        "Fetch failed for %s/%s: %s",
                        platform,
                        username,
                        e,
                        exc_info=True,
                    )
                    result.add_failure(
                        platform,
                        username,
                        "Unexpected",
                        f"Unexpected error: {type(e).__name__}",
                    )

        self._log_fetch_summary(result)
        return result

    def _log_fetch_summary(self, result: FetchResult) -> None:
        """Log a short summary of fetch results (headless-safe)."""
        if not result.failed and not result.rate_limited:
            logger.info(
                "All fetches successful (%s targets)",
                len(result.successful),
            )
            return

        logger.warning("Fetch summary: %s", result.get_summary())
        for platform, username, error_type, message in result.failed:
            logger.warning(
                "Fetch issue: %s/%s — %s: %s",
                platform,
                username,
                error_type,
                message,
            )
        for platform, username in result.rate_limited:
            logger.warning("Fetch issue: %s/%s — Rate limited", platform, username)

    async def _perform_vision_analysis_async(
        self,
        successful_fetches: List[tuple],
    ) -> Dict[str, Any]:
        """
        Perform vision analysis on images with async download + preprocessing.

        Phase 1: Download and preprocess all images in parallel
        Phase 2: Analyze images serially (respect rate limits)

        Returns:
            Statistics about vision processing with detailed error breakdown
        """
        # Collect all images to download and analyze
        images_to_process = []
        for platform, username, user_data in successful_fetches:
            for post in user_data.get("posts", []):
                for media_item in post.get("media", []):
                    url = media_item.get("url")
                    # Only process images that haven't been analyzed yet
                    if url and not media_item.get("analysis"):
                        images_to_process.append(
                            {
                                "url": url,
                                "context": f"{platform} user {username}",
                                "media_item": media_item,
                                "user_data": user_data,
                                "platform": platform,
                                "username": username,
                            }
                        )

        if not images_to_process:
            return {
                "total": 0,
                "analyzed": 0,
                "failed": 0,
                "skipped": 0,
                "cleaned": 0,
                "errors": {},
                "error_summaries": [],
            }

        logger.info(
            "Processing %s images for vision analysis (async)", len(images_to_process)
        )

        # Track errors
        errors: List[ImageProcessingError] = []

        # Phase 1: Download all images in parallel
        download_tasks = [
            download_media_async(
                self.base_dir,
                img["url"],
                self.cache.is_offline,
                img["platform"],
                allow_external=self.args.unsafe_allow_external_media,
            )
            for img in images_to_process
        ]

        downloaded_paths = await asyncio.gather(*download_tasks, return_exceptions=True)

        # Pair downloaded paths with metadata and track errors
        images_to_analyze = []
        for metadata, result in zip(images_to_process, downloaded_paths):
            if isinstance(result, Exception):
                error_type = self._categorize_download_error(
                    result, metadata["url"], metadata["platform"]
                )
                error_msg = str(result)
                logger.error(f"Download failed for {metadata['url']}: {error_msg}")
                errors.append(
                    ImageProcessingError(
                        url=metadata["url"],
                        stage="download",
                        error_type=error_type,
                        error_message=error_msg,
                        context=metadata["context"],
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )
                continue

            if (
                result
                and result.exists()
                and result.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
            ):
                images_to_analyze.append({"file_path": result, "metadata": metadata})

        if not images_to_analyze:
            logger.warning("No valid images downloaded for analysis")
            error_summary = self._build_error_summary(errors, len(images_to_process))
            return {
                "total": len(images_to_process),
                "analyzed": 0,
                "failed": len(images_to_process),
                "skipped": 0,
                "cleaned": 0,
                "errors": self._categorize_errors(errors),
                "error_summaries": error_summary,
            }

        logger.info(
            "Downloaded %s/%s images successfully",
            len(images_to_analyze),
            len(images_to_process),
        )

        # Phase 2: Preprocess all images in parallel
        preprocess_tasks = [
            self.image_processor.preprocess_image_async(img["file_path"])
            for img in images_to_analyze
        ]

        processed_paths = await asyncio.gather(
            *preprocess_tasks, return_exceptions=True
        )

        # Update images_to_analyze with processed paths and track errors
        for img, processed_path in zip(images_to_analyze, processed_paths):
            if isinstance(processed_path, Exception):
                error_type = self._categorize_preprocess_error(
                    processed_path, img["file_path"]
                )
                error_msg = str(processed_path)
                logger.error(
                    f"Preprocessing failed for {img['file_path']}: {error_msg}"
                )
                errors.append(
                    ImageProcessingError(
                        url=img["metadata"]["url"],
                        stage="preprocess",
                        error_type=error_type,
                        error_message=error_msg,
                        context=img["metadata"]["context"],
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )
                img["processed_path"] = None
            else:
                img["processed_path"] = processed_path

        # Phase 3: Analyze images serially (respect rate limits)
        analyzed_count = 0
        failed_count = 0
        skipped_count = 0
        modified_users = set()

        for img in images_to_analyze:
            if not img["processed_path"]:
                failed_count += 1
                continue

            metadata = img["metadata"]
            file_path = img["file_path"]
            processed_path = img["processed_path"]

            try:
                # Analyze the image (sync to respect rate limits)
                analysis = self.llm.analyze_image(
                    processed_path,
                    source_url=metadata["url"],
                    context=metadata["context"],
                )

                if analysis:
                    metadata["media_item"]["analysis"] = analysis
                    modified_users.add((metadata["platform"], metadata["username"]))
                    analyzed_count += 1
                else:
                    failed_count += 1
                    errors.append(
                        ImageProcessingError(
                            url=metadata["url"],
                            stage="analyze",
                            error_type="empty_response",
                            error_message="Analysis returned no result",
                            context=metadata["context"],
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        )
                    )

            except RateLimitExceededError:
                logger.error("Vision model rate limit hit; stopping image analysis.")
                skipped_count = len(images_to_analyze) - analyzed_count - failed_count
                # Add error for all remaining images
                for remaining_img in images_to_analyze[
                    len(images_to_analyze) - skipped_count :
                ]:
                    errors.append(
                        ImageProcessingError(
                            url=remaining_img["metadata"]["url"],
                            stage="analyze",
                            error_type="rate_limit",
                            error_message="Vision model rate limit exceeded",
                            context=remaining_img["metadata"]["context"],
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        )
                    )
                break

            except Exception as e:
                error_type = self._categorize_analysis_error(e)
                logger.error(f"Image analysis failed for {file_path}: {e}")
                failed_count += 1
                errors.append(
                    ImageProcessingError(
                        url=metadata["url"],
                        stage="analyze",
                        error_type=error_type,
                        error_message=str(e),
                        context=metadata["context"],
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )

            finally:
                # Clean up processed file
                if (
                    processed_path
                    and processed_path.exists()
                    and processed_path != file_path
                ):
                    try:
                        processed_path.unlink()
                    except Exception:
                        pass

        # Save updated caches for modified users
        for platform, username in modified_users:
            for p, u, user_data in successful_fetches:
                if p == platform and u == username:
                    self.cache.save(platform, username, user_data)
                    break

        # Clean up downloaded media files to save disk space
        cleaned_count = 0
        for img in images_to_analyze:
            file_path = img["file_path"]
            try:
                if file_path.exists():
                    file_path.unlink()
                    cleaned_count += 1
                    # Clear local_path from media_item since file is gone
                    img["metadata"]["media_item"]["local_path"] = None
            except Exception as e:
                logger.warning("Failed to clean up media file %s: %s", file_path, e)

        if cleaned_count > 0:
            logger.info("Cleaned up %s media files after analysis", cleaned_count)

        # Build error summary
        error_summary = self._build_error_summary(errors, len(images_to_process))

        stats = {
            "total": len(images_to_process),
            "analyzed": analyzed_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "cleaned": cleaned_count,
            "errors": self._categorize_errors(errors),
            "error_summaries": error_summary,
        }

        if analyzed_count > 0:
            logger.info(
                "Analyzed %s/%s images (async pipeline)",
                analyzed_count,
                len(images_to_process),
            )
        if failed_count > 0:
            logger.warning(
                "%s images failed analysis (continued processing)",
                failed_count,
            )
            # Log error summary
            for summary in error_summary:
                logger.warning("  - %s", summary)
        if skipped_count > 0:
            logger.warning(
                "%s images skipped due to rate limit",
                skipped_count,
            )

        return stats

    def _categorize_download_error(
        self, error: Exception, url: str, platform: str
    ) -> str:
        """Categorize download error type."""
        error_str = str(error).lower()
        error_type = "unknown"

        if "timeout" in error_str or "timed out" in error_str:
            error_type = "timeout"
        elif "429" in error_str or "rate limit" in error_str:
            error_type = "rate_limit"
        elif "404" in error_str or "not found" in error_str:
            error_type = "not_found"
        elif "403" in error_str or "forbidden" in error_str:
            error_type = "forbidden"
        elif "connection" in error_str or "network" in error_str:
            error_type = "network"
        elif "dns" in error_str:
            error_type = "dns"
        elif "ssl" in error_str or "tls" in error_str:
            error_type = "ssl"

        return error_type

    def _categorize_preprocess_error(self, error: Exception, file_path: Path) -> str:
        """Categorize preprocess error type."""
        error_str = str(error).lower()
        error_type = "unknown"

        if "unsupported" in error_str or "format" in error_str:
            error_type = "invalid_format"
        elif "corrupt" in error_str or "invalid" in error_str:
            error_type = "corrupt_file"
        elif "memory" in error_str:
            error_type = "out_of_memory"
        elif "permission" in error_str or "access" in error_str:
            error_type = "permission_error"

        return error_type

    def _categorize_analysis_error(self, error: Exception) -> str:
        """Categorize analysis error type."""
        error_str = str(error).lower()
        error_type = "unknown"

        if "rate limit" in error_str or "429" in error_str:
            error_type = "rate_limit"
        elif "api" in error_str or "request" in error_str:
            error_type = "api_error"
        elif "timeout" in error_str:
            error_type = "timeout"
        elif "authentication" in error_str or "unauthorized" in error_str:
            error_type = "auth_error"

        return error_type

    def _categorize_errors(self, errors: List[ImageProcessingError]) -> Dict[str, int]:
        """Categorize errors by stage and type."""
        categorized = {
            "download_failed": 0,
            "preprocess_failed": 0,
            "analyze_failed": 0,
            "rate_limited": 0,
            "network_errors": 0,
            "invalid_format": 0,
            "other_errors": 0,
        }

        for error in errors:
            if error.stage == "download":
                categorized["download_failed"] += 1
                if error.error_type in ["timeout", "network", "dns", "ssl"]:
                    categorized["network_errors"] += 1
                elif error.error_type == "rate_limit":
                    categorized["rate_limited"] += 1
            elif error.stage == "preprocess":
                categorized["preprocess_failed"] += 1
                if error.error_type == "invalid_format":
                    categorized["invalid_format"] += 1
            elif error.stage == "analyze":
                categorized["analyze_failed"] += 1
                if error.error_type == "rate_limit":
                    categorized["rate_limited"] += 1

            categorized["other_errors"] += 1

        return categorized

    def _build_error_summary(
        self, errors: List[ImageProcessingError], total_images: int
    ) -> List[str]:
        """Build user-friendly error summary."""
        summaries = []

        if not errors:
            return summaries

        # Group errors by type
        error_groups = {}
        for error in errors:
            key = f"{error.stage}:{error.error_type}"
            if key not in error_groups:
                error_groups[key] = {
                    "stage": error.stage,
                    "type": error.error_type,
                    "count": 0,
                }
            error_groups[key]["count"] += 1

        # Build human-readable summaries
        for group in error_groups.values():
            stage = group["stage"]
            etype = group["type"]
            count = group["count"]

            if stage == "download":
                if etype == "timeout":
                    summaries.append(
                        f"{count} images failed to download (connection timeout)"
                    )
                elif etype == "network":
                    summaries.append(
                        f"{count} images failed to download (network error)"
                    )
                elif etype == "not_found":
                    summaries.append(f"{count} images not found (404)")
                elif etype == "forbidden":
                    summaries.append(f"{count} images blocked (403 forbidden)")
                elif etype == "rate_limit":
                    summaries.append(
                        f"{count} images failed to download (rate limited)"
                    )
                else:
                    summaries.append(f"{count} images failed to download")
            elif stage == "preprocess":
                if etype == "invalid_format":
                    summaries.append(f"{count} images had unsupported format")
                elif etype == "corrupt_file":
                    summaries.append(f"{count} images were corrupt")
                else:
                    summaries.append(f"{count} images failed preprocessing")
            elif stage == "analyze":
                if etype == "rate_limit":
                    summaries.append(f"{count} images skipped (rate limit)")
                elif etype == "empty_response":
                    summaries.append(f"{count} images returned no analysis")
                else:
                    summaries.append(f"{count} images failed analysis")

        # Add suggestions
        if any(e.stage == "download" for e in errors):
            summaries.append("Tip: Images are cached - re-running will skip downloads")

        return summaries

    def _perform_vision_analysis(
        self,
        successful_fetches: List[tuple],
    ) -> Dict[str, Any]:
        """
        Synchronous wrapper for async vision analysis.

        Returns:
            Statistics about vision processing
        """
        return asyncio.run(self._perform_vision_analysis_async(successful_fetches))

    def _generate_analysis_report(
        self,
        fetch_result: FetchResult,
        query: str,
        vision_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate the final analysis report."""
        logger.info("Synthesizing report with LLM")
        try:
            collected_data = {
                p: [] for p in set(p for p, _, _ in fetch_result.successful)
            }
            for platform, username, data in fetch_result.successful:
                collected_data[platform].append(
                    {"username_key": username, "data": data}
                )

            report, entities = self.llm.run_analysis(collected_data, query)

        except RateLimitExceededError as e:
            handle_rate_limit("LLM Analysis", e)
            return {
                "metadata": {},
                "report": "Analysis aborted due to LLM rate limit.",
                "error": True,
            }
        except Exception as e:
            logger.error("LLM analysis failed: %s", e, exc_info=True)
            return {
                "metadata": {},
                "report": f"LLM analysis failed: {e}",
                "error": True,
            }

        # Build metadata
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        text_model = os.getenv("ANALYSIS_MODEL")
        img_model = os.getenv("IMAGE_ANALYSIS_MODEL")

        platforms_used = {
            p: [u for p2, u, _ in fetch_result.successful if p2 == p]
            for p in set(p for p, _, _ in fetch_result.successful)
        }

        metadata = {
            "query": query,
            "targets": platforms_used,
            "generated_utc": ts,
            "mode": "Offline" if self.args.offline else "Online",
            "models": {"text": text_model, "image": img_model},
            "fetch_stats": {
                "successful": len(fetch_result.successful),
                "failed": len(fetch_result.failed),
                "rate_limited": len(fetch_result.rate_limited),
            },
            "vision_stats": vision_stats,
        }

        # Build header
        header = (
            f"# OSINT Analysis Report\n\n"
            f"**Query:** `{query}`\n"
            f"**Generated:** `{ts}`\n"
            f"**Mode:** `{metadata['mode']}`\n"
            f"**Models Used:**\n- Text: `{text_model}`\n- Image: `{img_model}`\n"
            f"**Data Sources:** {len(fetch_result.successful)} targets\n"
        )

        if vision_stats.get("analyzed", 0) > 0:
            header += f"**Images Analyzed:** {vision_stats['analyzed']}/{vision_stats['total']}\n"

        header += "\n---\n\n"

        # Add vision analysis summary if there were any errors
        if vision_stats.get("failed", 0) > 0 or vision_stats.get("skipped", 0) > 0:
            header += self._build_vision_summary_section(vision_stats)
            header += "\n"

        # Return entities explicitly
        return {
            "metadata": metadata,
            "report": header + report,
            "entities": entities,
            "error": False,
        }

    def _build_vision_summary_section(self, vision_stats: Dict[str, Any]) -> str:
        """Build vision analysis summary section for the report."""
        total = vision_stats.get("total", 0)
        analyzed = vision_stats.get("analyzed", 0)
        failed = vision_stats.get("failed", 0)
        skipped = vision_stats.get("skipped", 0)
        error_summaries = vision_stats.get("error_summaries", [])

        section = "## Image Analysis Results\n\n"
        section += f"**Processed**: {analyzed}/{total} images analyzed successfully"

        if failed > 0:
            section += f", {failed} failed"
        if skipped > 0:
            section += f", {skipped} skipped"

        section += "\n\n"

        # Add error summary
        if error_summaries:
            section += "### Issues Encountered\n\n"
            for summary in error_summaries:
                section += f"- {summary}\n"
            section += "\n"

        return section

    def get_contacts(
        self,
        platforms: Dict[str, List[str]],
    ):
        """
        Extract discovered network contacts from cached post data.

        Runs deterministic extraction (mentions, retweets, repo interactions)
        over the cached posts for every active target. Does not make any
        API calls — operates entirely on locally-cached data.

        Results are sorted by weight (most-interacted-with contacts first).
        Active targets are automatically excluded from the returned list so
        the UI doesn't suggest promoting someone who is already being tracked.

        Args:
            platforms: The session's active targets dict
                       (platform -> [usernames]).

        Returns:
            List of DiscoveredContact sorted by weight descending.
        """
        from .network_extractor import extract_contacts

        # Build the posts dict that extract_contacts expects:
        # platform -> username -> [NormalizedPost]
        platform_posts: Dict[str, Dict] = {}
        for platform, usernames in platforms.items():
            platform_posts[platform] = {}
            for username in usernames:
                data = self.cache.load(platform, username)
                if data:
                    platform_posts[platform][username] = data.get("posts", [])

        return extract_contacts(
            platform_posts=platform_posts,
            active_targets=platforms,
        )

    def process_stdin(self):
        """Processes an analysis request provided via stdin as a JSON object."""
        logger.info("Processing analysis request from stdin...")

        # Parse JSON with detailed error handling
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            error_detail = {
                "error": "Invalid JSON",
                "message": str(e),
                "line": e.lineno,
                "column": e.colno,
                "help": 'Ensure your JSON is properly formatted. Example: {"platforms": {"twitter": ["user1"]}, "query": "What are their interests?"}',
            }
            sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
            sys.exit(1)

        # Validate required fields
        required_fields = ["platforms", "query"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            error_detail = {
                "error": "Missing required fields",
                "missing_fields": missing,
                "provided_fields": list(data.keys()),
                "example": {
                    "platforms": {
                        "twitter": ["example_user"],
                        "reddit": ["example_user"],
                    },
                    "query": "What are their primary interests and communication patterns?",
                    "fetch_options": {"default_count": 50},
                },
            }
            sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
            sys.exit(1)

        # Validate field types
        platforms = data.get("platforms")
        query = data.get("query")
        fetch_options = data.get("fetch_options")

        if not isinstance(platforms, dict):
            error_detail = {
                "error": "Invalid field type",
                "field": "platforms",
                "expected_type": "dict",
                "received_type": type(platforms).__name__,
                "example": {"twitter": ["user1", "user2"], "reddit": ["user3"]},
            }
            sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
            sys.exit(1)

        if not isinstance(query, str) or not query.strip():
            error_detail = {
                "error": "Invalid field type or empty value",
                "field": "query",
                "expected_type": "non-empty string",
                "received_type": type(query).__name__,
                "example": "What are the user's primary interests and recent activities?",
            }
            sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
            sys.exit(1)

        if not platforms:
            error_detail = {
                "error": "Empty platforms",
                "message": "The 'platforms' field must contain at least one platform with usernames",
                "example": {"twitter": ["example_user"]},
            }
            sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
            sys.exit(1)

        # Validate platform configuration
        try:
            available_platforms = self.client_manager.get_available_platforms(
                check_creds=True
            )

            if not available_platforms:
                error_detail = {
                    "error": "No platforms configured",
                    "message": "No platform API credentials are configured. Please check your .env file.",
                    "help": "At minimum, configure credentials for: TWITTER_BEARER_TOKEN, REDDIT_CLIENT_ID/SECRET, or BLUESKY_IDENTIFIER/SECRET",
                }
                sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
                sys.exit(1)

            # Filter to only valid platforms and sanitize usernames
            query_platforms = {}
            invalid_platforms = []

            for platform, usernames in platforms.items():
                if platform not in available_platforms:
                    invalid_platforms.append(platform)
                    continue

                if not isinstance(usernames, list):
                    error_detail = {
                        "error": "Invalid usernames format",
                        "platform": platform,
                        "expected_type": "list of strings",
                        "received_type": type(usernames).__name__,
                        "example": {"twitter": ["user1", "user2"]},
                    }
                    sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
                    sys.exit(1)

                sanitized = [
                    sanitize_username(u.strip()) for u in usernames if u and u.strip()
                ]
                if sanitized:
                    query_platforms[platform] = sanitized

            if invalid_platforms:
                logger.warning(
                    "Skipping unconfigured platforms: %s",
                    ", ".join(invalid_platforms),
                )
                logger.info(
                    "Available platforms: %s",
                    ", ".join(available_platforms),
                )

            if not query_platforms:
                error_detail = {
                    "error": "No valid platforms found",
                    "message": "None of the requested platforms are configured or contain valid usernames",
                    "requested_platforms": list(platforms.keys()),
                    "available_platforms": available_platforms,
                    "help": "Configure credentials for at least one requested platform in your .env file",
                }
                sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
                sys.exit(1)

        except RuntimeError as e:
            error_detail = {
                "error": "Platform initialization failed",
                "message": str(e),
                "help": "Check your .env file for correct API credentials",
            }
            sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
            sys.exit(1)

        try:
            result = self.analyze(
                query_platforms,
                query,
                fetch_options=fetch_options,
            )

        except Exception as e:
            logger.error(f"Analysis failed during execution: {e}", exc_info=True)
            error_detail = {
                "error": "Analysis execution failed",
                "message": str(e),
                "type": type(e).__name__,
            }
            sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
            sys.exit(1)

        # Handle results
        if result.get("error"):
            # Analysis completed but with errors
            error_detail = {
                "error": "Analysis completed with errors",
                "report": result.get("report", "No report available"),
                "metadata": result.get("metadata", {}),
            }
            sys.stderr.write(json.dumps(error_detail, indent=2) + "\n")
            sys.exit(2)

        # Success - output the report
        if self.args.no_auto_save:
            # Print to stdout (machine-readable mode)
            if self.args.format == "json":
                output = {
                    "success": True,
                    "metadata": result.get("metadata", {}),
                    "report": result.get("report", ""),
                }
                print(json.dumps(output, indent=2))
            else:
                # Print markdown directly
                print(result["report"])
        else:
            # Save to file and report the path
            output_path = self._save_output_headless(result, self.args.format)
            success_detail = {
                "success": True,
                "output_file": str(output_path),
                "metadata": result.get("metadata", {}),
            }
            # Print success info to stdout (JSON format for easy parsing)
            print(json.dumps(success_detail, indent=2))

        sys.exit(0)

    def _save_output_headless(self, result: Dict[str, Any], file_format: str) -> Path:
        """
        Saves the analysis report to a file in non-interactive mode.

        Returns:
            Path: The path to the saved file
        """
        metadata = result["metadata"]
        query = metadata.get("query", "query")
        platforms = list(metadata.get("targets", {}).keys())

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_q = (
            "".join(c for c in query[:30] if c.isalnum() or c in " _-").strip()
            or "query"
        )
        safe_p = "_".join(sorted(platforms)) or "platforms"
        base_filename = f"analysis_{ts}_{safe_p}_{safe_q}"
        ext = "md" if file_format == "markdown" else file_format
        path = self.base_dir / "outputs" / f"{base_filename}.{ext}"

        if file_format == "json":
            data_to_save = {
                "analysis_metadata": metadata,
                "analysis_report_markdown": result["report"],
            }
            path.write_text(json.dumps(data_to_save, indent=2), encoding="utf-8")
        else:
            path.write_text(result["report"], encoding="utf-8")

        # Log to stderr so it doesnt interfere with stdout JSON
        sys.stderr.write(f"Analysis saved to: {path}\n")

        return path
