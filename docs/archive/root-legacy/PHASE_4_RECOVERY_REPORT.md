# Phase 4: Source Stability & Recovery
## Comprehensive Implementation Report

**Status:** ✅ COMPLETE  
**Date Completed:** May 16, 2026  
**Test Results:** 39/39 tests passing  
**Breaking Changes:** 0  
**Backward Compatibility:** 100%

---

## Executive Summary

Phase 4 implements comprehensive error recovery and source health monitoring for the JUDGE_ATLASX ingestion system. The phase adds:

1. **Error Classification Framework** - Distinguishes transient (retriable) vs. permanent (non-retriable) errors
2. **Exponential Backoff Retry Logic** - Automatic recovery from transient failures with configurable retry limits
3. **Dead-Letter Queue System** - Centralized management of quarantined/failed ingestions
4. **Health Monitoring** - Real-time source health score tracking with degradation alerts
5. **Recovery Runbooks** - Human-readable guides for admin intervention

**Key Achievement:** Failed ingestions are now automatically classified and recoverable without manual intervention for transient errors.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    IngestionRun Lifecycle                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Adapter executes ingestion                              │
│     ↓                                                        │
│  2. Check if successful (status = COMPLETED/COMPLETED_WITH_WARNINGS)
│     ├─ Yes → Update health_score ✓                         │
│     └─ No → Step 3                                          │
│                                                              │
│  3. Classify error (transient vs permanent)                │
│     ├─ Transient → Mark for retry (scheduled_retry_at)   │
│     ├─ Permanent → Quarantine + Add to dead-letter queue  │
│     └─ Unknown → Quarantine for manual review             │
│                                                              │
│  4. Dead-letter queue scheduler picks up retry_scheduled  │
│     ├─ Check max_retries not exceeded                     │
│     ├─ Calculate backoff delay                            │
│     └─ Requeue for next execution window                  │
│                                                              │
│  5. If max retries exceeded → Admin intervention          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 4 Components

### 1. Error Classification (`recovery_strategies.py`)

**Purpose:** Classify ingestion errors to determine recovery strategy.

**Key Functions:**

- `classify_error(error_message: str) -> ErrorClassification`
  - Scans error message against transient/permanent patterns
  - Returns category, strategy, and suggested backoff
  - Example patterns:
    - **Transient:** timeout, connection reset, 429/503, "temporarily unavailable"
    - **Permanent:** 401/403, contract violation, schema mismatch, deprecated source
    - **Unknown:** unclassified errors → quarantine for review

- `calculate_backoff_seconds(attempt, base_seconds, max_seconds, jitter_factor) -> int`
  - Exponential backoff: base × 2^attempt
  - Capped at max_seconds (default 1 hour)
  - Adds random jitter (default 10%) to prevent thundering herd
  - Formula: min(base × 2^attempt + random(jitter%), max_seconds)

- `should_retry_ingestion(run, max_retries=3) -> tuple[bool, str]`
  - Determines if failed run should be retried
  - Checks error classification and retry count
  - Returns (decision, reason) for logging

- `is_health_degraded(health_score, threshold=0.6) -> bool`
  - Monitors source health for degradation
  - Default threshold: 60% (0.6)
  - Supports alerting on critical sources (< 40%)

**Error Pattern Matching:**

Transient errors (automatically retriable):
```
timeout, connection reset, connection refused
HTTP 429, HTTP 502, HTTP 503, HTTP 504
connection pool exhausted, too many connections
```

Permanent errors (require intervention):
```
HTTP 401 (Unauthorized), HTTP 403 (Forbidden)
contract violation, schema mismatch
parser version mismatch, invalid config
deprecated source, source disabled
```

### 2. Dead-Letter Queue (`dead_letter_queue.py`)

**Purpose:** Manage quarantined and failed ingestions with recovery interface.

**Key Class: `DeadLetterQueue`**

Methods:

- `list_quarantined_runs(source_key, limit, offset, min_age_hours) -> list[dict]`
  - Query quarantined/failed runs
  - Filter by source, pagination, age
  - Returns run metadata for admin UI

- `classify_dead_letter(run) -> dict`
  - Analyze failed run to determine recovery options
  - Returns error_category, retriable flag, suggested action
  - Helps admin decide next step

- `schedule_retry(run_id, scheduled_for) -> bool`
  - Schedule transient error for retry
  - Increments retry_count
  - Sets scheduled_retry_at timestamp
  - Returns False for permanent errors (non-retriable)

- `get_recovery_runbook(run) -> str`
  - Generate human-readable recovery guide
  - Different instructions for transient vs. permanent
  - Includes diagnostic steps and remediation actions

