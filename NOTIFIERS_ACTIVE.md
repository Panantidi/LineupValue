# FormAlert Notifiers — Active Feed (Sep 15 2026)

The `@lineupvalue_alert` Telegram channel is currently driven by
**three** notifier processes. Everything else is intentionally off.

## Active (DO NOT KILL)

| Process                  | Source                                        | Format                                          |
|--------------------------|-----------------------------------------------|-------------------------------------------------|
| `pxi_notifier.py`        | `/lineup_ai/api/test_rotowire_matches/{lg}`   | `🎯 Predicted XI` per match (T-18h horizon, 7 leagues) |
| `sxi_notifier.py`        | `/lineup_ai/api/test_rotowire_matches/{lg}`   | `🏁 Starting XI` per match (kickoff-time gate)         |
| `news_notifier_tweets.py`| `/lineup_ai/api/recent_tweets`                | verbatim tweet text + `Read More (URL)` link     |

All three are watched by `xi_supervisor.sh` (cron `*/2 * * * *`),
which restarts any of them if the process dies OR if the
notifier's log goes stale for >5 min (Sep 15 incident: SXI
froze in poll() while the PID stayed alive — `kill -0` alone
isn't enough, see commit `c8bfec5`).

PID files live in `data/`:
- `pxi_notifier.pid`, `sxi_notifier.pid` — restarted by supervisor
- `news_notifier_tweets.pid` — manual restart only

## Inactive (RSS feeds — DISABLED by request Sep 15 2026)

These are killed and their pid files are gone. The `start_*.sh`
restarters are kept around in case the decision is reversed, but
nothing in the repo or cron will start them automatically.

| Process                | Source / league                  | Status (Sep 15 2026)        |
|------------------------|----------------------------------|-----------------------------|
| `news_notifier_ff.py`  | futbolfantasy.com (LaLiga, Spain)        | killed (PID 2694269) |
| `news_notifier_epl.py` | starting11.com (EPL, England)            | killed (PID 2678806) |
| `news_notifier_bund.py`| ligainsider.de (Bundesliga, Germany)     | was already off Sep 13  |

PID files removed:
- `data/news_notifier_ff.pid`
- `data/news_notifier_epl.pid`
- `data/news_notifier_bund.pid`

State files **kept** in `data/news_state{_epl,_bund,_ff}.json` so
re-enabling is a one-shot `./start_news_notifier_<league>.sh` and
won't flood the channel with a backlog (the diff/state logic
treats existing state as "seen" on first cycle).

Legacy `news_notifier.py` (Sep 11) was already dead before this
change — not touched.

## Adding a feed back

If a new feed is wanted, follow the same pattern as the active
ones:
1. Drop the new `news_notifier_<league>.py` and
   `start_news_notifier_<league>.sh` next to the others.
2. Add the notifier to `xi_supervisor.sh` if it should be
   process-supervised (independent of FastAPI).
3. Don't add it to any cron or systemd unit that auto-restarts;
   manual start only, until verified.

## Why this document exists

Before Sep 15 the channel was driven by 4-7 notifiers in
parallel and the active set changed frequently. Hunting through
`ps -ef | grep notifier` is fine when one person is paying
attention, but the silent-miss on Sep 13 → Sep 15 (PXI down 2
days, SXI frozen 22h, only the human noticing) shows the
cost of "I think it's running". This file pins the contract:
the three processes above are the channel, nothing else.
