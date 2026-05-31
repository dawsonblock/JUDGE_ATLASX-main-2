# Crime Incident CSV Import

Manual CSV import path for the crime incidents layer. Administered via `POST /api/admin/import/crime-incidents/manual-csv` (requires `JTA_ENABLE_ADMIN_IMPORTS=true` and `X-JTA-Admin-Token`).

---

## Required columns

All columns must be present as a header row. Values may be empty where noted as optional.

| Column | Type | Required | Notes |
|---|---|---|---|
| `source_id` | string | optional | Internal source identifier |
| `external_id` | string | required | Unique ID within this source — used for duplicate detection |
| `incident_type` | string | required | Free-form incident description, e.g. `Assault`, `Break and Enter` |
| `incident_category` | string | required | Normalised category, e.g. `violent`, `property` |
| `reported_at` | ISO 8601 datetime | optional | When the incident was reported, e.g. `2026-04-25T12:00:00Z` |
| `occurred_at` | ISO 8601 datetime | optional | When the incident occurred |
| `city` | string | optional | City name |
| `province_state` | string | optional | Province or state code/name |
| `country` | string | optional | Country name |
| `public_area_label` | string | optional | Human-readable area label shown on map, e.g. `Downtown`, `West End` |
| `latitude_public` | float | required | Generalised latitude — must not be 0.0 |
| `longitude_public` | float | required | Generalised longitude — must not be 0.0 |
| `precision_level` | string | required | See accepted values below |
| `source_url` | string | optional | Must begin with `http://` or `https://` if provided |
| `source_name` | string | required | Name of the data source |
| `verification_status` | string | optional | e.g. `reported`, `corroborated`, `official` |
| `notes` | string | optional | Must not contain prohibited terms — see below |

---

## Accepted `precision_level` values

| Value | Meaning |
|---|---|
| `general_area` | Neighbourhood, community, or district centroid |
| `city_centroid` | City or municipality centroid |
| `postal_area` | Postal/ZIP code centroid |
| `intersection` | Named intersection (non-residential) |

**Rejected:** `exact_address` — records with this precision level are rejected at import. The system does not store exact incident addresses.

---

## Prohibited fields and content

The following will cause a record to be **rejected** at import:

- `precision_level = "exact_address"`
- `latitude_public = 0.0` and `longitude_public = 0.0` simultaneously (zero-coordinate guard)
- `public_area_label` or `notes` containing residence or victim terms:
  - `residence`, `home`, `house`, `apartment`, `victim's`, `victim address`, `complainant address`
- `source_url` that does not start with `http://` or `https://`

---

## Default behaviour

Regardless of any value in the CSV row:

- `is_public` is always set to **`False`** — records are not publicly visible until manually reviewed and approved via the admin review queue.
- `review_status` is always set to **`pending_review`**.

These defaults cannot be overridden by the CSV file.

---

## Duplicate behaviour

Records are upserted on the `(source_name, external_id)` unique constraint:

- If a record with the same `source_name` and `external_id` already exists, its non-safety fields are updated in place.
- If a safety-sensitive field changes (coordinates, precision level, notes), the record's `review_status` is reset to `pending_review` and `is_public` is set to `False`.
- If only non-safety fields change (e.g. `verification_status`, `occurred_at`), an already-approved review status is preserved.

---

## Example: safe row

```csv
source_id,external_id,incident_type,incident_category,reported_at,occurred_at,city,province_state,country,public_area_label,latitude_public,longitude_public,precision_level,source_url,source_name,verification_status,notes
SPS,SPS-2026-0042,Assault,violent,2026-04-25T14:30:00Z,2026-04-25T13:00:00Z,Saskatoon,SK,Canada,Downtown,52.1332,-106.6700,general_area,https://police.saskatoon.ca/open-data,Saskatoon Police Service,reported,Generalized area only
```

---

## Rejected row examples

**Rejected — exact address precision:**
```csv
SPS,SPS-2026-0043,Break and Enter,property,2026-04-25T09:00:00Z,,Saskatoon,SK,Canada,123 Main St,52.1234,-106.6543,exact_address,https://police.saskatoon.ca/open-data,Saskatoon Police Service,reported,
```
Reason: `precision_level = exact_address` is never permitted.

**Rejected — invalid source URL:**
```csv
SPS,SPS-2026-0044,Theft,property,2026-04-25T10:00:00Z,,Saskatoon,SK,Canada,Stonebridge,52.0800,-106.6400,general_area,internal-db://sps/44,Saskatoon Police Service,reported,
```
Reason: `source_url` must start with `http://` or `https://`.

**Rejected — zero coordinates:**
```csv
SPS,SPS-2026-0045,Fraud,property,2026-04-25T11:00:00Z,,,,Canada,,0.0,0.0,general_area,,Saskatoon Police Service,reported,
```
Reason: Both `latitude_public` and `longitude_public` are 0.0.

**Rejected — residence term in notes:**
```csv
SPS,SPS-2026-0046,Assault,violent,2026-04-25T12:00:00Z,,Saskatoon,SK,Canada,West End,52.1100,-106.7000,general_area,https://police.saskatoon.ca,Saskatoon Police Service,reported,Occurred at victim's residence
```
Reason: Notes contain the prohibited term `victim's residence`.
