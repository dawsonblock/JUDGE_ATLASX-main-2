"""
Phase 5: Adaptive Retry Strategy Tests

Comprehensive test coverage for adaptive retry functionality including:
- Source success metrics calculation
- Circuit breaker state transitions
- Max retry adjustments
- Backoff duration optimization
- Success probability estimation
- Retry decisions
- Recovery time prediction
- Budget management
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.ingestion.adaptive_retry import (
    AdaptiveRetryStrategy,
    CircuitState,
    SourceSuccessMetrics,
    AdaptiveRetryParams,
    RetryDecision
)
from app.models.entities import SourceRegistry, IngestionRun
from app.ingestion.statuses import COMPLETED, FAILED, QUARANTINED


@pytest.mark.usefixtures("db_session")
class TestSourceSuccessMetrics:
    """Tests for source success metric calculation."""

    def test_metrics_with_no_runs(self, db_session: Session):
        """Test metrics when source has no ingestion history."""
        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("nonexistent_source")

        assert metrics.total_runs == 0
        assert metrics.successful_runs == 0
        assert metrics.failed_runs == 0
        assert metrics.success_rate == 0.5  # Conservative default
        assert metrics.recent_success_rate == 0.5
        assert metrics.failure_streak == 0
        assert metrics.trend == "unknown"

    def test_metrics_all_successful(self, db_session: Session):
        """Test metrics when all runs are successful."""
        # Create source and successful runs
        source = SourceRegistry(
            source_key="test_source",
            source_name="test_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        for i in range(5):
            run = IngestionRun(
                source_name="test_source",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("test_source")

        assert metrics.total_runs == 5
        assert metrics.successful_runs == 5
        assert metrics.failed_runs == 0
        assert metrics.success_rate == 1.0
        assert metrics.recent_success_rate == 1.0
        assert metrics.failure_streak == 0

    def test_metrics_all_failed(self, db_session: Session):
        """Test metrics when all runs fail."""
        source = SourceRegistry(
            source_key="failing_source",
            source_name="failing_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        for i in range(5):
            run = IngestionRun(
                source_name="failing_source",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Connection timeout"]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("failing_source")

        assert metrics.total_runs == 5
        assert metrics.successful_runs == 0
        assert metrics.failed_runs == 5
        assert metrics.success_rate == 0.0
        assert metrics.failure_streak == 5  # All recent runs failed
        assert metrics.trend in ["degrading", "stable"]  # Both are valid when all fail

    def test_metrics_mixed_with_trend_improving(self, db_session: Session):
        """Test metrics when performance is improving."""
        source = SourceRegistry(
            source_key="improving_source",
            source_name="improving_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Early runs: 2 successes, 3 failures (40% success)
        base_time = datetime.now(timezone.utc) - timedelta(hours=10)
        statuses = [FAILED, FAILED, FAILED, COMPLETED, COMPLETED]
        for i, status in enumerate(statuses):
            run = IngestionRun(
                source_name="improving_source",
                started_at=datetime.now(timezone.utc),
                status=status,
                persisted_count=100 if status == COMPLETED else 0,
                errors=[] if status == COMPLETED else ["Error"],
                created_at=base_time + timedelta(hours=i)
            )
            db_session.add(run)

        # Recent runs: 8 successes, 2 failures (80% success)
        for i in range(8):
            run = IngestionRun(
                source_name="improving_source",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[],
                created_at=base_time + timedelta(hours=5 + i)
            )
            db_session.add(run)
        for i in range(2):
            run = IngestionRun(
                source_name="improving_source",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Error"],
                created_at=base_time + timedelta(hours=13 + i)
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("improving_source")

        assert metrics.total_runs >= 10
        assert metrics.recent_success_rate > metrics.success_rate
        assert metrics.trend == "improving"

    def test_failure_streak_calculation(self, db_session: Session):
        """Test that failure streaks are calculated correctly."""
        source = SourceRegistry(
            source_key="streak_source",
            source_name="streak_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Sequence: SUCCESS, FAILED, FAILED, FAILED, FAILED (4-run failure streak)
        base_time = datetime.now(timezone.utc)
        statuses = [COMPLETED, FAILED, FAILED, FAILED, FAILED]
        for i, status in enumerate(statuses):
            run = IngestionRun(
                source_name="streak_source",
                started_at=datetime.now(timezone.utc),
                status=status,
                persisted_count=100 if status == COMPLETED else 0,
                errors=[] if status == COMPLETED else ["Error"],
                created_at=base_time + timedelta(hours=i)
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("streak_source")

        assert metrics.failure_streak == 4


@pytest.mark.usefixtures("db_session")
class TestCircuitBreaker:
    """Tests for circuit breaker state transitions."""

    def test_circuit_closed_high_success_rate(self, db_session: Session):
        """Test circuit stays closed with high success rate."""
        source = SourceRegistry(
            source_key="healthy_source",
            source_name="healthy_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # 9 successful, 1 failed = 90% success rate
        for i in range(9):
            run = IngestionRun(
                source_name="healthy_source",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[]
            )
            db_session.add(run)
        run = IngestionRun(
            source_name="healthy_source",
                started_at=datetime.now(timezone.utc),
            status=FAILED,
            persisted_count=0,
            errors=["Temporary error"]
        )
        db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("healthy_source")
        state = strategy.determine_circuit_state("healthy_source", metrics)

        assert state == CircuitState.CLOSED
        assert metrics.success_rate == 0.9

    def test_circuit_open_low_success_rate(self, db_session: Session):
        """Test circuit opens with very low success rate."""
        source = SourceRegistry(
            source_key="broken_source",
            source_name="broken_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # 1 successful, 9 failed = 10% success rate (below 20% threshold)
        run = IngestionRun(
            source_name="broken_source",
                started_at=datetime.now(timezone.utc),
            status=COMPLETED,
            persisted_count=100,
            errors=[]
        )
        db_session.add(run)
        for i in range(9):
            run = IngestionRun(
                source_name="broken_source",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Connection refused"]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("broken_source")
        state = strategy.determine_circuit_state("broken_source", metrics)

        assert state == CircuitState.OPEN
        assert metrics.success_rate == 0.1

    def test_circuit_half_open_moderate_success_rate(self, db_session: Session):
        """Test circuit enters half-open with moderate success rate."""
        source = SourceRegistry(
            source_key="recovering_source",
            source_name="recovering_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # 5 successful, 5 failed = 50% success rate (between 20% and 70%)
        for i in range(5):
            run = IngestionRun(
                source_name="recovering_source",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[]
            )
            db_session.add(run)
        for i in range(5):
            run = IngestionRun(
                source_name="recovering_source",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Transient error"]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("recovering_source")
        state = strategy.determine_circuit_state("recovering_source", metrics)

        assert state == CircuitState.HALF_OPEN
        assert metrics.success_rate == 0.5


@pytest.mark.usefixtures("db_session")
class TestMaxRetriesAdjustment:
    """Tests for dynamic max_retries adjustment."""

    def test_max_retries_high_success_rate(self, db_session: Session):
        """Test max_retries is 3 for high success rate."""
        source = SourceRegistry(
            source_key="good_source",
            source_name="good_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create 10 successful runs
        for i in range(10):
            run = IngestionRun(
                source_name="good_source",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("good_source")
        max_retries = strategy.adjust_max_retries(metrics)

        assert max_retries == 3
        assert metrics.success_rate >= 0.8

    def test_max_retries_poor_success_rate(self, db_session: Session):
        """Test max_retries is reduced for poor success rate."""
        source = SourceRegistry(
            source_key="poor_source",
            source_name="poor_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create 3 successful, 7 failed (30% success)
        for i in range(3):
            run = IngestionRun(
                source_name="poor_source",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[]
            )
            db_session.add(run)
        for i in range(7):
            run = IngestionRun(
                source_name="poor_source",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Error"]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("poor_source")
        max_retries = strategy.adjust_max_retries(metrics)

        # 30% success rate falls in 0.2-0.4 range, gets max_retries=1
        assert max_retries == 1
        assert metrics.success_rate == 0.3

    def test_max_retries_circuit_open(self, db_session: Session):
        """Test max_retries is 0 when circuit opens."""
        source = SourceRegistry(
            source_key="dead_source",
            source_name="dead_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create 2 successful, 18 failed (10% success - below 20%)
        for i in range(2):
            run = IngestionRun(
                source_name="dead_source",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[]
            )
            db_session.add(run)
        for i in range(18):
            run = IngestionRun(
                source_name="dead_source",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Persistent failure"]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("dead_source")
        max_retries = strategy.adjust_max_retries(metrics)

        assert max_retries == 0
        assert metrics.success_rate < 0.2


@pytest.mark.usefixtures("db_session")
class TestBackoffAdjustment:
    """Tests for adaptive backoff duration adjustment."""

    def test_backoff_uses_recovery_time(self, db_session: Session):
        """Test that backoff is adjusted based on observed recovery times."""
        source = SourceRegistry(
            source_key="slow_recover_source",
            source_name="slow_recover_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create pattern: failure -> wait -> success (simulating recovery)
        base_time = datetime.now(timezone.utc)
        
        # Sequence of failures followed by recovery (30 min recovery time)
        for cycle in range(3):
            run = IngestionRun(
                source_name="slow_recover_source",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Unavailable"],
                created_at=base_time + timedelta(hours=cycle*2)
            )
            db_session.add(run)
            
            run = IngestionRun(
                source_name="slow_recover_source",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[],
                created_at=base_time + timedelta(hours=cycle*2 + 0.5)  # 30 min after failure
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("slow_recover_source")
        base_backoff = strategy.adjust_backoff_base(metrics)

        # Recovery time should be around 30 minutes, so backoff should be ~15 minutes
        assert metrics.avg_time_to_recovery_minutes > 0
        assert base_backoff > 60  # More than default 60 seconds
        assert base_backoff <= 600  # But less than 10 minutes cap


@pytest.mark.usefixtures("db_session")
class TestSuccessProbabilityEstimation:
    """Tests for success probability calculation."""

    def test_success_probability_high_success_rate(self, db_session: Session):
        """Test high probability for source with good history."""
        source = SourceRegistry(
            source_key="reliable_source",
            source_name="reliable_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create 9 successful runs
        for i in range(9):
            run = IngestionRun(
                source_name="reliable_source",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("reliable_source")
        
        probability = strategy.calculate_success_probability(
            metrics, attempt_number=0, circuit_state=CircuitState.CLOSED
        )

        assert probability > 0.7  # High probability
        assert metrics.success_rate == 1.0

    def test_success_probability_circuit_open(self, db_session: Session):
        """Test very low probability when circuit is open."""
        source = SourceRegistry(
            source_key="broken_service",
            source_name="broken_service",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create failing source
        for i in range(10):
            run = IngestionRun(
                source_name="broken_service",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Service down"]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("broken_service")
        
        probability = strategy.calculate_success_probability(
            metrics, attempt_number=0, circuit_state=CircuitState.OPEN
        )

        assert probability <= 0.05  # Very low probability when circuit open

    def test_success_probability_decreases_with_attempts(self, db_session: Session):
        """Test that success probability decreases with more attempts."""
        source = SourceRegistry(
            source_key="test_attempts",
            source_name="test_attempts",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Average source
        for i in range(5):
            run = IngestionRun(
                source_name="test_attempts",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        metrics = strategy.calculate_source_metrics("test_attempts")
        
        prob_attempt_0 = strategy.calculate_success_probability(
            metrics, attempt_number=0, circuit_state=CircuitState.CLOSED
        )
        prob_attempt_2 = strategy.calculate_success_probability(
            metrics, attempt_number=2, circuit_state=CircuitState.CLOSED
        )

        assert prob_attempt_0 > prob_attempt_2


@pytest.mark.usefixtures("db_session")
class TestAdaptiveRetryDecision:
    """Tests for overall retry decision making."""

    def test_retry_decision_circuit_open(self, db_session: Session):
        """Test retry is blocked when circuit is open."""
        source = SourceRegistry(
            source_key="unavailable",
            source_name="unavailable",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create failing source
        for i in range(15):
            run = IngestionRun(
                source_name="unavailable",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Connection refused"]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        run = IngestionRun(
            source_name="unavailable",
                started_at=datetime.now(timezone.utc),
            status=FAILED,
            persisted_count=0,
            errors=["Connection refused"]
        )
        
        decision = strategy.should_retry_with_adaptive_params(run, attempt_number=0)

        assert decision.should_retry is False
        assert decision.strategy == "circuit_open"
        assert "Circuit open" in decision.reason

    def test_retry_decision_success(self, db_session: Session):
        """Test retry is allowed for healthy source."""
        source = SourceRegistry(
            source_key="healthy",
            source_name="healthy",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create successful source
        for i in range(10):
            run = IngestionRun(
                source_name="healthy",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        run = IngestionRun(
            source_name="healthy",
                started_at=datetime.now(timezone.utc),
            status=FAILED,
            persisted_count=0,
            errors=["Transient error"]
        )
        
        decision = strategy.should_retry_with_adaptive_params(run, attempt_number=0)

        assert decision.should_retry is True
        assert decision.backoff_seconds > 0
        assert decision.max_retries >= 2
        assert "Adaptive retry" in decision.reason

    def test_retry_decision_max_attempts_exceeded(self, db_session: Session):
        """Test retry is blocked when max attempts exceeded."""
        source = SourceRegistry(
            source_key="exhausted",
            source_name="exhausted",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create source with moderate success
        for i in range(5):
            run = IngestionRun(
                source_name="exhausted",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[]
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        run = IngestionRun(
            source_name="exhausted",
                started_at=datetime.now(timezone.utc),
            status=FAILED,
            persisted_count=0,
            errors=["Error"]
        )
        
        # Try at attempt 5 (exceeds max of 3)
        decision = strategy.should_retry_with_adaptive_params(run, attempt_number=5)

        assert decision.should_retry is False
        assert decision.strategy == "max_retries_exceeded"


@pytest.mark.usefixtures("db_session")
class TestRecoveryTimePrediction:
    """Tests for recovery time estimation."""

    def test_recovery_time_no_data(self, db_session: Session):
        """Test recovery time estimate when no data available."""
        strategy = AdaptiveRetryStrategy(db_session)
        recovery_time = strategy.predict_recovery_time("unknown_source")

        assert recovery_time == timedelta(minutes=30)  # Conservative default

    def test_recovery_time_quick_recovery(self, db_session: Session):
        """Test recovery time when source recovers quickly."""
        source = SourceRegistry(
            source_key="quick_source",
            source_name="quick_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Failures followed by quick recovery (5 minutes)
        base_time = datetime.now(timezone.utc)
        for cycle in range(3):
            run = IngestionRun(
                source_name="quick_source",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Brief outage"],
                created_at=base_time + timedelta(hours=cycle*1)
            )
            db_session.add(run)
            
            run = IngestionRun(
                source_name="quick_source",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[],
                created_at=base_time + timedelta(hours=cycle*1, minutes=5)
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        recovery_time = strategy.predict_recovery_time("quick_source")

        # Should predict ~7-10 minutes (1.5x the 5 minute average)
        assert recovery_time.total_seconds() > 300  # More than 5 minutes
        assert recovery_time.total_seconds() < 900  # Less than 15 minutes


@pytest.mark.usefixtures("db_session")
class TestRetryBudget:
    """Tests for retry budget management."""

    def test_budget_no_source(self, db_session: Session):
        """Test budget for nonexistent source."""
        strategy = AdaptiveRetryStrategy(db_session)
        budget = strategy.get_retry_budget("unknown_source")

        assert budget["total_allowed"] == 100
        assert budget["used"] == 0
        assert budget["remaining"] == 100
        assert budget["status"] == "no_source"

    def test_budget_within_limit(self, db_session: Session):
        """Test budget when within acceptable retries."""
        source = SourceRegistry(
            source_key="active_source",
            source_name="active_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create 5 retries in last 24 hours
        base_time = datetime.now(timezone.utc)
        for i in range(5):
            run = IngestionRun(
                source_name="active_source",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Error"],
                retry_count=1,
                created_at=base_time - timedelta(hours=i)
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        budget = strategy.get_retry_budget("active_source", time_window_hours=24)

        assert budget["used"] == 5
        assert budget["remaining"] > 0
        assert budget["status"] == "ok"

    def test_budget_exceeded(self, db_session: Session):
        """Test budget when retry limit exceeded."""
        source = SourceRegistry(
            source_key="overused_source",
            source_name="overused_source",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create 250 retries in last 24 hours (far above limit)
        base_time = datetime.now(timezone.utc)
        for i in range(250):
            run = IngestionRun(
                source_name="overused_source",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Error"],
                retry_count=1,
                created_at=base_time - timedelta(minutes=i)
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)
        budget = strategy.get_retry_budget("overused_source", time_window_hours=24)

        assert budget["used"] > budget["total_allowed"]
        assert budget["remaining"] == 0
        assert budget["status"] == "exceeded"


@pytest.mark.usefixtures("db_session")
class TestPhase5Integration:
    """Integration tests for Phase 5 adaptive retry system."""

    def test_full_adaptive_workflow(self, db_session: Session):
        """Test complete adaptive retry workflow."""
        source = SourceRegistry(
            source_key="integration_test",
            source_name="integration_test",
            canonical_url="https://example.com",
            source_type="website"
        )
        db_session.add(source)
        db_session.flush()

        # Create history: improving performance
        base_time = datetime.now(timezone.utc)
        
        # Early: failures
        for i in range(3):
            run = IngestionRun(
                source_name="integration_test",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Service degradation"],
                created_at=base_time - timedelta(hours=10 + i)
            )
            db_session.add(run)

        # Middle: recovery
        for i in range(5):
            run = IngestionRun(
                source_name="integration_test",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[],
                created_at=base_time - timedelta(hours=6 + i)
            )
            db_session.add(run)

        # Recent: stable
        for i in range(5):
            run = IngestionRun(
                source_name="integration_test",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[],
                created_at=base_time - timedelta(hours=i)
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)

        # Get metrics
        metrics = strategy.calculate_source_metrics("integration_test")
        assert metrics.trend == "improving" or metrics.trend == "stable"

        # Get adaptive params
        params = strategy.get_adaptive_params("integration_test")
        assert params.circuit_state == CircuitState.CLOSED
        assert params.max_retries >= 2

        # Get retry decision
        run = IngestionRun(
            source_name="integration_test",
                started_at=datetime.now(timezone.utc),
            status=FAILED,
            persisted_count=0,
            errors=["Transient error"]
        )
        decision = strategy.should_retry_with_adaptive_params(run, attempt_number=0)
        assert decision.should_retry is True

    def test_adaptive_vs_static_backoff(self, db_session: Session):
        """Test that adaptive backoff differs from static for different sources."""
        # Create two sources with different recovery patterns
        for source_name in ["fast_recover", "slow_recover"]:
            source = SourceRegistry(
                source_key=source_name,
                source_name=source_name,
                canonical_url="https://example.com",
                source_type="website"
            )
            db_session.add(source)
        db_session.flush()

        # Fast recovery: failures with 5-minute recovery
        base_time = datetime.now(timezone.utc)
        for i in range(5):
            run = IngestionRun(
                source_name="fast_recover",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Brief failure"],
                created_at=base_time + timedelta(hours=i*2)
            )
            db_session.add(run)
            
            run = IngestionRun(
                source_name="fast_recover",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[],
                created_at=base_time + timedelta(hours=i*2, minutes=5)
            )
            db_session.add(run)

        # Slow recovery: failures with 60-minute recovery
        for i in range(5):
            run = IngestionRun(
                source_name="slow_recover",
                started_at=datetime.now(timezone.utc),
                status=FAILED,
                persisted_count=0,
                errors=["Extended failure"],
                created_at=base_time + timedelta(hours=i*3)
            )
            db_session.add(run)
            
            run = IngestionRun(
                source_name="slow_recover",
                started_at=datetime.now(timezone.utc),
                status=COMPLETED,
                persisted_count=100,
                errors=[],
                created_at=base_time + timedelta(hours=i*3, minutes=60)
            )
            db_session.add(run)
        db_session.commit()

        strategy = AdaptiveRetryStrategy(db_session)

        # Get adaptive params for each
        fast_params = strategy.get_adaptive_params("fast_recover")
        slow_params = strategy.get_adaptive_params("slow_recover")

        # Slow recovery should have longer base backoff
        assert slow_params.base_backoff_seconds > fast_params.base_backoff_seconds
