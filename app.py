import os
import time
from dotenv import load_dotenv

load_dotenv()
import asyncio
import sqlite3
import urllib.parse
import json
import unicodedata
import re
import hashlib
import secrets
import subprocess
import uuid
import base64
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import FastAPI, Request, Form, Body, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse

security = HTTPBasic(auto_error=False)

APP_TITLE = "FormAlert"
APP_VERSION = "3.0"

BOT_TOKEN = os.environ.get("FORMALERT_BOT_TOKEN", "")
CHAT_ID = os.environ.get("FORMALERT_CHAT_ID", "")  # can be numeric id or @channelusername
DB_PATH = os.environ.get("FORMALERT_DB_PATH", os.path.join(os.path.dirname(__file__), "formalert.db"))
BASE_URL = os.environ.get("FORMALERT_BASE_URL", "https://x11radar.ru")

X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "")
X_LIST_ID = os.environ.get("X_LIST_ID", "")
FETCH_ENABLED = os.environ.get("FETCH_ENABLED", "0") == "1"
FETCH_INTERVAL_SECONDS = int(os.environ.get("FETCH_INTERVAL_SECONDS", "240"))

FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "")
FOOTBALL_DATA_BASE = os.environ.get("FOOTBALL_DATA_BASE", "https://api.football-data.org")

QUIET_HOURS_ENABLED = os.environ.get("QUIET_HOURS_ENABLED", "0") == "1"
QUIET_HOURS_FROM = os.environ.get("QUIET_HOURS_FROM", "00:00")  # MSK
QUIET_HOURS_TO = os.environ.get("QUIET_HOURS_TO", "00:00")      # MSK

# AI Gate (cheap YES/NO before Core engine)
GATE_ENABLED = os.environ.get("GATE_ENABLED", "1") == "1"
GATE_MODEL = os.environ.get("GATE_MODEL", "openai/gpt-5.2")
GATE_TIMEOUT_SECONDS = int(os.environ.get("GATE_TIMEOUT_SECONDS", "15"))

KEYWORDS_INCLUDE_PATH = os.environ.get("KEYWORDS_INCLUDE_PATH", os.path.join(os.path.dirname(__file__), "keywords_include.txt"))
KEYWORDS_BLACKLIST_PATH = os.environ.get("KEYWORDS_BLACKLIST_PATH", os.path.join(os.path.dirname(__file__), "keywords_blacklist.txt"))
PLAYER_NAMES_PATH = os.environ.get("PLAYER_NAMES_PATH", os.path.join(os.path.dirname(__file__), "player_names.txt"))
PROBABLE_XI_PATH = os.environ.get("PROBABLE_XI_PATH", os.path.join(os.path.dirname(__file__), "probable_xi_keywords.txt"))
STARTING_XI_PATH = os.environ.get("STARTING_XI_PATH", os.path.join(os.path.dirname(__file__), "starting_xi_keywords.txt"))
MODES_PATH = os.environ.get("MODES_PATH", os.path.join(os.path.dirname(__file__), "modes.json"))
MATCH_MODE = os.environ.get("MATCH_MODE", "substring").lower()  # substring|exact

CATEGORIES = [
    "official_lineup",
    "injury",
    "suspension",
    "availability",
    "training",
    "recovery",
    "travel_squad",
    "rotation",
    "coach_comment",
    "goalkeeper",
    "tactical",
    "other",
]

IMPACT_LEVELS = ["critical", "high", "medium", "low", "none"]


def _scrape_flashscore_infobox(match_id: str) -> str:
    """Scrape the infoBox text from the Flashscore match HTML page.

    Jul 30 2026: the /matches/details JSON API does NOT include the
    infoBox (it only has venue, referee, scores). Flashscore renders
    the infoBox text in the match HTML page inside a JSON-encoded
    array under the abbreviated key "DM" — e.g.:

        {"DM":"Playing home matches at a different stadium -
         Adjarabet Arena. First leg result: 5-0."}

    We pull the page, extract {"DM":"..."}, and return the text.
    Empty string if the field is absent (regular match) or on
    any error.

    This is the source of truth for the infoBox content per match.
    Different matches will have different texts (or no text at all).
    """
    if not match_id:
        return ""
    try:
        import urllib.request as _ur
        url = f"https://www.flashscore.com/match/{match_id}/"
        req = _ur.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/121.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with _ur.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # Try strict JSON-like pattern first, then simple.
        m = re.search(r'\{"DM":"([^"\\]*(?:\\.[^"\\]*)*)"\}', html)
        if not m:
            m = re.search(r'"DM":"([^"]+)"', html)
        if m:
            text = (m.group(1)
                    .replace('\\"', '"')
                    .replace('\\\\', '\\')
                    .replace('\\n', ' ')
                    .replace('\\t', ' ')
                    .strip())
            return text
    except Exception:
        pass
    return ""


def now_msk_hhmm() -> str:
    # MSK is UTC+3 without DST
    return datetime.now(timezone.utc).astimezone(timezone.utc).replace(tzinfo=None)  # placeholder


OFFICIAL_SOURCES = {
    "@AngersSCO","@AJA","@SB29","@HAC_Foot","@RCLens","@losclive","@FCLorient","@OL","@OM_Officiel",
    "@FCMetz","@AS_Monaco","@FCNantes","@ogcnice","@ParisFC","@PSG_inside","@staderennais","@RCSA","@ToulouseFC",
}

JOURNO_SOURCES = {
    "@AntoineRaguin", "@Flo_Leyb", "@ju_benbouali", "@ClesagePro", "@benoit_donckele", "@SandArrestier", "@EloiseDM62",
    "@BaptisteCogne", "@GuillaumeTarpi", "@enzomarcon_", "@karimattab1", "@RLgallois", "@RouxChristopher", "@VSeiller",
    "@dphelippeau", "@buchotm", "@pabard", "@SimonReungoat", "@SolamenNissa", "@ftresarrieu", "@PrunetaLaurent", "@LGClequipe",
    "@IliesPeeters", "@AbdellahBoulma", "@bruno_salomon", "@gui_tog", "@CyrilOlives", "@faugere_theo", "@ArthurLeMaout",
    "@ArisDjennadi", "@FabriceHawkins", "@CasseJosue", "@AndiOnrubia", "@MPGLaurent", "@Tanziloic", "@MohamedTERParis", "@ArthurPerrot",
    "@AntoineGegat", "@ArnaudLeSauce", "@brunoblanzat", "@flogermain", "@AJac13", "@TJeangeorge", "@LukeEntwistle",
    "@ManuMerceron", "@loicfolliot", "@naninho06", "@ClemBigois", "@Clem_Gavv", "@hugoguillemet", "@B_Quarez", "@AliPaacha",
}

OFFICIAL_PREFIXES = [
    "Из официальных источников сообщается, что ",
    "По данным официальных источников ",
    "Как сообщает официальный X, ",
    "По сведениям официального X ",
    "По данным официального X ",
    "Из официального X следует, что ",
    "Официально: ",
    "В официальном X сообщается, что ",
    "Согласно данным официального X ",
]

JOURNO_PREFIXES = [
    "По данным журналистов ",
    "Как сообщают близкие к ситуации источники, ",
    "Согласно сведениям от экспертов, ",
    "Согласно источникам среди журналистов, ",
    "По сведениям журналистов ",
    "По данным, известным инсайдерам, ",
    "Инсайдеры сообщают, что ",
    "По данным, поступившим от надежных источников, ",
    "От надежных источников стало известно, что ",
    "По данным источников, близких к команде, ",
    "По сообщениям инсайдеров ",
    "По данным экспертов ",
]

FAN_MEDIA_SOURCES = {
    "@IncroyableSCO", "@BrestOnAir", "@LaMareeRouge", "@DoyensLeMedia", "@LensoisComLive", "@LePetitLillois",
    "@LoscFansOnline", "@oetl", "@lyon_foot69", "@LaMinuteOM_", "@MassiliaZone", "@treize013", "@lephoceen",
    "@letsgomtz", "@TeamGrenat", "@LaDiagonale_", "@TribuneNantaise", "@PassionParisFC", "@ParisFCinfos",
    "@CulturePSG", "@lasource75006", "@MediaParisien", "@CanalSupporters", "@Paristeamfr", "@S_R_Online",
    "@ROUGEmemoire", "@Direct__Racing", "@JournalDuRcsa_", "@LesVioletsCom",
    "@Thescoismagic", "@EliotAJA", "@TeamAJA89", "@DOGUE_INSIDE", "@FCMarseille", "@LigASM_", "@ActuSRFC_", "@FDMToulouseFoot",
    "@Journalrennais"
}

FAN_SUPPORTIVE_SOURCES = {
    "@lacouture49", "@inffred89", "@bras_george", "@Vincent_1393", "@FadaOM_", "@Olympien2613",
    "@NissaEbasta", "@alex_nissadu06", "@badagous", "@FrRenzini", "@jonathan35001", "@TheCoach_2",
    "@Onparledupsg"
}

REGIONAL_SOURCES = {"@LeProgresOL", "@OMLaProvence", "@sports_rl", "@ici_alsace", "@lalsace", "@iciazur", "@Oxygene_Radio"}

FAN_MEDIA_PREFIXES = [
    "По информации источника: ",
    "Согласно источникам ",
    "По последним данным ",
    "Как информируют СМИ ",
    "Сообщается, что ",
    "Стало известно, что ",
    "По данным СМИ ",
    "Как стало известно ",
    "Появилась информация о ",
    "По информации СМИ ",
    "По сообщениям из X ",
]

FAN_SUPPORTIVE_PREFIXES = [
    "Фанаты сообщают ",
    "Болельщик клуба сообщает ",
    "Болельщики пишут, что ",
    "Болельщик поделился информацией: ",
    "Болельщик пишет, что ",
    "Фанат клуба сообщает, что ",
    "Фанат команды поделился ",
    "Фанат делится: ",
]

REGIONAL_PREFIXES = [
    "Региональное издание сообщает, что ",
    "По информации местных СМИ ",
    "Местная пресса пишет, что ",
    "Согласно региональному источнику: ",
    "Региональные источники сообщают ",
    "По данным местных СМИ ",
    "Как сообщает местное издание ",
]


def _choose_fan_media_prefix(seed: str) -> str:
    import hashlib
    h = hashlib.sha256((seed or "").encode("utf-8")).digest()
    idx = h[2] % len(FAN_MEDIA_PREFIXES)
    return FAN_MEDIA_PREFIXES[idx]


def _choose_fan_supportive_prefix(seed: str) -> str:
    import hashlib
    h = hashlib.sha256((seed or "").encode("utf-8")).digest()
    idx = h[4] % len(FAN_SUPPORTIVE_PREFIXES)
    return FAN_SUPPORTIVE_PREFIXES[idx]


def _choose_regional_prefix(seed: str) -> str:
    import hashlib
    h = hashlib.sha256((seed or "").encode("utf-8")).digest()
    idx = h[5] % len(REGIONAL_PREFIXES)
    return REGIONAL_PREFIXES[idx]


def _choose_official_prefix(seed: str) -> str:
    # deterministic-ish choice to avoid repetition without storing state
    import hashlib
    h = hashlib.sha256((seed or "").encode("utf-8")).digest()
    idx = h[0] % len(OFFICIAL_PREFIXES)
    return OFFICIAL_PREFIXES[idx]


def _choose_journo_prefix(seed: str) -> str:
    import hashlib
    h = hashlib.sha256((seed or "").encode("utf-8")).digest()
    idx = h[1] % len(JOURNO_PREFIXES)
    return JOURNO_PREFIXES[idx]


_ENCRYPT_KEY = os.environ.get("FORMALERT_ENCRYPT_KEY", "x11radar-secret-key-2026")

def _encrypt(text: str) -> str:
    """Simple reversible encryption for storing plain passwords."""
    import base64 as _b64
    raw = text.encode()
    key = _ENCRYPT_KEY.encode()
    enc = bytes(a ^ key[i % len(key)] for i, a in enumerate(raw))
    return _b64.b64encode(enc).decode()

def _decrypt(token: str) -> str:
    """Decrypt stored plain password."""
    import base64 as _b64
    key = _ENCRYPT_KEY.encode()
    dec = _b64.b64decode(token)
    return bytes(a ^ key[i % len(key)] for i, a in enumerate(dec)).decode()

def _hash_password(password: str) -> str:
    """Hash password with salt using SHA-256."""
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"

