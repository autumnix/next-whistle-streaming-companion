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
        """Save the OBS replay buffer, load the clip into REPLAY_MEDIA (hidden)."""
        game_id = self._bout.require_current_game()
        await self._bout.ensure_game_row(game_id)

        # Snapshot existing files so we can detect the new one
        replay_dir = self._clip._replay_file.resolve_replay_dir()
        old_newest = self._clip._replay_file.newest_replay_file(replay_dir)

        self._obs.save_replay_buffer()

        # Wait for a new file to appear (not the one that was already there)
        new_file = await self._clip._replay_file.wait_for_new_file(
            replay_dir, old_newest
        )
        log.info("save_and_arm.new_file_detected", path=str(new_file))

        result = await self._clip.arm_file(game_id, new_file)

        # Load into REPLAY_MEDIA (hidden) so it's ready for jam-reset-and-play
        replay_scene = self._config.obs.scenes.replay
        self._obs.load_media(result.path, scene_name=replay_scene)

        return ArmResponse(
            game_id=result.game_id,
            period=result.period,
            jam=result.jam,
            path=result.path,
        )

    async def jam_reset(self) -> JamResetResponse:
        """Jam reset without replay: switch to cam1 and reset PTZ cameras.

        OBS and PTZ happen first so the camera operator is never blocked.
        Game and clip consumption are best-effort afterward.
        """
        # 1) OBS + PTZ first — nothing blocks these
        cam1 = self._config.obs.scenes.cam1
        self._obs.set_scene(cam1)

        preset = self._config.ptz.jam_start_preset
        try:
            await self._ptz.call_preset_all(preset)
        except Exception as e:
            log.warning("jam_reset.ptz_failed", error=str(e))

        # 2) Clip metadata — best-effort, does not block the operator
        result = None
        try:
            game_id = self._bout.get_current_game_id()
            if game_id:
                await self._bout.ensure_game_row(game_id)
                result = await self._clip.consume_for_jam(game_id)
            else:
                log.info("jam_reset.no_active_game")
        except Exception as e:
            log.warning("jam_reset.clip_consume_failed", error=str(e))

        return JamResetResponse(
            current_period=result.current_period if result else 0,
            current_jam=result.current_jam if result else 0,
            previous_period=result.current_period if result else 0,
            previous_jam=result.current_jam if result else 0,
            play_path=result.play_path if result else None,
        )

    async def jam_reset_and_play(self) -> JamResetResponse:
        """Jam reset with replay: show and play the armed clip, then switch back.

        The clip was already loaded into REPLAY_MEDIA (hidden) by save_and_arm.
        This just shows it, plays it, and after the delay hides + unloads it.
        """
        cam1 = self._config.obs.scenes.cam1
        replay_scene = self._config.obs.scenes.replay
        safe_scene = self._config.obs.scenes.safe
        preset = self._config.ptz.jam_start_preset

        has_replay = self._obs.has_media_loaded()

        if has_replay:
            # Replay is armed: cut to replay scene, show and play
            self._obs.set_scene(replay_scene)

            # PTZ movement hidden behind replay
            try:
                await self._ptz.call_preset_all(preset)
            except Exception as e:
                log.warning("jam_reset_and_play.ptz_failed", error=str(e))

            self._obs.show_and_play_media(replay_scene)

            # Schedule switch back to cam1; hide + unload after
            delay = self._config.obs.replay_length_s + self._config.obs.replay_pad_s
            self._schedule_delayed_switch(cam1, delay, unload_media_scene=replay_scene)

            log.info("jam_reset_and_play.replay_started", switch_back_in=delay)
        else:
            # No replay armed: go to safe scene while PTZ moves
            self._obs.set_scene(safe_scene)

            try:
                await self._ptz.call_preset_all(preset)
            except Exception as e:
                log.warning("jam_reset_and_play.ptz_failed", error=str(e))

            self._schedule_delayed_switch(cam1, self._config.ptz.settle_s)

            log.info("jam_reset_and_play.no_replay", switch_back_in=self._config.ptz.settle_s)

        # Get scoreboard state for the response
        try:
            state = await self._clip._scoreboard.get_state_or_last()
            period, jam = state.period, state.jam
        except Exception:
            period, jam = 0, 0

        return JamResetResponse(
            current_period=period,
            current_jam=jam,
            previous_period=period,
            previous_jam=jam,
            play_path="(armed)" if has_replay else None,
        )

    def _schedule_delayed_switch(
        self, scene: str, delay_s: float, unload_media_scene: str | None = None
    ) -> None:
        """Schedule a delayed scene switch, cancelling any pending one."""
        if self._delayed_switch_task and not self._delayed_switch_task.done():
            self._delayed_switch_task.cancel()

        self._delayed_switch_task = asyncio.create_task(
            self._delayed_switch(scene, delay_s, unload_media_scene)
        )

    async def _delayed_switch(
        self, scene: str, delay_s: float, unload_media_scene: str | None = None
    ) -> None:
        """Wait, switch OBS scene, then hide + unload the media source."""
        try:
            await asyncio.sleep(max(0.0, delay_s))
            self._obs.set_scene(scene)
            if unload_media_scene:
                self._obs.hide_and_unload_media(unload_media_scene)
            log.info("jam_cycle.delayed_switch_complete", scene=scene)
        except asyncio.CancelledError:
            log.debug("jam_cycle.delayed_switch_cancelled", scene=scene)
        except Exception as e:
            log.error("jam_cycle.delayed_switch_failed", scene=scene, error=str(e))
