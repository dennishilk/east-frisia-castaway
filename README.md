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
