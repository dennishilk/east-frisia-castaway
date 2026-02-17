"""Scheduler priority checks for rare tier handling."""

from __future__ import annotations

import random
import unittest

from engine.event_manager import EventManager
from engine.timer import SessionTimer


class SchedulerPriorityTests(unittest.TestCase):
    def test_tier1_rare_beats_tier2_when_eligible(self) -> None:
        manager = EventManager("events/events.json")
        timer = SessionTimer()
        timer.session_time = 2000.0

        environment = {"time_of_day": "night", "weather": "clear"}

        state = random.getstate()
        try:
            random.seed(7)
            manager.activate(timer, environment)
        finally:
            random.setstate(state)

        self.assertIsNotNone(manager.active_event)
        self.assertEqual(manager.active_event.event_type, "rare")
        self.assertEqual(manager.active_event.rare_tier, 1)
        self.assertNotEqual(manager.active_event.name, "moon_glint")

    def test_tier2_rare_is_used_as_fallback(self) -> None:
        manager = EventManager("events/events.json")
        timer = SessionTimer()

        state = random.getstate()
        try:
            random.seed(11)

            timer.session_time = 0.0
            manager.activate(timer, {"time_of_day": "day", "weather": "rain"})
            manager.active_event = None

            timer.session_time = 200.0
            manager.activate(timer, {"time_of_day": "day", "weather": "rain"})
        finally:
            random.setstate(state)

        self.assertIsNotNone(manager.active_event)
        self.assertEqual(manager.active_event.name, "moon_glint")
        self.assertEqual(manager.active_event.rare_tier, 2)

    def test_ambient_runs_when_rare_slot_has_no_eligible_events(self) -> None:
        manager = EventManager("events/events.json")
        timer = SessionTimer()
        timer.session_time = 1.0

        environment = {"time_of_day": "night", "weather": "storm"}

        state = random.getstate()
        try:
            random.seed(19)
            manager.activate(timer, environment)
        finally:
            random.setstate(state)

        self.assertIsNotNone(manager.active_event)
        self.assertNotEqual(manager.active_event.event_type, "rare")


if __name__ == "__main__":
    unittest.main()
