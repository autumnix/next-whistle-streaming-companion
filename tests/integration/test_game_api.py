"""Integration tests for game API endpoints."""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from nwsc.app import create_app
from nwsc.config import load_config
from tests.conftest import FIXTURES_DIR


@pytest.fixture
def client(tmp_path, mock_obs, mock_ptz, mock_scoreboard) -> TestClient:
    config = load_config(FIXTURES_DIR / "config.test.yaml")
    config.database.path = str(tmp_path / "test.sqlite3")
    app = create_app(config)
    app.state.obs = mock_obs
    app.state.ptz = mock_ptz
    app.state.scoreboard = mock_scoreboard
    from nwsc.domain.jam_cycle import JamCycleOrchestrator
    app.state.jam_cycle = JamCycleOrchestrator(
        mock_obs, mock_ptz, app.state.bout_svc, app.state.clip_svc, config
    )
    with TestClient(app) as c:
        yield c


class TestGameStart:
    def test_start_game(self, client: TestClient):
        resp = client.post("/game/start")
        assert resp.status_code == 200
        data = resp.json()
        assert "game_id" in data
        assert data["game_id"].startswith("game-")

    def test_start_game_get(self, client: TestClient):
        """Stream Deck compatibility: GET also works."""
        resp = client.get("/game/start")
        assert resp.status_code == 200

    def test_multiple_starts(self, client: TestClient):
        resp1 = client.post("/game/start")
        resp2 = client.post("/game/start")
        assert resp1.json()["game_id"] != resp2.json()["game_id"]


class TestGameCurrent:
    def test_no_active_game(self, client: TestClient):
        resp = client.get("/game/current")
        assert resp.status_code == 200
        assert resp.json()["game_id"] is None

    def test_with_active_game(self, client: TestClient):
        start_resp = client.post("/game/start")
        game_id = start_resp.json()["game_id"]

        resp = client.get("/game/current")
        assert resp.status_code == 200
        assert resp.json()["game_id"] == game_id
