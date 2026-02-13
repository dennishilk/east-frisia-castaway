"""Entry point for the East Frisia Castaway screensaver."""

from __future__ import annotations

import logging
import os
import sys

import pygame

from engine.scene import Scene
from engine.timer import SessionTimer

# Internal retro resolution used for all scene rendering.
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 200
# Fixed update rate for calm, consistent motion.
TARGET_FPS = 20


def _configure_logging() -> None:
    """Enable minimal optional logging when CASTAWAY_DEBUG=1 is set."""
    if os.environ.get("CASTAWAY_DEBUG") == "1":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _compute_integer_scale(screen_size: tuple[int, int]) -> tuple[int, tuple[int, int], tuple[int, int]]:
    """Compute integer nearest-neighbor scale and centered output rectangle."""
    screen_width, screen_height = screen_size
    scale = min(screen_width // INTERNAL_WIDTH, screen_height // INTERNAL_HEIGHT)
    if scale < 1:
        scale = 1

    scaled_size = (INTERNAL_WIDTH * scale, INTERNAL_HEIGHT * scale)
    offset = ((screen_width - scaled_size[0]) // 2, (screen_height - scaled_size[1]) // 2)
    return scale, scaled_size, offset


def _shutdown() -> None:
    """Terminate pygame cleanly and exit immediately."""
    pygame.quit()
    sys.exit(0)


def main() -> None:
    """Start the screensaver loop and exit on any user interaction."""
    _configure_logging()
    pygame.init()

    display_info = pygame.display.Info()
    fullscreen_size = (display_info.current_w, display_info.current_h)
    window = pygame.display.set_mode(fullscreen_size, pygame.FULLSCREEN)
    pygame.display.set_caption("East Frisia Castaway")

    _scale_factor, scaled_size, scaled_offset = _compute_integer_scale(fullscreen_size)

    internal_surface = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
    scaled_surface = pygame.Surface(scaled_size)
    clock = pygame.time.Clock()

    timer = SessionTimer()
    scene = Scene((INTERNAL_WIDTH, INTERNAL_HEIGHT))

    while True:
        delta_time = timer.tick()

        for event in pygame.event.get():
            if event.type in (
                pygame.QUIT,
                pygame.KEYDOWN,
                pygame.MOUSEMOTION,
                pygame.MOUSEBUTTONDOWN,
            ):
                _shutdown()

        scene.update(delta_time, timer)
        scene.render(internal_surface)

        pygame.transform.scale(internal_surface, scaled_size, scaled_surface)
        window.fill((0, 0, 0))
        window.blit(scaled_surface, scaled_offset)
        pygame.display.flip()

        clock.tick(TARGET_FPS)


if __name__ == "__main__":
    main()
