"""Tests for jam cycle orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nwsc.config import AppConfig, load_config
from nwsc.domain.bout import BoutService
from nwsc.domain.clip import ClipService
from nwsc.domain.jam_cycle import JamCycleOrchestrator


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def config() -> AppConfig:
    return load_config(FIXTURES_DIR / "config.test.yaml")


@pytest.fixture
def jam_cycle(
    mock_obs: MagicMock,
    mock_ptz: MagicMock,
    bout_svc: BoutService,
    clip_svc: ClipService,
    config: AppConfig,
) -> JamCycleOrchestrator:
    return JamCycleOrchestrator(mock_obs, mock_ptz, bout_svc, clip_svc, config)


class TestJamReset:
    async def test_jam_reset_switches_to_cam1(
        self, jam_cycle: JamCycleOrchestrator, bout_svc: BoutService, mock_obs: MagicMock
    ):
        await bout_svc.start_game()
        await jam_cycle.jam_reset()

        mock_obs.set_scene.assert_called_with("CAM1")

    async def test_jam_reset_calls_ptz_preset(
        self, jam_cycle: JamCycleOrchestrator, bout_svc: BoutService, mock_ptz: MagicMock
    ):
        await bout_svc.start_game()
        await jam_cycle.jam_reset()

        mock_ptz.call_preset_all.assert_called_with(0)

    async def test_jam_reset_returns_response(
        self, jam_cycle: JamCycleOrchestrator, bout_svc: BoutService
    ):
        await bout_svc.start_game()
        resp = await jam_cycle.jam_reset()

        assert resp.current_period == 1
        assert resp.current_jam == 3
        assert resp.play_path is None


class TestJamResetAndPlay:
    async def test_with_replay(
        self,
        jam_cycle: JamCycleOrchestrator,
        bout_svc: BoutService,
        clip_svc: ClipService,
        mock_obs: MagicMock,
        mock_ptz: MagicMock,
        tmp_path: Path,
    ):
        # Setup replay file
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()
        (replay_dir / "replay.mkv").write_bytes(b"x" * 100)
        clip_svc._replay_file._config.replay_dir_override = str(replay_dir)

        game_id = await bout_svc.start_game()
        await clip_svc.arm_latest(game_id)

        resp = await jam_cycle.jam_reset_and_play()

        # Should switch to replay scene
        mock_obs.set_scene.assert_called_with("REPLAY")
        # Should call PTZ
        mock_ptz.call_preset_all.assert_called_with(0)
        # Should load and play media
        mock_obs.load_and_play_media.assert_called_once()
        # Should have a play path
        assert resp.play_path is not None

    async def test_without_replay(
        self,
        jam_cycle: JamCycleOrchestrator,
        bout_svc: BoutService,
        mock_obs: MagicMock,
        mock_ptz: MagicMock,
    ):
        await bout_svc.start_game()
        resp = await jam_cycle.jam_reset_and_play()

        # Should switch to safe scene (no replay available)
        mock_obs.set_scene.assert_called_with("BUMPER")
        mock_ptz.call_preset_all.assert_called_with(0)
        assert resp.play_path is None

    async def test_ptz_failure_does_not_block(
        self,
        jam_cycle: JamCycleOrchestrator,
        bout_svc: BoutService,
        mock_obs: MagicMock,
        mock_ptz: MagicMock,
    ):
        mock_ptz.call_preset_all.side_effect = ConnectionError("PTZ unreachable")
        await bout_svc.start_game()

        # Should not raise despite PTZ failure
        resp = await jam_cycle.jam_reset_and_play()
        assert resp.current_period == 1


class TestSaveAndArm:
    async def test_save_and_arm(
        self,
        jam_cycle: JamCycleOrchestrator,
        bout_svc: BoutService,
        clip_svc: ClipService,
        mock_obs: MagicMock,
        tmp_path: Path,
    ):
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()
        (replay_dir / "replay.mkv").write_bytes(b"x" * 100)
        clip_svc._replay_file._config.replay_dir_override = str(replay_dir)

        await bout_svc.start_game()
        resp = await jam_cycle.save_and_arm()

        mock_obs.save_replay_buffer.assert_called_once()
        assert resp.period == 1
        assert resp.jam == 3
