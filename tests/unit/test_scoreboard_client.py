"""Tests for CRG scoreboard WebSocket client."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from nwsc.config import ScoreboardConfig
from nwsc.integrations.scoreboard.client import ScoreboardClient, ScoreState


@pytest.fixture
def sb_config() -> ScoreboardConfig:
    return ScoreboardConfig(
        url="ws://localhost:8000/WS/",
        prime_timeout_s=1.0,
    )


class TestMessageParsing:
    """Test all three CRG message formats."""

    async def test_state_dict_format(self, sb_config: ScoreboardConfig):
        """Format 1: {"state": {"key": "value"}}"""
        sb = ScoreboardClient(sb_config)
        sb._ws = AsyncMock()
        sb._ws.recv = AsyncMock(
            return_value=json.dumps(
                {
                    "state": {
                        "ScoreBoard.CurrentGame.Clock(Jam).Number": "5",
                        "ScoreBoard.CurrentGame.Clock(Period).Number": "2",
                    }
                }
            )
        )

        await sb._recv_one()
        assert sb._jam == 5
        assert sb._period == 2

    async def test_typed_state_format(self, sb_config: ScoreboardConfig):
        """Format 2: {"type": "state", "state": {"key": "value"}}"""
        sb = ScoreboardClient(sb_config)
        sb._ws = AsyncMock()
        sb._ws.recv = AsyncMock(
            return_value=json.dumps(
                {
                    "type": "state",
                    "state": {
                        "ScoreBoard.CurrentGame.Clock(Jam).Number": "3",
                        "ScoreBoard.CurrentGame.Clock(Period).Number": "1",
                    },
                }
            )
        )

        await sb._recv_one()
        assert sb._jam == 3
        assert sb._period == 1

    async def test_update_key_value_format(self, sb_config: ScoreboardConfig):
        """Format 3: {"type": "update", "key": "...", "value": "..."}"""
        sb = ScoreboardClient(sb_config)
        sb._ws = AsyncMock()
        sb._ws.recv = AsyncMock(
            return_value=json.dumps(
                {
                    "type": "update",
                    "key": "ScoreBoard.CurrentGame.Clock(Jam).Number",
                    "value": "7",
                }
            )
        )

        await sb._recv_one()
        assert sb._jam == 7

    async def test_snapshot_format(self, sb_config: ScoreboardConfig):
        """Format: {"type": "snapshot", "state": {"key": "value"}}"""
        sb = ScoreboardClient(sb_config)
        sb._ws = AsyncMock()
        sb._ws.recv = AsyncMock(
            return_value=json.dumps(
                {
                    "type": "snapshot",
                    "state": {
                        "ScoreBoard.CurrentGame.Clock(Period).Number": "2",
                    },
                }
            )
        )

        await sb._recv_one()
        assert sb._period == 2

    async def test_set_format(self, sb_config: ScoreboardConfig):
        """Format: {"type": "set", "key": "...", "value": "..."}"""
        sb = ScoreboardClient(sb_config)
        sb._ws = AsyncMock()
        sb._ws.recv = AsyncMock(
            return_value=json.dumps(
                {
                    "type": "set",
                    "key": "ScoreBoard.CurrentGame.Clock(Period).Number",
                    "value": "1",
                }
            )
        )

        await sb._recv_one()
        assert sb._period == 1

    async def test_ignores_unknown_keys(self, sb_config: ScoreboardConfig):
        sb = ScoreboardClient(sb_config)
        sb._ws = AsyncMock()
        sb._ws.recv = AsyncMock(
            return_value=json.dumps(
                {"state": {"ScoreBoard.CurrentGame.Score": "100"}}
            )
        )

        await sb._recv_one()
        assert sb._jam is None
        assert sb._period is None

    async def test_ignores_non_dict_messages(self, sb_config: ScoreboardConfig):
        sb = ScoreboardClient(sb_config)
        sb._ws = AsyncMock()
        sb._ws.recv = AsyncMock(return_value=json.dumps([1, 2, 3]))

        await sb._recv_one()  # Should not raise
        assert sb._jam is None


class TestGetState:
    async def test_get_state_returns_current(self, sb_config: ScoreboardConfig):
        sb = ScoreboardClient(sb_config)
        sb._period = 1
        sb._jam = 5
        sb._ws = AsyncMock()
        sb._ws.recv = AsyncMock(side_effect=asyncio.TimeoutError)

        state = await sb.get_state()
        assert state == ScoreState(period=1, jam=5)


class TestHealthCheck:
    async def test_healthy_when_connected(self, sb_config: ScoreboardConfig):
        sb = ScoreboardClient(sb_config)
        sb._connected = True
        sb._period = 1
        sb._jam = 3
        sb._last_update = asyncio.get_event_loop().time()

        status = await sb.health_check()
        assert status.healthy is True
        assert "period=1" in status.detail

    async def test_unhealthy_when_disconnected(self, sb_config: ScoreboardConfig):
        sb = ScoreboardClient(sb_config)
        status = await sb.health_check()
        assert status.healthy is False


class TestGetStateOrLast:
    async def test_returns_live_state_when_connected(self, sb_config: ScoreboardConfig):
        sb = ScoreboardClient(sb_config)
        sb._period = 2
        sb._jam = 7
        sb._ws = AsyncMock()
        sb._ws.recv = AsyncMock(side_effect=asyncio.TimeoutError)

        state = await sb.get_state_or_last()
        assert state == ScoreState(period=2, jam=7)

    async def test_falls_back_to_cached_state(self, sb_config: ScoreboardConfig):
        sb = ScoreboardClient(sb_config)
        # Simulate previously received state
        sb._period = 1
        sb._jam = 5
        # Force get_state to fail (simulates unreachable scoreboard)
        sb.get_state = AsyncMock(side_effect=RuntimeError("connection refused"))

        state = await sb.get_state_or_last()
        assert state == ScoreState(period=1, jam=5)

    async def test_returns_zero_when_never_connected(self, sb_config: ScoreboardConfig):
        sb = ScoreboardClient(sb_config)
        # No cached state at all — period and jam are None
        # Force get_state to fail
        sb.get_state = AsyncMock(side_effect=RuntimeError("connection refused"))

        state = await sb.get_state_or_last()
        assert state == ScoreState(period=0, jam=0)
