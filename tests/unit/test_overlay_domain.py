"""Tests for overlay source group management."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from nwsc.domain.overlay import OverlayService
from nwsc.integrations.obs.client import GroupItem, OBSClient


@pytest.fixture
def mock_obs() -> MagicMock:
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
def overlay_svc(mock_obs: MagicMock) -> OverlayService:
    return OverlayService(mock_obs, allowed_groups=["Stat Overlays"])


class TestListSources:
    def test_lists_all_sources(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        sources = overlay_svc.list_sources("Stat Overlays")
        assert len(sources) == 3
        assert sources[0].name == "Penalties"
        assert sources[1].name == "Jammer Stat"
        assert sources[2].name == "Rosters"
        mock_obs.get_group_items.assert_called_with("Stat Overlays")

    def test_rejects_unknown_group(self, overlay_svc: OverlayService):
        with pytest.raises(ValueError, match="Unknown overlay group"):
            overlay_svc.list_sources("Nonexistent Group")


class TestToggle:
    def test_toggle_on(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        result = overlay_svc.toggle("Stat Overlays", "Penalties", True)
        assert result.name == "Penalties"
        assert result.enabled is True
        mock_obs.set_item_enabled.assert_called_with("Stat Overlays", 1, True)

    def test_toggle_off(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        result = overlay_svc.toggle("Stat Overlays", "Rosters", False)
        assert result.name == "Rosters"
        assert result.enabled is False
        mock_obs.set_item_enabled.assert_called_with("Stat Overlays", 3, False)


class TestDisplayOnly:
    def test_shows_target_hides_others(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        # All start disabled
        result = overlay_svc.display_only("Stat Overlays", "Penalties")

        assert result.name == "Penalties"
        assert result.enabled is True

        # Should enable Penalties (item_id=1)
        mock_obs.set_item_enabled.assert_any_call("Stat Overlays", 1, True)
        # Should NOT disable already-disabled items (optimization)

    def test_hides_previously_enabled(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        # Simulate Rosters currently enabled
        mock_obs.get_group_items.return_value = [
            GroupItem(name="Penalties", item_id=1, enabled=False),
            GroupItem(name="Jammer Stat", item_id=2, enabled=False),
            GroupItem(name="Rosters", item_id=3, enabled=True),
        ]

        overlay_svc.display_only("Stat Overlays", "Penalties")

        # Should disable Rosters
        mock_obs.set_item_enabled.assert_any_call("Stat Overlays", 3, False)
        # Should enable Penalties
        mock_obs.set_item_enabled.assert_any_call("Stat Overlays", 1, True)

    def test_unknown_source_raises(self, overlay_svc: OverlayService):
        with pytest.raises(ValueError, match="not found in group"):
            overlay_svc.display_only("Stat Overlays", "Nonexistent")

    async def test_with_timeout_schedules_auto_hide(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        result = overlay_svc.display_only("Stat Overlays", "Penalties", timeout_s=10.0)
        assert result.enabled is True

        # Should have an auto-hide task scheduled
        assert "Stat Overlays:Penalties" in overlay_svc._auto_hide_tasks
        task = overlay_svc._auto_hide_tasks["Stat Overlays:Penalties"]
        assert not task.done()

        # Clean up
        task.cancel()

    async def test_repeated_show_cancels_previous_timer(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        overlay_svc.display_only("Stat Overlays", "Penalties", timeout_s=30.0)
        first_task = overlay_svc._auto_hide_tasks["Stat Overlays:Penalties"]

        overlay_svc.display_only("Stat Overlays", "Penalties", timeout_s=15.0)
        second_task = overlay_svc._auto_hide_tasks["Stat Overlays:Penalties"]

        # Yield to let cancellation propagate
        await asyncio.sleep(0)

        assert first_task.cancelled()
        assert first_task is not second_task

        # Clean up
        second_task.cancel()

    def test_no_timeout_means_no_task(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        overlay_svc.display_only("Stat Overlays", "Penalties")
        assert "Stat Overlays:Penalties" not in overlay_svc._auto_hide_tasks


class TestHideAll:
    def test_hides_all_sources(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        mock_obs.get_group_items.return_value = [
            GroupItem(name="Penalties", item_id=1, enabled=True),
            GroupItem(name="Jammer Stat", item_id=2, enabled=False),
            GroupItem(name="Rosters", item_id=3, enabled=True),
        ]

        results = overlay_svc.hide_all("Stat Overlays")

        assert len(results) == 3
        assert all(s.enabled is False for s in results)
        # Should only call set_item_enabled for items that were enabled
        assert mock_obs.set_item_enabled.call_count == 2
        mock_obs.set_item_enabled.assert_any_call("Stat Overlays", 1, False)
        mock_obs.set_item_enabled.assert_any_call("Stat Overlays", 3, False)

    async def test_cancels_pending_auto_hide(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        overlay_svc.display_only("Stat Overlays", "Penalties", timeout_s=30.0)
        assert "Stat Overlays:Penalties" in overlay_svc._auto_hide_tasks

        overlay_svc.hide_all("Stat Overlays")
        assert "Stat Overlays:Penalties" not in overlay_svc._auto_hide_tasks


class TestAutoHide:
    async def test_auto_hide_fires_after_delay(self, overlay_svc: OverlayService, mock_obs: MagicMock):
        overlay_svc.display_only("Stat Overlays", "Penalties", timeout_s=0.1)

        # Wait for the auto-hide to fire
        await asyncio.sleep(0.2)

        # Should have called set_item_enabled to disable
        mock_obs.set_item_enabled.assert_any_call("Stat Overlays", 1, False)
        # Task should be cleaned up
        assert "Stat Overlays:Penalties" not in overlay_svc._auto_hide_tasks


class TestNoGroupValidation:
    def test_no_allowed_groups_means_any_group(self):
        obs = MagicMock(spec=OBSClient)
        obs.get_group_items.return_value = []
        svc = OverlayService(obs, allowed_groups=None)

        # Should not raise for any group name
        svc.list_sources("Any Group Name")
