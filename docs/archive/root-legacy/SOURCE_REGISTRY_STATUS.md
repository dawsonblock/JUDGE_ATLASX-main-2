# SOURCE_REGISTRY_STATUS

- generated_at_utc: 2026-05-15T07:24:58.369721+00:00
- commit_hash: 58f055d0bb56c4d69ebd6407ca6ad950b843b27f
- total_sources: 26
- machine_ingest_sources: 7
- runnable_when_active_sources: unknown
- enableable_sources: unknown
- sources_requiring_secrets: unknown

| source key | source name | jurisdiction | source class/type | automation status | adapter key | adapter exists | required secrets | required secrets present during proof | enabled by default | can be enabled by admin | can run now | reason if not runnable | review required before public visibility | public exposure allowed before review | current alpha status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| canada_justice_laws | Department of Justice Canada – Justice Laws Website (Deprecated Alias) | Canada | disabled_stub/aggregate_stats | disabled_stub | None | no | none | no | no | no | no | none | yes | no | limited-alpha-source |
| canada_open_data_crime | Open Government Canada – Crime & Justice Datasets | Canada | portal_reference/aggregate_stats | adapter_missing | ckan_api | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| canlii_sk | CanLII – Saskatchewan Courts | Saskatchewan, Canada | portal_reference/court_record | adapter_missing | canlii_api | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| federal_court_canada | Federal Court of Canada – Decisions | Canada | machine_ingest/court_record | machine_ready_disabled | federal_court_html | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| federal_court_canada_decisions | Federal Court of Canada – Decisions | Canada | portal_reference/court_record | adapter_missing | federal_court_html | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| justice_canada_laws_pit_xml | Department of Justice Canada – Point-in-Time Laws XML | Canada | disabled_stub/legislation | adapter_missing | None | no | none | no | no | no | no | none | yes | no | limited-alpha-source |
| justice_canada_laws_xml | Justice Canada Consolidated Acts and Regulations XML | Canada | machine_ingest/legislation | machine_ready_enabled | laws_justice_xml | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| justice_canada_laws_xml_repo | Justice Canada Laws XML GitHub Repository (Fixtures) | Canada | manual_reference/reference_repository | adapter_missing | None | no | none | no | no | no | no | none | yes | no | limited-alpha-source |
| justice_canada_lims_xml_dtd | Justice Canada LIMS XML DTD (Schema Validation) | Canada | manual_reference/schema_reference | adapter_missing | None | no | none | no | no | no | no | none | yes | no | limited-alpha-source |
| justice_canada_otto_reference | Justice Canada Otto AI Legal Tools (Architecture Reference) | Canada | manual_reference/architecture_reference | adapter_missing | None | no | none | no | no | no | no | none | yes | no | limited-alpha-source |
| rcmp_sk_news | RCMP Saskatchewan – News Releases | Saskatchewan, Canada | disabled_stub/news_monitor | adapter_missing | crawlee_police_release | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| saskatchewan_legislation | Saskatchewan Legislation – Acts and Regulations | CA-SK | portal_reference/legislation | adapter_missing | None | no | none | no | no | no | no | none | yes | no | limited-alpha-source |
| saskatoon_open_data_crime | City of Saskatoon Open Data – Crime Incidents | Saskatoon, Saskatchewan, Canada | portal_reference/crime_incident | adapter_missing | saskatoon_csv | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| saskatoon_open_data_portal | City of Saskatoon – Open Data Portal | Saskatoon, Saskatchewan, Canada | portal_reference/aggregate_stats | adapter_missing | ckan_api | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| saskatoon_open_data_public_safety | City of Saskatoon Open Data – Public Safety | CA-SK-Saskatoon | portal_reference/aggregate_stats | adapter_missing | ckan_api | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| saskatoon_police_open_data | Saskatoon Police Service – Open Data Portal | Saskatoon, Saskatchewan, Canada | portal_reference/crime_incident | adapter_missing | saskatoon_police_csv | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| scc_decisions | Supreme Court of Canada – Decisions | Canada | machine_ingest/court_record | machine_ready_disabled | scc_lexum_api | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| scc_judgments | Supreme Court of Canada – Judgments | Canada | machine_ingest/court_record | machine_ready_disabled | scc_lexum_api | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| sk_courts_ca_decisions | Saskatchewan Court of Appeal – Decisions | Saskatchewan, Canada | machine_ingest/court_record | machine_ready_disabled | canlii_api | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| sk_courts_qb_decisions | Saskatchewan Court of King's Bench – Decisions | Saskatchewan, Canada | machine_ingest/court_record | machine_ready_disabled | canlii_api | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| sk_justice_ministry | Saskatchewan Ministry of Justice – News Releases | Saskatchewan, Canada | disabled_stub/news_monitor | adapter_missing | crawlee_gov_news | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| sk_legislature_hansard | Saskatchewan Legislative Assembly – Hansard | Saskatchewan, Canada | machine_ingest/aggregate_stats | machine_ready_disabled | sk_legislature_html | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| statscan_ccjs_crime_sk | Statistics Canada – Canadian Centre for Justice Statistics (SK) | Saskatchewan, Canada | portal_reference/aggregate_stats | adapter_missing | statscan_table | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| statscan_crime_tables | Statistics Canada – Crime and Justice Tables | Canada | portal_reference/aggregate_stats | adapter_missing | statscan_table | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| statscan_ucr_national | Statistics Canada – Uniform Crime Reporting Survey (national) | Canada | portal_reference/aggregate_stats | adapter_missing | statscan_table | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |
| web_monitor_saskatoon_police_news | Saskatoon Police Service – News Releases (Web Monitor) | Saskatoon, Saskatchewan, Canada | disabled_stub/news_monitor | adapter_missing | crawlee_police_release | yes | none | no | no | no | no | none | yes | no | limited-alpha-source |

- artifacts/proof/current/source_registry_status.json
