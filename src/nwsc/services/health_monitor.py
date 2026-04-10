"""Background health monitor that periodically checks all integrations."""

from __future__ import annotations

import asyncio

import structlog

from nwsc.integrations.base import HealthStatus, Integration

log = structlog.get_logger()


class HealthMonitor:
    """Periodically polls integration health and tracks status changes."""

    def __init__(
        self,
        integrations: list[Integration],
        poll_interval_s: float = 30.0,
    ) -> None:
        self._integrations = integrations
        self._poll_interval = poll_interval_s
        self._status: dict[str, HealthStatus] = {}
        self._task: asyncio.Task[None] | None = None

    @property
    def status(self) -> dict[str, HealthStatus]:
        return dict(self._status)

    async def check_all(self) -> dict[str, HealthStatus]:
        """Run health checks on all integrations."""
        results: dict[str, HealthStatus] = {}
        for integration in self._integrations:
            try:
                results[integration.name] = await integration.health_check()
            except Exception as e:
                results[integration.name] = HealthStatus(healthy=False, detail=str(e))

        # Log status changes
        for name, new_status in results.items():
            old = self._status.get(name)
            if old is None or old.healthy != new_status.healthy:
                if new_status.healthy:
                    log.info("health.recovered", integration=name)
                else:
                    log.warning("health.degraded", integration=name, detail=new_status.detail)

        self._status = results
        return results

    async def run(self) -> None:
        """Long-running background task: poll health on interval."""
        while True:
            try:
                await self.check_all()
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.error("health_monitor.error", error=str(e))
            await asyncio.sleep(self._poll_interval)

    def start(self) -> asyncio.Task[None]:
        self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
