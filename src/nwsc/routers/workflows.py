"""Orchestrated workflow endpoints (jam reset, save-and-arm, etc.)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from nwsc.db.models import ArmResponse, JamResetResponse
from nwsc.dependencies import get_jam_cycle
from nwsc.domain.bout import NoActiveGameError
from nwsc.domain.jam_cycle import JamCycleOrchestrator

router = APIRouter()


@router.api_route("/save-and-arm", methods=["GET", "POST"], response_model=ArmResponse)
async def save_and_arm(
    jam_cycle: JamCycleOrchestrator = Depends(get_jam_cycle),
) -> ArmResponse:
    """Save OBS replay buffer and arm the clip."""
    try:
        return await jam_cycle.save_and_arm()
    except NoActiveGameError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.api_route("/jam-reset", methods=["GET", "POST"], response_model=JamResetResponse)
async def jam_reset(
    jam_cycle: JamCycleOrchestrator = Depends(get_jam_cycle),
) -> JamResetResponse:
    """Jam reset without replay playback."""
    try:
        return await jam_cycle.jam_reset()
    except NoActiveGameError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.api_route(
    "/jam-reset-and-play", methods=["GET", "POST"], response_model=JamResetResponse
)
async def jam_reset_and_play(
    jam_cycle: JamCycleOrchestrator = Depends(get_jam_cycle),
) -> JamResetResponse:
    """Jam reset with replay: play highlight, then switch back to live cam."""
    try:
        return await jam_cycle.jam_reset_and_play()
    except NoActiveGameError as e:
        raise HTTPException(status_code=409, detail=str(e))