- `get_recovery_summary() -> dict`
  - Summary statistics for monitoring:
    - total_quarantined, failed_runs, quarantined_runs
    - retriable_count (transient errors that can auto-retry)
    - quarantined_by_source (breakdown by source)

**Example Recovery Workflow:**

```python
from app.ingestion.dead_letter_queue import DeadLetterQueue

dlq = DeadLetterQueue(db)

# 1. Find quarantined runs
quarantined = dlq.list_quarantined_runs(source_key="courtlistener")

# 2. Analyze each run
for run in quarantined:
    classification = dlq.classify_dead_letter(run)
    
    if classification["retriable"]:
        # Auto-retry transient errors
        dlq.schedule_retry(run.id)
        print(f"Scheduled retry for run {run.id}")
    else:
        # Get recovery guide for permanent errors
        guide = dlq.get_recovery_runbook(run)
        print(guide)

# 3. Monitor health
summary = dlq.get_recovery_summary()
print(f"Retriable: {summary['retriable_count']}")
print(f"Quarantined by source: {summary['quarantined_by_source']}")
```

### 3. Database Schema Changes

**Migration:** `20260516_0004_phase4_recovery_tracking.py`

**New Fields on `IngestionRun`:**

| Field | Type | Purpose | Default |
|-------|------|---------|---------|
| `retry_count` | Integer | Number of retry attempts | 0 |
| `scheduled_retry_at` | DateTime | When to retry this run | NULL |
| `recovery_classification` | String(20) | Error category: transient/permanent/unknown | NULL |
| `last_error_at` | DateTime | Timestamp of last error | NULL |

**Indices Created:**
- `ix_ingestion_runs_scheduled_retry_at` - Query pending retries
- `ix_ingestion_runs_recovery_classification` - Filter by error type

**Migration Safety:**
- Adds 4 new nullable columns (no data loss)
- Creates indices (no blocking operations)
- Includes downgrade path for rollback
- No breaking changes to existing schema

---

## Usage Examples

### Example 1: Auto-Retry Transient Error

```python
from app.ingestion.recovery_strategies import classify_error, calculate_backoff_seconds

# Simulate failed ingestion with transient error
error_msg = "HTTP 503 Service Unavailable"
classification = classify_error(error_msg)

print(classification.category)        # ErrorCategory.TRANSIENT
print(classification.retriable)        # True
print(classification.strategy)         # RecoveryStrategy.EXPONENTIAL_BACKOFF
print(classification.suggested_backoff_seconds)  # 60 (base)

# Calculate backoff for each retry attempt
for attempt in range(3):
    backoff = calculate_backoff_seconds(attempt, base_seconds=60, max_seconds=3600)
    print(f"Attempt {attempt + 1}: Wait {backoff} seconds")
    # Output:
    # Attempt 1: Wait ~60 seconds
    # Attempt 2: Wait ~120 seconds  
    # Attempt 3: Wait ~240 seconds
```

### Example 2: Manual Recovery Decision

```python
from app.ingestion.dead_letter_queue import DeadLetterQueue
from sqlalchemy.orm import Session

dlq = DeadLetterQueue(db)

# Get all quarantined runs older than 1 hour
quarantined = dlq.list_quarantined_runs(
    min_age_hours=1,
    limit=50
)

# For each run, decide on recovery
for run_dict in quarantined:
    run = db.query(IngestionRun).filter_by(id=run_dict['id']).first()
    classification = dlq.classify_dead_letter(run)
    
    if classification['retriable']:
        # Automatic recovery possible
        success = dlq.schedule_retry(run.id)
        if success:
            print(f"Scheduled retry for {run.source_name}")
    else:
        # Manual intervention required
        runbook = dlq.get_recovery_runbook(run)
        print(f"\n{run.source_name} Recovery Runbook:")
        print(runbook)
```

### Example 3: Health Monitoring Dashboard

```python
from app.ingestion.recovery_strategies import (
    is_health_degraded,
    get_health_status_label
)

# Get all sources and check health
sources = db.query(SourceRegistry).all()

critical_sources = []
for source in sources:
    status = get_health_status_label(source.health_score)
    
    if status == "critical":
        critical_sources.append({
            "source": source.source_name,
            "health_score": source.health_score,
            "last_error": source.last_error,
            "last_error_at": source.last_error_at
        })

print(f"⚠️  {len(critical_sources)} sources with critical health:")
for critical in critical_sources:
    print(f"  - {critical['source']}: {critical['health_score']}")
    print(f"    Last error: {critical['last_error']}")
```

