"""Headless-safe checks for XSCREENSAVER_WINDOW embedding path selection."""

from __future__ import annotations

import os
import unittest

import main


class WindowIdEnvironmentTests(unittest.TestCase):
    def test_env_window_id_sets_sdl_target_without_crash(self) -> None:
        old_video_driver = os.environ.get("SDL_VIDEODRIVER")
        old_xss_window = os.environ.get("XSCREENSAVER_WINDOW")
        old_sdl_windowid = os.environ.get("SDL_WINDOWID")

        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["XSCREENSAVER_WINDOW"] = "424242"

        try:
            args = main.parse_arguments([])
            logger = main.configure_logging(False)
            config = main.resolve_launch_config(args, logger)
            self.assertEqual(config.mode, "embed")
            self.assertEqual(config.embed_window_id, "424242")

            main.prepare_sdl_embedding(config)
            self.assertEqual(os.environ.get("SDL_WINDOWID"), "424242")
        finally:
            if old_video_driver is None:
                os.environ.pop("SDL_VIDEODRIVER", None)
            else:
                os.environ["SDL_VIDEODRIVER"] = old_video_driver

            if old_xss_window is None:
                os.environ.pop("XSCREENSAVER_WINDOW", None)
            else:
                os.environ["XSCREENSAVER_WINDOW"] = old_xss_window

            if old_sdl_windowid is None:
                os.environ.pop("SDL_WINDOWID", None)
            else:
                os.environ["SDL_WINDOWID"] = old_sdl_windowid

    def test_invalid_env_window_id_is_ignored(self) -> None:
        old_xss_window = os.environ.get("XSCREENSAVER_WINDOW")

        os.environ["XSCREENSAVER_WINDOW"] = "not-a-window-id"
        try:
            args = main.parse_arguments([])
            logger = main.configure_logging(False)
            config = main.resolve_launch_config(args, logger)
            self.assertEqual(config.mode, "fullscreen")
            self.assertIsNone(config.embed_window_id)
        finally:
            if old_xss_window is None:
                os.environ.pop("XSCREENSAVER_WINDOW", None)
            else:
                os.environ["XSCREENSAVER_WINDOW"] = old_xss_window



if __name__ == "__main__":
    unittest.main()
