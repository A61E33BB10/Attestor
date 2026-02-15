"""Health check protocol for Attestor infrastructure dependencies.

Kubernetes probes:
  livenessProbe  -> GET /health/live   -> liveness_check()
  readinessProbe -> GET /health/ready  -> readiness_check()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, final

from attestor.core.errors import PersistenceError
from attestor.core.result import Err, Ok


@final
@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Status of a single health check."""

    healthy: bool
    component: str
    message: str
    checked_at: datetime
    latency_ms: float  # infra latency metric, not financial arithmetic (noqa-float)


@final
@dataclass(frozen=True, slots=True)
class SystemHealth:
    """Aggregate health status of all dependencies."""

    overall_healthy: bool
    checks: tuple[HealthStatus, ...]
    checked_at: datetime


class HealthCheckable(Protocol):
    """Protocol for components that support health checks."""

    def health_check(self) -> Ok[HealthStatus] | Err[PersistenceError]: ...


def liveness_check() -> HealthStatus:
    """Return healthy status — process is alive."""
    return HealthStatus(
        healthy=True, component="process", message="alive",
        checked_at=datetime.now(tz=UTC), latency_ms=0.0,
    )


def readiness_check(
    dependencies: tuple[HealthCheckable, ...],
) -> SystemHealth:
    """Check all dependencies and return aggregate health."""
    checks: list[HealthStatus] = []
    all_healthy = True
    for dep in dependencies:
        result = dep.health_check()
        match result:
            case Ok(status):
                checks.append(status)
                if not status.healthy:
                    all_healthy = False
            case Err(error):
                checks.append(HealthStatus(
                    healthy=False, component="unknown",
                    message=f"Health check failed: {error.message}",
                    checked_at=datetime.now(tz=UTC), latency_ms=0.0,
                ))
                all_healthy = False
    return SystemHealth(
        overall_healthy=all_healthy,
        checks=tuple(checks),
        checked_at=datetime.now(tz=UTC),
    )
