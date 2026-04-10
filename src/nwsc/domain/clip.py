"""Clip/highlight domain logic: arm and consume replay highlights."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from nwsc.db.models import ClipCreate
from nwsc.db.repository import Repository
from nwsc.integrations.scoreboard.client import ScoreboardClient
from nwsc.services.replay_file import ReplayFileService

log = structlog.get_logger()


@dataclass
class ArmResult:
    game_id: str
    period: int
    jam: int
    path: str


@dataclass
class ConsumeResult:
    current_period: int
    current_jam: int
    play_path: str | None


class ClipService:
    """Manages clip arming and consumption for replay highlights."""

    def __init__(
        self,
        repo: Repository,
        scoreboard: ScoreboardClient,
        replay_file_svc: ReplayFileService,
    ) -> None:
        self._repo = repo
        self._scoreboard = scoreboard
        self._replay_file = replay_file_svc

    async def arm_latest(self, game_id: str) -> ArmResult:
        """Arm the newest replay file as a highlight for the current jam.

        Finds the newest replay file, waits for it to stabilize,
        tags it with the current period/jam from the scoreboard,
        and marks it as armed in the database.
        """
        replay_dir = self._replay_file.resolve_replay_dir()
        latest = self._replay_file.newest_replay_file(replay_dir)
        if latest is None:
            raise FileNotFoundError(f"No replay files found in {replay_dir}")

        await self._replay_file.wait_for_stable(latest)

        state = await self._scoreboard.get_state()

        clip = ClipCreate(
            game_id=game_id,
            period=state.period,
            jam=state.jam,
            path=str(latest),
        )
        await self._repo.insert_clip(clip)

        log.info("clip.armed", period=state.period, jam=state.jam, path=str(latest))
        return ArmResult(
            game_id=game_id,
            period=state.period,
            jam=state.jam,
            path=str(latest),
        )

    async def consume_for_jam(self, game_id: str) -> ConsumeResult:
        """Consume the armed clip for the current jam.

        Returns the play_path if a replay is available, or None.
        Also skips armed clips from other jams to prevent leakage.
        """
        state = await self._scoreboard.get_state()

        play_path = await self._repo.consume_armed_clip(
            game_id, state.period, state.jam
        )

        if play_path:
            log.info("clip.consumed", period=state.period, jam=state.jam, path=play_path)
        else:
            log.info("clip.none_to_consume", period=state.period, jam=state.jam)

        return ConsumeResult(
            current_period=state.period,
            current_jam=state.jam,
            play_path=play_path,
        )