def _verify_password(password: str, password_hash: str) -> bool:
    """Verify password against stored hash."""
    try:
        salt, h = password_hash.split(":", 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == h
    except Exception:
        return False

def _generate_password(length: int = 12) -> str:
    """Generate a random password."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))

def _generate_username() -> str:
    """Generate a random username."""
    return "user_" + secrets.token_hex(4)

def _get_current_user(credentials: HTTPBasicCredentials | None = Depends(security)):
    """Verify Basic Auth credentials. Returns (username, is_admin) or raises 401."""
    if not credentials:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT username, password_hash, is_admin, active FROM users WHERE username=? AND active=1",
                      (credentials.username,)).fetchone()
    con.close()
    if not row or not _verify_password(credentials.password, row[1]):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return row[0], bool(row[2])

def _log_access(username: str, ip: str, path: str, action: str, details: str = ""):
    """Log user access/action."""
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute("INSERT INTO access_log (username, ip, path, action, details, timestamp) VALUES (?,?,?,?,?,?)",
                     (username, ip, path, action, details, datetime.now(timezone.utc).isoformat()))
        # Update last_login
        if action == "login":
            con.execute("UPDATE users SET last_login=? WHERE username=?",
                         (datetime.now(timezone.utc).isoformat(), username))
        con.commit()
        con.close()
    except Exception:
        pass


def _extract_path_details(path: str) -> str:
    """Extract a short human-readable description of what this path did.

    Jul 24 2026: the Details column in /admin was always empty
    because the view-event logger was passing details="". We now
    extract the team name (or match header) from the live cache
    files so an admin looking at Recent Activity can tell what
    the user actually opened without grepping team_ids.

    Args:
        path: URL path, e.g. "/lineup_ai/pKS9M7R7"

    Returns:
        A short string like "Ferencvaros" (team name), or "" if
        we can't determine it.
    """
    try:
        import re as _re
        from urllib.parse import urlparse, parse_qs
        u = urlparse(path)
        seg = [s for s in u.path.split('/') if s]
        if not seg:
            return ""
        # /lineup_ai/<team_id>            -> team name
        # /lineup_ai/snapshots/<team_id>  -> team name
        # /lineup_ai/compare/<team_id>    -> team name
        # /lineup_ai/api/squad/<team_id>  -> team name
        # /lineup_ai/api/fixtures/<team_id> -> team name
        # /lineup_ai/match_save/<match_id> -> team names from query
        # /lineup_ai/match/h2h/<match_id> -> team names from query
        if len(seg) >= 2 and seg[0] == "lineup_ai":
            sub = seg[1]
            if sub in ("api",):
                # /lineup_ai/api/<kind>/<team_id>
                if len(seg) >= 4:
                    team_id = seg[3]
                else:
                    return ""
            elif sub in ("snapshots", "compare"):
                if len(seg) >= 3:
                    team_id = seg[2]
                else:
                    return ""
            elif sub == "match_save":
                # /lineup_ai/match_save/<match_id>?home=...&away=...
                qs = parse_qs(u.query)
                h = qs.get("home_name", qs.get("home", [""]))[0]
                a = qs.get("away_name", qs.get("away", [""]))[0]
                if h and a:
                    return f"{h} vs {a}"
                elif h:
                    return h
                elif a:
                    return a
                return ""
            elif sub == "match":
                # /lineup_ai/match/h2h/<match_id>?my=<id>&opp=<id>
                # Resolve both team names from their respective live
                # caches. Falls back to the raw id if a cache is missing.
                qs = parse_qs(u.query)
                my_id = qs.get("my", [""])[0]
                opp_id = qs.get("opp", [""])[0]
                my_name = _extract_path_details(f"/lineup_ai/{my_id}") if my_id else ""
                opp_name = _extract_path_details(f"/lineup_ai/{opp_id}") if opp_id else ""
                if my_name and opp_name:
                    return f"{my_name} vs {opp_name}"
                elif my_name:
                    return my_name
                elif opp_name:
                    return opp_name
                return ""
            else:
                # /lineup_ai/<team_id> directly
                team_id = seg[1]
        else:
            return ""
        # Resolve team name from live cache.
        # Cache layout (see api_refresh.refresh_team):
        #   {
        #     "team": {"id": ..., "name": "Ferencvaros", "country": "..."},
        #     "stadium": "...",
        #     "matches": [...],
        #     "players": [...],
        #     "fixtures": [...],
        #     ...
        #   }
        # The team name is nested under "team.name", not at the
        # top level. We also surface the country so the admin
        # can disambiguate (e.g. "Ferencvaros (HUN)").
        cache_path = f"/home/openclaw/.openclaw/workspace/_live_cache_{team_id}.json"
        if not os.path.exists(cache_path):
            return f"team={team_id}"
        try:
            with open(cache_path) as fh:
                tc = json.load(fh)
        except Exception:
            return f"team={team_id}"
        team_obj = tc.get("team") or {}
        name = (team_obj.get("name") or "").strip()
        country = (team_obj.get("country") or "").strip()
        if name and country:
            return f"{name} ({country})"
        elif name:
            return name
        return f"team={team_id}"
    except Exception:
        return ""


def _log_view_throttled(username: str, ip: str, path: str, min_interval: int = 60) -> None:
    """Like _log_access(action="view") but suppresses duplicate rows.

    Jul 24 2026: every /lineup_ai/<team_id> page load would otherwise
    generate one access_log row, and the team page itself issues
    several internal AJAX calls (squad / fixtures / compare / etc.)
    on a single page render — so without throttling the access_log
    table would fill up with 20+ rows per user visit. With
    min_interval=60s, repeated views of the same path by the same
    user within a minute are dropped. The first view always logs.

    Jul 24 2026 (later same day): the Details column was always
    empty ("") because the logger didn't pass a details value.
    We now resolve the team name (or "A vs B" for match pages)
    via _extract_path_details() so the admin panel shows what
    the user actually opened.
    """
    details = _extract_path_details(path)
    try:
        con = sqlite3.connect(DB_PATH)
        # Check the most recent matching row
        row = con.execute(
            "SELECT timestamp FROM access_log "
            "WHERE username=? AND path=? AND action='view' "
            "ORDER BY id DESC LIMIT 1",
            (username, path),
        ).fetchone()
        if row:
            try:
                last = datetime.fromisoformat(row[0])
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - last).total_seconds()
                if age < min_interval:
                    con.close()
                    return
            except Exception:
                pass  # if timestamp parse fails, just log anyway
        con.execute(
            "INSERT INTO access_log (username, ip, path, action, details, timestamp) "
            "VALUES (?,?,?,?,?,?)",
            (username, ip, path, "view", details, datetime.now(timezone.utc).isoformat()),
        )
        con.commit()
        con.close()
    except Exception:
        pass


def cleanup_old_access_logs(keep: int = 300, threshold_mult: int = 2) -> int:
    """Delete everything from access_log except the newest `keep` rows,
    but only when the table is over `threshold_mult * keep` rows.

    Jul 24 2026 — user explicitly asked to drop the cap-only-threshold
    from /admin: "Старые данные можешь не хранить ... чтобы не
    забивать память". Keeps the most recent `keep` rows (default 300,
    matching the /admin cap from commit 9d18f5b) and DELETEs the rest.

    The threshold_mult guard means the DELETE only fires when the table
    is at least 2x the keep size (600 rows by default), so admin_panel
    does not hit SQLite with a DELETE on every single page load — the
    cleanup runs roughly once per ~300 new events.

    Returns the number of rows deleted (0 if nothing to do).

    Owner rows are deleted too — owner is the service account, not a
    real user, so the cap applies uniformly.
    """
    threshold = keep * threshold_mult
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.execute("SELECT COUNT(*) FROM access_log")
        total = cur.fetchone()[0]
        if total <= threshold:
            return 0
        # Find the id of the (keep+1)th newest row -- everything
        # with a smaller or equal id is older and must be removed,
        # leaving exactly the newest `keep` rows untouched.
        #   ORDER BY id DESC LIMIT 1 OFFSET keep
        #     -> skip the first `keep` rows (newest), return the
        #        (keep+1)th newest row.
        cutoff = con.execute(
            "SELECT id FROM access_log ORDER BY id DESC LIMIT 1 OFFSET ?",
            (keep,),
        ).fetchone()
        if not cutoff:
            return 0
        cur = con.execute("DELETE FROM access_log WHERE id <= ?", (cutoff[0],))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def ensure_db():
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          team TEXT,
          category TEXT,
          impact_level TEXT,
          confidence REAL,
          title TEXT,
          details1 TEXT,
          details2 TEXT,
          details3 TEXT,
          original_text TEXT,
          original_link TEXT,
          telegram_message_id INTEGER
        )
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS tweets (
          tweet_id TEXT PRIMARY KEY,
          created_at TEXT,
          author_id TEXT,
          source_username TEXT,
          text TEXT NOT NULL,
          url TEXT,
          raw_json TEXT,
          kw_pass INTEGER,
          kw_blacklist_hit INTEGER
        )
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS state (
          key TEXT PRIMARY KEY,
          value TEXT
        )
        """
    )

    # Add missing columns for tweets if table existed before
    cols_t = {r[1] for r in con.execute("PRAGMA table_info(tweets)").fetchall()}
    def add_col_t(name: str, ddl: str):
        if name not in cols_t:
            con.execute(f"ALTER TABLE tweets ADD COLUMN {ddl}")

    add_col_t("kw_pass", "kw_pass INTEGER")
    add_col_t("kw_blacklist_hit", "kw_blacklist_hit INTEGER")
    add_col_t("source_username", "source_username TEXT")
    add_col_t("media_url", "media_url TEXT")
    add_col_t("media_type", "media_type TEXT")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          x_requests INTEGER,
          received INTEGER,
          passed_keywords INTEGER,
          stored INTEGER,
          llm_gate_calls INTEGER,
          llm_core_calls INTEGER,
          relevant INTEGER,
          sent INTEGER
        )
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS teams_map (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source TEXT NOT NULL UNIQUE,
          team TEXT NOT NULL
        )
        """
    )

    # tweet_status: status + debug (best-effort migration)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS tweet_status (
          tweet_id TEXT PRIMARY KEY,
          classified_at TEXT,
          relevant INTEGER,
          sent_at TEXT,
          gate_decision TEXT,
          gate_fastpath INTEGER,
          core_json_valid INTEGER,
          core_error TEXT,
          core_preview TEXT,
          duplicate_of TEXT
        )
        """
    )

    cols = {r[1] for r in con.execute("PRAGMA table_info(tweet_status)").fetchall()}
    def add_col(name: str, ddl: str):
        if name not in cols:
            con.execute(f"ALTER TABLE tweet_status ADD COLUMN {ddl}")

    add_col("gate_decision", "gate_decision TEXT")
    add_col("gate_fastpath", "gate_fastpath INTEGER")
    add_col("core_json_valid", "core_json_valid INTEGER")
    add_col("core_error", "core_error TEXT")
    add_col("core_preview", "core_preview TEXT")
    add_col("duplicate_of", "duplicate_of TEXT")
    add_col("image_mode", "image_mode TEXT")  # '', 'media', 'og'

    # --- Users table ---
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL,
          plain_password TEXT,
          is_admin INTEGER NOT NULL DEFAULT 0,
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          last_login TEXT
        )
    """)
    # Add plain_password column if missing
    try:
        con.execute("ALTER TABLE users ADD COLUMN plain_password TEXT")
    except Exception:
        pass
    # Seed default admin if table is empty
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        _ph = _hash_password("admin")
        con.execute("INSERT INTO users (username, password_hash, is_admin, active, created_at) VALUES (?,?,?,?,?)",
                     ("admin", _ph, 1, 1, datetime.now(timezone.utc).isoformat()))

    # --- Access log ---
    con.execute("""
        CREATE TABLE IF NOT EXISTS access_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL,
          ip TEXT,
          path TEXT,
          action TEXT,
          details TEXT,
          timestamp TEXT NOT NULL
        )
    """)


    con.execute("""
        CREATE TABLE IF NOT EXISTS user_lineup_saves (
            id        INTEGER PRIMARY KEY,
            username  TEXT NOT NULL,
            team_id   TEXT NOT NULL,
            save_name TEXT NOT NULL DEFAULT 'Default',
            save_data TEXT NOT NULL,
            saved_at  TEXT NOT NULL,
            UNIQUE(username, team_id, save_name)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS user_lineup_snapshots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT NOT NULL,
            team_id   TEXT NOT NULL,
            name      TEXT NOT NULL,
            snapshot_data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_lineup_snapshots_user_team ON user_lineup_snapshots(username, team_id, created_at DESC)")
    # User favorites table
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            player_id TEXT NOT NULL,
            player_data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(username, player_id)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_user_favorites_username ON user_favorites(username)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_match_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            match_id TEXT NOT NULL,
            home_id TEXT,
            away_id TEXT,
            home_name TEXT,
            away_name TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(username, match_id)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_user_match_favorites_username ON user_match_favorites(username)")


    con.execute("""
        CREATE TABLE IF NOT EXISTS team_data_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            data_json TEXT NOT NULL,
            data_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_checked_at TEXT NOT NULL,
            is_current INTEGER NOT NULL DEFAULT 1,
            UNIQUE(team_id, version)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_team_versions_current ON team_data_versions(team_id, is_current, version DESC)")

    con.commit()
    con.close()


def build_signal(
    time_msk: str,
    team: str,
    category: str,
    impact_level: str,
    confidence: float,
    title: str,
    details1: str,
    details2: str,
    details3: str,
    original_text: str,
    original_link: str,
) -> str:
    emoji_map = {
        "lineup_change": "🟢",
        "injury_update": "⚠️",
        "suspension": "⛔️",
        "rotation_risk": "🔄",
        "tactical_leak": "🧠",
        "national_team_callup": "🌍",
        "squad_list": "📋",
    }
    emoji = emoji_map.get(category, "🚨")

    # Telegram quote: MUST be exact raw text, prefixed with > per line
    quoted = "\n".join(["> " + line for line in (original_text or "").splitlines()])

    market_effect = "Ожидается движение линии/коэффициентов из-за новости. Проверь рынки составов, игрока/команды и лайв-лимиты."

    parts = [
        f"🎨 ALERT • {time_msk} МСК",
        "",
        (team or "").strip(),
        "",
        f"{emoji} {(title or '').strip()}",
        "",
        (details1 or "").strip(),
        (details2 or "").strip(),
    ]
    if (details3 or "").strip():
        parts.append((details3 or "").strip())

    parts += [
        "",
        "📌 ОРИГИНАЛ:",
        "",
        quoted,
        "",
        f"🔗 Source: {original_link}",
        "",
        f"Влияние: {impact_level}",
        "",
        f"📊 {market_effect}",
        "",
        "━━━━━━━━━━━━━━",
        f"Уверенность: {confidence:.2f}",
        f"Категория: {category}",
    ]

    # Remove empty lines caused by missing optional fields
    out = "\n".join([p for p in parts if p is not None])
    # compress multiple blank lines a bit
    out = "\n".join([line for line in out.splitlines()])
    return out


def html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def send_telegram(text: str) -> int | None:
    return await send_telegram_message(text)


async def send_telegram_message(text: str) -> int | None:
    if not BOT_TOKEN or not CHAT_ID:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = (r.text or "").strip()
            raise RuntimeError(f"Telegram sendMessage error {r.status_code}: {detail}")
        data = r.json()
        return data.get("result", {}).get("message_id")


async def send_telegram_photo(photo_url: str, caption: str) -> int | None:
    if not BOT_TOKEN or not CHAT_ID:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.post(url, json=payload)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = (r.text or "").strip()
            raise RuntimeError(f"Telegram sendPhoto error {r.status_code}: {detail}")
        data = r.json()
        return data.get("result", {}).get("message_id")


def _extract_first_url(text: str) -> str:
    import re as _re
    t = (text or "")
    # prefer explicit http(s) urls
    m = _re.search(r"https?://\S+", t)
    if m:
        return m.group(0).rstrip(').,]')
    return ""


async def _fetch_og_image(url: str) -> str:
    """Fetch a page and extract og:image/twitter:image URL."""
    if not url:
        return ""
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers={"User-Agent": "FormAlert/1.0"}) as client:
            r = await client.get(url)
            if r.status_code >= 400:
                return ""
            html = r.text or ""
    except Exception:
        return ""

    import re as _re
    # og:image
    m = _re.search(r"<meta[^>]+property=['\"]og:image['\"][^>]+content=['\"]([^'\"]+)['\"]", html, flags=_re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = _re.search(r"<meta[^>]+name=['\"]twitter:image['\"][^>]+content=['\"]([^'\"]+)['\"]", html, flags=_re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


async def _fd_get(path: str, params: dict | None = None) -> dict:
    if not FOOTBALL_DATA_TOKEN:
        return {}
    url = FOOTBALL_DATA_BASE.rstrip('/') + path
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
            r = await client.get(url, params=params or {})
            if r.status_code >= 400:
                return {}
            return r.json() or {}
    except Exception:
        return {}


def _norm_team_name(s: str) -> str:
    s = _norm_text(s)
    s = s.lower().replace('fc', '').replace('sc', '').replace('ac', '')
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


async def _fd_find_team_id_fl1(team_name: str) -> int | None:
    """Best-effort map FormAlert team name -> football-data team id (FL1 only)."""
    name = (team_name or '').strip()
    if not name:
        return None
    data = await _fd_get('/v4/competitions/FL1/teams')
    teams = data.get('teams') or []
    target = _norm_team_name(name)
    best = None
    for t in teams:
        cand = _norm_team_name(str(t.get('name') or ''))
        cand2 = _norm_team_name(str(t.get('shortName') or ''))
        cand3 = _norm_team_name(str(t.get('tla') or ''))

        # Special-case Rennes (football-data uses 'Stade Rennais...')
        if target == 'rennes' and ('rennais' in cand or 'rennais' in cand2):
            return int(t.get('id'))

        if target and (target == cand or target == cand2 or target == cand3):
            return int(t.get('id'))
        # loose contains match
        if target and (target in cand or cand in target):
            best = int(t.get('id'))
    return best


async def _fd_is_within_starting_xi_window(team_name: str, window_minutes: int = 80) -> bool:
    """Return True if there is exactly one FL1 match for the team today and kickoff is within next window_minutes.

    If team cannot be mapped to FL1 team id, returns False.
    """
    from datetime import timedelta
    now_utc = datetime.now(timezone.utc)
    today = (now_utc + timedelta(hours=3)).date()  # MSK date
    date_from = today.strftime('%Y-%m-%d')
    date_to = today.strftime('%Y-%m-%d')

    tid = await _fd_find_team_id_fl1(team_name)
    if not tid:
        return False

    data = await _fd_get('/v4/competitions/FL1/matches', params={"dateFrom": date_from, "dateTo": date_to})
    matches = data.get('matches') or []
    rel = []
    for m in matches:
        try:
            h = m.get('homeTeam') or {}
            a = m.get('awayTeam') or {}
            if int(h.get('id') or 0) == int(tid) or int(a.get('id') or 0) == int(tid):
                rel.append(m)
        except Exception:
            continue

    # If 0 or >1 matches today => do not enable
    if len(rel) != 1:
        return False

    utc_dt = str(rel[0].get('utcDate') or '')
    if not utc_dt:
        return False
    try:
        dt = datetime.fromisoformat(utc_dt.replace('Z', '+00:00'))
    except Exception:
        return False

    delta = (dt - now_utc).total_seconds() / 60.0
    return (0 <= delta <= float(window_minutes))


app = FastAPI(title=APP_TITLE)



# --- Auth middleware ---
PUBLIC_PATHS = {"/health", "/favicon.ico", "/login", "/logout"}

# Session cookie signing
# Jul 30 2026 v8: runtime-generated session secret.
# Each server restart gets a fresh secret (so old cookies from
# previous deployments are immediately invalid). Admin can also
# rotate via POST /admin/rotate-secret to kill all active sessions.
import secrets as _secrets_mod
import secrets as _secrets_mod
_SESSION_SECRET_FILE = "/home/openclaw/FormAlert/.session_secret"
_SESSION_SECRET = None
_SESSION_SECRET_GENERATED_AT = None

# 1. env var (highest priority - explicit override)
_env_secret = os.environ.get("FORMALERT_SESSION_SECRET")
if _env_secret:
    _SESSION_SECRET = _env_secret
    _SESSION_SECRET_GENERATED_AT = time.time()

# 2. persistent file (survives restarts)
if _SESSION_SECRET is None:
    try:
        with open(_SESSION_SECRET_FILE, "r") as _sf:
            _loaded = _sf.read().strip()
            if _loaded and len(_loaded) >= 32:
                _SESSION_SECRET = _loaded
                _SESSION_SECRET_GENERATED_AT = time.time()
    except FileNotFoundError:
        pass
    except Exception:
        pass

# 3. generate new and save (one-time)
if _SESSION_SECRET is None:
    _SESSION_SECRET = _secrets_mod.token_hex(32)
    _SESSION_SECRET_GENERATED_AT = time.time()
    try:
        with open(_SESSION_SECRET_FILE, "w") as _sf:
            _sf.write(_SESSION_SECRET)
        try:
            import os as _os_mod
            _os_mod.chmod(_SESSION_SECRET_FILE, 0o600)
        except Exception:
            pass
    except Exception:
        pass

def _make_session_token(username: str, is_admin: bool) -> str:
    """Create signed session token: base64(username:is_admin:timestamp:hmac)"""
    import base64 as _b64, hmac as _hmac
    ts = str(int(time.time()))
    payload = f"{username}:{int(is_admin)}:{ts}"
    sig = _hmac.new(_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    token = f"{payload}:{sig}"
    return _b64.b64encode(token.encode()).decode()

def _parse_session_token(token: str) -> tuple[str, bool] | None:
    """Verify and parse session token. Returns (username, is_admin) or None."""
    import base64 as _b64, hmac as _hmac
    try:
        decoded = _b64.b64decode(token).decode()
        parts = decoded.split(":")
        if len(parts) != 4:
            return None
        username, admin_str, ts, sig = parts
        payload = f"{username}:{admin_str}:{ts}"
        expected_sig = _hmac.new(_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        if sig != expected_sig:
            return None
        # Token valid for 30 days
        if int(time.time()) - int(ts) > 30 * 86400:
            return None
        return (username, admin_str == "1")
    except Exception:
        return None
# Jul 29 2026: cache for user active-status so deactivate takes effect within TTL.
# Without this, deactivated users keep their cookie valid until 30-day expiry.
import time as _time_mod

# Jul 30 2026 v5: _active_user_cache removed — DB is source of truth.

# Jul 30 2026: PERMANENT BAN table. A username here is blocked
# regardless of the `active` flag. Must be removed manually.
# This is a hard block that survives admin_toggle.
def _is_banned(username: str) -> bool:
    """Return True if username is in banned_users table.

    Always reads from DB on every call (no cache). SQLite is
    fast enough (~10 us) and we want the ban to take effect
    immediately when added.
    """
    if not username:
        return False
    try:
        import sqlite3 as _sq
        con = _sq.connect(DB_PATH)
        row = con.execute(
            "SELECT 1 FROM banned_users WHERE username=? LIMIT 1",
            (username,)
        ).fetchone()
        con.close()
        return row is not None
    except Exception:
        return False


def _is_ip_banned(ip: str) -> bool:
    """v9+v11: IP ban check covers BOTH banned_ips table
    AND historical usage by banned_username.

    Returns True if:
      - ip is in banned_ips, OR
      - ip appears in access_log for ANY username in banned_users

    The second check catches NEW IPs the user starts using
    AFTER deactivation - they're picked up on the very next
    request from that IP.

    Always reads DB on every call. SQLite is fast enough.
    """
    if not ip or ip in {"", "127.0.0.1", "::1"}:
        return False
    try:
        import sqlite3 as _sq
        con = _sq.connect(DB_PATH)
        # (a) direct ban
        row = con.execute(
            "SELECT 1 FROM banned_ips WHERE ip=? LIMIT 1",
            (ip,)
        ).fetchone()
        if row:
            con.close()
            return True
        # (b) historical: this IP used by a banned user?
        row = con.execute(
            "SELECT 1 FROM access_log WHERE ip=? AND username IN (SELECT username FROM banned_users) LIMIT 1",
            (ip,)
        ).fetchone()
        con.close()
        return row is not None
    except Exception:
        return False


def _ban_ip_for_username(username: str) -> int:
    """v9: add all IPs known for this username to banned_ips.

    Reads access_log to find all IPs that user used,
    inserts them into banned_ips. Returns count of
    IPs banned.
    """
    if not username:
        return 0
    try:
        import sqlite3 as _sq
        con = _sq.connect(DB_PATH)
        rows = con.execute(
            "SELECT DISTINCT ip FROM access_log WHERE username=? AND ip IS NOT NULL",
            (username,)
        ).fetchall()
        for (ip,) in rows:
            if ip and ip not in {"127.0.0.1", "::1"}:
                con.execute(
                    "INSERT OR IGNORE INTO banned_ips (ip, username, banned_at) VALUES (?, ?, ?)",
                    (ip, username, datetime.now(timezone.utc).isoformat())
                )
        con.commit()
        con.close()
        return len(rows)
    except Exception:
        return 0


def _is_user_active(username: str) -> bool:
    """Return True if user exists and active=1.

    Jul 30 2026 v5: REMOVED CACHE. The DB is the source of truth.
    Every call hits SQLite (~10 us). This guarantees that any
    active=0 update is reflected on the very next request,
    with no 5-second race window. The previous caching was a
    premature optimization that defeated deactivation.
    """
    if not username:
        return False
    try:
        import sqlite3 as _sq
        con = _sq.connect(DB_PATH)
        row = con.execute("SELECT active FROM users WHERE username=?", (username,)).fetchone()
        con.close()
        return bool(row[0]) if row else False
    except Exception:
        # DB error: fail closed — assume inactive to be safe.
        return False

def _invalidate_active_user_cache(username: str | None = None) -> None:
    """Clear cached active status. Called by admin_toggle for instant effect."""
    if username is None:
        _active_user_cache.clear()
    elif username in _active_user_cache:
        del _active_user_cache[username]

# Jul 30 2026 v5: removed _killed_sessions helpers — DB is source of truth.

# IPs that bypass auth completely (owner VPN + direct)
IP_WHITELIST = {
    "217.107.106.0/24",
    "152.53.124.0/22",
    "159.195.0.0/16",
    "165.154.155.0/24",
    "185.215.184.0/24",
    "85.192.48.0/24",
    "45.92.219.0/24",
    "85.9.196.0/24",
    "50.7.177.0/24",
    "212.193.4.0/24",
    "37.203.37.0/24",
    "77.90.188.0/24",
    "127.0.0.1",
}

import ipaddress as _ip

def _ip_whitelisted(ip_str: str) -> bool:
    if not ip_str:
        return False
    try:
        addr = _ip.ip_address(ip_str)
        for cidr in IP_WHITELIST:
            if "/" in cidr:
                if addr in _ip.ip_network(cidr, strict=False):
                    return True
            elif ip_str == cidr:
                return True
    except Exception:
        pass
    return False

# Flash messages (uuid -> msg), auto-expire
_flash_store: dict[str, tuple[str, float]] = {}

def _flash_set(msg: str) -> str:
    key = secrets.token_hex(8)
    _flash_store[key] = (msg, time.time() + 60)  # expires in 60s
    return key

def _flash_get(key: str) -> str:
    if key in _flash_store:
        msg, _ = _flash_store.pop(key)
        return msg
    return ""

# Cleanup old flashes
def _flash_cleanup():
    now = time.time()
    expired = [k for k, (_, exp) in _flash_store.items() if now > exp]
    for k in expired:
        del _flash_store[k]

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    client_ip = request.client.host if request.client else ""
    # Jul 30 2026 v9/v11: IP-based ban check runs FIRST.
    # Blocked at network level - even anonymous requests
    # from a banned IP get 403. No way around it.
    #
    # v11: also catches HISTORICAL IPs of banned users via
    # access_log, so users can't escape by switching to a
    # new IP that wasn't in the snapshot at deactivation time.
    if path.strip("/") not in {"login"}:
        try:
            if _is_ip_banned(client_ip):
                resp = HTMLResponse(
                    status_code=403,
                    content="<h1>403 Forbidden</h1>"
                            "<p>Ваш IP адрес заблокирован. Пожалуйста, обратитесь к администратору.</p>"
                )
                resp.delete_cookie("fa_session", path="/")
                return resp
        except Exception:
            pass
        # v11 ban-on-sight: if a request arrives with a banned-user
        # cookie, ban the IP NOW. Catches new IPs the moment the
        # banned user tries to use them.
        try:
            mws_cookie = request.cookies.get("fa_session")
            if mws_cookie:
                mws_info = _parse_session_token(mws_cookie)
                if mws_info and _is_banned(mws_info[0]):
                    # Banned user. Ban this IP on-the-fly.
                    try:
                        import sqlite3 as _sq2
                        _con2 = _sq2.connect(DB_PATH)
                        _con2.execute(
                            "INSERT OR IGNORE INTO banned_ips (ip, username, banned_at, reason) VALUES (?, ?, ?, ?)",
                            (client_ip, mws_info[0], datetime.now(timezone.utc).isoformat(), "ban-on-sight v11")
                        )
                        _con2.commit()
                        _con2.close()
                    except Exception:
                        pass
                    resp = HTMLResponse(
                        status_code=403,
                        content="<h1>403 Forbidden</h1>"
                                "<p>Ваш аккаунт и IP адрес заблокированы. Пожалуйста, обратитесь к администратору.</p>"
                    )
                    resp.delete_cookie("fa_session", path="/")
                    return resp
        except Exception:
            pass
    # Jul 24 2026: log /lineup_ai/* view events EVEN on the public skip
    # path. Without this, only /login (action=login) and /admin (admin
    # events) are recorded in access_log, so the /admin Recent Activity
    # panel misses all "user opened a team page" events. We only log
    # when there is a valid session cookie (real logged-in user); if
    # the cookie is missing or invalid we still let the request through
    # anonymously because /lineup_ai/* is intentionally public.
    if path.startswith("/lineup_ai") and not path.endswith(".json"):
        session_cookie = request.cookies.get("fa_session")
        if session_cookie:
            user_info = _parse_session_token(session_cookie)
            # Jul 29 2026: skip deactivated users for /lineup_ai logging too.
            if user_info and _is_user_active(user_info[0]):
                # Mirror the username onto request.state so the route
                # handler (and any downstream code) can read it as
                # if the request had gone through the full auth path.
                request.state.username = user_info[0]
                request.state.is_admin = user_info[1]
                # Throttled so the team page's many internal AJAX calls
                # (squad / fixtures / compare) do not flood access_log.
                _log_view_throttled(user_info[0], client_ip, path)
    # Jul 30 2026 v3: blocked-active check covers ALL paths
    # the middleware reaches (HTML, JSON, AJAX, API, /team/*).
    #
    # v2 also blocked /login, /logout, /health, /favicon.ico for
    # deactivated users, which broke the redirect-to-login flow on
    # /team/* (the user saw a 403 instead of a login page). v3
    # only excludes /login and /logout so the user CAN see the
    # login page (and a clear message there). The /login POST
    # handler still checks active=1 in SQL — so even if the page
    # is reachable, deactivated users cannot log in.
    #
    # /health and /favicon.ico are NOT excluded here (they aren't
    # called by browsers for users anyway). Truly public paths
    # (no auth needed for anonymous) are handled by the skip-list
    # below.
    if path.strip("/") not in {"login", "logout"}:
        session_cookie = request.cookies.get("fa_session")
        if session_cookie:
            user_info_for_block = _parse_session_token(session_cookie)
            if user_info_for_block and not _is_user_active(user_info_for_block[0]):
                # Deactivated user with valid cookie -> reject.
                # Clear the stale cookie so the browser stops sending it.
                resp = HTMLResponse(
                    status_code=403,
                    content="<h1>403 Forbidden</h1>"
                            "<p>Ваш аккаунт деактивирован. Пожалуйста, обратитесь к администратору.</p>"
                )
                resp.delete_cookie("fa_session", path="/")
                return resp
    # Jul 30 2026 v6: PERMANENT BAN check runs BEFORE public-path skip
    # and BEFORE any auth. A banned username is blocked even on
    # /lineup_ai/* public paths. This survives admin_toggle.
    if path.strip("/") not in {"login", "logout"}:
        session_cookie_for_ban = request.cookies.get("fa_session")
        if session_cookie_for_ban:
            user_info_for_ban = _parse_session_token(session_cookie_for_ban)
            if user_info_for_ban and _is_banned(user_info_for_ban[0]):
                resp = HTMLResponse(
                    status_code=403,
                    content="<h1>403 Forbidden</h1>"
                            "<p>Ваш аккаунт заблокирован. Пожалуйста, обратитесь к администратору.</p>"
                )
                resp.delete_cookie("fa_session", path="/")
                return resp
    if (path in PUBLIC_PATHS or path.startswith("/icons/") or path.startswith("/vision_uploads/")
            or path.startswith("/api/favorites") or path.startswith("/lineup_ai")):
        # Jul 30 2026 v7: defensive double-check. Even public paths
        # must reject banned users. The v6 check at the top of the
        # middleware handles this, but as a belt-and-suspenders
        # measure, check again here before letting the request through.
        if path.startswith("/lineup_ai") and not path.endswith(".json"):
            sk_cookie = request.cookies.get("fa_session")
            if sk_cookie:
                sk_info = _parse_session_token(sk_cookie)
                if sk_info and _is_banned(sk_info[0]):
                    resp = HTMLResponse(
                        status_code=403,
                        content="<h1>403 Forbidden</h1>"
                                "<p>Ваш аккаунт заблокирован. Пожалуйста, обратитесь к администратору.</p>"
                    )
                    resp.delete_cookie("fa_session", path="/")
                    return resp
        return await call_next(request)
    # Check IP whitelist
    if _ip_whitelisted(client_ip):
        request.state.username = "owner"
        request.state.is_admin = True
        # Track admin panel visits as "last login" for the admin user.
        if path == "/admin" or path.startswith("/admin/"):
            try:
                con = sqlite3.connect(DB_PATH)
                con.execute("UPDATE users SET last_login=? WHERE username='admin'",
                             (datetime.now(timezone.utc).isoformat(),))
                con.commit()
                con.close()
            except Exception:
                pass
        return await call_next(request)
    # Check session cookie
    session_cookie = request.cookies.get("fa_session")
    user_info = None
    if session_cookie:
        user_info = _parse_session_token(session_cookie)
        # Jul 29 2026: reject sessions for deactivated users (active=0)
        if user_info and not _is_user_active(user_info[0]):
            user_info = None
            # Clear the stale cookie so the browser stops sending it.
            _ = session_cookie  # keep linter happy
    if not user_info:
        # Redirect to login page with return URL
        from urllib.parse import quote
        resp = RedirectResponse(url=f"/login?next={quote(path)}", status_code=302)
        # Jul 29 2026: tell the browser to drop the now-invalid session cookie.
        resp.delete_cookie("fa_session", path="/")
        return resp
    request.state.username = user_info[0]
    request.state.is_admin = user_info[1]
    # Block /admin for non-admin users
    if path == "/admin" or path.startswith("/admin/"):
        if not request.state.is_admin:
            return HTMLResponse(status_code=403, content="<h1>403 Forbidden</h1><p>Доступ запрещён</p>")
    # Log access (throttled — only /lineup_ai pages)
    if "/lineup_ai" in path and not path.endswith(".json"):
        _log_access(request.state.username, client_ip, path, "view")
    return await call_next(request)

from fastapi.staticfiles import StaticFiles
app.mount("/icons", StaticFiles(directory="/home/openclaw/FormAlert/icons"), name="icons")
app.mount("/static", StaticFiles(directory="/home/openclaw/FormAlert/static"), name="static")
os.makedirs("/home/openclaw/FormAlert/vision_uploads", exist_ok=True)
app.mount("/vision_uploads", StaticFiles(directory="/home/openclaw/FormAlert/vision_uploads"), name="vision_uploads")

# --- Login / Logout routes ---
_LOGIN_STYLE = """
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            margin: 0;
            padding: 40px;
            /* Jul 30 2026: login background image (1672x941 png) */
            background:
              linear-gradient(rgba(0,0,0,0.45), rgba(0,0,0,0.45)),
              url('/static/login_bg.png') center center / cover no-repeat fixed;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            max-width: 420px;
            width: 100%;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 {
            color: #333;
            margin-top: 0;
            font-size: 28px;
            text-align: center;
        }
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 32px;
            font-size: 15px;
        }
        .form-group {
            margin-bottom: 24px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 600;
            font-size: 14px;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            background: white;
            transition: all 0.3s;
        }
        input:hover {
            border-color: #667eea;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
            transition: opacity 0.3s;
        }
        button:hover {
            opacity: 0.9;
        }
        .error {
            background: #fee;
            color: #c00;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 14px;
            text-align: center;
        }
    </style>
"""

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve the real .ico file (48x48 MS Windows icon).
    Jul 30 2026: switched from PNG masquerade to actual ICO
    after user supplied full realfavicongenerator bundle."""
    from fastapi.responses import FileResponse
    return FileResponse(
        "/home/openclaw/FormAlert/static/favicon.ico",
        media_type="image/x-icon"
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(next: str = "/"):
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Sign In — LineupValue</title>
  <link rel="icon" type="image/x-icon" href="/favicon.ico">
  <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">
  <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png">
  <link rel="manifest" href="/static/site.webmanifest">
  {_LOGIN_STYLE}
</head>
<body>
<div class="container">
  <h1>📊 LineupValue</h1>
  <p class="subtitle">Sign in to continue</p>
  <form method="post" action="/login">
    <input type="hidden" name="next" value="{html_escape(next)}"/>
    <div class="form-group">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" placeholder="Enter username" required autofocus/>
    </div>
    <div class="form-group">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" placeholder="Enter password" required/>
    </div>
    <button type="submit">Sign In</button>
  </form>
</div>
</body>
</html>"""
    return HTMLResponse(html)

@app.post("/login")
async def login_submit(username: str = Form(...), password: str = Form(...), next: str = Form(default="/")):
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT username, password_hash, is_admin, active FROM users WHERE username=? AND active=1", (username,)).fetchone()
    con.close()
    if not row or not _verify_password(password, row[1]):
        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Sign In — LineupValue</title>
  <link rel="icon" type="image/x-icon" href="/favicon.ico">
  <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">
  <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png">
  <link rel="manifest" href="/static/site.webmanifest">
  {_LOGIN_STYLE}
</head>
<body>
<div class="container">
  <h1>📊 LineupValue</h1>
  <p class="subtitle">Sign in to continue</p>
  <div class="error">Invalid username or password</div>
  <form method="post" action="/login">
    <input type="hidden" name="next" value="{html_escape(next)}"/>
    <div class="form-group">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" placeholder="Enter username" value="{html_escape(username)}" required autofocus/>
    </div>
    <div class="form-group">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" placeholder="Enter password" required/>
    </div>
    <button type="submit">Sign In</button>
  </form>
</div>
</body>
</html>"""
        return HTMLResponse(html, status_code=401)
    # Valid credentials — set session cookie and redirect
    is_admin = bool(row[2])
    # Jul 24 2026: log the successful login as action="login" so it shows
    # up in /admin Recent Activity. Before this fix, /login never wrote
    # to access_log at all, so the admin panel only ever saw "view"
    # events from /lineup_ai/track. Now we record one login event per
    # successful POST /login, and last_login is bumped automatically
    # by _log_access (it checks action == "login").
    try:
        client_ip = request.client.host if request.client else "?"
    except Exception:
        client_ip = "?"
    _log_access(username, client_ip, "/login", "login")
    token = _make_session_token(username, is_admin)
    response = RedirectResponse(url=next or "/", status_code=303)
    response.set_cookie(
        key="fa_session",
        value=token,
        max_age=30 * 86400,  # 30 days
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="fa_session", path="/")
    return response

# --- LineUp AI routes ---
from fastapi.responses import JSONResponse
import sys
sys.path.insert(0, "/home/openclaw/FormAlert")
from lineup_team_view import render_team_view
from lineup_data_complete import load_complete_hierarchy


def _lineup_account(request: Request) -> str:
    """Stable per-user key for lineup saves. Uses authenticated username when available."""
    auth_user = getattr(getattr(request, "state", None), "username", None)
    if auth_user:
        return str(auth_user)[:120]
    import hashlib
    for header in ("x-forwarded-user", "x-auth-user", "remote-user"):
        val = (request.headers.get(header) or "").strip()
        if val:
            return val[:120]
    cookie_user = (request.cookies.get("formalert_user") or "").strip()
    if cookie_user:
        return cookie_user[:120]
    raw = f"{request.client.host if request.client else ''}|{request.headers.get('user-agent','')}"
    return "anon:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _team_cache_path(team_id: str) -> str:
    return os.path.join("/home/openclaw/.openclaw/workspace", f"_live_cache_{team_id}.json")


def _cache_age_seconds(team_id: str) -> float | None:
    path = _team_cache_path(team_id)
    if not os.path.exists(path):
        return None
    return max(0.0, time.time() - os.path.getmtime(path))


def _read_team_cache(team_id: str) -> dict:
    with open(_team_cache_path(team_id), "r", encoding="utf-8") as f:
        return json.load(f)


def _lookup_lineup_team(team_id: str) -> dict:
    try:
        hierarchy = load_complete_hierarchy()
        for leagues in hierarchy.values():
            if not isinstance(leagues, dict):
                continue
            for teams in leagues.values():
                if not isinstance(teams, list):
                    continue
                for team in teams:
                    if isinstance(team, dict) and str(team.get("id")) == str(team_id):
                        name = str(team.get("name") or team_id)
                        slug = str(team.get("slug") or "").strip()
                        if not slug:
                            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                        return {"id": team_id, "name": name, "slug": slug, "stadium": team.get("stadium") or ""}
    except Exception:
        pass
    return {"id": team_id, "name": team_id, "slug": ""}



TEAM_VERSION_CHECK_TTL = 3 * 3600
TEAM_VERSION_KEEP = 20


def _version_canonical_player(p: dict) -> dict:
    return {
        "name": str(p.get("name") or ""),
        "number": str(p.get("number") or p.get("shirt_number") or ""),
        "nationality": str(p.get("nationality") or ""),
        "status": str(p.get("status") or ""),
        "age": str(p.get("age") or ""),
        "mv": str(p.get("mv") or p.get("market_value") or ""),
        "pos": str(p.get("pos") or p.get("position") or ""),
        "impact_score": str(p.get("impact_score") or ""),
        "squad_role": str(p.get("squad_role") or ""),
        "last3": p.get("last3") or [],
        "last3_missing": p.get("last3_missing") or [],
        "last3_captain": p.get("last3_captain") or [],
        "apps": str(p.get("apps") or p.get("app") or p.get("appearances") or ""),
        "min": str(p.get("min") or p.get("minutes") or ""),
        "goal": str(p.get("goal") or p.get("goals") or ""),
        "assist": str(p.get("assist") or p.get("assists") or ""),
        "yellow_card": str(p.get("yellow_card") or p.get("yellow_cards") or ""),
        "red_card": str(p.get("red_card") or p.get("red_cards") or ""),
    }


def _team_version_subset(data: dict) -> dict:
    players = data.get("players") if isinstance(data, dict) else []
    if players is None: players = []
    matches = data.get("matches") if isinstance(data, dict) else []
    if matches is None: matches = []
    return {
        "team": data.get("team") or {},
        "coach": data.get("coach") or {},
        "stadium": data.get("stadium") or "",
        "players": sorted([_version_canonical_player(p) for p in players if isinstance(p, dict)], key=lambda x: x.get("name", "")),
        "matches": [
            {
                "date": str(m.get("date") or ""),
                "tournament": str(m.get("tournament") or m.get("comp") or ""),
                "score": str(m.get("score") or ""),
                "home_team": str(m.get("home_team") or ""),
                "away_team": str(m.get("away_team") or ""),
                "mid": str(m.get("mid") or ""),
            }
            for m in matches if isinstance(m, dict)
        ],
    }


def _team_data_hash(data: dict) -> str:
    subset = _team_version_subset(data)
    return hashlib.sha256(json.dumps(subset, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _get_current_team_version(team_id: str) -> dict | None:
    ensure_db()
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT id, version, data_json, data_hash, created_at, last_checked_at FROM team_data_versions WHERE team_id=? AND is_current=1 ORDER BY version DESC LIMIT 1",
        (team_id,),
    ).fetchone()
    con.close()
    if not row:
        return None
    return {"id": row[0], "version": row[1], "data": json.loads(row[2]), "hash": row[3], "created_at": row[4], "last_checked_at": row[5]}


def _save_team_version(team_id: str, data: dict, data_hash: str | None = None, checked_only: bool = False) -> dict:
    ensure_db()
    now = datetime.now(timezone.utc).isoformat()
    data_hash = data_hash or _team_data_hash(data)
    con = sqlite3.connect(DB_PATH)
    current = con.execute(
        "SELECT id, version, data_hash FROM team_data_versions WHERE team_id=? AND is_current=1 ORDER BY version DESC LIMIT 1",
        (team_id,),
    ).fetchone()
    if current and current[2] == data_hash:
        con.execute("UPDATE team_data_versions SET last_checked_at=? WHERE id=?", (now, current[0]))
        con.commit()
        con.close()
        return {"created": False, "version": current[1], "checked_at": now}
    next_version = (int(current[1]) + 1) if current else 1
    con.execute("UPDATE team_data_versions SET is_current=0 WHERE team_id=?", (team_id,))
    con.execute(
        "INSERT INTO team_data_versions(team_id, version, data_json, data_hash, created_at, last_checked_at, is_current) VALUES(?,?,?,?,?,?,1)",
        (team_id, next_version, json.dumps(data, ensure_ascii=False), data_hash, now, now),
    )
    # Keep latest N versions only.
    stale = con.execute(
        "SELECT id FROM team_data_versions WHERE team_id=? ORDER BY version DESC LIMIT -1 OFFSET ?",
        (team_id, TEAM_VERSION_KEEP),
    ).fetchall()
    if stale:
        con.executemany("DELETE FROM team_data_versions WHERE id=?", stale)
    con.commit()
    con.close()
    return {"created": True, "version": next_version, "checked_at": now}


def _write_team_cache(team_id: str, data: dict) -> None:
    path = _team_cache_path(team_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)




def _team_version_refresh_lock_path(team_id: str) -> str:
    return os.path.join("/tmp", f"formalert_refresh_{re.sub(r'[^A-Za-z0-9_.-]', '_', team_id)}.lock")


def _refresh_lock_is_active(path: str, max_age: int = 1800) -> bool:
    if not os.path.exists(path):
        return False
    try:
        age = time.time() - os.path.getmtime(path)
        if age > max_age:
            os.remove(path)
            return False
    except Exception:
        pass
    return True


def _is_team_refresh_running(team_id: str) -> bool:
    return _refresh_lock_is_active(_team_version_refresh_lock_path(team_id))


def _is_any_team_refresh_running() -> bool:
    return _refresh_lock_is_active("/tmp/formalert_refresh_global.lock")


def _start_team_version_refresh(team_id: str) -> bool:
    """Start a detached, serialized refresh. Page rendering must never wait for it."""
    # Soccerway/Playwright is heavy on the VPS: allow only one background refresh
    # globally. Extra page opens must stay fast and skip scheduling.
    if _is_any_team_refresh_running() or _is_team_refresh_running(team_id):
        return False
    # For protected teams (managed by non-Soccerway source like Flashscore prefill),
    # do NOT start a Soccerway refresh — it would clobber the prebuilt cache.
    try:
        import json as _json_p
        with open("/home/openclaw/.openclaw/workspace/_protected_teams.json", "r") as _f:
            _protected_p = set(_json_p.load(_f))
        if team_id in _protected_p:
            return False
    except Exception:
        pass
    script = os.path.join(os.path.dirname(__file__), "refresh_team_version.py")
    if not os.path.exists(script):
        return False
    try:
        subprocess.Popen(
            ["/home/openclaw/FormAlert/.venv/bin/python3", script, team_id],
            cwd="/home/openclaw/FormAlert",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception:
        return False

def _fetch_fresh_team_data(team_id: str, base_data: dict | None = None) -> dict | None:
    base_data = base_data or {}
    team = (base_data.get("team") if isinstance(base_data, dict) else {}) or {}
    lookup_team = _lookup_lineup_team(team_id)
    if not team.get("name") or team.get("name") == team_id:
        team = lookup_team
    elif not team.get("slug") and lookup_team.get("slug"):
        team["slug"] = lookup_team.get("slug")
    team_name = team.get("name") or team_id
    team_slug = team.get("slug") or re.sub(r"[^a-z0-9]+", "-", team_name.lower()).strip("-")
    coach_nat = ((base_data.get("coach") or {}) if isinstance(base_data, dict) else {}).get("nationality") or ""
    stadium = (base_data.get("stadium") if isinstance(base_data, dict) else "") or team.get("stadium") or ""
    cmd = [
        "/home/openclaw/FormAlert/.venv/bin/python3", "-u", "/home/openclaw/FormAlert/fetch_team.py", team_id,
        "--full", "--team-name", team_name, "--slug", team_slug, "--coach-nat", coach_nat, "--stadium", stadium,
    ]
    proc = subprocess.run(cmd, cwd="/home/openclaw/FormAlert", text=True, capture_output=True, timeout=900)
    if proc.returncode != 0:
        raise RuntimeError((proc.stdout + proc.stderr)[-4000:])
    data = _read_team_cache(team_id)
    if not data.get("players"):
        raise RuntimeError("fresh fetch returned empty players")
    return data


def prepare_team_data_version(team_id: str) -> dict:
    """Return cached data immediately, never call API.

    Jul 22 2026 — Senior Python Flask refactor: page renders from
    `_live_cache_{team_id}.json` only. No background refresh, no
    Flashscore API call, no Soccerway call. The page is purely
    cache-driven. API is invoked ONLY when the user explicitly clicks
    the "Update data" button (handled by /lineup_ai/api/fetch/{team_id}).

    Behaviour:
    - If SQLite `team_data_versions` has an `is_current=1` row → use it.
    - Else, fall back to the on-disk `_live_cache_{team_id}.json` file.
    - If neither exists → return `{}` (UI shows "No data"). The user
      must click "Update data" to populate.
    - On every call the cache is also persisted back to disk so the
      SQLite→file contract stays in sync (defensive write — costs ~5 ms).
    """
    # 1) Preferred: SQLite current version
    current = _get_current_team_version(team_id)
    if current and current.get("data"):
        # Defensive: write back to file (fast — no API, no network)
        try:
            _write_team_cache(team_id, current["data"])
        except Exception:
            pass
        return current["data"]

    # 2) Fallback: on-disk cache file
    try:
        cached = _read_team_cache(team_id)
        if cached:
            # Promote to SQLite so the next read is the fast path.
            # Idempotent: _save_team_version is md5-hash deduplicated.
            try:
                _save_team_version(team_id, cached)
            except Exception:
                pass
            return cached
    except Exception:
        pass

    # 3) Nothing on disk. Return empty — UI will render "No data" and
    #    the user can click "Update data" to trigger a real API fetch.
    return {}


def _lineup_save_payload(payload: dict) -> dict:
    """Normalize a full user-scoped page snapshot.

    The snapshot intentionally stores rendered/current page state (player visible stats,
    Last 3 cells, status and Squad/P-XI/S-XI flags) instead of references to live team data.
    """
    if not isinstance(payload, dict):
        return {"players": []}
    players = payload.get("players") if isinstance(payload.get("players"), list) else []
    clean_players = []
    for item in players:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        clean_players.append({
            "name": name,
            "number": str(item.get("number") or ""),
            "nationality_html": str(item.get("nationality_html") or ""),
            "status": str(item.get("status") or "Available"),
            "age": str(item.get("age") or ""),
            "mv": str(item.get("mv") or ""),
            "pos": str(item.get("pos") or ""),
            "role_html": str(item.get("role_html") or ""),
            "impact": str(item.get("impact") or ""),
            "squad": bool(item.get("squad")),
            "pxi": bool(item.get("pxi")),
            "sxi": bool(item.get("sxi")),
            "last3_html": item.get("last3_html") if isinstance(item.get("last3_html"), list) else [],
            "stats": item.get("stats") if isinstance(item.get("stats"), dict) else {},
            "row_html": str(item.get("row_html") or ""),
        })
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return {
        "version": 1,
        "team_id": str(payload.get("team_id") or ""),
        "team_name": str(payload.get("team_name") or ""),
        "meta": meta,
        "players": clean_players,
        "page_html": str(payload.get("page_html") or ""),
    }

async def lineup_get_hierarchy():
    return load_complete_hierarchy()

@app.get("/lineup_ai/data.json")
async def lineup_data_json():
    hierarchy = await lineup_get_hierarchy()
    return JSONResponse(content=hierarchy)

@app.get("/lineup_ai/select")
async def lineup_select_html():
    with open("/home/openclaw/FormAlert/lineup_select.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/lineup_ai/favorites")
async def favorites_page(request: Request):
    """My Favorites page - shows favorited players for logged-in user."""
    username = getattr(request.state, "username", "owner")
    with open("/home/openclaw/FormAlert/favorites.html", "r", encoding="utf-8") as f:
        html = f.read()
    # Inject username into HTML
    html = html.replace("</body>", f'<script>window.CURRENT_USER = "{username}";</script></body>')
    return HTMLResponse(content=html)


@app.get("/api/favorites")
async def get_favorites(request: Request):
    """Get user's favorite players with dynamic data from team cache."""
    username = getattr(request.state, "username", "owner")
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT player_id, team_id, player_data, created_at FROM user_favorites WHERE username = ? ORDER BY created_at",
            (username,)
        ).fetchall()
    
    favorites = []
    team_caches = {}  # Cache team data to avoid repeated loads
    
    for row in rows:
        player_id, team_id, player_data_json, created_at = row
        try:
            player_data = json.loads(player_data_json)
        except:
            player_data = {}
        
        # Try to get actual player data from team cache
        if team_id:
            # Load team cache if not already loaded
            if team_id not in team_caches:
                cache_path = os.path.join(DATA_DIR, f"_live_cache_{team_id}.json")
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        team_caches[team_id] = json.load(f)
                except:
                    team_caches[team_id] = None
            
            team_data = team_caches[team_id]
            if team_data and "players" in team_data:
                # Find player in team by player_id
                for p in team_data["players"]:
                    if p.get("player_id") == player_id or f"{p.get('number', '')}_{p.get('name', '')}" == player_id:
                        # Use actual data from team cache, preserving saved fields not in cache
                        actual_data = {
                            "player_id": player_id,
                            "number": p.get("number", player_data.get("number", "?")),
                            "name": p.get("name", player_data.get("name", "")),
                            "club": team_data.get("team", {}).get("name", player_data.get("club", "")),
                            "national": p.get("national", player_data.get("national", "")),
                            "age": p.get("age", player_data.get("age", "")),
                            "mv": p.get("mv", player_data.get("mv", "")),
                            "position": p.get("position", player_data.get("position", "")),
                            "squad_role": p.get("squad_role", player_data.get("squad_role", "")),
                            "impact": p.get("impact", player_data.get("impact", "")),
                            "apps": p.get("apps", player_data.get("apps", "")),
                            "minutes": p.get("minutes", player_data.get("minutes", "")),
                            "goals": p.get("goals", player_data.get("goals", "")),
                            "assists": p.get("assists", player_data.get("assists", "")),
                            "yellows": p.get("yellows", player_data.get("yellows", "")),
                            "reds": p.get("reds", player_data.get("reds", "")),
                        }
                        favorites.append(actual_data)
                        break
                else:
                    # Player not found in team, use saved data
                    favorites.append({"player_id": player_id, **player_data})
            else:
                # No team cache, use saved data
                favorites.append({"player_id": player_id, **player_data})
        else:
            # No team_id, use saved data
            favorites.append({"player_id": player_id, **player_data})
    
    # Clean surrogate characters that can't be encoded in UTF-8
    def clean_surrogates(obj):
        if isinstance(obj, str):
            return obj.encode('utf-8', errors='replace').decode('utf-8')
        elif isinstance(obj, dict):
            return {k: clean_surrogates(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_surrogates(item) for item in obj]
        else:
            return obj
    
    return clean_surrogates({"favorites": favorites})


@app.post("/api/favorites")
async def add_favorite(request: Request):
    """Add player to favorites."""
    username = getattr(request.state, "username", "owner")
    data = await request.json()
    player_id = data.get("player_id")
    team_id = data.get("team_id", "")
    player_data = data.get("player_data", {})
    
    # Clean player name - remove emojis and span tags
    if "name" in player_data:
        import re
        player_data["name"] = re.sub(r"<span[^>]*>[^<]*</span>", "", player_data.get("name", "")).strip()
        player_data["name"] = re.sub(r"[🎯🎨⭐👑⚽️👟]", "", player_data.get("name", "")).strip()
    
    if not player_id:
        return {"error": "player_id required"}, 400
    
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT OR REPLACE INTO user_favorites (username, player_id, team_id, player_data, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, player_id, team_id, json.dumps(player_data), datetime.now(timezone.utc).isoformat())
        )
    return {"success": True, "player_id": player_id}


@app.delete("/api/favorites/{player_id}")
async def remove_favorite(request: Request, player_id: str):
    """Remove player from favorites."""
    username = getattr(request.state, "username", "owner")
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "DELETE FROM user_favorites WHERE username = ? AND player_id = ?",
            (username, player_id)
        )
    return {"success": True}


# --- Match favorites (sidebar on compare page) ---
@app.get("/api/match-favorites")
async def get_match_favorites(request: Request):
    """Get user's saved favorite matches. Auto-prune entries older than 10 days."""
    username = getattr(request.state, "username", "owner")
    ensure_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM user_match_favorites WHERE username = ? AND created_at < ?", (username, cutoff))
        con.commit()
        rows = con.execute(
            "SELECT match_id, home_id, away_id, home_name, away_name, created_at FROM user_match_favorites WHERE username = ? ORDER BY created_at DESC",
            (username,)
        ).fetchall()
    favorites = [
        {
            "match_id": row[0],
            "home_id": row[1],
            "away_id": row[2],
            "home_name": row[3],
            "away_name": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]
    return {"favorites": favorites}


@app.post("/api/match-favorites")
async def add_match_favorite(request: Request):
    """Add a match to favorites."""
    username = getattr(request.state, "username", "owner")
    data = await request.json()
    match_id = data.get("match_id")
    home_id = data.get("home_id", "")
    away_id = data.get("away_id", "")
    home_name = data.get("home_name", "")
    away_name = data.get("away_name", "")
    if not match_id:
        return JSONResponse({"error": "match_id required"}, status_code=400)
    ensure_db()
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO user_match_favorites(username, match_id, home_id, away_id, home_name, away_name, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(username, match_id) DO UPDATE SET home_id=excluded.home_id, away_id=excluded.away_id, "
            "home_name=excluded.home_name, away_name=excluded.away_name, created_at=excluded.created_at",
            (username, match_id, home_id, away_id, home_name, away_name, datetime.now(timezone.utc).isoformat()),
        )
    return {"success": True, "match_id": match_id}


@app.delete("/api/match-favorites/{match_id}")
async def remove_match_favorite(request: Request, match_id: str):
    """Remove a match from favorites."""
    username = getattr(request.state, "username", "owner")
    ensure_db()
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "DELETE FROM user_match_favorites WHERE username = ? AND match_id = ?",
            (username, match_id),
        )
    return {"success": True}



@app.get("/lineup_ai")
async def lineup_index():
    return RedirectResponse(url="/lineup_ai/select", status_code=307)


_fetch_in_progress = set()

@app.get("/lineup_ai/api/fetch/{team_id}")
async def lineup_api_fetch(team_id: str):
    """Manual refresh — Flashscore API only.

    Triggered by the "Update data" button on the team page. The page
    itself never calls the API (cache-driven, see prepare_team_data_version).
    This endpoint is the single entry point that talks to Flashscore.

    Jul 22 2026 — replaced Soccerway fetch_team_live with
    api_refresh.refresh_team (Flashscore, force=True).

    Returns {"changed": true/false, "duration_seconds": ..., "error": ...}.
    """
    import sys, json, hashlib, time
    sys.path.insert(0, "/home/openclaw/FormAlert")
    from api_refresh import refresh_team

    # 1) Capture old-version hash BEFORE refresh so we can detect change.
    #    Read both the SQLite current version and the on-disk cache file;
    #    take the freshest one (highest last_updated / mtime).
    old_hash = ""
    try:
        old_ver = _get_current_team_version(team_id)
        if old_ver and old_ver.get("data"):
            old_subset = {
                k: old_ver["data"].get(k)
                for k in ("team", "coach", "stadium", "players", "matches", "fixtures")
            }
            old_hash = hashlib.md5(
                json.dumps(old_subset, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
        else:
            old_cache = _read_team_cache(team_id)
            if old_cache:
                old_subset = {
                    k: old_cache.get(k)
                    for k in ("team", "coach", "stadium", "players", "matches", "fixtures")
                }
                old_hash = hashlib.md5(
                    json.dumps(old_subset, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()
    except Exception:
        pass

    # 2) Race protection — only one refresh per team at a time.
    if team_id in _fetch_in_progress:
        return JSONResponse(content={
            "changed": False,
            "error": "Fetch already in progress",
            "duration_seconds": 0,
        })
    _fetch_in_progress.add(team_id)
    start_time = time.time()

    try:
        # 3) Sync refresh from Flashscore API (force=True bypasses is_fresh TTL).
        #    refresh_team writes _live_cache_{team_id}.json and returns True on success.
        ok = await asyncio.to_thread(refresh_team, team_id, True)
        if not ok:
            return JSONResponse(content={
                "changed": False,
                "duration_seconds": round(time.time() - start_time, 1),
                "error": "refresh_team returned False (no players, slug not found, or API error)",
            }, status_code=502)

        # 4) Promote fresh cache into SQLite (so prepare_team_data_version sees it).
        try:
            fresh_cache = _read_team_cache(team_id)
            if fresh_cache:
                _save_team_version(team_id, fresh_cache)
        except Exception as e:
            print(f"[fetch] failed to promote cache to SQLite for {team_id}: {e}")

        # 5) Compute new hash for change detection.
        new_hash = ""
        try:
            new_cache = _read_team_cache(team_id)
            if new_cache:
                new_subset = {
                    k: new_cache.get(k)
                    for k in ("team", "coach", "stadium", "players", "matches", "fixtures")
                }
                new_hash = hashlib.md5(
                    json.dumps(new_subset, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()
        except Exception:
            pass

        return JSONResponse(content={
            "changed": old_hash != new_hash,
            "duration_seconds": round(time.time() - start_time, 1),
            "error": None,
        })
    except Exception as e:
        print(f"[fetch] {team_id} error: {e}")
        return JSONResponse(content={
            "changed": False,
            "duration_seconds": round(time.time() - start_time, 1),
            "error": str(e),
        }, status_code=500)
    finally:
        _fetch_in_progress.discard(team_id)



# --- FIXTURES: fetch upcoming matches for a team ---

def _fixtures_cache_path(team_id: str) -> str:
    return os.path.join("/home/openclaw/.openclaw/workspace", f"_fixtures_{team_id}.json")

def _read_fixtures_cache(team_id: str):
    """Read fixtures cache with TTL and filter out past matches.
    Returns None if cache is stale OR if it doesn't have enough upcoming matches
    (so we trigger a fresh fetch from Soccerway).
    """
    path = _fixtures_cache_path(team_id)
    if not os.path.exists(path):
        return None

    # Check TTL (1 hour — fixtures change often, especially day-of-match)
    try:
        import time
        cache_age = time.time() - os.path.getmtime(path)
        if cache_age > 3600:  # 1 hour instead of 6
            return None
    except:
        pass

    try:
        with open(path, 'r') as f:
            data = json.load(f)
        fixtures = data.get('fixtures', [])

        # Filter out past matches
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day, 0, 0, 0)

        valid_fixtures = []
        for m in fixtures:
            date_str = m.get('date', '')
            # Parse date: "27.06 05:00" or "25.09"
            dm = re.match(r'(\d{1,2})\.(\d{2})(?:\s+(\d{2}):(\d{2}))?', date_str)
            if dm:
                day = int(dm.group(1))
                month = int(dm.group(2))

                # Determine year: assume current year first
                year = now.year

                # If month already passed this year, it's next year
                if month < now.month:
                    year = now.year + 1
                # If same month but day passed, it's this year (past match)
                # If same month and day >= today, it's this year

                if dm.group(3):
                    hour = int(dm.group(3))
                    minute = int(dm.group(4))
                else:
                    hour, minute = 12, 0

                try:
                    match_dt = datetime(year, month, day, hour, minute)
                    if match_dt >= today_start:
                        valid_fixtures.append(m)
                except ValueError:
                    pass

        # If all fixtures are past, return None to trigger refresh
        if not valid_fixtures:
            return None

        # If cache has fewer than 3 upcoming matches AND it's stale (>2h old),
        # force a refresh so we don't show incomplete fixture lists (e.g. missing today's match)
        if len(valid_fixtures) < 3 and cache_age > 7200:
            return None

        return valid_fixtures
    except:
        pass
    return None

def _write_fixtures_cache(team_id: str, fixtures: list):
    path = _fixtures_cache_path(team_id)
    try:
        with open(path, 'w') as f:
            json.dump({'cached_at': datetime.utcnow().isoformat(), 'fixtures': fixtures}, f)
    except:
        pass

@app.get("/lineup_ai/match/h2h/{match_id}")
async def lineup_match_h2h(match_id: str, my: str = "", opp: str = ""):
    """H2H + Last Matches for the Match-mode ‼️ popup.

    Jul 22 2026 — Senior Python Flask refactor.
    Called ONLY on click of the ‼️ button in /lineup_ai/compare/{team_id}.
    Three Flashscore endpoints (all lazy — no pre-fetch on page load):
        GET /matches/h2h?match_id={id}
        GET /teams/results?team_id={my_id}&page=1
        GET /teams/results?team_id={opp_id}&page=1
    Plus /teams/details for stadium info.

    Query params:
        my:  my team_id
        opp: opponent team_id

    Returns: JSON {stadium: {...}, h2h: [...], last_my: [...], last_opp: [...], error: ...}
    """
    if not match_id:
        return {"stadium": {}, "h2h": [], "last_my": [], "last_opp": [], "error": "missing match_id"}
    # Slug lookup: best-effort from leagues_data.json
    my_slug = ""
    opp_slug = ""
    LEAGUES_FILE = "/home/openclaw/FormAlert/leagues_data.json"
    try:
        ld = json.load(open(LEAGUES_FILE))
        for country, champs in ld.items():
            for champ, teams in champs.items():
                for t in teams:
                    if t.get("id") == my:
                        my_slug = t.get("slug", "")
                    elif t.get("id") == opp:
                        opp_slug = t.get("slug", "")
    except Exception:
        pass

    # === 24-hour file cache (Jul 22 2026) ===
    # H2H data is historical (matches that already happened), so it
    # doesn't change frequently. We cache the full payload for 24h
    # to avoid burning FlashScore API quota (240 req/min cap) on
    # repeated clicks of the ‼️ button.
    import os, time
    CACHE_DIR = "/home/openclaw/.openclaw/workspace"
    CACHE_TTL = 86400  # 24 hours in seconds
    cache_key = "_h2h_cache_{m}_{my}_{opp}.json".format(
        m=match_id, my=my or "_", opp=opp or "_"
    )
    cache_path = os.path.join(CACHE_DIR, cache_key)
    # 1. Try cache
    if os.path.exists(cache_path):
        try:
            age = time.time() - os.path.getmtime(cache_path)
            if age < CACHE_TTL:
                cached = json.load(open(cache_path))
                cached["_cache_age_seconds"] = int(age)
                cached["_cache_hit"] = True
                return cached
        except Exception:
            pass  # corrupt cache → fall through to fetch

    # 2. Fetch from FlashScore
    import api_refresh as _ar
    try:
        payload = _ar.fetch_match_h2h_payload(
            match_id=match_id,
            my_team_id=my or "",
            opp_team_id=opp or "",
            my_slug=my_slug or "",
            opp_slug=opp_slug or "",
        )
    except Exception as e:
        payload = {"stadium": {}, "h2h": [], "last_my": [], "last_opp": [], "error": str(e)}
    # 3. Save to cache (only if no error from the API)
    if not payload.get("error"):
        try:
            payload["_cached_at"] = int(time.time())
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception:
            pass
    payload["_cache_hit"] = False
    return payload


@app.get("/lineup_ai/api/fixtures/{team_id}")
async def lineup_api_fixtures(team_id: str):
    """Fetch upcoming fixtures from Soccerway and return as JSON.

    Returns:
        - 1 match happening today (if any)
        - 2 upcoming matches after today
        - Total: max 3 matches
        - Excludes all past/completed matches
        - Order: Home vs Away exactly as on Soccerway
    """
    import asyncio, re, json
    from bs4 import BeautifulSoup
    from playwright.async_api import async_playwright
    from datetime import datetime, timedelta

    # PRIMARY: read fixtures[] directly from main team cache (populated by phase2_generic.py via Flashscore API).
    # This is the fast path — 0 API calls, instant response.
    try:
        team_cache = _read_team_cache(team_id)
        if team_cache and team_cache.get("fixtures"):
            now = datetime.utcnow()
            today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
            converted = []
            for m in team_cache["fixtures"]:
                # Convert "dd/mm" + "HH:MM" to "dd.mm HH:MM" for the existing client format
                date_ddmm = m.get("date", "")
                time_str = m.get("time", "")
                dm = re.match(r"(\d{1,2})/(\d{2})", date_ddmm)
                if not dm:
                    continue
                day, month = int(dm.group(1)), int(dm.group(2))
                year = now.year if month >= now.month else now.year + 1
                try:
                    match_dt = datetime(year, month, day, 12, 0)
                except ValueError:
                    continue
                if match_dt < today_start:
                    continue  # past, skip
                home = m.get("home_team", {})
                away = m.get("away_team", {})
                home_name = home.get("name", "") if isinstance(home, dict) else str(home or "")
                away_name = away.get("name", "") if isinstance(away, dict) else str(away or "")
                home_id = home.get("id", "") if isinstance(home, dict) else ""
                away_id = away.get("id", "") if isinstance(away, dict) else ""
                date_combined = f"{day:02d}.{month:02d}" + (f" {time_str}" if time_str else "")
                converted.append({
                    "mid": m.get("match_id", ""),
                    "date": date_combined,
                    "home": home_name,
                    "away": away_name,
                    "home_id": home_id,
                    "away_id": away_id,
                    "is_home": str(home_id) == str(team_id) if home_id else team_id.lower() in home_name.lower(),
                    "url": "",
                    "tournament_name_short": m.get("tournament_name_short", ""),
                    "tournament_name_full": m.get("tournament_name_full", ""),
                })
            if converted:
                return JSONResponse(content={"fixtures": converted, "team_id": team_id, "from_team_cache": True, "source": "flashscore_api"})
    except Exception:
        pass

    # SECONDARY: legacy fixtures cache file
    cached = _read_fixtures_cache(team_id)
    if cached:
        return JSONResponse(content={"fixtures": cached, "team_id": team_id, "cached": True})

    # Fallback: get fixtures from team cache (instant)
    try:
        team_cache = _read_team_cache(team_id)
        if team_cache and team_cache.get("matches"):
            fixtures = []
            now = datetime.utcnow()
            today_start = datetime(now.year, now.month, now.day, 0, 0, 0)

            for m in team_cache.get("matches", []):
                date_str = m.get("date", "")
                # Parse date: "27.06" or "15.05"
                dm = re.match(r"(\d{1,2})\.(\d{2})", date_str)
                is_future = False
                if dm:
                    day = int(dm.group(1))
                    month = int(dm.group(2))
                    year = now.year
                    # If month already passed this year, it's a past match (not next year fixture).
                    # Soccerway team cache only contains PLAYED matches (Last 3), not fixtures.
                    # The only exception: if day is end-of-year and we're in early January
                    # (off-by-one), but we can ignore that edge case for simplicity.
                    is_past = (month < now.month) or (month == now.month and day < now.day)
                    if is_past:
                        # Skip — this is a played match
                        continue
                    # Same year, same/next month, day >= today: future
                    try:
                        match_dt = datetime(year, month, day, 12, 0)
                        if match_dt >= today_start:
                            is_future = True
                    except ValueError:
                        pass

                if is_future:
                    fixtures.append({
                        "mid": m.get("mid", ""),
                        "date": m.get("date", ""),
                        "home": m.get("home_team", ""),
                        "away": m.get("away_team", ""),
                        "home_id": "",
                        "away_id": "",
                        "is_home": team_id.lower() in m.get("home_team", "").lower(),
                        "url": m.get("url", "")
                    })

            if fixtures:
                return JSONResponse(content={"fixtures": fixtures[:5], "team_id": team_id, "from_team_cache": True})
    except:
        pass

    BASE = "https://www.soccerway.com"
    
    # Look up team slug from leagues_data.json
    slug = team_id.lower()
    try:
        with open("/home/openclaw/FormAlert/leagues_data.json", "r") as fh:
            ld = json.load(fh)
        for country, leagues in ld.items():
            for _league_name, teams in leagues.items():
                for t in teams:
                    if t["id"] == team_id:
                        slug = t.get("slug", slug)
                        break
    except Exception:
        pass

    async def _fetch():
        url = f"{BASE}/team/{slug}/{team_id}/fixtures/"
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-setuid-sandbox",
                      "--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"]
            )
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
                viewport={"width":1920,"height":1080}, locale="en-US"
            )
            await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = await ctx.new_page()
            await page.goto(url, wait_until="networkidle", timeout=25000)
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 800)")
                await page.wait_for_timeout(300)
            html = await page.content()
            await browser.close()
        return html

    try:
        html = await _fetch()
    except Exception as e:
        return JSONResponse(content={"error": str(e), "fixtures": []}, status_code=500)

    soup = BeautifulSoup(html, "html.parser")
    all_matches = []
    seen_mids = set()

    # Current time (UTC)
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    today_end = datetime(now.year, now.month, now.day, 23, 59, 59)

    # Parse match links from fixtures page
    for a in soup.select('a[href*="/match/"]'):
        href = a.get("href", "")
        mid_m = re.search(r"[?&]mid=([A-Za-z0-9]+)", href)
        mid = mid_m.group(1) if mid_m else ""
        if not mid or mid in seen_mids:
            continue
        seen_mids.add(mid)

        parent = a.find_parent("tr") or a.find_parent("div")
        row_text = parent.get_text(" ", strip=True) if parent else a.get_text(strip=True)

        # Extract date and time
        date_str = ""
        match_datetime = None
        
        # Try full datetime first: "23.07. 01:30"
        dm = re.search(r"(\d{1,2})\.(\d{2})\.\s+(\d{2}):(\d{2})", row_text)
        if dm:
            day = int(dm.group(1))
            month = int(dm.group(2))
            hour = int(dm.group(3))
            minute = int(dm.group(4))
            date_str = f"{dm.group(1).zfill(2)}.{dm.group(2)} {dm.group(3)}:{dm.group(4)}"
            
            # Determine year: if month < current month, it is next year
            year = now.year
            if month < now.month:
                year = now.year + 1
            elif month == now.month and day < now.day:
                year = now.year + 1
            
            try:
                match_datetime = datetime(year, month, day, hour, minute)
            except ValueError:
                continue
        else:
            # Try date only without time: "23.07."
            dm = re.search(r"(\d{1,2})\.(\d{2})\.", row_text)
            if dm:
                day = int(dm.group(1))
                month = int(dm.group(2))
                date_str = f"{dm.group(1).zfill(2)}.{dm.group(2)}"
                
                year = now.year
                if month < now.month:
                    year = now.year + 1
                elif month == now.month and day < now.day:
                    year = now.year + 1
                
                try:
                    match_datetime = datetime(year, month, day, 12, 0)  # noon placeholder
                except ValueError:
                    continue
            else:
                continue  # skip matches without date

        if not match_datetime:
            continue

        # Skip past matches (before today)
        if match_datetime < today_start:
            continue

        # Extract team names from URL - preserve exact Soccerway order
        teams_m = re.search(r"/match/([^/]+)/([^/]+)/", href)
        home_name = ""
        away_name = ""
        is_home = True
        if teams_m:
            home_slug = teams_m.group(1)
            away_slug = teams_m.group(2)
            home_name = home_slug.rsplit("-", 1)[0].replace("-", " ").title()
            away_name = away_slug.rsplit("-", 1)[0].replace("-", " ").title()
            is_home = team_id in home_slug

        full_url = href if href.startswith("http") else f"{BASE}{href}"
        
        # Extract team IDs from URL slug
        home_id = ""
        away_id = ""
        if teams_m:
            home_id = home_slug.rsplit("-", 1)[-1] if "-" in home_slug else ""
            away_id = away_slug.rsplit("-", 1)[-1] if "-" in away_slug else ""

        all_matches.append({
            "mid": mid,
            "date": date_str,
            "match_datetime": match_datetime,
            "home": home_name,
            "away": away_name,
            "home_id": home_id,
            "away_id": away_id,
            "is_home": is_home,
            "url": full_url
        })

    # Sort by datetime ascending
    all_matches.sort(key=lambda x: x["match_datetime"])

    # Separate matches into today and future
    today_matches = [m for m in all_matches if today_start <= m["match_datetime"] <= today_end]
    future_matches = [m for m in all_matches if m["match_datetime"] > today_end]

    # Take: 1 today (if any) + 2 future
    result = []
    if today_matches:
        result.append(today_matches[0])
    result.extend(future_matches[:2])

    # Remove internal match_datetime field before returning
    for m in result:
        del m["match_datetime"]

    # Cache the result
    _write_fixtures_cache(team_id, result)

    return JSONResponse(content={"fixtures": result, "team_id": team_id})


@app.get("/lineup_ai/api/fixture-congestion/{team_id}")
async def lineup_api_fixture_congestion(team_id: str):
    """Return Fixture Overview (FO, formerly Fixture Congestion) score for a team.

    FO measures calendar density over the next 5 upcoming matches
    using hours-based recovery time. Higher score = denser schedule.

    Jul 29 2026 v3: ALWAYS recompute from cache fixtures on the fly.
    The cached FC may be stale (older v1/v2 schema) or out of sync
    with the latest compute_fixture_congestion algorithm. We use
    the cached fixtures[] as source of truth and recompute FC every
    request. This is fast (no API calls) and guarantees consistent
    output regardless of when cache was last refreshed.
    """
    import json, os
    from fixture_congestion import compute_fixture_congestion, progress_bar, risk_label

    cache_path = "/home/openclaw/.openclaw/workspace/_live_cache_" + team_id + ".json"
    fixtures = []
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cache = json.load(f)
            fixtures = cache.get("fixtures", []) or []
        except Exception:
            pass

    # ALWAYS recompute from fixtures (ignore cached FO value).
    # Pass team_id so compute can count home/away matches.
    fc_data = None
    if fixtures:
        try:
            fc_data = compute_fixture_congestion(fixtures, team_id=team_id)
        except Exception as e:
            fc_data = None

    if fc_data is None:
        return JSONResponse(content={
            "team_id": team_id,
            "fixture_congestion": 0,
            "status": "LOW",
            "average_recovery_days": 0.0,
            "minimum_recovery_days": 0,
            "minimum_recovery_hours": 0,
            "next_matches_count": len(fixtures),
            "recovery_intervals": [],
            "recovery_hours": [],
            "home_matches": 0,
            "away_matches": 0,
            "total_matches": len(fixtures),
            "travel_penalty": 0,
            "travel_transitions": [],
            # Jul 30 2026: Next 14 Days density fields (new in v9).
            "next_14_days_matches": 0,
            "next_14_days_period": 14,
            "next_14_days_density_status": "NORMAL",
            "next_14_days_penalty": 0,
            "rotation_risk": "Low",
            "progress_bar": progress_bar(0),
            "risk_label": risk_label(0),
        }, status_code=200)

    fc = int(fc_data.get("fixture_congestion", 0))
    out = dict(fc_data)
    out["team_id"] = team_id
    out["progress_bar"] = progress_bar(fc)
    out["risk_label"] = risk_label(fc)
    return JSONResponse(content=out)


# --- COMPARE: side-by-side team comparison for a match ---
# --- COMPARE: side-by-side match comparison with full team views ---
def _resolve_country_from_suffix(name):
    """Convert 'Team (Ita)' → 'Italy', or None if no suffix."""
    code = None
    import re as _re
    m = _re.search(r'\(([A-Za-z]{2,4})\)\s*$', (name or "").strip())
    if m:
        code = m.group(1).lower()
    if not code:
        return None
    return COUNTRY_ALIASES.get(code, code)


COUNTRY_ALIASES = {
    "arg": "Argentina",
    "aus": "Australia",
    "aut": "Austria",
    "bel": "Belgium",
    "bol": "Bolivia",
    "bra": "Brazil",
    "bul": "Bulgaria",
    "can": "Canada",
    "chi": "Chile",
    "chn": "China",
    "col": "Colombia",
    "crc": "Costa Rica",
    "cro": "Croatia",
    "cze": "Czech Republic",
    "den": "Denmark",
    "ecu": "Ecuador",
    "egy": "Egypt",
    "eng": "England",
    "esp": "Spain",
    "fin": "Finland",
    "fra": "France",
    "ger": "Germany",
    "gre": "Greece",
    "hun": "Hungary",
    "ind": "India",
    "irl": "Ireland",
    "irn": "Iran",
    "isr": "Israel",
    "ita": "Italy",
    "jpn": "Japan",
    "kor": "Korea",
    "mex": "Mexico",
    "mor": "Morocco",
    "ned": "Netherlands",
    "nor": "Norway",
    "par": "Paraguay",
    "per": "Peru",
    "pol": "Poland",
    "por": "Portugal",
    "rou": "Romania",
    "rus": "Russia",
    "sau": "Saudi Arabia",
    "sco": "Scotland",
    "ser": "Serbia",
    "slo": "Slovakia",
    "sui": "Switzerland",
    "swe": "Sweden",
    "tur": "Turkey",
    "uae": "UAE",
    "ukr": "Ukraine",
    "uru": "Uruguay",
    "usa": "USA",
    "ven": "Venezuela",
    "wal": "Wales"
}

@app.get("/lineup_ai/compare/{team_id}")
async def lineup_compare(team_id: str, mid: str = "", home_id: str = "", away_id: str = "", home_name: str = "", away_name: str = ""):
    """Render two full team views side-by-side for an upcoming match.
    All match data (home_id, away_id, names) is passed from the select page
    which already has it from the fixtures API — no Playwright needed here."""
    import os, json

    if not mid:
        return HTMLResponse(content="<h2>Missing match ID (mid parameter)</h2>", status_code=400)

    cache_dir = "/home/openclaw/.openclaw/workspace"

    # Use passed names, fall back to team_id
    if not home_name:
        home_name = home_id or team_id
    if not away_name:
        away_name = away_id or "Opponent"

    # First try to find team_ids by name from leagues_data.json
    # Then fall back to passed IDs or team_id
    home_team_id = home_id if home_id else ""
    away_team_id = away_id if away_id else ""

    # Jul 31 2026: validate that passed home_id/away_id actually match
    # the corresponding *_name. If user copies URL with mismatched
    # ID+name (e.g. home_id=Almeria but home_name=Al Nassr), the
    # resolved IDs would conflict and both teams would show the
    # same squad. Fix: if name→id lookup disagrees with passed id,
    # prefer the name lookup.
    def _validate_team_id_against_name(passed_id, name):
        """If passed_id exists but does NOT match the name in leagues_data,
        return the correct id for the name. If they match, return passed_id.
        If no passed_id, returns ''."""
        if not name or not passed_id:
            return passed_id
        try:
            with open("/home/openclaw/FormAlert/leagues_data.json", "r", encoding="utf-8") as f:
                _leagues = json.load(f)
        except Exception:
            return passed_id
        # Find the team with this id; check if its name matches
        for _country, _ldict in _leagues.items():
            for _lname, _teams in _ldict.items():
                for _team in _teams:
                    if _team.get("id", "") == passed_id:
                        team_name = _team.get("name", "")
                        # Compare: strip (Country) suffix from both sides
                        tn_clean = team_name.split(" (")[0].strip().lower()
                        hn_clean = name.split(" (")[0].strip().lower()
                        if tn_clean == hn_clean:
                            return passed_id  # match — keep
                        # Mismatch — find correct id by name
                        for _country2, _ldict2 in _leagues.items():
                            for _lname2, _teams2 in _ldict2.items():
                                for _team2 in _teams2:
                                    t2n = _team2.get("name", "")
                                    t2n_clean = t2n.split(" (")[0].strip().lower()
                                    if t2n_clean == hn_clean or t2n.lower() == name.lower():
                                        return _team2.get("id", "")
                        return passed_id  # name not found — keep original
        return passed_id  # id not in leagues — keep original

    home_team_id = _validate_team_id_against_name(home_team_id, home_name)
    away_team_id = _validate_team_id_against_name(away_team_id, away_name)

    # If home_id is empty but home_name is provided, try to find team_id from leagues_data.json
    if not home_team_id and home_name:
        try:
            with open("/home/openclaw/FormAlert/leagues_data.json", "r", encoding="utf-8") as f:
                leagues = json.load(f)
            # 1. Try exact match (case-insensitive)
            for country, leagues_dict in leagues.items():
                for league_name, teams in leagues_dict.items():
                    for team in teams:
                        if team.get("name", "").lower() == home_name.lower():
                            home_team_id = team.get("id", "")
                            break
                    if home_team_id:
                        break
                if home_team_id:
                    break
            # 2. Try substring match (only if lengths are close: avoid 'Inter'
            # matching 'Inter Turku' when the user asked for 'Inter (Ita)')
            if not home_team_id:
                target_country = _resolve_country_from_suffix(home_name)
                candidate = None
                fallback = None
                for country, leagues_dict in leagues.items():
                    for league_name, teams in leagues_dict.items():
                        for team in teams:
                            tn = team.get("name", "").lower()
                            hn = home_name.lower()
                            tn_clean = tn.split(" (")[0].strip()
                            hn_clean = hn.split(" (")[0].strip()
                            if tn_clean == hn_clean:
                                # Exact match after stripping country — prefer
                                # this even if country suffix is absent
                                if target_country:
                                    if country.lower() == target_country.lower():
                                        home_team_id = team.get("id", "")
                                        break
                                    if fallback is None:
                                        fallback = team.get("id", "")
                                else:
                                    if candidate is None:
                                        candidate = team.get("id", "")
                            elif tn_clean.startswith(hn_clean + " ") or hn_clean.startswith(tn_clean + " "):
                                # Substring match: 'Inter Turku' starts with 'inter '
                                # Only accept as fallback if no exact match exists
                                if fallback is None:
                                    fallback = team.get("id", "")
                        if home_team_id:
                            break
                    if home_team_id:
                        break
                if not home_team_id:
                    home_team_id = candidate or fallback or home_team_id
        except Exception:
            pass

    # If still no home_team_id, use team_id as fallback
    if not home_team_id:
        home_team_id = team_id

    # If away_id is empty but away_name is provided, try to find team_id from leagues_data.json
    if not away_team_id and away_name:
        try:
            with open("/home/openclaw/FormAlert/leagues_data.json", "r", encoding="utf-8") as f:
                leagues = json.load(f)
            # 1. Try exact match (case-insensitive)
            for country, leagues_dict in leagues.items():
                for league_name, teams in leagues_dict.items():
                    for team in teams:
                        if team.get("name", "").lower() == away_name.lower():
                            away_team_id = team.get("id", "")
                            break
                    if away_team_id:
                        break
                if away_team_id:
                    break
            # 2. Try substring match (only if lengths are close)
            if not away_team_id:
                target_country = _resolve_country_from_suffix(away_name)
                candidate = None
                fallback = None
                for country, leagues_dict in leagues.items():
                    for league_name, teams in leagues_dict.items():
                        for team in teams:
                            tn = team.get("name", "").lower()
                            an = away_name.lower()
                            tn_clean = tn.split(" (")[0].strip()
                            an_clean = an.split(" (")[0].strip()
                            if tn_clean == an_clean:
                                if target_country:
                                    if country.lower() == target_country.lower():
                                        away_team_id = team.get("id", "")
                                        break
                                    if fallback is None:
                                        fallback = team.get("id", "")
                                else:
                                    if candidate is None:
                                        candidate = team.get("id", "")
                            elif tn_clean.startswith(an_clean + " ") or an_clean.startswith(tn_clean + " "):
                                if fallback is None:
                                    fallback = team.get("id", "")
                        if away_team_id:
                            break
                    if away_team_id:
                        break
                if not away_team_id:
                    away_team_id = candidate or fallback or away_team_id
        except Exception:
            pass

    # If still no away_id, return error
    if not away_team_id:
        error_msg = '<h2>Missing away_id for match comparison</h2><p>Please provide both home_id and away_id parameters. Could not resolve away team from away_name="' + away_name + '" (also not found in leagues_data.json).</p>'
        return HTMLResponse(content=error_msg, status_code=400)

    # --- Stadium: try to get actual match venue from Soccerway match page ---
    home_stadium = ""
    away_stadium = ""
    home_cache_path = os.path.join(cache_dir, f"_live_cache_{home_team_id}.json")
    away_cache_path = os.path.join(cache_dir, f"_live_cache_{away_team_id}.json")
    if os.path.exists(home_cache_path):
        with open(home_cache_path) as fh:
            home_data = json.load(fh)
        home_stadium = (home_data.get("stadium") or "").strip()
    if os.path.exists(away_cache_path):
        with open(away_cache_path) as fh:
            away_data = json.load(fh)
        away_stadium = (away_data.get("stadium") or "").strip()

    # Try to fetch actual match venue AND correct team order from Soccerway match page
    import httpx as _httpx
    import re as _re
    import html as _html
    match_venue = ""
    try:
        match_url = f"https://www.soccerway.com/match/{home_name.lower().replace(' ', '-')}-{home_team_id}/{away_name.lower().replace(' ', '-')}-{away_team_id}/?mid={mid}"
        resp = _httpx.get(match_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, follow_redirects=True)
        page_text = resp.text

        # 1. Parse correct team order from <title>: "PSG v Aston Villa live scores & match info | Soccerway"
        title_m = _re.search(r'<title>(.+?) live scores', page_text)
        if title_m:
            title_clean = _html.unescape(title_m.group(1)).strip()
            # Split by " v " or " vs " — left is real home, right is real away
            parts = _re.split(r'\s+v(?:s)?\s+', title_clean, flags=_re.IGNORECASE)
            if len(parts) == 2:
                real_home_name = parts[0].strip()
                real_away_name = parts[1].strip()
                # Match to team IDs by checking which name is closer
                # If real home matches away_name (from URL), swap
                if real_home_name.lower() in away_name.lower() or away_name.lower() in real_home_name.lower():
                    # Swap: away team is actually home
                    home_team_id, away_team_id = away_team_id, home_team_id
                    home_name, away_name = away_name, home_name
                    home_stadium, away_stadium = away_stadium, home_stadium
                elif real_home_name.lower() not in home_name.lower() and home_name.lower() not in real_home_name.lower():
                    # Names don't match at all, use title names directly
                    home_name = real_home_name
                    away_name = real_away_name

        # 2. Parse neutral venue from JSON: {"DM":"Neutral location - Red Bull Arena."}
        dm_match = _re.search(r'"DM":"([^"]*Neutral location[^"]*)"', page_text)
        if dm_match:
            dm_text = dm_match.group(1)
            venue_m = _re.search(r'Neutral location\s*-?\s*(.+)', dm_text, _re.IGNORECASE)
            if venue_m:
                match_venue = venue_m.group(1).strip().rstrip(".")
    except Exception:
        pass

    stadium_text = ""
    stadium_class = ""
    neutral_suffix = ""
    if match_venue:
        # Match is at a neutral venue
        stadium_text = match_venue
        stadium_class = "neutral"
        neutral_suffix = " \u2014 Neutral Stadium"
    else:
        # Normal: match at home team's stadium
        stadium_text = home_stadium or ""

    # --- Jul 23 2026: extract match metadata (date, league, round, stadium)
    # from the team's fixtures cache so the H2H popup can show a centered
    # header block: "26.07.2026 19:00 / Slovenia Prva liga - Round 2 / 🏟 ...".
    # We look in the home team's cache first, then the away team's cache.
    match_date = ""
    match_league = ""
    match_round = ""
    match_stadium = ""
    # Jul 24 2026: the home team's cache (loaded from /teams/results) does
    # NOT carry the match-specific venue — the API exposes that only via
    # /matches/details. We try to fetch it here so the H2H popup header
    # shows "Thermoplan Arena (Luzern) - 16 800" for THIS specific match,
    # not the home team's home stadium "Swissporarena". Failure is fine —
    # we fall back to home_stadium below.
    match_venue_data = {}
    try:
        import api_refresh as _ar
        match_venue_data = _ar.fetch_match_venue(mid) or {}
    except Exception:
        pass

    try:
        for lookup_id in (home_team_id, away_team_id):
            if not lookup_id:
                continue
            cache_path = os.path.join(cache_dir, f"_live_cache_{lookup_id}.json")
            if not os.path.exists(cache_path):
                continue
            with open(cache_path) as fh:
                tc = json.load(fh)
            for fx in (tc.get("fixtures") or []):
                if str(fx.get("match_id", "")) == str(mid):
                    # date: stored as "dd/mm" — convert to "dd.mm.YYYY HH:MM"
                    date_raw = fx.get("date", "")
                    time_str = fx.get("time", "")
                    dm = re.match(r"(\d{1,2})/(\d{2})", date_raw)
                    if dm:
                        day, month = int(dm.group(1)), int(dm.group(2))
                        # Pick a sensible year: same year, or next year if month < now
                        now_y = datetime.utcnow().year
                        now_m = datetime.utcnow().month
                        year = now_y if month >= now_m else now_y + 1
                        match_date = f"{day:02d}.{month:02d}.{year}"
                        if time_str:
                            match_date += f" {time_str}"
                    # league = full tournament name; round = stage.
                    # Jul 24 2026: per user spec, the championship line in the
                    # H2H popup header is rendered as UPPERCASE with a period
                    # after the country name, e.g. "RUSSIA. PREMIER LEAGUE"
                    # (not "RUSSIA: Premier League"). The uppercase is applied
                    # by the JS renderer via .toUpperCase() (so we keep the
                    # original case in the source data for any other consumer
                    # that wants title case). The colon-to-period swap is done
                    # here so all callers (including any future
                    # non-JS-rendered views) see the same form.
                    _raw_league = (fx.get("tournament_name_full") or
                                   fx.get("tournament_name_short") or
                                   fx.get("tournament") or "").strip()
                    # First occurrence of ":" after a country-shaped prefix
                    # (1-20 caps) becomes a period. e.g.
                    #   "RUSSIA: Premier League"        -> "RUSSIA. Premier League"
                    #   "SWITZERLAND: Super League"      -> "SWITZERLAND. Super League"
                    #   "NORTH MACEDONIA: First League"  -> "NORTH MACEDONIA. First League"
                    # We also allow spaces in the country prefix for compound
                    # country names. The captured group is reused as-is.
                    _league_norm = _re.sub(
                        r'^([A-Z][A-Z\s]{1,30}):\s*',
                        lambda m: m.group(1) + '. ',
                        _raw_league,
                    )
                    match_league = _league_norm
                    # round: if API exposes round_name, use it; else "Round N"
                    rd = (fx.get("round_name") or "").strip()
                    if not rd:
                        rn = fx.get("round")
                        if rn:
                            rd = f"Round {rn}"
                    match_round = rd
                    # stadium: prefer the explicit venue from
                    # /matches/details (match-specific, e.g. Thermoplan
                    # Arena for this Luzern-Thun match even though
                    # Luzern's home is Swissporarena). Fall back to
                    # the fixture's venue, then the home team's stadium.
                    if match_venue_data and match_venue_data.get("name"):
                        venue_raw = (match_venue_data.get("name") or "").strip()
                        city_raw = (match_venue_data.get("city") or "").strip()
                        cap_raw = match_venue_data.get("capacity")
                    else:
                        venue_raw = (fx.get("venue") or fx.get("stadium") or "").strip()
                        city_raw = (fx.get("city") or "").strip()
                        cap_raw = fx.get("capacity")
                    if venue_raw:
                        if city_raw and city_raw.lower() not in venue_raw.lower():
                            venue_line = f"{venue_raw} ({city_raw})"
                        else:
                            venue_line = venue_raw
                        if cap_raw:
                            try:
                                cap_clean = str(cap_raw).replace(" ", "").replace("\u00a0", "")
                                cap_n = int(cap_clean)
                                # Jul 24 2026: per user spec, the stadium capacity
                                # uses a comma with NO space (30,457) — not "30 457"
                                # as in the previous v4. The form is rendered as
                                # "VEB Arena (Moscow) · 30,457" with a middle-dot
                                # separator between the venue and the capacity.
                                cap_fmt = f"{cap_n:,}"
                                venue_line += f" \u00b7 {cap_fmt}"
                            except Exception:
                                pass
                        match_stadium = venue_line
                    elif home_stadium:
                        # Fallback: home team's stadium (already loaded by
                        # lineup_compare from /teams/details cache).
                        match_stadium = home_stadium
                    break
            if match_date or match_league:
                break
    except Exception:
        pass

    # --- Info box (Jul 30 2026) ---
    # Detect:
    #   1. Stadium mismatch: match_stadium != home_stadium (e.g. team
    #      plays a European match at a different venue).
    #   2. First-leg result: the most recent FINISHED match between
    #      the same two teams in the same tournament (e.g. Europa
    #      League Qualification two-leg ties).
    info_box_lines = []

    # 1) InfoBox content from Flashscore match HTML page.
    # Jul 30 2026 v3 (user spec): infoBox text comes from
    # the DM field of the match HTML page. If DM is empty or
    # absent, info_box_text stays empty — we DO NOT invent
    # a fallback. The user explicitly said: "не нужно
    # придумывать от себя, бери только данные по API!"
    info_box_text = ''
    try:
        info_box_text = _scrape_flashscore_infobox(mid) or ''
    except Exception:
        info_box_text = ''


    # --- Render template ---
    with open("/home/openclaw/FormAlert/compare_template.html", "r", encoding="utf-8") as f:
        template = f.read()

    # Selected team goes where it is in the fixture: home=LEFT, away=RIGHT
    result = template.replace("{{my_team_id}}", home_team_id)
    result = result.replace("{{opp_team_id}}", away_team_id or "")
    result = result.replace("{{my_name}}", home_name)
    result = result.replace("{{opponent_name}}", away_name)
    result = result.replace("{{mid}}", mid)
    result = result.replace("{{match_id}}", mid)
    result = result.replace("{{stadium_text}}", stadium_text)
    result = result.replace("{{stadium_class}}", stadium_class)
    result = result.replace("{{neutral_suffix}}", neutral_suffix)
    # Jul 23 2026: inject match metadata for H2H popup header.
    # Use a small HTML escaper to prevent template injection (team names
    # can contain quotes / angle brackets if entered by hand).
    import html as _html
    def _safe(s):
        return _html.escape(str(s or ""), quote=True)
    result = result.replace("{{match_date}}", _safe(match_date))
    result = result.replace("{{match_league}}", _safe(match_league))
    result = result.replace("{{match_round}}", _safe(match_round))
    result = result.replace("{{match_stadium}}", _safe(match_stadium))
    result = result.replace("{{info_box}}", _safe(info_box_text))

    return HTMLResponse(content=result)




# Match save endpoints - save data for both teams in a match
@app.get("/lineup_ai/match_save/{mid}")
async def match_get_save(mid: str, request: Request):
    """Get saved match data for both teams. Uses mid only (no username)."""
    ensure_db()
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT save_data, saved_at FROM user_match_saves WHERE mid=?",
        (mid,),
    ).fetchone()
    con.close()
    if not row:
        return JSONResponse(content={"ok": True, "home_data": None, "away_data": None, "saved_at": None})
    try:
        data = json.loads(row[0])
    except Exception:
        data = {"home_data": None, "away_data": None}
    return JSONResponse(content={"ok": True, "home_data": data.get("home_data"), "away_data": data.get("away_data"), "saved_at": row[1]})


@app.post("/lineup_ai/match_save/{mid}")
async def match_save_post(mid: str, request: Request, payload: dict = Body(default_factory=dict)):
    """Save match data for both teams. Uses mid only (no username)."""
    ensure_db()
    saved_at = datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO user_match_saves(username, mid, save_data, saved_at) VALUES(?,?,?,?) "
        "ON CONFLICT(mid) DO UPDATE SET save_data=excluded.save_data, saved_at=excluded.saved_at",
        ("match", mid, json.dumps(payload, ensure_ascii=False), saved_at),
    )
    con.commit()
    con.close()
    return JSONResponse(content={"ok": True, "saved_at": saved_at})


# Legacy redirect: /team/{team_id}/compare?mid=... -> /lineup_ai/compare/{team_id}?mid=...
@app.get("/team/{team_id}/compare")
async def team_compare_redirect(team_id: str, mid: str = ""):
    return RedirectResponse(url=f"/lineup_ai/compare/{team_id}?mid={mid}")

@app.get("/lineup_ai/save/{team_id}")
async def lineup_get_save(team_id: str, request: Request):
    ensure_db()
    username = _lineup_account(request)
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT save_data, saved_at FROM user_lineup_saves WHERE username=? AND team_id=? AND save_name='Default'",
        (username, team_id),
    ).fetchone()
    con.close()
    if not row:
        return JSONResponse(content={"ok": True, "data": {"players": []}, "saved_at": None})
    try:
        data = json.loads(row[0])
    except Exception:
        data = {"players": []}
    return JSONResponse(content={"ok": True, "data": data, "saved_at": row[1]})


