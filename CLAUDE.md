# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Linux-only jukebox kiosk volume control service. Two Python scripts, no package manifest, no tests, no CI.

- **`pa_volume_server.py`** — threaded HTTP server that exposes volume control and SSE streaming over PulseAudio via `pactl`
- **`volume-indicator.py`** — GTK3/Cairo popup overlay spawned as a subprocess to display volume visually; requires `python3-gi` and a display

## Running

```bash
python3 pa_volume_server.py
```

Server listens on `http://localhost:8000`. Requires Linux with PulseAudio or PipeWire.

**Test the API manually:**
```bash
# Raise volume
curl -X POST -H "Content-Type: application/json" -d '{"action":"raise"}' http://localhost:8000

# Lower volume
curl -X POST -H "Content-Type: application/json" -d '{"action":"lower"}' http://localhost:8000

# Stream SSE events
curl -N http://localhost:8000/events
```

## Architecture

`pa_volume_server.py` uses `socketserver.ThreadingMixIn` so each request (including long-lived SSE `GET /events` connections) runs in its own thread. All threads share `global_volume_state` dict guarded by `volume_lock`.

- `POST /` — accepts `{"action": "raise" | "lower"}`, calls `pactl set-sink-volume`, then spawns `volume-indicator.py` as a fire-and-forget subprocess
- `GET /events` — SSE stream polling every 0.1s, only sends when volume changes
- `GET /` (fallback) — serves static files via `SimpleHTTPRequestHandler`

Key config at the top of `pa_volume_server.py`: `PORT`, `VOLUME_STEP`, `SINK_IDENTIFIER`.

## Constraints

- Linux only — `pactl` must be available on `PATH`
- `volume-indicator.py` requires a display (X11/Wayland) and `python3-gi` with GTK3 and Cairo bindings; it is not installed in `.venv`
- No `requirements.txt` or `pyproject.toml` — dependencies are system packages only
- Preserve thread-safety: never read/write `global_volume_state` outside `volume_lock`
