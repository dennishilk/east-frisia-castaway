"""Slow weather transitions for a restrained atmospheric layer."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class WeatherSystem:
    """Manage long-form transitions between clear and cloudy states."""

    min_transition_seconds: float = 120.0
    max_transition_seconds: float = 300.0
    min_hold_seconds: float = 120.0
    max_hold_seconds: float = 300.0
    _current_weather: str = field(default="clear", init=False)
    _target_weather: str = field(default="clear", init=False)
    _transition_start: float = field(default=0.0, init=False)
    _transition_end: float = field(default=0.0, init=False)
    _next_change_time: float = field(default=180.0, init=False)

    def __post_init__(self) -> None:
        self._next_change_time = random.uniform(self.min_hold_seconds, self.max_hold_seconds)

    @staticmethod
    def _smoothstep(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    def _cloud_strength(self, session_time: float) -> float:
        if self._transition_end <= self._transition_start:
            return 1.0 if self._current_weather == "cloudy" else 0.0

        raw_t = (session_time - self._transition_start) / (self._transition_end - self._transition_start)
        t = self._smoothstep(raw_t)

        if self._current_weather == "clear" and self._target_weather == "cloudy":
            return t
        if self._current_weather == "cloudy" and self._target_weather == "clear":
            return 1.0 - t
        return 1.0 if self._current_weather == "cloudy" else 0.0

    def _begin_transition(self, session_time: float) -> None:
        self._current_weather = self.get_current_weather(session_time)
        self._target_weather = "cloudy" if self._current_weather == "clear" else "clear"

        duration = random.uniform(self.min_transition_seconds, self.max_transition_seconds)
        self._transition_start = session_time
        self._transition_end = session_time + duration

    def update(self, session_time: float) -> None:
        """Advance weather state using absolute session time."""
        if self._transition_end > self._transition_start and session_time >= self._transition_end:
            self._current_weather = self._target_weather
            self._transition_start = 0.0
            self._transition_end = 0.0
            self._next_change_time = session_time + random.uniform(self.min_hold_seconds, self.max_hold_seconds)

        if self._transition_end <= self._transition_start and session_time >= self._next_change_time:
            self._begin_transition(session_time)

    def get_current_weather(self, session_time: float) -> str:
        """Return dominant weather state at the provided timestamp."""
        strength = self._cloud_strength(session_time)
        return "cloudy" if strength >= 0.5 else "clear"

    def get_overlay_tint(self, session_time: float) -> tuple[int, int, int, int]:
        """Return soft RGBA tint representing cloud coverage."""
        strength = self._cloud_strength(session_time)
        return (
            int(round(18 * strength)),
            int(round(24 * strength)),
            int(round(28 * strength)),
            int(round(44 * strength)),
        )

    def get_cloud_layer_offset(self, session_time: float, scene_width: int) -> int:
        """Return a very slow horizontal offset for placeholder cloud bands."""
        if scene_width <= 0:
            return 0
        speed_pixels_per_second = 2.0
        return int((session_time * speed_pixels_per_second) % scene_width)

    def get_cloud_strength(self, session_time: float) -> float:
        """Expose blend strength for rendering helpers."""
        return self._cloud_strength(session_time)
