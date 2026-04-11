"""Integration tests for workflow endpoints."""

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
    # Replace integration clients
    app.state.obs = mock_obs
    app.state.ptz = mock_ptz
    app.state.scoreboard = mock_scoreboard
    # Rebuild bout_svc and orchestrator with mock scoreboard
    from nwsc.domain.bout import BoutService
    app.state.bout_svc = BoutService(app.state.repo, mock_scoreboard)
    app.state.jam_cycle = JamCycleOrchestrator(
        mock_obs, mock_ptz, app.state.bout_svc, app.state.clip_svc, config
    )
    with TestClient(app) as c:
        yield c


class TestJamReset:
    def test_jam_reset_works_without_game(
        self, client: TestClient, mock_obs: MagicMock, mock_scoreboard: MagicMock
    ):
        """OBS+PTZ should work even with no active game on scoreboard."""
        mock_scoreboard._game_id = None
        resp = client.post("/workflow/jam-reset")
        assert resp.status_code == 200
        mock_obs.set_scene.assert_called()

    def test_jam_reset_with_game(self, client: TestClient, mock_obs: MagicMock):
        resp = client.post("/workflow/jam-reset")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_period" in data
        assert "current_jam" in data
        mock_obs.set_scene.assert_called()

    def test_jam_reset_get_compat(self, client: TestClient):
        """Stream Deck compatibility."""
        resp = client.get("/workflow/jam-reset")
        assert resp.status_code == 200


class TestJamResetAndPlay:
    def test_works_without_game(
        self, client: TestClient, mock_obs: MagicMock, mock_scoreboard: MagicMock
    ):
        """Should degrade to safe scene when scoreboard has no game."""
        mock_scoreboard._game_id = None
        resp = client.post("/workflow/jam-reset-and-play")
        assert resp.status_code == 200
        data = resp.json()
        assert data["play_path"] is None
        mock_obs.set_scene.assert_any_call("BUMPER")

    def test_no_replay(self, client: TestClient, mock_obs: MagicMock):
        resp = client.post("/workflow/jam-reset-and-play")
        assert resp.status_code == 200
        data = resp.json()
        assert data["play_path"] is None
        mock_obs.set_scene.assert_any_call("BUMPER")


class TestBackwardCompatRoutes:
    def test_obs_jam_reset_alias(self, client: TestClient):
        resp = client.post("/obs/jam-reset")
        assert resp.status_code == 200

    def test_obs_jam_reset_and_play_alias(self, client: TestClient):
        resp = client.post("/obs/jam-reset-and-play")
        assert resp.status_code == 200

    def test_obs_save_and_arm_alias_requires_game(
        self, client: TestClient, mock_scoreboard: MagicMock
    ):
        mock_scoreboard._game_id = None
        resp = client.post("/obs/save-and-arm")
        assert resp.status_code == 409
