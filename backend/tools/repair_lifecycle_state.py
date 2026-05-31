#!/usr/bin/env python3
"""Repair lifecycle state fields in source_registry to match YAML truth."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.entities import SourceRegistry
from app.db.session import get_db_url


def load_yaml_sources() -> dict[str, dict[str, Any]]:
    """Load sources from YAML registry."""
    yaml_path = (
        BACKEND_DIR
        / "app"
        / "ingestion"
        / "sources"
        / "canada_saskatchewan_sources.yaml"
    )
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    sources_list = data.get("sources", [])
    return {src["source_key"]: src for src in sources_list}


def repair_lifecycle_state(
    dry_run: bool = False,
    source_key: str | None = None,
    verbose: bool = False,
) -> int:
    """Repair mismatches between DB and YAML."""
    
    yaml_sources = load_yaml_sources()
    db_url = get_db_url()
    engine = create_engine(db_url)
    
    repaired_count = 0
    mismatch_count = 0
    
    with Session(engine) as session:
        if source_key:
            stmt = select(SourceRegistry).where(
                SourceRegistry.source_key == source_key
            )
        else:
            stmt = select(SourceRegistry)
        
        db_rows = session.execute(stmt).scalars().all()
        
        for db_row in db_rows:
            key = db_row.source_key
            yaml_row = yaml_sources.get(key)
            
            if not yaml_row:
                if verbose:
                    print(f"  ⚠ {key}: not in YAML (skipping)")
                continue
            
            mismatches: list[tuple[str, Any, Any]] = []
            
            yaml_lifecycle = yaml_row.get("lifecycle_state")
            if db_row.lifecycle_state != yaml_lifecycle:
                mismatches.append(
                    ("lifecycle_state", db_row.lifecycle_state, yaml_lifecycle)
                )
            
            yaml_is_active = yaml_row.get("enabled_default", False)
            if db_row.is_active != yaml_is_active:
                mismatches.append(
                    ("is_active", db_row.is_active, yaml_is_active)
                )
            
            yaml_automation = yaml_row.get("automation_status")
            if db_row.automation_status != yaml_automation:
                mismatches.append(
                    ("automation_status", db_row.automation_status, yaml_automation)
                )
            
            if mismatches:
                mismatch_count += len(mismatches)
                if dry_run:
                    for field, old_val, new_val in mismatches:
                        print(f"  [DRY-RUN] {key}: {field} = {old_val} → {new_val}")
                else:
                    for field, old_val, new_val in mismatches:
                        setattr(db_row, field, new_val)
                        print(f"  ✓ {key}: {field} = {old_val} → {new_val}")
                    repaired_count += 1
        
        if not dry_run and repaired_count > 0:
            session.commit()
    
    print()
    if dry_run:
        print(f"DRY-RUN: {mismatch_count} mismatches found")
    else:
        print(f"REPAIRED: {repaired_count} sources updated")
    
    return 1 if mismatch_count > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair lifecycle state fields")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-key", type=str)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    
    try:
        return repair_lifecycle_state(
            dry_run=args.dry_run,
            source_key=args.source_key,
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
