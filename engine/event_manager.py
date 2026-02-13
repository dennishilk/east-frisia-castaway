"""Event loading and scheduling for ambient scene actions."""

from __future__ import annotations

import json
import logging
import math
import random
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pygame

from engine.timer import SessionTimer

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventPhase:
    """Single phase definition for multi-step events."""

    phase_type: str
    duration: float


@dataclass(frozen=True)
class SceneEvent:
    """Data model for a single timed ambient event."""

    name: str
    event_type: str
    weight: int
    cooldown: float
    min_runtime: float
    duration: float
    color: tuple[int, int, int]
    phases: tuple[EventPhase, ...]
    conditions: dict[str, tuple[str, ...]]
    rare_tier: int


class EventManager:
    """Control weighted event selection and active event lifecycle.

    At most one event can be active at once. Event cooldown and activation gates
    are evaluated against absolute session time from :class:`SessionTimer`.
    """

    def __init__(self, event_file: str, trace_rare: bool = False) -> None:
        self.rare_min_interval = 600.0
        self.rare_retry_interval = 30.0
        self.ambient_min_interval = 5.0
        self.events = self._load_events(event_file)
        self._ambient_events = tuple(event for event in self.events if event.event_type != "rare")
        self._rare_events = tuple(event for event in self.events if event.event_type == "rare")
        self._rare_tier1_events = tuple(event for event in self._rare_events if event.rare_tier == 1)
        self._rare_tier2_events = tuple(event for event in self._rare_events if event.rare_tier == 2)
        self.active_event: SceneEvent | None = None
        self._active_event_start_time = 0.0
        self._active_event_end_time = 0.0
        self._phase_timestamps: list[tuple[EventPhase, float, float]] = []
        self._font: pygame.font.Font | None = None
        self._current_session_time = 0.0
        self._event_state: dict[str, float] = {}
        self._last_event_time_by_name: dict[str, float] = {}
        self._next_rare_check_time = 0.0
        self._last_ambient_event_time = float("-inf")
        self._ferry_sprite = self._build_ferry_sprite()
        self._aurora_band: pygame.Surface | None = None
        self._aurora_band_width = 0
        self._trace_rare = trace_rare

    @staticmethod
    def _build_ferry_sprite() -> pygame.Surface:
        sprite = pygame.Surface((22, 7), pygame.SRCALPHA)
        silhouette = (34, 40, 52, 255)
        pygame.draw.rect(sprite, silhouette, pygame.Rect(0, 4, 22, 3))
        pygame.draw.rect(sprite, silhouette, pygame.Rect(6, 2, 8, 2))
        pygame.draw.rect(sprite, silhouette, pygame.Rect(8, 1, 2, 1))
        return sprite

    def _build_aurora_band(self, width: int) -> pygame.Surface:
        band = pygame.Surface((width, 24), pygame.SRCALPHA)
        for row in range(24):
            center_falloff = abs(11.5 - row) / 11.5
            alpha = int((1.0 - center_falloff) * 18)
            if alpha <= 0:
                continue
            green = 110 + row // 4
            pygame.draw.line(band, (92, green, 112, alpha), (0, row), (width - 1, row))

        for x in range(0, width, 6):
            band.set_at((x, 11), (118, 166, 126, 20))
            if x + 2 < width:
                band.set_at((x + 2, 13), (108, 156, 118, 14))
        return band

    def _load_events(self, event_file: str) -> list[SceneEvent]:
        """Load and validate event definitions from JSON configuration."""
        raw_data = json.loads(Path(event_file).read_text(encoding="utf-8"))
        self._load_scheduler_config(raw_data)
        raw_events = raw_data.get("events", [])
        if not isinstance(raw_events, list):
            LOGGER.warning("Ignoring malformed event list in %s", event_file)
            return []

        loaded_events: list[SceneEvent] = []
        for index, entry in enumerate(raw_events):
            event = self._parse_event_entry(entry, index)
            if event is not None:
                loaded_events.append(event)

        return loaded_events

    def _load_scheduler_config(self, raw_data: dict[str, Any]) -> None:
        scheduler = raw_data.get("scheduler", {})
        if not isinstance(scheduler, dict):
            return

        rare_min_interval = scheduler.get("rare_min_interval")
        rare_retry_interval = scheduler.get("rare_retry_interval")
        ambient_min_interval = scheduler.get("ambient_min_interval")

        if isinstance(rare_min_interval, (int, float)) and rare_min_interval >= 0.0:
            self.rare_min_interval = float(rare_min_interval)
        if isinstance(rare_retry_interval, (int, float)) and rare_retry_interval >= 0.0:
            self.rare_retry_interval = float(rare_retry_interval)
        if isinstance(ambient_min_interval, (int, float)) and ambient_min_interval >= 0.0:
            self.ambient_min_interval = float(ambient_min_interval)

    def _parse_phases(self, entry: dict[str, Any], index: int) -> tuple[tuple[EventPhase, ...], float] | None:
        phases_raw = entry.get("phases")
        if phases_raw is None:
            try:
                duration = float(entry["duration"])
            except (KeyError, TypeError, ValueError):
                LOGGER.warning("Skipping event[%d]: missing duration", index)
                return None
            if duration <= 0.0:
                LOGGER.warning("Skipping event[%d]: duration must be > 0", index)
                return None
            return (), duration

        if not isinstance(phases_raw, list) or not phases_raw:
            LOGGER.warning("Skipping event[%d]: phases must be a non-empty list", index)
            return None

        phases: list[EventPhase] = []
        total_duration = 0.0
        for phase_index, phase_entry in enumerate(phases_raw):
            if not isinstance(phase_entry, dict):
                LOGGER.warning("Skipping event[%d]: invalid phase[%d]", index, phase_index)
                return None
            try:
                phase_type = str(phase_entry["type"])
                phase_duration = float(phase_entry["duration"])
            except (KeyError, TypeError, ValueError):
                LOGGER.warning("Skipping event[%d]: malformed phase[%d]", index, phase_index)
                return None
            if phase_duration <= 0.0:
                LOGGER.warning("Skipping event[%d]: phase[%d] duration must be > 0", index, phase_index)
                return None
            total_duration += phase_duration
            phases.append(EventPhase(phase_type=phase_type, duration=phase_duration))

        return tuple(phases), total_duration

    def _parse_conditions(self, entry: dict[str, Any], index: int) -> dict[str, tuple[str, ...]]:
        conditions_raw = entry.get("conditions", {})
        if not isinstance(conditions_raw, dict):
            LOGGER.warning("Ignoring conditions for event[%d]: expected object", index)
            return {}

        conditions: dict[str, tuple[str, ...]] = {}
        for key, value in conditions_raw.items():
            if isinstance(value, list) and all(isinstance(item, str) for item in value) and value:
                conditions[str(key)] = tuple(value)
            else:
                LOGGER.warning("Ignoring malformed condition %s for event[%d]", key, index)
        return conditions

    def _parse_event_entry(self, entry: Any, index: int) -> SceneEvent | None:
        """Convert a raw JSON entry into a validated :class:`SceneEvent`."""
        if not isinstance(entry, dict):
            LOGGER.warning("Skipping event[%d]: entry is not an object", index)
            return None

        try:
            name = str(entry.get("id", entry.get("name")))
            event_type = str(entry.get("type", "ambient"))
            weight = int(entry["weight"])
            cooldown = float(entry["cooldown"])
            min_runtime = float(entry["min_runtime"])
            color_raw = entry.get("color", [100, 116, 132])
        except (TypeError, ValueError, KeyError) as error:
            LOGGER.warning("Skipping event[%d]: invalid schema (%s)", index, error)
            return None

        if not name or name == "None":
            LOGGER.warning("Skipping event[%d]: missing id/name", index)
            return None

        phase_parse = self._parse_phases(entry, index)
        if phase_parse is None:
            return None
        phases, duration = phase_parse
        conditions = self._parse_conditions(entry, index)
        rare_tier = self._parse_rare_tier(entry, index, event_type, conditions)

        if weight <= 0 or cooldown < 0.0 or min_runtime < 0.0 or duration <= 0.0:
            LOGGER.warning("Skipping event[%d]: invalid numeric ranges", index)
            return None

        if (
            not isinstance(color_raw, list)
            or len(color_raw) != 3
            or any(not isinstance(channel, (int, float)) for channel in color_raw)
        ):
            LOGGER.warning("Skipping event[%d]: color must be a 3-item numeric list", index)
            return None

        color = tuple(max(0, min(255, int(channel))) for channel in color_raw)
        return SceneEvent(
            name=name,
            event_type=event_type,
            weight=weight,
            cooldown=cooldown,
            min_runtime=min_runtime,
            duration=duration,
            color=color,
            phases=phases,
            conditions=conditions,
            rare_tier=rare_tier,
        )

    def _parse_rare_tier(
        self,
        entry: dict[str, Any],
        index: int,
        event_type: str,
        conditions: dict[str, tuple[str, ...]],
    ) -> int:
        if event_type != "rare":
            return 0

        scheduler = entry.get("scheduler", {})
        if isinstance(scheduler, dict):
            tier = scheduler.get("tier")
            if tier in (1, 2):
                return int(tier)
            if tier is not None:
                LOGGER.warning("Ignoring invalid scheduler.tier for event[%d]", index)

        return 1 if conditions else 2

    def _matches_conditions(self, event: SceneEvent, environment: dict[str, str] | None) -> bool:
        if not event.conditions:
            return True
        if environment is None:
            return False

        for key, allowed in event.conditions.items():
            current = environment.get(key)
            if current not in allowed:
                return False
        return True

    def _time_since_event(self, session_time: float, event_name: str) -> float:
        last_trigger = self._last_event_time_by_name.get(event_name)
        if last_trigger is None:
            return float("inf")
        return max(0.0, session_time - last_trigger)

    def _is_event_eligible(
        self,
        event: SceneEvent,
        session_time: float,
        environment: dict[str, str] | None,
    ) -> bool:
        return (
            session_time >= event.min_runtime
            and self._time_since_event(session_time, event.name) >= event.cooldown
            and self._matches_conditions(event, environment)
        )

    def _eligible_pool(
        self,
        events: tuple[SceneEvent, ...],
        session_time: float,
        environment: dict[str, str] | None,
    ) -> list[SceneEvent]:
        return [event for event in events if self._is_event_eligible(event, session_time, environment)]

    def _rare_slot_open(self, session_time: float) -> bool:
        return session_time >= self._next_rare_check_time

    def _ambient_slot_open(self, session_time: float) -> bool:
        return (session_time - self._last_ambient_event_time) >= self.ambient_min_interval

    @staticmethod
    def _rng_state_signature() -> dict[str, Any]:
        state = random.getstate()
        version, internal_state, gauss_next = state
        internal_state = tuple(internal_state)
        preview = list(internal_state[:5])
        state_hash = hashlib.sha1(repr(state).encode("utf-8")).hexdigest()[:12]
        return {
            "version": version,
            "index": internal_state[-1],
            "preview": preview,
            "gauss_next": gauss_next,
            "state_hash": state_hash,
        }

    def _trace_rare_selection(
        self,
        session_time: float,
        environment: dict[str, str] | None,
        tier1_eligible: list[SceneEvent],
        tier2_eligible: list[SceneEvent],
        selected_event: SceneEvent | None,
        selected_tier: int | None,
        rng_state_used: dict[str, Any] | None,
    ) -> None:
        if not self._trace_rare:
            return

        all_rare = sorted(self._rare_events, key=lambda event: event.name)
        tier1_names = {event.name for event in tier1_eligible}
        tier2_names = {event.name for event in tier2_eligible}
        selected_pool_names = tier1_names if tier1_eligible else tier2_names

        event_rows: list[dict[str, Any]] = []
        non_selected_reasons: dict[str, str] = {}

        for event in all_rare:
            time_since = self._time_since_event(session_time, event.name)
            cooldown_left = max(0.0, event.cooldown - time_since)
            conditions_exist = bool(event.conditions)
            conditions_satisfied = self._matches_conditions(event, environment)
            eligible = self._is_event_eligible(event, session_time, environment)
            tier_classification = "Tier1" if conditions_exist else "Tier2"

            if eligible and selected_event is not None and event.name != selected_event.name:
                if event.name not in selected_pool_names:
                    non_selected_reasons[event.name] = "higher priority tier had eligible events"
                else:
                    non_selected_reasons[event.name] = "weighted RNG selection"
            elif eligible and selected_event is None:
                if event.name not in selected_pool_names:
                    non_selected_reasons[event.name] = "higher priority tier had eligible events"
                else:
                    non_selected_reasons[event.name] = "no event selected"
            elif not eligible:
                if session_time < event.min_runtime:
                    non_selected_reasons[event.name] = "min_runtime gate"
                elif cooldown_left > 0.0:
                    non_selected_reasons[event.name] = "cooldown gate"
                elif not conditions_satisfied:
                    non_selected_reasons[event.name] = "conditions mismatch"

            event_rows.append(
                {
                    "id": event.name,
                    "weight": event.weight,
                    "min_runtime": event.min_runtime,
                    "cooldown_left": round(cooldown_left, 3),
                    "conditions_exist": conditions_exist,
                    "conditions_satisfied": conditions_satisfied,
                    "eligible": eligible,
                    "tier": tier_classification,
                }
            )

        selection_pool = tier1_eligible if tier1_eligible else tier2_eligible
        total_weight = sum(event.weight for event in selection_pool)
        trace_payload = {
            "session_time": round(session_time, 3),
            "environment": {
                "time_of_day": None if environment is None else environment.get("time_of_day"),
                "weather": None if environment is None else environment.get("weather"),
            },
            "rare_events": event_rows,
            "tier1_eligible": [{"id": event.name, "weight": event.weight} for event in tier1_eligible],
            "tier2_eligible": [{"id": event.name, "weight": event.weight} for event in tier2_eligible],
            "selection_tier_used": selected_tier,
            "combined_weight_for_selection": total_weight,
            "rng_state_used": rng_state_used,
            "chosen_event_id": None if selected_event is None else selected_event.name,
            "not_chosen_reasons": non_selected_reasons,
        }
        print(f"[rare-trace] {json.dumps(trace_payload, sort_keys=True)}")

    def _build_phase_timestamps(self, event: SceneEvent, start_time: float) -> None:
        self._phase_timestamps = []
        cursor = start_time
        for phase in event.phases:
            phase_start = cursor
            phase_end = cursor + phase.duration
            self._phase_timestamps.append((phase, phase_start, phase_end))
            cursor = phase_end

    def get_current_phase(self, session_time: float) -> EventPhase | None:
        """Return active phase for the current event using absolute timestamps."""
        for phase, start, end in self._phase_timestamps:
            if start <= session_time < end:
                return phase

        if self._phase_timestamps and session_time >= self._phase_timestamps[-1][2]:
            return self._phase_timestamps[-1][0]
        return None

    def activate(self, timer: SessionTimer, environment: dict[str, str] | None = None) -> None:
        """Activate one weighted random event if no event is currently active."""
        if self.active_event is not None:
            return

        session_time = timer.session_time
        selected_event: SceneEvent | None = None

        rare_evaluated = False
        if self._rare_slot_open(session_time):
            rare_evaluated = True
            rare_eligible_tier1 = self._eligible_pool(self._rare_tier1_events, session_time, environment)
            selected_tier: int | None = None
            rng_state_used: dict[str, Any] | None = None
            if rare_eligible_tier1:
                selected_tier = 1
                rng_state_used = self._rng_state_signature()
                selected_event = random.choices(
                    rare_eligible_tier1,
                    weights=[event.weight for event in rare_eligible_tier1],
                    k=1,
                )[0]
            else:
                rare_eligible_tier2 = self._eligible_pool(self._rare_tier2_events, session_time, environment)
                if rare_eligible_tier2:
                    selected_tier = 2
                    rng_state_used = self._rng_state_signature()
                    selected_event = random.choices(
                        rare_eligible_tier2,
                        weights=[event.weight for event in rare_eligible_tier2],
                        k=1,
                    )[0]
                self._trace_rare_selection(
                    session_time,
                    environment,
                    rare_eligible_tier1,
                    rare_eligible_tier2,
                    selected_event,
                    selected_tier,
                    rng_state_used,
                )

            if rare_eligible_tier1:
                self._trace_rare_selection(
                    session_time,
                    environment,
                    rare_eligible_tier1,
                    [],
                    selected_event,
                    selected_tier,
                    rng_state_used,
                )

            if selected_event is None:
                self._next_rare_check_time = session_time + self.rare_retry_interval

        if selected_event is None and self._ambient_slot_open(session_time):
            ambient_eligible = self._eligible_pool(self._ambient_events, session_time, environment)
            if ambient_eligible:
                selected_event = random.choices(
                    ambient_eligible,
                    weights=[event.weight for event in ambient_eligible],
                    k=1,
                )[0]

        if selected_event is None:
            return

        self.active_event = selected_event
        self._active_event_start_time = session_time
        self._active_event_end_time = session_time + self.active_event.duration
        self._build_phase_timestamps(self.active_event, session_time)
        self._event_state = self._build_event_state(self.active_event)
        self._last_event_time_by_name[self.active_event.name] = session_time
        if self.active_event.event_type == "rare":
            self._next_rare_check_time = session_time + self.rare_min_interval
        else:
            self._last_ambient_event_time = session_time

        if rare_evaluated and self.active_event.event_type != "rare":
            self._next_rare_check_time = session_time + self.rare_retry_interval
        timer.mark_event_triggered()

    @staticmethod
    def _build_event_state(event: SceneEvent) -> dict[str, float]:
        if event.name == "shooting_star":
            return {
                "start_x_factor": random.uniform(0.1, 0.85),
                "start_y": random.uniform(8.0, 50.0),
                "delta_x": random.uniform(16.0, 30.0),
                "delta_y": random.uniform(8.0, 16.0),
            }
        if event.name == "aurora_faint":
            return {
                "shimmer_phase": random.uniform(0.0, math.tau),
                "base_y": random.uniform(18.0, 28.0),
                "max_alpha": random.uniform(16.0, 26.0),
            }
        return {}

    def update(
        self,
        _delta_time: float,
        timer: SessionTimer,
        environment: dict[str, str] | None = None,
    ) -> None:
        """Update active event state and schedule the next event when idle."""
        self._current_session_time = timer.session_time

        if self.active_event is None:
            self.activate(timer, environment)
            return

        if timer.session_time >= self._active_event_end_time:
            self.active_event = None
            self._active_event_start_time = 0.0
            self._active_event_end_time = 0.0
            self._phase_timestamps = []
            self._event_state = {}

    def _ensure_font(self) -> pygame.font.Font | None:
        if not pygame.font.get_init():
            return None
        if self._font is None:
            self._font = pygame.font.Font(None, 12)
        return self._font

    def _render_borkum_buoy(self, surface: pygame.Surface) -> None:
        if self.active_event is None:
            return

        now = max(self._active_event_start_time, min(self._active_event_end_time, self._current_session_time))
        elapsed = now - self._active_event_start_time
        progress = elapsed / self.active_event.duration if self.active_event.duration > 0 else 1.0

        x = int(-24 + (surface.get_width() + 48) * progress)
        bob = int(round(math.sin(elapsed * 1.6) * 2.0))
        y = surface.get_height() // 2 + 44 + bob

        alpha = 180
        phase = self.get_current_phase(self._active_event_start_time + elapsed)
        if phase is not None:
            if phase.phase_type == "approach":
                phase_duration = max(0.01, phase.duration)
                alpha = int(70 + 110 * min(1.0, elapsed / phase_duration))
            elif phase.phase_type == "fade":
                remaining = max(0.0, self._active_event_end_time - (self._active_event_start_time + elapsed))
                phase_duration = max(0.01, phase.duration)
                alpha = int(180 * min(1.0, remaining / phase_duration))

        buoy_layer = pygame.Surface((40, 16), pygame.SRCALPHA)
        pygame.draw.rect(buoy_layer, (176, 72, 48, alpha), pygame.Rect(4, 6, 10, 7))
        pygame.draw.rect(buoy_layer, (190, 188, 180, alpha), pygame.Rect(8, 1, 2, 5))

        font = self._ensure_font()
        if font is not None:
            label = font.render("Borkum", True, (225, 215, 184))
            buoy_layer.blit(label, (14, 5))

        surface.blit(buoy_layer, (x, y))

    def _render_distant_ferry(self, surface: pygame.Surface) -> None:
        if self.active_event is None:
            return

        now = max(self._active_event_start_time, min(self._active_event_end_time, self._current_session_time))
        elapsed = now - self._active_event_start_time
        progress = elapsed / self.active_event.duration if self.active_event.duration > 0 else 1.0

        ferry_width = self._ferry_sprite.get_width()
        travel = surface.get_width() + ferry_width + 16
        x = int(-ferry_width + progress * travel)
        y = surface.get_height() // 2 + 17

        alpha = 80
        phase = self.get_current_phase(now)
        if phase is not None:
            if phase.phase_type == "approach":
                phase_elapsed = now - self._active_event_start_time
                alpha = int(30 + 50 * min(1.0, phase_elapsed / max(phase.duration, 0.01)))
            elif phase.phase_type == "fade":
                remaining = max(0.0, self._active_event_end_time - now)
                alpha = int(80 * min(1.0, remaining / max(phase.duration, 0.01)))

        self._ferry_sprite.set_alpha(max(0, min(90, alpha)))
        surface.blit(self._ferry_sprite, (x, y))

    def _render_shooting_star(self, surface: pygame.Surface) -> None:
        if self.active_event is None:
            return

        now = max(self._active_event_start_time, min(self._active_event_end_time, self._current_session_time))
        progress = (now - self._active_event_start_time) / max(self.active_event.duration, 0.01)

        start_x = int(self._event_state.get("start_x_factor", 0.5) * surface.get_width())
        start_y = int(self._event_state.get("start_y", 20.0))
        delta_x = self._event_state.get("delta_x", 24.0)
        delta_y = self._event_state.get("delta_y", 12.0)

        head_x = int(start_x + delta_x * progress)
        head_y = int(start_y + delta_y * progress)
        tail_x = int(head_x - 5)
        tail_y = int(head_y - 2)

        brightness = 255
        phase = self.get_current_phase(now)
        if phase is not None and phase.phase_type == "fade":
            remaining = max(0.0, self._active_event_end_time - now)
            brightness = int(255 * min(1.0, remaining / max(phase.duration, 0.01)))

        color = (brightness, brightness, min(255, brightness + 4))
        pygame.draw.line(surface, color, (tail_x, tail_y), (head_x, head_y), 1)
        surface.set_at((head_x, head_y), color)

    def _render_faint_aurora(self, surface: pygame.Surface) -> None:
        if self.active_event is None:
            return
        width = surface.get_width()
        if self._aurora_band is None or self._aurora_band_width != width:
            self._aurora_band = self._build_aurora_band(width)
            self._aurora_band_width = width

        now = max(self._active_event_start_time, min(self._active_event_end_time, self._current_session_time))
        phase_offset = self._event_state.get("shimmer_phase", 0.0)
        shimmer = math.sin(now * 0.2 + phase_offset)
        y = int(self._event_state.get("base_y", 24.0) + shimmer * 2.0)

        alpha = int(self._event_state.get("max_alpha", 20.0))
        phase = self.get_current_phase(now)
        if phase is not None:
            if phase.phase_type == "fade":
                remaining = max(0.0, self._active_event_end_time - now)
                alpha = int(alpha * min(1.0, remaining / max(phase.duration, 0.01)))
            elif phase.phase_type == "approach":
                elapsed = max(0.0, now - self._active_event_start_time)
                alpha = int(alpha * min(1.0, elapsed / max(phase.duration, 0.01)))

        self._aurora_band.set_alpha(max(0, min(32, alpha)))
        surface.blit(self._aurora_band, (0, y))

    def render(self, surface: pygame.Surface) -> None:
        """Render active event visuals."""
        if self.active_event is None:
            return

        if self.active_event.name == "borkum_buoy":
            self._render_borkum_buoy(surface)
            return

        if self.active_event.name == "distant_ferry":
            self._render_distant_ferry(surface)
            return

        if self.active_event.name == "shooting_star":
            self._render_shooting_star(surface)
            return

        if self.active_event.name == "aurora_faint":
            self._render_faint_aurora(surface)
            return

        pygame.draw.rect(surface, self.active_event.color, pygame.Rect(0, 6, surface.get_width(), 8))
