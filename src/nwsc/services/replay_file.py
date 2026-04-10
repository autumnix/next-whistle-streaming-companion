"""Filesystem service: find newest replay files and wait for stabilization."""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

import structlog

from nwsc.config import RecordingsConfig

log = structlog.get_logger()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ReplayFileService:
    """Handles replay file discovery and stabilization."""

    def __init__(self, config: RecordingsConfig) -> None:
        self._config = config

    def resolve_replay_dir(self) -> Path:
        """Resolve the replay directory.

        Priority:
        1. Explicit override in config
        2. Auto-detect newest YYYY-MM-DD folder under recordings base
        3. Fall back to current directory
        """
        if self._config.replay_dir_override:
            return Path(self._config.replay_dir_override).expanduser()

        base = Path(self._config.base_path).expanduser()
        if base.exists():
            dated = [
                p
                for p in base.iterdir()
                if p.is_dir() and _DATE_RE.match(p.name)
            ]
            if dated:
                latest = max(dated, key=lambda p: p.name)
                return latest / "replays"

        return Path(".")

    def newest_replay_file(self, directory: Path | None = None) -> Path | None:
        """Find the newest replay file in the directory."""
        replay_dir = directory or self.resolve_replay_dir()
        if not replay_dir.exists():
            return None

        exts = set(self._config.extensions)
        candidates = [
            p for p in replay_dir.iterdir() if p.is_file() and p.suffix.lower() in exts
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    async def wait_for_stable(self, path: Path) -> None:
        """Wait until the file size stops changing (OBS finished writing)."""
        deadline = time.time() + self._config.file_stabilize_timeout_s
        last_size = -1

        while time.time() < deadline:
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                await asyncio.sleep(self._config.file_stabilize_poll_s)
                continue

            if size == last_size and size > 0:
                log.debug("replay_file.stable", path=str(path), size=size)
                return
            last_size = size
            await asyncio.sleep(self._config.file_stabilize_poll_s)

        raise TimeoutError(f"Replay file did not stabilize in time: {path}")
