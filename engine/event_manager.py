"""Event loading and scheduling for ambient scene actions."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import pygame

from engine.timer import SessionTimer


@dataclass
class SceneEvent:
    """Data model for a single timed ambient event."""

    name: str
    weight: int
    cooldown: float
    min_runtime: float
    duration: float
    color: tuple[int, int, int]


class EventManager:
    """Controls weighted event selection and active event lifecycle."""

    def __init__(self, event_file: str) -> None:
        self.events = self._load_events(event_file)
        self.active_event: SceneEvent | None = None
        self.active_time = 0.0

    def _load_events(self, event_file: str) -> list[SceneEvent]:
        """Load event definitions from JSON configuration."""
        data = json.loads(Path(event_file).read_text(encoding="utf-8"))
        loaded_events: list[SceneEvent] = []
        for entry in data.get("events", []):
            loaded_events.append(
                SceneEvent(
                    name=entry["name"],
                    weight=int(entry["weight"]),
                    cooldown=float(entry["cooldown"]),
                    min_runtime=float(entry["min_runtime"]),
                    duration=float(entry["duration"]),
                    color=tuple(entry["color"]),
                )
            )
        return loaded_events

    def _eligible_events(self, timer: SessionTimer) -> list[SceneEvent]:
        """Return events that satisfy runtime and cooldown requirements."""
        eligible: list[SceneEvent] = []
        for event in self.events:
            if timer.session_time < event.min_runtime:
                continue
            if timer.time_since_last_event < event.cooldown:
                continue
            eligible.append(event)
        return eligible

    def activate(self, timer: SessionTimer) -> None:
        """Activate one weighted random event if none is running."""
        if self.active_event is not None:
            return

        eligible = self._eligible_events(timer)
        if not eligible:
            return

        weights = [event.weight for event in eligible]
        self.active_event = random.choices(eligible, weights=weights, k=1)[0]
        self.active_time = 0.0
        timer.mark_event_triggered()

    def update(self, delta_time: float, timer: SessionTimer) -> None:
        """Update active event duration and schedule the next one."""
        if self.active_event is None:
            self.activate(timer)
            return

        self.active_time += delta_time
        if self.active_time >= self.active_event.duration:
            self.active_event = None
            self.active_time = 0.0

    def render(self, surface: pygame.Surface) -> None:
        """Render a subtle sky band to represent the current active event."""
        if self.active_event is None:
            return

        band_height = 8
        overlay = pygame.Rect(0, 6, surface.get_width(), band_height)
        pygame.draw.rect(surface, self.active_event.color, overlay)
