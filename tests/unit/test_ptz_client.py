"""Tests for PTZ camera client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from nwsc.config import PTZCameraConfig, PTZConfig
from nwsc.integrations.ptz.client import PTZClient


@pytest.fixture
def ptz_config() -> PTZConfig:
    return PTZConfig(
        cameras={
            "cam1": PTZCameraConfig(host="192.168.1.10"),
            "cam2": PTZCameraConfig(host="192.168.1.11"),
        },
        url_template="http://{host}/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&{preset}",
        timeout_s=2,
    )


@pytest.fixture
def mock_http() -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.raise_for_status = MagicMock()
    client.get.return_value = response
    return client


class TestPTZClient:
    async def test_call_preset(self, ptz_config: PTZConfig, mock_http: AsyncMock):
        ptz = PTZClient(ptz_config, mock_http)
        await ptz.call_preset("cam1", 3)

        mock_http.get.assert_called_with(
            "http://192.168.1.10/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&3"
        )

    async def test_call_preset_unknown_camera(self, ptz_config: PTZConfig, mock_http: AsyncMock):
        ptz = PTZClient(ptz_config, mock_http)
        with pytest.raises(ValueError, match="Unknown camera"):
            await ptz.call_preset("cam99", 0)

    async def test_call_preset_all(self, ptz_config: PTZConfig, mock_http: AsyncMock):
        ptz = PTZClient(ptz_config, mock_http)
        await ptz.call_preset_all(5)

        assert mock_http.get.call_count == 2
        urls = [call.args[0] for call in mock_http.get.call_args_list]
        assert "http://192.168.1.10/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&5" in urls
        assert "http://192.168.1.11/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&5" in urls

    async def test_camera_ids(self, ptz_config: PTZConfig, mock_http: AsyncMock):
        ptz = PTZClient(ptz_config, mock_http)
        assert ptz.camera_ids == ["cam1", "cam2"]

    async def test_health_check_healthy(self, ptz_config: PTZConfig, mock_http: AsyncMock):
        ptz = PTZClient(ptz_config, mock_http)
        status = await ptz.health_check()
        assert status.healthy is True

    async def test_health_check_unhealthy(self, ptz_config: PTZConfig, mock_http: AsyncMock):
        mock_http.get.side_effect = httpx.ConnectError("Connection refused")
        ptz = PTZClient(ptz_config, mock_http)
        status = await ptz.health_check()
        assert status.healthy is False

    async def test_preset_url_construction(self, ptz_config: PTZConfig, mock_http: AsyncMock):
        ptz = PTZClient(ptz_config, mock_http)
        url = ptz._preset_url("cam.local", 7)
        assert url == "http://cam.local/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&7"
