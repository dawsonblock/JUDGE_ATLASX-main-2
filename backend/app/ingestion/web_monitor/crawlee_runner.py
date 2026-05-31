"""Crawlee-based web monitoring runner with strict safety controls.

This runner provides controlled fetching of known public pages only.
It enforces strict allowlists, request limits, and safety rules.

Safety features:
- Strict domain allowlist enforcement
- Request counting with hard stop at max_requests
- Low concurrency by default
- All fetched content defaults to pending_review
- Integration with SourceRegistry control plane
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import urllib.request
from urllib.robotparser import RobotFileParser

from sqlalchemy.orm import Session

from app.ingestion.source_registry_ctl import (
    check_ingestion_allowed,
    require_source_registry,
    update_source_health,
)
from app.ingestion.automation_statuses import BLOCK_SOURCE_INACTIVE
from app.models.entities import IngestionRun, ReviewItem, SourceSnapshot
from app.ingestion.statuses import COMPLETED, COMPLETED_WITH_WARNINGS, FAILED, PENDING, RUNNING


def _robots_allowed(url: str, user_agent: str = "*") -> bool:
    """Check whether *url* is permitted by the site's robots.txt.

    Fetches <scheme>://<host>/robots.txt with a 5-second timeout and
    evaluates the rule for *user_agent*.  Returns ``False`` (fail-closed)
    on any network or parse error so an unverifiable robots.txt always
    blocks ingestion.
    """
    from urllib.parse import urljoin

    try:
        robots_url = urljoin(url, "/robots.txt")
        with urllib.request.urlopen(robots_url, timeout=5) as resp:  # noqa: S310
            content = resp.read().decode("utf-8", errors="replace")
        rp = RobotFileParser()
        rp.parse(content.splitlines())
        return rp.can_fetch(user_agent, url)
    except Exception:
        return False  # Fail closed: block fetch if robots.txt cannot be verified


if TYPE_CHECKING:
    from app.ingestion.web_monitor.extractors import ExtractedCandidate
    from app.ingestion.web_monitor.source_targets import WebMonitorTarget


class CrawleeRunner:
    """Controlled web monitoring runner using Crawlee.

    Enforces strict safety limits and never performs open-ended crawling.
    """

    def __init__(self, target: "WebMonitorTarget", db: Session):
        """Initialize runner with target configuration.

        Args:
            target: WebMonitorTarget configuration
            db: Database session
        """
        self.target = target
        self.db = db
        self.request_count = 0
        self.snapshots: list[SourceSnapshot] = []
        self.errors: list[str] = []
        self._seen_urls: set[str] = set()  # within-run URL dedup
        self._seen_hashes: set[str] = set()  # within-run content-hash dedup
        self._db_tier: str | None = None  # set in run() from SourceRegistry

    def _is_url_allowed(self, url: str) -> bool:
        """Check if URL is in the allowed domains list.

        Args:
            url: URL to check

        Returns:
            True if allowed, False otherwise
        """
        return self.target.is_url_allowed(url)

    def _check_request_limit(self) -> bool:
        """Check if we've reached the request limit.

        Returns:
            True if under limit, False if limit reached
        """
        if self.request_count >= self.target.max_requests:
            return False
        return True

    def _create_snapshot(
        self,
        source_url: str,
        http_status: int,
        content_type: str | None,
        content: bytes | str,
        title: str | None = None,
        text_excerpt: str | None = None,
        ingestion_run_id: int | None = None,
    ) -> SourceSnapshot:
        """Create a source snapshot from fetched content.

        Supports external filesystem storage when JTA_EVIDENCE_STORE_ROOT is set.
        Falls back to DB storage when not configured.

        Args:
            source_url: Fetched URL
            http_status: HTTP status code
            content_type: Content-Type header
            content: Raw content (bytes or string)
            title: Page title if extracted (stored in raw_content field)
            text_excerpt: Text excerpt if extracted
            ingestion_run_id: Optional ID of the ingestion run

        Returns:
            SourceSnapshot entity
        """
        from app.services.snapshot_writer import write_snapshot

        # Pass raw content bytes unchanged — metadata belongs in extractor_name,
        # not prepended to the evidence bytes (which would corrupt the hash).
        snapshot = write_snapshot(
            db=self.db,
            source_url=source_url,
            fetched_at=datetime.now(timezone.utc),
            content=content,
            extracted_text=text_excerpt[:2000] if text_excerpt else None,
            http_status=http_status,
            content_type=content_type or "unknown",
            headers=None,  # Not captured in current implementation
            error_message=None,
            ingestion_run_id=ingestion_run_id,
            extractor_name=self.target.name,
            source_key=self.target.source_key,
        )
        self.db.flush()  # Get snapshot.id assigned
        return snapshot

    def _create_review_item(
        self,
        candidate: "ExtractedCandidate",
        snapshot: SourceSnapshot,
        ingestion_run_id: int | None = None,
    ) -> ReviewItem:
        """Create a ReviewItem from an ExtractedCandidate.

        All crawled candidates are created with:
        - status="pending" (never auto-publish)
        - publish_recommendation="review_required"
        - confidence capped at 0.5
        - privacy_status based on warnings

        Args:
            candidate: Extracted candidate from extractor
            snapshot: Associated SourceSnapshot
            ingestion_run_id: Optional ID of the ingestion run

        Returns:
            ReviewItem entity ready for admin review
        """
        # Determine privacy status based on warnings
        privacy_status = "safe"
        warning_text = " | ".join(candidate.warnings) if candidate.warnings else ""

        if candidate.warnings:
            # Check for high-risk warnings
            high_risk_patterns = [
                "address",
                "private",
                "person_name",
                "email",
                "phone",
            ]
            if any(pattern in warning_text.lower() for pattern in high_risk_patterns):
                privacy_status = "needs_review"

        # Build suggested payload from candidate
        suggested_payload = {
            "title": candidate.title,
            "summary": candidate.summary,
            "candidate_type": candidate.candidate_type,
            "location_text": candidate.location_text,
            "entities": candidate.entities,
            "published_at": (
                candidate.published_at.isoformat() if candidate.published_at else None
            ),
            "extracted_warnings": candidate.warnings,
            "extraction_confidence": candidate.confidence,
        }

        # Use auto_review to derive publish_recommendation and confidence
        from app.services.auto_review import auto_review as _auto_review
        from app.services.publish_rules import source_tier as _source_tier

        db_tier = self._db_tier or _source_tier(self.target.name)
        ar = _auto_review(
            candidate,
            self.target.name,
            has_snapshot_hash=bool(snapshot.content_hash),
            db_tier=db_tier,
        )
        _ACTION_MAP = {
            "block": ("block", "blocked"),
            "context_only": ("review_required", PENDING),
            "quarantine": ("review_required", PENDING),
            "publish": ("review_required", PENDING),
        }
        ri_rec, ri_status = _ACTION_MAP.get(ar.action, ("review_required", PENDING))

        review_item = ReviewItem(
            record_type=candidate.candidate_type,
            source_snapshot_id=snapshot.id,
            suggested_payload_json=suggested_payload,
            source_url=candidate.source_url,
            source_quality=self.target.source_tier,
            confidence=min(candidate.confidence, 0.5),
            privacy_status=privacy_status,
            publish_recommendation=ri_rec,
            status=ri_status,
            ingestion_run_id=ingestion_run_id,
        )
        return review_item

    async def run(self) -> IngestionRun:
        """Execute the web monitoring run.

        Returns:
            IngestionRun with metrics and status
        """
        from crawlee import Request
        from crawlee.crawlers import HttpCrawler

        # Check SourceRegistry control plane
        # Note: WebMonitorTarget.enabled is template metadata only;
        # SourceRegistry.is_active is the only runtime authority
        registry = require_source_registry(
            self.db,
            source_key=self.target.source_key,
            source_name=self.target.name,
        )

        allowed, reason = check_ingestion_allowed(registry)
        # Pre-compute source tier for review items (used by _create_review_item)
        from app.services.publish_rules import source_tier as _source_tier

        self._db_tier = _source_tier(self.target.name, registry=registry)
        if not allowed:
            human_reason = reason
            if reason.partition("::")[0] == BLOCK_SOURCE_INACTIVE:
                human_reason = "source is disabled"
            run = IngestionRun(
                source_name=self.target.source_key,
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                errors=[f"Ingestion blocked: {human_reason} ({reason})"],
            )
            run.error_count = 1
            run.fetched_count = 0
            run.parsed_count = 0
            run.persisted_count = 0
            run.finished_at = datetime.now(timezone.utc)
            self.db.add(run)
            self.db.commit()
            return run

        # Initialize run tracking
        run = IngestionRun(
            source_name=self.target.source_key,
            started_at=datetime.now(timezone.utc),
            status=RUNNING,
            errors=[],
        )
        self.db.add(run)
        self.db.flush()
        ingestion_run_id = run.id

        # Track metrics
        fetched_count = 0
        parsed_count = 0
        persisted_count = 0

        try:
            # Create crawler with safety limits
            config = self.target.get_crawlee_config()

            crawler = HttpCrawler(
                max_requests_per_crawl=config["max_requests_per_crawl"],
                max_crawl_depth=config["max_crawl_depth"],
                max_concurrency=config["max_concurrency"],
                # respect_robots_txt parameter removed - Crawlee does not expose direct control
                # robots.txt behavior is either respected by default or not configurable per-crawl
            )

            @crawler.router.default_handler
            async def handler(context) -> None:
                """Handle each crawled page."""
                nonlocal fetched_count, parsed_count, persisted_count

                # Check request limit
                if not self._check_request_limit():
                    context.log.warning(
                        f"Request limit ({self.target.max_requests}) reached"
                    )
                    return

                # Check allowlist
                url = str(context.request.url)
                if not self._is_url_allowed(url):
                    context.log.warning(f"URL not in allowlist: {url}")
                    return

                # robots.txt enforcement
                if self.target.robots_txt_obey and not _robots_allowed(url):
                    context.log.info(f"Skipping URL disallowed by robots.txt: {url}")
                    return

                # Within-run URL dedup
                if url in self._seen_urls:
                    context.log.debug(f"Skipping already-seen URL: {url}")
                    return
                self._seen_urls.add(url)

                try:
                    # Extract content
                    response = context.http.response
                    content = await response.text()
                    content_type = response.headers.get("content-type", "unknown")
                    http_status = response.status_code

                    # Skip non-HTML content types (images, CSS, JS, fonts, etc.)
                    _ct_lower = content_type.lower()
                    if not any(
                        t in _ct_lower
                        for t in ("text/html", "application/xhtml", "text/plain")
                    ):
                        context.log.info(
                            f"Skipping non-HTML content: {url} ({content_type})"
                        )
                        return

                    # Within-run content-hash dedup
                    import hashlib as _hashlib

                    _content_bytes = (
                        content.encode("utf-8") if isinstance(content, str) else content
                    )
                    _content_sig = _hashlib.sha256(_content_bytes).hexdigest()
                    if _content_sig in self._seen_hashes:
                        context.log.debug(f"Skipping duplicate content from {url}")
                        return
                    self._seen_hashes.add(_content_sig)

                    # Enqueue links within same hostname (depth controlled by HttpCrawler)
                    await context.enqueue_links(strategy="same-hostname")

                    # Try to extract title from HTML
                    title = None
                    import re

                    title_match = re.search(
                        r"<title[^>]*>([^<]*)</title>", content, re.IGNORECASE
                    )
                    if title_match:
                        title = title_match.group(1).strip()
                    text_excerpt = content[:2000] if content else None

                    # Create snapshot
                    snapshot = self._create_snapshot(
                        source_url=url,
                        http_status=http_status,
                        content_type=content_type,
                        content=content,
                        title=title,
                        text_excerpt=text_excerpt,
                        ingestion_run_id=ingestion_run_id,
                    )

                    self.snapshots.append(snapshot)
                    self.db.add(snapshot)
                    self.db.flush()  # Get snapshot.id assigned

                    # Successfully fetched
                    fetched_count += 1
                    self.request_count += 1
                    context.log.info(f"Fetched {url} ({http_status})")

                    # Extract candidate using appropriate extractor
                    from app.ingestion.web_monitor.extractors import extract_from_page

                    try:
                        candidate = extract_from_page(
                            url=url,
                            content=content,
                            title=title,
                            extractor_type=self.target.extractor_type,
                        )
                        parsed_count += 1  # Only increment on successful parse

                        # Create ReviewItem from candidate (never auto-publish)
                        review_item = self._create_review_item(
                            candidate, snapshot, ingestion_run_id
                        )
                        self.db.add(review_item)
                        context.log.info(
                            f"Created ReviewItem from {url}: "
                            f"type={candidate.candidate_type}, "
                            f"status={review_item.status}, "
                            f"snapshot_id={snapshot.id}"
                        )
                        persisted_count += 1  # Both snapshot and review item created
                    except Exception as extract_err:
                        error_msg = f"Extractor failed for {url}: {str(extract_err)}"
                        self.errors.append(error_msg)
                        context.log.warning(error_msg)
                        # Do NOT increment parsed_count or persisted_count on failure

                except Exception as e:
                    error_msg = f"Error processing {url}: {str(e)}"
                    self.errors.append(error_msg)
                    context.log.error(error_msg)

            # Run crawler with start URLs
            start_requests = [Request(url=url) for url in self.target.start_urls]

            # Execute crawl
            await crawler.run(start_requests)

            # Update run status
            run.fetched_count = fetched_count
            run.parsed_count = parsed_count
            run.persisted_count = persisted_count
            run.error_count = len(self.errors)
            run.errors = self.errors
            run.status = COMPLETED_WITH_WARNINGS if self.errors else COMPLETED
            run.finished_at = datetime.now(timezone.utc)

            self.db.commit()

            # Update source registry health
            update_source_health(self.db, self.target.source_key, run)

        except Exception as e:
            # Handle fatal errors
            run.status = FAILED
            run.errors.append(f"Fatal error: {str(e)}")
            run.error_count = len(run.errors)
            run.fetched_count = fetched_count
            run.parsed_count = parsed_count
            run.persisted_count = persisted_count
            run.finished_at = datetime.now(timezone.utc)
            self.db.commit()

        return run


async def run_web_monitor_target(
    target: "WebMonitorTarget", db: Session
) -> IngestionRun:
    """Run web monitoring for a specific target.

    Convenience function to create runner and execute.

    Args:
        target: WebMonitorTarget configuration
        db: Database session

    Returns:
        IngestionRun with results
    """
    runner = CrawleeRunner(target, db)
    return await runner.run()


def run_web_monitor_target_sync(
    target: "WebMonitorTarget", db: Session
) -> IngestionRun:
    """Run web monitoring for a specific target (sync wrapper).

    Convenience function to create runner and execute.

    Args:
        target: WebMonitorTarget configuration
        db: Database session

    Returns:
        IngestionRun with results
    """
    import asyncio

    return asyncio.run(run_web_monitor_target(target, db))