@app.post("/lineup_ai/save/{team_id}")
async def lineup_save(team_id: str, request: Request, payload: dict = Body(default_factory=dict)):
    ensure_db()
    username = _lineup_account(request)
    clean = _lineup_save_payload(payload)
    saved_at = datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO user_lineup_saves(username, team_id, save_name, save_data, saved_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(username, team_id, save_name) DO UPDATE SET save_data=excluded.save_data, saved_at=excluded.saved_at",
        (username, team_id, "Default", json.dumps(clean, ensure_ascii=False), saved_at),
    )
    con.commit()
    con.close()
    return JSONResponse(content={"ok": True, "saved_at": saved_at, "players": len(clean.get("players", []))})


@app.post("/team/{team_id}/save")
async def team_save_alias(team_id: str, request: Request, payload: dict = Body(default_factory=dict)):
    return await lineup_save(team_id, request, payload)


@app.get("/lineup_ai/snapshots/{team_id}")
async def lineup_list_snapshots(team_id: str, request: Request):
    ensure_db()
    username = _lineup_account(request)
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT id, name, created_at, updated_at FROM user_lineup_snapshots WHERE username=? AND team_id=? ORDER BY created_at DESC, id DESC",
        (username, team_id),
    ).fetchall()
    con.close()
    return JSONResponse(content={"ok": True, "snapshots": [
        {"id": r[0], "name": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows
    ]})


@app.post("/lineup_ai/snapshots/{team_id}")
async def lineup_create_snapshot(team_id: str, request: Request, payload: dict = Body(default_factory=dict)):
    ensure_db()
    username = _lineup_account(request)
    clean = _lineup_save_payload(payload)
    now = datetime.now(timezone.utc).isoformat()
    name = str(payload.get("name") or "").strip()
    if not name:
        name = f"{clean.get('team_name') or team_id} — Last Update"
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(
        "INSERT INTO user_lineup_snapshots(username, team_id, name, snapshot_data, created_at, updated_at) VALUES(?,?,?,?,?,?)",
        (username, team_id, name, json.dumps(clean, ensure_ascii=False), now, now),
    )
    snap_id = cur.lastrowid
    con.commit()
    con.close()
    return JSONResponse(content={"ok": True, "id": snap_id, "name": name, "created_at": now})


@app.get("/lineup_ai/snapshots/{team_id}/{snapshot_id}")
async def lineup_get_snapshot(team_id: str, snapshot_id: int, request: Request):
    ensure_db()
    username = _lineup_account(request)
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT id, name, snapshot_data, created_at, updated_at FROM user_lineup_snapshots WHERE username=? AND team_id=? AND id=?",
        (username, team_id, snapshot_id),
    ).fetchone()
    con.close()
    if not row:
        return JSONResponse(content={"ok": False, "error": "snapshot not found"}, status_code=404)
    try:
        data = json.loads(row[2])
    except Exception:
        data = {"players": []}
    return JSONResponse(content={"ok": True, "snapshot": {"id": row[0], "name": row[1], "data": data, "created_at": row[3], "updated_at": row[4]}})