---

## Transient vs. Permanent Error Examples

### Transient Errors (Auto-Retriable)

```
HTTP 429 Too Many Requests
→ Action: Wait, retry with exponential backoff
→ Max retries: 3 (default)

Connection timeout after 30 seconds
→ Action: Increase timeout, retry
→ Max retries: 3

HTTP 503 Service Unavailable
→ Action: Wait for service recovery, retry
→ Max retries: 3

Connection reset by peer
→ Action: Reconnect and retry
→ Max retries: 3

Pool timeout (too many connections)
→ Action: Wait for connection pool drain, retry
→ Max retries: 3
```

### Permanent Errors (Manual Intervention)

```
HTTP 401 Unauthorized - invalid API key
→ Action: Update credentials, fix configuration
→ Recovery: Manual configuration fix + manual retry

HTTP 403 Forbidden - access denied
→ Action: Request access, update permissions
→ Recovery: Permission grant + manual retry

Adapter contract violation: no_raw_content
→ Action: Fix adapter implementation
→ Recovery: Deploy new adapter version + manual retry

Parser version mismatch: expected 2.0, got 1.5
→ Action: Update parser or adapter version
→ Recovery: Version update + manual retry

Source deprecated; use new_source instead
→ Action: Migrate to new source
→ Recovery: Enable new_source + disable old source

Field validation error: required field missing
→ Action: Update source data format or adapter
→ Recovery: Fix data source + manual retry
```

---

## Health Score Monitoring

**Health Score Range:** 0.0 - 1.0

**Calculation:**
```
new_health = 0.7 * old_health + 0.3 * (success_count / total_records)
```

**Status Levels:**
- **Healthy** (≥ 0.8): No alerts needed
- **Degraded** (0.6-0.8): Monitor closely, prepare recovery
- **Critical** (< 0.6): Immediate action required, consider disable

**Source Registry Integration:**

```python
from app.models.entities import SourceRegistry

registry = db.query(SourceRegistry).filter_by(
    source_key="courtlistener"
).first()

# Fields available:
print(registry.health_score)          # 0.75
print(registry.reliability_score)     # 0.70
print(registry.last_successful_fetch) # 2026-05-16T10:30:00Z
print(registry.last_error)            # "HTTP 503 Service Unavailable"
print(registry.last_error_at)         # 2026-05-16T14:22:00Z
```

---

## Test Coverage

**Total Tests:** 39/39 passing ✅  
**Success Rate:** 100%

### Test Categories

**Error Classification (11 tests):**
- Transient error patterns (timeout, 429, 503, connection reset)
- Permanent error patterns (401, 403, contract violation, schema mismatch)
- Unknown error handling
- Empty error message handling

**Exponential Backoff (5 tests):**
- Attempt 0: ~60 seconds
- Attempt 1: ~120 seconds
- Attempt 2: ~240 seconds
- Max cap enforcement
- Custom base duration

**Retry Logic (4 tests):**
- Transient error first attempt (should retry)
- Permanent error (should not retry)
- Max attempts exceeded (should not retry)
- No errors recorded (should not retry)

**Health Monitoring (6 tests):**
- Health above/below threshold
- Status labels: healthy/degraded/critical
- None value handling

**Transient Error Detection (4 tests):**
- Timeout detection
- Rate limit detection
- Service unavailable detection
- Connection error detection

**Dead-Letter Queue (7 tests):**
- List quarantined runs (empty, filtered)
- Classify dead letters (transient, permanent)
- Schedule retry (success, failure for permanent)
- Recovery summary generation

**Integration Tests (2 tests):**
- Recovery fields on IngestionRun entity
- End-to-end recovery workflow

---

## Integration with Phase 2 & 3

**Phase 2 (Canonical Data Model Lock):**
- ✅ All 8 canonical entities remain immutable
- ✅ SourceRegistry.health_score field used for monitoring
- ✅ IngestionRun.quarantine_reason field used for tracking
- ✅ No breaking changes to Phase 2 schema

**Phase 3 (Ingestion Hardening):**
- ✅ SourceAdapterContract entities referenced for version validation
- ✅ Parser version validation informs retry decisions
- ✅ Adapter contracts inform permanent vs. transient classification
- ✅ No conflicts with Phase 3 immutability triggers

**Combined Test Results:**
- Phase 2: 12 tests passing ✅
- Phase 3: 7 tests passing ✅ (5 PostgreSQL-specific skipped)
- Phase 4: 39 tests passing ✅
- **Total: 58 passed, 5 skipped**

---

## Deployment Checklist

