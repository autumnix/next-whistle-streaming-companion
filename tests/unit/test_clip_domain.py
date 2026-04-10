"""Tests for clip/highlight domain service."""

from __future__ import annotations

from pathlib import Path

import pytest

from nwsc.domain.clip import ClipService


class TestClipService:
    async def test_arm_latest(
        self, clip_svc: ClipService, bout_svc, mock_scoreboard, tmp_path: Path
    ):
        # Setup: create a replay file
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()
        replay_file = replay_dir / "replay.mkv"
        replay_file.write_bytes(b"x" * 100)

        # Point the service at our temp dir
        clip_svc._replay_file._config.replay_dir_override = str(replay_dir)

        game_id = await bout_svc.start_game()
        result = await clip_svc.arm_latest(game_id)

        assert result.game_id == game_id
        assert result.period == 1
        assert result.jam == 3
        assert result.path == str(replay_file)

    async def test_arm_latest_no_files(self, clip_svc: ClipService, bout_svc, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        clip_svc._replay_file._config.replay_dir_override = str(empty_dir)

        game_id = await bout_svc.start_game()
        with pytest.raises(FileNotFoundError):
            await clip_svc.arm_latest(game_id)

    async def test_consume_for_jam(
        self, clip_svc: ClipService, bout_svc, tmp_path: Path
    ):
        # Setup
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()
        (replay_dir / "replay.mkv").write_bytes(b"x" * 100)
        clip_svc._replay_file._config.replay_dir_override = str(replay_dir)

        game_id = await bout_svc.start_game()
        await clip_svc.arm_latest(game_id)

        result = await clip_svc.consume_for_jam(game_id)
        assert result.current_period == 1
        assert result.current_jam == 3
        assert result.play_path is not None

    async def test_consume_returns_none_when_empty(
        self, clip_svc: ClipService, bout_svc
    ):
        game_id = await bout_svc.start_game()
        result = await clip_svc.consume_for_jam(game_id)
        assert result.play_path is None
