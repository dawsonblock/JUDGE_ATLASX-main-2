"""
Adaptive Retry Strategy - Phase 5

Learn optimal retry parameters from historical ingestion data and adjust dynamically
based on source success rates, error patterns, and health trends.

This module implements:
- Adaptive backoff calculation based on source-specific success rates
- Dynamic max_retries adjustment per source
- Predictive health degradation detection
- Circuit breaker decision logic
- Retry budget management (time + count constraints)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import NamedTuple
from sqlalchemy.orm import Session
from app.models.entities import SourceRegistry, IngestionRun
from app.ingestion.statuses import COMPLETED, FAILED, QUARANTINED


class CircuitState(Enum):
    """Circuit breaker states for source availability."""
    CLOSED = "closed"          # Normal operation, retries allowed
    OPEN = "open"              # Source unavailable, retries blocked
    HALF_OPEN = "half_open"    # Testing recovery, limited retries


@dataclass
class AdaptiveRetryParams:
    """Per-source adaptive retry parameters."""
    source_key: str
    base_backoff_seconds: int      # Initial backoff duration
    max_backoff_seconds: int       # Maximum backoff cap
    max_retries: int               # Maximum retry attempts
    jitter_factor: float           # Jitter percentage (0.0-1.0)
    success_rate: float            # Recent success rate (0.0-1.0)
    failure_streak: int            # Consecutive failures
    estimated_recovery_time: int   # Minutes until source likely recovers
    circuit_state: CircuitState    # Current circuit breaker state
    confidence: float              # Confidence in parameters (0.0-1.0)


@dataclass
class RetryDecision:
    """Decision to retry or not with explanation."""
    should_retry: bool
    strategy: str                  # "exponential_backoff", "static", "circuit_open", etc.
    backoff_seconds: int
    max_retries: int
    reason: str
    estimated_success_probability: float  # 0.0-1.0


class SourceSuccessMetrics(NamedTuple):
    """Calculated success metrics for a source."""
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    recent_success_rate: float  # Last 10 runs
    failure_streak: int
    avg_time_to_recovery_minutes: int
    trend: str  # "improving", "stable", "degrading"


class AdaptiveRetryStrategy:
    """
    Adaptive retry strategy that learns from historical data.
    
    Adjusts retry parameters based on:
    - Source success/failure patterns
    - Health score trends
    - Recovery time observations
    - Consecutive failure streaks
    - Time of day patterns (optional future enhancement)
    """

    def __init__(self, db: Session):
        self.db = db
        self.min_samples_for_adaptation = 5  # Need at least N runs for reliable statistics
        self.health_degradation_threshold = 0.6
        self.circuit_failure_threshold = 0.2  # Open circuit if success rate < 20%
        self.circuit_recovery_threshold = 0.7  # Close circuit if success rate > 70%
        self.half_open_retry_limit = 2  # Allow 2 retries while half-open

    def calculate_source_metrics(self, source_key: str) -> SourceSuccessMetrics:
        """
        Calculate success metrics for a source based on recent ingestion history.
        
        Returns:
            SourceSuccessMetrics with success rates, failure streaks, recovery times
        """
        # Get all runs for this source
        all_runs = self.db.query(IngestionRun)\
            .filter_by(source_name=source_key)\
            .order_by(IngestionRun.created_at.desc())\
            .limit(50)\
            .all()

        if not all_runs:
            # No data yet, use conservative defaults
            return SourceSuccessMetrics(
                total_runs=0,
                successful_runs=0,
                failed_runs=0,
                success_rate=0.5,
                recent_success_rate=0.5,
                failure_streak=0,
                avg_time_to_recovery_minutes=0,
                trend="unknown"
            )

        total = len(all_runs)
        successful = sum(1 for r in all_runs if r.status == COMPLETED)
        failed = sum(1 for r in all_runs if r.status in [FAILED, QUARANTINED])
        success_rate = successful / total if total > 0 else 0.5

        # Recent success rate (last 10 runs)
        recent_runs = all_runs[:10]
        recent_successful = sum(1 for r in recent_runs if r.status == COMPLETED)
        recent_success_rate = recent_successful / len(recent_runs) if recent_runs else 0.5

        # Calculate failure streak (consecutive failures from most recent)
        failure_streak = 0
        for run in all_runs:
            if run.status in [FAILED, QUARANTINED]:
                failure_streak += 1
            else:
                break

        # Estimate time to recovery (avg time between failure and next success)
        recovery_times = []
        consecutive_failures = []
        for i, run in enumerate(reversed(all_runs)):
            if run.status in [FAILED, QUARANTINED]:
                consecutive_failures.append(run)
            else:
                if consecutive_failures:
                    # Found a success after failures
                    failure_start = consecutive_failures[-1].created_at
                    success_time = run.created_at
                    recovery_time = (success_time - failure_start).total_seconds() / 60
                    recovery_times.append(recovery_time)
                    consecutive_failures = []

        avg_recovery_time = int(sum(recovery_times) / len(recovery_times)) if recovery_times else 30

        # Determine trend
        if recent_success_rate > success_rate:
            trend = "improving"
        elif recent_success_rate < success_rate * 0.8:
            trend = "degrading"
        else:
            trend = "stable"

        return SourceSuccessMetrics(
            total_runs=total,
            successful_runs=successful,
            failed_runs=failed,
            success_rate=success_rate,
            recent_success_rate=recent_success_rate,
            failure_streak=failure_streak,
            avg_time_to_recovery_minutes=avg_recovery_time,
            trend=trend
        )

    def determine_circuit_state(self, source_key: str, metrics: SourceSuccessMetrics) -> CircuitState:
        """
        Determine if circuit breaker should be OPEN, HALF_OPEN, or CLOSED.
        
        Logic:
        - OPEN: Success rate < 20% (source consistently failing)
        - HALF_OPEN: Between 20-70% (testing recovery with limited retries)
        - CLOSED: Success rate > 70% (normal operation)
        """
        # Get current state from source registry
        source = self.db.query(SourceRegistry).filter_by(source_key=source_key).first()
        
        if not source:
            return CircuitState.CLOSED
        
        # Store previous state for transition detection
        current_state = CircuitState.CLOSED  # Default
        if hasattr(source, 'circuit_state'):
            try:
                current_state = CircuitState(source.circuit_state)
            except (ValueError, AttributeError):
                current_state = CircuitState.CLOSED

        # Determine new state based on success rate
        if metrics.success_rate < self.circuit_failure_threshold:
            new_state = CircuitState.OPEN
        elif metrics.success_rate < self.circuit_recovery_threshold:
            new_state = CircuitState.HALF_OPEN
        else:
            new_state = CircuitState.CLOSED

        return new_state

    def adjust_max_retries(self, metrics: SourceSuccessMetrics) -> int:
        """
        Adjust max_retries based on success rate and recent performance.
        
        Formula:
        - High success rate (>80%): 3 retries (standard)
        - Good success rate (60-80%): 2 retries (limited)
        - Poor success rate (40-60%): 2 retries (be conservative)
        - Very poor (<40%): 1 retry (minimal attempts)
        - Critical (<20%): 0 retries (circuit open)
        """
        if metrics.total_runs < self.min_samples_for_adaptation:
            return 3  # Default until we have enough data

        if metrics.success_rate >= 0.8:
            return 3
        elif metrics.success_rate >= 0.6:
            return 2
        elif metrics.success_rate >= 0.4:
            return 2
        elif metrics.success_rate >= 0.2:
            return 1
        else:
            return 0  # Circuit open

    def adjust_backoff_base(self, metrics: SourceSuccessMetrics, base_seconds: int = 60) -> int:
        """
        Adjust base backoff duration based on estimated recovery time.
        
        If source tends to recover quickly, use shorter backoff.
        If source recovery is slow, use longer backoff.
        
        Returns adjusted base in seconds.
        """
        if metrics.avg_time_to_recovery_minutes == 0:
            return base_seconds

        # Use half of estimated recovery time as base backoff
        estimated_base = int(metrics.avg_time_to_recovery_minutes * 30)  # 30 seconds per minute

        # But cap within reasonable bounds
        min_base = 30      # Minimum 30 seconds
        max_base = 600     # Maximum 10 minutes

        return max(min_base, min(max_base, estimated_base))

    def calculate_success_probability(
        self,
        metrics: SourceSuccessMetrics,
        attempt_number: int,
        circuit_state: CircuitState
    ) -> float:
        """
        Estimate probability of success for next retry based on patterns.
        
        Factors:
        - Overall success rate
        - Recent trend
        - Failure streak length
        - Circuit breaker state
        - Attempt number (early attempts more likely)
        """
        if circuit_state == CircuitState.OPEN:
            return 0.05  # 5% chance if circuit is open

        base_probability = metrics.recent_success_rate

        # Adjust for trend
        if metrics.trend == "improving":
            base_probability *= 1.1
        elif metrics.trend == "degrading":
            base_probability *= 0.9

        # Adjust for failure streak (more consecutive failures = lower probability)
        if metrics.failure_streak > 0:
            base_probability *= max(0.1, 1.0 - (metrics.failure_streak * 0.2))

        # Adjust for attempt number (later attempts less likely)
        attempt_penalty = max(0.5, 1.0 - (attempt_number * 0.1))
        base_probability *= attempt_penalty

        # Circuit half-open: limited retry success
        if circuit_state == CircuitState.HALF_OPEN:
            base_probability *= 0.8

        return max(0.0, min(1.0, base_probability))

    def get_adaptive_params(self, source_key: str) -> AdaptiveRetryParams:
        """
        Get adaptive retry parameters for a source.
        
        Returns:
            AdaptiveRetryParams with dynamically adjusted retry settings
        """
        metrics = self.calculate_source_metrics(source_key)
        circuit_state = self.determine_circuit_state(source_key, metrics)
        max_retries = self.adjust_max_retries(metrics)
        base_backoff = self.adjust_backoff_base(metrics)

        # Calculate confidence in our parameters
        min_samples = self.min_samples_for_adaptation
        max_samples = 50
        confidence = min(1.0, metrics.total_runs / max_samples)

        return AdaptiveRetryParams(
            source_key=source_key,
            base_backoff_seconds=base_backoff,
            max_backoff_seconds=3600,
            max_retries=max_retries,
            jitter_factor=0.1,
            success_rate=metrics.success_rate,
            failure_streak=metrics.failure_streak,
            estimated_recovery_time=metrics.avg_time_to_recovery_minutes,
            circuit_state=circuit_state,
            confidence=confidence
        )

    def should_retry_with_adaptive_params(
        self,
        run: IngestionRun,
        attempt_number: int = 0
    ) -> RetryDecision:
        """
        Decide whether to retry based on adaptive parameters.
        
        Args:
            run: The failed IngestionRun to evaluate
            attempt_number: Current attempt number (0-indexed)
            
        Returns:
            RetryDecision with retry recommendation and reasoning
        """
        params = self.get_adaptive_params(run.source_name)
        metrics = self.calculate_source_metrics(run.source_name)
        success_prob = self.calculate_success_probability(
            metrics, attempt_number, params.circuit_state
        )

        # Decision logic
        if params.circuit_state == CircuitState.OPEN:
            return RetryDecision(
                should_retry=False,
                strategy="circuit_open",
                backoff_seconds=0,
                max_retries=0,
                reason=f"Circuit open: Success rate {params.success_rate:.1%} below threshold. Manual recovery needed.",
                estimated_success_probability=0.05
            )

        if attempt_number >= params.max_retries:
            return RetryDecision(
                should_retry=False,
                strategy="max_retries_exceeded",
                backoff_seconds=0,
                max_retries=params.max_retries,
                reason=f"Max retries ({params.max_retries}) exceeded after {attempt_number} attempts",
                estimated_success_probability=success_prob
            )

        # Calculate backoff with adaptation
        from app.ingestion.recovery_strategies import calculate_backoff_seconds
        backoff = calculate_backoff_seconds(
            attempt=attempt_number,
            base_seconds=params.base_backoff_seconds,
            max_seconds=params.max_backoff_seconds,
            jitter_factor=params.jitter_factor
        )

        # Adjust backoff if success probability is low
        if success_prob < 0.3:
            backoff = int(backoff * 2)  # Double wait time for risky retries
            strategy = "conservative_adaptive"
        elif success_prob > 0.7:
            strategy = "optimistic_adaptive"
        else:
            strategy = "standard_adaptive"

        reason = (
            f"Adaptive retry: Success rate {params.success_rate:.1%}, "
            f"Trend: {metrics.trend}, "
            f"Failure streak: {metrics.failure_streak}, "
            f"Est. success prob: {success_prob:.1%}"
        )

        return RetryDecision(
            should_retry=True,
            strategy=strategy,
            backoff_seconds=backoff,
            max_retries=params.max_retries,
            reason=reason,
            estimated_success_probability=success_prob
        )

    def predict_recovery_time(self, source_key: str) -> timedelta:
        """
        Predict when a source is likely to recover based on historical patterns.
        
        Returns:
            Estimated time until source recovers (for circuit breaker half-open)
        """
        metrics = self.calculate_source_metrics(source_key)
        
        # If no recovery data, use conservative estimate
        if metrics.avg_time_to_recovery_minutes == 0:
            recovery_minutes = 30
        else:
            # Use 1.5x the average recovery time
            recovery_minutes = int(metrics.avg_time_to_recovery_minutes * 1.5)

        return timedelta(minutes=recovery_minutes)

    def get_retry_budget(self, source_key: str, time_window_hours: int = 24) -> dict:
        """
        Get remaining retry budget for a source (time + count constraints).
        
        Returns:
            Dict with budget stats: total_allowed, used, remaining, reset_in
        """
        # Get source
        source = self.db.query(SourceRegistry).filter_by(source_key=source_key).first()
        if not source:
            return {
                "total_allowed": 100,
                "used": 0,
                "remaining": 100,
                "reset_in_hours": time_window_hours,
                "status": "no_source"
            }

        # Calculate retries in time window
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
        recent_retries = self.db.query(IngestionRun)\
            .filter(
                IngestionRun.source_name == source_key,
                IngestionRun.created_at >= cutoff_time,
                IngestionRun.retry_count > 0
            ).count()

        # Budget: allow 10 retries per hour, max 100 in 24h window
        max_budget = 10 * time_window_hours
        remaining = max(0, max_budget - recent_retries)

        return {
            "total_allowed": max_budget,
            "used": recent_retries,
            "remaining": remaining,
            "reset_in_hours": time_window_hours,
            "status": "ok" if remaining > 0 else "exceeded"
        }
