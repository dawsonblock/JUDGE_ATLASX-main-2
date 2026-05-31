# Phase 5 Quick Reference — Adaptive Retry Strategy

## Import & Initialize
```python
from app.ingestion.adaptive_retry import (
    AdaptiveRetryStrategy,
    CircuitState,
    SourceSuccessMetrics,
    AdaptiveRetryParams,
    RetryDecision
)

strategy = AdaptiveRetryStrategy(db_session)
```

## Core Methods

### 1. Calculate Source Metrics
```python
metrics = strategy.calculate_source_metrics(source_key="reuters")
# Returns: SourceSuccessMetrics with success_rate, failure_streak, trend
```

### 2. Get Adaptive Parameters
```python
params = strategy.get_adaptive_params(source_key="reuters")
# Returns: AdaptiveRetryParams with max_retries, backoff, circuit_state
```

### 3. Make Retry Decision
```python
run = db_session.query(IngestionRun).filter_by(id=run_id).first()
decision = strategy.should_retry_with_adaptive_params(run, attempt_number=0)
# Returns: RetryDecision with should_retry, backoff_seconds, reason
```

### 4. Get Recovery Time Prediction
```python
recovery_time = strategy.predict_recovery_time(source_key="reuters")
# Returns: timedelta (minutes until likely recovery)
```

### 5. Check Retry Budget
```python
budget = strategy.get_retry_budget(source_key="reuters", time_window_hours=24)
# Returns: dict with remaining, total_allowed, status
```

## Decision Outcomes

### Circuit Breaker States
```
CLOSED (>70% success)     → Normal retries allowed
HALF_OPEN (20-70%)       → Limited retries, testing recovery
OPEN (<20%)              → No retries, circuit broken
```

### Max Retries by Success Rate
```
≥80%  → 3 retries
60-80% → 2 retries
40-60% → 2 retries
20-40% → 1 retry
<20%  → 0 retries (OPEN)
```

## Real-World Integration Example

```python
from app.ingestion.adaptive_retry import AdaptiveRetryStrategy
from app.ingestion.statuses import FAILED, COMPLETED
import time

def run_ingestion_with_adaptive_retry(source_key, adapter):
    strategy = AdaptiveRetryStrategy(db_session)
    
    for attempt in range(10):  # Soft limit; circuit breaker will stop it
        try:
            result = adapter.fetch_and_parse()
            if result.success:
                # Record success
                run = IngestionRun(
                    source_name=source_key,
                    status=COMPLETED,
                    started_at=datetime.now(timezone.utc),
                    persisted_count=len(result.records)
                )
                db_session.add(run)
                db_session.commit()
                return result
                
        except Exception as error:
            # Record failure
            run = IngestionRun(
                source_name=source_key,
                status=FAILED,
                started_at=datetime.now(timezone.utc),
                errors=[str(error)],
                retry_count=attempt
            )
            db_session.add(run)
            db_session.commit()
            
            # Get adaptive retry decision
            decision = strategy.should_retry_with_adaptive_params(run, attempt)
            
            if decision.should_retry:
                log.info(
                    f"Retry {attempt+1}: waiting {decision.backoff_seconds}s "
                    f"({decision.estimated_success_probability:.0%} chance). "
                    f"Reason: {decision.reason}"
                )
                time.sleep(decision.backoff_seconds)
            else:
                log.error(f"Giving up after {attempt+1} attempts: {decision.reason}")
                raise
    
    raise Exception(f"Max retries exceeded for {source_key}")
```

## Monitoring Dashboard Template

```python
def print_source_status(source_key):
    strategy = AdaptiveRetryStrategy(db_session)
    
    metrics = strategy.calculate_source_metrics(source_key)
    params = strategy.get_adaptive_params(source_key)
    budget = strategy.get_retry_budget(source_key)
    
    print(f"""
    ╔═════════════════════════════════════════════╗
    ║ {source_key:^43} ║
    ╚═════════════════════════════════════════════╝
    
    Performance:
      Success Rate     : {metrics.success_rate:>6.1%}
      Trend            : {metrics.trend:>6} (last 10 runs: {metrics.recent_success_rate:.1%})
      Failure Streak   : {metrics.failure_streak:>6}
      Total Runs       : {metrics.total_runs:>6}
    
    Retry Strategy:
      Circuit State    : {params.circuit_state.value:>6}
      Max Retries      : {params.max_retries:>6}
      Base Backoff     : {params.base_backoff_seconds:>6}s
      Recovery Time    : {params.estimated_recovery_time:>6} min
      Confidence       : {params.confidence:>6.0%}
    
    Retry Budget (24h):
      Used             : {budget['used']:>6} / {budget['total_allowed']}
      Remaining        : {budget['remaining']:>6}
      Status           : {budget['status']:>6}
    """)

# Usage
print_source_status("legal_canada_daily")
print_source_status("court_decisions_api")
```

## Data Flow Diagram

