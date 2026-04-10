"""CRG Scoreboard WebSocket client with auto-reconnect."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

import structlog
import websockets
from websockets.exceptions import ConnectionClosed

from nwsc.config import ScoreboardConfig
from nwsc.integrations.base import HealthStatus

log = structlog.get_logger()


@dataclass
class ScoreState:
    period: int
    jam: int


class ScoreboardClient:
    """Async CRG scoreboard WebSocket client.

    Connects to the CRG scoreboard, registers for jam/period updates,
    and maintains the latest game state. Supports auto-reconnection.
    """

    def __init__(self, config: ScoreboardConfig) -> None:
        self._config = config
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._period: int | None = None
        self._jam: int | None = None
        self._connected = False
        self._last_update: float = 0
        self._listener_task: asyncio.Task[None] | None = None

    @property
    def name(self) -> str:
        return "scoreboard"

    async def health_check(self) -> HealthStatus:
        if self._connected and self._period is not None:
            staleness = time.monotonic() - self._last_update
            return HealthStatus(
                healthy=True,
                detail=f"period={self._period} jam={self._jam} staleness={staleness:.1f}s",
            )
        return HealthStatus(healthy=False, detail="not connected or state unknown")

    async def connect(self) -> None:
        """Establish WebSocket connection and register for state updates."""
        self._ws = await websockets.connect(
            self._config.url,
            ping_interval=self._config.ping_interval_s,
            ping_timeout=self._config.ping_timeout_s,
        )
        register_msg = {
            "action": "Register",
            "paths": [
                "ScoreBoard.CurrentGame.Clock(Jam).Number",
                "ScoreBoard.CurrentGame.Clock(Period).Number",
            ],
        }
        await self._ws.send(json.dumps(register_msg))
        await self._prime_state()
        self._connected = True
        log.info("scoreboard.connected", period=self._period, jam=self._jam)

    async def disconnect(self) -> None:
        """Close WebSocket and cancel listener."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        self._connected = False
        log.info("scoreboard.disconnected")

    async def get_state(self) -> ScoreState:
        """Return the current scoreboard state.

        Attempts to drain pending messages first. If not connected, reconnects.
        """
        if self._ws is None:
            await self.connect()

        # Drain any pending messages
        try:
            await self._recv_one(timeout=0.1)
        except (asyncio.TimeoutError, Exception):
            pass

        if self._period is None or self._jam is None:
            await self._prime_state()

        assert self._period is not None and self._jam is not None
        return ScoreState(period=self._period, jam=self._jam)

    async def get_state_or_last(self) -> ScoreState:
        """Return the current scoreboard state, falling back to the last known state.

        Calls get_state() first (which retries connection + priming). If that
        fails entirely, returns the most recent cached period/jam. If no state
        has ever been received, returns (0, 0) as a safe default — which means
        no clips will be found, but OBS/PTZ calls won't be blocked.
        """
        try:
            return await self.get_state()
        except Exception as e:
            if self._period is not None and self._jam is not None:
                log.warning(
                    "scoreboard.using_cached_state",
                    period=self._period,
                    jam=self._jam,
                    error=str(e),
                )
                return ScoreState(period=self._period, jam=self._jam)
            log.warning("scoreboard.no_state_available", error=str(e))
            return ScoreState(period=0, jam=0)

    async def run_listener(self) -> None:
        """Long-running background task: listen for updates with auto-reconnect."""
        while True:
            try:
                if self._ws is None:
                    await self.connect()
                while True:
                    try:
                        await self._recv_one(timeout=60.0)
                    except (asyncio.TimeoutError, TimeoutError):
                        # No message within timeout — perfectly normal between jams
                        pass
            except (ConnectionClosed, ConnectionError, OSError) as e:
                log.warning("scoreboard.connection_lost", error=str(e))
                self._connected = False
                self._ws = None
                await asyncio.sleep(self._config.reconnect_delay_s)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.error("scoreboard.listener_error", error=str(e))
                self._connected = False
                self._ws = None
                await asyncio.sleep(self._config.reconnect_delay_s)

    def start_listener(self) -> asyncio.Task[None]:
        """Start the listener as a background task. Returns the task handle."""
        self._listener_task = asyncio.create_task(self.run_listener())
        return self._listener_task

    # --- Internal ---

    async def _prime_state(self) -> None:
        """Wait until both period and jam are known."""
        deadline = time.time() + self._config.prime_timeout_s
        while time.time() < deadline:
            await self._recv_one(timeout=2.0)
            if self._period is not None and self._jam is not None:
                return
        raise RuntimeError(
            f"Could not prime scoreboard state within {self._config.prime_timeout_s}s"
        )

    async def _recv_one(self, timeout: float = 10.0) -> None:
        """Receive and process one WebSocket message."""
        assert self._ws is not None
        raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
        msg = json.loads(raw)

        state_blob: dict[str, str] | None = None

        if isinstance(msg, dict):
            if "state" in msg and isinstance(msg["state"], dict):
                state_blob = msg["state"]
            elif msg.get("type") in ("state", "snapshot") and isinstance(
                msg.get("state"), dict
            ):
                state_blob = msg["state"]
            elif msg.get("type") in ("update", "set") and "key" in msg and "value" in msg:
                state_blob = {msg["key"]: msg["value"]}

        if not state_blob:
            return

        for k, v in state_blob.items():
            if k.endswith("Clock(Jam).Number"):
                self._jam = int(v)
                self._last_update = time.monotonic()
            elif k.endswith("Clock(Period).Number"):
                self._period = int(v)
                self._last_update = time.monotonic()
