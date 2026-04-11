"""Integration tests for health and status endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from nwsc.app import create_app
from nwsc.config import load_config
from nwsc.domain.jam_cycle import JamCycleOrchestrator
from tests.conftest import FIXTURES_DIR


@pytest.fixture
def client(tmp_path, mock_obs, mock_ptz, mock_scoreboard) -> TestClient:
    config = load_config(FIXTURES_DIR / "config.test.yaml")
    config.database.path = str(tmp_path / "test.sqlite3")
    app = create_app(config)
    app.state.obs = mock_obs
    app.state.ptz = mock_ptz
    app.state.scoreboard = mock_scoreboard
    # Rebuild bout_svc with mock scoreboard
    from nwsc.domain.bout import BoutService
    app.state.bout_svc = BoutService(app.state.repo, mock_scoreboard)
    app.state.jam_cycle = JamCycleOrchestrator(
        mock_obs, mock_ptz, app.state.bout_svc, app.state.clip_svc, config
    )
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")


class TestStatusEndpoint:
    def test_status_no_game(self, client: TestClient, mock_scoreboard: MagicMock):
        mock_scoreboard._game_id = None
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] is None
        assert data["recent_clips"] == []

    def test_status_with_game(self, client: TestClient, mock_scoreboard: MagicMock):
        mock_scoreboard._game_id = "test-game-1"
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == "test-game-1"
