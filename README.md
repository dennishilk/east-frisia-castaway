# East Frisia Castaway

East Frisia Castaway is a fully original Linux X11 screensaver built with Python and Pygame. It presents a calm, nostalgic, low-resolution island scene with subtle movement and lightweight ambient events.

This project is **not a game**. It contains no menus, no user interface, and no gameplay systems. It is designed to behave like a traditional fullscreen screensaver.

## Phase 2 Overview: Atmosphere Expansion

Phase 2 expands the atmosphere while preserving the stable Phase 1 runtime behavior:

- A smooth day/night lighting cycle with soft transitions
- A gradual weather system (clear ↔ cloudy)
- Multi-step events driven by absolute timestamps
- A rare drifting buoy event labeled **"Borkum"**
- Preserved fixed **20 FPS**, fullscreen scaling, and instant-exit behavior

## Features

- Fully original concept and art direction
- Internal rendering resolution of **320x200** for retro aesthetics
- Fullscreen output scaled from internal resolution
- Fixed **20 FPS** update and render cadence
- Immediate exit on any keyboard or mouse interaction
- Modular event system with weighted random event selection
- Cooldown and minimum-runtime gating for event pacing
- Day/night and weather layers designed for calm, minimal visuals
- Expandable architecture for future environmental systems

## Day/Night System

- Implemented as a modular `DayCycle` component (`engine/day_cycle.py`)
- Default cycle length is 30 real-time minutes
- Time-of-day labels: `dawn`, `day`, `sunset`, `night`
- Uses smooth interpolation and a subtle semi-transparent overlay
- Avoids abrupt shifts and extreme darkness

## Weather System

- Implemented as a modular `WeatherSystem` component (`engine/weather.py`)
- States: `clear` and `cloudy`
- Slow transition and hold durations (default range: 2–5 minutes)
- Gradual tint blending, plus optional slow placeholder cloud bands
- Logic remains headless-safe and does not depend on a display

## Event System (Multi-Step + Conditions)

- Events are data-driven from `events/events.json`
- Supports optional phase-based definitions with absolute phase timestamps
- Supports optional environmental conditions:
  - `time_of_day`
  - `weather`
- Still enforces one active event at a time for stable pacing

### Rare Event: Borkum Buoy

- Event ID: `borkum_buoy`
- Appears rarely, only in clear `day` or `sunset` conditions
- Small drifting buoy with subtle bobbing and pixel text "Borkum"
- Designed as a quiet atmospheric reference with no interaction or sound

## Installation

### Requirements

- Python 3.10+
- X11 session (Debian, Arch Linux, or NixOS)

### Setup

```bash
git clone https://github.com/your-user/east-frisia-castaway.git
cd east-frisia-castaway
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Run the screensaver directly:

```bash
python main.py
```

Behavior details:

- Opens in fullscreen mode
- Renders scene at 320x200 and scales to your display
- Runs at 20 FPS
- Exits instantly on any key press, mouse movement, or mouse button press

## XScreenSaver Integration

The runtime now includes launch modes that map cleanly to XScreenSaver embedding behavior.

### Fullscreen mode

Default launch behavior remains fullscreen. You can run this explicitly as well:

```bash
python main.py --fullscreen
```

### Window ID mode

To render into an externally managed X11 window (such as one created by XScreenSaver), pass its numeric window ID:

```bash
python main.py --window-id 123456
```

In this mode, the application renders into the provided window and does not request fullscreen or override the display resolution.

### Root window mode

To render directly into the X11 root window:

```bash
python main.py --root
```

This mode behaves like `--window-id` after resolving the root window ID automatically.

### Preview mode

For local preview without fullscreen:

```bash
python main.py --preview
```

Preview opens a `640x400` window (2× integer scale of the internal `320x200` render surface).

### Debug mode

Enable minimal structured console logging:

```bash
python main.py --debug
```

Without `--debug`, runtime output is suppressed.

An installation helper script for end-to-end XScreenSaver deployment is planned for an upcoming phase.

## Project Structure

```text
east-frisia-castaway/
├── main.py
├── engine/
│   ├── scene.py
│   ├── day_cycle.py
│   ├── weather.py
│   ├── event_manager.py
│   └── timer.py
├── assets/
│   ├── sprites/
│   └── backgrounds/
├── events/
│   └── events.json
├── tests/
│   └── burn_in_simulation.py
├── README.md
├── LICENSE
└── requirements.txt
```

## Roadmap

### Phase 3

- Add richer hand-crafted atmospheric event variants
- Improve sprite detailing while keeping low-resolution constraints
- Integrate with XScreenSaver packaging and deployment flow

## Upcoming Integration

XScreenSaver integration is planned in an upcoming phase, with packaging and launch behavior aligned to the current stable runtime profile.

## Originality Statement

East Frisia Castaway is a fully original project concept, visual direction, and implementation. It does not use copyrighted characters, stories, or direct references to existing commercial screensaver properties.
