"""Overlay source group management: toggle, display-only, auto-hide."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

from nwsc.integrations.obs.client import GroupItem, OBSClient

log = structlog.get_logger()


@dataclass
class OverlaySource:
    name: str
    enabled: bool
    item_id: int


class OverlayService:
    """Manages OBS source group overlays with display-only and auto-hide support."""

    def __init__(self, obs: OBSClient, allowed_groups: list[str] | None = None) -> None:
        self._obs = obs
        self._allowed_groups = set(allowed_groups) if allowed_groups else None
        self._auto_hide_tasks: dict[str, asyncio.Task[None]] = {}

    def _validate_group(self, group_name: str) -> None:
        if self._allowed_groups is not None and group_name not in self._allowed_groups:
            raise ValueError(
                f"Unknown overlay group: {group_name!r}. "
                f"Configured groups: {sorted(self._allowed_groups)}"
            )

    def _to_overlay_source(self, item: GroupItem) -> OverlaySource:
        return OverlaySource(name=item.name, enabled=item.enabled, item_id=item.item_id)

    def list_sources(self, group_name: str) -> list[OverlaySource]:
        """List all sources in an OBS group with their current visibility."""
        self._validate_group(group_name)
        items = self._obs.get_group_items(group_name)
        return [self._to_overlay_source(item) for item in items]

    def toggle(self, group_name: str, source_name: str, enabled: bool) -> OverlaySource:
        """Toggle a single source's visibility within a group."""
        self._validate_group(group_name)
        item_id = self._obs.get_item_id(group_name, source_name)
        self._obs.set_item_enabled(group_name, item_id, enabled)
        log.info("overlay.toggled", group=group_name, source=source_name, enabled=enabled)
        return OverlaySource(name=source_name, enabled=enabled, item_id=item_id)

    def display_only(
        self,
        group_name: str,
        source_name: str,
        timeout_s: float | None = None,
    ) -> OverlaySource:
        """Show one source and hide all others in the group.

        If timeout_s is provided, schedules auto-hide after the timeout.
        Repeated calls cancel the previous timer for that group+source.
        """
        self._validate_group(group_name)

        items = self._obs.get_group_items(group_name)
        target_item: GroupItem | None = None

        for item in items:
            if item.name == source_name:
                target_item = item
                if not item.enabled:
                    self._obs.set_item_enabled(group_name, item.item_id, True)
            else:
                if item.enabled:
                    self._obs.set_item_enabled(group_name, item.item_id, False)

        if target_item is None:
            raise ValueError(
                f"Source {source_name!r} not found in group {group_name!r}. "
                f"Available: {[i.name for i in items]}"
            )

        # Cancel any existing auto-hide for this group+source
        task_key = f"{group_name}:{source_name}"
        self._cancel_auto_hide(task_key)

        if timeout_s is not None and timeout_s > 0:
            self._schedule_auto_hide(group_name, source_name, target_item.item_id, timeout_s)

        log.info(
            "overlay.display_only",
            group=group_name,
            source=source_name,
            timeout_s=timeout_s,
        )
        return OverlaySource(name=source_name, enabled=True, item_id=target_item.item_id)

    def hide_all(self, group_name: str) -> list[OverlaySource]:
        """Hide all sources in a group."""
        self._validate_group(group_name)

        items = self._obs.get_group_items(group_name)
        results = []
        for item in items:
            if item.enabled:
                self._obs.set_item_enabled(group_name, item.item_id, False)
            results.append(OverlaySource(name=item.name, enabled=False, item_id=item.item_id))

        # Cancel any pending auto-hide tasks for this group
        keys_to_cancel = [k for k in self._auto_hide_tasks if k.startswith(f"{group_name}:")]
        for key in keys_to_cancel:
            self._cancel_auto_hide(key)

        log.info("overlay.hide_all", group=group_name, count=len(results))
        return results

    # --- Auto-hide scheduling ---

    def _schedule_auto_hide(
        self, group_name: str, source_name: str, item_id: int, delay_s: float
    ) -> None:
        task_key = f"{group_name}:{source_name}"
        self._auto_hide_tasks[task_key] = asyncio.create_task(
            self._auto_hide(group_name, source_name, item_id, delay_s, task_key)
        )

    def _cancel_auto_hide(self, task_key: str) -> None:
        task = self._auto_hide_tasks.pop(task_key, None)
        if task and not task.done():
            task.cancel()

    async def _auto_hide(
        self,
        group_name: str,
        source_name: str,
        item_id: int,
        delay_s: float,
        task_key: str,
    ) -> None:
        try:
            await asyncio.sleep(delay_s)
            self._obs.set_item_enabled(group_name, item_id, False)
            log.info("overlay.auto_hidden", group=group_name, source=source_name)
        except asyncio.CancelledError:
            log.debug("overlay.auto_hide_cancelled", group=group_name, source=source_name)
        except Exception as e:
            log.warning("overlay.auto_hide_failed", group=group_name, source=source_name, error=str(e))
        finally:
            self._auto_hide_tasks.pop(task_key, None)
