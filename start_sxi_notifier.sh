#!/usr/bin/env bash
# Sep 10 2026 — Start/restart the sxi_notifier background process.
# Pattern: kill prior PID, start fresh, write PID file, log to data/.
set -e
APP_DIR="/home/openclaw/FormAlert"
LOG_DIR="$APP_DIR/data"
NOTIFIER_LOG="$LOG_DIR/sxi_notifier.log"
NOTIFIER_PID_FILE="$LOG_DIR/sxi_notifier.pid"
PYTHON="$APP_DIR/.venv/bin/python3"

# Kill any prior notifier
if [[ -f "$NOTIFIER_PID_FILE" ]]; then
    OLD_PID=$(cat "$NOTIFIER_PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "killing old notifier PID=$OLD_PID"
        kill -9 "$OLD_PID" 2>/dev/null || true
    fi
    rm -f "$NOTIFIER_PID_FILE"
fi
# Also kill any stray
pkill -9 -f "sxi_notifier.py" 2>/dev/null || true
sleep 1

mkdir -p "$LOG_DIR"
rm -f "$NOTIFIER_LOG"

cd "$APP_DIR"
nohup "$PYTHON" -u "$APP_DIR/sxi_notifier.py" > "$NOTIFIER_LOG" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$NOTIFIER_PID_FILE"
disown
echo "started sxi_notifier PID=$NEW_PID  log=$NOTIFIER_LOG"
sleep 2
# Show first lines of log to confirm startup
head -20 "$NOTIFIER_LOG" 2>/dev/null || true
