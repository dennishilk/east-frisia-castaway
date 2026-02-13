"""Timing utilities for a stable screensaver session."""

from __future__ import annotations

import time


class SessionTimer:
    """Track monotonic frame timing and session-relative timestamps.

    All public timing values are derived from :func:`time.perf_counter` to keep
    scheduling stable over long runtimes.
    """

    def __init__(self) -> None:
        now = time.perf_counter()
        self._last_tick = now
        self._session_start = now
        self._last_event_session_time = 0.0

        self.delta_time = 0.0
        self.session_time = 0.0
        self.time_since_last_event = 0.0

    def tick(self) -> float:
        """Advance timer state and return delta time in seconds."""
        now = time.perf_counter()
        self.delta_time = max(0.0, now - self._last_tick)
        self._last_tick = now

        self.session_time = now - self._session_start
        self.time_since_last_event = max(0.0, self.session_time - self._last_event_session_time)
        return self.delta_time

    def mark_event_triggered(self) -> None:
        """Record the current session timestamp as the latest event trigger."""
        self._last_event_session_time = self.session_time
        self.time_since_last_event = 0.0

    def has_reached_runtime(self, seconds: float) -> bool:
        """Check if session has reached a minimum runtime threshold."""
        return self.session_time >= seconds
