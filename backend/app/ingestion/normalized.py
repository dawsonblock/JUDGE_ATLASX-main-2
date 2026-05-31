"""
Typed normalized record structs for ingestion adapters.

The plain-dict ``payload`` in :class:`~app.ingestion.adapters.CreatedRecord`
is difficult to type-check and easy to misuse.  Adapters that have been
migrated to this module return a :class:`NormalizedIncident` from their
parsing logic and call :meth:`NormalizedIncident.to_payload` when building
the final ``CreatedRecord``.

This keeps the persistence path unchanged while giving adapters a validated,
self-documenting interface.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NormalizedIncident:
    """A fully typed, immutable crime-incident record ready for persistence.

    Field names match the ``payload`` keys expected by
    :mod:`app.ingestion.source_runner` and the ``CrimeIncident`` ORM model.
    Adding a field here requires a corresponding migration unless the field is
    declared :data:`None`-default and is stored in ``extra_data``.
    """

    # --- Identity ---------------------------------------------------------- #
    source_key: str
    external_id: "str | None"

    # --- Classification ---------------------------------------------------- #
    incident_type: str
    incident_category: str = "crime"

    # --- Temporal ---------------------------------------------------------- #
    reported_at: "datetime | None" = None
    occurred_at: "datetime | None" = None

    # --- Location ---------------------------------------------------------- #
    city: "str | None" = None
    province_state: "str | None" = None
    country: "str | None" = None
    public_area_label: "str | None" = None
    latitude_public: "float | None" = None
    longitude_public: "float | None" = None

    # Precision vocabulary:
    #   "exact"                  — precise address (blocked by publish_rules)
    #   "neighbourhood_centroid" — neighbourhood/area centroid (map-safe)
    #   "city_centroid"          — city-level only
    #   "unknown"                — precision not stated by source
    precision: str = "unknown"

    # --- Provenance -------------------------------------------------------- #
    source_url: "str | None" = None
    notes: "str | None" = None
    is_aggregate: bool = False

    # Extra fields not yet promoted to first-class columns land here.
    extra_data: "dict[str, Any]" = field(
        default_factory=dict, compare=False, hash=False
    )

    # ------------------------------------------------------------------ #

    def to_payload(self) -> "dict[str, Any]":
        """Return a ``dict`` suitable for ``CreatedRecord.payload``.

        Datetime fields are serialised to ISO 8601 strings.  ``None`` values
        are preserved so the persistence layer can distinguish "explicitly
        absent" from "field not present".
        """
        d = asdict(self)
        # source_key is carried on CreatedRecord itself, not in payload.
        d.pop("source_key", None)
        d.pop("external_id", None)

        for key in ("reported_at", "occurred_at"):
            val = d.get(key)
            if isinstance(val, datetime):
                d[key] = val.isoformat()

        return d
