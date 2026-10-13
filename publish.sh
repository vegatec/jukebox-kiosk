#!/usr/bin/env bash
set -euo pipefail

# --- Configuration ---
HOST="vegatec@192.168.2.2"
REMOTE_DIR="/home/vegatec/jukebox/kiosk"
FILES=(
  pa_volume_server.py
  maintenance-indicator.py
  volume-indicator.py
  power-menu.py
  qr-indicator.py
  README.md
)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Publishing to ${HOST}:${REMOTE_DIR}"
for f in "${FILES[@]}"; do
  echo "  - ${f}"
done

sftp -b - "${HOST}" <<EOF
-mkdir ${REMOTE_DIR}
cd ${REMOTE_DIR}
$(for f in "${FILES[@]}"; do echo "put ${f}"; done)
bye
EOF

echo "Done."
