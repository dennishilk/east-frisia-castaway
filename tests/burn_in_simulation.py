"""Burn-in simulation and long-run stability checks for event scheduling.

This script runs a headless, deterministic simulation of the event system at the
project's fixed 20 FPS cadence. It does not open a window or depend on wall
clock progression for session timing.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import random
import statistics
import time
import tracemalloc
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.event_manager import EventManager, SceneEvent
from engine.timer import SessionTimer

FPS = 20
FIXED_DT = 1.0 / FPS
DEFAULT_HOURS = 8.0
EVENT_FILE = REPO_ROOT / "events" / "events.json"


class FakePerfClock:
    """Monotonic fake clock used to drive SessionTimer.tick deterministically."""

    def __init__(self) -> None:
        self.now = 0.0

    def perf_counter(self) -> float:
        return self.now

    def advance(self, delta: float) -> None:
        self.now += delta


@contextmanager
def patched_perf_counter(fake_clock: FakePerfClock) -> Iterator[None]:
    """Patch ``time.perf_counter`` so SessionTimer can run in virtual time."""

    with patch("engine.timer.time.perf_counter", side_effect=fake_clock.perf_counter):
        yield


@dataclass
class SimulationStats:
    """Aggregate counters and metrics captured during simulation."""

    total_frames: int
    total_events: int
    event_counts: dict[str, int]
    average_interval: float
    event_intervals_by_id: dict[str, float]
    rare_event_total: int
    max_simultaneous_events: int
    cooldown_violations: int
    min_runtime_violations: int
    timing_drift_seconds: float
    accumulation_drift_seconds: float
    avg_iteration_seconds: float
    memory_start_bytes: int
    memory_end_bytes: int
    memory_peak_bytes: int
    rare_ratio_warning: str | None


@dataclass
class TriggerRecord:
    """Event trigger details for validation and reporting."""

    frame: int
    session_time: float
    event: SceneEvent


def identify_rare_events(events: list[SceneEvent]) -> set[str]:
    """Heuristic: treat low-weight events as rare."""

    if not events:
        return set()

    max_weight = max(event.weight for event in events)
    threshold = max(1, int(max_weight * 0.25))
    return {event.name for event in events if event.weight <= threshold}


def _format_seconds(seconds: float) -> str:
    return f"{seconds:.6f}s"


def run_simulation(hours: float, seed: int | None, debug: bool) -> SimulationStats:
    """Execute deterministic burn-in loop and return captured metrics."""

    if seed is not None:
        random.seed(seed)

    target_seconds = hours * 3600.0
    total_frames = int(target_seconds * FPS)

    fake_clock = FakePerfClock()
    event_counts: dict[str, int] = defaultdict(int)
    trigger_records: list[TriggerRecord] = []
    event_intervals_by_id: dict[str, list[float]] = defaultdict(list)

    cooldown_violations = 0
    min_runtime_violations = 0
    max_simultaneous_events = 0

    iteration_durations: list[float] = []
    delta_accumulator = 0.0

    tracemalloc.start()
    memory_start = tracemalloc.get_traced_memory()[0]

    with patched_perf_counter(fake_clock):
        timer = SessionTimer()
        manager = EventManager(str(EVENT_FILE))

        if debug:
            print(f"Loaded events: {[event.name for event in manager.events]}")

        last_trigger_by_event: dict[str, float] = {}
        previous_event_trigger_time: float | None = None

        for frame in range(total_frames):
            loop_start = time.process_time_ns()

            fake_clock.advance(FIXED_DT)
            delta_time = timer.tick()
            delta_accumulator += delta_time

            event_before = manager.active_event
            manager.update(delta_time, timer)
            active_count = 1 if manager.active_event is not None else 0
            max_simultaneous_events = max(max_simultaneous_events, active_count)

            event_after = manager.active_event
            if event_before is None and event_after is not None:
                event_counts[event_after.name] += 1
                trigger = TriggerRecord(frame=frame, session_time=timer.session_time, event=event_after)
                trigger_records.append(trigger)

                if timer.session_time < event_after.min_runtime:
                    min_runtime_violations += 1

                previous_same = last_trigger_by_event.get(event_after.name)
                if previous_same is not None:
                    same_interval = timer.session_time - previous_same
                    event_intervals_by_id[event_after.name].append(same_interval)
                    if same_interval + 1e-9 < event_after.cooldown:
                        cooldown_violations += 1
                last_trigger_by_event[event_after.name] = timer.session_time

                if previous_event_trigger_time is not None:
                    interval = timer.session_time - previous_event_trigger_time
                    event_intervals_by_id["__all__"].append(interval)
                previous_event_trigger_time = timer.session_time

                if debug:
                    print(
                        f"frame={frame} t={timer.session_time:.3f} "
                        f"triggered={event_after.name} duration={event_after.duration}"
                    )

            loop_end = time.process_time_ns()
            iteration_durations.append((loop_end - loop_start) / 1_000_000_000)

    memory_end, memory_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    expected_session_time = total_frames / FPS
    timing_drift_seconds = timer.session_time - expected_session_time
    accumulation_drift_seconds = delta_accumulator - expected_session_time

    average_interval = (
        statistics.fmean(event_intervals_by_id["__all__"])
        if event_intervals_by_id["__all__"]
        else math.nan
    )

    event_interval_averages = {
        event_name: statistics.fmean(intervals)
        for event_name, intervals in event_intervals_by_id.items()
        if event_name != "__all__" and intervals
    }

    rare_events = identify_rare_events(manager.events)
    rare_event_total = sum(event_counts[name] for name in rare_events)

    rare_ratio_warning = None
    if manager.events and rare_events and len(trigger_records) > 0:
        total_weight = sum(event.weight for event in manager.events)
        rare_weight = sum(event.weight for event in manager.events if event.name in rare_events)
        expected_rare_ratio = rare_weight / total_weight if total_weight else 0.0
        observed_rare_ratio = rare_event_total / len(trigger_records)
        if expected_rare_ratio > 0.0 and (
            observed_rare_ratio > expected_rare_ratio * 3.0
            or observed_rare_ratio < expected_rare_ratio / 3.0
        ):
            rare_ratio_warning = (
                "Rare-event frequency deviates from static weight ratio: "
                f"observed={observed_rare_ratio:.4f}, expected~={expected_rare_ratio:.4f}"
            )

    return SimulationStats(
        total_frames=total_frames,
        total_events=len(trigger_records),
        event_counts=dict(sorted(event_counts.items())),
        average_interval=average_interval,
        event_intervals_by_id=event_interval_averages,
        rare_event_total=rare_event_total,
        max_simultaneous_events=max_simultaneous_events,
        cooldown_violations=cooldown_violations,
        min_runtime_violations=min_runtime_violations,
        timing_drift_seconds=timing_drift_seconds,
        accumulation_drift_seconds=accumulation_drift_seconds,
        avg_iteration_seconds=statistics.fmean(iteration_durations) if iteration_durations else 0.0,
        memory_start_bytes=memory_start,
        memory_end_bytes=memory_end,
        memory_peak_bytes=memory_peak,
        rare_ratio_warning=rare_ratio_warning,
    )


def print_report(hours: float, stats: SimulationStats) -> None:
    """Print required burn-in report metrics."""

    print("\n=== Burn-In Simulation Report ===")
    print(f"Total simulated hours: {hours:.2f}")
    print(f"Total frames processed: {stats.total_frames}")
    print(f"Total events: {stats.total_events}")

    print("\nEvent distribution:")
    if not stats.event_counts:
        print("  (none)")
    else:
        width = max(len(name) for name in stats.event_counts)
        for name, count in stats.event_counts.items():
            print(f"  {name:<{width}} : {count}")

    avg_interval_text = (
        _format_seconds(stats.average_interval)
        if not math.isnan(stats.average_interval)
        else "n/a"
    )

    print(f"\nRare event count: {stats.rare_event_total}")
    print(f"Average interval between events: {avg_interval_text}")
    print(f"Max simultaneous events: {stats.max_simultaneous_events}")

    memory_delta = stats.memory_end_bytes - stats.memory_start_bytes
    print(f"Memory delta: {memory_delta} bytes")
    print(f"Memory peak: {stats.memory_peak_bytes} bytes")

    print(f"Timing drift (session_time - expected): {stats.timing_drift_seconds:.12f}s")
    print(f"Timing drift (sum(delta) - expected): {stats.accumulation_drift_seconds:.12f}s")

    print("\nValidation checks:")
    print(f"  Min runtime violations: {stats.min_runtime_violations}")
    print(f"  Cooldown violations: {stats.cooldown_violations}")
    print(f"  One-active-event invariant violations: {max(0, stats.max_simultaneous_events - 1)}")
    print(f"  Avg loop iteration wall time: {stats.avg_iteration_seconds * 1_000_000:.2f} µs")

    if stats.event_intervals_by_id:
        print("\nAverage interval by event id:")
        width = max(len(name) for name in stats.event_intervals_by_id)
        for event_name, avg in sorted(stats.event_intervals_by_id.items()):
            print(f"  {event_name:<{width}} : {_format_seconds(avg)}")

    if stats.rare_ratio_warning:
        print(f"WARNING: {stats.rare_ratio_warning}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Headless burn-in simulation for event timing.")
    parser.add_argument("--seed", type=int, default=None, help="Fixed RNG seed for deterministic runs")
    parser.add_argument("--hours", type=float, default=DEFAULT_HOURS, help="Simulated hours to run")
    parser.add_argument("--debug", action="store_true", help="Print per-trigger debug output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = run_simulation(hours=args.hours, seed=args.seed, debug=args.debug)
    print_report(hours=args.hours, stats=stats)


if __name__ == "__main__":
    main()
