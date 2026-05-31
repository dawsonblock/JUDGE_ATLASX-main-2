# THIRD-PARTY REFERENCES

This document lists the external data sources, legal databases, and open-data
portals referenced by JUDGE_ATLAS, along with the terms-of-service constraints
that apply to each.

---

## Legal Databases

### CourtListener / RECAP (Free Law Project)

- **URL**: https://www.courtlistener.com
- **Data scope**: US federal court opinions and PACER docket filings mirrored
  through the RECAP Archive.
- **Licence**: Bulk data available under the Free Law Project open data licence;
  see https://free.law/recap.
- **Terms**: Machine access permitted for non-commercial research use. Rate-limit
  observance required. Attribution expected in derivative works.
- **Role in JUDGE_ATLAS**: Tier-1 US legal decision source. No Canadian content.

### PACER (Public Access to Court Electronic Records)

- **URL**: https://pacer.uscourts.gov
- **Data scope**: US federal court dockets and filings.
- **Terms**: Access requires a registered account with per-page fees. Automated
  bulk downloads are prohibited without explicit permission. Use the RECAP mirror
  (CourtListener) for bulk access where available.
- **Role in JUDGE_ATLAS**: Referenced via CourtListener/RECAP; not directly
  polled by any adapter.

### CanLII (Canadian Legal Information Institute)

- **URL**: https://www.canlii.org
- **Data scope**: Canadian court decisions, legislation, and tribunal decisions.
- **Terms**: **Automated scraping is prohibited under the CanLII Terms of Use.**
  Human researchers may access the site manually. A CanLII Connects
  API is available only to academic partners with a signed data-access agreement.
- **Role in JUDGE_ATLAS**: `portal_reference` only. Manual researchers may link
  to CanLII decisions. No adapter is implemented. Any future integration would
  require a formal data-access agreement.

---

## Canadian Government Sources

### Justice Canada — Laws-Lois (justice_canada_laws_xml)

- **URL**: https://laws-lois.justice.gc.ca/eng/XML/
- **Data scope**: Consolidated federal statutes and regulations in XML (Akoma Ntoso).
- **Licence**: Open Government Licence — Canada.
- **Terms**: Machine download permitted. Attribution required. Reproductions
  permitted for non-commercial use.
- **Role in JUDGE_ATLAS**: Canonical source for federal statute text. Tier-2.
  Adapter implemented; currently `runnable_disabled`.

### Supreme Court of Canada (scc_decisions)

- **URL**: https://decisions.scc-csc.ca
- **Data scope**: SCC judgments since 1985.
- **Licence**: Crown copyright; reproductions permitted for personal/research use.
- **Terms**: Bulk automated download should respect robots.txt and server load.
  SCC publishes an informal "open access" policy but no explicit bulk-access API.
- **Role in JUDGE_ATLAS**: Tier-1. Adapter implemented; `runnable_disabled`.

### Federal Court of Canada (federal_court_canada)

- **URL**: https://decisions.fct-cf.gc.ca
- **Data scope**: Federal Court and Federal Court of Appeal decisions.
- **Licence**: Crown copyright; same as SCC above.
- **Role in JUDGE_ATLAS**: Tier-1. Adapter implemented; `runnable_disabled`.

### Saskatchewan Court of King's Bench / Court of Appeal

- **Source keys**: `sk_courts_qb_decisions`, `sk_courts_ca_decisions`
- **URL**: https://www.sasklawcourts.ca
- **Data scope**: Saskatchewan Queen's/King's Bench and Court of Appeal decisions.
- **Licence**: Crown copyright; open access policy.
- **Role in JUDGE_ATLAS**: Tier-1. Adapters implemented; `runnable_disabled`.

### Saskatchewan Legislature Hansard (sk_legislature_hansard)

- **URL**: https://www.legassembly.sk.ca/legislative-business/legislative-records/hansard
- **Data scope**: Legislative debates and committee proceedings.
- **Licence**: Open Government Licence — Saskatchewan.
- **Role in JUDGE_ATLAS**: Tier-2. Adapter implemented; `runnable_disabled`.

### Saskatchewan Ministry of Justice

- **URL**: https://www.saskatchewan.ca/government/government-structure/ministries/justice
- **Data scope**: Ministerial press releases and policy documents.
- **Role in JUDGE_ATLAS**: Tier-2. Portal-reference only; no adapter.

---

## Statistics Sources

### Statistics Canada — UCR Survey / CCJS

- **URL**: https://www150.statcan.gc.ca
- **Data scope**: Uniform Crime Reporting Survey (UCR) and Canadian Centre for
  Justice Statistics (CCJS) data tables.
- **Licence**: Statistics Canada Open Licence (modified OGL-Canada).
- **Terms**: Redistribution permitted with attribution.
- **Role in JUDGE_ATLAS**: Tier-3 statistical context. Portal-reference; no
  automated adapter. Crime coordinates must be generalised before storage (see
  crime layer rules below).

### FBI Crime Data API

- **URL**: https://cde.ucr.cjis.gov/LATEST/webapp/#/pages/docApi
- **Data scope**: US Uniform Crime Report and National Incident-Based Reporting
  System (NIBRS) data.
- **Licence**: US government public domain.
- **Terms**: API key required; rate limits apply.
- **Role in JUDGE_ATLAS**: Not yet implemented. Listed as future portal-reference
  for US crime statistics.

### Bureau of Justice Statistics — NIBRS

- **URL**: https://bjs.ojp.gov
- **Data scope**: National Incident-Based Reporting System annual data files.
- **Licence**: US government public domain.
- **Role in JUDGE_ATLAS**: Not yet implemented.

---

## Open Data Portals

### City of Saskatoon Open Data

- **URL**: https://opendata-saskatoon.opendata.arcgis.com
- **Licence**: City of Saskatoon Open Data Licence.
- **Role in JUDGE_ATLAS**: Possible tier-3 source for local crime statistics
  and infrastructure data. Portal-reference; no adapter implemented.

### City of Toronto Open Data

- **URL**: https://open.toronto.ca
- **Licence**: Open Government Licence — Ontario.
- **Role in JUDGE_ATLAS**: Possible tier-3 source. Portal-reference.

---

## Crime Layer Rules

Regardless of source, the following rules apply to all crime coordinate data:

1. Only generalised coordinates (city block level or lower precision) may be
   stored or displayed.
2. Precise incident locations that could identify a private residence are
   prohibited.
3. Crime data must never be linked to individual person profiles unless
   supported by a tier-1 or tier-2 conviction record.
4. Statistical aggregation is preferred over incident-level storage wherever
   the use case allows.

---

## Legal Decision Rules

1. **Tier-1 first**: Court decisions from CourtListener/RECAP, SCC, Federal
   Court, or Saskatchewan courts take precedence for all legal outcome claims.
2. **News cannot create a verified outcome**: A news article (tier-4) may
   provide secondary context but cannot by itself establish that a charge,
   conviction, or sentence is a verified legal fact.
3. **CanLII decisions**: May be cited manually by researchers. No automated
   adapter; any future integration requires a formal data agreement.
4. **Crown copyright material**: Reproductions permitted for research purposes
   under the applicable open government licence; commercial redistribution
   requires separate clearance.

---

## What Is NOT Referenced

- No private data brokers or background-check services.
- No social media platforms (scraping is prohibited under their terms).
- No dark-web or grey-area data aggregators.
- No databases acquired through breach, leak, or unauthorised disclosure.
- No health or financial records.
