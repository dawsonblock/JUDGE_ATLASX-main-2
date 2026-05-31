"""Append-only audit chain for all admin mutations."""
from app.audit.append_log import append_audit_entry
from app.audit.integrity_chain import verify_chain, ChainVerificationResult

__all__ = ["append_audit_entry", "verify_chain", "ChainVerificationResult"]
