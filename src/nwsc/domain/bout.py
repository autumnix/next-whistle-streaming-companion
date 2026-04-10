"""Bout (game) lifecycle management."""

from __future__ import annotations

import time
import uuid

import structlog

from nwsc.db.repository import Repository

log = structlog.get_logger()


class BoutService:
    """Manages the lifecycle of a roller derby bout/game."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    async def start_game(self) -> str:
        """Create a new game and set it as the current active game.

        Returns the new game_id.
        """
        game_id = f"game-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
        await self._repo.create_game(game_id)
        log.info("bout.started", game_id=game_id)
        return game_id

    async def get_current_game_id(self) -> str | None:
        """Return the current active game_id, or None."""
        return await self._repo.get_current_game_id()

    async def require_current_game(self) -> str:
        """Return the current game_id or raise if none is active."""
        game_id = await self.get_current_game_id()
        if not game_id:
            raise NoActiveGameError("No active game. Call /game/start first.")
        return game_id


class NoActiveGameError(Exception):
    pass
