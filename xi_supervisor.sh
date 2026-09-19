#!/usr/bin/env bash
# Sep 19 2026 v5 — Watchdog for pxi, sxi, news_tweets, news (main, epl,
# ff, bund), live_events notifiers.
#
# Three failure modes we have to handle:
#   1. Process died (SIGKILL, unhandled exception, OOM-killer).
#      Detect via `kill -0` on the stored PID.
#   2. Process is alive but FROZEN — stuck on a poll() syscall
#      or a never-resuming time.sleep.
#   3. The watchdog itself died (e.g. shell bug, FS full).
#
# Detect stale log via mtime: if the most recent line is older
# than STALE_SEC (default 5 min for notifiers, 30 min for the
# supervisor itself), force-restart.
#
# Per-notifier file naming convention:
#   pxi            -> pxi_notifier.py / pxi_notifier.pid / pxi_notifier.log
#   sxi            -> sxi_notifier.py / sxi_notifier.pid / sxi_notifier.log
#   news_tweets    -> news_notifier_tweets.py / news_notifier_tweets.pid / news_notifier_tweets.log
#   news           -> news_notifier.py / news_notifier.pid / news_notifier.log (general)
#   news_epl       -> news_notifier_epl.py / news_notifier_epl.pid / news_notifier_epl.log
#   news_ff        -> news_notifier_ff.py / news_notifier_ff.pid / news_notifier_ff.log
#   news_bund      -> news_notifier_bund.py / news_notifier_bund.pid / news_notifier_bund.log
#   live_events    -> live_events_notifier.py / live_events_notifier.pid / live_events_notifier.log
#
# Install (one-shot, on the server, as `openclaw`):
#   crontab -e
#   * * * * * SXI_TG_TOKEN=*** [REDACTED] SXI_TG_CHAT=@lineupvalue_alert /home/openclaw/FormAlert/xi_supervisor.sh >> /home/openclaw/FormAlert/data/xi_supervisor.log 2>&1
#
# Run manually for diagnostics:
#   DEBUG=1 bash /home/openclaw/FormAlert/xi_supervisor.sh

set -u

APP_DIR="/home/openclaw/FormAlert"
LOG_DIR="$APP_DIR/data"
SUP_LOG="$LOG_DIR/xi_supervisor.log"
PYTHON="$APP_DIR/.venv/bin/python3"
STALE_SEC="${STALE_SEC:-300}"      # 5 min for notifiers
SUP_STALE_SEC="${SUP_STALE_SEC:-1800}"  # 30 min — supervisor itself

# Telegram channel + token — required for restart so the
# restarted notifier can post. Cron line passes them via env
# so they never appear in the script body.
export SXI_TG_TOKEN="${SXI_TG_TOKEN:-}"
export SXI_TG_CHAT="${SXI_TG_CHAT:-@lineupvalue_alert}"

stamp() { date -u +"%Y-%m-%d %H:%M:%S UTC"; }
log() {
    printf "[%s] %s\n" "$(stamp)" "$*" >> "$SUP_LOG"
    if [ "${DEBUG:-0}" = "1" ]; then
        printf "[%s] %s\n" "$(stamp)" "$*"
    fi
}

age_seconds() {
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

# Per-target configuration table. Each line is:
#   config_key | script_name | pid_file_name | log_file_name | stale_sec
TARGETS=(
    "pxi|pxi_notifier.py|pxi_notifier.pid|pxi_notifier.log|${STALE_SEC}"
    "sxi|sxi_notifier.py|sxi_notifier.pid|sxi_notifier.log|${STALE_SEC}"
    "news|news_notifier.py|news_notifier.pid|news_notifier.log|600"
    "news_epl|news_notifier_epl.py|news_notifier_epl.pid|news_notifier_epl.log|600"
    "news_ff|news_notifier_ff.py|news_notifier_ff.pid|news_notifier_ff.log|600"
    "news_bund|news_notifier_bund.py|news_notifier_bund.pid|news_notifier_bund.log|600"
    "news_tweets|news_notifier_tweets.py|news_notifier_tweets.pid|news_notifier_tweets.log|360"
    "live_events|live_events_notifier.py|live_events_notifier.pid|live_events_notifier.log|180"
)

should_restart_target() {
    local pid_file="$1"
    local log_file="$2"
    local stale="$3"

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
    if [ "$age" -gt "$stale" ]; then
        echo "stale (alive but log ${age}s old > ${stale}s threshold; pid=$cur_pid)"
        return 0
    fi

    return 1
}

restart_target() {
    local key="$1"
    local script="$2"
    local pid_file="$3"
    local log_file="$4"
    local stale="$5"

    if ! should_restart_target "$pid_file" "$log_file" "$stale"; then
        return 0
    fi

    local reason
    reason=$(should_restart_target "$pid_file" "$log_file" "$stale" 2>/dev/null) || reason="triggered"
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
    log "[$key] $reason; (re)starting"

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
    pkill -9 -f "$script" 2>/dev/null || true
    sleep 1
    rm -f "$pid_file"

    cd "$APP_DIR" || { log "[$key] cd failed"; return 1; }
    nohup "$PYTHON" -u "$APP_DIR/$script" >> "$log_file" 2>&1 &
    local new_pid=$!
    disown
    echo "$new_pid" > "$pid_file"
    log "[$key] (re)started PID=$new_pid"
}

mkdir -p "$LOG_DIR"

# Iterate through all configured targets. Each entry is pipe-
# separated; we use bash here-string to avoid subshell quoting.
while IFS='|' read -r key script pid log_name stale; do
    [ -z "$key" ] && continue
    restart_target "$key" "$script" "$LOG_DIR/$pid" "$LOG_DIR/$log_name" "$stale"
done < <(printf '%s\n' "${TARGETS[@]}")
