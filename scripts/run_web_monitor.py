#!/usr/bin/env python3
"""CLI script to run web monitoring for specific targets.

Usage:
    python scripts/run_web_monitor.py --target saskatoon_police_news --limit 25
    python scripts/run_web_monitor.py --target saskatoon_police_news --dry-run

Safety:
- All targets default to disabled
- Must be explicitly enabled in admin panel
- Respects max_requests, max_depth limits
- Creates pending_review candidates only
- Never publishes directly
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.db.session import SessionLocal
from app.ingestion.web_monitor.source_targets import EXAMPLE_TARGETS
from app.ingestion.web_monitor import run_web_monitor_target_sync


def list_targets():
    """List all available targets."""
    print("\nAvailable web monitoring targets:")
    print("-" * 60)
    for key, target in EXAMPLE_TARGETS.items():
        status = "✓ ENABLED" if target.enabled else "✗ DISABLED"
        print(f"  {key:30} {status}")
        print(f"    Name: {target.name}")
        print(f"    Type: {target.extractor_type}")
        print(f"    Source Tier: {target.source_tier}")
        print(f"    Max Requests: {target.max_requests}")
        print(f"    Max Depth: {target.max_depth}")
        print()


def run_target(
    target_key: str,
    limit: int | None = None,
    dry_run: bool = False,
):
    """Run web monitoring for a specific target.

    Args:
        target_key: Target key from EXAMPLE_TARGETS
        limit: Override max_requests limit
        dry_run: Simulate without saving (config check only)
    """
    if target_key not in EXAMPLE_TARGETS:
        print(f"Error: Unknown target '{target_key}'")
        print(f"Available targets: {', '.join(EXAMPLE_TARGETS.keys())}")
        return 1

    target = EXAMPLE_TARGETS[target_key]

    # Override limit if provided
    if limit is not None:
        target = target.model_copy(update={"max_requests": limit})

    print(f"\nRunning web monitor for: {target.name}")
    print(f"  Target: {target_key}")
    print(f"  Source: {target.base_url}")
    print(f"  Type: {target.extractor_type}")
    print(f"  Tier: {target.source_tier}")
    print(f"  Max Requests: {target.max_requests}")
    print(f"  Max Depth: {target.max_depth}")
    print(f"  Dry Run: {dry_run}")
    print()

    if dry_run:
        print("DRY RUN - Would execute with these settings:")
        print(f"  Start URLs: {target.start_urls}")
        print(f"  Allowed Domains: {target.allowed_domains}")
        return 0

    # Check if target is enabled
    if not target.enabled:
        print(f"WARNING: Target '{target_key}' is disabled.")
        print(f"Enable the source in the admin panel (source key: {target.source_key}).")

    with SessionLocal() as db:
        print(f"Starting crawl at {datetime.now(timezone.utc).isoformat()}...")

        try:
            run = run_web_monitor_target_sync(target, db)

            print(f"\nCrawl completed at {datetime.now(timezone.utc).isoformat()}")
            print(f"Status: {run.status}")
            print(f"Fetched: {run.fetched_count}")
            print(f"Parsed: {run.parsed_count}")
            print(f"Persisted: {run.persisted_count}")
            print(f"Errors: {run.error_count}")

            if run.errors:
                print("\nErrors:")
                for error in run.errors:
                    print(f"  - {error}")

            # Return exit code based on status
            if run.status == "failed":
                return 1
            elif run.status in ("completed_with_warnings", "completed_with_errors"):
                return 2  # Partial success
            return 0

        except Exception as e:
            print(f"\nFatal error: {e}")
            return 1


def main():
    parser = argparse.ArgumentParser(
        description="Run web monitoring for Judge Atlas source targets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all available targets
  python scripts/run_web_monitor.py --list

  # Run saskatoon_police_news target with default limits
  python scripts/run_web_monitor.py --target saskatoon_police_news

  # Run with custom request limit
  python scripts/run_web_monitor.py --target saskatoon_police_news --limit 10

  # Dry run (simulate without saving)
  python scripts/run_web_monitor.py --target saskatoon_police_news --dry-run

Safety Notes:
  - All targets default to DISABLED
  - Must be enabled in admin panel before use
  - Respects robots.txt and site terms
  - Creates pending_review candidates only
  - Never publishes directly to public APIs
        """,
    )

    parser.add_argument(
        "--target",
        type=str,
        help="Target key to run (e.g., saskatoon_police_news)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Override max_requests limit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without saving (config check only)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available targets",
    )

    args = parser.parse_args()

    if args.list:
        list_targets()
        return 0

    if not args.target:
        print("Error: --target is required (unless using --list)")
        parser.print_help()
        return 1

    return run_target(
        target_key=args.target,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
