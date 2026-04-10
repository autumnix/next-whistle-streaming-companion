"""Database repository: all SQL operations for games, clips, and key-value store."""

from __future__ import annotations

import os

import structlog

from nwsc.db.engine import Database
from nwsc.db.models import ClipCreate, ClipRow, ClipStatus, GameRow

log = structlog.get_logger()

# KV key constants
LAST_PLAYED_KV = "last_played_replay_path"
CURRENT_GAME_KV = "current_game_id"


def last_jam_key(period: int) -> str:
    return f"last_seen_jam_p{period}"


class Repository:
    """Encapsulates all database access."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # --- Games ---

    async def create_game(self, game_id: str) -> None:
        async with self._db.connection() as conn:
            await conn.execute("INSERT INTO games(game_id) VALUES(?)", (game_id,))
            await self.kv_set(conn, CURRENT_GAME_KV, game_id)
            await self.kv_set(conn, LAST_PLAYED_KV, "")
            await conn.commit()
        log.info("game.created", game_id=game_id)

    async def get_current_game_id(self) -> str | None:
        async with self._db.connection() as conn:
            return await self.kv_get(conn, CURRENT_GAME_KV)

    async def get_game(self, game_id: str) -> GameRow | None:
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT game_id, created_at FROM games WHERE game_id = ?", (game_id,)
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return GameRow(game_id=row[0], created_at=row[1])

    # --- Clips ---

    async def insert_clip(self, clip: ClipCreate) -> int:
        """Insert or upsert a clip. Returns the clip id."""
        async with self._db.connection() as conn:
            # Supersede previously armed clips for the same jam
            await conn.execute(
                "UPDATE clips SET status='superseded' "
                "WHERE game_id=? AND period=? AND jam=? AND type=? AND status='armed'",
                (clip.game_id, clip.period, clip.jam, clip.type.value),
            )

            await conn.execute(
                "INSERT INTO clips(game_id, period, jam, path, type, status) "
                "VALUES(?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(game_id, path) DO UPDATE SET "
                "  period=excluded.period, jam=excluded.jam, "
                "  type=excluded.type, status=excluded.status",
                (clip.game_id, clip.period, clip.jam, clip.path, clip.type.value, clip.status.value),
            )

            # Track last seen jam for this period
            await self.kv_set(conn, last_jam_key(clip.period), str(clip.jam))
            await conn.commit()

            cur = await conn.execute("SELECT last_insert_rowid()")
            row = await cur.fetchone()
            clip_id = row[0] if row else 0
            log.info("clip.inserted", clip_id=clip_id, period=clip.period, jam=clip.jam)
            return clip_id

    async def get_armed_clip(
        self, game_id: str, period: int, jam: int
    ) -> ClipRow | None:
        """Get the most recently armed clip for a given jam."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT id, game_id, period, jam, created_at, path, type, status "
                "FROM clips "
                "WHERE game_id=? AND period=? AND jam=? AND type='highlight' AND status='armed' "
                "ORDER BY created_at DESC LIMIT 1",
                (game_id, period, jam),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return ClipRow(
                id=row[0],
                game_id=row[1],
                period=row[2],
                jam=row[3],
                created_at=row[4],
                path=row[5],
                type=row[6],
                status=row[7],
            )

    async def update_clip_status(self, clip_id: int, status: ClipStatus) -> None:
        async with self._db.connection() as conn:
            await conn.execute(
                "UPDATE clips SET status=? WHERE id=?", (status.value, clip_id)
            )
            await conn.commit()

    async def skip_stale_armed_clips(
        self, game_id: str, period: int, jam: int
    ) -> int:
        """Mark armed clips for OTHER jams as skipped (prevents leakage)."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "UPDATE clips SET status='skipped' "
                "WHERE game_id=? AND type='highlight' AND status='armed' "
                "AND NOT (period=? AND jam=?)",
                (game_id, period, jam),
            )
            await conn.commit()
            return cur.rowcount

    async def get_recent_clips(self, game_id: str, limit: int = 20) -> list[ClipRow]:
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT id, game_id, period, jam, created_at, path, type, status "
                "FROM clips WHERE game_id=? ORDER BY created_at DESC LIMIT ?",
                (game_id, limit),
            )
            rows = await cur.fetchall()
            return [
                ClipRow(
                    id=r[0], game_id=r[1], period=r[2], jam=r[3],
                    created_at=r[4], path=r[5], type=r[6], status=r[7],
                )
                for r in rows
            ]

    # --- KV Store ---

    async def kv_get(self, conn: object, key: str) -> str | None:
        """Get a value from the kv table. Accepts an aiosqlite Connection."""
        cur = await conn.execute("SELECT value FROM kv WHERE key = ?", (key,))  # type: ignore[union-attr]
        row = await cur.fetchone()
        return row[0] if row else None

    async def kv_set(self, conn: object, key: str, value: str) -> None:
        """Set a value in the kv table. Accepts an aiosqlite Connection."""
        await conn.execute(  # type: ignore[union-attr]
            "INSERT INTO kv(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    # --- Jam Reset Transaction ---

    async def consume_armed_clip(
        self, game_id: str, period: int, jam: int
    ) -> str | None:
        """Consume the armed clip for the given jam. Returns the play_path or None.

        This is a single transaction that:
        1. Finds the armed clip
        2. Guards against replaying the same file
        3. Updates status to played/skipped
        4. Skips armed clips from other jams
        """
        async with self._db.connection() as conn:
            await self.kv_set(conn, last_jam_key(period), str(jam))

            play_path: str | None = None

            if jam > 0:
                cur = await conn.execute(
                    "SELECT id, path FROM clips "
                    "WHERE game_id=? AND period=? AND jam=? "
                    "AND type='highlight' AND status='armed' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (game_id, period, jam),
                )
                row = await cur.fetchone()
                if row:
                    clip_id, candidate_path = row

                    last_played = await self.kv_get(conn, LAST_PLAYED_KV)
                    last_played = (last_played or "").strip()

                    # Guard: do not return the same replay twice (case-insensitive on Windows)
                    if last_played and os.path.normcase(last_played) == os.path.normcase(
                        candidate_path
                    ):
                        await conn.execute(
                            "UPDATE clips SET status='skipped' WHERE id=?", (clip_id,)
                        )
                    else:
                        await conn.execute(
                            "UPDATE clips SET status='played' WHERE id=?", (clip_id,)
                        )
                        await self.kv_set(conn, LAST_PLAYED_KV, candidate_path)
                        play_path = candidate_path

            # Skip armed clips from other jams
            await conn.execute(
                "UPDATE clips SET status='skipped' "
                "WHERE game_id=? AND type='highlight' AND status='armed' "
                "AND NOT (period=? AND jam=?)",
                (game_id, period, jam),
            )

            await conn.commit()
            return play_path
