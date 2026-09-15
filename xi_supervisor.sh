#!/usr/bin/env bash
# Sep 15 2026 — Watchdog for pxi_notifier.py and sxi_notifier.py.
#
# Two failure modes we have to handle:
#   1. Process died (SIGKILL, unhandled exception, OOM-killer).
#      Detect via `kill -0` on the stored PID.
#   2. Process is alive but FROZEN — stuck on a poll() syscall
#      or a never-resuming time.sleep. The Sep 13 22:30 → Sep 15
#      17:40 incident: SXI was alive (PID 2648258, state S) but
#      hadn't written a log line in 22 hours because it was
#      stuck inside urllib's poll() on a socket to the local
#      uvicorn. `kill -0` returned 0 the whole time. The channel
#      went dark and we had no signal until a human noticed.
#
#      Detect via log mtime: if the most recent line is older
#      than STALE_SEC (default 5 min), force-restart.
#
# Both checks run on every invocation. The watchdog itself is
# idempotent: in the happy path it does almost nothing and exits
# 0, so cron is happy.
#
# Install (one-shot, on the server, as `openclaw`):
#   crontab -e
#   */2 * * * * /home/openclaw/FormAlert/xi_supervisor.sh >> /home/openclaw/FormAlert/data/xi_supervisor.log 2>&1
#
# Run manually for diagnostics:
#   DEBUG=1 bash /home/openclaw/FormAlert/xi_supervisor.sh

set -u

APP_DIR="/home/openclaw/FormAlert"
LOG_DIR="$APP_DIR/data"
SUP_LOG="$LOG_DIR/xi_supervisor.log"
PYTHON="$APP_DIR/.venv/bin/python3"
STALE_SEC="${STALE_SEC:-300}"   # 5 min — PXI/SXI both have 30s INTERVAL

stamp() { date -u +"%Y-%m-%d %H:%M:%S UTC"; }
log() {
    printf "[%s] %s\n" "$(stamp)" "$*" >> "$SUP_LOG"
    if [ "${DEBUG:-0}" = "1" ]; then
        printf "[%s] %s\n" "$(stamp)" "$*"
    fi
}

age_seconds() {
    # Echo age of a file in seconds. Echo 99999999 if file is missing
    # so the caller treats it as "very stale" and force-restarts.
    local f="$1"
    if [ ! -f "$f" ]; then
        echo 99999999
        return
    fi
    local now_epoch file_epoch
    now_epoch=$(date +%s)
    file_epoch=$(stat -c %Y "$f")
    echo $(( now_epoch - file_epoch ))
}

# Decide: alive and fresh = healthy. alive and stale = force-kill.
# dead = start fresh. missing pid file = start fresh.
should_restart() {
    local name="$1"
    local pid_file="$LOG_DIR/${name}_notifier.pid"
    local log_file="$LOG_DIR/${name}_notifier.log"
    local reason

    if [ ! -f "$pid_file" ]; then
        echo "no pid file"
        return 0
    fi

    local cur_pid
    cur_pid=$(cat "$pid_file" 2>/dev/null || echo "")
    if [ -z "$cur_pid" ]; then
        echo "empty pid file"
        return 0
    fi

    if ! kill -0 "$cur_pid" 2>/dev/null; then
        echo "dead (pid=$cur_pid)"
        return 0
    fi

    local age
    age=$(age_seconds "$log_file")
    if [ "$age" -gt "$STALE_SEC" ]; then
        echo "stale (alive but log ${age}s old > ${STALE_SEC}s threshold; pid=$cur_pid)"
        return 0
    fi

    return 1   # healthy
}

restart_one() {
    local name="$1"   # "pxi" or "sxi"
    local pid_file="$LOG_DIR/${name}_notifier.pid"
    local log_file="$LOG_DIR/${name}_notifier.log"

    if should_restart "$name"; then
        local reason
        reason=$(should_restart "$name" 2>/dev/null) || reason="triggered"
        # When should_restart said "stale" we want the message, but
        # the second call returns 0 (no message) because the file is
        # already gone. Re-derive the reason explicitly:
        if [ ! -f "$pid_file" ]; then
            reason="no pid file"
        else
            local cur_pid
            cur_pid=$(cat "$pid_file" 2>/dev/null || echo "")
            if [ -z "$cur_pid" ] || ! kill -0 "$cur_pid" 2>/dev/null; then
                reason="dead (pid=$cur_pid)"
            else
                local age
                age=$(age_seconds "$log_file")
                reason="stale (log ${age}s old, pid=$cur_pid)"
            fi
        fi
        log "[$name] $reason; (re)starting"

        # If alive but stale, hard-kill before restarting. SIGTERM
        # is racy on a frozen process — SIGKILL is the only way to
        # be sure a stuck poll() returns.
        if [ -f "$pid_file" ]; then
            local cur_pid
            cur_pid=$(cat "$pid_file" 2>/dev/null || echo "")
            if [ -n "$cur_pid" ] && kill -0 "$cur_pid" 2>/dev/null; then
                kill -9 "$cur_pid" 2>/dev/null || true
                sleep 1
            fi
        fi
        # Belt-and-braces: kill any other copy that's still hanging
        # around (e.g. orphaned by a different cgroup).
        pkill -9 -f "${name}_notifier.py" 2>/dev/null || true
        sleep 1
        rm -f "$pid_file"

        cd "$APP_DIR" || { log "[$name] cd failed"; return 1; }
        nohup "$PYTHON" -u "$APP_DIR/${name}_notifier.py" >> "$log_file" 2>&1 &
        local new_pid=$!
        disown
        echo "$new_pid" > "$pid_file"
        log "[$name] (re)started PID=$new_pid"
    fi
}

mkdir -p "$LOG_DIR"
restart_one pxi
restart_one sxi
