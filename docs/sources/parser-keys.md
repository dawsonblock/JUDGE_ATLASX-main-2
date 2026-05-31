# Parser Keys and Adapter Registry

Each `SourceRegistry` row has a `parser` field that maps to a concrete adapter
class in `backend/app/ingestion/source_adapters/`.

---

## Registry

| `parser` key | Adapter class | Module |
|-------------|--------------|--------|
| `saskatoon_csv` | `SaskatoonCsvAdapter` | `saskatoon_csv.py` |
| `saskatoon_police_csv` | `SaskatoonPoliceCsvAdapter` | `saskatoon_police_csv.py` |
| `crawlee_police_release` | `CrawleePoliceReleaseAdapter` | `crawlee_police_release.py` |
| `sk_courts_html` | `SKCourtsHtmlAdapter` | `sk_courts_html.py` |
| `statscan_table` | `StatscanTableAdapter` | `statscan_table.py` |
| `canlii_api` | `CanLIIApiAdapter` | `canlii_api.py` |
| `federal_court_html` | `FederalCourtHtmlAdapter` | `federal_court_html.py` |
| `scc_lexum_api` | `SCCLexumApiAdapter` | `scc_lexum_api.py` |
| `crawlee_gov_news` | `CrawleeGovNewsAdapter` | `crawlee_gov_news.py` |
| `sk_legislature_html` | `SKCourtsHtmlAdapter` | *(reuses `sk_courts_html.py`)* |
| `laws_justice_html` | `LawsJusticeHtmlAdapter` | `laws_justice_html.py` |
| `ckan_api` | `CKANApiAdapter` | `ckan_api.py` |

---

## Adapter interface

Every adapter inherits from `SourceAdapter` (`adapters.py`) and implements:

```python
def fetch(self) -> list[Any]:
    """Retrieve raw rows / documents from the remote source."""

def parse(self, raw: list[Any]) -> list[ParsedRecord]:
    """Convert raw rows to ParsedRecord instances."""

def run(self) -> IngestionResult:
    """Orchestrate fetch → parse → safety check → insert."""
```

The `run()` method calls `enforce_all()` from `source_rules.py` before
writing any record to the database.

---

## Adding a new adapter

See [adding-a-source.md](adding-a-source.md).
