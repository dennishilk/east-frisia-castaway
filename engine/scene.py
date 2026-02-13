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
WATERLINE_COLOR = (46, 58, 76)
SAND_BASE_COLOR = (70, 80, 60)
SAND_DEPTH_COLOR = (58, 68, 50)
SAND_DITHER_COLOR = (63, 73, 54)


@dataclass
class Waterline:
    """Subtle horizontal waterline with very slow sinusoidal drift."""

    y: int
    width: int
    thickness: int = 2
    base_amplitude: float = 2.0

    def render(self, surface: pygame.Surface, session_time: float, time_of_day: str) -> None:
        """Render a calm 1-2 pixel band with minimal horizontal motion."""
        night_factor = 0.7 if time_of_day == "night" else 1.0
        amplitude = self.base_amplitude * night_factor
        wave_input = max(-10_000.0, min(10_000.0, session_time * 0.1))
        offset = int(round(math.sin(wave_input) * amplitude))

        for row in range(self.thickness):
            line_y = self.y + row
            segment_shift = (offset + row) % 8
            for x in range(-8 + segment_shift, self.width + 8, 8):
                pygame.draw.line(surface, WATERLINE_COLOR, (x, line_y), (x + 5, line_y))


class IdleCharacter:
    """Minimal pixel-art character with slow sway and subtle bobbing."""

    def __init__(self, base_x: int, base_y: int) -> None:
        self.base_x = base_x
        self.base_y = base_y
        self._session_time = 0.0
        self._weather_name = "clear"
        self._frames = self._build_frames()

    @staticmethod
    def _build_frames() -> list[pygame.Surface]:
        palette = {
            " ": (0, 0, 0, 0),
            "s": (210, 194, 152, 255),
            "h": (184, 164, 122, 255),
            "c": (76, 86, 66, 255),
            "d": (58, 66, 50, 255),
            "a": (170, 154, 118, 255),
        }

        frame_patterns = [
            [
                "     ss     ",
                "    shhs    ",
                "    shhs    ",
                "    shhs    ",
                "    ssss    ",
                "    cccc    ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   a   a    ",
                "  aa   aa   ",
                "  aa   aa   ",
                "  aa   aa   ",
                "  aa   aa   ",
                "            ",
            ],
            [
                "     ss     ",
                "    shhs    ",
                "    shhs    ",
                "    shhs    ",
                "    ssss    ",
                "    cccc    ",
                "   dccccc   ",
                "   dccccc   ",
                "   dccccc   ",
                "   dccccc   ",
                "   dccccc   ",
                "   dccccc   ",
                "   dccccc   ",
                "   dccccc   ",
                "    a   a   ",
                "   aa   aa  ",
                "   aa   aa  ",
                "   aa   aa  ",
                "   aa   aa  ",
                "            ",
            ],
            [
                "     ss     ",
                "    shhs    ",
                "    shhs    ",
                "    shhs    ",
                "    ssss    ",
                "    cccc    ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "   cccccd   ",
                "    a   a   ",
                "   aa   aa  ",
                "   aa   aa  ",
                "   aa   aa  ",
                "   aa   aa  ",
                "            ",
            ],
        ]

        frames: list[pygame.Surface] = []
        for pattern in frame_patterns:
            frame_surface = pygame.Surface((12, 20), pygame.SRCALPHA)
            for y, row in enumerate(pattern):
                for x, marker in enumerate(row):
                    color = palette[marker]
                    if color[3] > 0:
                        frame_surface.set_at((x, y), color)
            frames.append(frame_surface)
        return frames

    def update(self, session_time: float, weather_name: str) -> None:
        """Sync animation with absolute time to avoid frame drift."""
        self._session_time = session_time
        self._weather_name = weather_name

    def draw(self, surface: pygame.Surface) -> None:
        """Draw with slow sway and tiny shoreline bobbing."""
        sway_amp = 1.3
        if self._weather_name == "cloudy":
            sway_amp = 1.9

        sway_x = int(round(math.sin(self._session_time * 2.0 * math.pi * 0.6) * sway_amp))
        bob_y = int(round(math.sin(self._session_time * 2.0 * math.pi * 0.45) * 0.8))

        phase = (math.sin(self._session_time * 2.0 * math.pi * 0.75) + 1.0) * 0.5
        if phase < 0.33:
            frame_index = 0
        elif phase < 0.66:
            frame_index = 1
        else:
            frame_index = 2

        frame = self._frames[frame_index]
        surface.blit(frame, (self.base_x + sway_x, self.base_y + bob_y))


class Scene:
    """High-level scene logic for update and render operations."""

    def __init__(self, internal_size: tuple[int, int]) -> None:
        self.width, self.height = internal_size
        self.event_manager = EventManager("events/events.json")
        self.day_cycle = DayCycle()
        self.weather = WeatherSystem()

        sand_top = self.height // 2 + 22
        self._sand_rect = pygame.Rect(0, sand_top, self.width, self.height - sand_top)
        self._waterline = Waterline(y=sand_top - 2, width=self.width)
        self.idle_character = IdleCharacter(base_x=self.width // 2 - 6, base_y=sand_top - 22)

        self._sand_surface = self._build_sand_surface()
        self._weather_overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._day_overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        self._session_time = 0.0
        self._time_of_day = "day"
        self._weather_name = "clear"

    def _build_sand_surface(self) -> pygame.Surface:
        """Create static two-tone sand with lightweight dithering."""
        sand = pygame.Surface((self._sand_rect.width, self._sand_rect.height))
        sand.fill(SAND_BASE_COLOR)

        depth_height = self._sand_rect.height // 3
        depth_rect = pygame.Rect(0, self._sand_rect.height - depth_height, self._sand_rect.width, depth_height)
        pygame.draw.rect(sand, SAND_DEPTH_COLOR, depth_rect)

        for y in range(0, self._sand_rect.height, 2):
            start_x = (y // 2) % 2
            for x in range(start_x, self._sand_rect.width, 4):
                sand.set_at((x, y), SAND_DITHER_COLOR)

        return sand

    def update(self, delta_time: float, timer: SessionTimer) -> None:
        """Update animation, environmental state, and event scheduling."""

        self._session_time = timer.session_time
        self._time_of_day = self.day_cycle.get_time_of_day(timer.session_time)

        self.weather.update(timer.session_time)
        self._weather_name = self.weather.get_current_weather(timer.session_time)

        self.idle_character.update(timer.session_time, self._weather_name)
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
        # 1) Background sky
        surface.fill(SKY_COLOR)

        # 2) Waterline
        self._waterline.render(surface, self._session_time, self._time_of_day)

        # 3) Sandbank
        surface.blit(self._sand_surface, self._sand_rect.topleft)

        # 4) Weather overlays
        self._render_weather_overlay(surface)

        # 5) Day/Night overlay
        self._render_day_overlay(surface)

        # 6) Character
        self.idle_character.draw(surface)

        # 7) Active event render
        self.event_manager.render(surface)