@app.patch("/lineup_ai/snapshots/{team_id}/{snapshot_id}")
async def lineup_rename_snapshot(team_id: str, snapshot_id: int, request: Request, payload: dict = Body(default_factory=dict)):
    ensure_db()
    username = _lineup_account(request)
    name = str((payload or {}).get("name") or "").strip()
    if not name:
        return JSONResponse(content={"ok": False, "error": "empty name"}, status_code=400)
    now = datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(
        "UPDATE user_lineup_snapshots SET name=?, updated_at=? WHERE username=? AND team_id=? AND id=?",
        (name, now, username, team_id, snapshot_id),
    )
    con.commit()
    changed = cur.rowcount
    con.close()
    if not changed:
        return JSONResponse(content={"ok": False, "error": "snapshot not found"}, status_code=404)
    return JSONResponse(content={"ok": True, "id": snapshot_id, "name": name, "updated_at": now})


@app.delete("/lineup_ai/snapshots/{team_id}/{snapshot_id}")
async def lineup_delete_snapshot(team_id: str, snapshot_id: int, request: Request):
    ensure_db()
    username = _lineup_account(request)
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(
        "DELETE FROM user_lineup_snapshots WHERE username=? AND team_id=? AND id=?",
        (username, team_id, snapshot_id),
    )
    con.commit()
    changed = cur.rowcount
    con.close()
    if not changed:
        return JSONResponse(content={"ok": False, "error": "snapshot not found"}, status_code=404)
    return JSONResponse(content={"ok": True, "id": snapshot_id})