```
┌──────────────────────────────────┐
│ IngestionRun fails               │
│ (source_name, status=FAILED)     │
└──────────────────────┬────────────┘
                       │
                       ▼
        ┌──────────────────────────┐
        │ should_retry_with_       │
        │ adaptive_params(run)     │
        └──────────────┬───────────┘
                       │
        ┌──────────────┴────────────┐
        │                           │
        ▼                           ▼
    (1) get_adaptive_params()   (Circuit check)
        │                           │
        ├─ calculate_source_metrics()
        │  • Count successes/failures (last 50 runs)
        │  • Calculate success rate
        │  • Detect trend
        │  • Estimate recovery time
        │
        ├─ determine_circuit_state()
        │  • CLOSED if >70% success
        │  • HALF_OPEN if 20-70%
        │  • OPEN if <20%
        │
        ├─ adjust_max_retries()
        │  • 3 if ≥80%, 2 if 60-80%, etc.
        │
        ├─ adjust_backoff_base()
        │  • Base on recovery time
        │
        └─ calculate_success_probability()
           • Account for trend, streak, attempt #
           
                       │
                       ▼
        ┌──────────────────────────┐
        │ RetryDecision            │
        │ • should_retry           │
        │ • backoff_seconds        │
        │ • estimated_success_prob │
        └──────────────┬───────────┘
                       │
        ┌──────────────┴────────────┐
        │                           │
        ▼ (YES)              ▼ (NO)
    Sleep & retry       No retry
```

## Key Thresholds

| Parameter | Value | Meaning |
|-----------|-------|---------|
| min_samples_for_adaptation | 5 | Need 5+ runs before adapting |
| circuit_failure_threshold | 0.2 | <20% success opens circuit |
| circuit_recovery_threshold | 0.7 | >70% success closes circuit |
| health_degradation_threshold | 0.6 | <0.6 health score is critical |
| half_open_retry_limit | 2 | Max 2 retries while testing |
| retry_budget (24h) | 10 × 24 = 240 | 10 retries/hour limit |

## Common Patterns

### Pattern 1: Adaptive Retry with Phase 4 Integration
```python
from app.ingestion.recovery_strategies import classify_error

decision = strategy.should_retry_with_adaptive_params(run, attempt)

if decision.should_retry:
    # Optionally use Phase 4 classification for context
    error_class = classify_error(run.errors[0] if run.errors else "")
    log.debug(f"Retry: {error_class.strategy}, Adaptive: {decision.strategy}")
```

### Pattern 2: Dead-Letter Queue Bulk Retry
```python
from app.ingestion.dead_letter_queue import DeadLetterQueue

dlq = DeadLetterQueue(db_session)
strategy = AdaptiveRetryStrategy(db_session)

for run in dlq.list_quarantined_runs(source_key="reuters", limit=100):
    params = strategy.get_adaptive_params(run.source_name)
    
    if params.circuit_state != CircuitState.OPEN:
        # Schedule for retry
        recovery_time = strategy.predict_recovery_time(run.source_name)
        scheduled_at = datetime.now(timezone.utc) + recovery_time
        dlq.schedule_retry(run.id, scheduled_at)
```

### Pattern 3: Monitoring with Alerts
```python
def alert_on_degradation():
    sources = db_session.query(SourceRegistry).all()
    
    for source in sources:
        metrics = strategy.calculate_source_metrics(source.source_key)
        params = strategy.get_adaptive_params(source.source_key)
        
        if params.circuit_state == CircuitState.OPEN:
            alert(f"CRITICAL: {source.source_name} circuit OPEN",
                  severity="CRITICAL")
        
        elif metrics.trend == "degrading" and metrics.recent_success_rate < 0.6:
            alert(f"WARNING: {source.source_name} degrading (trend: {metrics.trend})",
                  severity="WARNING")
        
        elif metrics.failure_streak >= 5:
            alert(f"INFO: {source.source_name} on failure streak ({metrics.failure_streak})",
                  severity="INFO")
```

## Testing

Run Phase 5 tests:
```bash
cd backend

# Phase 5 only
pytest app/tests/test_phase5_adaptive_retry.py -v

# Phase 4 + 5
pytest app/tests/test_phase4_recovery.py app/tests/test_phase5_adaptive_retry.py -v

# Expected: 64 tests passing (39 Phase 4 + 25 Phase 5)
```

## Troubleshooting

### Circuit Stuck OPEN
```python
# Check if recovery threshold can be met
metrics = strategy.calculate_source_metrics(source_key)
print(f"Current success rate: {metrics.success_rate:.1%}")
print(f"Need: >70% to close circuit")
print(f"Gap: {0.70 - metrics.success_rate:.1%}")

# Solution: Manual recovery or data cleanup
```

### Retries Not Happening
```python
# Debug: Check circuit state
params = strategy.get_adaptive_params(source_key)
print(f"Circuit state: {params.circuit_state.value}")  # Should be CLOSED

# Check: Max retries
print(f"Max retries: {params.max_retries}")  # Should be >0

# Check: Success probability
decision = strategy.should_retry_with_adaptive_params(run, attempt=0)
print(f"Success probability: {decision.estimated_success_probability:.1%}")
```

### Budget Exceeded
```python
# Check budget status
budget = strategy.get_retry_budget(source_key, time_window_hours=24)
print(f"Remaining: {budget['remaining']} / {budget['total_allowed']}")

# Solution: Wait for window to reset or increase budget threshold
```
