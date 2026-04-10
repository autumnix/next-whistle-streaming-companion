"""Integration tests for overlay API endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from nwsc.app import create_app
from nwsc.config import load_config
from nwsc.domain.overlay import OverlayService
from nwsc.integrations.obs.client import GroupItem, OBSClient
from tests.conftest import FIXTURES_DIR


@pytest.fixture
def mock_obs_for_overlay() -> MagicMock:
    obs = MagicMock(spec=OBSClient)
    obs.get_group_items.return_value = [
        GroupItem(name="Penalties", item_id=1, enabled=False),
        GroupItem(name="Jammer Stat", item_id=2, enabled=False),
        GroupItem(name="Rosters", item_id=3, enabled=False),
    ]
    obs.get_item_id.side_effect = lambda group, name: {
        "Penalties": 1, "Jammer Stat": 2, "Rosters": 3
    }[name]
    return obs


@pytest.fixture
def client(tmp_path, mock_obs_for_overlay, mock_ptz, mock_scoreboard) -> TestClient:
    config = load_config(FIXTURES_DIR / "config.test.yaml")
    config.database.path = str(tmp_path / "test.sqlite3")
    config.obs.overlay_groups = ["Stat Overlays"]
    app = create_app(config)
    app.state.obs = mock_obs_for_overlay
    app.state.overlay_svc = OverlayService(mock_obs_for_overlay, allowed_groups=["Stat Overlays"])
    app.state.ptz = mock_ptz
    app.state.scoreboard = mock_scoreboard
    from nwsc.domain.jam_cycle import JamCycleOrchestrator
    app.state.jam_cycle = JamCycleOrchestrator(
        mock_obs_for_overlay, mock_ptz, app.state.bout_svc, app.state.clip_svc, config
    )
    with TestClient(app) as c:
        yield c


class TestListSources:
    def test_list_sources(self, client: TestClient):
        resp = client.get("/overlay/Stat Overlays/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["group"] == "Stat Overlays"
        assert len(data["sources"]) == 3
        assert data["sources"][0]["name"] == "Penalties"

    def test_unknown_group_404(self, client: TestClient):
        resp = client.get("/overlay/Unknown Group/sources")
        assert resp.status_code == 404


class TestShowSource:
    def test_show_source(self, client: TestClient, mock_obs_for_overlay):
        resp = client.post("/overlay/Stat Overlays/show?source=Penalties")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "Penalties"
        assert data["enabled"] is True
        assert data["timeout_s"] is None

    def test_show_with_timeout(self, client: TestClient):
        resp = client.post("/overlay/Stat Overlays/show?source=Penalties&timeout=15")
        assert resp.status_code == 200
        data = resp.json()
        assert data["timeout_s"] == 15.0

    def test_show_via_get(self, client: TestClient):
        """Stream Deck compatibility."""
        resp = client.get("/overlay/Stat Overlays/show?source=Rosters")
        assert resp.status_code == 200

    def test_show_unknown_source(self, client: TestClient):
        resp = client.post("/overlay/Stat Overlays/show?source=Nonexistent")
        assert resp.status_code == 404


class TestToggle:
    def test_toggle_on(self, client: TestClient):
        resp = client.post("/overlay/Stat Overlays/toggle?source=Penalties&enabled=true")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_toggle_off(self, client: TestClient):
        resp = client.post("/overlay/Stat Overlays/toggle?source=Penalties&enabled=false")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


class TestHideAll:
    def test_hide_all(self, client: TestClient):
        resp = client.post("/overlay/Stat Overlays/hide-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["group"] == "Stat Overlays"
        assert all(s["enabled"] is False for s in data["sources"])
