"""OBS Studio control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from nwsc.dependencies import get_obs
from nwsc.integrations.obs.client import OBSClient

router = APIRouter()


@router.api_route("/go-cam1", methods=["GET", "POST"])
def go_cam1(obs: OBSClient = Depends(get_obs)) -> dict:
    """Switch to camera 1 scene."""
    cam1 = obs._config.scenes.cam1
    actual = obs.set_scene(cam1)
    return {"requested": cam1, "program_now": actual}


@router.api_route("/go-cam2", methods=["GET", "POST"])
def go_cam2(obs: OBSClient = Depends(get_obs)) -> dict:
    """Switch to camera 2 scene."""
    cam2 = obs._config.scenes.cam2
    actual = obs.set_scene(cam2)
    return {"requested": cam2, "program_now": actual}


@router.get("/ping")
def ping(obs: OBSClient = Depends(get_obs)) -> dict:
    """OBS health check - returns current scene."""
    scene = obs.get_current_scene()
    return {"scene": scene}
