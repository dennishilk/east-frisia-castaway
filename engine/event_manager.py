"""Event loading and scheduling for ambient scene actions."""

from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pygame

from engine.timer import SessionTimer

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventPhase:
    """Single phase definition for multi-step events."""

    phase_type: str
    duration: float


@dataclass(frozen=True)
class SceneEvent:
    """Data model for a single timed ambient event."""

    name: str
    event_type: str
    weight: int
    cooldown: float
    min_runtime: float
    duration: float
    color: tuple[int, int, int]
    phases: tuple[EventPhase, ...]
    conditions: dict[str, tuple[str, ...]]


class EventManager:
    """Control weighted event selection and active event lifecycle.

    At most one event can be active at once. Event cooldown and activation gates
    are evaluated against absolute session time from :class:`SessionTimer`.
    """

    def __init__(self, event_file: str) -> None:
        self.events = self._load_events(event_file)
        self.active_event: SceneEvent | None = None
        self._active_event_start_time = 0.0
        self._active_event_end_time = 0.0
        self._phase_timestamps: list[tuple[EventPhase, float, float]] = []
        self._font: pygame.font.Font | None = None
        self._current_session_time = 0.0

    def _load_events(self, event_file: str) -> list[SceneEvent]:
        """Load and validate event definitions from JSON configuration."""
        raw_data = json.loads(Path(event_file).read_text(encoding="utf-8"))
        raw_events = raw_data.get("events", [])
        if not isinstance(raw_events, list):
            LOGGER.warning("Ignoring malformed event list in %s", event_file)
            return []

        loaded_events: list[SceneEvent] = []
        for index, entry in enumerate(raw_events):
            event = self._parse_event_entry(entry, index)
            if event is not None:
                loaded_events.append(event)

        return loaded_events

    def _parse_phases(self, entry: dict[str, Any], index: int) -> tuple[tuple[EventPhase, ...], float] | None:
        phases_raw = entry.get("phases")
        if phases_raw is None:
            try:
                duration = float(entry["duration"])
            except (KeyError, TypeError, ValueError):
                LOGGER.warning("Skipping event[%d]: missing duration", index)
                return None
            if duration <= 0.0:
                LOGGER.warning("Skipping event[%d]: duration must be > 0", index)
                return None
            return (), duration

        if not isinstance(phases_raw, list) or not phases_raw:
            LOGGER.warning("Skipping event[%d]: phases must be a non-empty list", index)
            return None

        phases: list[EventPhase] = []
        total_duration = 0.0
        for phase_index, phase_entry in enumerate(phases_raw):
            if not isinstance(phase_entry, dict):
                LOGGER.warning("Skipping event[%d]: invalid phase[%d]", index, phase_index)
                return None
            try:
                phase_type = str(phase_entry["type"])
                phase_duration = float(phase_entry["duration"])
            except (KeyError, TypeError, ValueError):
                LOGGER.warning("Skipping event[%d]: malformed phase[%d]", index, phase_index)
                return None
            if phase_duration <= 0.0:
                LOGGER.warning("Skipping event[%d]: phase[%d] duration must be > 0", index, phase_index)
                return None
            total_duration += phase_duration
            phases.append(EventPhase(phase_type=phase_type, duration=phase_duration))

        return tuple(phases), total_duration

    def _parse_conditions(self, entry: dict[str, Any], index: int) -> dict[str, tuple[str, ...]]:
        conditions_raw = entry.get("conditions", {})
        if not isinstance(conditions_raw, dict):
            LOGGER.warning("Ignoring conditions for event[%d]: expected object", index)
            return {}

        conditions: dict[str, tuple[str, ...]] = {}
        for key, value in conditions_raw.items():
            if isinstance(value, list) and all(isinstance(item, str) for item in value) and value:
                conditions[str(key)] = tuple(value)
            else:
                LOGGER.warning("Ignoring malformed condition %s for event[%d]", key, index)
        return conditions

    def _parse_event_entry(self, entry: Any, index: int) -> SceneEvent | None:
        """Convert a raw JSON entry into a validated :class:`SceneEvent`."""
        if not isinstance(entry, dict):
            LOGGER.warning("Skipping event[%d]: entry is not an object", index)
            return None

        try:
            name = str(entry.get("id", entry.get("name")))
            event_type = str(entry.get("type", "ambient"))
            weight = int(entry["weight"])
            cooldown = float(entry["cooldown"])
            min_runtime = float(entry["min_runtime"])
            color_raw = entry.get("color", [100, 116, 132])
        except (TypeError, ValueError, KeyError) as error:
            LOGGER.warning("Skipping event[%d]: invalid schema (%s)", index, error)
            return None

        if not name or name == "None":
            LOGGER.warning("Skipping event[%d]: missing id/name", index)
            return None

        phase_parse = self._parse_phases(entry, index)
        if phase_parse is None:
            return None
        phases, duration = phase_parse

        if weight <= 0 or cooldown < 0.0 or min_runtime < 0.0 or duration <= 0.0:
            LOGGER.warning("Skipping event[%d]: invalid numeric ranges", index)
            return None

        if (
            not isinstance(color_raw, list)
            or len(color_raw) != 3
            or any(not isinstance(channel, (int, float)) for channel in color_raw)
        ):
            LOGGER.warning("Skipping event[%d]: color must be a 3-item numeric list", index)
            return None

        color = tuple(max(0, min(255, int(channel))) for channel in color_raw)
        return SceneEvent(
            name=name,
            event_type=event_type,
            weight=weight,
            cooldown=cooldown,
            min_runtime=min_runtime,
            duration=duration,
            color=color,
            phases=phases,
            conditions=self._parse_conditions(entry, index),
        )

    def _matches_conditions(self, event: SceneEvent, environment: dict[str, str] | None) -> bool:
        if not event.conditions:
            return True
        if environment is None:
            return False

        for key, allowed in event.conditions.items():
            current = environment.get(key)
            if current not in allowed:
                return False
        return True

    def _eligible_events(self, timer: SessionTimer, environment: dict[str, str] | None) -> list[SceneEvent]:
        """Return events that satisfy runtime, cooldown, and conditions."""
        return [
            event
            for event in self.events
            if timer.has_reached_runtime(event.min_runtime)
            and timer.time_since_last_event >= event.cooldown
            and self._matches_conditions(event, environment)
        ]

    def _build_phase_timestamps(self, event: SceneEvent, start_time: float) -> None:
        self._phase_timestamps = []
        cursor = start_time
        for phase in event.phases:
            phase_start = cursor
            phase_end = cursor + phase.duration
            self._phase_timestamps.append((phase, phase_start, phase_end))
            cursor = phase_end

    def get_current_phase(self, session_time: float) -> EventPhase | None:
        """Return active phase for the current event using absolute timestamps."""
        for phase, start, end in self._phase_timestamps:
            if start <= session_time < end:
                return phase

        if self._phase_timestamps and session_time >= self._phase_timestamps[-1][2]:
            return self._phase_timestamps[-1][0]
        return None

    def activate(self, timer: SessionTimer, environment: dict[str, str] | None = None) -> None:
        """Activate one weighted random event if no event is currently active."""
        if self.active_event is not None:
            return

        eligible = self._eligible_events(timer, environment)
        if not eligible:
            return

        weights = [event.weight for event in eligible]
        self.active_event = random.choices(eligible, weights=weights, k=1)[0]
        self._active_event_start_time = timer.session_time
        self._active_event_end_time = timer.session_time + self.active_event.duration
        self._build_phase_timestamps(self.active_event, timer.session_time)
        timer.mark_event_triggered()

    def update(
        self,
        _delta_time: float,
        timer: SessionTimer,
        environment: dict[str, str] | None = None,
    ) -> None:
        """Update active event state and schedule the next event when idle."""
        self._current_session_time = timer.session_time

        if self.active_event is None:
            self.activate(timer, environment)
            return

        if timer.session_time >= self._active_event_end_time:
            self.active_event = None
            self._active_event_start_time = 0.0
            self._active_event_end_time = 0.0
            self._phase_timestamps = []

    def _ensure_font(self) -> pygame.font.Font | None:
        if not pygame.font.get_init():
            return None
        if self._font is None:
            self._font = pygame.font.Font(None, 12)
        return self._font

    def _render_borkum_buoy(self, surface: pygame.Surface) -> None:
        if self.active_event is None:
            return

        now = max(self._active_event_start_time, min(self._active_event_end_time, self._current_session_time))
        elapsed = now - self._active_event_start_time
        progress = elapsed / self.active_event.duration if self.active_event.duration > 0 else 1.0

        x = int(-24 + (surface.get_width() + 48) * progress)
        bob = int(round(math.sin(elapsed * 1.6) * 2.0))
        y = surface.get_height() // 2 + 44 + bob

        alpha = 180
        phase = self.get_current_phase(self._active_event_start_time + elapsed)
        if phase is not None:
            if phase.phase_type == "approach":
                phase_duration = max(0.01, phase.duration)
                alpha = int(70 + 110 * min(1.0, elapsed / phase_duration))
            elif phase.phase_type == "fade":
                remaining = max(0.0, self._active_event_end_time - (self._active_event_start_time + elapsed))
                phase_duration = max(0.01, phase.duration)
                alpha = int(180 * min(1.0, remaining / phase_duration))

        buoy_layer = pygame.Surface((40, 16), pygame.SRCALPHA)
        pygame.draw.rect(buoy_layer, (176, 72, 48, alpha), pygame.Rect(4, 6, 10, 7))
        pygame.draw.rect(buoy_layer, (190, 188, 180, alpha), pygame.Rect(8, 1, 2, 5))

        font = self._ensure_font()
        if font is not None:
            label = font.render("Borkum", True, (225, 215, 184))
            buoy_layer.blit(label, (14, 5))

        surface.blit(buoy_layer, (x, y))

    def render(self, surface: pygame.Surface) -> None:
        """Render active event visuals."""
        if self.active_event is None:
            return

        if self.active_event.name == "borkum_buoy":
            self._render_borkum_buoy(surface)
            return

        pygame.draw.rect(surface, self.active_event.color, pygame.Rect(0, 6, surface.get_width(), 8))
