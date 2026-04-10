"""PTZ camera control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from nwsc.dependencies import get_ptz
from nwsc.integrations.ptz.client import PTZClient

router = APIRouter()


@router.api_route("/cam/{cam_id}/preset/{preset}", methods=["GET", "POST"])
async def set_cam_preset(
    cam_id: str,
    preset: int,
    ptz: PTZClient = Depends(get_ptz),
) -> dict:
    """Call a preset on a single camera."""
    try:
        await ptz.call_preset(cam_id, preset)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "cam": cam_id, "preset": preset}


@router.api_route("/all/preset/{preset}", methods=["GET", "POST"])
async def set_all_preset(
    preset: int,
    ptz: PTZClient = Depends(get_ptz),
) -> dict:
    """Call a preset on all cameras in parallel."""
    await ptz.call_preset_all(preset)
    return {"ok": True, "cams": ptz.camera_ids, "preset": preset}
