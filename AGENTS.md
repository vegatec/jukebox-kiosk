# Agent Instructions for jukebox-kiosk

## Purpose
This repository contains a single Python service, `pa_volume_server.py`, that exposes a threaded HTTP server for controlling PulseAudio volume on Linux.

## What an agent should know
- The script is meant to run on Linux with PulseAudio or PipeWire available.
- It depends on the `pactl` CLI and Python 3.
- The service exposes:
  - `POST /` with JSON: `{ "action": "raise" | "lower" }`
  - `GET /events` as a Server-Sent Events (SSE) stream sending volume updates.
- The server uses `socketserver.ThreadingMixIn` so SSE connections and control requests do not block each other.
- It also calls an external helper script `volume-indicator.py`, which is not present in this repository.

## How to run
- Start the service with:
  - `python3 pa_volume_server.py`
- The service listens on `http://localhost:8000` by default.

## Useful details
- `VOLUME_COMMAND`, `VOLUME_STEP`, and `SINK_IDENTIFIER` are configured at the top of `pa_volume_server.py`.
- Volume state is stored in `global_volume_state` and guarded with `volume_lock`.
- The SSE loop polls every 0.1 seconds and sends updates only when the volume changes.
- CORS is enabled for all origins in both POST and SSE responses.

## What agents should not assume
- There is no package manifest (`requirements.txt`, `pyproject.toml`, etc.) in this repo.
- No tests or CI configuration exist in the repository.
- The repository is not a library; it is an executable script.

## When editing
- Preserve the thread-safe design around `global_volume_state`.
- Keep Linux-specific runtime assumptions explicit.
- Validate JSON input and return proper HTTP status codes for invalid payloads.
