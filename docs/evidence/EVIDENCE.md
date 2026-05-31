# Evidence Storage

**Date**: 2026-05-02  
**Status**: PARTIAL — Content-addressed provenance foundation  
**NOT YET**: Encrypted legal evidence vault

---

## Current State

Evidence storage in Judge Atlas is a **content-addressed provenance foundation**, not a full legal evidence vault.

### What Works

- ✅ **SHA-256 content hashing** — Every source snapshot gets a hash
- ✅ **Source snapshots** — URL, timestamp, content, hash stored
- ✅ **Provenance chain** — Source → Snapshot → Event linking
- ✅ **Fail-closed ingestion** — Unsafe URLs blocked by SSRF protection

### What's Missing for Legal Vault

- ❌ **Encryption at rest** — Content stored plain
- ❌ **Tamper-evident logging** — No blockchain/merkle tree
- ❌ **Chain of custody** — No formal custody tracking
- ❌ **Access controls** — No granular evidence access
- ❌ **Retention policies** — No automated lifecycle
- ❌ **Digital signatures** — No signer verification
- ❌ **WORM storage** — Write-once-read-many not enforced

---

## Architecture

### Source Snapshots

```python
class SourceSnapshot:
    id: int
    url: str              # Source URL
    fetched_at: datetime  # When fetched
    content_hash: str   # SHA-256 of raw content
    raw_content: bytes  # Raw source (if stored)
    http_status: int    # HTTP response code
    headers: dict       # Response headers
    media_type: str     # Content-Type
```

### Hash Verification

```python
# Content is hashed on fetch
content_hash = sha256(raw_content).hexdigest()

# Hash is verified on retrieval
assert sha256(stored_content).hexdigest() == stored_hash
```

---

## Security Controls

### SSRF Protection

Source fetcher blocks:
- Localhost, 127.0.0.1, ::1
- Private networks (10.x, 192.168.x, 172.16-31.x)
- Link-local (169.254.x.x)
- Cloud metadata (169.254.169.254)
- File scheme (file://)
- FTP, JavaScript, data schemes

### Hash Verification

- Empty hash indicates stub/placeholder content
- Non-empty hash required for trusted sources
- Hash mismatch detection (if content changes)

---

## Use Cases

### ✅ Supported

- **Provenance tracking** — "Where did this data come from?"
- **Source verification** — "Has this content changed?"
- **Audit trail** — "When was this fetched?"
- **Research reproducibility** — "Can I re-fetch the same source?"

### ❌ Not Supported

- **Legal evidence** — Cannot be used as court evidence
- **Cryptographic proof** — No tamper-proof guarantees
- **Access control** — No granular permissions
- **Retention compliance** — No legal hold support

---

## Future: Evidence Vault

To become a legal-grade evidence vault:

1. **Encryption at rest**
   - AES-256 encryption of content
   - Key management via HSM/vault

2. **Tamper-evident logging**
   - Merkle tree of all operations
   - Blockchain anchoring (optional)
   - Immutable audit chain

3. **Chain of custody**
   - Formal custody transfers
   - Digital signatures
   - Timestamp authority

4. **Access controls**
   - Role-based evidence access
   - Need-to-know enforcement
   - Access logging

5. **Retention policies**
   - Legal hold support
   - Automated lifecycle
   - Compliance (GDPR, CCPA)

6. **WORM storage**
   - Write-once-read-many
   - Physical media separation
   - Air-gapped backups

---

## Testing

```bash
# SSRF protection tests
cd backend
pytest app/tests/test_source_fetcher_ssrf.py

# Evidence store tests
pytest app/tests/test_evidence_store.py
```

---

## Compliance Notes

### Research Use

Current implementation is suitable for:
- Academic research
- Journalism sourcing
- Transparency projects
- Internal review

### Legal Use

Current implementation is **NOT** suitable for:
- Court evidence submission
- Legal proceedings
- Regulatory compliance
- Law enforcement cases

For legal use cases, implement the "Evidence Vault" features listed above.

---

## Integration Points

### Source Fetcher

- `app/services/source_fetcher.py` — URL fetching, SSRF protection, hashing

### Snapshots

- `app/models/entities.py` — SourceSnapshot model

### Evidence Store

- `app/services/evidence_store.py` — Content-addressed storage

---

## References

- [Source Fetcher SSRF Tests](../backend/app/tests/test_source_fetcher_ssrf.py)
- [Evidence Store Tests](../backend/app/tests/test_evidence_store.py)
- [Source Snapshots](../backend/app/models/entities.py)