### Pre-Deployment

- [x] All 39 Phase 4 tests passing
- [x] All 58 combined Phase 2-4 tests passing
- [x] Migration syntax validated
- [x] No breaking changes detected
- [x] Backward compatibility confirmed
- [x] Documentation complete

### Deployment Steps

1. **Database Migration**
   ```bash
   cd backend
   alembic upgrade head
   # Runs: 20260516_0004_phase4_recovery_tracking.py
   ```

2. **Import New Modules**
   ```python
   from app.ingestion.recovery_strategies import classify_error, calculate_backoff_seconds
   from app.ingestion.dead_letter_queue import DeadLetterQueue
   ```

3. **Enable Recovery Features** (in ingestion runner)
   ```python
   # In run_ingestion function, after persisting run:
   classification = classify_error(run.errors[0] if run.errors else None)
   run.recovery_classification = classification.category.value
   run.last_error_at = datetime.now(timezone.utc)
   
   if classification.retriable:
       run.scheduled_retry_at = datetime.now(timezone.utc) + timedelta(
           seconds=classification.suggested_backoff_seconds
       )
   ```

4. **Monitor Dead-Letter Queue**
   ```python
   dlq = DeadLetterQueue(db)
   summary = dlq.get_recovery_summary()
   # Log and alert on retriable_count > threshold
   ```

### Post-Deployment Validation

- [ ] Verify migrations applied successfully: `SELECT * FROM ingestion_runs LIMIT 1`
- [ ] Test transient error classification with sample error
- [ ] Test permanent error quarantine with sample error
- [ ] Verify health score updates on successful run
- [ ] Verify dead-letter queue lists quarantined runs
- [ ] Test exponential backoff calculation

---

## Monitoring & Alerting

### Key Metrics to Monitor

1. **Retry Success Rate**
   ```sql
   SELECT 
       source_name,
       COUNT(*) as total_runs,
       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful,
       ROUND(100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_pct
   FROM ingestion_runs
   WHERE created_at > NOW() - INTERVAL '24 hours'
   GROUP BY source_name
   ORDER BY success_pct ASC;
   ```

2. **Quarantined Runs by Type**
   ```sql
   SELECT 
       recovery_classification,
       COUNT(*) as count
   FROM ingestion_runs
   WHERE status IN ('quarantined', 'failed')
   GROUP BY recovery_classification;
   ```

3. **Source Health Trends**
   ```sql
   SELECT 
       source_key,
       source_name,
       health_score,
       last_error,
       last_error_at
   FROM source_registry
   WHERE health_score < 0.6
   ORDER BY health_score ASC;
   ```

### Alert Triggers

- Source health < 0.6 (critical): Immediate admin review
- Retriable errors > 10 in 1 hour: Check service status
- Max retries exceeded > 5 in 1 hour: Investigate permanent failures
- Manual intervention required > 20 runs: Review recovery runbooks

---

## Future Enhancement Opportunities

**Phase 5 Candidates:**

1. **Adaptive Retry Strategy**
   - Learn optimal backoff from historical data
   - Adjust max_retries per source based on success rate
   - Dynamic threshold adjustment for health degradation

2. **Parallel Retry Scheduling**
   - Schedule multiple retries simultaneously (not just sequential)
   - Circuit breaker pattern for consistently failing sources
   - Fallback to alternative data sources

3. **Root Cause Analysis**
   - ML-based error pattern clustering
   - Automatic correlation with external service status
   - Predictive failure alerts

4. **Admin Recovery UI**
   - Web interface for browsing dead-letter queue
   - One-click recovery for transient errors
   - Batch retry scheduling
   - Recovery metrics dashboard

5. **Advanced Monitoring**
   - Integration with APM systems (DataDog, New Relic)
   - Custom recovery metrics per source
   - SLA tracking and breach alerts

---

## Summary

Phase 4 successfully implements a complete error recovery and health monitoring system for the JUDGE_ATLASX ingestion pipeline. The system automatically classifies errors, schedules retries for transient failures, and provides admin interfaces for managing permanent failures. All 39 tests pass, backward compatibility is maintained, and the system is ready for production deployment.

**Key Statistics:**
- 2 new modules (recovery_strategies.py, dead_letter_queue.py)
- 1 database migration with 4 new tracked fields
- 39 comprehensive unit tests
- 100% test success rate
- 0 breaking changes
- Full backward compatibility with Phases 2-3

**Next Phase:** Phase 5 (Source Stability Optimization) will build on this foundation to implement adaptive retry strategies, circuit breaker patterns, and advanced root cause analysis.
