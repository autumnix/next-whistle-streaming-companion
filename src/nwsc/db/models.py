"""Pydantic models for database rows and API responses."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class ClipType(str, Enum):
    HIGHLIGHT = "highlight"


class ClipStatus(str, Enum):
    ARMED = "armed"
    PLAYED = "played"
    SUPERSEDED = "superseded"
    SKIPPED = "skipped"


class GameRow(BaseModel):
    game_id: str
    created_at: str


class ClipRow(BaseModel):
    id: int
    game_id: str
    period: int
    jam: int
    created_at: str
    path: str
    type: ClipType
    status: ClipStatus


class ClipCreate(BaseModel):
    game_id: str
    period: int
    jam: int
    path: str
    type: ClipType = ClipType.HIGHLIGHT
    status: ClipStatus = ClipStatus.ARMED


# API response models

class GameCurrentResponse(BaseModel):
    game_id: str | None
    created_at: str | None = None


class ArmResponse(BaseModel):
    game_id: str
    period: int
    jam: int
    path: str


class JamResetResponse(BaseModel):
    current_period: int
    current_jam: int
    previous_period: int
    previous_jam: int
    play_path: str | None = None


class HealthCheckResponse(BaseModel):
    status: str
    integrations: dict[str, IntegrationHealthResponse] = {}


class IntegrationHealthResponse(BaseModel):
    healthy: bool
    latency_ms: float | None = None
    detail: str = ""


class StatusResponse(BaseModel):
    game_id: str | None = None
    period: int | None = None
    jam: int | None = None
    integrations: dict[str, IntegrationHealthResponse] = {}
    recent_clips: list[ClipRow] = []


# --- Overlay models ---


class OverlaySourceModel(BaseModel):
    name: str
    enabled: bool
    item_id: int


class OverlayActionResponse(BaseModel):
    group: str
    source: str
    enabled: bool
    timeout_s: float | None = None


class OverlayGroupResponse(BaseModel):
    group: str
    sources: list[OverlaySourceModel]


class OverlayHideAllResponse(BaseModel):
    group: str
    sources: list[OverlaySourceModel]
