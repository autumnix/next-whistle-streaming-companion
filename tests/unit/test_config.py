"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from nwsc.config import AppConfig, load_config

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_load_from_yaml():
    config = load_config(FIXTURES_DIR / "config.test.yaml")
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8787
    assert config.obs.port == 4455
    assert config.obs.scenes.cam1 == "CAM1"
    assert len(config.ptz.cameras) == 2
    assert config.ptz.cameras["cam1"].host == "192.168.1.10"


def test_defaults_when_no_file():
    config = load_config("/nonexistent/config.yaml")
    assert config.server.port == 8787
    assert config.obs.host == "127.0.0.1"
    assert config.obs.scenes.cam1 == "LIVE - CAM 1"
    assert config.database.path == "nwsc.sqlite3"


def test_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NWSC_OBS__HOST", "10.0.0.5")
    monkeypatch.setenv("NWSC_OBS__PORT", "9999")
    config = load_config("/nonexistent/config.yaml")
    assert config.obs.host == "10.0.0.5"
    assert config.obs.port == 9999


def test_env_override_with_yaml(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NWSC_OBS__HOST", "override.local")
    config = load_config(FIXTURES_DIR / "config.test.yaml")
    assert config.obs.host == "override.local"
    # Other values from YAML should still be present
    assert config.obs.port == 4455


def test_recordings_extensions():
    config = load_config(FIXTURES_DIR / "config.test.yaml")
    assert ".mkv" in config.recordings.extensions
    assert ".mp4" in config.recordings.extensions
    assert ".mov" in config.recordings.extensions


def test_scoreboard_config():
    config = load_config(FIXTURES_DIR / "config.test.yaml")
    assert config.scoreboard.url == "ws://localhost:8000/WS/"
    assert config.scoreboard.prime_timeout_s == 1.0


def test_ptz_url_template():
    config = load_config(FIXTURES_DIR / "config.test.yaml")
    url = config.ptz.url_template.format(host="cam1.local", preset=3)
    assert url == "http://cam1.local/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&3"


def test_full_model_validation():
    """Ensure AppConfig can be constructed from a minimal dict."""
    config = AppConfig.model_validate({})
    assert config.server.port == 8787
    assert config.obs.transition.name == "Fade"


def test_nested_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NWSC_SERVER__LOG_LEVEL", "debug")
    config = load_config("/nonexistent/config.yaml")
    assert config.server.log_level == "debug"
