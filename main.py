"""Entry point for the East Frisia Castaway screensaver."""

import sys

import pygame

from engine.scene import Scene
from engine.timer import SessionTimer

# Internal retro resolution used for all scene rendering.
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 200
# Fixed update rate for calm, consistent motion.
TARGET_FPS = 20


def main() -> None:
    """Start the screensaver loop and exit on any user interaction."""
    pygame.init()

    display_info = pygame.display.Info()
    fullscreen_size = (display_info.current_w, display_info.current_h)
    window = pygame.display.set_mode(fullscreen_size, pygame.FULLSCREEN)
    pygame.display.set_caption("East Frisia Castaway")

    internal_surface = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
    clock = pygame.time.Clock()

    timer = SessionTimer()
    scene = Scene((INTERNAL_WIDTH, INTERNAL_HEIGHT))

    running = True
    while running:
        delta_time = timer.tick()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type in (
                pygame.KEYDOWN,
                pygame.MOUSEMOTION,
                pygame.MOUSEBUTTONDOWN,
            ):
                running = False

        scene.update(delta_time, timer)
        scene.render(internal_surface)

        scaled_surface = pygame.transform.scale(internal_surface, fullscreen_size)
        window.blit(scaled_surface, (0, 0))
        pygame.display.flip()

        clock.tick(TARGET_FPS)

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
