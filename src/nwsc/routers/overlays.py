"""Overlay source group control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from nwsc.db.models import (
    OverlayActionResponse,
    OverlayGroupResponse,
    OverlayHideAllResponse,
    OverlaySourceModel,
)
from nwsc.domain.overlay import OverlayService

router = APIRouter()


def get_overlay_svc(request: Request) -> OverlayService:
    return request.app.state.overlay_svc


@router.api_route("/{group}/sources", methods=["GET", "POST"], response_model=OverlayGroupResponse)
def list_sources(
    group: str,
    overlay_svc: OverlayService = Depends(get_overlay_svc),
) -> OverlayGroupResponse:
    """List all sources in an overlay group with current visibility."""
    try:
        sources = overlay_svc.list_sources(group)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return OverlayGroupResponse(
        group=group,
        sources=[OverlaySourceModel(name=s.name, enabled=s.enabled, item_id=s.item_id) for s in sources],
    )


@router.api_route("/{group}/toggle", methods=["GET", "POST"], response_model=OverlayActionResponse)
def toggle_source(
    group: str,
    source: str = Query(..., description="Source name within the group"),
    enabled: bool = Query(..., description="True to show, False to hide"),
    overlay_svc: OverlayService = Depends(get_overlay_svc),
) -> OverlayActionResponse:
    """Toggle a single source's visibility."""
    try:
        result = overlay_svc.toggle(group, source, enabled)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return OverlayActionResponse(group=group, source=result.name, enabled=result.enabled)


@router.api_route("/{group}/show", methods=["GET", "POST"], response_model=OverlayActionResponse)
async def show_source(
    group: str,
    source: str = Query(..., description="Source name to display"),
    timeout: float | None = Query(None, description="Auto-hide after N seconds"),
    overlay_svc: OverlayService = Depends(get_overlay_svc),
) -> OverlayActionResponse:
    """Display one source exclusively — hides all others in the group.

    Optionally auto-hides after timeout seconds.
    """
    try:
        result = overlay_svc.display_only(group, source, timeout_s=timeout)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return OverlayActionResponse(
        group=group, source=result.name, enabled=result.enabled, timeout_s=timeout
    )


@router.api_route("/{group}/hide-all", methods=["GET", "POST"], response_model=OverlayHideAllResponse)
def hide_all(
    group: str,
    overlay_svc: OverlayService = Depends(get_overlay_svc),
) -> OverlayHideAllResponse:
    """Hide all sources in the overlay group."""
    try:
        sources = overlay_svc.hide_all(group)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return OverlayHideAllResponse(
        group=group,
        sources=[OverlaySourceModel(name=s.name, enabled=s.enabled, item_id=s.item_id) for s in sources],
    )
