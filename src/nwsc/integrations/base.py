"""Base protocol for all external integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class HealthStatus:
    healthy: bool
    latency_ms: float | None = None
    detail: str = ""


@runtime_checkable
class Integration(Protocol):
    """Common interface for external service integrations."""

    @property
    def name(self) -> str: ...

    async def health_check(self) -> HealthStatus: ...
