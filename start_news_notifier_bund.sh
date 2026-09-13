#!/usr/bin/env bash
# Start/restart news_notifier_bund (ligainsider Bundesliga injury feed).
set -e
APP_DIR="/home/openclaw/FormAlert"
LOG_DIR="$APP_DIR/data"
NOTIFIER_LOG="$LOG_DIR/news_notifier_bund.log"
NOTIFIER_PID_FILE="$LOG_DIR/news_notifier_bund.pid"
PYTHON="$APP_DIR/.venv/bin/python3"

if [[ -f "$NOTIFIER_PID_FILE" ]]; then
    OLD_PID=$(cat "$NOTIFIER_PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "killing old news_notifier_bund PID=$OLD_PID"
        kill -9 "$OLD_PID" 2>/dev/null || true
    fi
    rm -f "$NOTIFIER_PID_FILE"
fi
pkill -9 -f "news_notifier_bund.py" 2>/dev/null || true
sleep 1

mkdir -p "$LOG_DIR"
rm -f "$NOTIFIER_LOG"

cd "$APP_DIR"
setsid nohup "$PYTHON" -u "$APP_DIR/news_notifier_bund.py" </dev/null >"$NOTIFIER_LOG" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$NOTIFIER_PID_FILE"
disown
sleep 2
echo "started news_notifier_bund PID=$NEW_PID  log=$NOTIFIER_LOG"
ps -p "$NEW_PID" -o pid,etime,cmd 2>/dev/null || echo "process died"
