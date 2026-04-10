"""Tests for replay file service."""

from __future__ import annotations

from pathlib import Path

import pytest

from nwsc.config import RecordingsConfig
from nwsc.services.replay_file import ReplayFileService


@pytest.fixture
def svc(tmp_path: Path) -> ReplayFileService:
    config = RecordingsConfig(
        base_path=str(tmp_path / "recordings"),
        extensions=[".mkv", ".mp4", ".mov"],
        file_stabilize_timeout_s=1.0,
        file_stabilize_poll_s=0.05,
    )
    return ReplayFileService(config)


class TestNewestReplayFile:
    def test_finds_newest_file(self, svc: ReplayFileService, tmp_path: Path):
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()

        (replay_dir / "old.mkv").write_bytes(b"old")
        import time
        time.sleep(0.05)
        (replay_dir / "new.mkv").write_bytes(b"newer")

        result = svc.newest_replay_file(replay_dir)
        assert result is not None
        assert result.name == "new.mkv"

    def test_returns_none_when_empty(self, svc: ReplayFileService, tmp_path: Path):
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()
        assert svc.newest_replay_file(replay_dir) is None

    def test_returns_none_when_dir_missing(self, svc: ReplayFileService, tmp_path: Path):
        assert svc.newest_replay_file(tmp_path / "nonexistent") is None

    def test_ignores_non_replay_extensions(self, svc: ReplayFileService, tmp_path: Path):
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()

        (replay_dir / "file.txt").write_bytes(b"text")
        (replay_dir / "file.jpg").write_bytes(b"image")
        (replay_dir / "replay.mkv").write_bytes(b"video")

        result = svc.newest_replay_file(replay_dir)
        assert result is not None
        assert result.name == "replay.mkv"

    def test_handles_multiple_extensions(self, svc: ReplayFileService, tmp_path: Path):
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()

        (replay_dir / "a.mkv").write_bytes(b"a")
        import time
        time.sleep(0.05)
        (replay_dir / "b.mp4").write_bytes(b"b")
        time.sleep(0.05)
        (replay_dir / "c.mov").write_bytes(b"c")

        result = svc.newest_replay_file(replay_dir)
        assert result is not None
        assert result.name == "c.mov"


class TestResolveReplayDir:
    def test_explicit_override(self, tmp_path: Path):
        override = tmp_path / "my_replays"
        config = RecordingsConfig(
            base_path=str(tmp_path),
            replay_dir_override=str(override),
        )
        svc = ReplayFileService(config)
        assert svc.resolve_replay_dir() == override

    def test_auto_detect_date_dir(self, tmp_path: Path):
        base = tmp_path / "recordings"
        base.mkdir()
        (base / "2024-01-15").mkdir()
        (base / "2024-03-20").mkdir()
        (base / "2024-02-10").mkdir()
        (base / "not-a-date").mkdir()

        config = RecordingsConfig(base_path=str(base))
        svc = ReplayFileService(config)
        result = svc.resolve_replay_dir()
        assert result == base / "2024-03-20" / "replays"

    def test_fallback_to_cwd(self, tmp_path: Path):
        config = RecordingsConfig(base_path=str(tmp_path / "nonexistent"))
        svc = ReplayFileService(config)
        assert svc.resolve_replay_dir() == Path(".")


class TestWaitForStable:
    async def test_stable_file(self, svc: ReplayFileService, tmp_path: Path):
        f = tmp_path / "replay.mkv"
        f.write_bytes(b"x" * 100)
        await svc.wait_for_stable(f)  # Should not raise

    async def test_timeout_on_missing_file(self, tmp_path: Path):
        config = RecordingsConfig(
            base_path=str(tmp_path),
            file_stabilize_timeout_s=0.2,
            file_stabilize_poll_s=0.05,
        )
        svc = ReplayFileService(config)
        with pytest.raises(TimeoutError):
            await svc.wait_for_stable(tmp_path / "missing.mkv")
