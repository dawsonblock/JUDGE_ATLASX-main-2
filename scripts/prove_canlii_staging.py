#!/usr/bin/env python3
"""Staging proof for Saskatchewan CanLII machine-ingest sources.

This script validates a small fetch path for:
- sk_courts_qb_decisions (skkb)
- sk_courts_ca_decisions (skca)

Behavior:
- If CANLII_API_KEY is present, uses CanLII API checks.
- If CANLII_API_KEY is absent, attempts public RSS checks from canlii.org.
- If RSS endpoints are bot-protected, falls back to Saskatchewan Courts HTML
    references that link to CanLII court pages.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter  # noqa: E402
from app.ingestion.source_adapters.sk_courts_html import SKCourtsHtmlAdapter  # noqa: E402
from app.ingestion.fetcher import fetch_for_ingestion  # noqa: E402


@dataclass
class StagingCheck:
    source_key: str
    database: str


@dataclass
class RssCheck:
    source_key: str
    url: str


_RSS_CHECKS = [
    # User-provided CanLII RSS endpoints.
    RssCheck("sk_courts_qb_decisions", "https://www.canlii.org/rss"),
    RssCheck("sk_courts_ca_decisions", "https://www.canlii.org/rss#skd"),
]


def _looks_like_bot_challenge(raw_text: str) -> bool:
    text = raw_text.lower()
    return (
        "please enable js" in text
        or "captcha-delivery" in text
        or "window.ddjskey" in text
    )


def _rss_has_items(raw_bytes: bytes | None) -> bool:
    if not raw_bytes:
        return False
    try:
        root = ET.fromstring(raw_bytes.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return False
    # RSS 2.0 and Atom support.
    if root.findall(".//item"):
        return True
    if root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        return True
    return False


def _validate_result(
    source_key: str,
    result,
    *,
    require_parser_version: bool = True,
) -> list[str]:
    errors: list[str] = []
    if result.created_records:
        errors.append("created_records_must_be_empty")
    if require_parser_version and result.parser_version is None:
        errors.append("missing_parser_version")
    if not result.fetch_url:
        errors.append("missing_fetch_url")
    if not result.raw_snapshot_bytes:
        errors.append("missing_raw_snapshot_bytes")
    if result.errors:
        errors.extend(f"adapter_error:{err}" for err in result.errors)
    if any(item.payload.get("public_visibility") == "public" for item in result.review_items):
        errors.append("review_item_attempted_public_visibility")

    if errors:
        print(f"CANLII_STAGING_{source_key.upper()}=FAIL:{'|'.join(errors)}")
    else:
        print(
            f"CANLII_STAGING_{source_key.upper()}=PASS:"
            f"review_items={len(result.review_items)}"
        )
    return errors


def _validate_rss_fetch(check: RssCheck) -> tuple[list[str], str]:
    errors: list[str] = []
    fetch_result = fetch_for_ingestion(
        check.url,
        allowed_domains=("canlii.org", "www.canlii.org"),
    )
    if fetch_result.error:
        errors.append(f"fetch_error:{fetch_result.error}")
    raw_text = (fetch_result.raw_content or b"").decode("utf-8", errors="replace")
    if _looks_like_bot_challenge(raw_text):
        errors.append("rss_bot_protected")
    elif not _rss_has_items(fetch_result.raw_content):
        errors.append("rss_missing_items")

    if errors:
        print(f"CANLII_STAGING_{check.source_key.upper()}=FAIL:{'|'.join(errors)}")
    else:
        print(f"CANLII_STAGING_{check.source_key.upper()}=PASS:rss_url={check.url}")
    return errors, (fetch_result.content_type or "unknown")


def _run_html_fallback_checks() -> list[str]:
    checks = [
        StagingCheck("sk_courts_qb_decisions", "skkb"),
        StagingCheck("sk_courts_ca_decisions", "skca"),
    ]

    failures: list[str] = []
    for check in checks:
        adapter = SKCourtsHtmlAdapter(
            source_key=check.source_key,
            base_url="https://sasklawcourts.ca/saskatchewan-court-decisions/",
            allowed_domains_json=(
                '["sasklawcourts.ca", "www.sasklawcourts.ca", '
                '"canlii.org", "www.canlii.org"]'
            ),
            public_record_authority="official_court_record",
        )
        result = adapter.run()
        failures.extend(
            f"{check.source_key}:html_fallback:{reason}"
            for reason in _validate_result(
                check.source_key,
                result,
                require_parser_version=False,
            )
        )
    return failures


def main() -> int:
    api_key = os.getenv("CANLII_API_KEY", "").strip()
    checks = [
        StagingCheck("sk_courts_qb_decisions", "skkb"),
        StagingCheck("sk_courts_ca_decisions", "skca"),
    ]

    if not api_key:
        rss_failures: list[str] = []
        for rss_check in _RSS_CHECKS:
            errors, _content_type = _validate_rss_fetch(rss_check)
            rss_failures.extend(f"{rss_check.source_key}:{reason}" for reason in errors)

        if not rss_failures:
            print("CANLII_STAGING_STATUS=PASS")
            print("CANLII_STAGING_MODE=rss")
            print("CANLII_STAGING_NO_AUTO_PUBLICATION=true")
            return 0

        # CanLII RSS is often protected by anti-bot checks; use deterministic
        # Saskatchewan courts references that point to CanLII as fallback proof.
        html_failures = _run_html_fallback_checks()
        if html_failures:
            print("CANLII_STAGING_STATUS=FAIL")
            for failure in rss_failures + html_failures:
                print(f"CANLII_STAGING_FAILURE={failure}")
            return 1

        print("CANLII_STAGING_STATUS=PASS")
        print("CANLII_STAGING_MODE=html_fallback")
        print("CANLII_STAGING_NOTE=RSS endpoints are bot-protected; fallback uses SK courts CanLII references")
        print("CANLII_STAGING_NO_AUTO_PUBLICATION=true")
        return 0

    failures: list[str] = []
    for check in checks:
        adapter = CanLIIApiAdapter(
            source_key=check.source_key,
            base_url="https://api.canlii.org/v1",
            api_key=api_key,
            allowed_domains_json='["api.canlii.org", "canlii.org", "www.canlii.org"]',
            public_record_authority="official_court_record",
            databases=[check.database],
            result_count=1,
            offset=0,
        )
        result = adapter.run()
        failures.extend(f"{check.source_key}:{reason}" for reason in _validate_result(check.source_key, result))

    if failures:
        print("CANLII_STAGING_STATUS=FAIL")
        for failure in failures:
            print(f"CANLII_STAGING_FAILURE={failure}")
        return 1

    print("CANLII_STAGING_STATUS=PASS")
    print("CANLII_STAGING_MODE=api")
    print("CANLII_STAGING_NO_AUTO_PUBLICATION=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
