"""Entry point for the East Frisia Castaway screensaver."""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from engine.scene import Scene
from engine.timer import SessionTimer

# Internal retro resolution used for all scene rendering.
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 200
# Fixed update rate for calm, consistent motion.
TARGET_FPS = 20


class RuntimeArgs(argparse.Namespace):
    """Container for command-line runtime options."""

    fullscreen: bool
    root: bool
    window_id: int | None
    preview: bool
    debug: bool


def _parse_arguments(argv: list[str] | None = None) -> RuntimeArgs:
    """Parse command-line options for fullscreen and XScreenSaver integration."""
    parser = argparse.ArgumentParser(description="East Frisia Castaway screensaver")
    parser.add_argument("--fullscreen", action="store_true", help="force fullscreen mode")
    parser.add_argument("--root", action="store_true", help="render into the X11 root window")
    parser.add_argument("--window-id", type=int, help="render into a specific X11 window id")
    parser.add_argument("--preview", action="store_true", help="run in 640x400 preview mode")
    parser.add_argument("--debug", action="store_true", help="enable structured debug logging")
    args = parser.parse_args(argv, namespace=RuntimeArgs())

    if args.root and args.window_id is not None:
        parser.error("--root and --window-id cannot be used together")
    if args.preview and (args.root or args.window_id is not None):
        parser.error("--preview cannot be combined with --root or --window-id")
    if args.fullscreen and (args.preview or args.root or args.window_id is not None):
        parser.error("--fullscreen cannot be combined with --preview, --root, or --window-id")

    return args


def _configure_logging(enabled: bool) -> logging.Logger:
    """Enable minimal structured logging only when debug mode is active."""
    logger = logging.getLogger("castaway")
    if enabled:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        logger.info("logging enabled")
    else:
        logging.disable(logging.CRITICAL)
    return logger


def _resolve_root_window_id() -> int:
    """Resolve the active X11 root window ID using libX11."""
    lib_x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
    lib_x11.XOpenDisplay.restype = ctypes.c_void_p
    lib_x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib_x11.XDefaultRootWindow.restype = ctypes.c_ulong
    lib_x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    lib_x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    display = lib_x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError("failed to open X11 display for root window lookup")

    try:
        root_window = int(lib_x11.XDefaultRootWindow(display))
    finally:
        lib_x11.XCloseDisplay(display)

    if root_window <= 0:
        raise RuntimeError("resolved invalid X11 root window id")
    return root_window


def _configure_sdl_window_target(args: RuntimeArgs, logger: logging.Logger) -> tuple[bool, bool]:
    """Configure SDL_WINDOWID for embedding modes and return mode flags."""
    is_window_target = args.window_id is not None or args.root
    is_preview = args.preview

    if args.window_id is not None:
        os.environ["SDL_WINDOWID"] = str(args.window_id)
        logger.info("using explicit window id target", extra={"window_id": args.window_id})
    elif args.root:
        root_window_id = _resolve_root_window_id()
        os.environ["SDL_WINDOWID"] = str(root_window_id)
        logger.info("using root window target", extra={"window_id": root_window_id})

    return is_window_target, is_preview


def _create_window(is_window_target: bool, is_preview: bool) -> tuple[pygame.Surface, tuple[int, int]]:
    """Create the pygame window surface and return the active output size."""
    if is_window_target:
        window = pygame.display.set_mode((0, 0))
        return window, window.get_size()

    if is_preview:
        preview_size = (640, 400)
        window = pygame.display.set_mode(preview_size)
        return window, preview_size

    display_info = pygame.display.Info()
    fullscreen_size = (display_info.current_w, display_info.current_h)
    window = pygame.display.set_mode(fullscreen_size, pygame.FULLSCREEN)
    return window, fullscreen_size


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
    args = _parse_arguments()
    logger = _configure_logging(args.debug)

    is_window_target, is_preview = _configure_sdl_window_target(args, logger)

    pygame.init()
    window, output_size = _create_window(is_window_target, is_preview)
    pygame.display.set_caption("East Frisia Castaway")

    _scale_factor, scaled_size, scaled_offset = _compute_integer_scale(output_size)

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
