# East Frisia Castaway

East Frisia Castaway is a fully original Linux X11 screensaver built with Python and Pygame. It presents a calm, nostalgic, low-resolution island scene with subtle movement and lightweight ambient events.

This project is **not a game**. It contains no menus, no user interface, and no gameplay systems. It is designed to behave like a traditional fullscreen screensaver.

## Features

- Fully original concept and art direction
- Internal rendering resolution of **320x200** for retro aesthetics
- Fullscreen output scaled from internal resolution
- Fixed **20 FPS** update and render cadence
- Immediate exit on any keyboard or mouse interaction
- Modular event system with weighted random event selection
- Cooldown and minimum-runtime gating for event pacing
- Expandable architecture for future environmental systems

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

## Project Structure

```text
east-frisia-castaway/
├── main.py
├── engine/
│   ├── scene.py
│   ├── event_manager.py
│   └── timer.py
├── assets/
│   ├── sprites/
│   └── backgrounds/
├── events/
│   └── events.json
├── README.md
├── LICENSE
└── requirements.txt
```

- `main.py`: Application bootstrap, fullscreen setup, main loop, and exit handling
- `engine/scene.py`: Scene composition, placeholder visuals, and render orchestration
- `engine/event_manager.py`: Event loading, weighted selection, cooldown/runtime checks
- `engine/timer.py`: Session timing and delta-time tracking
- `events/events.json`: Data-driven event definitions

## Roadmap

### Phase 2

- Add layered weather states (fog, light drizzle, still nights)
- Introduce richer sprite-based idle animation
- Improve event visuals with subtle per-event overlays

### Phase 3

- Add a gentle day/night lighting cycle
- Expand rare event pool with long-runtime atmospheric moments
- Add deterministic seed mode for reproducible sessions

## Originality Statement

East Frisia Castaway is a fully original project concept, visual direction, and implementation. It does not use copyrighted characters, stories, or direct references to existing commercial screensaver properties.
