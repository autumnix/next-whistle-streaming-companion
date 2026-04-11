"""Integration tests for game API endpoints."""

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


class TestGameCurrent:
    def test_no_active_game(self, client: TestClient, mock_scoreboard: MagicMock):
        mock_scoreboard._game_id = None
        resp = client.get("/game/current")
        assert resp.status_code == 200
        assert resp.json()["game_id"] is None

    def test_with_active_game(self, client: TestClient, mock_scoreboard: MagicMock):
        mock_scoreboard._game_id = "sb-game-42"
        resp = client.get("/game/current")
        assert resp.status_code == 200
        assert resp.json()["game_id"] == "sb-game-42"

    def test_game_start_removed(self, client: TestClient):
        resp = client.post("/game/start")
        assert resp.status_code == 404 or resp.status_code == 405
