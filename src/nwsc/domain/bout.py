"""Bout (game) lifecycle management — backed by the CRG scoreboard."""

from __future__ import annotations

import structlog

from nwsc.db.repository import Repository
from nwsc.integrations.scoreboard.client import ScoreboardClient

log = structlog.get_logger()


class BoutService:
    """Provides game_id from the CRG scoreboard and ensures DB rows exist."""

    def __init__(self, repo: Repository, scoreboard: ScoreboardClient) -> None:
        self._repo = repo
        self._scoreboard = scoreboard

    def get_current_game_id(self) -> str | None:
        """Return the current game_id from the scoreboard, or None."""
        return self._scoreboard._game_id

    def require_current_game(self) -> str:
        """Return the current game_id or raise if the scoreboard has none."""
        game_id = self.get_current_game_id()
        if not game_id:
            raise NoActiveGameError(
                "No active game on scoreboard. Is the scoreboard connected?"
            )
        return game_id

    async def ensure_game_row(self, game_id: str) -> None:
        """Ensure the games table has a row for this game_id (idempotent)."""
        await self._repo.ensure_game(game_id)


class NoActiveGameError(Exception):
    pass
