"""SQLite database connection management with aiosqlite."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite
import structlog

log = structlog.get_logger()

SCHEMA_SQL = """\
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS games (
    game_id    TEXT    PRIMARY KEY,
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS clips (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id       TEXT    NOT NULL REFERENCES games(game_id),
    period        INTEGER NOT NULL,
    jam           INTEGER NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    path          TEXT    NOT NULL,
    type          TEXT    NOT NULL CHECK(type IN ('highlight')),
    status        TEXT    NOT NULL CHECK(status IN ('armed', 'played', 'superseded', 'skipped')),
    UNIQUE(game_id, path)
);

CREATE INDEX IF NOT EXISTS idx_clips_lookup
    ON clips(game_id, period, jam, type, status);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    """Manages the SQLite database lifecycle."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        async with self.connection() as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()
        log.info("database.initialized", path=self._db_path)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Yield an aiosqlite connection."""
        db = await aiosqlite.connect(self._db_path)
        try:
            yield db
        finally:
            await db.close()

    @property
    def path(self) -> str:
        return self._db_path

    def db_file_exists(self) -> bool:
        return Path(self._db_path).exists()
