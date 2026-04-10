"""Dashboard web UI: serves HTML pages for status monitoring."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

_TEMPLATE_DIR = Path(__file__).parent.parent / "dashboard" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


@router.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request) -> HTMLResponse:
    """Main dashboard page - shows live status."""
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/config", response_class=HTMLResponse)
async def dashboard_config(request: Request) -> HTMLResponse:
    """Configuration viewer page."""
    config = request.app.state.config
    return templates.TemplateResponse("config.html", {"request": request, "config": config})
