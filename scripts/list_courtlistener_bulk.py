#!/usr/bin/env python3
"""List CourtListener bulk-data files from the public S3 bucket.

Usage:
    python scripts/list_courtlistener_bulk.py
    python scripts/list_courtlistener_bulk.py --date 2026-03-31

No AWS credentials required (public bucket, --no-sign-request).

Requires either:
  - boto3 (pip install boto3)
  - or urllib (built-in fallback via HTTP listing)
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
import xml.etree.ElementTree as ET

BUCKET = "com-courtlistener-storage"
PREFIX = "bulk-data/"
BASE_URL = f"https://{BUCKET}.s3.amazonaws.com/"

WANTED_STEMS = [
    "schema",
    "courts",
    "people-db-people",
    "people-db-positions",
    "dockets",
    "opinion-clusters",
    "opinions",
]


def list_objects_via_http(prefix: str) -> list[dict]:
    url = f"{BASE_URL}?list-type=2&prefix={prefix}&max-keys=1000"
    with urllib.request.urlopen(url, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    root = ET.fromstring(body)
    objects = []
    for content in root.findall("s3:Contents", ns):
        key_el = content.find("s3:Key", ns)
        size_el = content.find("s3:Size", ns)
        modified_el = content.find("s3:LastModified", ns)
        if key_el is not None:
            objects.append({
                "key": key_el.text or "",
                "size": int(size_el.text or 0) if size_el is not None else 0,
                "last_modified": (modified_el.text or "")[:10],
            })
    return objects


def _stem_for(key: str) -> str | None:
    filename = key.split("/")[-1]
    for stem in WANTED_STEMS:
        if filename.startswith(stem):
            return stem
    return None


def _date_for(key: str) -> str:
    parts = key.split("/")[-1].rsplit(".", 1)[0]
    tokens = parts.split("-")
    for i in range(len(tokens) - 2):
        candidate = "-".join(tokens[i:i + 3])
        if len(candidate) == 10 and candidate[4] == "-" and candidate[7] == "-":
            return candidate
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List CourtListener bulk-data files"
    )
    parser.add_argument(
        "--date",
        help="Filter to specific snapshot date (YYYY-MM-DD)",
        default=None,
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show all files, not just the newest snapshot",
    )
    args = parser.parse_args()

    print(f"Listing {BASE_URL}{PREFIX} ...", file=sys.stderr)
    try:
        objects = list_objects_via_http(PREFIX)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not objects:
        print("No objects found.", file=sys.stderr)
        sys.exit(1)

    relevant = []
    for obj in objects:
        stem = _stem_for(obj["key"])
        if stem:
            obj["stem"] = stem
            obj["snapshot_date"] = _date_for(obj["key"])
            relevant.append(obj)

    if not relevant:
        print("No relevant files found.", file=sys.stderr)
        sys.exit(1)

    if args.date:
        relevant = [o for o in relevant if o["snapshot_date"] == args.date]
        if not relevant:
            print(
                f"No files found for date {args.date}.", file=sys.stderr
            )
            sys.exit(1)
    elif not args.all:
        newest_date = max(o["snapshot_date"] for o in relevant if o["snapshot_date"])
        relevant = [o for o in relevant if o["snapshot_date"] == newest_date]

    snapshot_date = relevant[0]["snapshot_date"] if relevant else "unknown"
    print(f"\nSnapshot date: {snapshot_date}")
    print(f"Found {len(relevant)} relevant file(s):\n")

    print("# Download commands (no AWS credentials required):")
    print("mkdir -p data/courtlistener-bulk\n")
    for obj in sorted(relevant, key=lambda o: WANTED_STEMS.index(o["stem"]) if o["stem"] in WANTED_STEMS else 99):
        filename = obj["key"].split("/")[-1]
        size_mb = obj["size"] / 1_048_576
        print(
            f"# {filename}  ({size_mb:.1f} MB)"
        )
        print(
            f"aws s3 cp s3://{BUCKET}/{obj['key']} "
            f"data/courtlistener-bulk/ --no-sign-request"
        )
        print()


if __name__ == "__main__":
    main()
