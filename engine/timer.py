"""Timing utilities for a stable screensaver session."""

from __future__ import annotations

import time


class SessionTimer:
    """Track frame delta, session runtime, and event intervals."""

    def __init__(self) -> None:
        now = time.perf_counter()
        self._last_tick = now
        self._session_start = now
        self._last_event_time = now

        self.delta_time = 0.0
        self.session_time = 0.0
        self.time_since_last_event = 0.0

    def tick(self) -> float:
        """Advance timer state and return delta time in seconds."""
        now = time.perf_counter()
        self.delta_time = now - self._last_tick
        self._last_tick = now

        self.session_time = now - self._session_start
        self.time_since_last_event = now - self._last_event_time
        return self.delta_time

    def mark_event_triggered(self) -> None:
        """Reset the event interval timer when an event starts."""
        self._last_event_time = time.perf_counter()
        self.time_since_last_event = 0.0

    def has_reached_runtime(self, seconds: float) -> bool:
        """Check if session has reached a minimum runtime threshold."""
        return self.session_time >= seconds
