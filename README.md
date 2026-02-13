# East Frisia Castaway

East Frisia Castaway is a fully original Linux X11 screensaver built with Python and Pygame. It presents a calm, nostalgic, low-resolution island scene with subtle movement and lightweight ambient events.

This project is **not a game**. It contains no menus, no user interface, and no gameplay systems.

## Features

- Internal rendering at **320x200**, scaled with nearest-neighbor integer scaling
- Fixed **20 FPS** runtime cadence
- Immediate exit on user interaction (key press, mouse movement, mouse button, or close)
- Day/night cycle and weather transitions
- Multi-step conditional event system
- Burn-in simulation utility for long-running checks

## Requirements

- Python 3.10+
- Linux X11 session
- Dependencies from `requirements.txt`

## Setup

```bash
git clone https://github.com/your-user/east-frisia-castaway.git
cd east-frisia-castaway
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## XScreenSaver Integration

Use the wrapper command below in XScreenSaver:

```bash
east-frisia-castaway --window-id %w
```

### Modes

Preview mode:

```bash
east-frisia-castaway --preview
```

Standalone fullscreen mode:

```bash
east-frisia-castaway --fullscreen
```

Root-target mode (with graceful fallback):

```bash
east-frisia-castaway --root
```

Debug logging:

```bash
east-frisia-castaway --debug
```

If no explicit mode is provided and `XSCREENSAVER_WINDOW` exists, the wrapper defaults to window embedding automatically.

### Install / Uninstall

Install user-local wrapper and register in `~/.xscreensaver`:

```bash
./scripts/install_xscreensaver.sh
```

Uninstall wrapper and remove registration:

```bash
./scripts/uninstall_xscreensaver.sh
```

`xscreensaver-demo` / `xscreensaver-settings` manages `~/.xscreensaver` and should be used to review active programs.


## Ecological Event Scheduling

Event scheduling uses two independent internal pools:

- **Ambient pool** for frequent low-impact motion.
- **Rare pool** for scenic highlights that should still appear during long sessions.

Both pools evaluate event conditions (`weather`, `time_of_day`), per-event cooldown, and `min_runtime` against absolute session time. Rare events also use a global minimum spacing (`rare_min_interval`) so they remain uncommon without being starved by ambient traffic. Ambient events can keep flowing via their own spacing control (`ambient_min_interval`) when no rare slot is currently open.

The scheduler keeps visual behavior unchanged while improving long-run ecology in burn-in simulations.

### Rare Priority Tier System

Rare slots now resolve in two priority tiers:

- **Tier 1 (priority rares):** rare events with explicit conditions (or `"scheduler": {"tier": 1}`), such as `aurora_faint`, `shooting_star`, `distant_ferry`, and `borkum_buoy`.
- **Tier 2 (fallback rares):** rare events without conditions (or `"scheduler": {"tier": 2}`), such as `moon_glint`.

When a rare slot opens, the scheduler first checks eligible Tier 1 rares (runtime/cooldown/conditions). If none are eligible, it checks Tier 2. If no rare is eligible in either tier, ambient scheduling continues normally and the rare slot is retried on the next check.

## Atmospheric Tuning

Atmospheric frequency defaults are tuned for calmer long-run balance: `rare_min_interval` now defaults to 300s and `rare_retry_interval` to 20s (while still honoring scheduler values from `events/events.json` when present). Rare conditions were also softened so `aurora_faint` can appear during cloudy nights and `shooting_star` can appear at sunset, with subtle weight balancing (`moon_glint` reduced, `distant_ferry` increased) to keep fallback events from dominating burn-in runs.

## Project Structure

```text
east-frisia-castaway/
├── main.py
├── engine/
├── events/
├── scripts/
├── tests/
├── README.md
└── requirements.txt
```

## Originality Statement

East Frisia Castaway is a fully original project concept, visual direction, and implementation. It does not use copyrighted characters, stories, or direct references to existing commercial screensaver properties.
