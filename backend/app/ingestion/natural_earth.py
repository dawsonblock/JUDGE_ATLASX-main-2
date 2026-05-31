"""Natural Earth boundary loader.

Loads country and state/province boundaries from Natural Earth GeoJSON files
(1:50m scale recommended) into the ``boundaries`` table.

Usage::

    with SessionLocal() as db:
        result = load_natural_earth_file(db, path="data/natural_earth/ne_50m_admin_0_countries.geojson", boundary_type="country")
        result = load_natural_earth_file(db, path="data/natural_earth/ne_50m_admin_1_states_provinces.geojson", boundary_type="state_province")

Natural Earth data is public domain. Download from https://www.naturalearthdata.com/
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Boundary


@dataclass
class BoundaryImportResult:
    read_count: int = 0
    upserted_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


def load_natural_earth_file(
    db: Session,
    path: str | Path,
    boundary_type: str,
    simplify: bool = True,
) -> BoundaryImportResult:
    """Parse a Natural Earth GeoJSON file and upsert rows into ``boundaries``.

    Args:
        db:            SQLAlchemy session.
        path:          Path to the ``.geojson`` file.
        boundary_type: One of ``"country"`` or ``"state_province"``.
        simplify:      If True, strip geometry coordinates to save space
                       (keeps properties and type, drops coordinate arrays).
    """
    result = BoundaryImportResult()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        result.error_count = 1
        result.errors.append(f"file_read_error:{exc}")
        return result

    features = data.get("features") or []
    for feature in features:
        result.read_count += 1
        try:
            props = feature.get("properties") or {}
            name = (
                props.get("NAME")
                or props.get("name")
                or props.get("ADMIN")
                or props.get("admin")
                or ""
            ).strip()
            if not name:
                result.skipped_count += 1
                continue

            iso_code = _extract_iso(props, boundary_type)
            parent_iso = props.get("iso_a2") or props.get("ISO_A2") or None
            if boundary_type == "country":
                parent_iso = None

            geojson_str = _feature_geojson(feature, simplify)

            existing = db.scalar(
                select(Boundary).where(
                    Boundary.name == name,
                    Boundary.boundary_type == boundary_type,
                )
            )
            if existing:
                existing.iso_code = iso_code
                existing.parent_iso = parent_iso
                existing.geojson_simplified = geojson_str
            else:
                db.add(
                    Boundary(
                        name=name,
                        iso_code=iso_code,
                        boundary_type=boundary_type,
                        parent_iso=parent_iso,
                        source="natural_earth",
                        geojson_simplified=geojson_str,
                    )
                )
            result.upserted_count += 1
        except Exception as exc:  # noqa: BLE001
            result.error_count += 1
            result.errors.append(f"feature_error:{exc}")

    db.commit()
    return result


def _extract_iso(props: dict[str, Any], boundary_type: str) -> str | None:
    if boundary_type == "country":
        return (
            props.get("ISO_A2")
            or props.get("iso_a2")
            or props.get("ADM0_A3")
            or None
        )
    return (
        props.get("iso_3166_2")
        or props.get("ISO_3166_2")
        or props.get("adm1_code")
        or None
    )


def _feature_geojson(feature: dict[str, Any], simplify: bool) -> str:
    """Return a compact GeoJSON string for the feature.

    When simplify=True the geometry coordinates are dropped (properties kept)
    to avoid storing multi-megabyte polygon arrays in SQLite.
    """
    if simplify:
        slim = {
            "type": "Feature",
            "properties": feature.get("properties") or {},
            "geometry": {
                "type": (feature.get("geometry") or {}).get("type"),
                "coordinates": [],
            },
        }
        return json.dumps(slim, separators=(",", ":"))
    return json.dumps(feature, separators=(",", ":"))
