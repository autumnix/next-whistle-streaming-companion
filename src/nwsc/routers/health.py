"""Health check and status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from nwsc.db.models import (
    HealthCheckResponse,
    IntegrationHealthResponse,
    StatusResponse,
)
from nwsc.dependencies import get_bout_svc, get_health_monitor, get_repo, get_scoreboard
from nwsc.domain.bout import BoutService
from nwsc.db.repository import Repository
from nwsc.integrations.scoreboard.client import ScoreboardClient
from nwsc.services.health_monitor import HealthMonitor

router = APIRouter()


@router.get("/health", response_model=HealthCheckResponse)
async def health(
    monitor: HealthMonitor = Depends(get_health_monitor),
) -> HealthCheckResponse:
    """Overall health status of all integrations."""
    statuses = monitor.status
    all_healthy = all(s.healthy for s in statuses.values()) if statuses else True

    return HealthCheckResponse(
        status="ok" if all_healthy else "degraded",
        integrations={
            name: IntegrationHealthResponse(
                healthy=s.healthy, latency_ms=s.latency_ms, detail=s.detail
            )
            for name, s in statuses.items()
        },
    )


@router.get("/status", response_model=StatusResponse)
async def status(
    bout_svc: BoutService = Depends(get_bout_svc),
    repo: Repository = Depends(get_repo),
    scoreboard: ScoreboardClient = Depends(get_scoreboard),
    monitor: HealthMonitor = Depends(get_health_monitor),
) -> StatusResponse:
    """Combined status: game state, connections, recent clips."""
    game_id = bout_svc.get_current_game_id()

    period = None
    jam = None
    try:
        state = await scoreboard.get_state()
        period = state.period
        jam = state.jam
    except Exception:
        pass

    recent_clips = []
    if game_id:
        recent_clips = await repo.get_recent_clips(game_id, limit=10)

    statuses = monitor.status
    return StatusResponse(
        game_id=game_id,
        period=period,
        jam=jam,
        integrations={
            name: IntegrationHealthResponse(
                healthy=s.healthy, latency_ms=s.latency_ms, detail=s.detail
            )
            for name, s in statuses.items()
        },
        recent_clips=recent_clips,
    )
