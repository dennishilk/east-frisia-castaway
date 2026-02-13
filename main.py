"""Entry point for the East Frisia Castaway screensaver."""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys
from dataclasses import dataclass

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from engine.scene import Scene
from engine.timer import SessionTimer

INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 200
PREVIEW_SIZE = (640, 400)
TARGET_FPS = 20


class RuntimeArgs(argparse.Namespace):
    """Container for command-line runtime options."""

    fullscreen: bool
    preview: bool
    window_id: int | None
    root: bool
    debug: bool


@dataclass(frozen=True)
class LaunchConfig:
    """Resolved runtime mode after parsing CLI and environment."""

    mode: str
    embed_window_id: str | None = None


class ShutdownRequested(Exception):
    """Raised when the saver should exit immediately."""


def parse_arguments(argv: list[str] | None = None) -> RuntimeArgs:
    """Parse CLI arguments expected by XScreenSaver integrations."""
    parser = argparse.ArgumentParser(description="East Frisia Castaway screensaver")
    parser.add_argument("--fullscreen", action="store_true", help="force fullscreen mode")
    parser.add_argument("--preview", action="store_true", help="open a local 640x400 preview window")
    parser.add_argument("--window-id", type=int, help="embed in an existing X11 window")
    parser.add_argument("--root", action="store_true", help="target the X11 root window")
    parser.add_argument("--debug", action="store_true", help="enable concise debug logging")

    args = parser.parse_args(argv, namespace=RuntimeArgs())

    if args.window_id is not None and args.root:
        parser.error("--window-id and --root cannot be used together")
    if args.preview and (args.window_id is not None or args.root):
        parser.error("--preview cannot be used with --window-id or --root")
    if args.fullscreen and (args.preview or args.window_id is not None or args.root):
        parser.error("--fullscreen cannot be used with --preview, --window-id, or --root")

    return args


def configure_logging(debug_enabled: bool) -> logging.Logger:
    """Create a logger that stays quiet unless debug is enabled."""
    logger = logging.getLogger("castaway")
    logger.handlers.clear()
    logger.propagate = False

    if debug_enabled:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s castaway %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    else:
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.CRITICAL + 1)

    return logger


def _resolve_root_window_id() -> str | None:
    """Resolve the X11 root window ID through libX11 using ctypes."""
    try:
        lib_x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
    except OSError:
        return None

    lib_x11.XOpenDisplay.restype = ctypes.c_void_p
    lib_x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib_x11.XDefaultRootWindow.restype = ctypes.c_ulong
    lib_x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    lib_x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    display = lib_x11.XOpenDisplay(None)
    if not display:
        return None

    try:
        root_window = int(lib_x11.XDefaultRootWindow(display))
    finally:
        lib_x11.XCloseDisplay(display)

    if root_window <= 0:
        return None
    return str(root_window)


def resolve_launch_config(args: RuntimeArgs, logger: logging.Logger) -> LaunchConfig:
    """Resolve launch mode based on CLI flags and XScreenSaver environment."""
    env_window = os.environ.get("XSCREENSAVER_WINDOW")

    if args.window_id is not None:
        return LaunchConfig(mode="embed", embed_window_id=str(args.window_id))

    if env_window:
        return LaunchConfig(mode="embed", embed_window_id=env_window)

    if args.root:
        root_window = _resolve_root_window_id()
        if root_window:
            return LaunchConfig(mode="embed", embed_window_id=root_window)
        logger.info("root mode requested but root window id could not be resolved; falling back to fullscreen")
        return LaunchConfig(mode="fullscreen")

    if args.preview:
        return LaunchConfig(mode="preview")

    return LaunchConfig(mode="fullscreen")


def prepare_sdl_embedding(config: LaunchConfig) -> None:
    """Set SDL embedding target before pygame initialization."""
    if config.embed_window_id:
        os.environ["SDL_WINDOWID"] = config.embed_window_id
    else:
        os.environ.pop("SDL_WINDOWID", None)


