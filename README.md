# jukebox-kiosk

A Linux volume control service for jukebox/kiosk deployments. Exposes a local HTTP API for raising, lowering, and setting PulseAudio volume, with a Server-Sent Events stream for real-time updates and GTK overlay indicators for visual feedback.

## Requirements

- Linux with PulseAudio or PipeWire (`pactl` on `PATH`)
- Python 3 (stdlib only for the server)
- `python3-gi`, GTK3, and Cairo bindings for the visual overlays
- `python3-qrcode` for the QR indicator

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 python3-qrcode
```

## Running

```bash
python3 pa_volume_server.py
```

Server starts on `http://localhost:8000`.

## API

### POST `/`

Control volume. Body is JSON.

```bash
# Raise by 5%
curl -X POST -H "Content-Type: application/json" \
  -d '{"action":"raise"}' http://localhost:8000

# Lower by 5%
curl -X POST -H "Content-Type: application/json" \
  -d '{"action":"lower"}' http://localhost:8000

# Set to exact level
curl -X POST -H "Content-Type: application/json" \
  -d '{"action":"set","level":75}' http://localhost:8000
```

Response:
```json
{"status": "success", "message": "Volume adjusted to 75%.", "volume": 75}
```

### GET `/events`

SSE stream. Emits a JSON event whenever the volume changes.

```bash
curl -N http://localhost:8000/events
```

Event format:
```
data: {"volume": 75, "timestamp": 1234567890.123}
```

### GET `/qr`

Spawns a GTK overlay displaying a QR code that encodes `http://<local-ip>:3000/remote-control`. The overlay auto-dismisses after 20 seconds or on click (after a 10-second lock period).

```bash
curl http://localhost:8000/qr
```

### GET `/power-menu`

Spawns a three-phase GTK overlay:

1. **Menu** — Power Off / Restart / Change Volume buttons (auto-dismisses in 8s)
2. **PIN entry** — numeric keypad; enter the configured PIN to proceed
3. **Volume slider** — full-width horizontal slider pinned to the bottom of the screen; dismisses after 10s of inactivity or on "DONE"

```bash
curl http://localhost:8000/power-menu
```

#### Wiring to the hardware power button

Disable logind's built-in shutdown handler and route the event to the server via acpid:

```bash
# 1. Tell logind to ignore the power key
sudo sed -i 's/#HandlePowerKey=poweroff/HandlePowerKey=ignore/' /etc/systemd/logind.conf
sudo systemctl restart systemd-logind

# 2. Install acpid if not present
sudo apt install acpid

# 3. Create the event handler
sudo tee /etc/acpi/events/powerbtn-kiosk <<'EOF'
event=button/power.*
action=curl -s -o /dev/null http://localhost:8000/power-menu
EOF

sudo systemctl restart acpid
```

## Visual Overlays

All overlays are spawned as fire-and-forget subprocesses and require a display (X11 or Wayland).

- **`volume-indicator.py`** — shown on every volume change; displays current level as a cyan arc
- **`qr-indicator.py`** — shown on `GET /qr`; displays a scannable QR code and URL
- **`power-menu.py`** — shown on `GET /power-menu`; three-phase menu → PIN → volume slider

## Configuration

Edit the constants at the top of `pa_volume_server.py`:

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | HTTP server port |
| `VOLUME_STEP` | `5` | Percent change per raise/lower action |
| `SINK_IDENTIFIER` | `"0"` | PulseAudio sink index or name |
| `POWER_MENU_PIN` | `"1234"` | PIN required to access volume control from the power menu |
