import os
import time
import sqlite3
import urllib.parse
import json
import unicodedata
import re
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request, Form
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse

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
    "lineup_change",
    "injury_update",
    "suspension",
    "coach_change",
    "match_postponement",
    "disciplinary_decision",
    "red_card_impact",
    "national_team_callup",
    "return_to_squad",
    "rotation_risk",
    "predicted_lineup",
    "starting_lineup",
    "fans",
    "squad_list",
    "tactical_leak",
    "other",
]

IMPACT_LEVELS = ["HIGH", "MEDIUM", "LOW"]


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
        f"⚡️ ALERT • {time_msk} МСК",
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
    # strict schema + conservative fallbacks
    relevant = bool(obj.get("relevant"))
    category = obj.get("category") or "other"
    impact = obj.get("impact_level") or "LOW"
    confidence = obj.get("confidence")
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0

    if category not in CATEGORIES:
        category = "other"
    if impact not in IMPACT_LEVELS:
        impact = "LOW"

    teams = obj.get("teams") or []
    players = obj.get("players") or []
    competition = obj.get("competition") or ""

    if not isinstance(teams, list):
        teams = []
    if not isinstance(players, list):
        players = []

    # Normalize player names: Title Case (first/last names capitalized)
    def _cap_player_name(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        # Keep common apostrophes/hyphens; title() works reasonably for Latin names.
        # Preserve internal casing for particles if user wants later.
        out = " ".join([w for w in s.split() if w])
        return out.title()

    try:
        players = [_cap_player_name(str(p)) for p in (players or [])]
        players = [p for p in players if p]
    except Exception:
        pass
    if not isinstance(competition, str):
        competition = ""

    original_text = obj.get("original_text") or ""
    original_link = obj.get("original_link") or ""
    source_username = obj.get("source_username") or ""

    team_from_map = lookup_team_for_source(source_username) if source_username else ""

    if relevant and (not original_text.strip() or not original_link.strip()):
        relevant = False

    # fans is NOT always relevant; only relevant when there is an actual attendance/travel restriction fact.
    if category == "fans":
        t_low = (original_text or "").lower()
        fans_fact_markers = [
            "huis clos",
            "à huis clos",
            "behind closed doors",
            "closed doors",
            "tribune ferm",
            "sans public",
            "sans supporters",
            "supporters interdits",
            "interdiction de déplacement",
            "interdiction de deplacement",
            "privés de déplacement",
            "prives de deplacement",
            "déplacement interdit",
            "deplacement interdit",
        ]
        if any(m in t_low for m in fans_fact_markers):
            relevant = True
        else:
            relevant = False

    formatted_signal = ""
    if relevant:
        lines0 = original_text.split("\n")
        quoted_html = "<blockquote>" + "\n".join([html_escape(ln) for ln in lines0]) + "</blockquote>"

        # Also bold player names inside the quoted original text (for visibility)
        try:
            plist_q = _read_keywords_file(PLAYER_NAMES_PATH)
        except Exception:
            plist_q = []
        if plist_q and quoted_html:
            import re as _re
            for nm in sorted([p for p in plist_q if p], key=lambda x: -len(x)):
                nm_norm = str(nm).strip()
                if not nm_norm:
                    continue
                pat = r"(?<![\w’'])" + _re.escape(nm_norm) + r"(?![\w’'])"
                quoted_html = _re.sub(pat, lambda m: "<b>"+nm_norm+"</b>", quoted_html, flags=_re.IGNORECASE)

        cat_ru = {
            "lineup_change": "изменение состава",
            "predicted_lineup": "возможный состав/старт",
            "rotation_risk": "риск ротации/скамейка",
            "injury_update": "статус травмы/готовности",
            "suspension": "дисквалификация/бан",
            "disciplinary_decision": "дисциплинарное решение",
            "red_card_impact": "красная карточка/последствия",
            "coach_change": "изменение тренера",
            "match_postponement": "перенос/задержка матча",
            "national_team_callup": "вызов в сборную",
            "return_to_squad": "возвращение в состав",
            "squad_list": "заявка/список игроков",
            "tactical_leak": "тактический инсайд",
            "fans": "матч без болельщиков/ограничение посещаемости",
            "other": "прочее",
        }
        imp_ru = {"HIGH": "высокое", "MEDIUM": "среднее", "LOW": "низкое"}

        player_note = (players[0] if players else "").strip()
        analysis_ru = (obj.get("analysis_ru") or "").strip()

        if analysis_ru:
            # Remove awkward meta-source prefixes if the model added them.
            analysis_ru = re.sub(r"^(\s*(фан-аккаунт|fan\s*account)\s*:\s*)", "", analysis_ru, flags=re.IGNORECASE)
            analysis_ru = re.sub(r"^(\s*(источник\s*:|source\s*:)\s*)", "", analysis_ru, flags=re.IGNORECASE)
            low = analysis_ru.lower()

            # Add per-player emoji lines (ONLY if players are present)
            def _status_emoji_for(category: str, original_text: str) -> str:
                if category == "injury_update":
                    b = _injury_bucket(original_text)
                    return {"OK": "✅", "DOUBT": "⚠️", "OUT": "❌", "UNKNOWN": "🤷‍♂️"}.get(b, "")
                if category in ("suspension", "disciplinary_decision"):
                    return "⛔️"
                if category == "red_card_impact":
                    return "🟥"
                if category == "national_team_callup":
                    return "🌍"
                if category == "return_to_squad":
                    return "✅"
                return ""

            status_emo = _status_emoji_for(category, original_text)

            # Starting XI mode has priority over Probable XI.
            sx_pass, _, _ = starting_xi_filter_stats(original_text)
            px_pass, _, _ = probable_xi_filter_stats(original_text)

            if sx_pass:
                starters = [
                    "Опубликованы стартовые составы: ",
                    "Доступны стартовые составы — ",
                    "Появились официальные составы: ",
                    "Обнародованы стартовые составы — ",
                    "Стали известны стартовые составы: ",
                    "Вышли стартовые составы — ",
                    "Подтверждены стартовые составы: ",
                    "Официально: стартовые составы — ",
                ]
                import hashlib
                h = hashlib.sha256((source_username + "|" + original_link).encode("utf-8")).digest()
                pref = starters[h[6] % len(starters)]

                tail = (analysis_ru or "").strip()
                if tail:
                    tail = tail[:1].lower() + tail[1:]
                    for bad in [
                        "опубликованы стартовые составы",
                        "доступны стартовые составы",
                        "появились официальные составы",
                        "обнародованы стартовые составы",
                        "стали известны стартовые составы",
                        "вышли стартовые составы",
                        "подтверждены стартовые составы",
                        "официально: стартовые составы",
                        "официально стартовые составы",
                    ]:
                        if tail.lower().startswith(bad):
                            tail = tail[len(bad):].lstrip(" :—,-")
                            break
                # For starting XI posts, keep it dry: single factual sentence.
                # Strip "no names in text / by link"-style filler.
                for bad2 in [
                    "конкретные фамилии",
                    "в тексте не приведены",
                    "не перечислены",
                    "находятся по ссылке",
                    "вероятно они находятся",
                    "по прикреплённой ссылке",
                    "по прикрепленной ссылке",
                ]:
                    if bad2 in tail.lower():
                        # truncate at the first occurrence
                        idx = tail.lower().find(bad2)
                        tail = tail[:idx].rstrip(" .,:;—-")
                        break
                # enforce single sentence
                if tail.count('.') >= 1:
                    tail = tail.split('.', 1)[0].strip()
                analysis_ru = pref + tail
                category = "starting_lineup"
            elif px_pass:
                starters = [
                    "Опубликованы возможные составы: ",
                    "Появились предполагаемые составы — ",
                    "Опубликованы ориентировочные составы, ",
                    "Стали известны возможные составы: ",
                    "Появилась информация о возможных составах, ",
                    "Доступны предварительные составы команд — ",
                    "В X появились возможные составы: ",
                    "Опубликованы вероятные составы на матч — ",
                    "Опубликованы ожидаемые составы, ",
                ]
                import hashlib
                h = hashlib.sha256((source_username + "|" + original_link).encode("utf-8")).digest()
                pref = starters[h[6] % len(starters)]

                # Smooth transition: lowercase first letter and strip duplicate lead-in if model starts with it.
                tail = (analysis_ru or "").strip()
                if tail:
                    tail = tail[:1].lower() + tail[1:]
                    for bad in [
                        "опубликованы возможные составы",
                        "появились предполагаемые составы",
                        "опубликованы ориентировочные составы",
                        "стали известны возможные составы",
                        "появилась информация о возможных составах",
                        "доступны предварительные составы",
                        "в x появились возможные составы",
                        "опубликованы вероятные составы",
                        "опубликованы ожидаемые составы",
                    ]:
                        if tail.lower().startswith(bad):
                            tail = tail[len(bad):].lstrip(" :—,-")
                            break
                analysis_ru = pref + tail
            else:
                # Official club sources
                if source_username in OFFICIAL_SOURCES:
                    pref = _choose_official_prefix(source_username + "|" + original_link)
                    if not (low.startswith("из официаль") or low.startswith("по данным официаль") or low.startswith("как сообщает официальный") or low.startswith("по сведениям официаль") or low.startswith("в официальном") or low.startswith("согласно данных официаль") or low.startswith("официально")):
                        analysis_ru = pref + analysis_ru[:1].lower() + analysis_ru[1:]
                # Journalists/insiders
                elif source_username in JOURNO_SOURCES:
                    pref = _choose_journo_prefix(source_username + "|" + original_link)
                    if not (low.startswith("по данным журналист") or low.startswith("как сообщают близкие") or low.startswith("согласно сведениям от экспертов") or low.startswith("согласно источникам среди журналист") or low.startswith("по сведениям журналист") or low.startswith("по данным, известным инсайд") or low.startswith("инсайдеры сообщают") or low.startswith("по данным, поступившим от надеж") or low.startswith("от надежных источников") or low.startswith("по данным источников, близких") or low.startswith("по сообщениям инсайд") or low.startswith("по данным экспертов")):
                        analysis_ru = pref + analysis_ru[:1].lower() + analysis_ru[1:]
                # Regional / fans / fan-media
                elif source_username in REGIONAL_SOURCES:
                    pref = _choose_regional_prefix(source_username + "|" + original_link)
                    analysis_ru = pref + analysis_ru[:1].lower() + analysis_ru[1:]
                elif source_username in FAN_SUPPORTIVE_SOURCES:
                    pref = _choose_fan_supportive_prefix(source_username + "|" + original_link)
                    analysis_ru = pref + analysis_ru[:1].lower() + analysis_ru[1:]
                elif source_username in FAN_MEDIA_SOURCES:
                    pref = _choose_fan_media_prefix(source_username + "|" + original_link)
                    # Always force one of the approved starters (avoid variety outside the list)
                    analysis_ru = pref + analysis_ru[:1].lower() + analysis_ru[1:]

            market_effect = analysis_ru
        else:
            if category == "predicted_lineup":
                t_low = (original_text or "").lower()
                if any(k in t_low for k in ["composition probable", "compo probable", "xi probable", "l’equipe probable", "composition probable du", "starting xi", "probable xi"]):
                    market_effect = "Опубликован предполагаемый стартовый состав (XI)." + (f" {player_note} указан в составе." if player_note else "")
                else:
                    market_effect = "Опубликован предполагаемый состав/вариант XI."
            elif category == "rotation_risk":
                market_effect = f"{('Игрок ' + player_note + ' ') if player_note else ''}может начать матч не в старте/на скамейке (риск ротации)."
            elif category == "injury_update":
                market_effect = f"Обновление по готовности/травме{(' ('+player_note+')') if player_note else ''}."
            elif category in ("suspension", "red_card_impact"):
                market_effect = f"Дисциплинарный фактор{(' ('+player_note+')') if player_note else ''} (пропуск/ограничение участия)."
            elif category == "lineup_change":
                market_effect = "Есть изменение по составу/старту."
            else:
                market_effect = f"{cat_ru.get(category, category)} (влияние: {imp_ru.get(impact, impact)})."

        # Use tweet (X) created_at time in MSK for the header, not processing time.
        from datetime import timedelta
        def _x_created_at_msk(created_at_iso: str) -> str:
            try:
                s = (created_at_iso or "").replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                dt_msk = dt + timedelta(hours=3)
                return dt_msk.strftime("%d.%m.%Y • %H:%M")
            except Exception:
                ts_msk = datetime.utcnow() + timedelta(hours=3)
                return ts_msk.strftime("%d.%m.%Y • %H:%M")

        time_line = _x_created_at_msk(obj.get("tweet_created_at") or "")

        priority = f"{('🔴' if impact=='HIGH' else '🟠' if impact=='MEDIUM' else '🟡')} {impact} PRIORITY"
        # Enforce capitalization for player names in analysis text
        analysis_text = market_effect
        try:
            for p in (players or []):
                pn = str(p or "").strip()
                if not pn:
                    continue
                # Replace common lower/mixed variants with Title Case variant
                variants = {pn.lower(), pn.upper(), pn.title()}
                for v in variants:
                    if v and v != pn:
                        analysis_text = analysis_text.replace(v, pn)
        except Exception:
            pass

        # Bold player names from configured Player names list if present in analysis_ru.
        # Also canonicalize capitalization to match the list.
        try:
            plist = _read_keywords_file(PLAYER_NAMES_PATH)
        except Exception:
            plist = []

        def _apply_player_markup(s: str) -> str:
            if not plist or not s:
                return s
            out = s
            # longest-first to avoid partial overlap issues
            for nm in sorted([p for p in plist if p], key=lambda x: -len(x)):
                nm_norm = str(nm).strip()
                if not nm_norm:
                    continue
                import re as _re

                def _repl(m):
                    return "<b>" + nm_norm + "</b>"

                pat = r"(?<![\w’'])" + _re.escape(nm_norm) + r"(?![\w’'])"
                out = _re.sub(pat, _repl, out, flags=_re.IGNORECASE)
            return out

        analysis_text = _apply_player_markup(analysis_text)

        analysis = html_escape(analysis_text)
        # Keep <b> tags we inserted (unescape them back)
        analysis = analysis.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')

        header_team = team_from_map.strip()
        header_cat = category
        header_line = f"{html_escape(header_team)} • {html_escape(header_cat)}" if (header_team and header_cat) else (html_escape(header_team) if header_team else html_escape(header_cat))

        # Confidence display (based on source type)
        def _confidence_range(source_username: str) -> tuple[int,int]:
            if source_username in OFFICIAL_SOURCES:
                return (95, 99)
            if source_username in JOURNO_SOURCES:
                return (80, 95)
            if source_username in REGIONAL_SOURCES:
                return (80, 95)
            if source_username in FAN_MEDIA_SOURCES:
                return (70, 80)
            if source_username in FAN_SUPPORTIVE_SOURCES:
                return (60, 70)
            return (80, 95)

        conf_lo, conf_hi = _confidence_range(source_username)
        # Deterministic pick inside range (stable per tweet)
        import hashlib
        hh = hashlib.sha256((source_username + "|" + original_link).encode("utf-8")).digest()
        conf = conf_lo + (hh[3] % (conf_hi - conf_lo + 1))

        # Players block disabled (no emoji/player lines at bottom)
        pb = ""

        formatted_signal = (
            f"⚡️ ALERT • {time_line} (МСК)\n\n"
            f"<b>{html_escape(priority)}</b>\n\n"
            f"{header_line + '\n\n' if header_line else ''}"
            f"🔗 • {html_escape(original_link)}\n\n"
            f"Confidence • {conf}%\n\n"
            f"{quoted_html}\n\n"
            f"{analysis}"
            + (f"\n\n{pb}" if pb else "")
        )

    if confidence < 0:
        confidence = 0.0
    if confidence > 1:
        confidence = 1.0

    return {
        "relevant": relevant,
        "category": category,
        "impact_level": impact,
        "confidence": confidence,
        "teams": teams,
        "players": players,
        "competition": competition,
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

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=GATE_TIMEOUT_SECONDS) as client:
            r = await client.post(api_url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return False

    out_text = ""
    try:
        output = data.get("output") or []
        if output and isinstance(output, list):
            c = output[0].get("content") or []
            if c and isinstance(c, list):
                out_text = (c[0].get("text") or "").strip()
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

    schema_hint = (
        '{\n'
        ' "relevant": true|false,\n'
        ' "category": "lineup_change|injury_update|suspension|coach_change|match_postponement|disciplinary_decision|red_card_impact|national_team_callup|return_to_squad|rotation_risk|predicted_lineup|starting_lineup|squad_list|tactical_leak|fans|other",\n'
        ' "impact_level": "HIGH|MEDIUM|LOW",\n'
        ' "confidence": 0.0,\n'
        ' "teams": [],\n'
        ' "players": [],\n'
        ' "competition": "",\n'
        ' "analysis_ru": ""\n'
        '}\n'
    )

    prompt = (
        "Верни ТОЛЬКО один JSON-объект без markdown/текста вокруг. "
        "Будь консервативным, не выдумывай команды/турниры. Анализ на русском. "
        "\n\nСХЕМА JSON:\n" + schema_hint +
        "\nВАЖНО: добавь поле tweet_created_at в JSON (как было передано ниже, без изменений)."
        "\n\nПРАВИЛА ДЛЯ impact_level (важность):\n"
        "- HIGH: подтверждённый пропуск матча/нескольких матчей; тяжёлая травма/серьёзная дисквалификация; ключевой игрок; или подтверждение из официального источника.\n"
        "- MEDIUM: под вопросом/неясный статус; 1 матч; ожидаемая ротация/вероятность скамейки; формулировки типа 'incertain', 'doubtful', 'could miss'.\n"
        "- LOW: слухи/общая инфа без влияния на доступность/старт; нет факта пропуска/сомнения; просто обсуждение/контекст без конкретики.\n"
        "Выбирай самый консервативный уровень, если не уверен.\n"
        "\nПРАВИЛА ДЛЯ category=return_to_squad (важно):\n"
        "- return_to_squad ставь ТОЛЬКО если есть явный факт возвращения ПОСЛЕ отсутствия (травма/болезнь/дисквалификация/не попадал в заявку).\n"
        "- НЕ ставь return_to_squad, если игрок уже играл в последнем матче или был в стартовом составе/в XI (например: 'a débuté', 'titulaire', 'dans le onze', 'started', 'in the starting XI', 'played last match', 'уже играл', 'в стартовом составе').\n"
        "- В таких случаях выбирай starting_lineup/predicted_lineup/other по смыслу.\n"
        "\nTWEET_TEXT:\n" + tweet_text +
        "\n\nTWEET_URL:\n" + tweet_url + "\n\n"
        "ДОПОЛНИТЕЛЬНО: верни в JSON поля original_text и original_link ровно как они даны ниже (без изменений)."
        "\noriginal_text:\n" + tweet_text +
        "\noriginal_link:\n" + tweet_url + "\n\n"
        "И ЕЩЁ: верни поле source_username ровно как ниже (без изменений)."
        "\nsource_username:\n" + source_username + "\n\n"
        "И ЕЩЁ: верни поле tweet_created_at ровно как ниже (без изменений)."
        "\ntweet_created_at:\n" + tweet_created_at + "\n\n"
        "ДОПОЛНИТЕЛЬНО: верни analysis_ru (2-3 предложения на русском), строго по смыслу твита, без домыслов и без выдуманных сущностей. "
        "НЕ используй формулировки вроде 'в твите говорится/сообщается в твите'. "
        "НЕ пиши в analysis_ru мета-описания источника типа: 'фан-аккаунт', 'журналист', 'инсайдер', 'официальный аккаунт', 'местные СМИ' и т.п. "
        "(Стиль источника будет добавлен снаружи). "
        "ВАЖНО: имена и фамилии игроков пиши с заглавных букв (как имена собственные). "
        "ВАЖНО: если category=starting_lineup, пиши КРАТКО И ПО СУЩЕ: 1 предложение максимум, без уточнений вроде 'фамилии не перечислены/они по ссылке/вероятно' и без воды. "
        "ВАЖНО: category=fans используй ТОЛЬКО если в тексте есть факт ограничения болельщиков/посещаемости (huis clos, запрет выезда, закрытые трибуны). Фанатские просьбы/мемы/реакции НЕ относятся к fans.\n"
        "\nanalysis_ru:\n"
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
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(api_url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        out = _validate_classification({"relevant": False})
        out["_core_preview"] = ""
        out["_core_json_valid"] = False
        out["_core_error"] = f"HTTP_ERROR:{type(e).__name__}"
        return out

    # Wormsoft responses: try to extract output text
    out_text = ""
    try:
        # common layout: output[0].content[0].text
        output = data.get("output") or []
        if output and isinstance(output, list):
            c = output[0].get("content") or []
            if c and isinstance(c, list):
                out_text = c[0].get("text") or ""
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
                    mid = await send_telegram_photo(photo, cap)
                else:
                    mid = await send_telegram(cls["formatted_signal"])
            else:
                mid = await send_telegram(cls["formatted_signal"])
            if mid is not None:
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
    # Minimal HTML form
    options = "\n".join([f"<option value='{c}'>{c}</option>" for c in CATEGORIES])
    impacts = "\n".join([f"<option value='{i}'>{i}</option>" for i in IMPACT_LEVELS])

    html = f"""<!doctype html>
<html lang=\"ru\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>FormAlert</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; max-width: 900px; }}
    label {{ display:block; margin-top: 12px; font-weight: 600; }}
    input, select, textarea {{ width: 100%; padding: 10px; margin-top: 6px; }}
    textarea {{ min-height: 90px; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }}
    button {{ margin-top: 16px; padding: 12px 16px; font-weight: 700; }}
    .hint {{ color: #666; font-size: 13px; margin-top: 4px; }}
  </style>
</head>
<body>
  <h1>FormAlert</h1>
  <p class='hint'>Отправляет алерт в Telegram и сохраняет в SQLite. <a href='/admin/'>Админ</a> • <a href='/keywords'>Keywords &amp; Blacklist</a></p>

  <form method=\"post\" action=\"/send\">

    <label>Время (МСК, HH:MM)</label>
    <input name=\"time_msk\" placeholder=\"18:45\" />

    <label>Команда / TEAM</label>
    <input name=\"team\" placeholder=\"Chelsea\" />

    <div class=\"row\">
      <div>
        <label>Категория</label>
        <select name=\"category\">{options}</select>
      </div>
      <div>
        <label>Влияние</label>
        <select name=\"impact_level\">{impacts}</select>
      </div>
      <div>
        <label>Уверенность (0-1)</label>
        <input name=\"confidence\" type=\"number\" step=\"0.01\" min=\"0\" max=\"1\" value=\"0.60\" />
      </div>
    </div>

    <label>TITLE (рус)</label>
    <input name=\"title\" placeholder=\"Напр.: Потеря игрока основы перед матчем\" />

    <label>DETAILS_1 (рус)</label>
    <textarea name=\"details1\" placeholder=\"Коротко по факту\"></textarea>

    <label>DETAILS_2 (рус)</label>
    <textarea name=\"details2\" placeholder=\"Уточнение (статус, матч, сроки)\"></textarea>

    <label>DETAILS_3 (опц.)</label>
    <textarea name=\"details3\" placeholder=\"Доп. деталь (если надо)\"></textarea>

    <label>ORIGINAL_TEXT (как в твите, без правок)</label>
    <textarea name=\"original_text\" placeholder=\"Вставь текст твита 1:1\" required></textarea>

    <label>ORIGINAL_LINK</label>
    <input name=\"original_link\" placeholder=\"https://x.com/...\" required />

    <button type=\"submit\">Отправить</button>
  </form>

</body>
</html>"""
    return HTMLResponse(html)


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


@app.get("/keywords", response_class=HTMLResponse)
async def keywords_page():
    inc = _read_keywords_file(KEYWORDS_INCLUDE_PATH)
    bl = _read_keywords_file(KEYWORDS_BLACKLIST_PATH)
    pn = _read_keywords_file(PLAYER_NAMES_PATH)

    inc_txt = html_escape("\n".join(inc))
    bl_txt = html_escape("\n".join(bl))
    pn_txt = html_escape("\n".join(pn))

    html = f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
    <title>Keywords</title>
    <style>
      body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px;max-width:1200px}}
      textarea{{width:100%;min-height:240px;padding:10px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
      .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
      button{{padding:10px 14px;font-weight:800}}
      .hint{{color:#666;font-size:13px}}
    </style></head><body>
    <p><a href='/'>← На главную</a> · <a href='/admin/'>Admin</a></p>
    <h1>Keywords</h1>
    <p class='hint'>1 строка = 1 слово/фраза. Сохраняется в .txt. Дубликаты удаляются.</p>

    <form method='post' action='/keywords/save'>
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


@app.post("/keywords/save")
async def keywords_save(include: str = Form(default=""), blacklist: str = Form(default=""), player_names: str = Form(default="")):
    inc_lines = (include or "").splitlines()
    bl_lines = (blacklist or "").splitlines()
    pn_lines = (player_names or "").splitlines()
    _write_keywords_file(KEYWORDS_INCLUDE_PATH, inc_lines)
    _write_keywords_file(KEYWORDS_BLACKLIST_PATH, bl_lines)
    _write_keywords_file(PLAYER_NAMES_PATH, pn_lines)
    return RedirectResponse(url="/keywords", status_code=303)


def _admin_nav(active: str) -> str:
    items = [
        ("Форма", "/"),
        ("Runs", "/admin/runs"),
        ("Tweets", "/admin/tweets"),
        ("Teams", "/admin/teams"),
        ("Status", "/admin/status"),
        ("Modes", "/admin/modes"),
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
    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
    <title>FormAlert Admin</title>
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px;max-width:1200px}
      .topnav{margin:0 0 14px 0}
      .topnav a{display:inline-block;margin-right:10px;padding:6px 10px;border-radius:10px;text-decoration:none;background:#eee;color:#111;font-weight:800}
      .topnav a.active{background:#111;color:#fff}
    </style>
    </head><body>
    """ + _admin_nav("/admin/") + """
    <h1>Admin</h1>
    <p class='muted'>Навигация сверху.</p>
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

    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
    <title>Status</title>
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px;max-width:1200px}
      pre{background:#111;color:#eaeaea;padding:14px;border-radius:10px;overflow:auto}
      .topnav{margin:0 0 14px 0}
      .topnav a{display:inline-block;margin-right:10px;padding:6px 10px;border-radius:10px;text-decoration:none;background:#eee;color:#111;font-weight:800}
      .topnav a.active{background:#111;color:#fff}
    </style></head><body>
    """ + _admin_nav("/admin/status") + """
    <h1>Status</h1>
    <pre>""" + html_escape(body) + """</pre>
    </body></html>"""
    return HTMLResponse(html)


@app.get("/admin/modes", response_class=HTMLResponse)
async def admin_modes():
    modes = _load_modes() or {}
    txt = json.dumps(modes, ensure_ascii=False, indent=2)
    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
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
    """ + _admin_nav("/admin/modes") + """
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

    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
    <title>Teams Map</title>
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px;max-width:1100px}
      table{border-collapse:collapse;width:100%}
      th,td{border:1px solid #ddd;padding:8px;font-size:13px;vertical-align:top}
      th{background:#f6f6f6;text-align:left}
      input{padding:8px;width:100%}
    </style></head><body>
    """ + _admin_nav("/admin/teams") + """
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

    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
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
    """ + _admin_nav("/admin/runs") + """
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

    html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
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
    """ + _admin_nav("/admin/tweets") + """
    <h1>Tweets</h1>
    <form method='get' action='/admin/tweets' style='margin:12px 0'>
      <input name='tweet_id' placeholder='Поиск по tweet_id' value='""" + esc(tweet_id) + """' style='padding:8px;width:220px;max-width:100%' />
      <input name='kw' placeholder='Keyword' value='""" + esc(kw) + """' style='padding:8px;width:180px;max-width:100%' />
      <input name='player' placeholder='Player (поиск по имени)' value='""" + esc(player) + """' style='padding:8px;width:220px;max-width:100%' />
      <label style='margin-left:8px;white-space:nowrap'><input type='checkbox' name='only_players' value='1' """ + ("checked" if only_players else "") + """/> only players list</label>
      <button type='submit' style='padding:8px 12px;font-weight:700'>Search</button>
      <a href='/admin/tweets' style='margin-left:10px'>Reset</a>
      <a href='/keywords' style='margin-left:10px'>Keywords</a>
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


@app.post("/send")
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

    return RedirectResponse(url="/", status_code=303)