def _extract_response_text(data: dict) -> str:
    """Extract text from OpenAI-compatible Responses/Chat payloads."""
    try:
        output_text = data.get("output_text")
        if output_text:
            return str(output_text)
    except Exception:
        pass
    try:
        output = data.get("output") or []
        chunks = []
        for item in output:
            for c in item.get("content") or []:
                txt = c.get("text") or c.get("output_text")
                if txt:
                    chunks.append(str(txt))
        if chunks:
            return "\n".join(chunks)
    except Exception:
        pass
    try:
        choices = data.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(str(x.get("text") or "") for x in content if isinstance(x, dict))
    except Exception:
        pass
    return ""


def _parse_vision_players_text(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    # Prefer JSON: {"players": [..]} or [..]
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, str):
            obj = json.loads(obj)
        if isinstance(obj, dict):
            arr = obj.get("players") or obj.get("names") or []
        elif isinstance(obj, list):
            arr = obj
        else:
            arr = []
        names = []
        for x in arr:
            if isinstance(x, dict):
                x = x.get("name") or x.get("player") or ""
            x = re.sub(r"^\s*\d+[.)-]?\s*", "", str(x)).strip()
            if x:
                names.append(x)
        return names[:30]
    except Exception:
        pass
    # Fallback: split natural text/list.
    raw = re.sub(r"(?i)^players?\s*:\s*", "", raw)
    parts = re.split(r"[,;\n\r]+", raw)
    out = []
    for p in parts:
        p = re.sub(r"^\s*[-*•\d.)]+\s*", "", p).strip()
        p = re.sub(r"\s+", " ", p)
        if p and len(p) <= 80:
            out.append(p)
    return out[:30]


@app.post("/lineup_ai/vision_lineup/{team_id}")
async def lineup_vision_lineup(team_id: str, payload: dict = Body(default_factory=dict)):
    mode = str((payload or {}).get("mode") or "").strip()
    api_url = os.environ.get("VISION_API_URL") or os.environ.get("LLM_API_URL")
    api_key = os.environ.get("VISION_API_KEY") or os.environ.get("LLM_API_KEY")
    model = os.environ.get("VISION_MODEL") or os.environ.get("LLM_MODEL") or os.environ.get("GATE_MODEL")
    timeout_s = int(os.environ.get("VISION_TIMEOUT_SECONDS", os.environ.get("LLM_TIMEOUT_SECONDS", "45")))
    if not api_url or not api_key or not model:
        return JSONResponse(content={"ok": False, "error": "Vision API is not configured"}, status_code=503)

    image = str((payload or {}).get("image") or "").strip()
    if not image.startswith("data:image/") or ";base64," not in image:
        return JSONResponse(content={"ok": False, "error": "Expected image data URL"}, status_code=400)
    header, b64 = image.split(",", 1)
    if len(b64) > 8_000_000:
        return JSONResponse(content={"ok": False, "error": "Image is too large"}, status_code=413)
    try:
        image_bytes = base64.b64decode(b64, validate=True)
    except Exception:
        return JSONResponse(content={"ok": False, "error": "Invalid image base64"}, status_code=400)
    mime = header.split(";", 1)[0].replace("data:", "")
    ext = "jpg" if mime in ("image/jpeg", "image/jpg") else "png" if mime == "image/png" else "webp" if mime == "image/webp" else "bin"
    if ext == "bin":
        return JSONResponse(content={"ok": False, "error": "Unsupported image type"}, status_code=400)

    roster = []
    try:
        cache_path = f"/home/openclaw/.openclaw/workspace/_live_cache_{team_id}.json"
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        roster = [str(p.get("name") or "").strip() for p in data.get("players", []) if p.get("name")]
    except Exception:
        roster = []

    prompt = (
        "Extract football player names from this lineup/squad image. "
        "Return ONLY strict JSON with this schema: {\"players\":[\"Name\",\"Name\"]}. "
        "Do not add markdown or explanations. Preserve accents when visible. "
        "If the image contains abbreviated surnames, return the surname as visible. "
        "If a roster list is provided, prefer matching names/surnames from that roster."
    )
    if mode == "squad":
        prompt += " Extract ALL player names visible in the image (entire squad), not just starting XI."
    prompt += "\n\nCurrent team roster candidates:\n" + "\n".join(roster[:60])
    # Send base64 image data directly (Wormsoft API expects base64)
    payload_api = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image}},
            ],
        }],
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://x11radar.ru", "X-Title": "FormAlert Vision"}
    try:
        t = httpx.Timeout(timeout_s, connect=15.0)
        async with httpx.AsyncClient(timeout=t) as client:
            r = await client.post(api_url, headers=headers, json=payload_api)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:500] if e.response is not None else ""
        return JSONResponse(content={"ok": False, "error": f"Vision API HTTP {e.response.status_code if e.response is not None else ''}: {detail}"}, status_code=502)
    except Exception as e:
        return JSONResponse(content={"ok": False, "error": f"Vision API error: {type(e).__name__}"}, status_code=502)

    out_text = _extract_response_text(data)
    players = _parse_vision_players_text(out_text)
    return JSONResponse(content={"ok": True, "players": players, "raw": out_text[:1000]})


@app.get("/team/{team_id}")
async def team_get_alias(team_id: str, embed: str = ""):
    try:
        prepare_team_data_version(team_id)
    except Exception:
        pass
    return render_team_view(team_id, embed)


@app.get("/lineup_ai/{team_id}")
async def lineup_team(team_id: str, embed: str = ""):
    try:
        prepare_team_data_version(team_id)
    except Exception:
        pass
    return render_team_view(team_id, embed)





def _db_one(sql: str, args=()):
    con = sqlite3.connect(DB_PATH)
    row = con.execute(sql, args).fetchone()
    con.close()
    return row


def _db_exec(sql: str, args=()):
    con = sqlite3.connect(DB_PATH)
    con.execute(sql, args)
    con.commit()
    con.close()


