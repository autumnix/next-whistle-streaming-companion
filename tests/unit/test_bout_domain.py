"""Tests for bout/game domain service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nwsc.db.repository import Repository
from nwsc.domain.bout import BoutService, NoActiveGameError


class TestBoutService:
    async def test_get_current_game_id_from_scoreboard(
        self, bout_svc: BoutService, mock_scoreboard: MagicMock
    ):
        mock_scoreboard._game_id = "sb-game-42"
        assert bout_svc.get_current_game_id() == "sb-game-42"

    async def test_get_current_game_id_none(
        self, bout_svc: BoutService, mock_scoreboard: MagicMock
    ):
        mock_scoreboard._game_id = None
        assert bout_svc.get_current_game_id() is None

    async def test_require_current_game_success(
        self, bout_svc: BoutService, mock_scoreboard: MagicMock
    ):
        mock_scoreboard._game_id = "sb-game-42"
        assert bout_svc.require_current_game() == "sb-game-42"

    async def test_require_current_game_raises(
        self, bout_svc: BoutService, mock_scoreboard: MagicMock
    ):
        mock_scoreboard._game_id = None
        with pytest.raises(NoActiveGameError):
            bout_svc.require_current_game()

    async def test_ensure_game_row(
        self, bout_svc: BoutService, repo: Repository
    ):
        await bout_svc.ensure_game_row("sb-game-42")
        game = await repo.get_game("sb-game-42")
        assert game is not None
        assert game.game_id == "sb-game-42"

    async def test_ensure_game_row_idempotent(
        self, bout_svc: BoutService, repo: Repository
    ):
        await bout_svc.ensure_game_row("sb-game-42")
        await bout_svc.ensure_game_row("sb-game-42")
        game = await repo.get_game("sb-game-42")
        assert game is not None
