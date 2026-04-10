"""Clip/highlight management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from nwsc.db.models import ArmResponse, ClipRow
from nwsc.dependencies import get_bout_svc, get_clip_svc, get_repo
from nwsc.domain.bout import BoutService, NoActiveGameError
from nwsc.domain.clip import ClipService
from nwsc.db.repository import Repository

router = APIRouter()


@router.api_route("/arm-latest", methods=["GET", "POST"], response_model=ArmResponse)
async def arm_latest(
    bout_svc: BoutService = Depends(get_bout_svc),
    clip_svc: ClipService = Depends(get_clip_svc),
) -> ArmResponse:
    """Arm the newest replay file as the highlight for the current jam."""
    try:
        game_id = await bout_svc.require_current_game()
    except NoActiveGameError as e:
        raise HTTPException(status_code=409, detail=str(e))

    try:
        result = await clip_svc.arm_latest(game_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))

    return ArmResponse(
        game_id=result.game_id,
        period=result.period,
        jam=result.jam,
        path=result.path,
    )


@router.get("/history", response_model=list[ClipRow])
async def clip_history(
    bout_svc: BoutService = Depends(get_bout_svc),
    repo: Repository = Depends(get_repo),
) -> list[ClipRow]:
    """List recent clips for the current game."""
    game_id = await bout_svc.get_current_game_id()
    if not game_id:
        return []
    return await repo.get_recent_clips(game_id)
