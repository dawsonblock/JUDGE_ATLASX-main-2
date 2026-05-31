"""
Shared normalization utilities for ingestion adapters.

Functions
---------
parse_datetime_safe   — multi-format datetime parser that never raises
normalize_coordinates — WGS 84 range-validated (lat, lon) converter
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

# Common date/time format strings tried by parse_datetime_safe when no
# explicit format list is supplied.  Ordered from most specific to least.
_COMMON_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
)


def parse_datetime_safe(
    value: "str | None",
    formats: "Sequence[str] | None" = None,
    *,
    utc_assumed: bool = True,
) -> "datetime | None":
    """Attempt datetime parsing from *value* against *formats*.

    Parameters
    ----------
    value:
        Raw date/time string from the upstream source.  ``None`` and empty
        strings both return ``None``.
    formats:
        Ordered sequence of ``strptime`` format strings to try.  Defaults to
        :data:`_COMMON_DATE_FORMATS` when omitted.
    utc_assumed:
        When ``True`` (the default), a parsed ``datetime`` with no tzinfo is
        treated as UTC.  Tz-aware values are returned unchanged.

    Returns
    -------
    datetime | None
        A timezone-aware ``datetime`` or ``None`` when no format matches.
    """
    if not value:
        return None

    # Try fromisoformat first — handles most ISO 8601 variants cheaply.
    stripped = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(stripped)
        if utc_assumed and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    candidate_formats: Sequence[str] = (
        formats if formats is not None else _COMMON_DATE_FORMATS
    )
    for fmt in candidate_formats:
        try:
            dt = datetime.strptime(value.strip(), fmt)
            if utc_assumed and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return None


def normalize_coordinates(
    lat: "float | int | str | None",
    lon: "float | int | str | None",
) -> "tuple[float, float] | None":
    """Validate and return ``(latitude, longitude)`` as floats, or ``None``.

    Accepts numeric values or their string representations.  Returns ``None``
    when a conversion fails or when the coordinate is outside valid WGS 84
    ranges (lat −90…90, lon −180…180).

    Parameters
    ----------
    lat:
        Latitude value from the upstream source.
    lon:
        Longitude value from the upstream source.

    Returns
    -------
    tuple[float, float] | None
        ``(latitude, longitude)`` as Python floats, or ``None`` when the input
        is missing, unparseable, or out of range.
    """
    if lat is None or lon is None:
        return None
    try:
        flat = float(lat)
        flon = float(lon)
    except (TypeError, ValueError):
        return None

    if not (-90.0 <= flat <= 90.0) or not (-180.0 <= flon <= 180.0):
        return None

    return flat, flon
