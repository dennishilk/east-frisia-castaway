"""Burn-in simulation and long-run stability checks for event scheduling.

This script runs a headless, deterministic simulation of the event system at the
project's fixed 20 FPS cadence. It does not open a window or depend on wall
clock progression for session timing.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys
import time
import tracemalloc
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.event_manager import EventManager, SceneEvent
from engine.day_cycle import DayCycle
from engine.timer import SessionTimer
from engine.weather import WeatherSystem

FPS = 20
FIXED_DT = 1.0 / FPS
DEFAULT_HOURS = 8.0
DEFAULT_MEMORY_SNAPSHOT_INTERVAL = 10_000
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

    original_perf_counter = time.perf_counter
    import engine.timer as timer_module

    timer_module.time.perf_counter = fake_clock.perf_counter
    try:
        yield
    finally:
        timer_module.time.perf_counter = original_perf_counter


@dataclass(frozen=True)
class AllocationDiff:
    """Top memory growth item from tracemalloc snapshot comparison."""

    location: str
    size_diff_bytes: int
    count_diff: int


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
    rare_interval_violations: int
    ambient_interval_violations: int
    timing_drift_seconds: float
    accumulation_drift_seconds: float
    avg_iteration_seconds: float
    memory_baseline_bytes: int
    memory_end_bytes: int
    memory_peak_bytes: int
    top_allocation_increases: list[AllocationDiff]
    rare_ratio_warning: str | None
    weather_counts: dict[str, int]
    time_of_day_counts: dict[str, int]
    night_clear_frames: int
    day_clear_frames: int
    sunset_clear_frames: int
    rare_eligibility_summary: dict[str, dict[str, int]]




def identify_rare_events(events: list[SceneEvent]) -> set[str]:
    """Use explicit event type to identify rare events."""

    return {event.name for event in events if event.event_type == "rare"}


def _format_seconds(seconds: float) -> str:
    return f"{seconds:.6f}s"


def _format_trace_location(trace: tracemalloc.StatisticDiff) -> str:
    frame = trace.traceback[0]
    path = Path(frame.filename)
    try:
        display_path = path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        display_path = path
    return f"{display_path}:{frame.lineno}"


def _filtered_snapshot() -> tracemalloc.Snapshot:
    return tracemalloc.take_snapshot().filter_traces(
        (
            tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
            tracemalloc.Filter(False, "<frozen importlib._bootstrap_external>"),
            tracemalloc.Filter(False, "*/tracemalloc.py"),
        )
    )


def _top_growth(
    baseline_snapshot: tracemalloc.Snapshot,
    current_snapshot: tracemalloc.Snapshot,
    limit: int = 5,
) -> list[AllocationDiff]:
    diffs = current_snapshot.compare_to(baseline_snapshot, "lineno")
    growth = [diff for diff in diffs if diff.size_diff > 0]
    return [
        AllocationDiff(
            location=_format_trace_location(diff),
            size_diff_bytes=diff.size_diff,
            count_diff=diff.count_diff,
        )
        for diff in growth[:limit]
    ]


def run_simulation(
    hours: float,
    seed: int | None,
    debug: bool,
    profile_climate: bool,
    debug_eligibility: bool,
    trace_rare: bool,
    memory_snapshot_interval: int,
) -> SimulationStats:
    """Execute deterministic burn-in loop and return captured metrics."""

    if seed is not None:
        random.seed(seed)

    target_seconds = hours * 3600.0
    total_frames = int(target_seconds * FPS)

    fake_clock = FakePerfClock()
    event_counts: dict[str, int] = defaultdict(int)
    trigger_count = 0
    event_intervals_by_id: dict[str, list[float]] = defaultdict(list)

    cooldown_violations = 0
    min_runtime_violations = 0
    rare_interval_violations = 0
    ambient_interval_violations = 0
    max_simultaneous_events = 0

    iteration_total_seconds = 0.0
    delta_accumulator = 0.0
    weather_counts: dict[str, int] = defaultdict(int)
    time_of_day_counts: dict[str, int] = defaultdict(int)
    night_clear_frames = 0
    day_clear_frames = 0
    sunset_clear_frames = 0
    rare_eligibility_summary: dict[str, dict[str, int]] = {}

    tracemalloc.start()
    memory_baseline_bytes = 0
    baseline_snapshot: tracemalloc.Snapshot | None = None
    latest_top_growth: list[AllocationDiff] = []

    with patched_perf_counter(fake_clock):
        timer = SessionTimer()
        manager = EventManager(str(EVENT_FILE), trace_rare=trace_rare)
        day_cycle = DayCycle()
        weather = WeatherSystem()
        memory_baseline_bytes = tracemalloc.get_traced_memory()[0]
        baseline_snapshot = _filtered_snapshot()

        if debug_eligibility:
            rare_eligibility_summary = {
                event.name: {
                    "eligible": 0,
                    "weather mismatch": 0,
                    "time_of_day mismatch": 0,
                    "cooldown": 0,
                    "min_runtime": 0,
                    "no conditions": 0,
                }
                for event in manager.events
                if event.event_type == "rare"
            }

        if debug:
            print(f"Loaded events: {[event.name for event in manager.events]}")

        last_trigger_by_event: dict[str, float] = {}
        previous_event_trigger_time: float | None = None
        previous_rare_time: float | None = None
        previous_ambient_time: float | None = None

        for frame in range(total_frames):
            loop_start = time.process_time_ns()

            fake_clock.advance(FIXED_DT)
            delta_time = timer.tick()
            delta_accumulator += delta_time

            weather.update(timer.session_time)
            current_time_of_day = day_cycle.get_time_of_day(timer.session_time)
            current_weather = weather.get_current_weather(timer.session_time)
            environment = {"time_of_day": current_time_of_day, "weather": current_weather}

            if profile_climate:
                weather_counts[current_weather] += 1
                time_of_day_counts[current_time_of_day] += 1
                if current_weather == "clear":
                    if current_time_of_day == "night":
                        night_clear_frames += 1
                    if current_time_of_day == "day":
                        day_clear_frames += 1
                    if current_time_of_day == "sunset":
                        sunset_clear_frames += 1

            if debug_eligibility and manager.active_event is None and manager._rare_slot_open(timer.session_time):
                rare_events = [event for event in manager.events if event.event_type == "rare"]
                print(f"[eligibility] t={timer.session_time:.3f} rare slot check")
                print(f"[eligibility] rares={', '.join(event.name for event in rare_events)}")
                for event in rare_events:
                    event_summary = rare_eligibility_summary[event.name]

                    reasons: list[str] = []
                    if timer.session_time < event.min_runtime:
                        reasons.append("min_runtime")
                    if manager._time_since_event(timer.session_time, event.name) < event.cooldown:
                        reasons.append("cooldown")

                    weather_allowed = event.conditions.get("weather")
                    if weather_allowed is not None and current_weather not in weather_allowed:
                        reasons.append("weather mismatch")

                    time_allowed = event.conditions.get("time_of_day")
                    if time_allowed is not None and current_time_of_day not in time_allowed:
                        reasons.append("time_of_day mismatch")

                    if not event.conditions:
                        reasons.append("no conditions")

                    eligible = manager._is_event_eligible(event, timer.session_time, environment)
                    if eligible:
                        event_summary["eligible"] += 1
                        print(f"  - {event.name}: Eligible=True")
                    else:
                        for reason in reasons:
                            if reason in event_summary:
                                event_summary[reason] += 1
                        reason_text = ", ".join(reasons) if reasons else "unknown"
                        print(f"  - {event.name}: Eligible=False ({reason_text})")

            event_before = manager.active_event
            manager.update(delta_time, timer, environment if trace_rare else None)
            active_count = 1 if manager.active_event is not None else 0
            max_simultaneous_events = max(max_simultaneous_events, active_count)

            event_after = manager.active_event
            if event_before is None and event_after is not None:
                event_counts[event_after.name] += 1
                trigger_count += 1

                if timer.session_time < event_after.min_runtime:
                    min_runtime_violations += 1

                previous_same = last_trigger_by_event.get(event_after.name)
                if previous_same is not None:
                    same_interval = timer.session_time - previous_same
                    event_intervals_by_id[event_after.name].append(same_interval)
                    if same_interval + 1e-9 < event_after.cooldown:
                        cooldown_violations += 1
                last_trigger_by_event[event_after.name] = timer.session_time

                if event_after.event_type == "rare":
                    if previous_rare_time is not None:
                        rare_interval = timer.session_time - previous_rare_time
                        if rare_interval + 1e-9 < manager.rare_min_interval:
                            rare_interval_violations += 1
                    previous_rare_time = timer.session_time
                else:
                    if previous_ambient_time is not None:
                        ambient_interval = timer.session_time - previous_ambient_time
                        if ambient_interval + 1e-9 < manager.ambient_min_interval:
                            ambient_interval_violations += 1
                    previous_ambient_time = timer.session_time

                if previous_event_trigger_time is not None:
                    interval = timer.session_time - previous_event_trigger_time
                    event_intervals_by_id["__all__"].append(interval)
                previous_event_trigger_time = timer.session_time

                if debug:
                    print(
                        f"frame={frame} t={timer.session_time:.3f} "
                        f"triggered={event_after.name} duration={event_after.duration}"
                    )

            if memory_snapshot_interval > 0 and (frame + 1) % memory_snapshot_interval == 0:
                latest_top_growth = (
                    _top_growth(baseline_snapshot, _filtered_snapshot())
                    if baseline_snapshot is not None
                    else []
                )
                if debug:
                    print(f"frame={frame + 1} top allocation changes:")
                    for change in latest_top_growth:
                        print(
                            f"  {change.location} +{change.size_diff_bytes} bytes "
                            f"({change.count_diff:+d} allocations)"
                        )

            loop_end = time.process_time_ns()
            iteration_total_seconds += (loop_end - loop_start) / 1_000_000_000

    memory_end, memory_peak = tracemalloc.get_traced_memory()
    end_snapshot = _filtered_snapshot()
    tracemalloc.stop()

    latest_top_growth = _top_growth(baseline_snapshot, end_snapshot) if baseline_snapshot is not None else []

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
    rare_event_total = sum(event_counts.get(name, 0) for name in rare_events)

    rare_ratio_warning = None
    if manager.events and rare_events and trigger_count > 0:
        total_weight = sum(event.weight for event in manager.events)
        rare_weight = sum(event.weight for event in manager.events if event.name in rare_events)
        expected_rare_ratio = rare_weight / total_weight if total_weight else 0.0
        observed_rare_ratio = rare_event_total / trigger_count
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
        total_events=trigger_count,
        event_counts=dict(sorted(event_counts.items())),
        average_interval=average_interval,
        event_intervals_by_id=event_interval_averages,
        rare_event_total=rare_event_total,
        max_simultaneous_events=max_simultaneous_events,
        cooldown_violations=cooldown_violations,
        min_runtime_violations=min_runtime_violations,
        rare_interval_violations=rare_interval_violations,
        ambient_interval_violations=ambient_interval_violations,
        timing_drift_seconds=timing_drift_seconds,
        accumulation_drift_seconds=accumulation_drift_seconds,
        avg_iteration_seconds=(iteration_total_seconds / total_frames) if total_frames > 0 else 0.0,
        memory_baseline_bytes=memory_baseline_bytes,
        memory_end_bytes=memory_end,
        memory_peak_bytes=memory_peak,
        top_allocation_increases=latest_top_growth,
        rare_ratio_warning=rare_ratio_warning,
        weather_counts=dict(sorted(weather_counts.items())),
        time_of_day_counts=dict(sorted(time_of_day_counts.items())),
        night_clear_frames=night_clear_frames,
        day_clear_frames=day_clear_frames,
        sunset_clear_frames=sunset_clear_frames,
        rare_eligibility_summary=rare_eligibility_summary,
    )


def _format_percentage(count: int, total: int) -> str:
    return f"{(100.0 * count / total):.2f}%" if total > 0 else "0.00%"


def print_report(
    hours: float,
    stats: SimulationStats,
    profile_climate: bool,
    debug_eligibility: bool,
) -> None:
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

    memory_delta = stats.memory_end_bytes - stats.memory_baseline_bytes
    print(f"Memory heap baseline: {stats.memory_baseline_bytes} bytes")
    print(f"Memory heap end: {stats.memory_end_bytes} bytes")
    print(f"Memory heap delta: {memory_delta} bytes")
    print(f"Memory peak: {stats.memory_peak_bytes} bytes")

    print("Top 5 allocation increases since baseline:")
    if not stats.top_allocation_increases:
        print("  (none)")
    else:
        for change in stats.top_allocation_increases:
            print(
                f"  {change.location} +{change.size_diff_bytes} bytes "
                f"({change.count_diff:+d} allocations)"
            )

    print(f"Timing drift (session_time - expected): {stats.timing_drift_seconds:.12f}s")
    print(f"Timing drift (sum(delta) - expected): {stats.accumulation_drift_seconds:.12f}s")

    print("\nValidation checks:")
    print(f"  Min runtime violations: {stats.min_runtime_violations}")
    print(f"  Cooldown violations: {stats.cooldown_violations}")
    print(f"  Rare interval violations: {stats.rare_interval_violations}")
    print(f"  Ambient interval violations: {stats.ambient_interval_violations}")
    print(f"  One-active-event invariant violations: {max(0, stats.max_simultaneous_events - 1)}")
    print(f"  Avg loop iteration wall time: {stats.avg_iteration_seconds * 1_000_000:.2f} µs")

    if stats.event_intervals_by_id:
        print("\nAverage interval by event id:")
        width = max(len(name) for name in stats.event_intervals_by_id)
        for event_name, avg in sorted(stats.event_intervals_by_id.items()):
            print(f"  {event_name:<{width}} : {_format_seconds(avg)}")

    if stats.rare_ratio_warning:
        print(f"WARNING: {stats.rare_ratio_warning}")

    if profile_climate:
        print("\n=== Climate Distribution ===")
        print("\nWeather distribution (% of frames):")
        for weather_name, count in stats.weather_counts.items():
            print(f"  {weather_name}: {_format_percentage(count, stats.total_frames)}")

        print("\nTime-of-day distribution (% of frames):")
        for time_of_day in ("day", "sunset", "night", "dawn"):
            count = stats.time_of_day_counts.get(time_of_day, 0)
            print(f"  {time_of_day}: {_format_percentage(count, stats.total_frames)}")

        print("\nOverlap (% of frames):")
        print(f"  night+clear: {_format_percentage(stats.night_clear_frames, stats.total_frames)}")
        print(f"  day+clear: {_format_percentage(stats.day_clear_frames, stats.total_frames)}")
        print(f"  sunset+clear: {_format_percentage(stats.sunset_clear_frames, stats.total_frames)}")

    if debug_eligibility:
        print("\n=== Rare Eligibility Summary ===")
        for event_name, counts in sorted(stats.rare_eligibility_summary.items()):
            print(f"\n{event_name}:")
            print(f"  Times eligible: {counts['eligible']}")
            print(f"  Rejected (weather mismatch): {counts['weather mismatch']}")
            print(f"  Rejected (time_of_day mismatch): {counts['time_of_day mismatch']}")
            print(f"  Rejected (cooldown): {counts['cooldown']}")
            print(f"  Rejected (min_runtime): {counts['min_runtime']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Headless burn-in simulation for event timing.")
    parser.add_argument("--seed", type=int, default=None, help="Fixed RNG seed for deterministic runs")
    parser.add_argument("--hours", type=float, default=DEFAULT_HOURS, help="Simulated hours to run")
    parser.add_argument("--debug", action="store_true", help="Print per-trigger and memory debug output")
    parser.add_argument(
        "--profile-climate",
        action="store_true",
        help="Enable climate distribution diagnostics",
    )
    parser.add_argument(
        "--debug-eligibility",
        action="store_true",
        help="Print rare-slot eligibility diagnostics and summary",
    )
    parser.add_argument(
        "--trace-rare",
        action="store_true",
        help="Enable structured rare-event selection tracing",
    )
    parser.add_argument(
        "--memory-snapshot-interval",
        type=int,
        default=DEFAULT_MEMORY_SNAPSHOT_INTERVAL,
        help="Frames between memory snapshot comparisons (0 disables interval comparisons)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = run_simulation(
        hours=args.hours,
        seed=args.seed,
        debug=args.debug,
        profile_climate=args.profile_climate,
        debug_eligibility=args.debug_eligibility,
        trace_rare=args.trace_rare,
        memory_snapshot_interval=args.memory_snapshot_interval,
    )
    print_report(
        hours=args.hours,
        stats=stats,
        profile_climate=args.profile_climate,
        debug_eligibility=args.debug_eligibility,
    )


if __name__ == "__main__":
    main()
