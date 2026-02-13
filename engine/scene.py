"""Scene composition and rendering for the screensaver."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pygame

from engine.day_cycle import DayCycle
from engine.event_manager import EventManager
from engine.timer import SessionTimer
from engine.weather import WeatherSystem

# Calm dusk-like palette for a minimal atmosphere.
SKY_COLOR = (24, 34, 58)
WATER_COLOR = (18, 56, 84)
ISLET_COLOR = (62, 74, 52)
CHARACTER_COLOR = (214, 196, 150)


@dataclass
class IdleCharacter:
    """Simple idle figure with subtle horizontal sway animation."""

    base_x: int
    base_y: int
    width: int = 6
    height: int = 12
    sway_speed: float = 1.1
    sway_amplitude: float = 2.0
    animation_time: float = 0.0

    def update(self, delta_time: float) -> None:
        """Advance idle animation timing with bounded precision drift."""
        self.animation_time = (self.animation_time + delta_time) % (2.0 * math.pi)

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the character as a minimal retro rectangle."""
        offset = int(self.sway_amplitude * math.sin(self.animation_time * self.sway_speed))
        pygame.draw.rect(
            surface,
            CHARACTER_COLOR,
            pygame.Rect(self.base_x + offset, self.base_y, self.width, self.height),
        )


class Scene:
    """High-level scene logic for update and render operations."""

    def __init__(self, internal_size: tuple[int, int]) -> None:
        self.width, self.height = internal_size
        self.event_manager = EventManager("events/events.json")
        self.day_cycle = DayCycle()
        self.weather = WeatherSystem()
        self.idle_character = IdleCharacter(base_x=self.width // 2 - 3, base_y=self.height - 58)

        self._water_rect = pygame.Rect(0, self.height // 2 + 36, self.width, self.height // 2)
        self._islet_rect = pygame.Rect(self.width // 2 - 26, self.height // 2 + 18, 52, 24)

        self._weather_overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._day_overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        self._session_time = 0.0
        self._time_of_day = "day"
        self._weather_name = "clear"

    def update(self, delta_time: float, timer: SessionTimer) -> None:
        """Update animation, environmental state, and event scheduling."""
        self._session_time = timer.session_time
        self._time_of_day = self.day_cycle.get_time_of_day(timer.session_time)

        self.weather.update(timer.session_time)
        self._weather_name = self.weather.get_current_weather(timer.session_time)

        self.idle_character.update(delta_time)
        self.event_manager.update(
            delta_time,
            timer,
            environment={"time_of_day": self._time_of_day, "weather": self._weather_name},
        )

    def _render_weather_overlay(self, surface: pygame.Surface) -> None:
        tint = self.weather.get_overlay_tint(self._session_time)
        cloud_strength = self.weather.get_cloud_strength(self._session_time)

        self._weather_overlay.fill((0, 0, 0, 0))
        if tint[3] > 0:
            self._weather_overlay.fill(tint)

        if cloud_strength > 0.05:
            band_alpha = int(20 * cloud_strength)
            cloud_color = (170, 176, 184, band_alpha)
            offset = self.weather.get_cloud_layer_offset(self._session_time, self.width)
            cloud_rect = pygame.Rect(offset - self.width, 22, self.width + 40, 16)
            pygame.draw.rect(self._weather_overlay, cloud_color, cloud_rect)
            cloud_rect_2 = pygame.Rect(offset, 34, self.width + 30, 10)
            pygame.draw.rect(self._weather_overlay, cloud_color, cloud_rect_2)

        surface.blit(self._weather_overlay, (0, 0))

    def _render_day_overlay(self, surface: pygame.Surface) -> None:
        self._day_overlay.fill(self.day_cycle.get_light_overlay(self._session_time))
        surface.blit(self._day_overlay, (0, 0))

    def render(self, surface: pygame.Surface) -> None:
        """Render static atmosphere and active event overlays."""
        # 1) Background
        surface.fill(SKY_COLOR)
        pygame.draw.rect(surface, WATER_COLOR, self._water_rect)
        pygame.draw.rect(surface, ISLET_COLOR, self._islet_rect)

        # 2) Weather overlays
        self._render_weather_overlay(surface)

        # 3) Day/Night overlay
        self._render_day_overlay(surface)

        # 4) Character
        self.idle_character.draw(surface)

        # 5) Active event render
        self.event_manager.render(surface)
