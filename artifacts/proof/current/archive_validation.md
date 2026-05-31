# Archive Validation

- validated_at_utc: 2026-05-31T21:10:31.408502+00:00
- archive: [REDACTED_LOCAL_PATH]/JUDGE_ATLAS-main-final.zip
- archive_sha256: ebff1924572f07ac299bf57179da42e04cf1687839363271afbbefba06769b6d
- expected_root: JUDGE_ATLAS-main
- actual_root: JUDGE_ATLAS-main
- top_level_roots: JUDGE_ATLAS-main
- root_match: yes
- valid: PASS
- compressed_size_bytes: 2142729
- uncompressed_size_bytes: 8334638

## Errors

- none

## Warnings

- release_gate_not_alpha_passed
- release_gate_not_release_candidate

## Largest Files

| path | uncompressed | compressed |
|---|---:|---:|
| JUDGE_ATLAS-main/backend/uv.lock | 769811 | 238625 |
| JUDGE_ATLAS-main/frontend/package-lock.json | 393441 | 85051 |
| JUDGE_ATLAS-main/artifacts/proof/current/backend_pytest_collect.log | 322394 | 45760 |
| JUDGE_ATLAS-main/scripts/release_gate.py | 118932 | 21947 |
| JUDGE_ATLAS-main/backend/app/models/entities.py | 101799 | 16701 |
| JUDGE_ATLAS-main/artifacts/proof/current/release_gate.json | 91763 | 13712 |
| JUDGE_ATLAS-main/artifacts/proof/current/proof_manifest.json | 49785 | 6859 |
| JUDGE_ATLAS-main/backend/app/memory/contradiction_engine.py | 48640 | 8977 |
| JUDGE_ATLAS-main/backend/app/ingestion/sources/canada_saskatchewan_sources.yaml | 48453 | 6929 |
| JUDGE_ATLAS-main/backend/app/api/routes/admin_sources.py | 46092 | 9260 |
| JUDGE_ATLAS-main/backend/app/tests/test_api.py | 43536 | 7488 |
| JUDGE_ATLAS-main/backend/app/tests/test_admin_ingestion.py | 38695 | 5870 |
| JUDGE_ATLAS-main/backend/app/tests/test_ingestion_runtime.py | 38018 | 5725 |
| JUDGE_ATLAS-main/backend/app/tests/test_phase5_adaptive_retry.py | 35181 | 4174 |
| JUDGE_ATLAS-main/scripts/build_release_archive.py | 31305 | 6467 |
| JUDGE_ATLAS-main/backend/app/tests/test_ai_reasoning.py | 30318 | 4943 |
| JUDGE_ATLAS-main/scripts/check_proof_consistency.py | 30006 | 5902 |
| JUDGE_ATLAS-main/backend/app/ingestion/courtlistener_bulk_normalizer.py | 29758 | 5588 |
| JUDGE_ATLAS-main/backend/app/tests/test_graph_layer.py | 28216 | 4765 |
| JUDGE_ATLAS-main/artifacts/proof/current/source_registry_status.json | 27663 | 3321 |

## Largest Top-Level Directories

| path | uncompressed |
|---|---:|
| backend | 5566237 |
| frontend | 873789 |
| scripts | 812887 |
| artifacts | 581164 |
| docs | 365666 |
| .github | 50671 |
| demo | 26537 |
| infra | 17264 |
| Makefile | 8580 |
| REPO_REALITY.md | 8240 |
| STUBS_AND_PLACEHOLDERS.md | 4768 |
| STATUS.md | 3470 |
| CURRENT_STATUS.md | 2790 |
| PROOF_STATUS.md | 2686 |
| docker-compose.yml | 2496 |
| RELEASE_BLOCKERS.md | 2219 |
| README.md | 2194 |
| RELEASE_MANIFEST.json | 1701 |
| Dockerfile.proof | 890 |
| deploy | 389 |