def db_get_state(key: str) -> str | None:
    con = sqlite3.connect(DB_PATH)
    cur = con.execute("SELECT value FROM state WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else None


def db_set_state(key: str, value: str) -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute("INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    con.commit()
    con.close()


def _load_phrases(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            out = []
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                out.append(s.lower())
            return out
    except FileNotFoundError:
        return []


def _norm_text(s: str) -> str:
    # Normalize unicode (turn fancy bold/italic letters into plain where possible)
    return unicodedata.normalize('NFKC', s or '')


def _tokenize_words(s: str) -> list[str]:
    # letters/digits/' kept, everything else -> space
    s = _norm_text(s)
    out = []
    cur = []
    for ch in (s or "").lower():
        if ch.isalnum() or ch in ("'", "’"):
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur))
                cur = []
    if cur:
        out.append("".join(cur))
    return out


def _phrase_match_exact(words: list[str], phrase: str) -> bool:
    ph = (phrase or "").strip().lower()
    if not ph:
        return False
    ph_words = _tokenize_words(ph)
    if not ph_words:
        return False
    if len(ph_words) == 1:
        return ph_words[0] in words
    # multiword: contiguous subsequence
    n = len(ph_words)
    for i in range(0, max(0, len(words) - n + 1)):
        if words[i : i + n] == ph_words:
            return True
    return False


def keyword_filter_stats(text: str) -> tuple[bool,bool,bool,bool]:
    """Returns (passes, hit_include, hit_blacklist, hit_player).

    Policy:
    - MUST hit include keywords AND MUST hit player name
    - MUST NOT hit blacklist

    MATCH_MODE applies to include/blacklist.
    Player names: case-insensitive substring match on normalized text.

    - hit_blacklist is TRUE if any blacklist phrase matches (regardless of include/player)
    - passes is TRUE only if hit_include AND hit_player AND NOT hit_blacklist
    """
    t_norm = _norm_text(text)
    t_low = t_norm.lower()

    include = _load_phrases(KEYWORDS_INCLUDE_PATH)
    blacklist = _load_phrases(KEYWORDS_BLACKLIST_PATH)
    players = _load_phrases(PLAYER_NAMES_PATH)

    if MATCH_MODE == "exact":
        words = _tokenize_words(text)
        hit_black = any(_phrase_match_exact(words, ph) for ph in blacklist)
        hit_inc = any(_phrase_match_exact(words, ph) for ph in include) if include else False
    else:
        hit_black = any((ph and ph in t_low) for ph in blacklist)
        hit_inc = any((ph and ph in t_low) for ph in include) if include else False

    # player names match (substring on normalized text)
    hit_player = any((pn and pn.lower() in t_low) for pn in players) if players else False

    passes = bool(hit_inc) and bool(hit_player) and (not hit_black)
    return (passes, bool(hit_inc), bool(hit_black), bool(hit_player))


@app.get("/lineup_ai/api/team_tweets")
async def lineup_team_tweets(team_id: str = "", team_ids: str = "", limit: int = 20):
    """Return last N tweets matching any of the given teams.

    Filters:
      - kw_pass=1 (Keywords passed, Blacklist passed)
      - tweet_status.relevant=1 (AI relevance passed)
      - gate_decision NULL or IN (\'YES\', \'BYPASS\') (Gate AI)
      - duplicate_of IS NULL (Double dedupe)

    Args:
      team_id: single team id (for Team mode)
      team_ids: comma-separated team ids (for Match mode home + away)
      limit: 1-50, default 20

    Returns: {tweets: [...], count, team_ids: [...]}
    """
    if limit <= 0 or limit > 50:
        limit = 20

    # Build list of team ids.
    ids: list = []
    if team_ids:
        for t in team_ids.split(","):
            t = t.strip()
            if t and t not in ids:
                ids.append(t)
    if team_id and team_id not in ids:
        ids.append(team_id)
    if not ids:
        raise HTTPException(status_code=400, detail="team_id required")

    # Aggregate player names across all teams.
    player_names: list[str] = []
    for tid in ids:
        try:
            cache_path = os.path.join("/home/openclaw/.openclaw/workspace", f"_live_cache_{tid}.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                for p in (cache.get("players") or []):
                    n = (p.get("name") or "").strip()
                    if n and n not in player_names:
                        player_names.append(n)
        except Exception:
            pass

    kw_includes = _load_phrases(KEYWORDS_INCLUDE_PATH)

    ensure_db()
    con = sqlite3.connect(DB_PATH)
    try:
        conds = []
        args: list = []
        if player_names:
            for n in player_names:
                conds.append("LOWER(t.text) LIKE ?")
                args.append(f"%{n.lower()}%")
        for kw in kw_includes:
            conds.append("LOWER(t.text) LIKE ?")
            args.append(f"%{kw.lower()}%")
        if not conds:
            return {"tweets": [], "count": 0, "team_ids": ids}
        where = " OR ".join(conds)
        sql = (
            "SELECT t.tweet_id, t.created_at, t.source_username, t.text, t.url, t.media_url, t.media_type "
            "FROM tweets t "
            "INNER JOIN tweet_status s ON s.tweet_id = t.tweet_id "
            "WHERE t.kw_pass=1 AND t.kw_blacklist_hit=0 "
            "AND s.relevant=1 "
            "AND (s.gate_decision IS NULL OR s.gate_decision IN ('YES','BYPASS')) "
            "AND s.duplicate_of IS NULL "
            f"AND ({where}) "
            "ORDER BY t.created_at DESC LIMIT ?"
        )
        args.append(limit * 3)
        rows = con.execute(sql, args).fetchall()
    finally:
        con.close()

    out: list[dict] = []
    for tweet_id, created_at, source_username, text, url, media_url, media_type in rows:
        if not text:
            continue
        text_low = text.lower()
        matched_players = sorted({
            n for n in player_names if n.lower() in text_low
        })
        matched_keywords = sorted({
            kw for kw in kw_includes if kw and kw.lower() in text_low
        })
        out.append({
            "tweet_id": tweet_id,
            "created_at": created_at,
            "source_username": source_username or "",
            "text": text,
            "url": url or "",
            "media_url": media_url or "",
            "media_type": media_type or "",
            "matched_players": matched_players,
            "matched_keywords": matched_keywords,
        })
        if len(out) >= limit:
            break
    return {"tweets": out, "count": len(out), "team_ids": ids}


def _cleanup_old_tweets(max_age_days: int = 7) -> int:
    """Delete tweets older than max_age_days to bound DB size."""
    try:
        ensure_db()
        con = sqlite3.connect(DB_PATH)
        try:
            cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).strftime("%Y-%m-%dT%H:%M:%S")
            cur = con.execute("DELETE FROM tweets WHERE created_at < ?", (cutoff,))
            con.commit()
            deleted = cur.rowcount
        finally:
            con.close()
        if deleted:
            log.info("cleanup: deleted %d tweets older than %d days", deleted, max_age_days)
        return deleted
    except Exception as e:
        log.warning("cleanup_old_tweets failed: %s", e)
        return 0


def _start_tweets_cleanup_loop():
    import threading
    stop = {"flag": False}
    def loop():
        while not stop["flag"]:
            try:
                threading.Event().wait(1800)
                if stop["flag"]:
                    break
                _cleanup_old_tweets()
            except Exception as e:
                log.warning("cleanup loop error: %s", e)
    t = threading.Thread(target=loop, daemon=True, name="tweets-cleanup")
    t.start()


_start_tweets_cleanup_loop()


def probable_xi_filter_stats(text: str) -> tuple[bool,bool,bool]:
    """Returns (passes, hit_probable_xi, hit_blacklist)."""
    t_low = _norm_text(text).lower()
    probable = _load_phrases(PROBABLE_XI_PATH)
    blacklist = _load_phrases(KEYWORDS_BLACKLIST_PATH)

    hit_bl = any((ph and ph in t_low) for ph in blacklist)
    hit_px = any((ph and _norm_text(ph).lower() in t_low) for ph in probable) if probable else False

    passes = bool(hit_px) and (not hit_bl)
    return (passes, bool(hit_px), bool(hit_bl))


def starting_xi_filter_stats(text: str) -> tuple[bool,bool,bool]:
    """Returns (passes, hit_starting_xi, hit_blacklist).

    STRICT policy (official starting XI only):
    - MUST hit starting_xi keywords
    - MUST NOT hit blacklist
    - MUST NOT look like probable_xi (if probable_xi keywords also hit => do NOT treat as Starting XI)
    - Player names are NOT required.

    Matching is done on normalized lower text with simple substring.
    """
    t_low = _norm_text(text).lower()
    starters = _load_phrases(STARTING_XI_PATH)
    blacklist = _load_phrases(KEYWORDS_BLACKLIST_PATH)

    hit_bl = any((ph and ph in t_low) for ph in blacklist)
    hit_sx = any((ph and _norm_text(ph).lower() in t_low) for ph in starters) if starters else False

    # If it matches probable XI phrasing, do not treat as starting XI.
    px_pass, _, _ = probable_xi_filter_stats(text)

    passes = bool(hit_sx) and (not hit_bl) and (not px_pass)
    return (passes, bool(hit_sx), bool(hit_bl))


def _passes_keyword_filters(text: str) -> bool:
    return keyword_filter_stats(text)[0]


async def fetch_list_tweets_once(max_results: int = 100) -> tuple[int,int,int,int,list[str]]:
    """Fetch one page of tweets from X list and store unique ones.

    Returns: (x_requests, received_count, passed_keywords_count, stored_count, stored_ids)
    """
    if not X_BEARER_TOKEN or not X_LIST_ID:
        return 0

    # NOTE: /2/lists/:id/tweets does NOT support since_id.
    # Use pagination_token and keep the first page only to approximate incremental fetch.
    url = f"https://api.x.com/2/lists/{X_LIST_ID}/tweets"

    # Hard guarantee: exactly ONE X request per cycle.
    # We DO NOT paginate deeper.
    params = {
        "max_results": max(5, min(int(max_results), 100)),
        "tweet.fields": "created_at,author_id,attachments",
        "expansions": "author_id,attachments.media_keys",
        "user.fields": "username,name",
        "media.fields": "url,preview_image_url,type",
    }

    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()

    tweets = data.get("data") or []
    received_count = len(tweets)

    includes = data.get("includes") or {}
    users = includes.get("users") or []
    user_by_id = {}
    for u in users:
        uid = str(u.get("id"))
        if uid:
            user_by_id[uid] = u

    media = includes.get("media") or []
    media_by_key = {}
    for m in media:
        k = str(m.get("media_key") or "")
        if k:
            media_by_key[k] = m

    # meta contains pagination tokens, but we intentionally ignore them (single request per cycle)

    stored_count = 0              # NEW tweets inserted
    passed_keywords_count = 0      # NEW tweets that passed keywords
    stored_ids: list[str] = []

    con = sqlite3.connect(DB_PATH)
    for t in tweets:
        tid = str(t.get("id"))
        if not tid:
            continue
        text = t.get("text") or ""
        created_at = t.get("created_at")
        author_id = t.get("author_id")
        author_id_s = str(author_id) if author_id is not None else ""
        username = (user_by_id.get(author_id_s) or {}).get("username")
        source_username = f"@{username}" if username else ""

        link = f"https://x.com/i/web/status/{tid}"
        raw_json = str(t)

        # extract first media url (photo or preview)
        media_url = ""
        media_type = ""
        try:
            att = t.get("attachments") or {}
            keys = att.get("media_keys") or []
            if keys and isinstance(keys, list):
                m0 = media_by_key.get(str(keys[0]) or "") or {}
                media_type = str(m0.get("type") or "")
                media_url = str(m0.get("url") or m0.get("preview_image_url") or "")
        except Exception:
            media_url = ""
            media_type = ""

        passes, hit_inc, hit_bl, hit_player = keyword_filter_stats(text)

        inserted_new = False
        # Store ALL tweets for visibility, regardless of keyword pass
        try:
            con.execute(
                "INSERT INTO tweets(tweet_id, created_at, author_id, source_username, text, url, raw_json, kw_pass, kw_blacklist_hit, media_url, media_type) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (tid, created_at, author_id_s, source_username, text, link, raw_json, 1 if passes else 0, 1 if hit_bl else 0, media_url, media_type),
            )
            stored_count += 1
            inserted_new = True
        except sqlite3.IntegrityError:
            # update kw flags on existing row
            con.execute(
                "UPDATE tweets SET kw_pass=?, kw_blacklist_hit=?, source_username=?, media_url=?, media_type=? WHERE tweet_id=?",
                (1 if passes else 0, 1 if hit_bl else 0, source_username, media_url, media_type, tid),
            )

        # Only queue for LLM if it passes either:
        # - main filter (keywords+player_names, not blacklist)
        # - probable_xi mode (probable_xi keywords, not blacklist)
        if inserted_new:
            px_pass, _, _ = probable_xi_filter_stats(text)
            sx_pass, _, _ = starting_xi_filter_stats(text)
            if passes or px_pass or sx_pass:
                passed_keywords_count += 1
                stored_ids.append(tid)
    con.commit()
    con.close()

    # No pagination token is stored/used.

    return (1, received_count, passed_keywords_count, stored_count, stored_ids)


def _coerce_bool(v, default=False):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.lower() in ("true", "1", "yes", "y"):
            return True
        if v.lower() in ("false", "0", "no", "n"):
            return False
    return default


def _extract_json_from_text(s: str) -> str | None:
    """Extract the first valid JSON object substring using brace balancing.

    This is robust to leading/trailing text and multiple JSON objects.
    """
    if not s:
        return None

    in_str = False
    esc = False
    depth = 0
    start = None

    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = False
            continue

        # not in string
        if ch == '"':
            in_str = True
            continue

        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = s[start : i + 1]
                    # quick sanity
                    if '"relevant"' in candidate or '"category"' in candidate:
                        return candidate
                    return candidate

    return None


def lookup_team_for_source(source: str) -> str:
    try:
        con = sqlite3.connect(DB_PATH)
        row = con.execute("SELECT team FROM teams_map WHERE source=?", (source,)).fetchone()
        con.close()
        return (row[0] if row else "") or ""
    except Exception:
        return ""


def _validate_classification(obj: dict) -> dict:
    """Validate LLM output for new publish schema.

    Accepts: {publish: bool, impact: str, category: str,
              players: list, teams: list, reason: str}

    Returns: dict with backward-compatible keys (relevant, category,
    impact_level, teams, players, formatted_signal) so the rest of the
    pipeline keeps working without further changes.
    """
    publish = bool(obj.get("publish"))

    impact = (obj.get("impact") or "").strip().lower()
    if impact not in IMPACT_LEVELS:
        impact = "none" if not publish else "low"

    category = (obj.get("category") or "").strip().lower()
    if category not in CATEGORIES:
        category = "other"

    def _cap(s):
        s = (str(s) if s is not None else "").strip()
        if not s:
            return ""
        return " ".join(w for w in s.split() if w).title()

    players_raw = obj.get("players") or []
    teams_raw = obj.get("teams") or []
    players = [_cap(p) for p in (players_raw if isinstance(players_raw, list) else [])]
    players = [p for p in players if p]
    teams = [_cap(t) for t in (teams_raw if isinstance(teams_raw, list) else [])]
    teams = [t for t in teams if t]

    reason = (obj.get("reason") or "").strip()
    if len(reason) > 200:
        reason = reason[:197] + "..."

    # Backward compat aliases
    relevant = publish
    impact_level = impact.upper() if impact != "none" else "LOW"
    confidence = 1.0 if publish else 0.0
    competition = ""
    analysis_ru = reason  # reuse existing field

    # Build a simple formatted_signal for sidebar.
    # The sidebar shows the tweet as-is from the DB; formatted_signal is
    # legacy and not used by the new pipeline, but we still populate it
    # for compatibility.
    cat_ru = {
        "official_lineup": "стартовый состав",
        "injury": "травма / готовность",
        "suspension": "дисквалификация",
        "availability": "доступность",
        "training": "тренировка",
        "recovery": "возвращение после травмы",
        "travel_squad": "заявка на матч",
        "rotation": "ротация",
        "coach_comment": "заявление тренера",
        "goalkeeper": "смена вратаря",
        "tactical": "тактика",
        "other": "прочее",
    }
    imp_ru = {"critical": "критическое", "high": "высокое", "medium": "среднее", "low": "низкое", "none": "нет"}
    cat_text = cat_ru.get(category, category)
    imp_text = imp_ru.get(impact, impact)
    player_part = (", ".join(players[:3])) if players else ""
    parts = []
    if reason:
        parts.append(reason)
    if player_part:
        parts.append(player_part)
    parts.append(f"({cat_text}, влияние: {imp_text})")
    formatted_signal = " — ".join(parts)

    return {
        "relevant": relevant,
        "category": category,
        "impact_level": impact_level,
        "impact": impact,
        "publish": publish,
        "confidence": confidence,
        "teams": teams,
        "players": players,
        "competition": competition,
        "analysis_ru": analysis_ru,
        "reason": reason,
        "formatted_signal": formatted_signal,
    }



async def llm_gate_relevance(tweet_text: str, tweet_url: str) -> bool:
    """Cheap YES/NO gate to avoid expensive core calls.

    IMPORTANT: prefer recall over precision (avoid false negatives).
    If obvious football-signal phrases exist, return YES without model call.
    """
    if not GATE_ENABLED:
        return True

    t = (tweet_text or "").lower()

    # Fast-path: HOT-only signals (focus on next-match unavailability)
    # NOTE: We keep it strict to reduce noise.
    fast_yes_phrases = [
        # --- absences / injuries (hot) ---
        "absence", "absences", "absent", "absents", "absent sur blessure",
        "blesse", "blessees", "blesses", "blessure", "blessures", "nouvelles blessures",
        "forfait", "forfaits", "nouveau forfait",
        "incertain", "incertains", "incertitude",
        "infirmerie", "linfirmerie",
        "ne sera pas dans", "n'est pas pret", "pas certain",
        "se passer des services", "va devoir se passer des",
        "quitte prematurement", "sur civiere",
        "probleme graves", "problemes graves", "problemes grave", "grands problemes",
        # injuries/body parts (supporting, still hot when present)
        "adducteur", "adducteurs", "cuisse", "cheville", "contusion", "crampes", "dorsale", "douleur",
        "genou", "hanche", "lesion", "luxation", "malade", "maladie", "mollet", "musculaire",
        "rompu", "rupture", "tendon", "traumatisme", "virus", "covid", "coronavirus",
        "ischio-jambiers", "ligaments croise", "ligaments croises", "rupture des ligaments",
        "fracture de", "fracture de fatigue au tibia", "fracture d'un orteil",
        "inquiétant",
        # --- discipline (hot) ---
        "carton rouge", "rouge carton", "expulsion", "exclu", "suspendu", "suspendus", "suspension",
        "accumulation de cartons jaunes",
        # --- national team callup (hot-ish) ---
        "appele", "convoque",
    ]

    for ph in fast_yes_phrases:
        if ph and ph in t:
            return True

    api_url = os.environ.get("LLM_API_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("GATE_MODEL")

    if not api_url or not api_key or not model:
        return False

    prompt = (
        "Ты фильтр HOT-алертов. Ответь строго одним токеном: YES или NO. "
        "Ставь YES ТОЛЬКО если смысл твита: игрок НЕ СЫГРАЕТ или ПОД ВОПРОСОМ на следующий матч, "
        "или есть красная/удаление/дисквалификация, или вызов в сборную, который означает пропуск матча клуба. "
        "Если просто общие новости/слухи/игровой контекст без факта отсутствия — NO. "
        "Если сомневаешься — NO.\n\n"
        "КРИТЕРИИ YES (самые горячие):\n"
        "- absence/absent/absents/absences\n"
        "- blessure/blessures/blesse/blesses/forfait/nouveau forfait\n"
        "- incertain/incertitude/pas certain/n'est pas pret/ne sera pas dans\n"
        "- carton rouge/rouge carton/expulsion/exclu/suspendu/suspension/accumulation de cartons jaunes\n"
        "- fracture/luxation/rupture/ligaments croises/sur civiere\n"
        "- appele/convoque (YES только если явно = пропуск матча клуба)\n\n"
        "TWEET_TEXT:\n" + tweet_text + "\n\n"
        "TWEET_URL:\n" + tweet_url + "\n"
    )

    payload = {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "stream": False,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://x11radar.ru", "X-Title": "FormAlert Vision"}

    try:
        async with httpx.AsyncClient(timeout=GATE_TIMEOUT_SECONDS) as client:
            r = await client.post(api_url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return False

    out_text = ""
    try:
        # output may be [reasoning, message] for kimi. Collect all.
        output = data.get("output") or []
        parts = []
        for item in output:
            if not isinstance(item, dict):
                continue
            for c in (item.get("content") or []):
                if isinstance(c, dict) and c.get("text"):
                    parts.append(c["text"])
            for s in (item.get("summary") or []):
                if isinstance(s, dict) and s.get("text"):
                    parts.append(s["text"])
        out_text = "\n".join(parts).strip()
    except Exception:
        out_text = ""

    out_text = out_text.upper()
    if out_text.startswith("YES") and "NO" not in out_text:
        return True
    return False


async def llm_classify(tweet_text: str, tweet_url: str, source_username: str = "", tweet_created_at: str = "") -> dict:
    """Calls Wormsoft Responses API (Core engine). Returns validated classification dict.

    Adds debug fields (prefixed with _):
      _core_preview, _core_json_valid, _core_error
    """
    api_url = os.environ.get("LLM_API_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    timeout_s = int(os.environ.get("LLM_TIMEOUT_SECONDS", "40"))

    if not api_url or not api_key or not model:
        return _validate_classification({"relevant": False})

    prompt = (
        "# РОЛЬ\n"
        "Ты — футбольный аналитик сервиса LineupValue.\n"
        "Ты НЕ модератор Twitter.\n"
        "Ты НЕ журналист.\n"
        "Ты НЕ пересказываешь новости.\n"
        "Твоя единственная задача — определить, содержит ли пост информацию, "
        "которая может изменить ожидания по стартовому составу команды или "
        "повлиять на анализ ближайших матчей.\n\n"

        "# ВАЖНО\n"
        "До тебя уже были выполнены следующие проверки:\n"
        "- Пост не содержит слов из Blacklist.\n"
        "- Пост содержит одно или несколько ключевых слов.\n"
        "- В тексте найдено имя или фамилия игрока.\n"
        "- Пост не является дубликатом.\n"
        "Поэтому НЕ нужно заново оценивать эти критерии.\n"
        "Тебе нужно определить только смысл публикации.\n\n"

        "# ЧТО СЧИТАЕТСЯ РЕЛЕВАНТНЫМ\n"
        "Возвращай publish=true только если пост содержит новую информацию хотя бы об одном из следующих событий:\n"
        "- подтвержденная травма\n"
        "- вероятность пропуска матча\n"
        "- дисквалификация\n"
        "- возвращение после травмы\n"
        "- возвращение к тренировкам\n"
        "- отсутствие на тренировке\n"
        "- участие в тренировке отдельно от группы\n"
        "- попадание или непопадание в заявку\n"
        "- стартовый состав\n"
        "- запасные\n"
        "- изменение позиции игрока\n"
        "- смена основного вратаря\n"
        "- подтвержденная ротация\n"
        "- заявление тренера о готовности или неготовности игрока\n"
        "- официальный список игроков на матч\n"
        "- любая информация, которая увеличивает или уменьшает вероятность выхода игрока в стартовом составе\n\n"

        "# ЧТО НЕ ЯВЛЯЕТСЯ РЕЛЕВАНТНЫМ\n"
        "Возвращай publish=false если пост относится к следующим темам:\n"
        "- интервью без новой информации\n"
        "- поздравления\n"
        "- дни рождения\n"
        "- фотографии\n"
        "- видео\n"
        "- лучшие моменты\n"
        "- обзор матча\n"
        "- эмоции после матча\n"
        "- маркетинг\n"
        "- продажа билетов\n"
        "- продажа формы\n"
        "- реклама\n"
        "- статистика прошедших матчей\n"
        "- исторические публикации\n"
        "- цитаты без новой информации\n\n"

        "# ОСОБОЕ ПРАВИЛО\n"
        "Если новость выглядит важной, но не содержит новой информации относительно уже известных фактов — возвращай publish=false.\n"
        "LineupValue должна публиковать только события, которые действительно меняют понимание ситуации.\n\n"

        "# ОЦЕНИ ВЛИЯНИЕ\n"
        "impact: critical | high | medium | low | none\n\n"

        "# ОПРЕДЕЛИ КАТЕГОРИЮ (только одну)\n"
        "official_lineup | injury | suspension | availability | training | recovery | "
        "travel_squad | rotation | coach_comment | goalkeeper | tactical | other\n\n"

        "# ИЗВЛЕКИ\n"
        "players: имена/фамилии игроков (массив строк)\n"
        "teams: названия команд (массив строк)\n\n"

        "# КРАТКОЕ ОБОСНОВАНИЕ\n"
        "reason: одно предложение (не более 20 слов), почему пост релевантен или нерелевантен.\n\n"

        "# ВЕРНИ ТОЛЬКО JSON\n"
        "{\n"
        '  "publish": true|false,\n'
        '  "impact": "critical|high|medium|low|none",\n'
        '  "category": "...",\n'
        '  "players": ["..."],\n'
        '  "teams": ["..."],\n'
        '  "reason": "..."\n'
        "}\n\n"

        "# КОНТЕКСТ ТВИТА\n"
        "TWEET_TEXT:\n" + tweet_text + "\n\n"
        "TWEET_URL:\n" + tweet_url + "\n\n"
        "source_username:\n" + source_username + "\n\n"
        "tweet_created_at:\n" + tweet_created_at + "\n\n"
        "Верни ТОЛЬКО один JSON-объект. Никакого markdown, текста или пояснений вокруг."
    )

    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        t = httpx.Timeout(timeout_s, connect=15.0)
        async with httpx.AsyncClient(timeout=t) as client:
            r = await client.post(api_url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        out = _validate_classification({"relevant": False})
        out["_core_preview"] = ""
        out["_core_json_valid"] = False
        out["_core_error"] = f"HTTP_ERROR:{type(e).__name__}"
        return out

    # Wormsoft/kimi responses: output may be [reasoning, message].
    # We collect text from ALL output items (especially type=message).
    out_text = ""
    try:
        output = data.get("output") or []
        parts = []
        for item in output:
            if not isinstance(item, dict):
                continue
            for c in (item.get("content") or []):
                if isinstance(c, dict) and c.get("text"):
                    parts.append(c["text"])
            for s in (item.get("summary") or []):
                if isinstance(s, dict) and s.get("text"):
                    parts.append(s["text"])
        out_text = "\n".join(parts).strip()
    except Exception:
        out_text = ""

    # Trim to reduce chance of provider-side truncation
    out_text = (out_text or "").strip()

    json_str = _extract_json_from_text(out_text)
    if not json_str:
        # fallback: maybe the entire output is JSON
        if out_text.startswith("{") and out_text.rstrip().endswith("}"):
            json_str = out_text
        else:
            json_str = ""
    json_valid = False
    core_error = ""

    def try_parse(s: str):
        try:
            return json.loads(s) if s else {}
        except Exception as e:
            return e

    parsed = try_parse(json_str)

    # Cheap recovery: if JSON likely broke due to raw newlines, escape them and retry.
    if isinstance(parsed, Exception) and json_str:
        fixed = json_str.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
        parsed2 = try_parse(fixed)
        if not isinstance(parsed2, Exception):
            parsed = parsed2
        else:
            parsed = parsed  # keep original exception

    if isinstance(parsed, Exception):
        core_error = f"JSON_PARSE:{type(parsed).__name__}"  # real exception type
        obj = {}
        json_valid = False
    else:
        obj = parsed
        json_valid = True

    # carry source_username through (if present in JSON)
    validated = _validate_classification(obj)
    if validated is None:
        validated = _validate_classification({"relevant": False})
    validated["source_username"] = str((obj or {}).get("source_username") or "")
    validated["analysis_ru"] = str((obj or {}).get("analysis_ru") or "").strip()
    validated["tweet_created_at"] = str((obj or {}).get("tweet_created_at") or "")

    validated["_core_preview"] = (out_text or "")[:800]
    validated["_core_json_valid"] = json_valid
    validated["_core_error"] = core_error
    return validated


def _dedupe_key(team: str, category: str) -> str:
    return f"{(team or '').strip().lower()}|{(category or '').strip().lower()}"


def _canonical_player_for_dedupe(players, text: str) -> str:
    # Prefer extracted player token(s)
    if isinstance(players, list) and players:
        p0 = _norm_text(str(players[0] or "")).strip()
        if not p0:
            return ""
        # Allow single token (surname) or full name; normalize to lower
        return p0.lower()

    # Fallback: try to find a plausible player name token in text.
    # Prefer two consecutive capitalized words; if not found, fall back to a single capitalized word.
    t = _norm_text(text)
    words = [w for w in t.replace('\n', ' ').split(' ') if w]

    def clean(w: str) -> str:
        return w.strip(" ,.!?;:\"'()[]{}“”«»")

    best_two = ""
    for i in range(len(words) - 1):
        a = clean(words[i])
        b = clean(words[i + 1])
        if not a or not b:
            continue
        if a[:1].isupper() and b[:1].isupper() and a.isalpha() and b.isalpha():
            cand = f"{a} {b}"
            if len(cand) > len(best_two):
                best_two = cand

    if best_two:
        return best_two.lower()

    # single-token fallback
    for w in words:
        a = clean(w)
        if a and a[:1].isupper() and a.isalpha() and len(a) >= 3:
            return a.lower()

    return ""


def _injury_bucket(text: str) -> str:
    t = _norm_text(text).lower()
    # OUT
    out_markers = ["forfait", "ruled out", "out for", "will miss", "absent", "manquera", "ne jouera pas", "ne jouera", "не сыграет", "пропустит"]
    if any(m in t for m in out_markers):
        return "OUT"
    # OK
    ok_markers = ["va mieux", "fit", "prêt", "pret", "available", "de retour", "retour", "back", "disponible", "dans le groupe"]
    if any(m in t for m in ok_markers):
        return "OK"
    # DOUBT
    doubt_markers = ["incertain", "inquiétude", "inquietude", "not certain", "pas certain", "doute", "doubt", "fitness test", "n'est pas sûr", "n'est pas sur", "не уверен"]
    if any(m in t for m in doubt_markers):
        return "DOUBT"
    return "UNKNOWN"


def _is_duplicate_recent(team: str, category: str, hours: int = 12, player: str = "", bucket: str = "") -> str | None:
    """Return tweet_id of original if a similar item was already sent recently.

    Implemented:
      - squad_list: Team
      - coach_change: Team
      - injury_update: Team + Player + Bucket
      - starting_lineup: Team + (very loose) keyword in text
    """
    if category not in ("squad_list", "coach_change", "injury_update", "starting_lineup"):
        return None
    # Team required
    if not team:
        return None

    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat() + "Z"

    con = sqlite3.connect(DB_PATH)
    sent_rows = con.execute(
        """
        SELECT t.tweet_id, t.source_username, t.text
        FROM tweet_status s
        JOIN tweets t ON t.tweet_id = s.tweet_id
        WHERE (s.sent_at IS NOT NULL OR (s.classified_at IS NOT NULL AND s.relevant=1))
          AND s.duplicate_of IS NULL
          AND t.created_at >= ?
          AND t.source_username IS NOT NULL
        """,
        (cutoff_iso,),
    ).fetchall()
    con.close()

    for tid, srcu, txt in sent_rows:
        orig_team = ""
        if srcu:
            con = sqlite3.connect(DB_PATH)
            tr = con.execute('SELECT team FROM teams_map WHERE source=?',(srcu,)).fetchone()
            con.close()
            orig_team = tr[0] if tr else ""
        if orig_team.strip().lower() != team.strip().lower():
            continue

        if category in ("squad_list", "coach_change"):
            return tid

        # starting_lineup: dedupe by team only (2h window recommended by caller)
        if category == "starting_lineup":
            return tid

        # injury_update
        if category == "injury_update":
            if not player:
                continue
            # Compare canonical player names (prefer extracted players; fallback to text heuristics)
            old_player = _canonical_player_for_dedupe([], txt or "")
            new_player = _canonical_player_for_dedupe([player], "")
            # If we failed to canonicalize, fall back to substring match
            if new_player and old_player:
                if old_player != new_player:
                    continue
            else:
                if player.lower() not in _norm_text(txt or "").lower():
                    continue

            old_bucket = _injury_bucket(txt or "")
            # Hard rule: if an OUT was already sent for this player within window,
            # suppress any further injury_update except OK.
            if old_bucket == "OUT" and bucket != "OK":
                return tid
            if old_bucket == bucket:
                return tid

    return None


async def classify_and_alert_new_tweets(limit: int = 150, only_ids: list[str] | None = None) -> tuple[int,int,int,int]:
    """Classify unsent tweets and send only relevant=true.

    Returns: (gate_calls, core_calls, relevant_count, sent_count)
    """
    max_per_cycle = int(os.environ.get("LLM_MAX_TWEETS_PER_CYCLE", "30"))
    limit = min(int(limit), max_per_cycle)

    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS tweet_status (
          tweet_id TEXT PRIMARY KEY,
          classified_at TEXT,
          relevant INTEGER,
          sent_at TEXT,
          gate_decision TEXT,
          gate_fastpath INTEGER,
          core_json_valid INTEGER,
          core_error TEXT,
          core_preview TEXT,
          duplicate_of TEXT
        )
        """
    )
    if only_ids:
        # classify only specific tweet ids
        placeholders = ",".join(["?"] * len(only_ids))
        q = (
            "SELECT t.tweet_id, t.text, t.url, t.source_username, COALESCE(t.media_url,''), COALESCE(t.created_at,'') "
            "FROM tweets t "
            "LEFT JOIN tweet_status s ON s.tweet_id = t.tweet_id "
            f"WHERE t.tweet_id IN ({placeholders}) AND s.classified_at IS NULL "
            "ORDER BY t.tweet_id ASC "
            "LIMIT ?"
        )
        rows = con.execute(q, (*only_ids, limit)).fetchall()
    else:
        rows = con.execute(
            """
            SELECT t.tweet_id, t.text, t.url, t.source_username, COALESCE(t.media_url,''), COALESCE(t.created_at,'')
            FROM tweets t
            LEFT JOIN tweet_status s ON s.tweet_id = t.tweet_id
            WHERE s.classified_at IS NULL
            ORDER BY t.tweet_id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    con.close()

    core_calls = 0
    relevant_count = 0
    sent = 0
    gate_calls = 0

    for tid, text, url, source_username, media_url, row_created_at in rows:
        # Bypass Gate for Starting XI / Probable XI modes (keywords-only, still respect blacklist).
        sx_pass, _, _ = starting_xi_filter_stats(text or "")
        px_pass, _, _ = probable_xi_filter_stats(text or "")
        bypass_gate = bool(sx_pass or px_pass)

        if bypass_gate:
            gate_ok = True
            gate_dec = "BYPASS"
        else:
            gate_calls += 1
            gate_ok = await llm_gate_relevance(text, url)
            gate_dec = "YES" if gate_ok else "NO"

        if not gate_ok:
            # mark as classified but irrelevant (conservative)
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO tweet_status(tweet_id, classified_at, relevant, sent_at, gate_decision, gate_fastpath, core_json_valid, core_error, core_preview, duplicate_of)\n"
                "VALUES(?,?,0,NULL,?,0,NULL,?,NULL,NULL)\n"
                "ON CONFLICT(tweet_id) DO UPDATE SET classified_at=excluded.classified_at, relevant=0, gate_decision=excluded.gate_decision, core_error=excluded.core_error",
                (tid, datetime.utcnow().isoformat() + "Z", gate_dec, "GATE_NO"),
            )
            con.commit()
            con.close()
            continue

        # gate yes

        core_calls += 1
        cls = await llm_classify(text, url, source_username=source_username or "", tweet_created_at=str((row_created_at or "")))
        # store status incl. debug
        core_preview = (cls.get("_core_preview") or "")[:500]
        core_json_valid = 1 if cls.get("_core_json_valid") else 0
        core_error = cls.get("_core_error") or ""

        con = sqlite3.connect(DB_PATH)
        con.execute(
            "INSERT INTO tweet_status(tweet_id, classified_at, relevant, sent_at, gate_decision, gate_fastpath, core_json_valid, core_error, core_preview, duplicate_of)\n"
            "VALUES(?,?,?,NULL,?,0,?,?,?,NULL)\n"
            "ON CONFLICT(tweet_id) DO UPDATE SET classified_at=excluded.classified_at, relevant=excluded.relevant, gate_decision=excluded.gate_decision, core_json_valid=excluded.core_json_valid, core_error=excluded.core_error, core_preview=excluded.core_preview",
            (tid, datetime.utcnow().isoformat() + "Z", 1 if cls["relevant"] else 0, gate_dec, core_json_valid, core_error, core_preview),
        )
        con.commit()
        con.close()

        if cls["relevant"]:
            relevant_count += 1

            # Hard guard: never send Starting XI outside 80-min window to kickoff (FL1).
            if cls.get("category") == "starting_lineup":
                try:
                    team_nm = lookup_team_for_source(source_username) if source_username else ""
                    ok_window = await _fd_is_within_starting_xi_window(team_nm, window_minutes=80)
                except Exception:
                    ok_window = False
                if not ok_window:
                    con = sqlite3.connect(DB_PATH)
                    con.execute(
                        "UPDATE tweet_status SET relevant=0, core_error=? WHERE tweet_id=?",
                        ("STARTING_XI_OUTSIDE_WINDOW", tid),
                    )
                    con.commit(); con.close()
                    continue

            # Deduplicate within last 12 hours (no LLM) for selected categories
            cat = cls.get("category")
            if cat in ("squad_list", "coach_change", "injury_update", "starting_lineup"):
                team_for_dedupe = ""
                if source_username:
                    team_for_dedupe = lookup_team_for_source(source_username)

                player = ""
                bucket = ""
                hours = 12
                if cat == "injury_update":
                    pls = cls.get("players") or []
                    player = _canonical_player_for_dedupe(pls, text)
                    bucket = _injury_bucket(text)
                elif cat == "starting_lineup":
                    hours = 2

                dup_of = _is_duplicate_recent(team_for_dedupe, cat, hours=hours, player=player, bucket=bucket)
                if dup_of and dup_of != tid:
                    con = sqlite3.connect(DB_PATH)
                    con.execute(
                        "UPDATE tweet_status SET duplicate_of=? WHERE tweet_id=?",
                        (dup_of, tid),
                    )
                    con.commit(); con.close()
                    continue

            # Probable XI / Starting XI: photo+caption with optional OG image
            px_pass, _, _ = probable_xi_filter_stats(text or "")
            sx_pass, _, _ = starting_xi_filter_stats(text or "")
            image_mode = ""

            # Starting XI time gate: only enable within 80 minutes to kickoff (FL1, team from teams_map)
            sx_enabled = False
            if sx_pass:
                try:
                    team_nm = lookup_team_for_source(source_username) if source_username else ""
                    sx_enabled = await _fd_is_within_starting_xi_window(team_nm, window_minutes=80)
                except Exception:
                    sx_enabled = False

            if px_pass or sx_enabled:
                # Telegram caption limit ~1024; keep it safe
                cap = (cls.get("formatted_signal") or "")
                if len(cap) > 1000:
                    cap = cap[:1000] + "…"

                photo = (media_url or "").strip()
                if photo:
                    image_mode = "media"
                else:
                    # fallback: try OG image from first URL in tweet text
                    u = _extract_first_url(text or "")
                    if u:
                        photo = (await _fetch_og_image(u)) or ""
                        if photo:
                            image_mode = "og"

                if photo:
                    # Telegram send disabled; tweet goes to tweets-sidebar only.
                    mid = "sidebar"
                    image_mode = image_mode or "media"
                else:
                    mid = "sidebar"
            else:
                # Telegram send disabled; tweet goes to tweets-sidebar only.
                mid = "sidebar"
            if mid:
                con = sqlite3.connect(DB_PATH)
                con.execute(
                    "UPDATE tweet_status SET sent_at=?, image_mode=? WHERE tweet_id=?",
                    (datetime.utcnow().isoformat() + "Z", image_mode, tid),
                )
                con.commit()
                con.close()
                sent += 1

    return (gate_calls, core_calls, relevant_count, sent)


@app.post("/run_once", response_class=PlainTextResponse)
async def run_once(fetch_limit: int = 20, classify_limit: int = 5):
    """One controlled cycle: 1x X request -> keywords -> LLM -> Telegram.

    Safety:
    - exactly ONE X request
    - if keywords pass count is 0 => LLM is skipped
    """
    xreq, received, passed_kw, stored, stored_ids = await fetch_list_tweets_once(max_results=fetch_limit)

    if passed_kw == 0 or stored == 0:
        # log run
        con = sqlite3.connect(DB_PATH)
        con.execute(
            "INSERT INTO runs(created_at,x_requests,received,passed_keywords,stored,llm_gate_calls,llm_core_calls,relevant,sent) VALUES(?,?,?,?,?,?,?,?,?)",
            (datetime.utcnow().isoformat()+"Z", xreq, received, passed_kw, stored, 0, 0, 0, 0),
        )
        con.commit(); con.close()
        return (
            f"x_requests={xreq} received={received} passed_keywords={passed_kw} stored={stored} "
            f"gate_calls=0 core_calls=0 relevant=0 sent=0"
        )

    gate_calls, core_calls, relevant, sent = await classify_and_alert_new_tweets(limit=classify_limit, only_ids=stored_ids)

    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO runs(created_at,x_requests,received,passed_keywords,stored,llm_gate_calls,llm_core_calls,relevant,sent) VALUES(?,?,?,?,?,?,?,?,?)",
        (datetime.utcnow().isoformat()+"Z", xreq, received, passed_kw, stored, gate_calls, core_calls, relevant, sent),
    )
    con.commit(); con.close()

    return (
        f"x_requests={xreq} received={received} passed_keywords={passed_kw} stored={stored} "
        f"gate_calls={gate_calls} core_calls={core_calls} relevant={relevant} sent={sent}"
    )


scheduler = AsyncIOScheduler()
_scheduler_started = False


def _log_run(created_at: str, xreq: int, received: int, passed_kw: int, stored: int, gate_calls: int, core_calls: int, relevant: int, sent: int):
    ensure_db()
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO runs(created_at,x_requests,received,passed_keywords,stored,llm_gate_calls,llm_core_calls,relevant,sent) VALUES(?,?,?,?,?,?,?,?,?)",
        (created_at, xreq, received, passed_kw, stored, gate_calls, core_calls, relevant, sent),
    )
    con.commit(); con.close()


def _in_quiet_hours_msk() -> bool:
    if not QUIET_HOURS_ENABLED:
        return False
    try:
        from datetime import timedelta
        now_msk = datetime.utcnow() + timedelta(hours=3)
        cur = now_msk.strftime('%H:%M')
        f = (QUIET_HOURS_FROM or '00:00')
        t = (QUIET_HOURS_TO or '00:00')
        if f == t:
            return False
        # normal range
        if f < t:
            return f <= cur < t
        # crosses midnight
        return (cur >= f) or (cur < t)
    except Exception:
        return False


async def background_cycle():
    # One background cycle with logging
    try:
        if _in_quiet_hours_msk():
            # Quiet hours: skip completely (no X request, no run log)
            return

        # Re-check kw_pass for previously-rejected tweets against the current
        # keywords/player_names files. New players added since a tweet was
        # fetched (e.g. transfer window signings) will now allow past tweets
        # to qualify for LLM classification.
        try:
            rc = 0
            con = sqlite3.connect(DB_PATH)
            for r in con.execute("SELECT tweet_id, text FROM tweets WHERE kw_pass=0 ORDER BY created_at DESC LIMIT 500").fetchall():
                tid, text = r
                if not text:
                    continue
                passes, hit_inc, hit_bl, hit_pl = keyword_filter_stats(text)
                if passes:
                    con.execute("UPDATE tweets SET kw_pass=1, kw_blacklist_hit=? WHERE tweet_id=?",
                                (1 if hit_bl else 0, tid))
                    rc += 1
            if rc:
                con.commit()
            con.close()
            if rc:
                print(f"kw_pass recheck: {rc} tweets promoted kw_pass=0->1")
        except Exception as _e:
            print(f"kw_pass recheck error: {type(_e).__name__}: {_e}")

        xreq, received, passed_kw, stored, stored_ids = await fetch_list_tweets_once(max_results=15)
        if passed_kw == 0 or stored == 0:
            _log_run(datetime.utcnow().isoformat()+"Z", xreq, received, passed_kw, stored, 0, 0, 0, 0)
            return

        gate_calls, core_calls, relevant, sent = await classify_and_alert_new_tweets(limit=int(os.environ.get('LLM_MAX_TWEETS_PER_CYCLE','30')), only_ids=stored_ids)
        _log_run(datetime.utcnow().isoformat()+"Z", xreq, received, passed_kw, stored, gate_calls, core_calls, relevant, sent)
    except Exception as e:
        # Never let the scheduler job crash and drift; log a run row marking the error.
        try:
            ensure_db()
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO runs(created_at,x_requests,received,passed_keywords,stored,llm_gate_calls,llm_core_calls,relevant,sent) VALUES(?,?,?,?,?,?,?,?,?)",
                (datetime.utcnow().isoformat()+"Z", 0, 0, 0, 0, 0, 0, 0, 0),
            )
            con.commit(); con.close()
        except Exception:
            pass
        print(f"background_cycle error: {type(e).__name__}: {e}")


def scheduler_start():
    global _scheduler_started
    if _scheduler_started:
        return
    if not scheduler.running:
        scheduler.start()
    # single job does fetch+classify+log
    # Run "on the wall" every N minutes in MSK (UTC+3) to avoid drift.
    try:
        n = max(1, int(FETCH_INTERVAL_SECONDS // 60))
    except Exception:
        n = 6
    if n < 1:
        n = 6

    scheduler.add_job(
        background_cycle,
        CronTrigger(minute=f"*/{n}", timezone="Europe/Moscow"),
        id="bg_cycle",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
        replace_existing=True,
    )
    _scheduler_started = True


def scheduler_stop():
    global _scheduler_started
    if not _scheduler_started:
        return
    try:
        scheduler.remove_job("bg_cycle")
    except Exception:
        try:
            scheduler.remove_all_jobs()
        except Exception:
            pass
    _scheduler_started = False


@app.on_event("startup")
async def _startup():
    ensure_db()

    # background loop (runtime start/stop supported)
    if FETCH_ENABLED:
        scheduler_start()


@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "OK"


@app.get("/x/test", response_class=PlainTextResponse)
async def x_test():
    """One-shot fetch test endpoint (does not send alerts, DOES log run row for observability)."""
    xreq, received, passed_kw, stored, stored_ids = await fetch_list_tweets_once()
    _log_run(datetime.utcnow().isoformat()+"Z", xreq, received, passed_kw, stored, 0, 0, 0, 0)
    return f"x_requests={xreq} received={received} passed_keywords={passed_kw} stored={stored}"


@app.post("/admin/debug/tick")
async def admin_debug_tick():
    """Run one background cycle now (for debugging scheduler issues)."""
    try:
        await background_cycle()
        return PlainTextResponse("ok")
    except Exception as e:
        return PlainTextResponse(f"error: {type(e).__name__}: {e}", status_code=500)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse(url="/lineup_ai/select", status_code=307)


def _set_fetch_enabled(value: bool) -> None:
    # Update FETCH_ENABLED= in .env
    env_path = "/home/openclaw/FormAlert/.env"
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []

    out = []
    found = False
    for line in lines:
        if line.startswith("FETCH_ENABLED="):
            out.append(f"FETCH_ENABLED={1 if value else 0}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"FETCH_ENABLED={1 if value else 0}")

    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


@app.post("/admin/fetch/start", response_class=RedirectResponse)
async def admin_fetch_start():
    global FETCH_ENABLED
    _set_fetch_enabled(True)
    FETCH_ENABLED = True
    scheduler_start()
    return RedirectResponse(url="/admin/tweets", status_code=303)


@app.post("/admin/fetch/stop", response_class=RedirectResponse)
async def admin_fetch_stop():
    global FETCH_ENABLED
    _set_fetch_enabled(False)
    FETCH_ENABLED = False
    scheduler_stop()
    return RedirectResponse(url="/admin/tweets", status_code=303)


def _read_keywords_file(path: str) -> list[str]:
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.rstrip("\n")
                if not s.strip() or s.lstrip().startswith("#"):
                    continue
                out.append(s)
    except FileNotFoundError:
        pass
    return out


def _load_modes() -> dict:
    try:
        with open(MODES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _save_modes(obj: dict) -> None:
    with open(MODES_PATH, 'w', encoding='utf-8') as f:
        f.write(json.dumps(obj or {}, ensure_ascii=False, indent=2) + "\n")


def _write_keywords_file(path: str, lines: list[str]) -> None:
    # Normalize: trim, drop empties, unique preserving order
    seen = set()
    cleaned = []
    for s in lines:
        s2 = (s or "").strip()
        if not s2:
            continue
        key = s2.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s2)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(cleaned) + "\n")


@app.get("/admin/keywords", response_class=HTMLResponse)
async def keywords_page():
    inc = _read_keywords_file(KEYWORDS_INCLUDE_PATH)
    bl = _read_keywords_file(KEYWORDS_BLACKLIST_PATH)
    pn = _read_keywords_file(PLAYER_NAMES_PATH)

    inc_txt = html_escape("\n".join(inc))
    bl_txt = html_escape("\n".join(bl))
    pn_txt = html_escape("\n".join(pn))

    nav = _main_nav("/admin/keywords")
    html = f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><link rel="icon" type="image/x-icon" href="/favicon.ico"><link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/site.webmanifest">
    <title>Keywords</title>
    <style>
      body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px;max-width:1200px}}
      textarea{{width:100%;min-height:240px;padding:10px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
      .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
      button{{padding:10px 14px;font-weight:800}}
      .hint{{color:#666;font-size:13px}}
      .topnav{{margin:0 0 14px 0}}
      .topnav a{{display:inline-block;margin-right:10px;padding:6px 10px;border-radius:10px;text-decoration:none;background:#eee;color:#111;font-weight:800}}
      .topnav a.active{{background:#111;color:#fff}}
    </style></head><body>
    {nav}
    <h1>Keywords</h1>
    <p class='hint'>1 строка = 1 слово/фраза. Сохраняется в .txt. Дубликаты удаляются.</p>

    <form method='post' action='/admin/keywords/save'>
      <div class='grid'>
        <div>
          <h3>Keywords (include)</h3>
          <textarea name='include'>{inc_txt}</textarea>
        </div>
        <div>
          <h3>Blacklist</h3>
          <textarea name='blacklist'>{bl_txt}</textarea>
        </div>
      </div>

      <div style='margin-top:14px'>
        <h3>Player names (для поиска на /admin/tweets)</h3>
        <textarea name='player_names'>{pn_txt}</textarea>
        <div class='hint'>Используется для фильтра player=... и/или "показать только твиты где встречаются игроки из списка".</div>
      </div>

      <button type='submit' style='background:#1565c0;color:#fff;border:0;border-radius:6px;margin-top:12px'>Сохранить</button>
    </form>

    </body></html>"""
    return HTMLResponse(html)


@app.post("/admin/keywords/save")
async def keywords_save(include: str = Form(default=""), blacklist: str = Form(default=""), player_names: str = Form(default="")):
    inc_lines = (include or "").splitlines()
    bl_lines = (blacklist or "").splitlines()
    pn_lines = (player_names or "").splitlines()
    _write_keywords_file(KEYWORDS_INCLUDE_PATH, inc_lines)
    _write_keywords_file(KEYWORDS_BLACKLIST_PATH, bl_lines)
    _write_keywords_file(PLAYER_NAMES_PATH, pn_lines)
    return RedirectResponse(url="/admin/keywords", status_code=303)


def _main_nav(active: str = "/admin/") -> str:
    items = [
        ("Форма", "/admin/"),
        ("Runs", "/admin/runs"),
        ("Tweets", "/admin/tweets"),
        ("Teams", "/admin/teams"),
        ("Status", "/admin/status"),
        ("Modes", "/admin/modes"),
        ("Keywords & Blacklist", "/admin/keywords"),
    ]
    links = []
    for name, href in items:
        cls = "active" if active == href else ""
        links.append(f"<a class='{cls}' href='{href}'>{name}</a>")
    return (
        "<div class='topnav'>" + " ".join(links) + "</div>"
    )



@app.get("/admin/", response_class=HTMLResponse)
async def admin_home():
    options = "\n".join([f"<option value='{c}'>{c}</option>" for c in CATEGORIES])
    impacts = "\n".join([f"<option value='{i}'>{i}</option>" for i in IMPACT_LEVELS])
    nav = _main_nav("/admin/")
    html = f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><link rel="icon" type="image/x-icon" href="/favicon.ico"><link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/site.webmanifest">
    <title>FormAlert Admin</title>
    <style>
      body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px;max-width:900px}}
      label{{display:block;margin-top:12px;font-weight:600}}
      input,select,textarea{{width:100%;padding:10px;margin-top:6px}}
      textarea{{min-height:90px}}
      .row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}
      button{{margin-top:16px;padding:12px 16px;font-weight:700}}
      .hint{{color:#666;font-size:13px;margin-top:4px}}
      .topnav{{margin:0 0 14px 0}}
      .topnav a{{display:inline-block;margin-right:10px;padding:6px 10px;border-radius:10px;text-decoration:none;background:#eee;color:#111;font-weight:800}}
      .topnav a.active{{background:#111;color:#fff}}
    </style>
    </head><body>
    {nav}
    <h1>Форма отправки</h1>
    <p class='hint'>Отправляет алерт в Telegram и сохраняет в SQLite.</p>
    <form method="post" action="/admin/send">
      <label>Время (МСК, HH:MM)</label>
      <input name="time_msk" placeholder="18:45" />
      <label>Команда / TEAM</label>
      <input name="team" placeholder="Chelsea" />
      <div class="row">
        <div><label>Категория</label><select name="category">{options}</select></div>
        <div><label>Влияние</label><select name="impact_level">{impacts}</select></div>
        <div><label>Уверенность (0-1)</label><input name="confidence" type="number" step="0.01" min="0" max="1" value="0.60" /></div>
      </div>
      <label>TITLE (рус)</label>
      <input name="title" placeholder="Напр.: Потеря игрока основы перед матчем" />
      <label>DETAILS_1 (рус)</label>
      <textarea name="details1" placeholder="Коротко по факту"></textarea>
      <label>DETAILS_2 (рус)</label>
      <textarea name="details2" placeholder="Уточнение (статус, матч, сроки)"></textarea>
      <label>DETAILS_3 (опц.)</label>
      <textarea name="details3" placeholder="Доп. деталь (если надо)"></textarea>
      <label>ORIGINAL_TEXT (как в твите, без правок)</label>
      <textarea name="original_text" placeholder="Вставь текст твита 1:1" required></textarea>
      <label>ORIGINAL_LINK</label>
      <input name="original_link" placeholder="https://x.com/..." required />
      <button type="submit">Отправить</button>
    </form>
    </body></html>"""
    return HTMLResponse(html)


@app.get("/admin/status", response_class=HTMLResponse)
async def admin_status():
    # Best-effort scheduler introspection
    try:
        job = scheduler.get_job("bg_cycle")
        next_run = str(job.next_run_time) if job else "None"
    except Exception:
        next_run = "ERR"

    body = (
        f"FETCH_ENABLED={int(FETCH_ENABLED)}\n"
        f"FETCH_INTERVAL_SECONDS={FETCH_INTERVAL_SECONDS}\n"
        f"X_LIST_ID={X_LIST_ID}\n"
        f"GATE_ENABLED={int(GATE_ENABLED)}\n"
        f"GATE_MODEL={GATE_MODEL}\n"
        f"SCHEDULER_RUNNING={int(bool(getattr(scheduler, 'running', False)))}\n"
        f"SCHEDULER_STARTED_FLAG={int(bool(_scheduler_started))}\n"
        f"JOB_NEXT_RUN={next_run}\n"
    )

    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><link rel="icon" type="image/x-icon" href="/favicon.ico"><link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/site.webmanifest">
    <title>Status</title>
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px;max-width:1200px}
      pre{background:#111;color:#eaeaea;padding:14px;border-radius:10px;overflow:auto}
      .topnav{margin:0 0 14px 0}
      .topnav a{display:inline-block;margin-right:10px;padding:6px 10px;border-radius:10px;text-decoration:none;background:#eee;color:#111;font-weight:800}
      .topnav a.active{background:#111;color:#fff}
    </style></head><body>
    """ + _main_nav("/admin/status") + """
    <h1>Status</h1>
    <pre>""" + html_escape(body) + """</pre>
    </body></html>"""
    return HTMLResponse(html)


@app.get("/admin/modes", response_class=HTMLResponse)
async def admin_modes():
    modes = _load_modes() or {}
    txt = json.dumps(modes, ensure_ascii=False, indent=2)
    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><link rel="icon" type="image/x-icon" href="/favicon.ico"><link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/site.webmanifest">
    <title>Modes</title>
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px;max-width:1200px}
      textarea{width:100%;min-height:520px;padding:10px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
      button{padding:10px 14px;font-weight:900;border-radius:10px;border:0}
      .topnav{margin:0 0 14px 0}
      .topnav a{display:inline-block;margin-right:10px;padding:6px 10px;border-radius:10px;text-decoration:none;background:#eee;color:#111;font-weight:800}
      .topnav a.active{background:#111;color:#fff}
      .hint{color:#666;font-size:13px;margin:8px 0}
    </style></head><body>
    """ + _main_nav("/admin/modes") + """
    <h1>Modes</h1>
    <div class='hint'>Режимы хранятся в <code>modes.json</code>. Можно редактировать JSON и сохранять.</div>

    <form method='post' action='/admin/modes/save'>
      <textarea name='modes_json'>""" + html_escape(txt) + """</textarea>
      <div style='margin-top:10px'>
        <button type='submit' style='background:#1565c0;color:#fff'>Save</button>
      </div>
    </form>
    </body></html>"""
    return HTMLResponse(html)


@app.post("/admin/modes/save")
async def admin_modes_save(modes_json: str = Form(default="")):
    try:
        obj = json.loads(modes_json or "{}")
    except Exception:
        return PlainTextResponse("invalid json", status_code=400)
    _save_modes(obj)
    return RedirectResponse(url="/admin/modes", status_code=303)


@app.post("/admin/debug/send")
async def admin_debug_send(tweet_id: str = Form(default="")):
    """Force-send a single tweet by id to reproduce Telegram errors.

    - Loads stored tweet from DB
    - Runs llm_classify
    - Attempts to send to Telegram
    Returns plain text status.
    """
    tid = (tweet_id or "").strip()
    if not tid:
        return PlainTextResponse("missing tweet_id", status_code=400)

    row = _db_one("SELECT text, url, COALESCE(source_username,'') FROM tweets WHERE tweet_id=?", (tid,))
    if not row:
        return PlainTextResponse("tweet not found", status_code=404)

    text, url, src = row
    try:
        cls = await llm_classify(text or "", url or "", src or "")
        msg = cls.get("formatted_signal") or ""
        mid = await send_telegram(msg)
        return PlainTextResponse(f"ok sent message_id={mid}")
    except Exception as e:
        return PlainTextResponse(f"error: {type(e).__name__}: {e}", status_code=500)


@app.get("/admin/teams", response_class=HTMLResponse)
async def admin_teams(sort: str = "source", dir: str = "asc"):
    ensure_db()

    sort = (sort or "source").lower()
    dir = (dir or "asc").lower()
    if sort not in ("id", "source", "team"):
        sort = "source"
    if dir not in ("asc", "desc"):
        dir = "asc"

    order_sql = f"{sort} {dir.upper()}"

    con = sqlite3.connect(DB_PATH)
    rows = con.execute(f"SELECT id, source, team FROM teams_map ORDER BY {order_sql}").fetchall()
    con.close()

    def esc(x: str) -> str:
        return html_escape(x)

    trs = []
    for rid, source, team in rows:
        trs.append(
            "<tr>"
            f"<td>{rid}</td>"
            f"<td>{esc(source)}</td>"
            f"<td>{esc(team)}</td>"
            f"<td>\n"
            f"  <form method='post' action='/admin/teams/delete' style='margin:0'>\n"
            f"    <input type='hidden' name='id' value='{rid}'/>\n"
            f"    <button type='submit' style='padding:6px 10px;background:#c62828;color:#fff;border:0;border-radius:6px'>Delete</button>\n"
            f"  </form>\n"
            f"</td>"
            "</tr>"
        )

    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><link rel="icon" type="image/x-icon" href="/favicon.ico"><link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/site.webmanifest">
    <title>Teams Map</title>
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px;max-width:1100px}
      table{border-collapse:collapse;width:100%}
      th,td{border:1px solid #ddd;padding:8px;font-size:13px;vertical-align:top}
      th{background:#f6f6f6;text-align:left}
      input{padding:8px;width:100%}
    </style></head><body>
    """ + _main_nav("/admin/teams") + """
    <h1>Teams</h1>

    <h3>Добавить / обновить</h3>
    <form method='post' action='/admin/teams/upsert'>
      <label>Source (например: @SB29 или username)</label><br/>
      <input name='source' placeholder='@SB29' required/><br/><br/>
      <label>Team</label><br/>
      <input name='team' placeholder='Brest' required/><br/><br/>
      <button type='submit' style='padding:8px 12px;font-weight:700;background:#1565c0;color:#fff;border:0;border-radius:6px'>Save</button>
    </form>

    <h3>Таблица соответствий</h3>
    <table><thead><tr>
      <th><a href='/admin/teams?sort=id&dir=""" + ("desc" if sort=="id" and dir=="asc" else "asc") + """'>ID</a></th>
      <th><a href='/admin/teams?sort=source&dir=""" + ("desc" if sort=="source" and dir=="asc" else "asc") + """'>Source</a></th>
      <th><a href='/admin/teams?sort=team&dir=""" + ("desc" if sort=="team" and dir=="asc" else "asc") + """'>Team</a></th>
      <th>Actions</th>
    </tr></thead><tbody>
    """ + "\n".join(trs) + """
    </tbody></table>
    </body></html>"""
    return HTMLResponse(html)


@app.post("/admin/teams/upsert")
async def admin_teams_upsert(source: str = Form(...), team: str = Form(...)):
    ensure_db()
    source = source.strip()
    team = team.strip()
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO teams_map(source, team) VALUES(?,?) ON CONFLICT(source) DO UPDATE SET team=excluded.team",
        (source, team),
    )
    con.commit(); con.close()
    return RedirectResponse(url="/admin/teams", status_code=303)


@app.post("/admin/teams/delete")
async def admin_teams_delete(id: int = Form(...)):
    ensure_db()
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM teams_map WHERE id=?", (int(id),))
    con.commit(); con.close()
    return RedirectResponse(url="/admin/teams", status_code=303)


@app.get("/admin/runs", response_class=HTMLResponse)
async def admin_runs(limit: int = 50, date_from: str = "", date_to: str = "", time_from: str = "00:00", time_to: str = "23:59"):
    """Show sum of 'Новых в БД' for an MSK date range and time-of-day window."""
    ensure_db()

    def fmt_msk(iso_z: str) -> str:
        try:
            s = (iso_z or "").replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            from datetime import timedelta
            dt_msk = dt + timedelta(hours=3)
            return dt_msk.strftime("%d.%m.%Y — %H:%M")
        except Exception:
            return iso_z or ""

    def to_msk_dt(iso_z: str):
        try:
            s = (iso_z or "").replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            from datetime import timedelta
            dt_msk = dt + timedelta(hours=3)
            return dt_msk.strftime("%Y-%m-%d"), dt_msk.strftime("%H:%M")
        except Exception:
            return "", ""

    date_from = (date_from or "").strip()
    date_to = (date_to or "").strip()
    time_from = (time_from or "00:00").strip()
    time_to = (time_to or "23:59").strip()

    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT id, created_at, x_requests, received, passed_keywords, stored, llm_gate_calls, llm_core_calls, relevant, sent FROM runs ORDER BY id DESC LIMIT 5000"
    ).fetchall()
    con.close()

    # Filter and sum
    total_new_db = 0
    filtered = []
    if date_from and date_to:
        for r in rows:
            rid, created_at, xreq, received, passed_kw, stored, gate_calls, core_calls, relevant, sent = r
            d, tm = to_msk_dt(created_at)
            if not d:
                continue
            if d < date_from or d > date_to:
                continue
            if tm < time_from or tm > time_to:
                continue
            total_new_db += int(stored or 0)
            filtered.append(r)
    else:
        filtered = rows[: min(int(limit), 200)]
        total_new_db = sum(int(r[5] or 0) for r in filtered)

    # Optional table (keep for sanity)
    trs = []
    for r in filtered[: min(len(filtered), 200)]:
        (rid, created_at, xreq, received, passed_kw, stored, gate_calls, core_calls, relevant, sent) = r
        trs.append(
            f"<tr><td>{rid}</td><td>{fmt_msk(created_at)}</td><td>{xreq}</td><td>{received}</td><td>{stored}</td><td>{passed_kw}</td><td>{gate_calls}</td><td>{core_calls}</td><td>{relevant}</td><td>{sent}</td></tr>"
        )

    # Today cost widget (MSK 00:00-00:00)
    from datetime import timedelta
    now_msk = datetime.utcnow() + timedelta(hours=3)
    today = now_msk.strftime('%Y-%m-%d')
    day_start_iso, day_end_iso = None, None
    try:
        y,m,d = [int(x) for x in today.split('-')]
        start_msk = datetime(y,m,d,0,0)
        end_msk = start_msk + timedelta(days=1)
        start_utc = start_msk - timedelta(hours=3)
        end_utc = end_msk - timedelta(hours=3)
        day_start_iso = start_utc.strftime('%Y-%m-%dT%H:%M:%S')
        day_end_iso = end_utc.strftime('%Y-%m-%dT%H:%M:%S')
    except Exception:
        day_start_iso, day_end_iso = ('1970-01-01T00:00:00','2999-12-31T23:59:59')

    # compute totals from runs table
    con = sqlite3.connect(DB_PATH)
    rsum = con.execute(
        "SELECT COALESCE(SUM(x_requests),0), COALESCE(SUM(stored),0) FROM runs WHERE created_at >= ? AND created_at < ?",
        (day_start_iso, day_end_iso),
    ).fetchone()
    con.close()
    day_requests = int(rsum[0] or 0)
    day_posts = int(rsum[1] or 0)
    cost_req = day_requests * 0.005
    cost_posts = day_posts * 0.005

    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><link rel="icon" type="image/x-icon" href="/favicon.ico"><link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/site.webmanifest">
    <title>Runs</title>
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px}
      .layout{display:grid;grid-template-columns: 1fr 360px;gap:16px;align-items:start}
      table{border-collapse:collapse;width:100%}
      th,td{border:1px solid #ddd;padding:8px;font-size:13px}
      th{background:#f6f6f6;text-align:left}
      input{padding:8px}
      .card{border:1px solid #ddd;border-radius:10px;padding:12px;background:#fff}
      .muted{color:#666;font-size:12px}
      .big{font-size:20px;font-weight:900}
    </style></head><body>
<div class='layout'>
<div>
    """ + _main_nav("/admin/runs") + """
    <h1>Runs</h1>

    <h3>Сумма «Новых в БД» за период</h3>
    <form method='get' action='/admin/runs' style='margin:12px 0'>
      <label>Дата с (МСК):</label>
      <input type='date' name='date_from' value='""" + date_from + """' required />
      <label>по:</label>
      <input type='date' name='date_to' value='""" + date_to + """' required />
      <br/><br/>
      <label>Время с (МСК):</label>
      <input type='time' name='time_from' value='""" + time_from + """' required />
      <label>по:</label>
      <input type='time' name='time_to' value='""" + time_to + """' required />
      <button type='submit' style='padding:8px 12px;font-weight:700;margin-left:10px'>Посчитать</button>
      <a href='/admin/runs' style='margin-left:10px'>Сброс</a>
    </form>

    <div style='font-size:22px;font-weight:800;margin:10px 0'>Итого новых твитов в БД: """ + str(total_new_db) + """</div>

    <table><thead><tr>
      <th>id</th><th>Время (МСК)</th><th>Запрос</th><th>Получено постов</th><th>Новые</th><th>Прошло фильтр</th><th>Прошло Gate</th><th>Прошло LLM</th><th>Подходящие</th><th>Отправлено</th>
    </tr></thead><tbody>
    """ + "\n".join(trs) + """
    </tbody></table>
</div>

<div class='card'>
  <h3 style='margin:0 0 8px 0'>Траты за сегодня (МСК 00:00–00:00)</h3>
  <div class='muted' style='margin-bottom:8px'>Расчёт: $0.005 за запрос + $0.005 за «Новых в БД»</div>

  <div style='margin-bottom:10px'>
    <div><b>Запросов:</b> """ + str(day_requests) + """</div>
    <div><b>Стоимость запросов:</b> $""" + f"{cost_req:.3f}" + """</div>
  </div>

  <div style='margin-bottom:10px'>
    <div><b>Плата за посты (Новых в БД):</b> """ + str(day_posts) + """</div>
    <div><b>Стоимость постов:</b> $""" + f"{cost_posts:.3f}" + """</div>
  </div>

  <div class='big'>Итого: $""" + f"{(cost_req+cost_posts):.3f}" + """</div>
</div>
</div>
    </body></html>"""
    return HTMLResponse(html)


@app.get("/admin/tweets", response_class=HTMLResponse)
async def admin_tweets(limit: int = 100, tweet_id: str = "", kw: str = "", player: str = "", only_players: int = 0, src_sort: str = "rel", src_dir: str = "desc"):
    ensure_db()
    tweet_id = (tweet_id or "").strip()
    kw = (kw or "").strip()
    player = (player or "").strip()
    only_players = 1 if str(only_players).strip() in ("1","true","yes","on") else 0
    src_sort = (src_sort or "rel").strip().lower()
    src_dir = (src_dir or "desc").strip().lower()
    if src_sort not in ("source", "total", "kw", "rel", "pct"):
        src_sort = "rel"
    if src_dir not in ("asc", "desc"):
        src_dir = "desc"

    # MSK day window (today) 00:00–00:00
    from datetime import timedelta
    now_msk = datetime.utcnow() + timedelta(hours=3)
    y, m, d = now_msk.year, now_msk.month, now_msk.day
    start_msk = datetime(y, m, d, 0, 0)
    end_msk = start_msk + timedelta(days=1)
    start_utc = start_msk - timedelta(hours=3)
    end_utc = end_msk - timedelta(hours=3)
    start_iso = start_utc.strftime('%Y-%m-%dT%H:%M:%S')
    end_iso = end_utc.strftime('%Y-%m-%dT%H:%M:%S')

    con = sqlite3.connect(DB_PATH)

    # Right-side Source stats for today (MSK 00:00-00:00)
    _src_rows = con.execute(
        """
        SELECT
          t.source_username,
          COUNT(*) AS total,
          SUM(CASE WHEN t.kw_pass=1 THEN 1 ELSE 0 END) AS kw_cnt,
          SUM(CASE WHEN s.relevant=1 THEN 1 ELSE 0 END) AS rel_cnt
        FROM tweets t
        LEFT JOIN tweet_status s ON s.tweet_id = t.tweet_id
        WHERE t.source_username IS NOT NULL AND t.source_username != ''
          AND t.created_at >= ? AND t.created_at < ?
        GROUP BY t.source_username
        """,
        (start_iso, end_iso),
    ).fetchall()

    # compute pct and sort
    src_rows = []
    for src, total, kwc, relc in _src_rows:
        total_i = int(total or 0)
        rel_i = int(relc or 0)
        pct = 0.0 if total_i == 0 else (rel_i * 100.0 / total_i)
        src_rows.append((src, total_i, int(kwc or 0), rel_i, pct))

    def _key(row):
        src, total, kwc, relc, pct = row
        if src_sort == "source":
            return (src or "")
        if src_sort == "total":
            return total
        if src_sort == "kw":
            return kwc
        if src_sort == "rel":
            return relc
        return pct

    reverse = True if src_dir == "desc" else False
    src_rows.sort(key=_key, reverse=reverse)
    src_rows = src_rows[:100]

    # Top keywords stats (from include list) over recent tweets
    include_list = _load_phrases(KEYWORDS_INCLUDE_PATH)
    top = []
    if include_list:
        recent = con.execute("SELECT text FROM tweets ORDER BY tweet_id DESC LIMIT 1000").fetchall()
        counts = {k: 0 for k in include_list}
        for (txt,) in recent:
            # count individual keyword hits
            if MATCH_MODE == "exact":
                words = _tokenize_words(txt or "")
                for k in include_list:
                    if _phrase_match_exact(words, k):
                        counts[k] += 1
            else:
                t_low = (txt or "").lower()
                for k in include_list:
                    if k and k in t_low:
                        counts[k] += 1
        top = sorted([(k, v) for k, v in counts.items() if v > 0], key=lambda x: (-x[1], x[0]))[:20]

    def _kw_match_text(txt: str, keyword: str) -> bool:
        if not keyword:
            return True
        if MATCH_MODE == "exact":
            return _phrase_match_exact(_tokenize_words(txt or ""), keyword.lower())
        return keyword.lower() in (txt or "").lower()

    def _player_match_text(txt: str, needle: str) -> bool:
        if not needle:
            return True
        t = (txt or "")
        # simple case-insensitive substring match is good for names
        return needle.lower() in t.lower()

    if tweet_id:
        rows = con.execute(
            """
            SELECT t.tweet_id, t.created_at, t.source_username, t.url, t.text,
                   t.kw_pass, t.kw_blacklist_hit,
                   s.classified_at, s.relevant, s.sent_at, s.gate_decision, s.image_mode, s.core_json_valid, s.core_error, s.duplicate_of
            FROM tweets t
            LEFT JOIN tweet_status s ON s.tweet_id = t.tweet_id
            WHERE t.tweet_id = ?
            LIMIT 1
            """,
            (tweet_id,),
        ).fetchall()
    else:
        base = con.execute(
            """
            SELECT t.tweet_id, t.created_at, t.source_username, t.url, t.text,
                   t.kw_pass, t.kw_blacklist_hit,
                   s.classified_at, s.relevant, s.sent_at, s.gate_decision, s.image_mode, s.core_json_valid, s.core_error, s.duplicate_of
            FROM tweets t
            LEFT JOIN tweet_status s ON s.tweet_id = t.tweet_id
            ORDER BY t.tweet_id DESC
            LIMIT 1000
            """
        ).fetchall()
        rows = base
        if kw:
            rows = [r for r in rows if _kw_match_text(r[4], kw)]
        if player:
            rows = [r for r in rows if _player_match_text(r[4], player)]
        if only_players:
            plist = _read_keywords_file(PLAYER_NAMES_PATH)
            if plist:
                rows = [r for r in rows if any(_player_match_text(r[4], nm) for nm in plist)]
        rows = rows[: min(int(limit), 300)]
    con.close()

    def esc(x: str) -> str:
        return (x or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    include_phrases = _load_phrases(KEYWORDS_INCLUDE_PATH)
    blacklist_phrases = _load_phrases(KEYWORDS_BLACKLIST_PATH)
    player_phrases = _load_phrases(PLAYER_NAMES_PATH)

    def highlight(text: str) -> str:
        src = text or ""

        if MATCH_MODE != "exact":
            # legacy substring highlighter
            lower = src.lower()
            spans = []  # (start,end,cls)

            def add_spans(phrases, cls):
                for ph in phrases:
                    if not ph:
                        continue
                    start = 0
                    while True:
                        i = lower.find(ph, start)
                        if i == -1:
                            break
                        spans.append((i, i + len(ph), cls))
                        start = i + len(ph)

            add_spans(blacklist_phrases, "bl")
            add_spans(include_phrases, "inc")
            add_spans(player_phrases, "pl")

            if not spans:
                return esc(src)

            spans.sort(key=lambda x: (x[0], -(x[1]-x[0])))
            merged = []
            for s, e, cls in spans:
                if not merged:
                    merged.append([s, e, cls])
                    continue
                ps, pe, pcls = merged[-1]
                if s >= pe:
                    merged.append([s, e, cls])
                else:
                    merged[-1][1] = max(pe, e)
                    if pcls != "bl" and cls == "bl":
                        merged[-1][2] = "bl"

            out = []
            idx = 0
            for s, e, cls in merged:
                if s > idx:
                    out.append(esc(src[idx:s]))
                chunk = esc(src[s:e])
                out.append(f"<span class='kw {cls}'>{chunk}</span>")
                idx = e
            if idx < len(src):
                out.append(esc(src[idx:]))
            return "".join(out)

        # exact mode highlighter: tokenize with positions and match word/phrase boundaries
        lower = src.lower()
        tokens = []  # (word, start, end)
        i = 0
        n = len(src)
        while i < n:
            ch = src[i]
            if ch.isalnum() or ch in ("'", "’"):
                start = i
                j = i
                while j < n and (src[j].isalnum() or src[j] in ("'", "’")):
                    j += 1
                word = lower[start:j]
                tokens.append((word, start, j))
                i = j
            else:
                i += 1

        word_list = [w for (w, _, _) in tokens]

        def phrase_to_words(ph: str) -> list[str]:
            return _tokenize_words(ph)

        spans = []  # (start,end,cls)

        def add_phrase_spans(phrases, cls):
            for ph in phrases:
                ph_words = phrase_to_words(ph)
                if not ph_words:
                    continue
                L = len(ph_words)
                for k in range(0, max(0, len(word_list) - L + 1)):
                    if word_list[k : k + L] == ph_words:
                        s = tokens[k][1]
                        e = tokens[k + L - 1][2]
                        spans.append((s, e, cls))

        add_phrase_spans(blacklist_phrases, "bl")
        add_phrase_spans(include_phrases, "inc")
        add_phrase_spans(player_phrases, "pl")

        if not spans:
            return esc(src)

        spans.sort(key=lambda x: (x[0], -(x[1]-x[0])))
        merged = []
        for s, e, cls in spans:
            if not merged:
                merged.append([s, e, cls])
                continue
            ps, pe, pcls = merged[-1]
            if s >= pe:
                merged.append([s, e, cls])
            else:
                merged[-1][1] = max(pe, e)
                if pcls != "bl" and cls == "bl":
                    merged[-1][2] = "bl"

        out = []
        idx = 0
        for s, e, cls in merged:
            if s > idx:
                out.append(esc(src[idx:s]))
            chunk = esc(src[s:e])
            out.append(f"<span class='kw {cls}'>{chunk}</span>")
            idx = e
        if idx < len(src):
            out.append(esc(src[idx:]))
        return "".join(out)

    trs = []
    def fmt_dt(dt_str: str) -> str:
        try:
            if not dt_str:
                return ""
            # X created_at is usually UTC, like 2026-04-27T08:24:50.000Z
            s = dt_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            # MSK = UTC+3
            from datetime import timedelta
            dt_msk = dt + timedelta(hours=3)
            return dt_msk.strftime("%d.%m.%Y — %H:%M")
        except Exception:
            return (dt_str or "")[:16].replace("T", " — ")

    for (tid, created_at, source_username, url, text, kw_pass, kw_blacklist_hit, classified_at, relevant, sent_at, gate_decision, image_mode, core_json_valid, core_error, duplicate_of) in rows:
        trs.append(
            "<tr>"
            f"<td style='white-space:nowrap'><a target='_blank' href='{esc(url)}'>{esc(tid)}</a></td>"
            f"<td style='white-space:nowrap'>{esc(fmt_dt(created_at))}</td>"
            f"<td style='white-space:nowrap'>{esc(source_username or '')}</td>"
            f"<td>{highlight(text)[:2000]}</td>"
            f"<td style='white-space:nowrap'>{'' if kw_pass is None else int(kw_pass)}</td>"
            f"<td style='white-space:nowrap'>{'' if kw_blacklist_hit is None else int(kw_blacklist_hit)}</td>"
            f"<td style='white-space:nowrap'>{esc(fmt_dt(classified_at))}</td>"
            f"<td style='white-space:nowrap'>{'' if relevant is None else int(relevant)}</td>"
            f"<td style='white-space:nowrap'>{esc(gate_decision or '')}</td>"
            f"<td style='white-space:nowrap'>{'double' if duplicate_of else 'OK'}</td>"
            f"<td style='white-space:nowrap'>{esc(image_mode or '')}</td>"
            f"<td style='white-space:nowrap'>{'' if core_json_valid is None else int(core_json_valid)}</td>"
            f"<td>{esc(core_error or '')}</td>"
            f"<td style='white-space:nowrap'>{esc(fmt_dt(sent_at))}</td>"
            "</tr>"
        )

    # Build sortable Source table links safely (no nested f-strings in HTML string)
    base_qs = ""
    if tweet_id:
        base_qs += "tweet_id=" + urllib.parse.quote(tweet_id) + "&"
    if kw:
        base_qs += "kw=" + urllib.parse.quote(kw) + "&"

    def next_dir(col: str) -> str:
        return "desc" if (src_sort == col and src_dir == "asc") else "asc"

    src_hdr = {
        "source": f"/admin/tweets?{base_qs}src_sort=source&src_dir={next_dir('source')}",
        "total": f"/admin/tweets?{base_qs}src_sort=total&src_dir={next_dir('total')}",
        "kw": f"/admin/tweets?{base_qs}src_sort=kw&src_dir={next_dir('kw')}",
        "rel": f"/admin/tweets?{base_qs}src_sort=rel&src_dir={next_dir('rel')}",
        "pct": f"/admin/tweets?{base_qs}src_sort=pct&src_dir={next_dir('pct')}",
    }

    src_table_rows = "\n".join([
        f"<tr><td>{esc(src or '')}</td><td>{total}</td><td>{kwc}</td><td>{relc}</td><td>{round(pct,1)}%</td></tr>"
        for (src, total, kwc, relc, pct) in src_rows
    ])

    # Source table HTML moved below main table to free horizontal space
    src_table_html = (
        "<tr>"
        f"<th><a href='{src_hdr['source']}'>Source</a></th>"
        f"<th><a href='{src_hdr['total']}'>Total</a></th>"
        f"<th><a href='{src_hdr['kw']}'>KW</a></th>"
        f"<th><a href='{src_hdr['rel']}'>Relevant</a></th>"
        f"<th><a href='{src_hdr['pct']}'>%</a></th>"
        "</tr>"
    )

    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><link rel="icon" type="image/x-icon" href="/favicon.ico"><link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/site.webmanifest">
    <title>Tweets</title>
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px}
      .layout{display:grid;grid-template-columns: 1fr 420px;gap:16px;align-items:start}
      table{border-collapse:collapse;width:100%}
      th,td{border:1px solid #ddd;padding:8px;font-size:13px;vertical-align:top}
      th{background:#f6f6f6;text-align:left;position:relative}
      .card{border:1px solid #ddd;border-radius:10px;padding:12px;background:#fff}
      .muted{color:#666;font-size:12px}

      /* keyword highlighting */
      .kw{font-weight:900;padding:2px 4px;border-radius:4px;line-height:1.4}
      .kw.inc{background:#d9fdd3;color:#0b3d0b;border:1px solid #2e7d32}
      .kw.bl{background:#ffd6d6;color:#5a0000;border:1px solid #c62828}
      .kw.pl{background:#dbeafe;color:#0b2a5a;border:1px solid #1e40af}
    </style></head><body>

<div class='layout'>
<div>
    """ + _main_nav("/admin/tweets") + """
    <h1>Tweets</h1>
    <form method='get' action='/admin/tweets' style='margin:12px 0'>
      <input name='tweet_id' placeholder='Поиск по tweet_id' value='""" + esc(tweet_id) + """' style='padding:8px;width:220px;max-width:100%' />
      <input name='kw' placeholder='Keyword' value='""" + esc(kw) + """' style='padding:8px;width:180px;max-width:100%' />
      <input name='player' placeholder='Player (поиск по имени)' value='""" + esc(player) + """' style='padding:8px;width:220px;max-width:100%' />
      <label style='margin-left:8px;white-space:nowrap'><input type='checkbox' name='only_players' value='1' """ + ("checked" if only_players else "") + """/> only players list</label>
      <button type='submit' style='padding:8px 12px;font-weight:700'>Search</button>
      <a href='/admin/tweets' style='margin-left:10px'>Reset</a>
      <a href='/admin/keywords' style='margin-left:10px'>Keywords</a>
    </form>

    <div style='margin:10px 0'>
      <b>Top keywords</b>:
      """ + (" ".join([
        (f"<a href='/admin/tweets" + ("" if kw==k else f"?kw={urllib.parse.quote(k)}") + "' style='display:inline-block;margin:4px 8px 4px 0;padding:4px 8px;border-radius:10px;" + ("background:#222;color:#fff" if kw==k else "background:#eee;color:#111") + "'>" + esc(k) + f" <span style='opacity:.7'>({v})</span></a>")
        for (k,v) in top
      ]) if top else "<span style='color:#666'>нет данных</span>") + """
    </div>
    <form method='post' action='/admin/fetch/start' style='display:inline-block;margin-right:8px'>
      <button type='submit' style='padding:8px 12px;font-weight:700;background:#2e7d32;color:#fff;border:0;border-radius:6px'>Start</button>
    </form>
    <form method='post' action='/admin/fetch/stop' style='display:inline-block;margin-right:8px'>
      <button type='submit' style='padding:8px 12px;font-weight:700;background:#c62828;color:#fff;border:0;border-radius:6px'>Stop</button>
    </form>
    <form method='post' action='/admin/run_now' style='display:inline-block;margin-right:8px'>
      <button type='submit' style='padding:8px 12px;font-weight:700;background:#1565c0;color:#fff;border:0;border-radius:6px'>Run now</button>
    </form>

    <div class='card' style='margin:12px 0'>
      <h3 style='margin:0 0 8px 0'>Ночной режим (выключает только X‑запросы, МСК)</h3>
      <form method='post' action='/admin/quiet_hours/save'>
        <label><input type='checkbox' name='enabled' value='1' """ + ("checked" if QUIET_HOURS_ENABLED else "") + """/> Включить</label><br/><br/>
        <label>С</label> <input type='time' name='from_hhmm' value='""" + html_escape(QUIET_HOURS_FROM) + """' />
        <label>По</label> <input type='time' name='to_hhmm' value='""" + html_escape(QUIET_HOURS_TO) + """' />
        <button type='submit' style='margin-left:10px;padding:8px 12px;font-weight:800;background:#1565c0;color:#fff;border:0;border-radius:6px'>Сохранить</button>
      </form>
      <div class='muted' style='margin-top:6px'>Если С=По, режим считается выключенным.</div>
    </div>

    <table><thead><tr>
      <th>tweet_id</th><th>created_at</th><th>Source</th><th>text</th><th>Keywords</th><th>Blacklist</th><th>Обработан (AI)</th><th>Релевантный</th><th>Gate (AI-проверка)</th><th>Double</th><th>Image</th><th>JSON корректный (1/0)</th><th>Ошибка AI</th><th>Отправлен</th>
    </tr></thead><tbody>
    """ + "\n".join(trs) + """
    </tbody></table>
</div>

<div>
<div class='card'>
  <h3 style='margin:0 0 8px 0'>Source (сегодня, МСК 00:00–00:00)</h3>
  <div class='muted' style='margin-bottom:8px'>total = твитов, kw = Keywords=1, rel = релевантные, % = rel/total</div>
  <table><thead><tr>
    <th><a href='""" + src_hdr["source"] + """'>Source</a></th>
    <th><a href='""" + src_hdr["total"] + """'>total</a></th>
    <th><a href='""" + src_hdr["kw"] + """'>kw</a></th>
    <th><a href='""" + src_hdr["rel"] + """'>rel</a></th>
    <th><a href='""" + src_hdr["pct"] + """'>%</a></th>
  </tr></thead><tbody>
  """ + src_table_rows + """
  </tbody></table>
</div>
</div>
</div>
    </body></html>"""
    return HTMLResponse(html)


@app.post("/admin/run_now", response_class=RedirectResponse)
async def admin_run_now():
    await background_cycle()
    return RedirectResponse(url="/admin/runs", status_code=303)


def _set_env_kv(key: str, value: str) -> None:
    env_path = "/home/openclaw/FormAlert/.env"
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []

    out = []
    found = False
    for line in lines:
        if line.startswith(key + "="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")

    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


@app.post("/admin/quiet_hours/save")
async def admin_quiet_hours_save(enabled: str = Form(default=""), from_hhmm: str = Form(default="00:00"), to_hhmm: str = Form(default="00:00")):
    global QUIET_HOURS_ENABLED, QUIET_HOURS_FROM, QUIET_HOURS_TO
    QUIET_HOURS_ENABLED = bool(enabled)
    QUIET_HOURS_FROM = (from_hhmm or "00:00").strip()
    QUIET_HOURS_TO = (to_hhmm or "00:00").strip()

    _set_env_kv("QUIET_HOURS_ENABLED", "1" if QUIET_HOURS_ENABLED else "0")
    _set_env_kv("QUIET_HOURS_FROM", QUIET_HOURS_FROM)
    _set_env_kv("QUIET_HOURS_TO", QUIET_HOURS_TO)

    return RedirectResponse(url="/admin/tweets", status_code=303)


@app.post("/admin/reclassify_one", response_class=PlainTextResponse)
async def admin_reclassify_one(tweet_id: str):
    """Force re-classification of a single tweet_id (overrides previous status)."""
    ensure_db()
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT tweet_id, text, url FROM tweets WHERE tweet_id=?", (tweet_id,)).fetchone()
    con.close()
    if not row:
        return "NOT_FOUND"

    tid, text, url = row

    # reset status
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM tweet_status WHERE tweet_id=?", (tid,))
    con.commit(); con.close()

    gate_calls, core_calls, relevant, sent = await classify_and_alert_new_tweets(limit=1, only_ids=[tid])
    return f"tweet_id={tid} gate_calls={gate_calls} core_calls={core_calls} relevant={relevant} sent={sent}"


@app.post("/admin/send")
async def send(
    time_msk: str = Form(default=""),
    team: str = Form(default=""),
    category: str = Form(default="other"),
    impact_level: str = Form(default="MEDIUM"),
    confidence: float = Form(default=0.6),
    title: str = Form(default=""),
    details1: str = Form(default=""),
    details2: str = Form(default=""),
    details3: str = Form(default=""),
    original_text: str = Form(...),
    original_link: str = Form(...),
):
    ensure_db()

    if category not in CATEGORIES:
        category = "other"
    if impact_level not in IMPACT_LEVELS:
        impact_level = "MEDIUM"

    time_msk = (time_msk or "").strip() or datetime.now(timezone.utc).astimezone(timezone.utc).strftime("%H:%M")

    msg = build_signal(
        time_msk=time_msk,
        team=team,
        category=category,
        impact_level=impact_level,
        confidence=float(confidence),
        title=title,
        details1=details1,
        details2=details2,
        details3=details3,
        original_text=original_text,
        original_link=original_link,
    )

    telegram_message_id = None
    try:
        telegram_message_id = await send_telegram(msg)
    except Exception:
        telegram_message_id = None

    con = sqlite3.connect(DB_PATH)
    con.execute(
        """INSERT INTO alerts(created_at, team, category, impact_level, confidence, title, details1, details2, details3, original_text, original_link, telegram_message_id)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            datetime.utcnow().isoformat() + "Z",
            team,
            category,
            impact_level,
            float(confidence),
            title,
            details1,
            details2,
            details3,
            original_text,
            original_link,
            telegram_message_id,
        ),
    )
    con.commit()
    con.close()

    return RedirectResponse(url="/admin/", status_code=303)


# =====================================================================
# USER MANAGEMENT ADMIN
# =====================================================================

_MSK = timezone(timedelta(hours=3))

def _fmt_msk(iso_str):
    if not iso_str:
        return "–"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(_MSK).strftime("%d.%m.%y %H:%M")
    except Exception:
        return iso_str[:16] if len(iso_str) >= 16 else iso_str

# Flash store: key -> (msg_html, expires_at)
_flash: dict[str, tuple[str, float]] = {}

def _flash_set(msg: str) -> str:
    k = secrets.token_hex(8)
    _flash[k] = (msg, time.time() + 120)
    return k

def _flash_get(k: str) -> str:
    if k in _flash:
        m, _ = _flash.pop(k)
        return m
    return ""

def _flash_clean():
    now = time.time()
    for k in [k for k, (_, e) in _flash.items() if now > e]:
        del _flash[k]


def _render_admin(msg: str = "", page: int = 1, page_size: int = 50,
                user_filter: str = "", ip_filter: str = "", action_filter: str = "",
                period: str = "all") -> str:
    """Render /admin with optional filters on access_log (Jul 22 2026).

    period: time-window filter. One of '1d', '3d', '7d', 'all' (default).
      - '1d'  = last 24 hours
      - '3d'  = last 3 days   (Jul 24 2026, user request: "последние 3 дня")
      - '7d'  = last 7 days
      - 'all' = no time filter (every row, oldest possible match still wins)
    Filters by access_log.timestamp >= NOW - window.
    """
    from datetime import datetime, timezone, timedelta
    con = sqlite3.connect(DB_PATH)

    period_seconds = {
        '1d': 86400,
        '3d': 3 * 86400,
        '7d': 7 * 86400,
    }.get(period)
    since_iso = None
    if period_seconds is not None:
        since_iso = (datetime.now(timezone.utc) - timedelta(seconds=period_seconds)).isoformat()

    where_parts = ["al.username != 'owner'"]
    params = []
    if since_iso:
        where_parts.append("al.timestamp >= ?")
        params.append(since_iso)
    if user_filter:
        where_parts.append("al.username LIKE ?")
        params.append("%" + user_filter + "%")
    if ip_filter:
        where_parts.append("al.ip LIKE ?")
        params.append("%" + ip_filter + "%")
    if action_filter:
        where_parts.append("al.action LIKE ?")
        params.append("%" + action_filter + "%")
    where_sql = " AND ".join(where_parts)

    total_hits = con.execute(
        "SELECT COUNT(*) FROM access_log al "
        "LEFT JOIN users u ON u.username = al.username "
        "WHERE " + where_sql,
        params
    ).fetchone()[0]

    # Jul 24 2026: cap the visible activity at MAX_LOG_ROWS newest entries
    # (user spec: "не хочу видеть историю свыше 300 последних действий").
    # Older events are still in the DB but not shown in /admin. Anything
    # older than the 300th-newest row is dropped from the panel entirely
    # — the user explicitly does not want to scroll through 360+ pages
    # of stale /lineup_ai/track "view" events.
    from urllib.parse import urlencode
    MAX_LOG_ROWS = 300
    shown_hits = min(total_hits, MAX_LOG_ROWS)
    dropped = total_hits - shown_hits  # > 0 only when period='all'

    offset = (page - 1) * page_size
    # If the requested page is past the cap, clamp to the last valid page.
    max_page = (shown_hits + page_size - 1) // page_size if shown_hits else 1
    if page > max_page:
        page = max_page
        offset = (page - 1) * page_size
    total_logs = shown_hits
    total_pages = (total_logs + page_size - 1) // page_size

    users = con.execute("SELECT id,username,is_admin,active,created_at,last_login,plain_password FROM users ORDER BY id").fetchall()
    logs = con.execute(
        "SELECT al.username,al.ip,al.path,al.action,al.details,al.timestamp "
        "FROM access_log al "
        "LEFT JOIN users u ON u.username = al.username "
        "WHERE " + where_sql + " "
        "ORDER BY al.id DESC LIMIT ? OFFSET ?",
        params + [page_size, offset]
    ).fetchall()
    con.close()

    n_active = sum(1 for u in users if u[3])
    n_admin  = sum(1 for u in users if u[2])

    # --- users table rows ---
    rows = ""
    for u in users:
        uid, uname, is_adm, active, created, last, ppwd = u[:7]
        role   = '<span class="b b-a">Admin</span>' if is_adm else '<span class="b b-u">User</span>'
        status = '<span class="b b-on">Active</span>' if active else '<span class="b b-off">Inactive</span>'
        # password: click to reveal
        if ppwd:
            try:
                pwd = _decrypt(ppwd)
            except Exception:
                pwd = "–"
            pwd_cell = f'<span class="pwd" onclick="this.textContent=this.dataset.p" data-p="{pwd}">••••••</span>'
        else:
            pwd_cell = "–"

        toggle = "Deactivate" if active else "Activate"
        del_btn = "" if uname == "admin" else f'<form method="POST" action="/admin/del/{uid}"><button class="c rd" onclick="return confirm(\'Delete {uname}?\')">Delete</button></form>'

        rows += f"""<tr>
<td>{uid}</td><td><b>{uname}</b></td><td>{pwd_cell}</td>
<td>{role}</td><td>{status}</td>
<td>{_fmt_msk(created)}</td><td>{_fmt_msk(last)}</td>
<td>
<form method="POST" action="/admin/tog/{uid}"><button class="c yw">{toggle}</button></form>
<form method="POST" action="/admin/rst/{uid}"><button class="c bl">New Password</button></form>
{del_btn}
</td></tr>"""

    # --- log rows ---
    lrows = ""
    for l in logs:
        un, ip, path, act, det, ts = l
        # Jul 24 2026: per-cell la-* classes for the .ra-table fixed-width
        # CSS rule (see <style>). title="..." attribute on every cell so
        # the user can still see the full value on hover when it is
        # truncated by text-overflow:ellipsis.
        lrows += f"<tr><td class='la-time' title='{html_escape(ts)}'>{_fmt_msk(ts)}</td><td class='la-user' title='{html_escape(un)}'>{un}</td><td class='la-ip' title='{html_escape(ip or '')}'>{ip or ''}</td><td class='la-path' title='{html_escape(path)}'>{path}</td><td class='la-action' title='{html_escape(act)}'>{act}</td><td class='la-details g' title='{html_escape(det or '')}'>{det or ''}</td></tr>"

    # Pagination controls
    prev_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    pagination = ""
    if total_pages > 1:
        first_class = "disabled" if page == 1 else ""
        prev_class = "disabled" if page == 1 else ""
        next_class = "disabled" if page == total_pages else ""
        last_class = "disabled" if page == total_pages else ""
        # Preserve all non-page query params in the pagination links
        # so changing the page doesn't drop the period/user/ip/action
        # filters that the user picked.
        from urllib.parse import urlencode
        base_qs = {"period": period, "user": user_filter,
                   "ip": ip_filter, "action": action_filter}
        def _page_href(n: int) -> str:
            qs = dict(base_qs)
            qs["p"] = n
            return "/admin?" + urlencode(qs)
        pagination = f'<div class="pg"><a href="{_page_href(1)}" class="{first_class}">«</a> <a href="{_page_href(prev_page)}" class="{prev_class}">‹</a> <span>Page {page} of {total_pages}</span> <a href="{_page_href(next_page)}" class="{next_class}">›</a> <a href="{_page_href(total_pages)}" class="{last_class}">»</a></div>'

    # Preserved query string for the period-filter buttons ("1 day / 3 days
    # / 7 days / All") so the user's user/ip/action filters survive a
    # period change.
    from urllib.parse import urlencode
    period_qs = urlencode({k: v for k, v in {
        "user": user_filter, "ip": ip_filter, "action": action_filter,
        "p": page,
    }.items() if v})
    pq = ("&" + period_qs) if period_qs else ""

    msg_html = f'<div class="msg">{msg}</div>' if msg else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><link rel="icon" type="image/x-icon" href="/favicon.ico"><link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/site.webmanifest">
<title>User Admin — X11Radar</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0}}
.hd{{background:linear-gradient(135deg,#667eea,#764ba2);padding:20px 32px;display:flex;justify-content:space-between;align-items:center}}
.hd h1{{font-size:22px;color:#fff}}.hd a{{color:#fff;text-decoration:none;background:rgba(255,255,255,.15);padding:8px 16px;border-radius:6px;font-size:13px}}
.ct{{max-width:1100px;margin:24px auto;padding:0 16px}}
.cd{{background:#1e293b;border-radius:12px;padding:20px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.3)}}
.cd h2{{font-size:16px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:16px}}
.msg{{background:#065f46;color:#6ee7b7;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px;line-height:1.5}}
.msg b{{color:#fff}}.msg code{{background:#0f172a;padding:2px 8px;border-radius:4px;font-size:15px;color:#6ee7b7;font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px 10px;background:#334155;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:.5px}}
td{{padding:8px 10px;border-bottom:1px solid #334155}}tr:hover{{background:#334155}}
/* Jul 24 2026: Recent Activity table only. Without nowrap the long paths
   (/lineup_ai/compare/hpHBTd64?home_id=pKS9M7R7&away_id=dhOKTHGA) wrap to
   multiple lines. With .ra-table table-layout:fixed + these column widths,
   every row sits on exactly one line and overflowing text is truncated
   with an ellipsis. Users table is left alone (auto layout, no ellipsis). */
.ra-table{{table-layout:fixed}}
.ra-table td{{padding:6px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ra-table td.la-time{{width:130px}}
.ra-table td.la-user{{width:120px}}
.ra-table td.la-ip{{width:110px}}
.ra-table td.la-path{{max-width:0;width:auto}}
.ra-table td.la-action{{width:90px}}
.ra-table td.la-details{{max-width:0;width:auto}}
.b{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.b-a{{background:#7c3aed;color:#fff}}.b-u{{background:#1e40af;color:#93c5fd}}
.b-on{{background:#065f46;color:#6ee7b7}}.b-off{{background:#7f1d1d;color:#fca5a5}}
form{{display:inline}}button,.c{{display:inline-block;padding:4px 10px;border:none;border-radius:4px;font-size:12px;cursor:pointer;color:#fff;font-weight:500}}
.c:hover{{opacity:.85}}.gn{{background:#667eea}}.rd{{background:#dc2626}}.yw{{background:#d97706}}.bl{{background:#2563eb}}
.sts{{display:flex;gap:16px;margin-bottom:20px}}
.st{{background:#1e293b;padding:16px 20px;border-radius:10px;text-align:center;flex:1}}
.sv{{font-size:28px;font-weight:700;color:#667eea}}.sl{{font-size:11px;color:#64748b;text-transform:uppercase;margin-top:4px}}
.gbox{{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:12px 16px;margin-bottom:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.gbox input{{background:#334155;border:1px solid #475569;color:#e2e8f0;padding:6px 10px;border-radius:6px;font-size:13px;width:160px;outline:none}}
.gbox input::placeholder{{color:#64748b}}
.pf{{display:inline-block;padding:4px 10px;margin-left:4px;background:#0f172a;border:1px solid #334155;border-radius:6px;color:#94a3b8;text-decoration:none;font-size:11px;cursor:pointer}}
.pf:hover{{background:#334155;color:#e2e8f0}}
.pf.on{{background:#667eea;color:#fff;border-color:#667eea;font-weight:600}}
.pwd{{cursor:pointer;color:#6ee7b7;font-weight:600}}
.g{{color:#94a3b8}}
</style></head><body>
<div class="hd"><h1>User Admin</h1><a href="/lineup_ai/select">← Back to site</a></div>
<div class="ct">
{msg_html}
<div class="cd"><h2>Users</h2>
<div class="sts">
<div class="st"><div class="sv">{len(users)}</div><div class="sl">Total</div></div>
<div class="st"><div class="sv">{n_active}</div><div class="sl">Active</div></div>
<div class="st"><div class="sv">{n_admin}</div><div class="sl">Admins</div></div>
<div class="st"><div class="sv">{total_hits}</div><div class="sl">Page Hits</div></div>
</div>
<div class="gbox">
<form method="POST" action="/admin/gen"><input type="text" name="username" placeholder="Login (blank = auto)"><button class="c gn">Generate Login &amp; Password</button></form>
</div>
<table><thead><tr><th>ID</th><th>Login</th><th>Password</th><th>Role</th><th>Status</th><th>Created</th><th>Last Login</th><th>Actions</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<div class="cd"><h2 style="display:flex;justify-content:space-between;align-items:center;">
  <span>Recent Activity ({total_logs}{(' — showing newest 300 of ' + str(total_hits) + ' events') if dropped else ''})</span>
  <span style="font-size:11px;text-transform:none;letter-spacing:0;">
    <a href="/admin?period=1d{pq}" class="pf{' on' if period == '1d' else ''}">1 day</a>
    <a href="/admin?period=3d{pq}" class="pf{' on' if period == '3d' else ''}">3 days</a>
    <a href="/admin?period=7d{pq}" class="pf{' on' if period == '7d' else ''}">7 days</a>
    <a href="/admin?period=all{pq}" class="pf{' on' if period == 'all' else ''}">All</a>
  </span>
</h2>
<table class="ra-table"><thead><tr><th>Time</th><th>User</th><th>IP</th><th>Path</th><th>Action</th><th>Details</th></tr></thead>
<tbody>{lrows}</tbody></table>
{pagination}
</div>
</div></body></html>"""


@app.get("/admin")
async def admin_panel(request: Request, p: int = 1, period: str = "all",
                      user: str = "", ip: str = "", action: str = ""):
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403)
    _flash_clean()
    msg = _flash_get(request.query_params.get("f", ""))
    # Jul 24 2026: lazy GC of access_log — keep only the newest 300 rows
    # (matches the /admin cap from commit 9d18f5b). We trigger the cleanup
    # only when the table is more than 2x the keep threshold (600 rows),
    # so the DELETE does not fire on every single page load — it fires
    # roughly once per ~300 new events. The function itself is a no-op
    # when the table is already small.
    try:
        cleanup_old_access_logs(keep=300)
    except Exception:
        pass
    return HTMLResponse(_render_admin(msg, page=p, period=period,
                                       user_filter=user, ip_filter=ip, action_filter=action))


@app.post("/admin/gen")
async def admin_generate(request: Request):
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403)
    form = await request.form()
    custom = (form.get("username") or "").strip()
    pwd = _generate_password()
    ph = _hash_password(pwd)
    ep = _encrypt(pwd)
    con = sqlite3.connect(DB_PATH)
    if custom:
        if con.execute("SELECT 1 FROM users WHERE username=?", (custom,)).fetchone():
            con.close()
            k = _flash_set(f"Login <b>{custom}</b> already exists!")
            return RedirectResponse(f"/admin?f={k}", status_code=303)
        uname = custom
    else:
        uname = _generate_username()
    con.execute("INSERT INTO users(username,password_hash,plain_password,is_admin,active,created_at) VALUES(?,?,?,?,?,?)",
                (uname, ph, ep, 0, 1, datetime.now(timezone.utc).isoformat()))
    con.commit(); con.close()
    _log_access(getattr(request.state,"username",""), request.client.host if request.client else "", "/admin", "create_user", uname)
    k = _flash_set(f"Login: <b>{uname}</b> &nbsp;|&nbsp; Password: <code>{pwd}</code> — copy now, shown only once!")
    return RedirectResponse(f"/admin?f={k}", status_code=303)


@app.post("/admin/del/{uid}")
async def admin_delete(uid: int, request: Request):
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403)
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
    if row and row[0] == "admin":
        con.close()
        k = _flash_set("Cannot delete admin!")
        return RedirectResponse(f"/admin?f={k}", status_code=303)
    if row:
        con.execute("DELETE FROM users WHERE id=?", (uid,)); con.commit()
        # Jul 29 2026: clear active-status cache so deleted user can't reuse session.
        _invalidate_active_user_cache(row[0])
        _log_access(getattr(request.state,"username",""), request.client.host if request.client else "", "/admin", "delete_user", row[0])
    con.close()
    k = _flash_set("User deleted" if row else "User not found")
    return RedirectResponse(f"/admin?f={k}", status_code=303)


@app.post("/admin/rotate-secret")
async def admin_rotate_secret(request: Request):
    """Jul 30 2026 v8: rotate _SESSION_SECRET to kill all active sessions.

    All existing session cookies become invalid. Users must
    re-login. Use this when a banned user keeps accessing the
    service with an old cookie.
    """
    global _SESSION_SECRET, _SESSION_SECRET_GENERATED_AT
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403)
    old_prefix = _SESSION_SECRET[:8]
    _SESSION_SECRET = _secrets_mod.token_hex(32)
    _SESSION_SECRET_GENERATED_AT = time.time()
    # v12: persist the new secret to file so it survives restarts
    try:
        with open(_SESSION_SECRET_FILE, "w") as _sf:
            _sf.write(_SESSION_SECRET)
    except Exception:
        pass
    _log_access(
        getattr(request.state, "username", ""),
        request.client.host if request.client else "",
        "/admin", "rotate_secret",
        f"old={old_prefix}... new={_SESSION_SECRET[:8]}..."
    )
    k = _flash_set(f"Session secret rotated. All users must re-login.")
    return RedirectResponse(f"/admin?flash={k}", status_code=303)


@app.post("/admin/tog/{uid}")
async def admin_toggle(uid: int, request: Request):
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403)
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT username,active FROM users WHERE id=?", (uid,)).fetchone()
    if row:
        nv = 0 if row[1] else 1
        # Jul 30 2026 v7: refuse to toggle a banned user back to active.
        # Permanent ban must be lifted by SQL DELETE FROM banned_users,
        # NOT by a one-click toggle.
        username = row[0]
        if nv == 1:
            try:
                ban_row = con.execute(
                    "SELECT 1 FROM banned_users WHERE username=? LIMIT 1",
                    (username,)
                ).fetchone()
                if ban_row:
                    # User is banned; refuse to activate.
                    nv = 0  # keep them deactivated
            except Exception:
                pass
        # Jul 30 2026 v9: when deactivating a user, auto-ban
        # all IPs they have used. Makes the ban survive
        # even if the user clears cookies or uses a new browser.
        if nv == 0:
            try:
                _ban_ip_for_username(username)
            except Exception:
                pass
        # Jul 30 2026 v10: on deactivate, permanently ban username
        # AND auto-ban all IPs they have used. One click = full
        # network ban. Username stays banned until manual SQL DELETE.
        ip_banned_count = 0
        if nv == 0:
            try:
                con.execute(
                    "INSERT OR IGNORE INTO banned_users (username, reason, banned_at, banned_by) VALUES (?, ?, ?, ?)",
                    (username, "admin_toggle", datetime.now(timezone.utc).isoformat(), getattr(request.state, "username", "admin"))
                )
                ip_banned_count = _ban_ip_for_username(username)
                con.commit()
            except Exception:
                pass
        con.execute("UPDATE users SET active=? WHERE id=?", (nv, uid)); con.commit()
        # Jul 30 2026 v5: no in-memory state to manage. The DB is the
        # source of truth; the middleware reads it directly on every
        # request. Toggle is immediately effective.
        action = "activated" if nv else "deactivated"
        _log_access(getattr(request.state,"username",""), request.client.host if request.client else "", "/admin", "toggle", f"{row[0]} {action}")
    con.close()
    # Flash feedback with IP ban count
    if nv == 0 and ip_banned_count > 0:
        k = _flash_set(f"User <b>{row[0]}</b> deactivated and banned. <span style='color:#dc3545; font-weight:700'>{ip_banned_count} IP address(es) blocked.</span> User cannot use the service from any device.")
    else:
        k = _flash_set(f"User <b>{row[0]}</b> {action}.")
    return RedirectResponse(f"/admin?f={k}", status_code=303)


@app.post("/admin/rst/{uid}")
async def admin_reset(uid: int, request: Request):
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403)
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
    if row:
        pwd = _generate_password()
        ph = _hash_password(pwd)
        ep = _encrypt(pwd)
        con.execute("UPDATE users SET password_hash=?,plain_password=? WHERE id=?", (ph, ep, uid)); con.commit()
        _log_access(getattr(request.state,"username",""), request.client.host if request.client else "", "/admin", "reset_password", row[0])
        con.close()
        k = _flash_set(f"Password reset for <b>{row[0]}</b>: <code>{pwd}</code> — copy now!")
        return RedirectResponse(f"/admin?f={k}", status_code=303)
    con.close()
    return RedirectResponse("/admin", status_code=303)

