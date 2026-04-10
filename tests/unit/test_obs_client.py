"""Tests for OBS client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nwsc.config import OBSConfig
from nwsc.integrations.obs.client import OBSClient


@pytest.fixture
def obs_config() -> OBSConfig:
    return OBSConfig(host="127.0.0.1", port=4455, password="test")


@pytest.fixture
def mock_req_client() -> MagicMock:
    client = MagicMock()
    scene_resp = MagicMock()
    scene_resp.current_program_scene_name = "CAM1"
    client.get_current_program_scene.return_value = scene_resp

    studio_resp = MagicMock()
    studio_resp.studio_mode_enabled = False
    client.get_studio_mode_enabled.return_value = studio_resp
    return client


class TestOBSClient:
    def test_set_scene(self, obs_config: OBSConfig, mock_req_client: MagicMock):
        obs = OBSClient(obs_config)
        with patch.object(obs, "_connect", return_value=mock_req_client):
            result = obs.set_scene("CAM2")
            mock_req_client.set_current_program_scene.assert_called_with("CAM2")
            assert result == "CAM1"  # Returns what OBS reports

    def test_set_scene_studio_mode(self, obs_config: OBSConfig, mock_req_client: MagicMock):
        mock_req_client.get_studio_mode_enabled.return_value.studio_mode_enabled = True
        obs = OBSClient(obs_config)
        with patch.object(obs, "_connect", return_value=mock_req_client):
            obs.set_scene("CAM2")
            mock_req_client.set_current_preview_scene.assert_called_with("CAM2")

    def test_save_replay_buffer(self, obs_config: OBSConfig, mock_req_client: MagicMock):
        obs = OBSClient(obs_config)
        with patch.object(obs, "_connect", return_value=mock_req_client):
            obs.save_replay_buffer()
            mock_req_client.save_replay_buffer.assert_called_once()

    def test_load_and_play_media(self, obs_config: OBSConfig, mock_req_client: MagicMock):
        obs = OBSClient(obs_config)
        with patch.object(obs, "_connect", return_value=mock_req_client):
            obs.load_and_play_media("/path/to/replay.mkv")
            mock_req_client.set_input_settings.assert_called_once()
            mock_req_client.trigger_media_input_action.assert_called_once()

    def test_transition_to_scene(self, obs_config: OBSConfig, mock_req_client: MagicMock):
        obs = OBSClient(obs_config)
        with patch.object(obs, "_connect", return_value=mock_req_client):
            obs.transition_to_scene("REPLAY", "Cut", 0)
            mock_req_client.set_current_scene_transition.assert_called_with("Cut")
            mock_req_client.set_current_scene_transition_duration.assert_called_with(0)
            mock_req_client.set_current_program_scene.assert_called_with("REPLAY")

    def test_get_current_scene(self, obs_config: OBSConfig, mock_req_client: MagicMock):
        obs = OBSClient(obs_config)
        with patch.object(obs, "_connect", return_value=mock_req_client):
            result = obs.get_current_scene()
            assert result == "CAM1"

    async def test_health_check_healthy(self, obs_config: OBSConfig, mock_req_client: MagicMock):
        obs = OBSClient(obs_config)
        with patch.object(obs, "_connect", return_value=mock_req_client):
            status = await obs.health_check()
            assert status.healthy is True
            assert "CAM1" in status.detail

    async def test_health_check_unhealthy(self, obs_config: OBSConfig):
        obs = OBSClient(obs_config)
        with patch.object(obs, "_connect", side_effect=ConnectionError("refused")):
            status = await obs.health_check()
            assert status.healthy is False
            assert "refused" in status.detail
