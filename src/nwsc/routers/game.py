"""Game/bout management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from nwsc.db.models import GameCurrentResponse
from nwsc.db.repository import Repository
from nwsc.dependencies import get_bout_svc, get_repo
from nwsc.domain.bout import BoutService

router = APIRouter()


@router.get("/current", response_model=GameCurrentResponse)
async def game_current(
    bout_svc: BoutService = Depends(get_bout_svc),
    repo: Repository = Depends(get_repo),
) -> GameCurrentResponse:
    """Get the current active game (from scoreboard)."""
    game_id = bout_svc.get_current_game_id()
    if game_id:
        game = await repo.get_game(game_id)
        return GameCurrentResponse(
            game_id=game_id,
            created_at=game.created_at if game else None,
        )
    return GameCurrentResponse(game_id=None)
