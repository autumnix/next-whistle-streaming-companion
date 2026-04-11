"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from nwsc.config import AppConfig, load_config
from nwsc.db.engine import Database
from nwsc.db.repository import Repository
from nwsc.domain.bout import BoutService
from nwsc.domain.clip import ClipService
from nwsc.domain.jam_cycle import JamCycleOrchestrator
from nwsc.integrations.obs.client import OBSClient
from nwsc.integrations.ptz.client import PTZClient
from nwsc.integrations.scoreboard.client import ScoreboardClient
from nwsc.logging import setup_logging
from nwsc.domain.overlay import OverlayService
from nwsc.routers import clips, dashboard, game, health, obs, overlays, ptz, workflows
from nwsc.services.health_monitor import HealthMonitor
from nwsc.services.replay_file import ReplayFileService


def create_app(config: AppConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if config is None:
        config = load_config()

    setup_logging(config.server.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Startup
        await app.state.db.initialize()

        # Start scoreboard listener (best-effort, don't block startup)
        try:
            app.state.scoreboard.start_listener()
        except Exception:
            pass

        # Start health monitor
        app.state.health_monitor.start()

        yield

        # Shutdown
        await app.state.scoreboard.disconnect()
        await app.state.health_monitor.stop()
        await app.state.ptz.close()

    app = FastAPI(
        title="Next Whistle Streaming Companion",
        version="0.1.0",
        description="Roller derby live streaming control service",
        lifespan=lifespan,
    )

    # Store config
    app.state.config = config

    # Database
    db = Database(config.database.path)
    app.state.db = db

    # Repository
    repo = Repository(db)
    app.state.repo = repo

    # Integration clients
    obs_client = OBSClient(config.obs)
    ptz_client = PTZClient(config.ptz)
    scoreboard_client = ScoreboardClient(config.scoreboard)

    app.state.obs = obs_client
    app.state.ptz = ptz_client
    app.state.scoreboard = scoreboard_client

    # Domain services
    replay_file_svc = ReplayFileService(config.recordings)
    bout_svc = BoutService(repo, scoreboard_client)
    clip_svc = ClipService(repo, scoreboard_client, replay_file_svc)
    jam_cycle = JamCycleOrchestrator(obs_client, ptz_client, bout_svc, clip_svc, config)

    overlay_svc = OverlayService(obs_client, allowed_groups=config.obs.overlay_groups or None)

    app.state.bout_svc = bout_svc
    app.state.clip_svc = clip_svc
    app.state.jam_cycle = jam_cycle
    app.state.overlay_svc = overlay_svc

    # Health monitor
    integrations = [obs_client, ptz_client, scoreboard_client]  # type: ignore[list-item]
    health_monitor = HealthMonitor(integrations)
    app.state.health_monitor = health_monitor

    # Routers
    app.include_router(game.router, prefix="/game", tags=["Game"])
    app.include_router(clips.router, prefix="/highlight", tags=["Clips"])
    app.include_router(obs.router, prefix="/obs", tags=["OBS"])
    app.include_router(ptz.router, prefix="/ptz", tags=["PTZ"])
    app.include_router(workflows.router, prefix="/workflow", tags=["Workflows"])
    app.include_router(overlays.router, prefix="/overlay", tags=["Overlays"])
    app.include_router(health.router, tags=["Health"])
    app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])

    # Backward-compatible aliases for Stream Deck scripts
    app.include_router(
        _compat_router(workflows.router, "/obs"),
        include_in_schema=False,
    )

    # Static files for dashboard
    static_dir = Path(__file__).parent / "dashboard" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


def _compat_router(source_router, prefix: str):
    """Create backward-compatible route aliases under a different prefix."""
    from fastapi import APIRouter, Depends

    from nwsc.dependencies import get_jam_cycle

    compat = APIRouter(prefix=prefix)

    # /obs/save-and-arm -> /workflow/save-and-arm
    @compat.api_route("/save-and-arm", methods=["GET", "POST"])
    async def compat_save_and_arm(
        jam_cycle: JamCycleOrchestrator = Depends(get_jam_cycle),
    ):
        return await workflows.save_and_arm(jam_cycle)

    # /obs/jam-reset-and-play -> /workflow/jam-reset-and-play
    @compat.api_route("/jam-reset-and-play", methods=["GET", "POST"])
    async def compat_jam_reset_and_play(
        jam_cycle: JamCycleOrchestrator = Depends(get_jam_cycle),
    ):
        return await workflows.jam_reset_and_play(jam_cycle)

    # /obs/jam-reset -> /workflow/jam-reset
    @compat.api_route("/jam-reset", methods=["GET", "POST"])
    async def compat_jam_reset(
        jam_cycle: JamCycleOrchestrator = Depends(get_jam_cycle),
    ):
        return await workflows.jam_reset(jam_cycle)

    return compat
