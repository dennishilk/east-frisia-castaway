"""Scene composition and rendering for the screensaver."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pygame

from engine.event_manager import EventManager
from engine.timer import SessionTimer

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
        self.idle_character = IdleCharacter(base_x=self.width // 2 - 3, base_y=self.height - 58)

        self._water_rect = pygame.Rect(0, self.height // 2 + 36, self.width, self.height // 2)
        self._islet_rect = pygame.Rect(self.width // 2 - 26, self.height // 2 + 18, 52, 24)

    def update(self, delta_time: float, timer: SessionTimer) -> None:
        """Update animation and event scheduling."""
        self.idle_character.update(delta_time)
        self.event_manager.update(delta_time, timer)

    def render(self, surface: pygame.Surface) -> None:
        """Render static atmosphere and active event overlays."""
        surface.fill(SKY_COLOR)
        pygame.draw.rect(surface, WATER_COLOR, self._water_rect)
        pygame.draw.rect(surface, ISLET_COLOR, self._islet_rect)

        self.idle_character.draw(surface)
        self.event_manager.render(surface)
