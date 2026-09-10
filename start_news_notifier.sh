#!/usr/bin/env bash
# Sep 10 2026 — Start/restart the news_notifier background process.
# Pattern: kill prior PID, start fresh, write PID file, log to data/.
set -e
APP_DIR="/home/openclaw/FormAlert"
LOG_DIR="$APP_DIR/data"
PID_FILE="$LOG_DIR/news_notifier.pid"
LOG_FILE="$LOG_DIR/news_notifier.log"

mkdir -p "$LOG_DIR"

# Kill any prior instance
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill -9 "$OLD_PID" 2>/dev/null || true
        sleep 0.5
    fi
    rm -f "$PID_FILE"
fi

# Also kill any stragglers
pkill -9 -f "news_notifier.py" 2>/dev/null || true
sleep 0.3

# Start fresh
cd "$APP_DIR"
nohup .venv/bin/python3 -u news_notifier.py > "$LOG_FILE" 2>&1 &
NEW_PID=$!
disown
echo "$NEW_PID" > "$PID_FILE"
sleep 0.5

# Verify
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "OK news_notifier started PID=$NEW_PID"
    echo "log: $LOG_FILE"
else
    echo "FAIL: news_notifier died immediately"
    tail -20 "$LOG_FILE"
    exit 1
fi
