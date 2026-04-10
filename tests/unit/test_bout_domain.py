"""Tests for bout/game domain service."""

from __future__ import annotations

import pytest

from nwsc.domain.bout import BoutService, NoActiveGameError


class TestBoutService:
    async def test_start_game(self, bout_svc: BoutService):
        game_id = await bout_svc.start_game()
        assert game_id.startswith("game-")

    async def test_get_current_game(self, bout_svc: BoutService):
        assert await bout_svc.get_current_game_id() is None

        game_id = await bout_svc.start_game()
        assert await bout_svc.get_current_game_id() == game_id

    async def test_start_game_replaces_current(self, bout_svc: BoutService):
        game1 = await bout_svc.start_game()
        game2 = await bout_svc.start_game()
        assert game1 != game2
        assert await bout_svc.get_current_game_id() == game2

    async def test_require_current_game_raises(self, bout_svc: BoutService):
        with pytest.raises(NoActiveGameError):
            await bout_svc.require_current_game()

    async def test_require_current_game_success(self, bout_svc: BoutService):
        game_id = await bout_svc.start_game()
        assert await bout_svc.require_current_game() == game_id
