# Source Coverage Matrix

Generated from artifacts/proof/current/source_registry_status.json.
Generated at: 2026-05-26T04:59:12.396532+00:00

## Summary

- total_sources: 26
- machine_ingest_sources: 8
- runnable_now: 2
- enable_ready: 6
- deprecated: 3

## Sources

| source key | jurisdiction | class | lifecycle | automation | runnable | enable ready | parser | adapter status | next action |
|---|---|---|---|---|---|---|---|---|---|
| canada_justice_laws | Canada | disabled_stub | deprecated | disabled_stub | false | false |  | missing_parser | Remove all references to canada_justice_laws and use justice_canada_laws_xml instead. |
| canada_open_data_crime | Canada | portal_reference | portal_reference | adapter_missing | false | false | ckan_api | found | Validate open.canada.ca API endpoint and write adapter. |
| canlii_sk | Saskatchewan, Canada | portal_reference | portal_reference | adapter_missing | false | false | canlii_api | found | Negotiate data access agreement with CanLII, or use only as a reference link. |
| federal_court_canada | Canada | machine_ingest | runnable_disabled | machine_ready_disabled | false | true | federal_court_html | found | Confirm base_url is reachable and terms permit ingest, then /enable via admin panel. |
| federal_court_canada_decisions | Canada | portal_reference | deprecated | deprecated | false | false | federal_court_html | found | Migrate any references from federal_court_canada_decisions to federal_court_canada and remove this entry. |
| justice_canada_laws_pit_xml | Canada | disabled_stub | disabled_stub | adapter_missing | false | false |  | missing_parser | Write a PIT-date-parameterised adapter or remove if not needed. |
| justice_canada_laws_xml | Canada | machine_ingest | runnable | machine_ready_enabled | true | false | laws_justice_xml | found | None. Source is pinned and enabled. Monitor ingestion runs and review queue for new snapshots. |
| justice_canada_laws_xml_repo | Canada | manual_reference | manual_reference | adapter_missing | false | false |  | missing_parser | Use justice_canada_laws_xml as the live ingest source. This entry is for schema and DTD reference only. |
| justice_canada_lims_xml_dtd | Canada | manual_reference | manual_reference | adapter_missing | false | false |  | missing_parser | Keep as a documentation reference; not a data source. |
| justice_canada_otto_reference | Canada | manual_reference | manual_reference | adapter_missing | false | false |  | missing_parser | Keep as a documentation reference; not a data source. |
| rcmp_sk_news | Saskatchewan, Canada | disabled_stub | disabled_stub | adapter_missing | false | false | crawlee_police_release | found | Evaluate whether a scraper is required or remove this stub. |
| saskatchewan_legislation | CA-SK | portal_reference | portal_reference | adapter_missing | false | false |  | missing_parser | Evaluate whether an RSS/XML feed can be configured; otherwise keep as portal_reference. |
| saskatoon_open_data_crime | Saskatoon, Saskatchewan, Canada | portal_reference | portal_reference | adapter_missing | false | false | saskatoon_csv | found | Check data.saskatoon.ca for updated CSV/JSON endpoint; write adapter if machine-readable. |
| saskatoon_open_data_portal | Saskatoon, Saskatchewan, Canada | portal_reference | portal_reference | adapter_missing | false | false | ckan_api | found | Prefer specific source_key entries per dataset. |
| saskatoon_open_data_public_safety | CA-SK-Saskatoon | machine_ingest | runnable_disabled | machine_ready_disabled | false | true | ckan_api | found | Run fixture proof target, confirm review-only payloads, then enable only after legal and data-quality verification. |
| saskatoon_police_open_data | Saskatoon, Saskatchewan, Canada | portal_reference | portal_reference | adapter_missing | false | false | saskatoon_police_csv | found | Monitor Saskatoon Police data portal for a machine-readable feed. |
| scc_decisions | Canada | machine_ingest | runnable_disabled | machine_ready_disabled | false | true | scc_lexum_api | found | Confirm base_url is reachable and terms permit ingest, then /enable via admin panel. |
| scc_judgments | Canada | machine_ingest | deprecated | deprecated | false | false | scc_lexum_api | found | Migrate any references from scc_judgments to scc_decisions and remove this entry. |
| sk_courts_ca_decisions | Saskatchewan, Canada | machine_ingest | runnable_disabled | machine_ready_disabled | false | true | canlii_api | found | Confirm terms of use, then /enable via admin panel. |
| sk_courts_qb_decisions | Saskatchewan, Canada | machine_ingest | runnable_disabled | machine_ready_disabled | false | true | canlii_api | found | Confirm terms of use, then enable via admin panel after clean proof. |
| sk_justice_ministry | Saskatchewan, Canada | disabled_stub | disabled_stub | adapter_missing | false | false | crawlee_gov_news | found | Define what specific data is needed, then write a targeted adapter. |
| sk_legislature_hansard | Saskatchewan, Canada | machine_ingest | runnable_disabled | machine_ready_disabled | false | true | sk_legislature_html | found | Confirm base_url is reachable and terms permit ingest, then /enable via admin panel. |
| statscan_ccjs_crime_sk | Saskatchewan, Canada | portal_reference | portal_reference | adapter_missing | false | false | statscan_table | found | Monitor StatsCan open data API for a machine-readable CCJS endpoint. |
| statscan_crime_tables | Canada | portal_reference | portal_reference | adapter_missing | false | false | statscan_table | found | Monitor StatsCan API roadmap; build adapter if open data endpoint is published. |
| statscan_ucr_national | Canada | portal_reference | portal_reference | adapter_missing | false | false | statscan_table | found | Monitor StatsCan open data API for a machine-readable UCR endpoint. |
| web_monitor_saskatoon_police_news | Saskatoon, Saskatchewan, Canada | disabled_stub | disabled_stub | adapter_missing | false | false | crawlee_police_release | found | Evaluate whether a scraper is required or remove this stub. |

## Notes

- source_registry_status.json is authoritative.
- Evidence snapshots are authoritative; AI and memory outputs are derivative.
- Public data remains review-gated in alpha.
