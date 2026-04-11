"""Tests for database repository operations."""

from __future__ import annotations

import pytest

from nwsc.db.engine import Database
from nwsc.db.models import ClipCreate, ClipStatus
from nwsc.db.repository import Repository


@pytest.fixture
async def repo(tmp_path) -> Repository:
    db = Database(str(tmp_path / "test.sqlite3"))
    await db.initialize()
    return Repository(db)


class TestGameOperations:
    async def test_ensure_game(self, repo: Repository):
        await repo.ensure_game("game-1")
        game = await repo.get_game("game-1")
        assert game is not None
        assert game.game_id == "game-1"
        assert game.created_at is not None

    async def test_ensure_game_idempotent(self, repo: Repository):
        await repo.ensure_game("game-1")
        await repo.ensure_game("game-1")
        game = await repo.get_game("game-1")
        assert game is not None

    async def test_get_nonexistent_game(self, repo: Repository):
        game = await repo.get_game("nonexistent")
        assert game is None


class TestClipOperations:
    async def test_insert_clip(self, repo: Repository):
        await repo.ensure_game("game-1")
        clip = ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/test.mkv")
        clip_id = await repo.insert_clip(clip)
        assert clip_id > 0

    async def test_get_armed_clip(self, repo: Repository):
        await repo.ensure_game("game-1")
        clip = ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/test.mkv")
        await repo.insert_clip(clip)

        armed = await repo.get_armed_clip("game-1", 1, 3)
        assert armed is not None
        assert armed.path == "/replay/test.mkv"
        assert armed.status == ClipStatus.ARMED

    async def test_get_armed_clip_wrong_jam(self, repo: Repository):
        await repo.ensure_game("game-1")
        clip = ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/test.mkv")
        await repo.insert_clip(clip)

        armed = await repo.get_armed_clip("game-1", 1, 4)
        assert armed is None

    async def test_insert_supersedes_previous(self, repo: Repository):
        await repo.ensure_game("game-1")
        clip1 = ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/test1.mkv")
        await repo.insert_clip(clip1)

        clip2 = ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/test2.mkv")
        await repo.insert_clip(clip2)

        # First clip should be superseded
        armed = await repo.get_armed_clip("game-1", 1, 3)
        assert armed is not None
        assert armed.path == "/replay/test2.mkv"

    async def test_upsert_same_path(self, repo: Repository):
        await repo.ensure_game("game-1")
        clip = ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/test.mkv")
        await repo.insert_clip(clip)

        # Same path, different jam
        clip2 = ClipCreate(game_id="game-1", period=1, jam=4, path="/replay/test.mkv")
        await repo.insert_clip(clip2)

        # Should be updated to new jam
        armed = await repo.get_armed_clip("game-1", 1, 4)
        assert armed is not None
        assert armed.path == "/replay/test.mkv"

    async def test_update_clip_status(self, repo: Repository):
        await repo.ensure_game("game-1")
        clip = ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/test.mkv")
        await repo.insert_clip(clip)

        armed = await repo.get_armed_clip("game-1", 1, 3)
        assert armed is not None

        await repo.update_clip_status(armed.id, ClipStatus.PLAYED)

        # Should no longer be armed
        armed_after = await repo.get_armed_clip("game-1", 1, 3)
        assert armed_after is None

    async def test_skip_stale_armed_clips(self, repo: Repository):
        await repo.ensure_game("game-1")

        # Arm clips in different jams
        await repo.insert_clip(
            ClipCreate(game_id="game-1", period=1, jam=1, path="/replay/j1.mkv")
        )
        await repo.insert_clip(
            ClipCreate(game_id="game-1", period=1, jam=2, path="/replay/j2.mkv")
        )
        await repo.insert_clip(
            ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/j3.mkv")
        )

        # Skip stale clips for jam 3
        skipped = await repo.skip_stale_armed_clips("game-1", 1, 3)
        assert skipped == 2

        # Jam 3 clip should still be armed
        armed = await repo.get_armed_clip("game-1", 1, 3)
        assert armed is not None

        # Jam 1 and 2 should be skipped
        assert await repo.get_armed_clip("game-1", 1, 1) is None
        assert await repo.get_armed_clip("game-1", 1, 2) is None

    async def test_get_recent_clips(self, repo: Repository):
        await repo.ensure_game("game-1")
        for i in range(5):
            await repo.insert_clip(
                ClipCreate(game_id="game-1", period=1, jam=i + 1, path=f"/replay/j{i}.mkv")
            )

        recent = await repo.get_recent_clips("game-1", limit=3)
        assert len(recent) == 3


class TestConsumeArmedClip:
    async def test_consume_returns_path(self, repo: Repository):
        await repo.ensure_game("game-1")
        await repo.insert_clip(
            ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/test.mkv")
        )

        path = await repo.consume_armed_clip("game-1", 1, 3)
        assert path == "/replay/test.mkv"

    async def test_consume_returns_none_when_no_clip(self, repo: Repository):
        await repo.ensure_game("game-1")
        path = await repo.consume_armed_clip("game-1", 1, 3)
        assert path is None

    async def test_consume_prevents_duplicate_play(self, repo: Repository):
        await repo.ensure_game("game-1")
        await repo.insert_clip(
            ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/test.mkv")
        )

        # First consume
        path = await repo.consume_armed_clip("game-1", 1, 3)
        assert path == "/replay/test.mkv"

        # Arm the same file again
        await repo.insert_clip(
            ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/test.mkv")
        )

        # Second consume of same file should be skipped
        path2 = await repo.consume_armed_clip("game-1", 1, 3)
        assert path2 is None

    async def test_consume_skips_other_jams(self, repo: Repository):
        await repo.ensure_game("game-1")
        await repo.insert_clip(
            ClipCreate(game_id="game-1", period=1, jam=1, path="/replay/old.mkv")
        )
        await repo.insert_clip(
            ClipCreate(game_id="game-1", period=1, jam=3, path="/replay/current.mkv")
        )

        path = await repo.consume_armed_clip("game-1", 1, 3)
        assert path == "/replay/current.mkv"

        # Jam 1 clip should have been skipped
        assert await repo.get_armed_clip("game-1", 1, 1) is None

    async def test_consume_jam_zero_returns_none(self, repo: Repository):
        """Jam 0 means the game hasn't started - no clips to consume."""
        await repo.ensure_game("game-1")
        path = await repo.consume_armed_clip("game-1", 1, 0)
        assert path is None
