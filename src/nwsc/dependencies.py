"""FastAPI dependency injection providers."""

from __future__ import annotations

from fastapi import Request

from nwsc.domain.bout import BoutService
from nwsc.domain.clip import ClipService
from nwsc.domain.jam_cycle import JamCycleOrchestrator
from nwsc.integrations.obs.client import OBSClient
from nwsc.integrations.ptz.client import PTZClient
from nwsc.integrations.scoreboard.client import ScoreboardClient
from nwsc.db.repository import Repository
from nwsc.services.health_monitor import HealthMonitor


def get_bout_svc(request: Request) -> BoutService:
    return request.app.state.bout_svc


def get_clip_svc(request: Request) -> ClipService:
    return request.app.state.clip_svc


def get_jam_cycle(request: Request) -> JamCycleOrchestrator:
    return request.app.state.jam_cycle


def get_obs(request: Request) -> OBSClient:
    return request.app.state.obs


def get_ptz(request: Request) -> PTZClient:
    return request.app.state.ptz


def get_scoreboard(request: Request) -> ScoreboardClient:
    return request.app.state.scoreboard


def get_repo(request: Request) -> Repository:
    return request.app.state.repo


def get_health_monitor(request: Request) -> HealthMonitor:
    return request.app.state.health_monitor
