"""OBS Studio integration via obsws-python WebSocket client."""

from __future__ import annotations

import time
from dataclasses import dataclass

import structlog
from obsws_python import ReqClient

from nwsc.config import OBSConfig
from nwsc.integrations.base import HealthStatus

log = structlog.get_logger()


@dataclass
class GroupItem:
    name: str
    item_id: int
    enabled: bool


@dataclass
class MediaStatus:
    state: str
    duration_ms: float | None
    cursor_ms: float | None


class OBSClient:
    """Wraps obsws-python with per-call connections and retry logic.

    Per-request connections avoid stale-connection bugs when OBS restarts.
    """

    def __init__(self, config: OBSConfig) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "obs"

    def _connect(self) -> ReqClient:
        return ReqClient(
            host=self._config.host,
            port=self._config.port,
            password=self._config.password,
            timeout=self._config.timeout_s,
        )

    async def health_check(self) -> HealthStatus:
        start = time.monotonic()
        try:
            c = self._connect()
            scene = c.get_current_program_scene()
            latency = (time.monotonic() - start) * 1000
            return HealthStatus(
                healthy=True,
                latency_ms=latency,
                detail=f"scene={scene.current_program_scene_name}",
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return HealthStatus(healthy=False, latency_ms=latency, detail=str(e))

    def get_current_scene(self) -> str:
        """Return the current program scene name."""
        c = self._connect()
        scene = c.get_current_program_scene()
        return scene.current_program_scene_name

    def set_scene(self, scene_name: str) -> str:
        """Set program scene, sync preview if studio mode is active. Returns actual scene."""
        c = self._connect()
        c.set_current_program_scene(scene_name)

        try:
            if c.get_studio_mode_enabled().studio_mode_enabled:
                c.set_current_preview_scene(scene_name)
        except Exception:
            pass

        actual = c.get_current_program_scene()
        log.info("obs.scene_set", requested=scene_name, actual=actual.current_program_scene_name)
        return actual.current_program_scene_name

    def transition_to_scene(
        self,
        scene_name: str,
        transition_name: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Set transition settings then switch scene."""
        t_name = transition_name if transition_name is not None else self._config.transition.name
        t_dur = duration_ms if duration_ms is not None else self._config.transition.duration_ms

        c = self._connect()
        try:
            c.set_current_scene_transition(t_name)
            c.set_current_scene_transition_duration(t_dur)
        except Exception:
            pass

        c.set_current_program_scene(scene_name)
        try:
            if c.get_studio_mode_enabled().studio_mode_enabled:
                c.set_current_preview_scene(scene_name)
        except Exception:
            pass

        log.info("obs.transitioned", scene=scene_name, transition=t_name, duration_ms=t_dur)

    def save_replay_buffer(self) -> None:
        """Tell OBS to save the current replay buffer."""
        c = self._connect()
        c.save_replay_buffer()
        log.info("obs.replay_buffer_saved")

    def load_and_play_media(self, file_path: str, input_name: str | None = None) -> None:
        """Load a file into the media source and restart playback."""
        media = input_name or self._config.media_input_name
        c = self._connect()
        c.set_input_settings(
            name=media,
            settings={"local_file": file_path},
            overlay=True,
        )
        c.trigger_media_input_action(
            media, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"
        )
        log.info("obs.media_started", input=media, path=file_path)

    def get_media_status(self, input_name: str | None = None) -> MediaStatus:
        """Get playback status of the media source."""
        media = input_name or self._config.media_input_name
        c = self._connect()
        status = c.get_media_input_status(media)

        media_state = getattr(status, "media_state", None) or getattr(
            status, "mediaState", ""
        )
        duration = getattr(status, "media_duration", None) or getattr(
            status, "mediaDuration", None
        )
        cursor = getattr(status, "media_cursor", None) or getattr(
            status, "mediaCursor", None
        )

        return MediaStatus(
            state=str(media_state),
            duration_ms=duration,
            cursor_ms=cursor,
        )

    # --- Group / overlay source methods ---

    def get_group_items(self, group_name: str) -> list[GroupItem]:
        """Get all items (sources) inside an OBS group/folder."""
        c = self._connect()
        result = c.get_group_scene_item_list(group_name)
        items = []
        for item in result.scene_items:
            items.append(
                GroupItem(
                    name=item.get("sourceName", ""),
                    item_id=item.get("sceneItemId", 0),
                    enabled=item.get("sceneItemEnabled", False),
                )
            )
        return items

    def set_item_enabled(self, scene_or_group: str, item_id: int, enabled: bool) -> None:
        """Set visibility of a scene item by its ID."""
        c = self._connect()
        c.set_scene_item_enabled(scene_or_group, item_id, enabled)
        log.debug("obs.item_enabled_set", scene=scene_or_group, item_id=item_id, enabled=enabled)

    def get_item_id(self, scene_or_group: str, source_name: str) -> int:
        """Look up a scene item's ID by source name."""
        c = self._connect()
        result = c.get_scene_item_id(scene_or_group, source_name)
        return result.scene_item_id
