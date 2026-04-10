"""Jam cycle orchestration: coordinates OBS, PTZ, and clips for jam transitions."""

from __future__ import annotations

import asyncio

import structlog

from nwsc.config import AppConfig
from nwsc.db.models import ArmResponse, JamResetResponse
from nwsc.domain.bout import BoutService
from nwsc.domain.clip import ClipService
from nwsc.integrations.obs.client import OBSClient
from nwsc.integrations.ptz.client import PTZClient

log = structlog.get_logger()


class JamCycleOrchestrator:
    """Orchestrates the multi-step workflows for jam transitions.

    Key workflows:
    - save_and_arm: Save OBS replay buffer + arm the clip
    - jam_reset: Consume replay metadata, switch to cam1, reset PTZ
    - jam_reset_and_play: Same as jam_reset but plays the replay first
    """

    def __init__(
        self,
        obs: OBSClient,
        ptz: PTZClient,
        bout_svc: BoutService,
        clip_svc: ClipService,
        config: AppConfig,
    ) -> None:
        self._obs = obs
        self._ptz = ptz
        self._bout = bout_svc
        self._clip = clip_svc
        self._config = config
        self._delayed_switch_task: asyncio.Task[None] | None = None

    async def save_and_arm(self) -> ArmResponse:
        """Save the OBS replay buffer and arm the clip."""
        game_id = await self._bout.require_current_game()

        self._obs.save_replay_buffer()
        await asyncio.sleep(0.5)  # Give OBS time to write the file

        result = await self._clip.arm_latest(game_id)
        return ArmResponse(
            game_id=result.game_id,
            period=result.period,
            jam=result.jam,
            path=result.path,
        )

    async def jam_reset(self) -> JamResetResponse:
        """Jam reset without replay: switch to cam1 and reset PTZ cameras."""
        game_id = await self._bout.require_current_game()

        result = await self._clip.consume_for_jam(game_id)

        cam1 = self._config.obs.scenes.cam1
        self._obs.set_scene(cam1)

        # Reset PTZ cameras (fire and forget)
        preset = self._config.ptz.jam_start_preset
        try:
            await self._ptz.call_preset_all(preset)
        except Exception as e:
            log.warning("jam_reset.ptz_failed", error=str(e))

        return JamResetResponse(
            current_period=result.current_period,
            current_jam=result.current_jam,
            previous_period=result.current_period,
            previous_jam=result.current_jam,
            play_path=result.play_path,
        )

    async def jam_reset_and_play(self) -> JamResetResponse:
        """Jam reset with replay: play the highlight, then switch back to cam1.

        Orchestration:
        1. Consume the armed clip for the current jam
        2. If replay exists:
           - Switch to REPLAY scene
           - Call PTZ preset (hidden behind replay)
           - Load and play the replay media
           - Schedule delayed switch back to cam1
        3. If no replay:
           - Switch to safe/bumper scene
           - Call PTZ preset
           - Schedule delayed switch back to cam1
        """
        game_id = await self._bout.require_current_game()

        result = await self._clip.consume_for_jam(game_id)

        cam1 = self._config.obs.scenes.cam1
        replay_scene = self._config.obs.scenes.replay
        safe_scene = self._config.obs.scenes.safe
        preset = self._config.ptz.jam_start_preset

        if result.play_path:
            # Replay exists: cut to replay scene
            self._obs.set_scene(replay_scene)

            # PTZ movement hidden behind replay
            try:
                await self._ptz.call_preset_all(preset)
            except Exception as e:
                log.warning("jam_reset_and_play.ptz_failed", error=str(e))

            # Load and play the replay
            self._obs.load_and_play_media(result.play_path)

            # Schedule switch back to cam1 after replay finishes
            delay = self._config.obs.replay_length_s + self._config.obs.replay_pad_s
            self._schedule_delayed_switch(cam1, delay)

            log.info(
                "jam_reset_and_play.replay_started",
                path=result.play_path,
                switch_back_in=delay,
            )
        else:
            # No replay: go to safe scene while PTZ moves
            self._obs.set_scene(safe_scene)

            try:
                await self._ptz.call_preset_all(preset)
            except Exception as e:
                log.warning("jam_reset_and_play.ptz_failed", error=str(e))

            # Switch back to cam1 after PTZ settles
            self._schedule_delayed_switch(cam1, self._config.ptz.settle_s)

            log.info("jam_reset_and_play.no_replay", switch_back_in=self._config.ptz.settle_s)

        return JamResetResponse(
            current_period=result.current_period,
            current_jam=result.current_jam,
            previous_period=result.current_period,
            previous_jam=result.current_jam,
            play_path=result.play_path,
        )

    def _schedule_delayed_switch(self, scene: str, delay_s: float) -> None:
        """Schedule a delayed scene switch, cancelling any pending one."""
        if self._delayed_switch_task and not self._delayed_switch_task.done():
            self._delayed_switch_task.cancel()

        self._delayed_switch_task = asyncio.create_task(
            self._delayed_switch(scene, delay_s)
        )

    async def _delayed_switch(self, scene: str, delay_s: float) -> None:
        """Wait then switch OBS scene."""
        try:
            await asyncio.sleep(max(0.0, delay_s))
            self._obs.set_scene(scene)
            log.info("jam_cycle.delayed_switch_complete", scene=scene)
        except asyncio.CancelledError:
            log.debug("jam_cycle.delayed_switch_cancelled", scene=scene)
        except Exception as e:
            log.error("jam_cycle.delayed_switch_failed", scene=scene, error=str(e))
