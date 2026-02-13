"""Event loading and scheduling for ambient scene actions."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pygame

from engine.timer import SessionTimer

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SceneEvent:
    """Data model for a single timed ambient event."""

    name: str
    weight: int
    cooldown: float
    min_runtime: float
    duration: float
    color: tuple[int, int, int]


class EventManager:
    """Control weighted event selection and active event lifecycle.

    At most one event can be active at once. Event cooldown and activation gates
    are evaluated against absolute session time from :class:`SessionTimer`.
    """

    def __init__(self, event_file: str) -> None:
        self.events = self._load_events(event_file)
        self.active_event: SceneEvent | None = None
        self._active_event_end_time = 0.0

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

    def _parse_event_entry(self, entry: Any, index: int) -> SceneEvent | None:
        """Convert a raw JSON entry into a validated :class:`SceneEvent`."""
        if not isinstance(entry, dict):
            LOGGER.warning("Skipping event[%d]: entry is not an object", index)
            return None

        try:
            name = str(entry["name"])
            weight = int(entry["weight"])
            cooldown = float(entry["cooldown"])
            min_runtime = float(entry["min_runtime"])
            duration = float(entry["duration"])
            color_raw = entry["color"]
        except (KeyError, TypeError, ValueError) as error:
            LOGGER.warning("Skipping event[%d]: invalid schema (%s)", index, error)
            return None

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
            weight=weight,
            cooldown=cooldown,
            min_runtime=min_runtime,
            duration=duration,
            color=color,
        )

    def _eligible_events(self, timer: SessionTimer) -> list[SceneEvent]:
        """Return events that satisfy runtime and cooldown requirements."""
        return [
            event
            for event in self.events
            if timer.has_reached_runtime(event.min_runtime)
            and timer.time_since_last_event >= event.cooldown
        ]

    def activate(self, timer: SessionTimer) -> None:
        """Activate one weighted random event if no event is currently active."""
        if self.active_event is not None:
            return

        eligible = self._eligible_events(timer)
        if not eligible:
            return

        weights = [event.weight for event in eligible]
        self.active_event = random.choices(eligible, weights=weights, k=1)[0]
        self._active_event_end_time = timer.session_time + self.active_event.duration
        timer.mark_event_triggered()

    def update(self, _delta_time: float, timer: SessionTimer) -> None:
        """Update active event state and schedule the next event when idle."""
        if self.active_event is None:
            self.activate(timer)
            return

        if timer.session_time >= self._active_event_end_time:
            self.active_event = None
            self._active_event_end_time = 0.0

    def render(self, surface: pygame.Surface) -> None:
        """Render a subtle sky band to represent the current active event."""
        if self.active_event is None:
            return

        pygame.draw.rect(surface, self.active_event.color, pygame.Rect(0, 6, surface.get_width(), 8))
