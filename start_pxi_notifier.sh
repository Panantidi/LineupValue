#!/usr/bin/env bash
# Sep 10 2026 — Start/restart the pxi_notifier background process.
# Pattern: kill prior PID, start fresh, write PID file, log to data/.
set -e
APP_DIR="/home/openclaw/FormAlert"
LOG="/home/openclaw/FormAlert/data/pxi_notifier.log"
PIDFILE="/home/openclaw/FormAlert/data/pxi_notifier.pid"

# Kill prior
if [ -f "$PIDFILE" ]; then
  PRIOR=$(cat "$PIDFILE" 2>/dev/null || echo "")
  if [ -n "$PRIOR" ] && kill -0 "$PRIOR" 2>/dev/null; then
    kill -9 "$PRIOR" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

# Start
rm -f "$LOG"
nohup "$APP_DIR/.venv/bin/python3" -u "$APP_DIR/pxi_notifier.py" > "$LOG" 2>&1 &
NEW_PID=$!
disown
echo "$NEW_PID" > "$PIDFILE"

# Quick health-check
sleep 2
if kill -0 "$NEW_PID" 2>/dev/null; then
  echo "started pxi_notifier PID=$NEW_PID  log=$LOG"
  head -3 "$LOG"
else
  echo "FAILED to start pxi_notifier"
  tail -20 "$LOG"
  exit 1
fi
