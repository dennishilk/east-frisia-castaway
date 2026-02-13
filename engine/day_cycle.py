"""Time-of-day cycle logic for subtle day and night atmosphere."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DayCycle:
    """Compute smooth cyclical lighting from absolute session time."""

    day_length_seconds: float = 30.0 * 60.0

    def _normalized_progress(self, session_time: float) -> float:
        if self.day_length_seconds <= 0.0:
            return 0.0
        return (session_time % self.day_length_seconds) / self.day_length_seconds

    def get_time_of_day(self, session_time: float) -> str:
        """Return a coarse time-of-day label based on normalized cycle progress."""
        progress = self._normalized_progress(session_time)
        if progress < 0.20:
            return "dawn"
        if progress < 0.55:
            return "day"
        if progress < 0.75:
            return "sunset"
        return "night"

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    @staticmethod
    def _smoothstep(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    def get_light_overlay(self, session_time: float) -> tuple[int, int, int, int]:
        """Return subtle RGBA tint for the current cycle position."""
        progress = self._normalized_progress(session_time)

        # Each point is (cycle progress, (r, g, b, alpha)).
        # Keep values soft to preserve a calm, readable scene.
        points = (
            (0.00, (24, 16, 8, 14)),
            (0.20, (0, 0, 0, 0)),
            (0.55, (30, 14, 10, 18)),
            (0.75, (12, 18, 34, 44)),
            (1.00, (24, 16, 8, 14)),
        )

        for index in range(len(points) - 1):
            left_p, left_c = points[index]
            right_p, right_c = points[index + 1]
            if left_p <= progress <= right_p:
                local_t = (progress - left_p) / (right_p - left_p) if right_p > left_p else 0.0
                blend = self._smoothstep(local_t)
                return tuple(
                    int(round(self._lerp(left_c[channel], right_c[channel], blend)))
                    for channel in range(4)
                )

        return points[-1][1]
