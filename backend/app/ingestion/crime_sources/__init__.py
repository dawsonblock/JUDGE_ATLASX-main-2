"""Controlled manual/import adapters for reported crime incident sources.

.. warning::
   This package is EXPERIMENTAL / PARTIAL.  Modules here bypass the
   SSRF-safe ``app.ingestion.fetcher.fetch_for_ingestion`` path in several
   places.  They must not be imported by general runtime code; the only
   authorised production caller is ``app.api.routes.admin_ingest`` (gated
   by ``JTA_ENABLE_ADMIN_IMPORTS``).
"""

# Sentinel consumed by scripts/check_no_direct_ingestion_network_clients.py
# and the check_repo_boundaries guard to warn when non-authorised runtime
# code imports from this package.
NOT_RUNTIME: bool = True

