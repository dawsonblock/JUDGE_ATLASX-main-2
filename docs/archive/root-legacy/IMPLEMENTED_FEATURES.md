# Implemented Features

Date: 2026-05-06

This file lists implemented features only. Items that require missing credentials, manual setup, or incomplete review are marked with their limitation.

## Backend

- FastAPI app factory and route registration.
- SQLAlchemy ORM models for locations, courts, judges, cases, defendants, events, crime incidents, sources, snapshots, users, audit logs, graph/evidence/memory-related records.
- Alembic migration tree with a current single-head requirement.
- Source registry seed/validation flow for Canada/Saskatchewan sources.
- Source-class gating for automated ingestion eligibility.
- Evidence snapshot write/read/verification helpers with SHA-256 integrity checks.
- Review-first publication gates and public visibility filtering.
- Rate limiting with memory/Redis backends.
- JWT token helper code and password hashing support.
- Development shared-token admin compatibility.
- `judgectl` command entrypoint and existing command modules.

## Frontend

- Next.js App Router frontend.
- shadcn/Radix-style component library.
- Dashboard, entity pages, source pages, admin source/review pages.
- MapLibre map workspace under `/map`.
- Typed fetch API helpers.

## Operations

- Docker Compose stack for local Postgres/PostGIS, Redis, backend, and frontend.
- Existing verification scripts for backend, frontend, Docker, source validation, and proof.
- Added truth-claim and full-stack proof entrypoints in this repair pass.

## Explicit limitations

- JWT/RBAC is not yet the only mutation auth path.
- MapLibre is not yet the only map route.
- Source adapters need per-source fixture/proof before they can be called operational.
- AI is constrained to reviewer assistance and deterministic/rule-based checks unless a provider is explicitly configured and validated.
