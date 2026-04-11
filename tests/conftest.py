"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nwsc.config import AppConfig, load_config
from nwsc.db.engine import Database
from nwsc.db.repository import Repository
from nwsc.domain.bout import BoutService
from nwsc.domain.clip import ClipService
from nwsc.integrations.base import HealthStatus
from nwsc.integrations.obs.client import OBSClient
from nwsc.integrations.ptz.client import PTZClient
from nwsc.integrations.scoreboard.client import ScoreboardClient, ScoreState
from nwsc.services.replay_file import ReplayFileService

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def app_config() -> AppConfig:
    return load_config(FIXTURES_DIR / "config.test.yaml")


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "test.sqlite3"))
    await db.initialize()
    return db


@pytest.fixture
async def repo(db: Database) -> Repository:
    return Repository(db)


@pytest.fixture
def mock_obs(app_config: AppConfig) -> MagicMock:
    obs = MagicMock(spec=OBSClient)
    obs.name = "obs"
    obs._config = app_config.obs
    obs.health_check = AsyncMock(return_value=HealthStatus(healthy=True, detail="scene=CAM1"))
    obs.get_current_scene.return_value = "CAM1"
    obs.set_scene.return_value = "CAM1"
    obs.save_replay_buffer.return_value = None
    obs.load_media.return_value = None
    obs.show_and_play_media.return_value = None
    obs.hide_and_unload_media.return_value = None
    obs.has_media_loaded.return_value = False
    return obs


@pytest.fixture
def mock_ptz() -> MagicMock:
    ptz = MagicMock(spec=PTZClient)
    ptz.name = "ptz"
    ptz.camera_ids = ["cam1", "cam2"]
    ptz.health_check = AsyncMock(return_value=HealthStatus(healthy=True))
    ptz.call_preset = AsyncMock()
    ptz.call_preset_all = AsyncMock()
    ptz.close = AsyncMock()
    return ptz


@pytest.fixture
def mock_scoreboard() -> MagicMock:
    sb = MagicMock(spec=ScoreboardClient)
    sb.name = "scoreboard"
    sb._game_id = "test-game-1"
    sb.health_check = AsyncMock(return_value=HealthStatus(healthy=True, detail="period=1 jam=3"))
    sb.get_state = AsyncMock(return_value=ScoreState(period=1, jam=3, game_id="test-game-1"))
    sb.get_state_or_last = AsyncMock(return_value=ScoreState(period=1, jam=3, game_id="test-game-1"))
    sb.connect = AsyncMock()
    sb.disconnect = AsyncMock()
    sb.start_listener.return_value = MagicMock()
    return sb


@pytest.fixture
def replay_file_svc(app_config: AppConfig) -> ReplayFileService:
    return ReplayFileService(app_config.recordings)


@pytest.fixture
def bout_svc(repo: Repository, mock_scoreboard: MagicMock) -> BoutService:
    return BoutService(repo, mock_scoreboard)


@pytest.fixture
def clip_svc(
    repo: Repository, mock_scoreboard: MagicMock, replay_file_svc: ReplayFileService
) -> ClipService:
    return ClipService(repo, mock_scoreboard, replay_file_svc)
