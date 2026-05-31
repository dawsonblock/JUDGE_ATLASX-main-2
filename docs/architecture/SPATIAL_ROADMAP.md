# Spatial Roadmap

This document describes the current spatial implementation, its known limitations, and the planned migration path to full PostGIS spatial queries.

---

## Current Implementation (Alpha/Prototype)

### Bounding Box Filtering

All bbox filtering uses **latitude/longitude column comparisons only**:

```python
stmt = stmt.where(
    Location.longitude >= west,
    Location.longitude <= east,
    Location.latitude >= south,
    Location.latitude <= north,
)
```

This applies to both:
- `/api/map/events` (court events via `Location` lat/lon)
- `/api/map/crime-incidents` (crime incidents via `CrimeIncident.latitude_public/longitude_public`)

### Why Not PostGIS Geometry?

1. **ORM/Alembic Drift**: `Location.geom` exists only in PostgreSQL (added via migration), but is **NOT mapped in the ORM** to avoid drift between SQLite (tests) and PostgreSQL (production).

2. **NULL geom Rows**: Rows inserted after the migration may have NULL `geom` values. Until geom is trigger-maintained or a generated column, bbox filtering uses lat/lon only.

3. **Cross-Database Compatibility**: SQLite tests work without PostGIS extensions.

### PostGIS Extension Initialization

`initialize_postgis(engine)` in `app/db/spatial.py` only:
- Creates the PostGIS extension if not present
- Does NOT modify the `locations` table schema (Alembic owns schema changes)

### What Works

- Functional bbox filtering for both map endpoints using lat/lon
- WGS84 coordinate storage
- Correct public/review gating
- Works under SQLite for tests (see CI for current count)
- No PostGIS dependency for bbox queries

### Current Limitations

- No spatial index — every bbox query reads all visible rows
- No `ST_Within`, `ST_DWithin`, or `ST_Intersects` at query time
- Full table scan does not scale beyond ~10k rows without indexing

---

## Future migration steps

### Step 1 — Add Generated `geom` Columns

Add `geom` as a **generated column** (trigger-maintained) so it is always up-to-date:

```sql
-- For locations (if switching to generated column)
ALTER TABLE locations
  ALTER COLUMN geom TYPE geometry(Point, 4326)
  GENERATED ALWAYS AS (
    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
  ) STORED;

-- For crime_incidents
ALTER TABLE crime_incidents
  ADD COLUMN geom geometry(Point, 4326)
  GENERATED ALWAYS AS (
    ST_SetSRID(ST_MakePoint(longitude_public, latitude_public), 4326)
  ) STORED;
```

**Requirement**: geom must be trigger-maintained or generated to ensure all rows have valid values.

### Step 2 — Add GIST Spatial Indexes

```sql
CREATE INDEX idx_crime_incidents_geom ON crime_incidents USING GIST (geom);
CREATE INDEX idx_locations_geom ON locations USING GIST (geom);
```

### Step 3 — Switch to PostGIS Spatial Queries

After geom is trustworthy (all rows populated via trigger/generated column):

1. Add `geom` mapping to ORM using conditional TypeDecorator
2. Replace lat/lon comparisons with `ST_Intersects`:

```python
from geoalchemy2.functions import ST_Intersects, ST_MakeEnvelope

envelope = ST_MakeEnvelope(west, south, east, north, 4326)
stmt = stmt.where(ST_Intersects(Location.geom, envelope))
```

### Step 4 — Advanced Spatial Features

Once spatial indexes are in place:

- **Clustering:** `ST_ClusterDBSCAN` for marker clustering at low zoom
- **Vector tiles:** `ST_AsMVT` for large dataset rendering
- **Heatmap grids:** `ST_SnapToGrid` for server-side aggregation
- **Radius queries:** `ST_DWithin` for `?lat=&lng=&radius_km=` filters

### Step 5 — Add geom to ORM

Only after production PostGIS deployment and Docker/PostGIS integration tests pass:

```python
# In entities.py - conditional geom mapping
from geoalchemy2 import Geometry
from sqlalchemy import TypeDecorator, Text

class PointGeometry(TypeDecorator):
    impl = Text
    cache_ok = True
    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return Geometry(geometry_type="POINT", srid=4326)
        return dialect.type_descriptor(self.impl)

class Location(Base):
    # ... existing columns ...
    geom: Mapped[str | None] = mapped_column(
        PointGeometry(srid=4326), nullable=True
    )
```

---

## Requirements Before PostGIS Switch

1. ✅ Production PostgreSQL+PostGIS deployment confirmed
2. ⏳ Docker/PostGIS integration tests in CI pipeline
3. ⏳ Trigger or generated column maintaining geom for all rows
4. ⏳ GIST indexes created and performance validated
5. ⏳ ORM TypeDecorator tested on both SQLite and PostgreSQL
