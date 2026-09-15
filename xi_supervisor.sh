#!/usr/bin/env bash
# Sep 15 2026 — Watchdog for pxi_notifier.py and sxi_notifier.py.
#
# PXI went silent for ~2 days (Sep 13 22:51 -> Sep 15 17:20 UTC) because
# the background process exited and nothing restarted it. This supervisor
# is the safety net: if either notifier dies, restart it within 5 minutes.
#
# Install (one-shot, as openclaw):
#   crontab -e
#   */5 * * * * /home/openclaw/FormAlert/xi_supervisor.sh >> /home/openclaw/FormAlert/data/xi_supervisor.log 2>&1
#
# Idempotent: safe to run every minute. Does NOT touch the log files of
# the notifiers themselves — only restarts the process if the PID stored
# in data/<name>.pid is no longer alive.

set -u

APP_DIR="/home/openclaw/FormAlert"
LOG_DIR="$APP_DIR/data"
SUP_LOG="$LOG_DIR/xi_supervisor.log"
PYTHON="$APP_DIR/.venv/bin/python3"

stamp() { date -u +"%Y-%m-%d %H:%M:%S UTC"; }

log() {
    printf "[%s] %s\n" "$(stamp)" "$*" >> "$SUP_LOG"
}

restart_one() {
    local name="$1"   # "pxi" or "sxi"
    local pid_file="$LOG_DIR/${name}_notifier.pid"
    local log_file="$LOG_DIR/${name}_notifier.log"

    if [[ ! -f "$pid_file" ]]; then
        log "[$name] no pid file; starting fresh"
        cd "$APP_DIR" || { log "[$name] cd failed"; return 1; }
        nohup "$PYTHON" -u "$APP_DIR/${name}_notifier.py" >> "$log_file" 2>&1 &
        local new_pid=$!
        disown
        echo "$new_pid" > "$pid_file"
        log "[$name] started PID=$new_pid"
        return 0
    fi

    local cur_pid
    cur_pid=$(cat "$pid_file" 2>/dev/null || echo "")
    if [[ -z "$cur_pid" ]] || ! kill -0 "$cur_pid" 2>/dev/null; then
        log "[$name] dead (pid=$cur_pid); restarting"
        rm -f "$pid_file"
        cd "$APP_DIR" || { log "[$name] cd failed"; return 1; }
        nohup "$PYTHON" -u "$APP_DIR/${name}_notifier.py" >> "$log_file" 2>&1 &
        local new_pid=$!
        disown
        echo "$new_pid" > "$pid_file"
        log "[$name] restarted PID=$new_pid"
    fi
}

mkdir -p "$LOG_DIR"
restart_one pxi
restart_one sxi