def _create_window(config: LaunchConfig, logger: logging.Logger) -> tuple[pygame.Surface, tuple[int, int]]:
    """Create the pygame display surface according to resolved mode."""
    if config.mode == "embed":
        try:
            window = pygame.display.set_mode((0, 0), pygame.RESIZABLE)
        except pygame.error:
            logger.info("embed mode unavailable on this video driver; using windowed fallback")
            try:
                window = pygame.display.set_mode(PREVIEW_SIZE, pygame.RESIZABLE)
            except pygame.error:
                window = pygame.display.set_mode(PREVIEW_SIZE)
        return window, window.get_size()

    if config.mode == "preview":
        try:
            window = pygame.display.set_mode(PREVIEW_SIZE, pygame.RESIZABLE)
        except pygame.error:
            window = pygame.display.set_mode(PREVIEW_SIZE)
        return window, PREVIEW_SIZE

    display_info = pygame.display.Info()
    fullscreen_size = (display_info.current_w, display_info.current_h)
    window = pygame.display.set_mode(fullscreen_size, pygame.FULLSCREEN)
    return window, fullscreen_size


def _compute_integer_scale(screen_size: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    """Compute integer nearest-neighbor scale and centered offset."""
    screen_width, screen_height = screen_size
    scale = min(screen_width // INTERNAL_WIDTH, screen_height // INTERNAL_HEIGHT)
    if scale < 1:
        scale = 1

    scaled_size = (INTERNAL_WIDTH * scale, INTERNAL_HEIGHT * scale)
    offset = ((screen_width - scaled_size[0]) // 2, (screen_height - scaled_size[1]) // 2)
    return scaled_size, offset


def _rebuild_scaling(screen_size: tuple[int, int]) -> tuple[pygame.Surface, tuple[int, int], tuple[int, int]]:
    """Allocate surfaces only when output size changes."""
    scaled_size, scaled_offset = _compute_integer_scale(screen_size)
    scaled_surface = pygame.Surface(scaled_size)
    return scaled_surface, scaled_size, scaled_offset


def _handle_event(event: pygame.event.Event) -> tuple[bool, tuple[int, int] | None]:
    """Return whether to shutdown and an optional new screen size."""
    if event.type in (pygame.QUIT, pygame.KEYDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
        return True, None

    if event.type == pygame.VIDEORESIZE:
        return False, (event.w, event.h)

    if event.type == pygame.WINDOWRESIZED:
        return False, (event.x, event.y)

    return False, None


def run(argv: list[str] | None = None) -> int:
    """Run the saver loop."""
    args = parse_arguments(argv)
    logger = configure_logging(args.debug)
    config = resolve_launch_config(args, logger)
    prepare_sdl_embedding(config)

    pygame.init()
    window, output_size = _create_window(config, logger)
    pygame.display.set_caption("East Frisia Castaway")

    internal_surface = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
    scaled_surface, scaled_size, scaled_offset = _rebuild_scaling(output_size)

    clock = pygame.time.Clock()
    timer = SessionTimer()
    scene = Scene((INTERNAL_WIDTH, INTERNAL_HEIGHT))

    try:
        while True:
            delta_time = timer.tick()

            for event in pygame.event.get():
                should_shutdown, new_size = _handle_event(event)
                if should_shutdown:
                    raise ShutdownRequested
                if new_size and new_size[0] > 0 and new_size[1] > 0:
                    scaled_surface, scaled_size, scaled_offset = _rebuild_scaling(new_size)

            scene.update(delta_time, timer)
            scene.render(internal_surface)

            pygame.transform.scale(internal_surface, scaled_size, scaled_surface)
            window.fill((0, 0, 0))
            window.blit(scaled_surface, scaled_offset)
            pygame.display.flip()
            clock.tick(TARGET_FPS)
    except ShutdownRequested:
        return 0
    finally:
        pygame.quit()


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    raise SystemExit(run(argv))


if __name__ == "__main__":
    main()
