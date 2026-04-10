"""PTZ camera control via HTTP CGI API using async httpx."""

from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from nwsc.config import PTZConfig
from nwsc.integrations.base import HealthStatus

log = structlog.get_logger()


class PTZClient:
    """Async PTZ camera controller."""

    def __init__(self, config: PTZConfig, http_client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._http = http_client or httpx.AsyncClient(timeout=config.timeout_s)

    @property
    def name(self) -> str:
        return "ptz"

    @property
    def camera_ids(self) -> list[str]:
        return list(self._config.cameras.keys())

    async def health_check(self) -> HealthStatus:
        """Check reachability of all cameras."""
        start = time.monotonic()
        errors: list[str] = []
        for cam_id, cam in self._config.cameras.items():
            try:
                url = self._preset_url(cam.host, 0)
                resp = await self._http.get(url)
                resp.raise_for_status()
            except Exception as e:
                errors.append(f"{cam_id}: {e}")
        latency = (time.monotonic() - start) * 1000
        if errors:
            return HealthStatus(healthy=False, latency_ms=latency, detail="; ".join(errors))
        return HealthStatus(
            healthy=True,
            latency_ms=latency,
            detail=f"cameras={list(self._config.cameras.keys())}",
        )

    def _preset_url(self, host: str, preset: int) -> str:
        return self._config.url_template.format(host=host, preset=preset)

    async def call_preset(self, camera_id: str, preset: int) -> None:
        """Call a preset on a single camera."""
        cam = self._config.cameras.get(camera_id)
        if cam is None:
            raise ValueError(f"Unknown camera: {camera_id}")

        url = self._preset_url(cam.host, preset)
        resp = await self._http.get(url)
        resp.raise_for_status()
        log.info("ptz.preset_called", camera=camera_id, preset=preset)

    async def call_preset_all(self, preset: int) -> None:
        """Call a preset on all cameras in parallel."""
        await asyncio.gather(
            *(self.call_preset(cam_id, preset) for cam_id in self._config.cameras)
        )

    async def close(self) -> None:
        await self._http.aclose()
