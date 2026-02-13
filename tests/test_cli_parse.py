"""Sanity checks for CLI parsing behavior."""

from __future__ import annotations

import unittest

import main


class CliParseTests(unittest.TestCase):
    def test_default_arguments(self) -> None:
        args = main.parse_arguments([])
        self.assertFalse(args.fullscreen)
        self.assertFalse(args.preview)
        self.assertIsNone(args.window_id)
        self.assertFalse(args.root)

    def test_preview_flag(self) -> None:
        args = main.parse_arguments(["--preview"])
        self.assertTrue(args.preview)

    def test_window_id_flag(self) -> None:
        args = main.parse_arguments(["--window-id", "1234"])
        self.assertEqual(args.window_id, 1234)

    def test_conflicting_root_and_window_id(self) -> None:
        with self.assertRaises(SystemExit):
            main.parse_arguments(["--root", "--window-id", "99"])

    def test_conflicting_preview_and_root(self) -> None:
        with self.assertRaises(SystemExit):
            main.parse_arguments(["--preview", "--root"])


if __name__ == "__main__":
    unittest.main()
