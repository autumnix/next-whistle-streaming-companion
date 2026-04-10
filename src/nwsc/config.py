"""Configuration system: YAML file + env var overrides + Pydantic validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8787
    log_level: str = "info"


class DatabaseConfig(BaseModel):
    path: str = "nwsc.sqlite3"


class RecordingsConfig(BaseModel):
    base_path: str = "~/streaming/recordings"
    replay_dir_override: str | None = None
    extensions: list[str] = Field(default_factory=lambda: [".mkv", ".mp4", ".mov"])
    file_stabilize_timeout_s: float = 6.0
    file_stabilize_poll_s: float = 0.25


class OBSScenesConfig(BaseModel):
    cam1: str = "LIVE - CAM 1"
    cam2: str = "LIVE - CAM 2"
    replay: str = "REPLAY"
    safe: str = "BUMPER"


class OBSTransitionConfig(BaseModel):
    name: str = "Fade"
    duration_ms: int = 300


class OBSConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4455
    password: str = ""
    timeout_s: int = 5
    scenes: OBSScenesConfig = Field(default_factory=OBSScenesConfig)
    media_input_name: str = "REPLAY_MEDIA"
    replay_length_s: float = 8.0
    replay_pad_s: float = 0.25
    transition: OBSTransitionConfig = Field(default_factory=OBSTransitionConfig)


class PTZCameraConfig(BaseModel):
    host: str


class PTZConfig(BaseModel):
    cameras: dict[str, PTZCameraConfig] = Field(default_factory=dict)
    url_template: str = "http://{host}/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&{preset}"
    timeout_s: int = 2
    jam_start_preset: int = 0
    settle_s: float = 1.25


class ScoreboardConfig(BaseModel):
    url: str = "ws://scoreboard.nws.lan:8000/WS/"
    ping_interval_s: int = 20
    ping_timeout_s: int = 20
    reconnect_delay_s: int = 5
    prime_timeout_s: float = 3.0


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    recordings: RecordingsConfig = Field(default_factory=RecordingsConfig)
    obs: OBSConfig = Field(default_factory=OBSConfig)
    ptz: PTZConfig = Field(default_factory=PTZConfig)
    scoreboard: ScoreboardConfig = Field(default_factory=ScoreboardConfig)


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply NWSC_ prefixed env vars as overrides. Uses __ as nesting separator."""
    prefix = "NWSC_"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix) :].lower().split("__")
        target = data
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return data


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load config from YAML file with env var overrides.

    Resolution order for config file path:
    1. Explicit ``path`` argument
    2. ``NWSC_CONFIG`` environment variable
    3. ``config.yaml`` in the current working directory
    """
    if path is None:
        path = os.environ.get("NWSC_CONFIG", "config.yaml")

    config_path = Path(path)
    data: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

    data = _apply_env_overrides(data)
    return AppConfig.model_validate(data)
