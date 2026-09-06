"""
Lineup Team View - Displays squad table with all columns
"""
import json
import glob
import os
import re
import time
import html as html_lib
from fastapi.responses import HTMLResponse

def clean_player_name(name):
    """Strip Flashscore trailing reason suffix from player name.

    Jul 29 2026 — the Flashscore API sometimes appends a
    reason keyword (e.g. "Abdominal strain", "Hamstring
    Injury 01.08.2026") to a player's name when they're
    unavailable. This helper removes that suffix so the
    Player column shows only the name.

    The original stripping logic lives in
    api_refresh._strip_missing_reason_suffix; we re-implement
    it here (without date stripping) so it works in the
    template without an extra import. Keep in sync with
    api_refresh._REASON_TOKENS.

    Examples:
      "Guerra Gage Abdominal strain" -> "Guerra Gage"
      "Braunshtain Barak Abdominal strain" -> "Braunshtain Barak"
      "Neymar"                       -> "Neymar"
    """
    if not name:
        return name
    name = str(name).strip()
    # Reason tokens to strip (lowercase compare). Keep in sync with
    # api_refresh._REASON_TOKENS.
    _REASONS = (
        # 3-word
        "abdominal strain", "achilles tendon injury", "achilles tendon",
        "broken leg",
        "broken finger", "broken toe", "broken arm", "muscle injury",
        "knee injury", "foot injury", "thigh injury", "back injury",
        "groin injury", "calf injury", "neck injury", "shoulder injury",
        "rib injury", "leg injury", "arm injury", "eye injury",
        "head injury", "hand injury", "wrist injury", "hip injury",
        "ankle injury", "elbow injury", "nose injury",
        # 2-word
        "abdominal injury", "achilles injury", "ankle sprain",
        "broken collarbone", "broken foot", "broken hand",
        "broken nose", "foot sprain", "groin strain", "hamstring injury",
        "hamstring strain", "illness", "knee sprain", "ligament injury",
        "ligament tear", "lower back", "muscle fatigue", "muscle strain",
        "muscle tear", "muscle problem", "neck strain", "red card",
        "rib fracture", "shoulder strain", "suspension", "yellow card",
        "yellow red card", "yellow/red card", "red cards",
        # 1-word body parts
        "abdominal", "achilles", "tendon", "pelvis", "pelvis injury",
        "knock", "knock injury",
        "ankle", "back", "calf", "eye", "elbow",
        "finger", "foot", "groin", "hamstring", "hand", "head", "heel",
        "hip", "ill", "injured", "injury", "knee", "leg", "muscle",
        "neck", "nose", "rib", "shoulder", "strain", "thigh", "toe",
        "wrist",
        # generic reasons
        "doubt", "susp", "called", "personal", "sick",
        # transfer-related (Jul 31 2026: never show in Player column)
        "transfer negotiations", "transfer negotiation", "transfer",
        "negotiations", "negotiation",
        # lower-body (Jul 31 2026: never show in Player column)
        "lower-body injury", "lower-body", "lower body injury", "lower body",
        # status
        "injury",
    )
    # Try longest match first (multi-word reasons).
    parts = name.split()
    # Strip up to 4 trailing tokens that match a reason.
    for _ in range(4):
        if not parts:
            break
        matched = False
        for n in range(min(4, len(parts)), 0, -1):
            tail = " ".join(parts[-n:]).lower()
            if tail in _REASONS:
                parts = parts[:-n]
                matched = True
                break
        if not matched:
            break
    if not parts:
        return name  # safety: don't return empty
    return " ".join(parts)


def swap_name_order(name):
    """Swap Soccerway format (Surname FirstName) to display (FirstName Surname),
    keeping prefixes like de/van/al before the surname."""
    name = re.sub(r'\s*\([^)]*\)\s*', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    parts = name.split()
    if len(parts) < 2:
        return name
    
    # Lowercase prefix set for case-insensitive matching
    prefixes_lower = {'el', 'la', 'le', 'de', 'di', 'van', 'von', 'da', 'al', 'del', 'der', 'den', 'het', 'lo'}
    
    # Soccerway format: [prefix...] Surname FirstName [FirstName2...]
    # Collect leading prefixes
    prefix_parts = []
    i = 0
    while i < len(parts) and parts[i].lower() in prefixes_lower:
        prefix_parts.append(parts[i])
        i += 1
    
    if prefix_parts and i < len(parts):
        # prefix(es) + surname + first name(s)
        # e.g. "de Roon Marten" -> prefix=["de"], surname="Roon", first="Marten"
        # e.g. "Van de Beek Donny" -> prefix=["Van","de"], surname="Beek", first="Donny"
        surname = parts[i]
        first_name = ' '.join(parts[i+1:]) if i+1 < len(parts) else ''
        full_last = ' '.join(prefix_parts + [surname])
        if first_name:
            return f"{first_name} {full_last}"
        else:
            return full_last
    else:
        # No prefix: "Surname FirstName" -> "FirstName Surname"
        last_name = parts[0]
        first_name = ' '.join(parts[1:])
        return f"{first_name} {last_name}"

def get_flag_html(country_name):
    """Get HTML with flag image from flagcdn.com (no text)"""
    if not country_name or country_name == "–":
        return "–"
    
    # Full ISO 3166-1 alpha-2 country code mapping
    country_codes = {
        'Afghanistan': 'af', 'Albania': 'al', 'Algeria': 'dz', 'Andorra': 'ad',
        'Angola': 'ao', 'Antigua and Barbuda': 'ag', 'Argentina': 'ar', 'Armenia': 'am',
        'Australia': 'au', 'Austria': 'at', 'Azerbaijan': 'az', 'Bahamas': 'bs',
        'Bahrain': 'bh', 'Bangladesh': 'bd', 'Barbados': 'bb', 'Belarus': 'by',
        'Belgium': 'be', 'Belize': 'bz', 'Benin': 'bj', 'Bhutan': 'bt',
        'Bolivia': 'bo', 'Bosnia and Herzegovina': 'ba', 'Bosnia': 'ba',
        'Botswana': 'bw', 'Brazil': 'br', 'Brunei': 'bn', 'Bulgaria': 'bg',
        'Burkina Faso': 'bf', 'Burundi': 'bi', 'Cambodia': 'kh', 'Cameroon': 'cm',
        'Canada': 'ca', 'Cape Verde': 'cv', 'Cabo Verde': 'cv',
        'Central African Republic': 'cf', 'Chad': 'td', 'Chile': 'cl', 'China': 'cn',
        'Colombia': 'co', 'Comoros': 'km',        'Congo': 'cg', 'Republic of the Congo': 'cg', 'DR Congo': 'cd',
        'Congo DR': 'cd', 'Democratic Republic of the Congo': 'cd',
        'Costa Rica': 'cr', 'Croatia': 'hr',        'Cuba': 'cu', 'Curaçao': 'cw', 'Cyprus': 'cy',
        'Czech Republic': 'cz', 'Czechia': 'cz', 'Denmark': 'dk', 'Djibouti': 'dj',
        'Dominica': 'dm', 'Dominican Republic': 'do', 'Ecuador': 'ec', 'Egypt': 'eg',
        'El Salvador': 'sv', 'Equatorial Guinea': 'gq', 'Eritrea': 'er', 'Estonia': 'ee',
        'Eswatini': 'sz', 'Swaziland': 'sz', 'Ethiopia': 'et', 'Fiji': 'fj',
        'Faroe Islands': 'fo', 'Finland': 'fi', 'France': 'fr', 'French Guiana': 'gf', 'French Polynesia': 'pf',
        'Gabon': 'ga', 'Gambia': 'gm',
        'Guadeloupe': 'gp', 'Guam': 'gu',
        'Georgia': 'ge', 'Germany': 'de', 'Ghana': 'gh', 'Gibraltar': 'gi', 'Greece': 'gr',
        'Grenada': 'gd', 'Guatemala': 'gt', 'Guinea': 'gn', 'Guinea-Bissau': 'gw',
        'Guyana': 'gy', 'Haiti': 'ht', 'Honduras': 'hn', 'Hong Kong': 'hk', 'Hungary': 'hu',
        'Iceland': 'is', 'India': 'in', 'Indonesia': 'id', 'Iran': 'ir',
        'Iraq': 'iq', 'Ireland': 'ie', 'Israel': 'il', 'Italy': 'it',
        'Ivory Coast': 'ci', "Côte d'Ivoire": 'ci', 'Jamaica': 'jm', 'Japan': 'jp',
        'Jordan': 'jo', 'Kazakhstan': 'kz', 'Kenya': 'ke', 'Kiribati': 'ki',
        'Kosovo': 'xk', 'Kuwait': 'kw', 'Kyrgyzstan': 'kg', 'Laos': 'la',
        'Latvia': 'lv', 'Lebanon': 'lb', 'Lesotho': 'ls', 'Liberia': 'lr',
        'Libya': 'ly', 'Liechtenstein': 'li', 'Lithuania': 'lt', 'Luxembourg': 'lu',
        'Macao': 'mo', 'Macau': 'mo', 'Madagascar': 'mg', 'Malawi': 'mw', 'Malaysia': 'my', 'Maldives': 'mv',
        'Mali': 'ml', 'Malta': 'mt', 'Marshall Islands': 'mh', 'Mauritania': 'mr',
        'Mauritius': 'mu', 'Mexico': 'mx', 'Micronesia': 'fm', 'Moldova': 'md',
        'Monaco': 'mc', 'Mongolia': 'mn', 'Montenegro': 'me', 'Morocco': 'ma',
        'Mozambique': 'mz', 'Myanmar': 'mm', 'Namibia': 'na', 'Nauru': 'nr',
        'Nepal': 'np', 'Netherlands': 'nl', 'New Zealand': 'nz', 'Nicaragua': 'ni',
        'New Caledonia': 'nc', 'Martinique': 'mq', 'Réunion': 're', 'Mayotte': 'yt',
        'Saint Pierre and Miquelon': 'pm', 'Saint Barthélemy': 'bl', 'Saint Martin': 'mf',
        'Wallis and Futuna': 'wf', 'French Polynesia': 'pf', 'French Guiana': 'gf',
        'Guadeloupe': 'gp', 'Clipperton Island': 'cp',
        'Niger': 'ne', 'Nigeria': 'ng', 'North Korea': 'kp', 'North Macedonia': 'mk',
        'Norway': 'no', 'Oman': 'om', 'Pakistan': 'pk', 'Palau': 'pw',
        'Palestine': 'ps', 'Panama': 'pa', 'Papua New Guinea': 'pg', 'Paraguay': 'py',
        'Peru': 'pe', 'Philippines': 'ph', 'Poland': 'pl', 'Portugal': 'pt',
        'Qatar': 'qa', 'Romania': 'ro', 'Russia': 'ru', 'Rwanda': 'rw',
        'Saint Kitts and Nevis': 'kn', 'Saint Lucia': 'lc',
        'Saint Vincent and the Grenadines': 'vc', 'Samoa': 'ws', 'San Marino': 'sm', 'Sint Maarten': 'sx',
        'Sao Tome and Principe': 'st', 'Saudi Arabia': 'sa', 'Senegal': 'sn',
        'Serbia': 'rs', 'Seychelles': 'sc', 'Sierra Leone': 'sl', 'Singapore': 'sg',
        'Slovakia': 'sk', 'Slovenia': 'si', 'Solomon Islands': 'sb', 'Somalia': 'so',
        'South Africa': 'za', 'South Korea': 'kr', 'South Sudan': 'ss', 'Spain': 'es',
        'Sri Lanka': 'lk', 'Sudan': 'sd', 'Suriname': 'sr', 'Sweden': 'se',
        'Switzerland': 'ch', 'Syria': 'sy', 'Taiwan': 'tw', 'Tajikistan': 'tj',
        'Tanzania': 'tz', 'Thailand': 'th', 'Togo': 'tg', 'Tonga': 'to',
        'Trinidad and Tobago': 'tt', 'Tunisia': 'tn', 'Turkey': 'tr',
        'Turkmenistan': 'tm', 'Tuvalu': 'tv', 'Uganda': 'ug', 'Ukraine': 'ua',
        'United Arab Emirates': 'ae', 'United Kingdom': 'gb',
        # Aug 14 2026: England uses the English flag (gb-eng, St George's Cross)
        # rather than the UK Union Jack (gb) — England ≠ Great Britain.
        'England': 'gb-eng',
        'Scotland': 'gb-sct', 'Wales': 'gb-wls', 'Northern Ireland': 'gb-nir',
        'USA': 'us', 'United States': 'us', 'Uruguay': 'uy', 'Uzbekistan': 'uz',
        'Vanuatu': 'vu', 'Vatican City': 'va', 'Venezuela': 've', 'Vietnam': 'vn',
        'Yemen': 'ye', 'Zambia': 'zm', 'Zimbabwe': 'zw',
    }
    
    code = country_codes.get(country_name.strip())
    
    if not code:
        for cn, cd in country_codes.items():
            if cn.lower() == country_name.strip().lower():
                code = cd
                break
    
    if not code:
        return "–"
    
    return f'<img src="https://flagcdn.com/w20/{code}.png" alt="{country_name.strip()}" style="height:14px;width:auto;vertical-align:middle;border-radius:1px;margin:0 1px;">'


def get_nat_html(p):
    """Return flag (club teams) or club badge (national teams).

    Jul 28 2026: For National Team players, Flashscore's /squad
    `country` field contains the player's club name (e.g. "Werder
    Bremen"), not the country of birth. The /players/details call
    stores club name + club logo in `club` and `club_logo` fields
    (see api_refresh.refresh_player_details). For national teams
    we render the club badge from `club_logo`; for club teams we
    keep rendering the player nationality flag.
    """
    club = p.get("club", "")
    club_logo = p.get("club_logo", "")
    # 1. National-team player with club logo → club badge
    if club and club_logo:
        return f'<span class="club-badge" data-tooltip="{club}"><img src="{club_logo}" alt="{club}" style="width:14px;height:14px;vertical-align:middle;"></span>'
    # 2. National-team player with club name only (no logo yet)
    if club:
        return f'<span class="club-badge" data-tooltip="{club}">{club[:3]}</span>'
    # 3. Club-team player — use country as flag
    country = p.get("country", "") or p.get("country_name", "")
    if country:
        flag_html = get_flag_html(country)
        if flag_html != "–" and "flagcdn" in flag_html:
            return flag_html
        return f'<span class="club-badge" data-tooltip="{country}">{country[:3].upper()}</span>'
    # 4. Legacy fallback: national field (older snapshots)
    national = p.get("national", "")
    if national and national != "–":
        flag_html = get_flag_html(national)
        if flag_html != "–" and "flagcdn" in flag_html:
            return flag_html
        return f'<span class="club-badge" data-tooltip="{national}">{national[:3]}</span>'
    return "–"
def _parse_mv(value):
    s = str(value or "").strip()
    if not s or s in {"-", "—", "?", "N/A", "n/a"}:
        return 0.0
    s = s.replace("€", "").replace(",", ".").strip().lower()
    mult = 1.0
    if s.endswith("m"):
        mult = 1_000_000.0
        s = s[:-1]
    elif s.endswith("k"):
        mult = 1_000.0
        s = s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return 0.0


def _safe_num(value, default=0.0, cast=float):
    """Safely cast a cache value to int/float.

    Soccerway may store "?" / "–" / "N/A" / empty string for unknown numeric
    fields (age, MV, apps, minutes, goals, etc.). This helper returns
    `default` for any non-numeric input instead of raising ValueError.
    """
    if value is None:
        return cast(default)
    s = str(value).strip()
    if not s or s in {"-", "—", "?", "N/A", "n/a"}:
        return cast(default)
    s = s.replace(",", "").replace("€", "").strip()
    try:
        return cast(s)
    except (ValueError, TypeError):
        return cast(default)


def render_team_view(team_id: str, embed: str = "", _travel_opp: str = "") -> HTMLResponse:
    """Render team squad page"""
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    
    # --- Попробовать live-кеш (свежие данные от Soccerway) ---
    import time as _time
    if not os.path.exists(DATA_DIR):
        alt_dir = os.path.join(os.path.dirname(__file__), "sample_workspace")
        if os.path.exists(alt_dir):
            DATA_DIR = alt_dir
    live_cache_path = os.path.join(DATA_DIR, f"_live_cache_{team_id}.json")
    team_file = None
    
    # Сначала проверяем live-кеш (свежие данные)
    LIVE_CACHE_TTL = 3600  # 1 hour
    cache_age_hours = 999.0

    if os.path.exists(live_cache_path):
        try:
            age_s = _time.time() - os.path.getmtime(live_cache_path)
            cache_age_hours = age_s / 3600
            if age_s < LIVE_CACHE_TTL:
                team_file = live_cache_path
            else:
                # Stale cache — still use as fallback, badge will show "stale"
                team_file = live_cache_path
        except Exception:
            pass
    
    # Fallback к статическому JSON
    if not team_file:
        for f in sorted(glob.glob(DATA_DIR + "/lineup_ai_*.json")):
            if team_id in f and '_api' not in f:
                team_file = f
                break
    
    # Fallback to _api file if needed
    if not team_file:
        for f in sorted(glob.glob(DATA_DIR + "/lineup_ai_*.json")):
            if team_id in f:
                team_file = f
                break

    
    if not team_file:
        # Best-effort: try to fetch team data now if cache is missing.
        # This is necessary when comparing matches whose team_id has
        # never been opened in Team mode (no cache file yet).
        team_name_hint = team_id
        try:
            from lineup_data_complete import load_complete_hierarchy
            hierarchy = load_complete_hierarchy()
            for leagues in hierarchy.values():
                if isinstance(leagues, dict):
                    for teams in leagues.values():
                        if isinstance(teams, list):
                            for team in teams:
                                if isinstance(team, dict) and str(team.get("id")) == str(team_id):
                                    team_name_hint = str(team.get("name") or team_id)
                                    raise StopIteration
        except StopIteration:
            pass
        except Exception:
            pass
        # Try to fetch team data now (sync refresh)
        try:
            from api_refresh import refresh_team
            refresh_team(team_id=team_id, force=True)
            if os.path.exists(live_cache_path):
                team_file = live_cache_path
        except Exception as _e:
            pass
        if not team_file:
            html = f"""<!doctype html>
<html><head><link rel="icon" type="image/x-icon" href="/favicon.ico"><link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/site.webmanifest"><title>{team_name_hint} - loading</title></head>
  <div style="max-width:760px;margin:60px auto;background:white;border-radius:14px;padding:28px;box-shadow:0 2px 12px rgba(0,0,0,.08);">
    <h2 style="margin-top:0;color:#333;">{team_name_hint}</h2>
    <p style="color:#666;line-height:1.5;">Team data has not been loaded yet</p>
    </div>

        

</body></html>"""
        return HTMLResponse(html)
    
    try:
        with open(team_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return HTMLResponse(f"Error loading team data: {e}", status_code=500)
    
    team_name = data.get("team", {}).get("name", "Unknown")
    # Team emblem: try "emblem" (old) or "image_path" (Flashscore) or data["image_path"] (top-level)
    team_emblem = (
        data.get("team", {}).get("emblem", "")
        or data.get("team", {}).get("image_path", "")
        or data.get("image_path", "")
    )
    players = data.get("players", [])
    matches = data.get("matches", [])
    # Check if this is a national team (team name matches country name)
    NATIONAL_TEAMS = {"Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Canada", "Cape Verde", "Central African Republic", "Chad", "Chile", "China", "Colombia", "Comoros", "Congo", "Costa Rica", "Croatia", "Cuba", "Curaçao", "Cyprus", "Czech Republic", "Denmark", "Djibouti", "Dominican Republic", "DR Congo", "Ecuador", "Egypt", "El Salvador", "England", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Ivory Coast", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kosovo", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Mauritania", "Mauritius", "Mexico", "Moldova", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nepal", "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Qatar", "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia", "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Korea", "South Sudan", "Spain", "Sudan", "Suriname", "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Togo", "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Uganda", "Ukraine", "United Arab Emirates", "United States", "USA", "Uruguay", "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe", "Scotland", "Wales", "Northern Ireland"}
    is_national_team = team_name in NATIONAL_TEAMS
    # Block favorites for national teams (any tournament)
    # Note: FR (Friendly) removed - clubs can play friendlies too
    INTERNATIONAL_TOURNAMENTS = {"WC", "EURO", "COPA", "NAT", "CON", "AAC", "AFC", "OF", "FIFA", "WCQ", "EQ", "CH"}
    has_intl_tournament = any(m.get("tournament") in INTERNATIONAL_TOURNAMENTS for m in matches)
    is_international_tournament = is_national_team or has_intl_tournament

    cache_age_seconds = None
    cache_badge_text = ""
    cache_badge_color = "#6c757d"
    try:
        if team_file == live_cache_path and os.path.exists(live_cache_path):
            cache_age_seconds = max(0, int(time.time() - os.path.getmtime(live_cache_path)))
            # Stale cache — no badge shown
    except Exception:
        cache_badge_text = ""
    
    # Get coach data
    coach = data.get("coach", {})
    coach_name = coach.get("name", "–")
    coach_nationality = coach.get("nationality", "")
    coach_name_display = swap_name_order(coach_name) if coach_name != "–" else "–"
    coach_flag_html = ""
    if coach_nationality and coach_nationality != "–":
        coach_flag_html = get_flag_html(coach_nationality)
        if coach_flag_html == "–":
            coach_flag_html = ""
    coach_display_html = coach_name_display
    if coach_flag_html and coach_flag_html.strip() and "flagcdn" in coach_flag_html:
        coach_display_html = f'{coach_name_display} <span style="margin-left:6px;">{coach_flag_html}</span>'
    
    stadium_name = data.get("stadium", "") or data.get("team", {}).get("stadium", "")
    stadium_city = data.get("city", "") or data.get("team", {}).get("city", "")
    stadium_capacity = data.get("capacity", "") or data.get("team", {}).get("capacity", "")
    # Format capacity as "12 800" with space
    cap_str = ""
    if stadium_capacity and str(stadium_capacity).strip() and str(stadium_capacity) not in ("0", "0.0", "?"):
        try:
            cap_int = int(str(stadium_capacity).replace(",", "").replace(" ", ""))
            cap_str = f" {cap_int:,}".replace(",", " ")
        except (ValueError, TypeError):
            cap_str = ""
    if stadium_name and stadium_city:
        if cap_str:
            stadium_display = f"{stadium_name} ({stadium_city}) / {cap_str.strip()}"
        else:
            stadium_display = f"{stadium_name} ({stadium_city})"
    elif stadium_name:
        stadium_display = stadium_name
    elif stadium_city:
        stadium_display = f"({stadium_city})"
    else:
        stadium_display = "–"

    # Sep 1 2026 — 🚌 travel-analytics button: shown ONLY in Match mode
    # (embed=1) next to the Stadium block, and ONLY for the AWAY team
    # iframe (Match mode renders each team in its own iframe; the parent
    # compare page passes away_id via ?travel_opp=<away_team_id> so the
    # iframe knows its opponent). Home iframes and standalone Team mode
    # pages get no button. Clicking fetches
    # /lineup_ai/api/travel?home_id=<this>&away_id=<opp> and opens a modal.
    travel_btn_html = ""
    if embed and _travel_opp:
        travel_btn_html = (
            '<button type="button" id="travel-btn" '
            'style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:6px;'
            'padding:2px 8px;font-size:14px;cursor:pointer;line-height:1.4;" '
            'title="Travel analytics: stadium distance, difficulty, time zones" '
            'onclick="openTravelModal()">🚌</button>'
        )
    
    # Normalize player field names (Flashscore API: matches_played, goals, assists, yellow_cards, red_cards, minutes_played)
    for p in players:
        if "matches_played" in p and "apps" not in p:
            p["apps"] = p["matches_played"]
        if "goals" in p and "goal" not in p:
            p["goal"] = p["goals"]
        if "assists" in p and "assist" not in p:
            p["assist"] = p["assists"]
        if "yellow_cards" in p and "yellow_card" not in p:
            p["yellow_card"] = p["yellow_cards"]
        if "red_cards" in p and "red_card" not in p:
            p["red_card"] = p["red_cards"]
        if "minutes_played" in p and "min" not in p:
            p["min"] = p["minutes_played"]

    # Calculate stats
    squad_size = len(players)
    total_age = sum(int(p.get("age", 0)) for p in players if str(p.get("age", 0)).isdigit())
    avg_age = round(total_age / squad_size, 1) if squad_size > 0 else 0
    total_apps = sum(int(p.get("apps", 0)) for p in players if str(p.get("apps", 0)).isdigit())
    total_goals = sum(int(p.get("goal", 0)) for p in players if str(p.get("goal", 0)).isdigit())
    total_assists = sum(int(p.get("assist", 0)) for p in players if str(p.get("assist", 0)).isdigit())
    total_yellow = sum(int(p.get("yellow_card", 0)) for p in players if str(p.get("yellow_card", 0)).isdigit())
    total_red = sum(int(p.get("red_card", 0)) for p in players if str(p.get("red_card", 0)).isdigit())
    # starting_players calculated below after auto-calculation of impact_score
    total_value = round(sum(_parse_mv(p.get("market_value", 0)) for p in players) / 1_000_000.0, 1)
    
    def fmt_mv(val):
        """Format market value: <1000 → € Xm, >=1000 → € X.XXbn"""
        if val >= 1000:
            bn = val / 1000.0
            return f"€{bn:.2f}bn" if bn < 10 else f"€{bn:.1f}bn"
        return f"€{val:.1f}m"
    
    total_value_display = fmt_mv(total_value)

    max_goals = max((int(p.get("goal", 0)) for p in players if str(p.get("goal", 0)).isdigit()), default=0)
    goal_leaders = [swap_name_order(p.get("name", "–")) for p in players if str(p.get("goal", 0)).isdigit() and int(p.get("goal", 0)) == max_goals and max_goals > 0]
    unique_goal_leader = goal_leaders[0] if len(goal_leaders) == 1 else None

    max_assists = max((int(p.get("assist", 0)) for p in players if str(p.get("assist", 0)).isdigit()), default=0)
    assist_leaders = [swap_name_order(p.get("name", "–")) for p in players if str(p.get("assist", 0)).isdigit() and int(p.get("assist", 0)) == max_assists and max_assists > 0]
    unique_assist_leader = assist_leaders[0] if len(assist_leaders) == 1 else None
    
    fav_css = ""
    fav_js = ""
    fav_link = ""
    fav_attrs = "" 

    # Sort players by minutes played (descending)
    sorted_players = sorted(players, key=lambda x: int(x.get('min', '0')) if x.get('min', '0') and str(x.get('min', '0')).isdigit() else 0, reverse=True)
    
    # Verify all fields are present before rendering
    # Auto-calculate impact_score and squad_role using exact formulas
    # Y = max(Apps) * 90 (Average minute team)
    max_apps = max((int(p.get('apps', '0') or 0) for p in sorted_players if str(p.get('apps', '0')).isdigit()), default=0)
    Y = max_apps * 90  # e.g. 51 * 90 = 4590

    for p in sorted_players:
        R = int(p.get('min', '0') or 0) if str(p.get('min', '0')).isdigit() else 0  # Minutes
        apps = int(p.get('apps', '0') or 0) if str(p.get('apps', '0')).isdigit() else 0
        S = int(p.get('goal', '0') or 0) if str(p.get('goal', '0')).isdigit() else 0  # Goals
        T = int(p.get('assist', '0') or 0) if str(p.get('assist', '0')).isdigit() else 0  # Assists
        G = str(p.get('position', '')).strip().upper()  # GK/DF/MF/FW

        # --- Impact Score ---
        if R == 0:
            impact = 0
        elif G == 'GK':
            impact = (R / Y) * 10 * 0.75
        else:
            # Position coefficient
            if G == 'FW':
                coeff_attack = 0.75; coeff_min = 0.25
            elif G == 'MF':
                coeff_attack = 0.55; coeff_min = 0.45
            elif G == 'DF':
                coeff_attack = 0.45; coeff_min = 0.55
            else:
                coeff_attack = 0.35; coeff_min = 0.65
            attack_part = ((S + 0.9 * T) / R) * 1000 * coeff_attack
            min_part = (R / Y) * 10 * coeff_min
            impact = attack_part + min_part

        p['impact_score'] = round(impact, 2)

        # --- Squad Role ---
        # =IF(R/Y>=0,85;"Key";IF(AND(I>=7;R>=900);"Important";IF(R/Y<0,25;"Bench";IF(R/Y<0,55;"Rotation";IF(R/Y<0,7;"Starter";"Important")))))
        ratio = R / Y if Y > 0 else 0
        if ratio >= 0.85:
            role = 'Key'
        elif impact >= 7 and R >= 900:
            role = 'Important'
        elif ratio < 0.25:
            role = 'Bench'
        elif ratio < 0.55:
            role = 'Rotation'
        elif ratio < 0.70:
            role = 'Starter'
        else:
            role = 'Important'

        p['squad_role'] = role

        player_display_name = swap_name_order(clean_player_name(p.get("name", "–")))
        p['is_goal_leader'] = bool(unique_goal_leader and player_display_name == unique_goal_leader)
        p['is_assist_leader'] = bool(unique_assist_leader and player_display_name == unique_assist_leader)
    # Starting XI stats — 0 by default (user selects players via checkboxes)
    starting_xi_impact_score = 0.0
    mv_starting_xi = 0.0
    av_age_starting_xi = 0.0
    
    # Impact Score (Last match) = sum of impact_score for START players in last match
    last_match_impact = round(sum(
        _safe_num(p.get("impact_score", 0), default=0.0)
        for p in sorted_players
        if p.get("last3") and len(p["last3"]) > 0 and p["last3"][0] == "START"
    ), 2)
    # MV (Last match) = sum of MV for START players in last match
    last_match_mv = round(sum(
        _parse_mv(p.get("market_value", 0))
        for p in sorted_players
        if p.get("last3") and len(p["last3"]) > 0 and p["last3"][0] == "START"
    ) / 1_000_000.0, 1)
    # Av.Age (Last match) = average age for START players in last match
    last_match_ages = [
        _safe_num(p.get("age", 0), default=0.0)
        for p in sorted_players
        if p.get("last3") and len(p["last3"]) > 0 and p["last3"][0] == "START" and p.get("age") not in (None, "", "?", "-", "—", "N/A")
    ]
    last_match_age = round(sum(last_match_ages) / len(last_match_ages), 1) if last_match_ages else 0.0
    # Impact Diff will be calculated in JS: Starting XI Impact Score - Last Match Impact
    impact_diff = 0.0
    
    # --- Last 3: данные о матчах (из JSON) ---
    matches_data = data.get("matches", [])
    # Берём до 3 матчей (от свежего к старому)
    last3_matches = matches_data[:3]
    # Добиваем до 3 если меньше
    while len(last3_matches) < 3:
        last3_matches.append({"date": "", "comp": "", "url": ""})

    # Missing player emoji by reason. Returns (emoji, tooltip_text, color).
    # `miss` is now a dict {emoji, reason, side} from phase2_generic._missing_emoji,
    # not a plain string. Handle both shapes for backward compatibility with
    # caches that were written before the schema was upgraded.
    # Updated Jul 22 2026: roster-management / disciplinary reasons
    # (Inactive / Coach's decision / Suspended / Rest) render as ⛔️ (gray)
    # — NEVER as the red X default that was used for injuries. This is the
    # hard rule from the skill: every missing player cell must show a
    # meaningful emoji, and the emoji must match the reason.
    def _missing_emoji(miss):
        if isinstance(miss, dict):
            reason = miss.get("reason", "") or ""
            # If the data-prep side already classified the emoji, trust it
            pre_emoji = miss.get("emoji", "")
            if pre_emoji:
                r = reason.lower()
                if pre_emoji == "🟥":
                    return '🟥', reason, '#dc3545'
                if pre_emoji == "🟨":
                    return '🟨', reason, '#d4a017'
                if pre_emoji == "📄":
                    return '📄', reason, '#6c757d'
                if pre_emoji == "🛫":
                    return '🛫', reason, '#0d6efd'
                if pre_emoji == "⛔️":
                    return '⛔️', reason, '#6c757d'
                # ❌ default for injuries/illness/broken
                return '❌', reason, '#dc3545'
            r = reason.lower()
        else:
            reason = miss or ""
            r = reason.lower()
        if "red card" in r:
            return '🟥', reason, '#dc3545'
        if "yellow card" in r:
            return '🟨', reason, '#d4a017'
        if "loan" in r:
            return '📄', reason, '#6c757d'
        if "international" in r or "duty" in r:
            return '🛫', reason, '#0d6efd'
        # Roster-management / disciplinary → ⛔️ (gray).
        # Was previously a red X (injury default) — that was wrong because
        # Inactive / Coach's decision are NOT injuries.
        roster_kw = ("inactive", "coach's decision", "coaches decision",
                     "suspended", "lacking match fitness", "rest")
        if any(kw in r for kw in roster_kw):
            return '⛔️', reason, '#6c757d'
        # Default: injury, illness, broken, health, heart, etc → red X
        return '❌', reason, '#dc3545'

    # Строим HTML-ячейки для last3 каждого игрока
    def _last3_cells(p):
        last3 = p.get("last3", [])
        missing = p.get("last3_missing", [None, None, None])
        captains = p.get("last3_captain", [False, False, False])
        while len(last3) < 3:
            last3.append("—")
        while len(missing) < 3:
            missing.append(None)
        while len(captains) < 3:
            captains.append(False)
        cells = ""
        for i, val in enumerate(last3[:3]):
            miss = missing[i] if i < len(missing) else None
            is_capt = captains[i] if i < len(captains) else False
            if is_capt:
                # Jul 25 2026: captain takes priority — green circle with white
                # check mark in every last3 cell where the player was captain,
                # regardless of START/SUB/missing. User spec: "видеть кто был
                # капитаном в каждой из последних трех игр".
                cells += '<td style="text-align:center;vertical-align:middle;"><div style="width:20px;height:20px;border-radius:50%;background:#17843f;display:inline-flex;vertical-align:middle;align-items:center;justify-content:center;" title="Captain"><span style="color:white;font-size:12px;line-height:1;">✓</span></div></td>'
            elif val == "START":
                cells += '<td style="text-align:center;vertical-align:middle;"><div style="width:20px;height:20px;border-radius:50%;background:#17843f;display:inline-block;vertical-align:middle;"></div></td>'
            elif val == "SUB":
                cells += '<td style="text-align:center;vertical-align:middle;"><div style="width:20px;height:20px;border-radius:50%;background:#e3a035;display:inline-block;vertical-align:middle;"></div></td>'
            elif miss:
                emoji, reason, color = _missing_emoji(miss)
                # Escape the reason for HTML attribute (handles quotes/apostrophes)
                safe_reason = html_lib.escape(reason, quote=True)
                cells += f'<td style="text-align:center;vertical-align:middle;cursor:help;" data-tooltip="{safe_reason}"><span style="font-size:14px;color:{color};">{emoji}</span></td>'
            else:
                cells += '<td style="text-align:center;vertical-align:middle;"></td>'
        return cells

    players_rows = ""
    for p in sorted_players:
        last3 = p.get("last3", [])
        last_start = "START" if (last3 and len(last3) > 0 and last3[0] == "START") else ""
        player_display_name = swap_name_order(clean_player_name(p.get("name", "–")))
        try:
            player_impact = _safe_num(p.get("impact_score", 0), default=0.0)
        except Exception:
            player_impact = 0.0
        try:
            player_minutes = int(str(p.get("min", 0) or 0).replace(",", ""))
        except Exception:
            player_minutes = 0
        pos_code = str(p.get("position", "") or "").upper()
        df_aliases = {"DF", "D", "DEF", "DEFENDER", "CB", "LB", "RB", "LWB", "RWB"}
        mf_aliases = {"MF", "M", "MID", "MIDFIELDER", "CM", "DM", "AM", "LM", "RM"}
        df_fire = ' <span title="Attacking Defender">🎯</span>' if pos_code in df_aliases and player_impact >= 6 and player_minutes >= 900 else ""
        mf_lightning = ' <span title="Creative Midfielder">🎨</span>' if pos_code in mf_aliases and 5 <= player_impact <= 6.99 and player_minutes >= 900 else ""
        star_impact = ' <span title="Very Strong Player">⭐️</span>' if 7 <= player_impact <= 8.99 and player_minutes >= 900 else ""
        wc_attr = "wc" if is_international_tournament else ""
        top_impact = ' <span title="World-Class Player">👑</span>' if player_impact >= 9 and player_minutes >= 900 else ""
        top_scorer_badge = ' <span title="Top Scorer">⚽️</span>'
        top_assist_badge = ' <span title="Top Assist">👟</span>'
        player_row = f"""
            <tr data-last="{last_start}" data-player-name="{p.get("name", "–")}" data-player-number="{p.get("number", "–")}">
                <td style="text-align:center;padding:4px 2px;"><span class="player-number-circle" data-player-name="{player_display_name}" data-player-number="{p.get('number', '?')}" data-player-club="{team_name}" data-is-wc="{wc_attr}" onclick="toggleFavorite(this)" style="display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:#e9ecef;color:#495057;font-size:12px;font-weight:700;cursor:pointer;transition:all 0.2s;">{p.get('number', '?')}</span></td>
                <td style="text-align:center;">{get_nat_html(p)}</td>
<td class="player-name" style="white-space:nowrap;">{"<strong>" + player_display_name + df_fire + mf_lightning + star_impact + top_impact + (top_scorer_badge if (unique_goal_leader and player_display_name == unique_goal_leader) else "") + (top_assist_badge if (unique_assist_leader and player_display_name == unique_assist_leader) else "") + "</strong>" if (unique_goal_leader and player_display_name == unique_goal_leader) or (unique_assist_leader and player_display_name == unique_assist_leader) else player_display_name + df_fire + mf_lightning + star_impact + top_impact}</td>
                <td class="status-cell"><div class="status-wrapper"><span class="status-emoji-display">✅</span><span class="status-chevron">▼</span><select class="status-select" onchange="updateStatusIcon(this)"><option value="Available">✅ Available</option><option value="Doubt">❓ Doubt</option><option value="Doubt + Last yellow card">⚠️ Doubt + Last yellow card</option><option value="Injury">❌ Injury</option><option value="Red card">🟥 Red card</option><option value="Yellow red card">🟥 Yellow/red card</option><option value="Last Yellow card">🟨 Last Yellow card</option><option value="Not playing (Called up)">✈️ Not playing (Called up)</option><option value="Not playing (Other)">🚫 Not playing (Other)</option><option value="Return (Injury)">🔙 Return (Injury)</option><option value="Return (Susp)">🔙 Return (Susp)</option><option value="Return (Called up)">🔙 Return (Called up)</option><option value="Return (Other)">🔙 Return (Other)</option><option value="New player">🆕 New player</option><option value="Left the team">🚪 Left the team</option></select></div></td>
                <td style="text-align:center;padding:4px 2px;">{p["age"] if p.get("age") not in (None, "", 0) and str(p.get("age", "")).strip() not in ("–", "—", "-", "?", "N/A") else ""}</td>
                <td class="col-mv" style="text-align:center;">{p["market_value"] if p.get("market_value") not in (None, "", 0) and str(p.get("market_value", "")).strip() not in ("–", "—", "-", "?", "N/A") else ""}</td>
                <td class="pos-{p.get("position", "").lower()}" style="color:#000;font-weight:400;text-align:center;padding:4px 2px;">{p.get("position", "–")}</td>
                <td class="col-role" style="text-align:center;"><span class="squad-role {p.get('squad_role', '').lower()}">{p.get("squad_role", "–") if p.get("squad_role") else "–"}</span></td>
                <td class="col-is" style="text-align:center;">{p.get("impact_score", "–") if p.get("impact_score") is not None else "–"}</td>
                <td style="text-align:center;vertical-align:middle;"><input type="checkbox" name="player" value="{p.get("name", "–")}" class="squad-checkbox" style="width:20px;height:20px;border-radius:50%;border:2px solid #333;background:#e0e0e0;cursor:pointer;appearance:none;-webkit-appearance:none;-moz-appearance:none;vertical-align:middle;" onchange="if(this.checked){{this.style.background='#000';this.style.border='none';}}else{{this.style.background='#e0e0e0';this.style.border='2px solid #333';}}"></td>
                <td style="text-align:center;vertical-align:middle;"><input type="checkbox" name="possible_xi" value="{p.get("name", "–")}" class="xi-checkbox" style="width:20px;height:20px;border-radius:50%;border:2px solid #667eea;background:#e0e0e0;cursor:pointer;appearance:none;-webkit-appearance:none;-moz-appearance:none;transition:all 0.2s;vertical-align:middle;" onchange="updateXICounter(this)"></td>
                <td style="text-align:center;vertical-align:middle;"><input type="checkbox" name="starting_xi" value="{p.get("name", "–")}" class="starting-checkbox" style="width:20px;height:20px;border-radius:50%;border:2px solid #dc3545;background:#e0e0e0;cursor:pointer;appearance:none;-webkit-appearance:none;-moz-appearance:none;transition:all 0.2s;vertical-align:middle;" onchange="updateStartingCounter(this)"></td>
                {_last3_cells(p)}
                <td style="text-align:center;padding:4px 2px;border-left:1px solid #ddd;">{p.get("apps", "–")}</td>
                <td style="text-align:center;">{p.get("min", "–")}</td>
                <td style="text-align:center;padding:4px 2px;">{p.get("goal", "–")}</td>
                <td style="text-align:center;padding:4px 2px;">{p.get("assist", "–")}</td>
                <td style="text-align:center;padding:4px 2px;">{p.get("yellow_card", "–")}</td>
                <td style="text-align:center;padding:4px 2px;">{p.get("red_card", "–")}</td>
            </tr>
        """
        players_rows += player_row

    # --- Last 3: заголовок (две строки) ---
    # Строка 1: "Last 3" (colspan=3)
    # Строка 2: дата + турнир для каждого матча
    def _full_comp_name(comp):
        raw = str(comp or "").strip()
        key = raw.upper().replace(".", "")
        mapping = {
            "L1": "Ligue 1", "L2": "Ligue 2", "PL": "Premier League", "CH": "Championship",
            "LL": "La Liga", "SA": "Serie A", "BL": "Bundesliga", "B2": "2. Bundesliga",
            "ERE": "Eredivisie", "LGP": "Liga Portugal", "JPL": "Jupiler Pro League",
            "SL": "Super League", "SUP": "Superliga", "ALL": "Allsvenskan",
            "ELT": "Eliteserien", "MLS": "Major League Soccer",
            "VYS": "Vysshaya Liga", "VEI": "Veikkausliiga", "ALE": "A-League",
            "FA": "FA Cup", "CDF": "Coupe de France", "CL": "Champions League", "CLQ": "Champions League Qual.",
            "EL": "Europa League", "ECL": "Conference League", "EBL": "efbet League", "J1L": "J1 League", "CCL": "CONCACAF Champions Cup", "LGC": "Leagues Cup",
            "DFB": "DFB Pokal", "CDR": "Copa del Rey",
            "COI": "Coppa Italia", "KNVB": "KNVB Beker", "BCP": "Belgian Cup",
            "NMC": "NM Cup", "LPC": "Landspokal Cup", "SWC": "Swiss Cup",
            "TDP": "Taca de Portugal", "BLC": "Belarusian Cup", "LIC": "Liiga Cup", "SUC": "Suomen Cup",
            "LC": "League Cup", "CUP": "National Cup",
            "FIC": "FIFA Intercontinental Cup", "SCP": "Super Cup",
            "FR": "Friendly", "UNK": "Other Competition", "WC": "World Championship",
        }
        return mapping.get(key, raw or "Match")

    last3_header_row1 = '<th colspan="3" style="text-align:center;font-size:11px;padding:6px 4px;border-bottom:1px solid #e0e0e0;">Last 3</th>'
    last3_header_cells = ""
    for m in last3_matches:
        # New Flashscore-driven format: {date, tournament_name_short, tournament_name_full,
        #   home_team, away_team, score ("1-1"), side, match_id}
        # Fallback to old Soccerway format if new fields absent.
        date_str = m.get("date", "")
        comp_short = m.get("tournament_name_short") or m.get("comp") or m.get("tournament") or ""
        comp_full = m.get("tournament_name_full") or _full_comp_name(comp_short)
        # home_team/away_team may be dict (Flashscore) or string (old)
        ht = m.get("home_team")
        at = m.get("away_team")
        if isinstance(ht, dict):
            home_t = ht.get("name", "")
        else:
            home_t = ht or ""
        if isinstance(at, dict):
            away_t = at.get("name", "")
        else:
            away_t = at or ""
        score_str = m.get("score", "")

        # Tooltip: full tournament name + blank line + "home vs away — h:a" +
        # blank line + stat lines. Sep 1 2026 — per-user spec:
        #   SPAIN: LaLiga2
        #   (blank)
        #   Celta Vigo B vs Andorra — 4:2
        #   (blank)
        #   xG: 2.64 — 1.98
        #   Ball possession: 35% — 65%
        #   Total shots: 10 — 17
        #   Shots on Target: 8 — 5
        #   Corner kicks: 4 — 4
        # Values are "home — away" pairs from api_refresh.fetch_match_stats
        # (stored as m["stats"]). Score is shown as h:a (colon separator),
        # converted from the stored "4-2" format.
        score_vis = score_str.replace("-", ":") if score_str else score_str
        if home_t and away_t:
            tooltip_text = f"{comp_full}\n\n{home_t} vs {away_t} — {score_vis}"
        else:
            tooltip_text = f"{comp_full}: {score_str}" if score_str else comp_full
        mstats = m.get("stats") or {}
        if mstats:
            stat_lines = []
            stat_labels = [
                ("xg", "xG"),
                ("poss", "Ball possession"),
                ("tshots", "Total shots"),
                ("sot", "Shots on Target"),
                ("corners", "Corner kicks"),
            ]
            for key, label in stat_labels:
                v = mstats.get(key)
                if v:
                    stat_lines.append(f"{label}: {v}")
            if stat_lines:
                tooltip_text += "\n\n" + "\n".join(stat_lines)
        tooltip_html = html_lib.escape(tooltip_text, quote=True)

        # Determine match result color for selected team (new format uses m["side"])
        bg_color = ""
        side = m.get("side")
        if score_str and ("-" in score_str):
            try:
                parts = score_str.split("-")
                gh = int(parts[0].strip())
                ga = int(parts[1].strip())
                if side == "home":
                    if gh > ga: bg_color = "background:#d4edda;"
                    elif gh < ga: bg_color = "background:#f8d7da;"
                    else: bg_color = "background:#fff3cd;"
                elif side == "away":
                    if ga > gh: bg_color = "background:#d4edda;"
                    elif ga < gh: bg_color = "background:#f8d7da;"
                    else: bg_color = "background:#fff3cd;"
            except (ValueError, IndexError):
                pass
            # Fallback: old regex-based detection if new side field missing
            if not bg_color and not side:
                score_match = re.match(r'(.+?)\s+(\d+)\s*-\s*(\d+)\s+(.+)', score_str)
                if score_match:
                    team1_name = score_match.group(1).strip()
                    goals1 = int(score_match.group(2))
                    goals2 = int(score_match.group(3))
                    team2_name = score_match.group(4).strip()
                    team_name_lower = team_name.lower()
                    is_team1 = team_name_lower in team1_name.lower() or team1_name.lower() in team_name_lower
                    is_team2 = team_name_lower in team2_name.lower() or team2_name.lower() in team_name_lower
                    if is_team1 and not is_team2:
                        if goals1 > goals2: bg_color = "background:#d4edda;"
                        elif goals1 < goals2: bg_color = "background:#f8d7da;"
                        else: bg_color = "background:#fff3cd;"
                    elif is_team2 and not is_team1:
                        if goals2 > goals1: bg_color = "background:#d4edda;"
                        elif goals2 < goals1: bg_color = "background:#f8d7da;"
                        else: bg_color = "background:#fff3cd;"

        last3_header_cells += f'<th class="last3-tooltip" style="text-align:center;font-size:10px;padding:2px 2px;line-height:1.2;white-space:nowrap;border-top:none;cursor:default;width:37px;{bg_color}" data-tooltip="{tooltip_html}">{date_str}<br><span style="font-weight:400;color:#888;">{html_lib.escape(comp_short, quote=True)}</span></th>'
    
    # Team emblem (loaded from Soccerway squad page; falls back to initials if missing)
    if team_emblem:
        team_logo_html = f'<img class="team-emblem" src="{html_lib.escape(team_emblem, quote=True)}" alt="{html_lib.escape(team_name, quote=True)}" loading="lazy" onerror="this.outerHTML=\'<span class=&quot;team-emblem-fallback&quot;>{html_lib.escape(team_name[:1].upper(), quote=True)}</span>\'" />'
    else:
        team_logo_html = f'<span class="team-emblem team-emblem-fallback">{html_lib.escape(team_name[:1].upper(), quote=True)}</span>'

    # Top 3 players by impact_score, filtered to Key/Important/Starter roles only
    _top3 = sorted(
        [p for p in sorted_players
         if _safe_num(p.get("impact_score", 0), default=0.0) > 0
         and p.get("squad_role") in ("Key", "Important", "Starter")],
        key=lambda p: _safe_num(p.get("impact_score", 0), default=0.0),
        reverse=True
    )[:3]
    _top3_rows = []
    for idx, p in enumerate(_top3, 1):
        _name = swap_name_order(p.get("name", "–"))
        _is = _safe_num(p.get("impact_score", 0), default=0.0)
        _pos = str(p.get("position", "") or "").strip().upper()
        # Compact position label
        if _pos in ("GK",):
            _pos_label = "GK"
        elif _pos in ("DF",):
            _pos_label = "DF"
        elif _pos in ("MF",):
            _pos_label = "MF"
        elif _pos in ("FW",):
            _pos_label = "FW"
        else:
            _pos_label = _pos[:2] if _pos else ""
        _top3_rows.append(
            f'<div style="display:flex;align-items:center;gap:6px;padding:3px 0;">'
            f''
            f'<span style="background:#f0f2fa;color:#333;font-weight:600;font-size:10px;padding:1px 5px;border-radius:3px;min-width:24px;text-align:center;">{_pos_label}</span>'
            f'<span style="flex:1;font-size:12px;color:#333;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{_name}</span>'
            f'<span style="color:#333;font-weight:600;font-size:12px;">{_is:.2f}</span>'
            f'</div>'
        )
    top3_players_html = "".join(_top3_rows) if _top3_rows else '<div style="font-size:11px;color:#999;text-align:center;">No data</div>'


    # Positional overview: count GK/DF/MF/FW
    _pos_counts = {"GK": 0, "DF": 0, "MF": 0, "FW": 0}
    for _pp in sorted_players:
        _pp_pos = str(_pp.get("position", "") or "").strip().upper()
        if _pp_pos in _pos_counts:
            _pos_counts[_pp_pos] += 1
        elif _pp_pos in ("D", "M", "F", "G"):
            # some sources use single-letter
            _norm = {"G": "GK", "D": "DF", "M": "MF", "F": "FW"}.get(_pp_pos)
            if _norm:
                _pos_counts[_norm] += 1
    _pos_labels = [("GK", "GK"), ("DF", "DF"), ("MF", "MF"), ("FW", "FW")]
    _pos_pills = []
    for _plabel, _pkey in _pos_labels:
        _pcount = _pos_counts[_pkey]
        _pos_pills.append(
            f'<span style="display:inline-flex;align-items:center;gap:4px;background:#f0f2fa;border-radius:4px;padding:2px 6px;">'
            f'<span style="color:#333;font-weight:700;font-size:11px;">{_plabel}</span>'
            f'<span style="color:#333;font-weight:600;font-size:11px;">{_pcount}</span>'
            f'</span>'
        )
    positional_overview_html = (
        f'<div style="display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:wrap;">'
        + "".join(_pos_pills)
        + '</div>'
    )

    html = f"""<!doctype html>
<html>
<head>
    <link rel="icon" type="image/x-icon" href="/favicon.ico"><link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/site.webmanifest">
    <meta charset="utf-8">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>{team_name} - Squad | LineUp AI</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            margin: 0;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(to right, #043fb6 0%, #2e7af8 100%);
            color: white;
            padding: 16px 40px;
            display: flex;
            align-items: center;
            gap: 24px;
            flex-wrap: wrap;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
            white-space: nowrap;
        }}
        .team-title {{
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 0;
        }}
        .team-emblem {{
            width: 36px;
            height: 36px;
            object-fit: contain;
            flex-shrink: 0;
            background: rgba(255, 255, 255, 0.15);
            border-radius: 8px;
            padding: 4px;
        }}
        .team-emblem-fallback {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            font-weight: 600;
            color: #fff;
            background: rgba(255, 255, 255, 0.20);
            border-radius: 8px;
        }}
        .header-tabs {{
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }}
        .header-tabs .tab {{
            padding: 6px 14px;
            font-size: 13px;
            border-radius: 4px;
            color: white;
            background: rgba(255,255,255,0.15);
            border: 1px solid rgba(255,255,255,0.3);
            cursor: pointer;
        }}
        .header-tabs .tab:hover {{
            background: rgba(255,255,255,0.25);
        }}
        .header-tabs .tab.active {{
            background: rgba(255,255,255,0.35);
            border-color: rgba(255,255,255,0.5);
        }}
        .header a {{
            color: white;
            text-decoration: none;
            padding: 6px 12px;
            background: rgba(255,255,255,0.2);
            border-radius: 6px;
            transition: background 0.2s;
            font-size: 13px;
            white-space: nowrap;
        }}
        .header a:hover {{
            background: rgba(255,255,255,0.3);
        }}
        .header-action-btn {{
            color: white;
            background: rgba(255,255,255,0.15);
            border: 1px solid rgba(255,255,255,0.3);
            border-radius: 6px;
            padding: 6px 12px;
            cursor: pointer;
            font-size: 13px;
            white-space: nowrap;
            transition: background 0.2s;
            font-family: inherit;
        }}
        .header-action-btn:hover {{
            background: rgba(255,255,255,0.25);
        }}
        .header-action-btn.active {{
            background: rgba(255,255,255,0.45);
            border-color: rgba(255,255,255,0.7);
            font-weight: 600;
        }}
        /* Aug 30 2026 — Match-mode Reverse Odds: the frame that hosts NO
           modal gets this gray highlight overlay (the parent asks one
           frame to open the modal and the other to dim itself, so BOTH
           frames read as "behind the modal"). Same rgba as the modal
           host backdrop below, so both frames dim IDENTICALLY. Sits
           below the modal host (z-index 99999) and intercepts clicks on
           the dimmed frame (they close the modal via the parent). */
        body.ro-dim::after {{
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.55);
            z-index: 99998;
            pointer-events: auto;
        }}
        .container {{
            padding: 0 32px 24px 32px;
            max-width: 1400px;
            margin: 0 auto;
        }}
        .main-layout {{
            display: flex;
            flex-direction: column;
            gap: 20px;
            align-items: center;
        }}
        .main-table {{
            margin-left: 0;
            margin-right: auto;
            min-width: 0;
            overflow-x: visible;
        }}
        .main-table > .table-container {{
            width: 964px;
            max-width: 100%;
        }}
        .main-table tbody tr {{
            height: 22px;
        }}
        .main-table tbody td {{
            padding: 0 2px !important;
            line-height: 22px;
            font-size: 13px;
        }}
        .main-table tbody td.player-name {{
            padding: 0 6px !important;
        }}
        .stats-sidebar {{
            width: 180px;
            flex-shrink: 0;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        .stats-sidebar .stat-card {{
            padding: 12px 10px;
        }}
        .stats-sidebar .stat-value {{
            font-size: 20px;
        }}
        .stats-sidebar .stat-label {{
            font-size: 10px;
        }}
        .tabs {{ display: none; }}
        .tab {{
            padding: 10px 20px;
            background: rgba(255,255,255,0.15);
            border: 1px solid rgba(255,255,255,0.3);
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
            font-size: 13px;
            color: white;
            transition: all 0.2s;
        }}
        .tab:hover {{
            background: rgba(255,255,255,0.25);
        }}
        .tab.active {{
            background: rgba(255,255,255,0.35);
            border-color: rgba(255,255,255,0.5);
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            text-align: center;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 4px;
        }}
        .stat-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .table-container {{
            position: relative;
            background: white;
            border-radius: 12px;
            overflow: visible;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        .table-container::before {{
            content: "@LineupValue";
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) rotate(-45deg);
            font-size: 120px;
            font-weight: bold;
            color: rgba(180, 180, 180, 0.35);
            pointer-events: none;
            white-space: nowrap;
            z-index: 1;
        }}
        table {{
            position: relative;
            z-index: 0;
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
            border: 1px solid #e0e0e0;
        }}
        .hide-watermark .table-container::before {{
            display: none;
        }}
        .player-name {{
            white-space: nowrap !important;
        }}
        th {{
            background: #f8f9fa;
            padding: 14px 16px;
            text-align: left;
            font-weight: 600;
            color: #444;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 2px solid #e0e0e0;
            border-right: 1px solid #e8e8e8;
            white-space: nowrap;
        }}
        td {{
            padding: 12px 16px;
            border-bottom: 1px solid #f0f0f0;
            border-right: 1px solid #f0f0f0;
            color: #333;
        }}
        th:last-child, td:last-child {{
            border-right: none;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .pos-gk {{ color: #28a745; font-weight: bold; }}
        .pos-def {{ color: #17a2b8; font-weight: bold; }}
        .pos-mid {{ color: #ffc107; font-weight: bold; }}
        .pos-att {{ color: #dc3545; font-weight: bold; }}
        .status-start {{ color: #28a745; font-weight: bold; }}
        .status-sub {{ color: #ffc107; font-weight: bold; }}
        .status-bench {{ color: #6c757d; font-weight: bold; }}
        .impact-high {{ color: #28a745; font-weight: bold; }}
        .impact-med {{ color: #ffc107; font-weight: bold; }}
        .impact-low {{ color: #6c757d; font-weight: bold; }}
        .squad-role {{
            background: #e9ecef;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            text-transform: capitalize;
        }}
        .squad-role.key {{ background: #d4edda; color: #000; border: 2px solid #28a745; }}
        .squad-role.important {{ background: #d1ecf1; color: #000; border: 2px solid #17a2b8; }}
        .squad-role.starter {{ background: #fff3cd; color: #000; border: 2px solid #856404; }}
        .squad-role.rotation {{ background: #e2e3e4; color: #000; border: 2px solid #6c757d; }}
        .squad-role.bench {{ background: #f8d7da; color: #000; border: 2px solid #dc3545; }}
        /* Aug 14 2026: Collapse Details — toggle MV / Squad Role / Impact Score columns
           via the header button in Match Mode. The compare-template postMessages
           a "setDetailsCollapsed" event on load and on every toggle; we add/remove
           the `detail-hidden` class on <body> so a single CSS rule hides all three
           columns across thead and tbody without touching layout. */
        .detail-hidden .col-mv,
        .detail-hidden .col-role,
        .detail-hidden .col-is {{ display: none !important; }}
        .last-5 {{
            display: flex;
            gap: 4px;
        }}
        .last-5 span {{
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        }}
        .last-5 .win {{ background: #d4edda; color: #155724; }}
        .last-5 .draw {{ background: #e2e3e4; color: #383d41; }}
        .last-5 .loss {{ background: #f8d7da; color: #721c24; }}
        .last-5 .start {{ background: #28a745; color: white; }}
        .last-5 .sub {{ background: #ffc107; color: #333; }}
        .last-5 .none {{ background: #e9ecef; color: #6c757d; }}
        .status-cell {{ padding: 0; }}
        .status-wrapper {{ position: relative; display: inline-flex; align-items: center; background: #f5f5f5; border: 1px solid #ccc; border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 14px; white-space: nowrap; }}
        .status-emoji-display {{ font-size: 16px; line-height: 1; }}
        .status-chevron {{ font-size: 10px; color: #666; margin-left: 3px; line-height: 1; }}
        .status-select {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }}
        .status-red {{ color: red !important; font-weight: bold !important; text-decoration: line-through !important; }}
        .status-green {{ color: green !important; font-weight: bold !important; text-decoration: underline !important; }}
        .status-orange {{ color: orange !important; font-weight: bold !important; text-decoration: underline !important; }}
        tr.missing-from-last td {{ background-color: #F5A3A3 !important; }}

        .page-content {{
            display: flex;
            gap: 12px;
            align-items: flex-start;
            padding: 0 16px 16px 5px;
            margin: 0;
        }}
        .team-nav-sidebar {{
            width: 255px;
            flex-shrink: 0;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            padding: 12px;
            z-index: 50;
            font-size: 13px;
        }}
        .page-main {{
            flex: 1;
            min-width: 0;
        }}

        .team-nav-sidebar select {{
            width: 100%;
            padding: 6px 8px;
            padding-right: 24px;
            border: 1px solid #d5d9e8;
            border-radius: 6px;
            font-size: 13px;
            margin-bottom: 8px;
            background: #f8f9fc;
            color: #333;
            appearance: none;
            -webkit-appearance: none;
            -moz-appearance: none;
        }}
        /* Custom ▼ arrow for Championship/Team/Match selects (matches Country dropdown) */
        .team-nav-sidebar .select-wrapper {{
            position: relative;
            width: 100%;
        }}
        .team-nav-sidebar .select-wrapper::after {{
            content: "▼";
            position: absolute;
            right: 10px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 9px;
            color: #888;
            pointer-events: none;
        }}
        .team-nav-sidebar select:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .team-nav-sidebar label {{
            display: block;
            font-size: 11px;
            color: #888;
            margin-bottom: 2px;
            margin-top: 4px;
        }}
        /* Right-side X/Twitter feed sidebar (Team mode). */
        .tweets-sidebar {{
            position: fixed;
            top: 64px;
            right: 12px;
            width: 400px;
            max-height: 790px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            z-index: 40;
            display: flex;
            flex-direction: column;
            font-size: 13px;
            overflow: hidden;
            transition: opacity 0.2s ease;
        }}
        body.embed-mode .tweets-sidebar {{ display: none !important; }}
        .tweets-sidebar.hidden {{ display: none !important; }}
        .tweets-sidebar-header {{
            padding: 10px 12px;
            border-bottom: 1px solid #e5e7eb;
            font-weight: 700;
            font-size: 13px;
            color: #1f2937;
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: linear-gradient(135deg, #f8f9fc 0%, #eef1f8 100%);
            flex-shrink: 0;
        }}
        .tweets-sidebar-header .tweets-count {{
            font-size: 11px;
            color: #6b7280;
            font-weight: 500;
        }}
        .tweets-sidebar-list {{
            overflow-y: auto;
            overflow-x: hidden;
            flex: 1;
            padding: 8px;
        }}
        .tweet-card {{
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 8px 10px;
            margin-bottom: 8px;
            background: #fff;
            font-size: 12px;
            line-height: 1.4;
        }}
        .tweet-card:hover {{ background: #f8f9fc; }}
        .tweet-source {{
            font-weight: 600;
            color: #1d9bf0;
            margin-bottom: 4px;
            font-size: 11px;
        }}
        .tweet-text {{
            color: #1f2937;
            white-space: pre-wrap;
            word-wrap: break-word;
            margin-bottom: 4px;
        }}
        .tweet-text mark.player {{
            background: #fef08a;
            color: #713f12;
            padding: 0 2px;
            border-radius: 2px;
            font-weight: 600;
        }}
        /* Aug 7 2026: drop green highlight on keywords — use subtle bold/color only. */
        .tweet-text mark.keyword {{
            background: transparent;
            color: #14532d;
            font-weight: 700;
        }}
        /* Aug 7 2026: read state — fade out tweets the user has clicked on. */
        .tweet-card.read {{ opacity: 0.55; }}
        .tweet-card {{ cursor: pointer; }}
        /* Aug 7 2026: live event card (mirrored from Telegram @LineupValue_LIVE). */
        .tweet-card.live-event {{
            background: #fff7ed;
            border-left: 4px solid #f59e0b;
            padding-left: 8px;
        }}
        .tweet-card.live-event .tweet-source {{ color: #c2410c; }}
        .tweet-card.live-event .tweet-line {{ display: block; }}
        .tweet-card.live-event .tweet-event {{
            font-weight: 700;
            font-size: 13px;
            color: #1f2937;
            margin-top: 4px;
        }}
        .tweet-meta {{
            font-size: 10px;
            color: #9ca3af;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .tweet-meta a {{
            color: #1d9bf0;
            text-decoration: none;
        }}
        .tweet-meta a:hover {{ text-decoration: underline; }}
        .tweet-empty {{
            text-align: center;
            padding: 24px 12px;
            color: #9ca3af;
            font-size: 12px;
        }}
        body.embed-mode .tweets-sidebar {{ display: none !important; }}

                body.embed-mode .team-nav-sidebar {{ display: none !important; }}
        /* Country favorites — star button */
        .country-fav-star {{
            display: inline-block;
            width: 18px;
            text-align: center;
            cursor: pointer;
            color: #cbd5e0;
            font-size: 14px;
            line-height: 1;
            margin-left: 6px;
            text-decoration: none;
            user-select: none;
            vertical-align: middle;
        }}
        .country-fav-star:hover {{ color: #fbbf24; }}
        .country-fav-star.is-fav {{ color: #f59e0b; }}
        /* Custom country dropdown (replaces native <select> to allow flag images) */
        .nav-country-dropdown {{
            position: relative;
            width: 100%;
            margin-bottom: 8px;
        }}
        .nav-dropdown-trigger {{
            width: 100%;
            display: flex;
            align-items: center;
            padding: 6px 8px;
            border: 1px solid #d5d9e8;
            border-radius: 6px;
            font-size: 13px;
            background: #f8f9fc;
            color: #333;
            cursor: pointer;
            text-align: left;
            font-family: inherit;
        }}
        .nav-dropdown-trigger:hover {{ background: #eef1f8; }}
        .nav-dropdown-trigger:focus {{ outline: 2px solid #2e7af8; outline-offset: 1px; }}
        .nav-dropdown-arrow {{ font-size: 9px; color: #888; transition: transform 0.15s; }}
        .nav-dropdown-trigger[aria-expanded="true"] .nav-dropdown-arrow {{ transform: rotate(180deg); }}
        .nav-dropdown-list {{
            position: fixed;
            max-height: 520px;
            overflow-y: auto;
            background: white;
            border: 1px solid #d5d9e8;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.12);
            z-index: 10000;
            padding: 4px 0;
            margin: 0;
            list-style: none;
            min-width: 200px;
        }}
        .nav-dropdown-list li {{
            display: flex;
            align-items: center;
            padding: 5px 8px;
            cursor: pointer;
            font-size: 13px;
            color: #333;
        }}
        .nav-dropdown-list li:hover {{ background: #f0f4ff; }}
        .nav-dropdown-list li.selected {{ background: #e0e9ff; font-weight: 600; }}
        .nav-dropdown-list li img {{
            height: 14px;
            width: auto;
            vertical-align: middle;
            border-radius: 1px;
            margin-right: 6px;
        }}
        .my-squads-sidebar {{
            width: 255px;
            flex-shrink: 0;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            padding: 12px;
            font-size: 13px;
            z-index: 50;
        }}
        .my-squads-title {{
            font-size: 15px;
            font-weight: 700;
            color: #333;
            margin-bottom: 8px;
        }}
        .my-squads-help {{
            font-size: 11px;
            color: #888;
            line-height: 1.35;
            margin-bottom: 10px;
        }}
        .snapshot-list-item {{
            border: 1px solid #e6e9f2;
            border-left: 4px solid #667eea;
            border-radius: 8px;
            padding: 8px;
            margin-bottom: 8px;
            background: #fff;
            cursor: pointer;
        }}
        .snapshot-list-item.active {{
            background: #f2f5ff;
            border-color: #667eea;
        }}
        .snapshot-list-name {{
            font-size: 12px;
            font-weight: 700;
            line-height: 1.25;
            color: #333;
            margin-bottom: 6px;
        }}
        .snapshot-list-actions {{
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
        }}
        .snapshot-list-actions button {{
            border: 0;
            border-radius: 5px;
            padding: 4px 6px;
            font-size: 10px;
            font-weight: 700;
            cursor: pointer;
            background: #eef1f8;
            color: #444;
        }}
        .snapshot-list-actions button:hover {{ background:#dde4f4; }}
        .snapshot-delete {{ background:#f8d7da !important; color:#842029 !important; }}
        .snapshot-empty-list {{
            color: #999;
            font-size: 12px;
            line-height: 1.4;
            padding: 8px 0;
        }}
        body.snapshot-mode .table-container {{
            outline: 3px solid #667eea;
            outline-offset: 2px;
        }}
        .snapshot-mode-banner {{
            display: none;
            background: #fff3cd;
            color: #7a5a00;
            border: 1px solid #ffe08a;
            border-radius: 8px;
            padding: 8px 12px;
            margin: 0 0 12px 0;
            font-size: 13px;
            font-weight: 700;
            /* Jul 24 2026: per user spec, the banner width was set
               to 964px first, then user asked for 922px. The two
               values are visually similar (42px difference, ~4%)
               but the user specifically asked for 922px. The
               .info-bar-* blocks (lines 1887-1915) use 964px, so
               the snapshot banner is now slightly narrower than
               the info bars. If a future request is to align
               these, the answer is 964px not 922px. */
            width: 922px;
            max-width: 100%;
            box-sizing: border-box;
        }}
        body.snapshot-mode .snapshot-mode-banner {{ display:block; }}
        .bulk-lineup-panel {{
            background: #fff;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            padding: 12px;
            margin: 0 auto 12px 0;
            width: 964px;
            max-width: 100%;
            box-sizing: border-box;
        }}
        .bulk-lineup-title {{
            font-size: 14px;
            font-weight: 800;
            color: #333;
            margin-bottom: 8px;
        }}
        .bulk-lineup-controls {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .bulk-lineup-row {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .bulk-lineup-controls select {{
            border: 1px solid #d5d9e8;
            border-radius: 8px;
            padding: 7px 8px;
            font-weight: 700;
            color: #333;
            background: #f8f9fc;
        }}
        .bulk-lineup-controls textarea, #bulk-lineup-text {{
            flex: 1;
            height: 120px;
            min-height: 120px;
            /* Jul 31 2026: removed max-height + resize:none.
               User wants to drag the textarea corner to
               resize manually while keeping the same
               default 120px appearance. */
            border: 1px solid #d5d9e8;
            border-radius: 8px;
            padding: 8px 10px;
            resize: both;
            overflow-y: auto;
            font-size: 12px;
            line-height: 1.35;
            font-family: inherit;
        }}
        .bulk-lineup-controls button, .bulk-ambiguous button, .vision-lineup-btn {{
            border: 0;
            border-radius: 8px;
            background: #2e7af8;
            color: #fff;
            font-weight: 800;
            padding: 8px 12px;
            cursor: pointer;
        }}
        .bulk-lineup-controls button, .vision-lineup-btn {{
            width: 128px;
            min-width: 128px;
            text-align: center;
        }}
        /* Auto-width override for the renamed action buttons (Go, Upload, Run AI).
           Lets each button size to its label rather than a fixed 128px. */
        .bl-action-btn {{
            width: auto !important;
            min-width: 0 !important;
            padding: 8px 14px !important;
        }}
        .vision-lineup-row {{
            display: flex;
            gap: 8px;
            align-items: center;
            font-size: 12px;
            color: #555;
            white-space: nowrap;
        }}
        .vision-lineup-row input[type="file"] {{
            flex: 1;
            border: 1px solid #d5d9e8;
            border-radius: 8px;
            padding: 6px 8px;
            background: #f8f9fc;
        }}
        .vision-lineup-status {{ font-size: 12px; font-weight: 700; }}
        /* File-name emoji (💤 / 🆗) is larger than the text status */
        #vision-file-name {{ font-size: 20px; line-height: 1; }}
        .bulk-lineup-report {{
            margin-top: 8px;
            font-size: 12px;
            line-height: 1.45;
            color: #333;
            white-space: pre-wrap;
        }}
        .bulk-lineup-report .not-found {{ color: #dc3545; font-weight: 700; }}
        .bulk-lineup-report .found {{ color: #17843f; font-weight: 700; }}
        .bulk-ambiguous {{
            margin-top: 8px;
            padding: 8px;
            border: 1px solid #ffe08a;
            background: #fff8dd;
            border-radius: 8px;
            font-size: 12px;
        }}
        .bulk-ambiguous-row {{
            display: flex;
            gap: 8px;
            align-items: center;
            margin: 5px 0;
        }}
        .bulk-ambiguous-row label {{ min-width: 150px; font-weight: 700; color: #7a5a00; }}
        .bulk-ambiguous-row select {{ flex: 1; padding: 5px; border-radius: 6px; border: 1px solid #d5c16d; }}
        .squad-checkbox:checked {{ background: #000 !important; border: none !important; }}
        .xi-checkbox:checked {{ background: #667eea !important; border: 2px solid #667eea !important; }}
        .starting-checkbox:checked {{ background: #dc3545 !important; border: 2px solid #dc3545 !important; }}
        .last3-tooltip {{
            position: relative;
        }}
        .last3-tooltip::after {{
            content: attr(data-tooltip);
            position: absolute;
            left: 50%;
            bottom: calc(100% + 8px);
            transform: translateX(-50%);
            background: rgba(30, 30, 30, 0.96);
            color: #fff;
            border-radius: 6px;
            padding: 6px 9px;
            font-size: 11px;
            font-weight: 600;
            line-height: 1.25;
            text-transform: none;
            letter-spacing: 0;
            /* Aug 31 2026 — tooltip now carries match stats (5 lines).
               Sep 1 2026 — left-aligned, and the match line
               ("Home vs Away — 4:2") must NEVER wrap: width:max-content
               sizes the box to the longest line so pre-line wrapping
               never kicks in (max-width is a tiny-screen safety net). */
            white-space: pre-line;
            width: max-content;
            max-width: min(420px, calc(100vw - 16px));
            text-align: left;
            box-shadow: 0 4px 12px rgba(0,0,0,0.22);
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            z-index: 1000;
            transition: opacity .18s ease .65s, visibility 0s linear .65s;
        }}
        .last3-tooltip:hover::after {{
            opacity: 1;
            visibility: visible;
        }}
        /* Generic cell tooltip (used by missing-player ❌/🟥/🟨/📄/🛫 cells) */
        td[data-tooltip] {{
            position: relative;
            cursor: help;
        }}
        td[data-tooltip]:hover::after {{
            content: attr(data-tooltip);
            position: absolute;
            bottom: calc(100% + 6px);
            left: 50%;
            transform: translateX(-50%);
            background: rgba(30, 30, 30, 0.96);
            color: #fff;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 11px;
            font-weight: 600;
            line-height: 1.25;
            text-transform: none;
            letter-spacing: 0;
            white-space: nowrap;
            box-shadow: 0 4px 12px rgba(0,0,0,0.22);
            opacity: 1;
            visibility: visible;
            pointer-events: none;
            z-index: 100;
        }}
        .club-badge {{
            position: relative;
        }}
        .club-badge::after {{
            content: attr(data-tooltip);
            position: absolute;
            left: 50%;
            bottom: calc(100% + 8px);
            transform: translateX(-50%);
            background: rgba(30, 30, 30, 0.96);
            color: #fff;
            border-radius: 6px;
            padding: 6px 9px;
            font-size: 11px;
            font-weight: 600;
            line-height: 1.25;
            text-transform: none;
            letter-spacing: 0;
            white-space: nowrap;
            box-shadow: 0 4px 12px rgba(0,0,0,0.22);
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            z-index: 1000;
            transition: opacity .18s ease .65s, visibility 0s linear .65s;
        }}
        .club-badge:hover::after {{
            opacity: 1;
            visibility: visible;
        }}

        /* Embed mode: remove ALL inner scrolls, parent handles scrolling */
        html.embed-mode, body.embed-mode {{ overflow: visible !important; height: auto !important; max-height: none !important; }}
        body.embed-mode .main-layout {{ overflow: visible !important; height: auto !important; max-height: none !important; }}
        body.embed-mode .table-container {{ overflow: visible !important; height: auto !important; max-height: none !important; }}
        body.embed-mode .main-table {{ overflow: visible !important; height: auto !important; }}
        body.embed-mode .content-wrapper {{ overflow: visible !important; height: auto !important; max-height: none !important; }}
        body.embed-mode .squad-table-wrapper {{ overflow: visible !important; height: auto !important; max-height: none !important; }}
        body.embed-mode .comparison-tables {{ overflow: visible !important; height: auto !important; }}
        body.embed-mode .table-scroll-wrapper {{ overflow: visible !important; height: auto !important; max-height: none !important; }}
        body.embed-mode .header {{ flex-wrap: nowrap; }}
        body.embed-mode .header-tabs {{ margin-left: auto; }}
        body.embed-mode aside.my-squads-sidebar {{ display: none !important; }}
        body.embed-mode .actions-bar {{ display: none !important; }}
        body.embed-mode .container {{ overflow: visible !important; height: auto !important; max-height: none !important; }}
        body.embed-mode .main-table {{ overflow-x: visible !important; }}
        /* Team + Match mode: bulk-lineup-panel 700px, comparison-table 254.99px.
           Both panels share bl-compare-row (980px = 700 + 9 + 254.99 + slack). */
        .bulk-lineup-panel {{ width: 700px !important; max-width: 700px !important; flex-shrink: 0 !important; box-sizing: border-box !important; }}
        #comparison-table {{
            width: 254.99px !important;
            min-width: 254.99px !important;
            max-width: 254.99px !important;
            flex-shrink: 0 !important;
            flex-grow: 0 !important;
            box-sizing: border-box !important;
            overflow: visible !important;
        }}
        /* Prevent text wrap in comparison cards */
        #comparison-table > div {{
            min-width: 0 !important;
            overflow: hidden !important;
        }}
        #comparison-table > div > span:last-child {{
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            min-width: 0 !important;
        }}
        /* Match mode: bulk-lineup-panel narrows so comparison-table (255px) can sit
           to its right within the same row, total 700 + 9 + 255 = 964px (= main table). */
        body.embed-mode .bulk-lineup-panel {{ width: 700px !important; flex-shrink: 0 !important; }}
        body.embed-mode #comparison-table {{
            width: 254.99px !important;
            min-width: 254.99px !important;
            max-width: 254.99px !important;
            flex-shrink: 0 !important;
            flex-grow: 0 !important;
            box-sizing: border-box !important;
            overflow: visible !important;
        }}
        /* Match mode: comparison-table cards must fit on one line.
           Truncate with ellipsis instead of wrapping. */
        body.embed-mode #comparison-table > div {{
            min-width: 0 !important;
            overflow: hidden !important;
        }}
        body.embed-mode #comparison-table > div > span:last-child {{
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            min-width: 0 !important;
        }}
        /* Team + Match mode: info-bar-squad-host is hidden (the 📊 emoji next to
           team name shows the same data as a hover tooltip). No standalone panel. */
        #info-bar-squad-host {{ display: none !important; }}
        /* Match mode: page-content fixed at 980px (fits main-table 964px + padding).
           page-main is flex:1 inside it, so it also becomes 980px. */
        body.embed-mode .page-content {{
            width: 980px !important;
            max-width: 100% !important;
            min-width: 0 !important;
            flex: 0 0 auto !important;
        }}
        body.embed-mode .page-main {{
            width: auto !important;
            min-width: 0 !important;
            flex: 1 1 auto !important;
        }}
        /* Match mode: team-squad-emoji shows a tooltip with info-bar-squad on hover.
           The tooltip is fixed-position so it overlays everything; size 255x258.4px. */
        .team-squad-tooltip {{
            position: fixed;
            z-index: 10001;
            width: 255px;
            height: 258.4px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.25);
            padding: 8px 10px;
            box-sizing: border-box;
            overflow: hidden;
            display: none;
            pointer-events: none;
        }}
        .team-squad-emoji:hover + .team-squad-tooltip,
        .team-squad-tooltip:hover {{
            display: block;
        }}
        /* Favorites: disabled for international tournaments */
        .player-number-circle[data-is-wc="wc"] {{
            opacity: 0.4;
            cursor: not-allowed;
        }}
        .player-number-circle[data-is-wc="wc"]:hover {{
            background: #e9ecef;
        }}
        .player-number-circle.favorite {{
            background: #28a745 !important;
            color: white;
        }}
    </style>




<script src="/icons/status-icons.js?v=4"></script>
<!-- Inline fallback (Jul 23 2026): mirrors icons/status-icons.js inline so it
     works even if the browser caches a stale version of the external file.
     Hard refresh (Ctrl+Shift+R) still helps. -->
<script>
(function() {{
  if (window.STATUS_EMOJI && window.updateStatusIcon) return;
  var STATUS_EMOJI = {{
    "Available": "✅",
    "Doubt": "❓",
    "Doubt + Last yellow card": "⚠️",
    "Injury": "❌",
    "Red card": "🟥",
    "Yellow red card": "🟥",
    "Last Yellow card": "🟨",
    "Not playing (Called up)": "✈️",
    "Not playing (Other)": "🚫",
    "Return (Injury)": "🔙",
    "Return (Susp)": "🔙",
    "Return (Called up)": "🔙",
    "Return (Other)": "🔙",
    "New player": "🆕",
    "Left the team": "🚪"
  }};
  window.updateStatusIcon = function(s) {{
    var val = s.value;
    var wrapper = s.parentElement;
    var display = wrapper.querySelector(".status-emoji-display");
    if (display && STATUS_EMOJI[val]) display.textContent = STATUS_EMOJI[val];
    var row = wrapper.closest("tr");
    if (!row) return;
    var player = row.querySelector("td.player-name");
    if (!player) return;
    player.classList.remove("status-red","status-green","status-orange");
    player.style.color = ""; player.style.fontWeight = ""; player.style.textDecoration = "";
    var x = ["Injury","Red card","Yellow red card","Not playing (Called up)","Not playing (Other)","Left the team"];
    var g = ["Return (Injury)","Return (Susp)","Return (Called up)","Return (Other)","New player"];
    var d = ["Doubt", "Doubt + Last yellow card"];
    if (x.indexOf(val) !== -1) player.classList.add("status-red");
    else if (g.indexOf(val) !== -1) player.classList.add("status-green");
    else if (d.indexOf(val) !== -1) {{
      player.style.color = "#5F5D58";
      player.style.fontWeight = "bold";
      player.style.textDecoration = "underline";
    }}
  }};
  document.addEventListener("DOMContentLoaded", function() {{
    document.querySelectorAll(".status-select").forEach(function(s) {{
      var v = s.value;
      var d = s.parentElement.querySelector(".status-emoji-display");
      if (d && STATUS_EMOJI[v]) d.textContent = STATUS_EMOJI[v];
    }});
  }});
}})();
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script src="/static/favorites.js?v=7"></script>
<script src="/static/country_favorites.js?v=1"></script>

</head>
<body class="{('embed-mode' if embed else '')}">
    <div class="header">
        <!-- Aug 22 2026 — Max asked for a left-to-right header layout:
             LEFT  : ❓ FAQ, 🔼 Expand Details, 🔮 Predicted XI
             RIGHT : 👥 Add Lineups, 🧩 Build Lineup, 📸 Screenshot
             The 💎 My Favorites button is hidden in Team mode per
             the same instruction.
        -->
        <div style="display:flex;align-items:center;gap:8px;margin-right:auto;">
            <button type="button" id="btn-faq" class="header-action-btn" onclick="toggleFaq()">❓ FAQ</button>
            <button type="button" id="btn-collapse-details" class="header-action-btn" onclick="toggleDetailsCollapsed()">🔼 Expand Details</button>
            <button type="button" id="btn-reverse-odds" class="header-action-btn" onclick="toggleReverseOdds()">🔄 Reverse Odds</button>
            <button type="button" id="btn-test-rotowire" class="header-action-btn" onclick="testRotowireFRAN()" >🎯 Predicted XI</button>
            <button type="button" id="btn-starting-xi" class="header-action-btn" onclick="toggleStartingXI()">🏁 Starting XI</button>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
            <button type="button" id="btn-add-lineups" class="header-action-btn" onclick="toggleSection('bulk-lineup-panel-host', this, ['comparison-table-host'])">👥 Add Lineups</button>
            <button type="button" id="btn-builder" class="header-action-btn" onclick="toggleSection('builder-lineup-host', this)">🧩 Build Lineup</button>
            <button type="button" class="header-action-btn" onclick="exportScreenshot()" id="btn-export">📸 Screenshot</button>
        </div>
    </div>

    <div class="container">
        <div class="tabs">
            <div class="tab active">Squad</div>
            <div class="tab">Missing Players</div>
            <div class="tab">Doubtful Players</div>
            <div class="tab">Returning Players</div>
            <div class="tab">Transfer In</div>
            <div class="tab">Transfer Out</div>
        </div>

        <div id="snapshot-mode-banner" class="snapshot-mode-banner">Snapshot mode: showing saved independent squad. <button type="button" onclick="returnToLiveTeam()" style="margin-left:10px;border:0;border-radius:5px;background:#667eea;color:white;font-weight:700;padding:4px 8px;cursor:pointer;">Back to current team</button></div>
    </div>

    <div class="page-content">
    <div style="display:flex;flex-direction:column;gap:12px;flex-shrink:0;">
    <aside class="team-nav-sidebar" id="team-nav-sidebar">

        <label for="nav-country-trigger">Country</label>
        <div class="nav-country-dropdown" id="nav-country-dropdown">
            <button type="button" id="nav-country-trigger" class="nav-dropdown-trigger" aria-haspopup="listbox" aria-expanded="false" onclick="toggleCountryDropdown()">
                <span id="nav-country-flag" style="display:none;"></span>
                <span id="nav-country-name">-- Select Country --</span>
                <span class="nav-dropdown-arrow" style="margin-left:auto;">▼</span>
            </button>
        </div>
        <!-- Country list lives in document.body (z-index escapes parent stacking context) -->
        <ul class="nav-dropdown-list" id="nav-country-list" role="listbox" style="display:none;"></ul>
        <!-- hidden original select to keep onNavCountryChange() compatible -->
        <select id="nav-country" style="display:none;" onchange="onNavCountryChange()">
            <option value=""></option>
        </select>
        <label for="nav-championship">Championship</label>
        <div class="select-wrapper">
            <select id="nav-championship" onchange="onNavChampionshipChange()" disabled>
                <option value="">-- Select Championship --</option>
            </select>
        </div>
        <label for="nav-team">Team</label>
        <div class="select-wrapper">
            <select id="nav-team" onchange="onNavTeamChange()" disabled>
                <option value="">-- Select Team --</option>
            </select>
        </div>
        <div id="nav-match-group">
            <label for="nav-match" id="nav-match-label">Match</label>
            <div class="select-wrapper">
                <select id="nav-match" onchange="onNavMatchChange()" disabled>
                    <option value="">-- Select Match --</option>
                </select>
            </div>
            <!-- Fixture Overview block (Jul 30 2026): calendar density metric, was Fixture Congestion -->
            <div id="nav-fc-block" style="display:none; margin-top:14px; padding:10px 12px; background:#f8f9fb; border:1px solid #e0e3e8; border-radius:8px; font-size:12px;">
                <div style="font-weight:700; color:#333; margin-bottom:6px; font-size:13px;">Fixture Overview</div>
                <div id="nav-fc-bar" style="font-family:monospace; font-size:18px; letter-spacing:1px; margin-bottom:4px;">░░░░░░░░░░ <span id="nav-fc-pct">0%</span></div>
                <div id="nav-fc-status" style="font-weight:700; margin-bottom:8px;">—</div>
                <div style="display:flex; flex-direction:column; gap:2px; color:#555; font-size:11px;">
                    <div>Average Rest &mdash; <span id="nav-fc-avg">—</span></div>
                    <div>Shortest Rest &mdash; <span id="nav-fc-min">—</span></div>
                    <div>Away Matches &mdash; <span id="nav-fc-away">—</span></div>
                    <div>Next 14 Days &mdash; <span id="nav-fc-next14">—</span></div>
                    <div><span id="nav-fc-risk">—</span></div>
                </div>
            </div>
        </div>
        <div id="nav-actions" style="display:none; text-align:center; margin-top:10px;">
            <button id="nav-btn-analysis" onclick="openNavTeamAnalysis()" style="background:#043fb6; color:white; border:none; padding:8px 16px; border-radius:6px; font-size:13px; cursor:pointer;">
                Team Analysis
            </button>
        </div>
    </aside>

    <aside class="my-squads-sidebar" id="my-squads-sidebar">
        <div class="actions-bar" style="margin:0 0 10px 0;align-items:flex-start;flex-direction:column;gap:6px;">
            <button type="button" class="action-btn save-btn" id="save-btn" onclick="saveTeamState()">💾 Save</button>
            <span class="cache-badge" style="color:{cache_badge_color};">{cache_badge_text}</span>
            <span id="save-message"></span>
        </div>
        <div class="my-squads-title">My Squads</div>
        <div class="my-squads-help">Saved snapshots are independent from future team data updates.</div>
        <div id="my-squads-list"><div class="snapshot-empty-list">No saved squads yet.</div></div>
    </aside>

    <!-- Comparison Tables (toggled by ⚖️ Compare Lineups, appears below my-squads-sidebar, mutually exclusive with info-bar-squad-host) -->
    <div id="comparison-table-host" style="display:none;">
    <div id="comparison-table" style="display:flex;flex-direction:column;gap:8px;">
        <div style="background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:10px 12px;display:flex;align-items:center;justify-content:flex-start;min-height:42px;">
            <span id="cmp-val-pct-impact" style="font-size:15px;font-weight:600;">–</span>
            <span style="font-size:12px;margin-left:6px;position:relative;display:inline-block;" onmouseenter="showTooltip(this)" onmouseleave="hideTooltip(this)"><span style="font-weight:600;color:#dc3545;">Starting XI</span> — <span style="font-weight:600;color:#667eea;">Possible XI</span><span class="tooltip-delay" style="visibility:hidden;opacity:0;transition:opacity 0.3s;position:fixed;background:#333;color:#fff;padding:6px 10px;border-radius:6px;font-size:11px;font-weight:500;white-space:nowrap;z-index:9999;pointer-events:none;">&gt;8% = possible odds move</span></span>
        </div>
        <div style="background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:10px 12px;display:flex;align-items:center;justify-content:flex-start;min-height:42px;">
            <span id="cmp-sxi-pct-impact" style="font-size:15px;font-weight:600;">–</span>
            <span style="font-size:12px;margin-left:6px;"><span style="font-weight:600;color:#dc3545;">Starting XI</span> — <span style="font-weight:600;color:#000;">Last Match</span></span>
        </div>
        <div style="background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:10px 12px;display:flex;align-items:center;justify-content:flex-start;min-height:42px;">
            <span id="cmp-pxi-pct-impact" style="font-size:15px;font-weight:600;">–</span>
            <span style="font-size:12px;margin-left:6px;"><span style="font-weight:600;color:#667eea;">Possible XI</span> — <span style="font-weight:600;color:#000;">Last Match</span></span>
        </div>
    </div>
    </div>

    <!-- Info Bar Squad Overview (toggled by header button, appears below my-squads-sidebar) -->
    <div id="info-bar-squad-host" style="display:none;">
<div id="info-bar-squad" style="display:flex;flex-direction:column;gap:12px;width:255px;box-sizing:border-box;">
            <div style="display:flex;gap:8px;">
                <div style="flex:2;background:white;padding:10px 4px;border-radius:8px;border:1px solid #667eea;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;min-width:0;">
                    <div style="text-align:center;font-weight:bold;color:#667eea;font-size:11px;margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">Total Value</div>
                    <div style="font-weight:normal;color:#333;font-size:20px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{total_value_display}</div>
                </div>
                <div style="flex:1;background:white;padding:10px 6px;border-radius:8px;border:1px solid #667eea;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;min-width:0;">
                    <div style="text-align:center;font-weight:bold;color:#667eea;font-size:11px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">Avg Age</div>
                    <div style="font-weight:normal;color:#333;font-size:20px;text-align:center;">{avg_age}</div>
                </div>
                <div style="flex:1;background:white;padding:10px 6px;border-radius:8px;border:1px solid #667eea;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;min-width:0;">
                    <div style="text-align:center;font-weight:bold;color:#667eea;font-size:11px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">Players</div>
                    <div style="font-weight:normal;color:#333;font-size:20px;text-align:center;">{squad_size}</div>
                </div>
            </div>
            <div style="background:white;padding:10px 16px;border-radius:8px;border:1px solid #667eea;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;">
                <div style="text-align:center;font-weight:bold;color:#667eea;font-size:11px;margin-bottom:6px;white-space:nowrap;">Pos.Overview</div>
                {positional_overview_html}
            </div>
            <div style="background:white;padding:10px 16px;border-radius:8px;border:1px solid #667eea;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;">
                <div style="text-align:center;font-weight:bold;color:#667eea;font-size:11px;margin-bottom:6px;white-space:nowrap;">Players on Fire</div>
                {top3_players_html}
            </div>
        </div>
    </div>
    </div>

    <div class="page-main">
<div id="predicted11-panel-host" style="display:none;position:relative;width:963.99px;margin-bottom:12px;background:#0f1623;border-radius:10px;padding:14px 18px;box-shadow:0 4px 14px rgba(0,0,0,0.25);color:#e8eef7;">
        <button type="button" onclick="togglePredicted11()" style="position:absolute;top:4px;right:4px;background:transparent;border:none;color:#94a3b8;font-size:20px;cursor:pointer;line-height:1;padding:2px 8px;border-radius:4px;" title="Close">×</button>
        <div id="predicted11-body">
            <div style="color:#94a3b8;font-size:14px;">Loading next LaLiga fixtures…</div>
        </div>
        <div id="predicted11-footer" style="margin-top:10px;font-size:11px;color:#64748b;text-align:right;"></div>
    </div>

<div id="startingxi-panel-host" style="display:none;position:relative;width:963.99px;margin-bottom:12px;background:#0f1623;border-radius:10px;padding:14px 18px;box-shadow:0 4px 14px rgba(0,0,0,0.25);color:#e8eef7;">        <button type="button" onclick="toggleStartingXI()" style="position:absolute;top:4px;right:4px;background:transparent;border:none;color:#94a3b8;font-size:20px;cursor:pointer;line-height:1;padding:2px 8px;border-radius:4px;" title="Close">✕</button>        <div style="margin-bottom:8px;"><div onclick="toggleStartingXILeague('epl')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">England - Premier League <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="startingxi-epl-list" style="display:none;"></div></div>
<div style="margin-bottom:8px;"><div onclick="toggleStartingXILeague('fran')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">France - Ligue 1 <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="startingxi-fran-list" style="display:none;"></div></div>
<div style="margin-bottom:8px;"><div onclick="toggleStartingXILeague('bund')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">Germany - Bundesliga <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="startingxi-bund-list" style="display:none;"></div></div>
<div style="margin-bottom:8px;"><div onclick="toggleStartingXILeague('liga')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">Spain - La Liga <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="startingxi-liga-list" style="display:none;"></div></div>
<div style="margin-bottom:8px;"><div onclick="toggleStartingXILeague('seri')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">Italy - Serie A <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="startingxi-seri-list" style="display:none;"></div></div>
<div style="margin-bottom:8px;"><div onclick="toggleStartingXILeague('mls')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">USA - MLS <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="startingxi-mls-list" style="display:none;"></div></div>                                            </div>

<div id="test-rotowire-panel-host" style="display:none;position:relative;width:963.99px;margin-bottom:12px;background:#0f1623;border-radius:10px;padding:14px 18px;box-shadow:0 4px 14px rgba(0,0,0,0.25);color:#e8eef7;">        <button type="button" onclick="toggleTestRotowire()" style="position:absolute;top:4px;right:4px;background:transparent;border:none;color:#94a3b8;font-size:20px;cursor:pointer;line-height:1;padding:2px 8px;border-radius:4px;" title="Close">✕</button>        <div style="margin-bottom:8px;"><div onclick="toggleTestLeague('epl')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">England - Premier League <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="test-league-epl-list" style="display:none;"></div></div>
<div style="margin-bottom:8px;"><div onclick="toggleTestLeague('fran')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">France - Ligue 1 <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="test-league-fran-list" style="display:none;"></div></div>
<div style="margin-bottom:8px;"><div onclick="toggleTestLeague('bund')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">Germany - Bundesliga <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="test-league-bund-list" style="display:none;"></div></div>
<div style="margin-bottom:8px;"><div onclick="toggleTestLeague('liga')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">Spain - La Liga <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="test-league-liga-list" style="display:none;"></div></div>
<div style="margin-bottom:8px;"><div onclick="toggleTestLeague('seri')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">Italy - Serie A <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="test-league-seri-list" style="display:none;"></div></div>
<div style="margin-bottom:8px;"><div onclick="toggleTestLeague('mls')" style="font-size:15px;font-weight:700;color:#e8eef7;cursor:pointer;">USA - MLS <span style="color:#60a5fa;font-size:12px;vertical-align:middle;">▼</span></div><div id="test-league-mls-list" style="display:none;"></div></div>                                            </div>
    <div id="bulk-lineup-panel-host" style="display:none;margin-bottom:12px;">
            <div class="bulk-lineup-panel">
            <div class="bulk-lineup-controls">
                <div class="bulk-lineup-row">
                    <select id="bulk-lineup-mode" aria-label="Bulk lineup mode">
                        <option value="possible">🔵 P-XI</option>
                        <option value="start">🔴 S-XI</option>
                        <option value="squad">⚫️ List (all found)</option>
                    </select>
                    <button type="button" class="bl-action-btn" onclick="applyBulkLineup()">Go</button>
                    <div class="vision-lineup-row" style="margin-left:auto;">
                        <input type="file" id="vision-lineup-image" accept="image/*" aria-label="Vision lineup image" style="display:none;">
                        <button type="button" class="vision-lineup-btn bl-action-btn" onclick="document.getElementById('vision-lineup-image').click()">Upload</button>
                        <button type="button" class="vision-lineup-btn bl-action-btn" id="vision-paste-btn" onclick="pasteImageFromClipboard()" title="Paste image from clipboard (Ctrl+V also works)">📋 Paste</button>
                        <span id="vision-file-name" class="vision-lineup-status">💤</span>
                        <button type="button" class="vision-lineup-btn bl-action-btn" onclick="applyVisionLineup()">Run AI</button>
                        <span id="vision-lineup-status" class="vision-lineup-status"></span>
                    </div>
                </div>
                <div class="bulk-lineup-text-row" style="display:flex;gap:8px;align-items:flex-start;margin-top:8px;">
                    <div id="bulk-lineup-text" contenteditable="true" placeholder="Paste players" style="flex:1;height:120px;min-height:120px;resize:both;overflow-y:auto;border:1px solid #d5d9e8;border-radius:8px;padding:8px 10px;font-size:12px;line-height:1.35;font-family:inherit;white-space:pre-wrap;background:white;"></div>
                    <div id="vision-lineup-stats" class="vision-lineup-stats" style="display:none;min-width:120px;font-size:12px;color:#555;line-height:1.6;">
                        <div>Total: <span id="vision-total-count">0</span> players</div>
                        <div style="color:#17843f;">Found: <span id="vision-found-count">0</span> players</div>
                        <div style="color:#dc3545;">Not found: <span id="vision-notfound-count">0</span> players</div>
                    </div>
                </div>
            </div>
            <div id="bulk-lineup-report" class="bulk-lineup-report"></div>
            <div id="bulk-lineup-ambiguous" class="bulk-ambiguous" style="display:none;"></div>
            <div class="bulk-lineup-footer" style="display:flex;justify-content:flex-end;margin-top:8px;">
                <button type="button" onclick="clearBulkLineup()" title="Clear textarea and report" style="background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin:0;">✖️</button>
            </div>
        </div>
</div>

        <!-- Hidden -->
        <div style="display:none;">
        {last_match_impact:.2f}
        </div>

        <div class="main-layout">
            <div class="main-table">
                <!-- Team name + dropdown (replaces tabs) + 📊 emoji aligned to right -->
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:12px;flex-wrap:wrap;background:linear-gradient(to right, #043fb6 0%, #2e7af8 100%);padding:16px 20px;border-radius:12px;">
                    <div style="display:flex;align-items:center;gap:10px;">
                        {team_logo_html}
                        <h1 style="margin:0;font-size:24px;font-weight:600;color:white;">{team_name}</h1>
                    </div>
                    <div style="display:flex;align-items:center;gap:12px;">
                        <button type="button" id="update-data-btn" class="header-action-btn" onclick="updateData()" title="Fetch latest updates">♻️ Refresh</button>
                        <span id="update-counter" style="color:rgba(255,255,255,0.85);font-size:13px;font-weight:500;min-width:60px;"></span>
                        <select id="tournament-select" onchange="onTournamentChange(this.value)" title="Filter by tournament" style="padding:6px 12px;border:1px solid rgba(255,255,255,0.4);border-radius:6px;font-size:14px;background:rgba(255,255,255,0.15);color:white;cursor:pointer;font-weight:600;">
                            <option value="" style="color:#333;">Loading…</option>
                        </select>
                        <select id="squad-mode-select" onchange="onSquadModeChange(this.value)" style="padding:6px 12px;border:1px solid rgba(255,255,255,0.4);border-radius:6px;font-size:14px;background:rgba(255,255,255,0.15);color:white;cursor:pointer;font-weight:600;width:160px;">
                            <option value="Squad" style="color:#333;">All Squad</option>
                            <option value="Missing Players" style="color:#333;">Missing Players</option>
                            <option value="Doubtful Players" style="color:#333;">Doubtful Players</option>
                            <option value="Returning Players" style="color:#333;">Returning Players</option>
                            <option value="Transfer In" style="color:#333;">Transfer In</option>
                            <option value="Transfer Out" style="color:#333;">Transfer Out</option>
                        </select>
                        <span class="team-squad-emoji" style="cursor:help;font-size:18px;line-height:1;position:relative;display:inline-block;color:white;margin-left:auto;">📊</span>
                    </div>
                </div>
                <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">№</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">Nat</th>
                        <th rowspan="2" style="width:200px;padding:0 2px;white-space:nowrap;">Player</th>
                        <th rowspan="2" style="text-align:center;width:70px;padding:0;font-size:10px;vertical-align:top;"><div style="display:flex;flex-direction:column;align-items:center;height:100%;"><button onclick="clearStatus();return false;" style="background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin:0;" title="Clear Status">✖️</button><span title="Status" style="font-size:10px;margin-top:2px;">Status</span></div></th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">Age</th>
                        <th rowspan="2" style="text-align:center;width:60px;padding:0;" title="Market Value" class="col-mv">MV</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">Pos</th>
                        <th rowspan="2" style="text-align:center;width:60px;padding:0;font-size:11px;" class="col-role">Squad<br>Role</th>
                        <th rowspan="2" style="text-align:center;width:40px;padding:0;font-size:11px;" title="Impact Score" class="col-is">IS</th>
                        <th rowspan="2" style="text-align:center;width:37px;padding:0;font-size:10px;vertical-align:top;"><div style="display:flex;flex-direction:column;align-items:center;height:100%;"><button onclick="clearColumn('squad');return false;" style="background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin:0;" title="Clear List">✖️</button><span title="Squad List" style="font-size:10px;margin-top:2px;">List</span></div></th>
                        <th rowspan="2" style="text-align:center;width:37px;padding:0;font-size:10px;vertical-align:top;"><div style="display:flex;flex-direction:column;align-items:center;height:100%;"><button onclick="clearColumn('possible');return false;" style="background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin:0;" title="Clear P-XI">✖️</button><span title="Predicted XI" style="font-size:10px;margin-top:2px;">P-XI</span><span id="xi-counter" style="color:#667eea;font-size:9px;">0/11</span></div></th>
                        <th rowspan="2" style="text-align:center;width:37px;padding:0;font-size:10px;vertical-align:top;"><div style="display:flex;flex-direction:column;align-items:center;height:100%;"><button onclick="clearColumn('start');return false;" style="background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin:0;" title="Clear S-XI">✖️</button><span title="Starting XI" style="font-size:10px;margin-top:2px;">S-XI</span><span id="starting-counter" style="color:#dc3545;font-size:9px;">0/11</span></div></th>
                        {last3_header_row1}
                        <th rowspan="2" style="text-align:center;width:32px;padding:0;border-left:1px solid #ddd;">Apps</th>
                        <th rowspan="2" style="text-align:center;width:40px;padding:0;">Min</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">G</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">A</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">YC</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">RC</th>
                    </tr>
                    <tr>
                        {last3_header_cells}
                    </tr>
                </thead>
                <tbody>
                    {players_rows}
                </tbody>
            </table>
                </div>
                <!-- Info-bars (moved below main table) -->
                <div id="info-bar-missing" style="display:none;gap:12px;margin-top:10px;margin-bottom:12px;width:964px;max-width:100%;box-sizing:border-box;">
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-impact">0.00</span><br><span style="color:#888;font-size:11px;">IS</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;"><span id="missing-goals">0</span><span style="font-size:14px;color:#999;"> / <span id="missing-goals-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;"><span id="missing-assists">0</span><span style="font-size:14px;color:#999;"> / <span id="missing-assists-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
                </div>
                <div id="info-bar-doubtful" style="display:none;gap:12px;margin-top:10px;margin-bottom:12px;width:964px;max-width:100%;box-sizing:border-box;">
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-impact">0.00</span><br><span style="color:#888;font-size:11px;">IS</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;"><span id="doubtful-goals">0</span><span style="font-size:14px;color:#999;"> / <span id="doubtful-goals-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;"><span id="doubtful-assists">0</span><span style="font-size:14px;color:#999;"> / <span id="doubtful-assists-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
                </div>
                <div id="info-bar-returning" style="display:none;gap:12px;margin-top:10px;margin-bottom:12px;width:964px;max-width:100%;box-sizing:border-box;">
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-impact">0.00</span><br><span style="color:#888;font-size:11px;">IS</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;"><span id="returning-goals">0</span><span style="font-size:14px;color:#999;"> / <span id="returning-goals-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;"><span id="returning-assists">0</span><span style="font-size:14px;color:#999;"> / <span id="returning-assists-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
                </div>
                <div id="info-bar-transfer-in" style="display:none;gap:12px;margin-top:10px;margin-bottom:12px;width:964px;max-width:100%;box-sizing:border-box;">
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="transfer-in-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="transfer-in-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="transfer-in-impact">0.00</span><br><span style="color:#888;font-size:11px;">IS</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;"><span id="transfer-in-goals">0</span><span style="font-size:14px;color:#999;"> / <span id="transfer-in-goals-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;"><span id="transfer-in-assists">0</span><span style="font-size:14px;color:#999;"> / <span id="transfer-in-assists-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
                </div>
                <div id="info-bar-transfer-out" style="display:none;gap:12px;margin-top:10px;margin-bottom:12px;width:964px;max-width:100%;box-sizing:border-box;">
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="transfer-out-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="transfer-out-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="transfer-out-impact">0.00</span><br><span style="color:#888;font-size:11px;">IS</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;"><span id="transfer-out-goals">0</span><span style="font-size:14px;color:#999;"> / <span id="transfer-out-goals-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
                    <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;"><span id="transfer-out-assists">0</span><span style="font-size:14px;color:#999;"> / <span id="transfer-out-assists-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
                </div>
                <!-- Coach (left) + [🚌 separate button] + Stadium (right) below main table.
                     Sep 1 2026 — 🚌 moved OUT of the white Stadium card: it is a
                     standalone sibling so the stadium block keeps its clean look. -->
                <div id="coach-stadium-bar" style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;gap:10px;">
                    <div style="display:inline-block;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;"><span style="color:#667eea;font-weight:600;">Coach:</span> {coach_display_html}</div>
                    <div style="display:inline-flex;align-items:center;gap:8px;">
                        {travel_btn_html}
                        <div style="display:inline-block;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;"><span style="color:#667eea;font-weight:600;">Stadium:</span> {stadium_display}</div>
                    </div>
                </div>
            </div>

            <!-- Builder Lineup: pitch with 11 draggable player circles (sits right of main table) -->
            <div id="builder-lineup-host" style="display:none;flex-shrink:0;margin-top:0;">
                <div id="builder-lineup" style="background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.05);padding:16px;width:fit-content;">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
                        <label style="font-weight:600;color:#333;font-size:12px;">Formation:</label>
                        <select id="bl-formation" onchange="applyFormation(this.value)" style="padding:5px 8px;border:1px solid #ccc;border-radius:5px;font-size:12px;background:white;cursor:pointer;">
                            <option value="4-3-3">4-3-3</option>
                            <option value="4-4-2">4-4-2</option>
                            <option value="4-2-3-1">4-2-3-1</option>
                            <option value="4-1-4-1">4-1-4-1</option>
                            <option value="4-2-4">4-2-4</option>
                            <option value="4-4-1-1">4-4-1-1</option>
                            <option value="4-4-2-diamond">4-4-2 (Diamond)</option>
                            <option value="3-1-4-2">3-1-4-2</option>
                            <option value="3-4-3">3-4-3</option>
                            <option value="3-5-2">3-5-2</option>
                            <option value="5-3-2">5-3-2</option>
                            <option value="5-4-1">5-4-1</option>
                            <option value="custom">Custom</option>
                        </select>
                        <button type="button" onclick="clearFormation()" style="padding:5px 10px;background:#f0f0f0;border:1px solid #ccc;border-radius:5px;cursor:pointer;font-size:11px;">Clear</button>
                        <button type="button" onclick="saveLineupPNG()" style="padding:5px 10px;background:#2e7af8;color:white;border:none;border-radius:5px;cursor:pointer;font-size:11px;font-weight:600;">Save PNG</button>
                    </div>
                    <div id="bl-pitch" style="position:relative;width:540px;height:675px;border-radius:6px;overflow:hidden;border:3px solid #fff;background-color:#2d8f3f;">
                        <!-- Pitch background with horizontal stripes (mowed field, perpendicular to touchline) -->
                        <div style="position:absolute;inset:0;background:repeating-linear-gradient(0deg, #2d8f3f 0px, #2d8f3f 75px, #298238 75px, #298238 150px);"></div>
                        <!-- Outer touchline (already covered by border) -->
                        <!-- Halfway line (horizontal center) -->
                        <div style="position:absolute;left:0;right:0;top:50%;height:2px;background:rgba(255,255,255,0.85);transform:translateY(-50%);"></div>
                        <!-- Center circle -->
                        <div style="position:absolute;left:50%;top:50%;width:130px;height:130px;border:2px solid rgba(255,255,255,0.85);border-radius:50%;transform:translate(-50%,-50%);"></div>
                        <!-- Center spot -->
                        <div style="position:absolute;left:50%;top:50%;width:4px;height:4px;background:rgba(255,255,255,0.9);border-radius:50%;transform:translate(-50%,-50%);"></div>
                        <!-- Top penalty area -->
                        <div style="position:absolute;left:50%;top:0;width:330px;height:120px;border:2px solid rgba(255,255,255,0.85);border-top:none;transform:translateX(-50%);"></div>
                        <!-- Top goal area (6-yard box) -->
                        <div style="position:absolute;left:50%;top:0;width:160px;height:50px;border:2px solid rgba(255,255,255,0.85);border-top:none;transform:translateX(-50%);"></div>
                        <!-- Top penalty spot (11 m from goal line ≈ 72px at 6.5 px/m) -->
                        <div style="position:absolute;left:50%;top:72px;width:3px;height:3px;background:rgba(255,255,255,0.9);border-radius:50%;transform:translateX(-50%);"></div>
                        <!-- Top goal (net) -->
                        <div style="position:absolute;left:50%;top:-8px;width:80px;height:10px;border:2px solid #fff;background:rgba(255,255,255,0.1);transform:translateX(-50%);"></div>
                        <!-- Bottom penalty area -->
                        <div style="position:absolute;left:50%;bottom:0;width:330px;height:120px;border:2px solid rgba(255,255,255,0.85);border-bottom:none;transform:translateX(-50%);"></div>
                        <!-- Bottom goal area -->
                        <div style="position:absolute;left:50%;bottom:0;width:160px;height:50px;border:2px solid rgba(255,255,255,0.85);border-bottom:none;transform:translateX(-50%);"></div>
                        <!-- Bottom penalty spot (11 m from goal line ≈ 72px at 6.5 px/m) -->
                        <div style="position:absolute;left:50%;bottom:72px;width:3px;height:3px;background:rgba(255,255,255,0.9);border-radius:50%;transform:translateX(-50%);"></div>
                        <!-- Bottom goal (net) -->
                        <div style="position:absolute;left:50%;bottom:-8px;width:80px;height:10px;border:2px solid #fff;background:rgba(255,255,255,0.1);transform:translateX(-50%);"></div>
                        <!-- Top penalty arc (D) — outside penalty area, facing center
                             FIFA: radius 9.15 m from penalty spot (11 m from goal line).
                             Scale: 1m ≈ 6.5px → radius ≈ 60px, spot ≈ 72px. -->
                        <svg style="position:absolute;left:50%;top:120px;transform:translateX(-50%);" width="180" height="62" viewBox="0 0 180 62">
                            <path d="M 30 0 A 60 60 0 0 1 150 0" fill="none" stroke="rgba(255,255,255,0.85)" stroke-width="2"/>
                        </svg>
                        <!-- Bottom penalty arc (D) — outside penalty area, facing center -->
                        <svg style="position:absolute;left:50%;bottom:120px;transform:translateX(-50%) scale(1,-1);" width="180" height="62" viewBox="0 0 180 62">
                            <path d="M 30 0 A 60 60 0 0 1 150 0" fill="none" stroke="rgba(255,255,255,0.85)" stroke-width="2"/>
                        </svg>
                        <div id="bl-team-name" style="position:absolute;left:14px;bottom:10px;color:white;font-size:16px;font-weight:700;text-shadow:0 1px 4px rgba(0,0,0,0.9);z-index:1;">{team_name}</div>
                        <div id="bl-watermark" style="position:absolute;right:14px;bottom:10px;color:white;font-size:16px;font-weight:700;text-shadow:0 1px 4px rgba(0,0,0,0.9);z-index:1;letter-spacing:0.3px;">@LineupValue</div>
                        <div id="bl-players" style="position:absolute;inset:0;z-index:2;"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        var _tooltipTimer = null;
        function toggleSection(hostId, btn, extraHosts) {{
            var host = document.getElementById(hostId);
            if (!host) return;
            var isVisible = host.style.display !== 'none';
            // All header panels are independent — they can all be open at the same time.
            // ⚖️ Compare Lineups and 📊 Squad Overview both live in the left column wrapper
            // (Compare above, Squad below), so when both are toggled on, both stay visible.
            var willShow = !isVisible;
            // If extraHosts is provided, sync them with the primary host:
            // - When primary becomes visible, all extraHosts also become visible.
            // - When primary becomes hidden, all extraHosts also become hidden.
            // (Used by the merged 👥 Add Lineups button to control both bulk and compare.)
            var extra = [];
            if (extraHosts) {{
                if (Array.isArray(extraHosts)) {{
                    extra = extraHosts;
                }} else {{
                    extra = [extraHosts];
                }}
            }}
            if (!isVisible) {{
                host.style.display = 'block';
                if (btn) btn.classList.add('active');
                // Show extraHosts
                extra.forEach(function(hid) {{
                    var h = document.getElementById(hid);
                    if (h) h.style.display = 'block';
                }});
            }} else {{
                host.style.display = 'none';
                if (btn) btn.classList.remove('active');
                // Hide extraHosts
                extra.forEach(function(hid) {{
                    var h = document.getElementById(hid);
                    if (h) h.style.display = 'none';
                }});
            }}
            // 🏗️ Builder Lineup — keep .main-layout in row whenever builder-lineup-host is visible,
            // regardless of which other hostId triggered this toggleSection call.
            var mainLayout = document.querySelector('.main-layout');
            if (mainLayout) {{
                var builderHost = document.getElementById('builder-lineup-host');
                var builderVisible = builderHost && builderHost.style.display !== 'none';
                if (builderVisible) {{
                    mainLayout.style.setProperty('flex-direction', 'row', 'important');
                    mainLayout.style.setProperty('align-items', 'flex-start', 'important');
                    mainLayout.style.setProperty('gap', '20px', 'important');
                    mainLayout.style.setProperty('flex-wrap', 'nowrap', 'important');
                }} else {{
                    mainLayout.style.removeProperty('flex-direction');
                    mainLayout.style.removeProperty('align-items');
                    mainLayout.style.removeProperty('gap');
                    mainLayout.style.removeProperty('flex-wrap');
                }}
            }}
        }}
        // ===================================================================
        // 🔮 Predicted XI — Aug 21 2026
        // Toggles the Spain LaLiga fixtures panel below the header.
        // First open → fetches /lineup_ai/api/laliga_fixtures once, then
        // reuses the cached payload for the rest of the session.
        // ===================================================================
        let _predicted11Loaded = false;
        // Aug 22 2026 — Countdown refresh timer. While the Predicted
        // XI panel is open we recompute every .p11-countdown span
        // every 30 seconds so "Match starts in 5h 12m" ticks down
        // without re-rendering the whole panel (which would reset
        // scroll position and lose open round sections).
        let _p11CountdownTimer = null;
        function refreshPredicted11Countdowns() {{
            const ACTIVE_WINDOW = 20 * 3600;
            const now = Math.floor(Date.now() / 1000);
            // Aug 22 2026 — refresh every countdown span (existing
            // behaviour) AND every Check Predicted XI button. Buttons
            // unlock at T-20h, so we walk the row, look up the same
            // data-ts, and either activate the button (replace the
            // disabled grey placeholder with the blue active one) or
            // leave it alone.
            const spans = document.querySelectorAll('#predicted11-body .p11-countdown');
            spans.forEach(function (el) {{
                const ts = parseInt(el.getAttribute('data-ts') || '0', 10);
                if (!ts) return;
                const delta = ts - now;
                if (delta <= 0) {{ el.parentNode && el.parentNode.removeChild(el); return; }}
                const days = Math.floor(delta / 86400);
                const hours = Math.floor((delta % 86400) / 3600);
                const minutes = Math.floor((delta % 3600) / 60);
                let body;
                if (days > 0) body = days + 'd ' + hours + 'h';
                else if (hours > 0) body = hours + 'h ' + pad2(minutes) + 'm';
                else body = minutes + 'm';
                // Aug 24 2026 — prefix changed from
                // "Match starts in " to the 🕒 clock emoji so the row
                // reads "🕒 4h 21m" / "🕒 2d 4h" / "🕒 18m" instead of
                // "Match starts in 4h 21m". The clock glyph also
                // visually anchors it as a countdown chip on the left
                // edge of the row.
                el.textContent = '🕒 ' + body;
            }});
            // Aug 24 2026 — the "🔍 Check Predicted XI" button was
            // removed from the predicted XI row, so there is no
            // longer a locked-placeholder that needs promoting to
            // active when the T-18h window opens. (The T-18h
            // auto-builder scheduler in app.py is the only path
            // that fills the predicted XI cache now.)
        }}
        function togglePredicted11() {{
            const host = document.getElementById('predicted11-panel-host');
            const btn = document.getElementById('btn-predicted-11');
            if (!host) return;
            const willShow = host.style.display === 'none';
            host.style.display = willShow ? 'block' : 'none';
            if (btn) btn.classList.toggle('active', willShow);
            // Aug 22 2026 — Max asked: when 🔮 Predicted XI is open the
            // tweets sidebar disappears (it's a wide block that crowds the
            // fixtures list). The CSS already supports .tweets-sidebar.hidden.

            if (willShow && !_predicted11Loaded) {{
                loadPredicted11();
            }}
            // Aug 22 2026 — start/stop the countdown ticker so the
            // "Match starts in ..." labels stay current while the panel
            // is open, and we don't leak a timer when it's hidden.
            if (willShow) {{
                if (!_p11CountdownTimer) _p11CountdownTimer = setInterval(refreshPredicted11Countdowns, 30000);
            }} else {{
                if (_p11CountdownTimer) {{ clearInterval(_p11CountdownTimer); _p11CountdownTimer = null; }}
            }}
        }}
        // Aug 22 2026 — expose so the Match-mode header button
        // (compare_template.html) can trigger it via postMessage.
        window.togglePredicted11 = togglePredicted11;

        // Sep 6 2026 — Test button: fetch rotowire FRAN Predicted Lineup
        // and match P-XI checkboxes + statuses.
        async function testRotowireFRAN() {{
            const host = document.getElementById('test-rotowire-panel-host');
            if (host) {{
                if (host.style.display === 'none' || !host.style.display) {{
                    host.style.display = 'block';
                    const _tbtn = document.getElementById('btn-test-rotowire');
                    if (_tbtn) _tbtn.classList.add('active');
                    const _sxiHost = document.getElementById('startingxi-panel-host');
                    if (_sxiHost && _sxiHost.style.display !== 'none') toggleStartingXI();
                    await loadTestRotowireMatches();
                }} else {{
                    host.style.display = 'none';
                    const _tbtn2 = document.getElementById('btn-test-rotowire');
                    if (_tbtn2) _tbtn2.classList.remove('active');
                }}
            }}
        }}
        window.testRotowireFRAN = testRotowireFRAN;
        window.toggleTestRotowire = testRotowireFRAN;

        // Sep 6 2026 — dropdown: load matches ONLY when the
        // France - Ligue 1 dropdown is opened (not on panel open).

        // Sep 6 2026 — Starting XI panel (Confirmed lineups within 1h15m)
        function toggleStartingXI() {{
            const host = document.getElementById('startingxi-panel-host');
            if (!host) return;
            const willShow = host.style.display === 'none';
            host.style.display = willShow ? 'block' : 'none';
            const tbtn = document.getElementById('btn-starting-xi');
            if (tbtn) tbtn.classList.toggle('active', willShow);
            if (willShow) {{
                const other = document.getElementById('test-rotowire-panel-host');
                if (other && other.style.display !== 'none') testRotowireFRAN();
            }}
        }}
        window.toggleStartingXI = toggleStartingXI;

        async function toggleStartingXILeague(leagueKey) {{
            const list = document.getElementById('startingxi-' + leagueKey + '-list');
            if (!list) return;
            const willShow = list.style.display === 'none';
            list.style.display = willShow ? 'block' : 'none';
            if (willShow && !list.innerHTML) {{
                await loadStartingXIMatches(leagueKey);
            }}
        }}
        window.toggleStartingXILeague = toggleStartingXILeague;

        async function loadStartingXIMatches(leagueKey) {{
            const body = document.getElementById('startingxi-' + leagueKey + '-list');
            if (!body) return;
            body.innerHTML = '<div style="color:#94a3b8;font-size:14px;">Loading...</div>';
            try {{
                const r = await fetch('/lineup_ai/api/starting_xi_matches/' + leagueKey, {{ cache: 'no-store' }});
                const d = await r.json();
                renderStartingXIMatches(d, leagueKey);
            }} catch (e) {{
                body.innerHTML = '<div style="color:#dc3545;font-size:14px;">Failed to load matches.</div>';
            }}
        }}

        function renderStartingXIMatches(d, leagueKey) {{
            const body = document.getElementById('startingxi-' + leagueKey + '-list');
            if (!body) return;

            const matches = (d && d.matches) || [];
            if (matches.length === 0) {{
                body.innerHTML = '<div style="color:#94a3b8;font-size:14px;">No confirmed matches</div>';
                return;
            }}
            let html = '';
            for (const m of matches) {{
                if (!m.home_id && !m.away_id) {{
                    html += '<div style="padding:6px 10px;margin-bottom:8px;background:#172033;border-radius:6px;border:1px solid #1f2b40;font-size:14px;color:#e8eef7;">No LV match. ' + m.home_team + ' / ' + m.away_team + '</div>';
                    continue;
                }}
                const kickStr = m.lv_time || '';
                let openMatchBtn = '';
                if (m.home_id && m.away_id) {{
                    const openHref = '/lineup_ai/compare/' + m.home_id +
                        '?mid=' + encodeURIComponent('sx-' + m.home_id + '-' + m.away_id) +
                        '&home_id=' + encodeURIComponent(m.home_id) +
                        '&away_id=' + encodeURIComponent(m.away_id) +
                        '&home_name=' + encodeURIComponent(m.home_team) +
                        '&away_name=' + encodeURIComponent(m.away_team) +
                        '&rotowire_fran=1' +
                        '&rw_league=' + leagueKey +
                        '&kickoff_ts=' + (m.kickoff_ts || 0);
                    openMatchBtn = '<a href="' + openHref + '" target="_blank" rel="noopener" style="font-size:11px;color:#60a5fa;text-decoration:none;border:1px solid #60a5fa;padding:4px 10px;border-radius:5px;white-space:nowrap;">▶ Open Match</a>';
                }}
                const pxiHomeFull = (m.pxi_home_matched === 11 && m.pxi_home_total === 11);
                const pxiAwayFull = (m.pxi_away_matched === 11 && m.pxi_away_total === 11);
                const pxiAwayPartial = (m.pxi_away_matched > 0 && !pxiAwayFull);
                const pxiHomePartial = (m.pxi_home_matched > 0 && !pxiHomeFull);
                html += '<div style="display:grid;grid-template-columns:60px 88px 1fr auto;align-items:center;column-gap:12px;padding:6px 10px;background:#172033;border-radius:6px;border:1px solid #1f2b40;">';
                html += '<span class="test-countdown" data-ts="' + (m.kickoff_ts || 0) + '" style="grid-column:1;font-size:12px;color:#94a3b8;width:60px;font-variant-numeric:tabular-nums;justify-self:start;"></span>';
                html += '<span style="grid-column:2;font-size:12px;color:#94a3b8;width:88px;font-variant-numeric:tabular-nums;justify-self:start;">' + kickStr + '</span>';
                html += '<div style="grid-column:3;display:flex;align-items:center;gap:8px;font-size:14px;color:#e8eef7;min-width:0;">';
                if (m.is_confirmed) {{
                    if (pxiHomeFull) {{
                        html += '<span title="' + m.pxi_home_matched + '/11 matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#dc3545;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;">✓</span>';
                    }} else if (pxiHomePartial) {{
                        html += '<span title="' + (m.pxi_home_matched || 0) + '/11 matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#dc3545;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;opacity:0.55;"></span>';
                    }} else {{
                        html += '<span style="display:inline-block;width:18px;flex-shrink:0;"></span>';
                    }}
                }}
                html += '<span style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + m.home_team + '</span>';
                html += '<span style="color:#64748b;font-size:12px;flex-shrink:0;">vs</span>';
                html += '<span style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + m.away_team + '</span>';
                if (m.is_confirmed) {{
                    if (pxiAwayFull) {{
                        html += '<span title="' + m.pxi_away_matched + '/11 matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#dc3545;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;">✓</span>';
                    }} else if (pxiAwayPartial) {{
                        html += '<span title="' + (m.pxi_away_matched || 0) + '/11 matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#dc3545;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;opacity:0.55;"></span>';
                    }}
                }}
                html += '<span style="font-size:10px;font-weight:600;color:#f87171;white-space:nowrap;">' + m.pxi_home_matched + '/' + m.pxi_home_total + ' · ' + m.pxi_away_matched + '/' + m.pxi_away_total + '</span>';
                if (m.is_confirmed) {{
                    html += '<span style="font-size:10px;font-weight:600;color:#f87171;white-space:nowrap;">Confirmed</span>';
                }} else {{
                    html += '<span style="font-size:10px;font-weight:600;color:#94a3b8;white-space:nowrap;">Not confirmed</span>';
                }}
                html += '</div>';
                html += '<span style="grid-column:4;justify-self:end;display:flex;gap:6px;"><button type="button" onclick="loadStartingXIMatches(&#39;' + leagueKey + '&#39;)" style="font-size:11px;color:#e8eef7;background:#1f2b40;border:1px solid #3b5270;padding:4px 10px;border-radius:5px;white-space:nowrap;cursor:pointer;" title="Check Confirmed">🔄 Check</button>' + openMatchBtn + '</span>';
                html += '</div>';
            }}
            body.innerHTML = html;
            if (typeof refreshTestCountdowns === 'function') refreshTestCountdowns();
        }}

        async function toggleTestLeague(leagueKey) {{
            const list = document.getElementById('test-league-' + leagueKey + '-list');
            if (!list) return;
            const willShow = list.style.display === 'none';
            list.style.display = willShow ? 'block' : 'none';
            if (willShow && !list.innerHTML) {{
                await loadTestRotowireMatches(leagueKey);
            }}
        }}
        window.toggleTestLeague = toggleTestLeague;

        // Sep 6 2026 — listen for rotowire-fran-apply message from
        // the compare page (Match mode) and auto-apply rotowire lineups.
        window.addEventListener('message', async function(e) {{
            if (!e.data || e.data.type !== 'rotowire-fran-apply') return;
            try {{
                const _modeSel = document.getElementById('bulk-lineup-mode');
                const _rwLg = (e.data && e.data.league) || 'fran';
                const r = await fetch('/lineup_ai/api/test_rotowire_fran/' + encodeURIComponent(TEAM_ID) + '?league=' + encodeURIComponent(_rwLg), {{ cache: 'no-store' }});
                const d = await r.json();
                if (!d || d.match_found === false || d.error) return;
                // Resize the bulk-lineup textarea to show exactly 11 rows
                // after a lineup match so no scrolling is needed.
                function _rwFitTextarea() {{
                    var el = document.getElementById('bulk-lineup-text');
                    if (!el) return;
                    var cs = window.getComputedStyle(el);
                    var lh = parseFloat(cs.lineHeight);
                    if (!lh || isNaN(lh)) lh = 16;
                    var pad = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
                    if (isNaN(pad)) pad = 16;
                    var h = Math.ceil(lh * 11 + pad + 2);
                    el.style.height = h + 'px';
                    el.style.minHeight = h + 'px';
                }}
                async function _rwApply(players) {{
                    const _mSelEl = document.getElementById('bulk-lineup-mode');
                    const _cbCls = (_mSelEl && _mSelEl.value === 'start') ? 'input.starting-checkbox' : 'input.xi-checkbox';
                    for (const p of players) {{
                        if (!p.lv_name) continue;
                        const cbs = document.querySelectorAll(_cbCls);
                        for (const cb of cbs) {{
                            const rowName = (cb.value || '').toLowerCase().trim();
                            const targetName = (p.lv_name || '').toLowerCase().trim();
                            if (rowName === targetName) {{
                                if (!cb.checked) {{
                                    cb.checked = true;
                                    cb.dispatchEvent(new Event('change', {{bubbles: true}}));
                                }}
                                if (p.status === 'Injury' || p.status === 'Doubt') {{
                                    const row = cb.closest('tr');
                                    if (row) {{
                                        const sel = row.querySelector('select.status-select');
                                        if (sel) {{
                                            sel.value = p.status;
                                            sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                                        }}
                                    }}
                                }}
                                break;
                            }}
                        }}
                    }}
                }}
                if (d.predicted_players && d.predicted_players.length > 0) {{
                    if (_modeSel) _modeSel.value = 'possible';
                    await _rwApply(d.predicted_players);
                }}
                if (_modeSel) _modeSel.value = 'start';
                await _rwApply(d.players);
                const players = d.players || [];
                const notFound = d.not_found || [];
if (notFound.length > 0) {{
                    const ta = document.getElementById('bulk-lineup-text');
                    if (ta) {{
                        let nfHtml = '';
                        for (const nf of notFound) {{
                            const _marker = nf.pos + ' - ' + nf.name + ' - NOT FOUND';
                            if (ta.innerHTML.indexOf(_marker) !== -1) continue;
                            nfHtml += '<div style="color:#dc3545;font-weight:700;">' + _marker + '</div>';
                        }}
                        ta.innerHTML = nfHtml + ta.innerHTML;
                    }}
                }}
                _rwFitTextarea();
            }} catch (err) {{ /* silent */ }}
        }});

        async function loadTestRotowireMatches(leagueKey) {{
            const body = document.getElementById('test-league-' + leagueKey + '-list');
            const footer = document.getElementById('test-rotowire-footer');
            if (!body) return;
            body.innerHTML = '<div style="color:#94a3b8;font-size:14px;">Loading...</div>';
            try {{
                const r = await fetch('/lineup_ai/api/test_rotowire_matches/' + leagueKey, {{ cache: 'no-store' }});
                const d = await r.json();
                renderTestRotowireMatches(d, leagueKey);
            }} catch (e) {{
                body.innerHTML = '<div style="color:#f87171;font-size:14px;">Error: ' + e.message + '</div>';
            }}
        }}

        function renderTestRotowireMatches(d, leagueKey) {{
            const body = document.getElementById('test-league-' + leagueKey + '-list');
            const footer = document.getElementById('test-rotowire-footer');
            if (!body) return;

            const matches = (d && d.matches) || [];
            if (matches.length === 0) {{
                body.innerHTML = '<div style="color:#94a3b8;font-size:14px;">No upcoming matches</div>';
                if (footer) footer.textContent = '';
                return;
            }}

            let html = '';
            for (const m of matches) {{
                const kick = new Date((m.kickoff_ts || 0) * 1000);
                const kickStr = m.lv_time || kick.toLocaleDateString('en-GB', {{day:'2-digit',month:'short'}}) + ' ' + kick.toLocaleTimeString('en-GB', {{hour:'2-digit',minute:'2-digit'}});

                let openMatchBtn = '';
                if (m.home_id && m.away_id) {{
                    const openHref = '/lineup_ai/compare/' + encodeURIComponent(m.home_id) +
                        '?mid=' + encodeURIComponent('rw-' + m.home_id + '-' + m.away_id) +
                        '&home_id=' + encodeURIComponent(m.home_id) +
                        '&away_id=' + encodeURIComponent(m.away_id) +
                        '&home_name=' + encodeURIComponent(m.home_team) +
                        '&away_name=' + encodeURIComponent(m.away_team) +
                        '&rotowire_fran=1' +
                        '&rw_league=' + leagueKey +
                        '&kickoff_ts=' + (m.kickoff_ts || 0);
                    openMatchBtn = '<a href="' + openHref + '" target="_blank" rel="noopener" style="font-size:11px;color:#60a5fa;background:transparent;border:1px solid #1f2b40;padding:4px 9px;border-radius:5px;text-decoration:none;white-space:nowrap;font-weight:600;justify-self:end;" title="Open this match in Match mode with rotowire lineups applied">▶ Open Match</a>';
                }} else {{
                    const missing = !m.home_matched ? m.home_team : m.away_team;
                    openMatchBtn = '<span style="font-size:11px;color:#64748b;">No LV match: ' + missing + '</span>';
                }}

                const lineupBadge = m.lineup_posted
                    ? '<span style="color:#60a5fa;font-size:10px;font-weight:600;">Predicted</span>'
                    : (m.is_confirmed ? '<span style="color:#f87171;font-size:10px;font-weight:600;">Confirmed</span>' : '<span style="color:#94a3b8;font-size:10px;">Not posted</span>');

                html += '<div style="display:grid;grid-template-columns:60px 88px 1fr auto;align-items:center;column-gap:12px;padding:6px 10px;background:#172033;border-radius:6px;border:1px solid #1f2b40;">';
                html += '<span class="test-countdown" data-ts="' + (m.kickoff_ts || 0) + '" style="grid-column:1;font-size:12px;color:#94a3b8;width:60px;font-variant-numeric:tabular-nums;justify-self:start;"></span>';
                html += '<span style="grid-column:2;font-size:12px;color:#94a3b8;width:88px;font-variant-numeric:tabular-nums;justify-self:start;">' + kickStr + '</span>';
                html += '<div style="grid-column:3;display:flex;align-items:center;gap:8px;font-size:14px;color:#e8eef7;min-width:0;">';
                const pxiHomeFull = (m.pxi_home_matched === 11 && m.pxi_home_total === 11);
                const pxiHomePartial = (m.pxi_home_matched > 0 && !pxiHomeFull);
                const pxiAwayFull = (m.pxi_away_matched === 11 && m.pxi_away_total === 11);
                const pxiAwayPartial = (m.pxi_away_matched > 0 && !pxiAwayFull);
                if (pxiHomeFull) {{
                    html += '<span class="p11-check" title="11/11 Predicted XI matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#60a5fa;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;">✓</span>';
                }} else if (pxiHomePartial) {{
                    html += '<span class="p11-check p11-check-partial" title="' + (m.pxi_home_matched || 0) + '/11 matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#60a5fa;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;opacity:0.55;"></span>';
                }} else {{
                    html += '<span style="display:inline-block;width:18px;flex-shrink:0;"></span>';
                }}
                html += '<span style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + m.home_team + '</span>';
                html += '<span style="color:#64748b;font-size:12px;flex-shrink:0;">vs</span>';
                html += '<span style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + m.away_team + '</span>';
                if (pxiAwayFull) {{
                    html += '<span class="p11-check" title="11/11 Predicted XI matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#60a5fa;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;">✓</span>';
                }} else if (pxiAwayPartial) {{
                    html += '<span class="p11-check p11-check-partial" title="' + (m.pxi_away_matched || 0) + '/11 matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#60a5fa;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;opacity:0.55;"></span>';
                }}
                html += '<span style="font-size:10px;font-weight:600;color:' + (m.is_confirmed ? '#f87171' : '#60a5fa') + ';white-space:nowrap;">' + m.pxi_home_matched + '/' + m.pxi_home_total + ' · ' + m.pxi_away_matched + '/' + m.pxi_away_total + '</span>';
                html += lineupBadge;
                html += '</div>';
                html += '<span style="grid-column:4;justify-self:end;">' + openMatchBtn + '</span>';
                html += '</div>';
            }}

            body.innerHTML = html;
            if (footer) {{
                footer.textContent = '';
            }}
        }}

        // Sep 6 2026 — countdown ticks + auto-remove matches that
        // started more than 2 minutes ago (Test panel).
        function refreshTestCountdowns() {{
            const now = Math.floor(Date.now() / 1000);
            const spans = document.querySelectorAll('.test-countdown');
            spans.forEach(function (el) {{
                const ts = parseInt(el.getAttribute('data-ts') || '0', 10);
                if (!ts) return;
                const delta = ts - now;
                if (delta <= -120) {{
                    // Match started >= 2 min ago — remove the card
                    const card = el.closest('[data-kickoff]');
                    if (card && card.parentNode) card.parentNode.removeChild(card);
                    return;
                }}
                const days = Math.floor(delta / 86400);
                const hours = Math.floor((delta % 86400) / 3600);
                const minutes = Math.floor((delta % 3600) / 60);
                let body;
                if (delta <= 0) body = '0m';
                else if (days > 0) body = days + 'd ' + hours + 'h';
                else if (hours > 0) body = hours + 'h ' + (minutes < 10 ? '0' : '') + minutes + 'm';
                else body = minutes + 'm';
                el.textContent = '🕒 ' + body;
            }});
        }}
        setInterval(refreshTestCountdowns, 30);

        function applyTestRotowirePXI() {{
            const d = window._testRotowireData;
            if (!d) return;
        }}

        async function loadPredicted11() {{
            const body = document.getElementById('predicted11-body');
            const footer = document.getElementById('predicted11-footer');
            if (!body) return;
            body.innerHTML = '<div style="color:#94a3b8;font-size:14px;">Loading next LaLiga fixtures…</div>';
            try {{
                const r = await fetch('/lineup_ai/api/laliga_fixtures', {{ cache: 'no-store' }});
                if (!r.ok) throw new Error('HTTP ' + r.status);
                const data = await r.json();
                renderPredicted11(data);
                _predicted11Loaded = true;
            }} catch (e) {{
                body.innerHTML = '<div style="color:#f87171;font-size:14px;">⚠️ Could not load fixtures: ' + _escapeText(e.message) + '</div>';
                if (footer) footer.textContent = '';
            }}
        }}

        function renderPredicted11(data) {{
            const body = document.getElementById('predicted11-body');
            const footer = document.getElementById('predicted11-footer');
            if (!body) return;
            const fixtures = Array.isArray(data && data.fixtures) ? data.fixtures : [];
            if (fixtures.length === 0) {{
                body.innerHTML = '<div style="color:#94a3b8;font-size:14px;">No upcoming LaLiga matches.</div>';
                if (footer) footer.textContent = '';
                return;
            }}
            // Aug 22 2026 — Predicted XI show rules (v7, per-division
            // dropdown).
            //
            // Max asked for LaLiga and LaLiga 2 to live in separate
            // round pickers, not share one. The panel now renders one
            // outer block per division. Each block carries its own
            // active round header (the next round to play in that
            // division), expandable to reveal the matches.
            //
            // Group math:
            //   * Group fixtures by m.tournament (LaLiga vs LaLiga 2).
            //     Falls back to "LaLiga" when missing.
            //   * Inside each division, group by round label.
            //   * Active round = round with the smallest earliest
            //     still-live timestamp within that division.
            //   * Drop past matches (ts + 600s < now).

            // ----- Helpers shared across renders (moved up here
            // because every block below uses them) -----
            const madridFmt = (function () {{
                try {{
                    return new Intl.DateTimeFormat('en-GB', {{
                        timeZone: 'Europe/Madrid',
                        day: '2-digit', month: '2-digit',
                        hour: '2-digit', minute: '2-digit', hour12: false,
                    }});
                }} catch (e) {{
                    return null;
                }}
            }})();
            function pad2(n) {{ return String(n).padStart(2, '0'); }}
            function extractTime(ts) {{
                const d = new Date(ts * 1000);
                const parts = madridFmt ? madridFmt.formatToParts(d) : null;
                if (parts) {{
                    const map = {{}};
                    parts.forEach(function (p) {{ map[p.type] = p.value; }});
                    return (map.day || '00') + '.' + (map.month || '00') + '  ' + (map.hour || '00') + ':' + (map.minute || '00');
                }}
                return pad2(d.getDate()) + '.' + pad2(d.getMonth() + 1) + '  ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
            }}
            function renderMatchRow(m) {{
                const homeName = (m.home && m.home.name) || '?';
                const awayName = (m.away && m.away.name) || '?';
                const homeImg = (m.home && m.home.image) || '';
                const awayImg = (m.away && m.away.image) || '';
                const time = extractTime(m.timestamp);
                // Aug 22 2026 — countdown helper for "Match starts in 5h 12m".
                // Returns null for matches already started (or starting
                // in < 1 minute) so the caller can omit the span.
                const renderCountdown = function(ts) {{
                    if (!ts) return null;
                    const delta = ts - nowSec;
                    if (delta <= 0) return null;
                    const days = Math.floor(delta / 86400);
                    const hours = Math.floor((delta % 86400) / 3600);
                    const minutes = Math.floor((delta % 3600) / 60);
                    let body;
                    if (days > 0) {{
                        body = days + 'd ' + hours + 'h';
                    }} else if (hours > 0) {{
                        body = hours + 'h ' + pad2(minutes) + 'm';
                    }} else if (minutes > 0) {{
                        body = minutes + 'm';
                    }} else {{
                        return null;  // under 1 minute — start is imminent
                    }}
                    return '<span class="p11-countdown" data-ts="' + ts + '" ' +
                        'style="grid-column:1;font-size:11px;color:#94a3b8;white-space:nowrap;font-variant-numeric:tabular-nums;justify-self:start;">' +
                        '🕒 ' + body + '</span>';
                }};
                const countdownHtml = renderCountdown(m.timestamp);
                const mid = m.match_id || '';
                // Aug 24 2026 — Max asked to fix the columns in 🔮 Predicted XI
                // so dates / team names / Open Match button stay vertically
                // aligned across rows. The previous flex layout relied on
                // `min-width:90px` for the date and `flex:1` for the team
                // names which let long team names push the Open Match button
                // back and forth between rows. Switching to CSS Grid with
                // fixed column widths keeps every column locked in place.
                // Columns: 1=countdown (60px), 2=time (88px), 3=teams (1fr),
                // 4=Open Match (auto, justified end).
                let html = '<div style="display:grid;grid-template-columns:60px 88px 1fr auto;align-items:center;column-gap:12px;padding:6px 10px;background:#172033;border-radius:6px;border:1px solid #1f2b40;">';
                if (countdownHtml) html += countdownHtml;
                html += '<span style="grid-column:2;font-size:12px;color:#94a3b8;width:88px;font-variant-numeric:tabular-nums;justify-self:start;">' + time + '</span>';
                html += '<div style="grid-column:3;display:flex;align-items:center;gap:8px;font-size:14px;color:#e8eef7;min-width:0;">';
                const pxiHomeFull = (m.pxi_home_matched === 11 && m.pxi_home_total === 11);
                const pxiAwayFull = (m.pxi_away_matched === 11 && m.pxi_away_total === 11);
                const pxiHomePartial = (m.pxi_home_matched > 0 && !pxiHomeFull);
                const pxiAwayPartial = (m.pxi_away_matched > 0 && !pxiAwayFull);
                if (pxiHomeFull) {{
                    html += '<span class="p11-check" title="11/11 Predicted XI matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#60a5fa;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;">✓</span>';
                }} else if (pxiHomePartial) {{
                    html += '<span class="p11-check p11-check-partial" title="' + (m.pxi_home_matched || 0) + '/11 matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#60a5fa;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;opacity:0.55;"></span>';
                }} else {{
                    html += '<span style="display:inline-block;width:18px;flex-shrink:0;"></span>';
                }}
                // Aug 30 2026 — team logos removed (Max): the panel
                // shows names only, no club crests.
                html += '<span style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + _escapeText(homeName) + '</span>';
                html += '<span style="color:#64748b;font-size:12px;flex-shrink:0;">vs</span>';
                html += '<span style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + _escapeText(awayName) + '</span>';
                if (pxiAwayFull) {{
                    html += '<span class="p11-check" title="11/11 Predicted XI matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#60a5fa;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;">✓</span>';
                }} else if (pxiAwayPartial) {{
                    html += '<span class="p11-check p11-check-partial" title="' + (m.pxi_away_matched || 0) + '/11 matched" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#60a5fa;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;opacity:0.55;"></span>';
                }}
                html += '</div>';
                // Aug 24 2026 — countdown was moved to the LEFT of the
                // date/time column above. Removed the duplicate append
                // that used to live here.
                const homeId = (m.home && m.home.team_id) || '';
                const awayId = (m.away && m.away.team_id) || '';
                const openHref = '/lineup_ai/compare/' + encodeURIComponent(homeId || awayId || '') +
                    '?mid=' + encodeURIComponent(mid) +
                    '&home_id=' + encodeURIComponent(homeId) +
                    '&away_id=' + encodeURIComponent(awayId) +
                    '&home_name=' + encodeURIComponent(homeName) +
                    '&away_name=' + encodeURIComponent(awayName) +
                    '&autopxi=1';
                // Aug 24 2026 — Max asked to drop the 🔍 Check
                // Predicted XI button entirely. Predicted XI
                // should rely solely on the T-18h auto-builder
                // scheduler; users no longer trigger a manual
                // refresh per row. The ▶ Open Match link below
                // keeps the autopxi=1 URL flow alive for cases
                // where the user wants to drill into a specific
                // match.
                html += '<a href="' + openHref + '&kickoff_ts=' + (m.timestamp || 0) + '" target="_blank" rel="noopener" style="grid-column:4;font-size:11px;color:#60a5fa;background:transparent;border:1px solid #1f2b40;padding:4px 9px;border-radius:5px;text-decoration:none;white-space:nowrap;font-weight:600;justify-self:end;" title="Open this match in Match mode (new tab) with Predicted XI applied">▶ Open Match</a>';
                html += '</div>';
                return html;
            }}

            // Aug 24 2026 — 🔍 Check Predicted XI click handler
            // was removed (Max asked to drop the button). The
            // T-18h auto-builder scheduler is now the only path
            // that populates the predicted XI cache; users no
            // longer trigger manual per-row refreshes.

            const nowSec = Math.floor(Date.now() / 1000);
            const PAST_GRACE_SEC = 10 * 60;

            // Sort rounds numerically so Round 1 < Round 2 < Round 3.
            const sortRound = function (a, b) {{
                if (a === '__upcoming__') return 1;
                if (b === '__upcoming__') return -1;
                const na = parseInt((a.match(/\d+/) || ['999'])[0], 10);
                const nb = parseInt((b.match(/\d+/) || ['999'])[0], 10);
                if (na !== nb) return na - nb;
                return a.localeCompare(b);
            }};

            // First-level split: by tournament/division.
            const byDivision = {{}};
            fixtures.forEach(function (m) {{
                const tk = (m.tournament && String(m.tournament).trim()) || 'LaLiga';
                if (!byDivision[tk]) byDivision[tk] = [];
                byDivision[tk].push(m);
            }});
            const divisionKeys = Object.keys(byDivision).sort();

            // For each division, group matches by round and find the
            // active round. We store the rendered HTML per division
            // and concatenate below.
            const divisionBlocks = [];
            divisionKeys.forEach(function (divisionKey) {{
                const divMatches = byDivision[divisionKey];
                // Group by round.
                const byRound = {{}};
                divMatches.forEach(function (m) {{
                    const rk = (m.round && String(m.round).trim()) || '__upcoming__';
                    if (!byRound[rk]) byRound[rk] = [];
                    byRound[rk].push(m);
                }});
                const roundKeys = Object.keys(byRound).sort(sortRound);

                // Earliest live ts per round.
                const earliest = {{}};
                roundKeys.forEach(function (rk) {{
                    const liveTs = byRound[rk]
                        .map(function (m) {{ return m.timestamp || 0; }})
                        .filter(function (t) {{ return (t + PAST_GRACE_SEC) >= nowSec; }});
                    earliest[rk] = liveTs.length ? Math.min.apply(null, liveTs) : Infinity;
                }});
                // Active round within this division.
                let activeRk = '';
                let activeEarliest = Infinity;
                roundKeys.forEach(function (rk) {{
                    const e = earliest[rk];
                    if (e === Infinity) return;
                    if (e < activeEarliest) {{
                        activeEarliest = e;
                        activeRk = rk;
                    }}
                }});
                const live = activeRk
                    ? byRound[activeRk]
                        .filter(function (m) {{ return (m.timestamp + PAST_GRACE_SEC) >= nowSec; }})
                        .sort(function (a, b) {{ return (a.timestamp || 0) - (b.timestamp || 0); }})
                    : [];

                divisionBlocks.push({{
                    divisionKey: divisionKey,
                    activeRoundKey: activeRk,
                    roundKeys: roundKeys,
                    live: live,
                    byRound: byRound,
                }});
            }});

            // Outer container.
            let html = '<div id="p11-root" style="display:flex;flex-direction:column;gap:10px;">';
            if (!divisionBlocks.length) {{
                html += '<div style="color:#94a3b8;font-size:14px;padding:6px 2px;">No upcoming LaLiga matches.</div>';
            }}
            divisionBlocks.forEach(function (block) {{
                const divisionKey = block.divisionKey;
                const live = block.live;
                // Aug 30 2026 — display names: country merged into the
                // division header, so no separate country label blocks.
                const P11_DISPLAY_NAMES = {{
                    'LaLiga': 'Spain - La Liga',
                    'LaLiga 2': 'Spain - La Liga 2',
                    'Serie A': 'Italy - Serie A'
                }};
                const divLabel = P11_DISPLAY_NAMES[divisionKey] || divisionKey;
                if (!live.length) {{
                    // No active round with live matches in this division.
                    // Still render the block so the user knows the
                    // division is tracked; show a tiny hint instead of
                    // a dropdown.
                    html += '<div style="background:#0f1623;border-radius:8px;border:1px solid #1f2b40;overflow:hidden;">';
                    html += '<div style="display:flex;align-items:center;gap:10px;padding:11px 14px;background:#0f1a2e;">';
                    html += '<span style="font-size:13px;color:#60a5fa;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">' + _escapeText(divLabel) + '</span>';
                    html += '<span style="font-size:10px;background:#475569;color:#0b1020;padding:2px 7px;border-radius:10px;font-weight:700;letter-spacing:0.04em;">NO LIVE ROUND</span>';
                    html += '</div>';
                    html += '<div style="background:#0b1020;border-top:1px solid #1f2b40;padding:10px 14px;color:#64748b;font-size:12px;">No upcoming fixtures in this division.</div>';
                    html += '</div>';
                    return;
                }}

                // Round date range for the active round.
                const roundFirst = live[0] ? live[0].timestamp : 0;
                const roundLast = live.length ? live[live.length - 1].timestamp : 0;
                const roundDateRange = (function () {{
                    if (!live.length) return '';
                    const fmt = function (ts) {{
                        const d = new Date(ts * 1000);
                        const p = madridFmt ? madridFmt.formatToParts(d) : null;
                        if (p) {{
                            const m = {{}};
                            p.forEach(function (x) {{ m[x.type] = x.value; }});
                            return (m.day || '00') + '.' + (m.month || '00');
                        }}
                        return pad2(d.getDate()) + '.' + pad2(d.getMonth() + 1);
                    }};
                    const a = fmt(roundFirst);
                    const b = fmt(roundLast);
                    return (a === b) ? a : a + '–' + b;
                }})();

                // Outer per-division block. Aug 22 2026 — every
                // division now renders its own OUTER dropdown (the
                // round picker). The tournament sub-block that v6 had
                // is gone — it was redundant once we promoted LaLiga
                // and LaLiga 2 to top-level peers.
                const divId = 'p11-div-' + encodeURIComponent(divisionKey).replace(/%/g, '_');
                const roundId = 'p11-round-' + encodeURIComponent(divisionKey).replace(/%/g, '_');
                html += '<div style="background:#0f1623;border-radius:8px;border:1px solid #1f2b40;overflow:hidden;">';
                // Division header (always visible)
                html += '<div style="display:flex;align-items:center;gap:10px;padding:11px 14px;background:#0f1a2e;border-bottom:1px solid #1f2b40;">';
                html += '<span style="font-size:13px;color:#60a5fa;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">' + _escapeText(divLabel) + '</span>';
                html += '</div>';
                // Round picker: header is the active round, opens on
                // click to reveal the round selector and the matches.
                html += '<div data-p11-toggle="' + roundId + '" style="display:flex;align-items:center;gap:10px;padding:11px 14px;cursor:pointer;user-select:none;">';
                html += '<span data-p11-chevron="' + roundId + '" style="color:#60a5fa;font-size:14px;transition:transform 0.15s ease;">▶</span>';
                html += '<div style="flex:1;display:flex;align-items:center;gap:10px;">';
                html += '<span style="font-size:13px;color:#60a5fa;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">Round</span>';
                html += '<span style="font-size:10px;background:#22c55e;color:#0b1020;padding:2px 7px;border-radius:10px;font-weight:700;letter-spacing:0.04em;">NEXT</span>';
                if (roundDateRange) {{
                    html += '<span style="font-size:11px;color:#64748b;font-weight:500;">' + _escapeText(roundDateRange) + '</span>';
                }}
                html += '</div>';
                html += '<span style="font-size:11px;color:#64748b;">' + live.length + ' match' + (live.length === 1 ? '' : 'es') + '</span>';
                html += '</div>';
                // Round body — closed by default. Inside: a row of
                // round chips that the user can click to switch the
                // active round for this division.
                html += '<div id="' + roundId + '" style="background:#0b1020;border-top:1px solid #1f2b40;display:none;">';
                // Round picker row — every round the division has.
                html += '<div style="display:flex;flex-wrap:wrap;gap:6px;padding:10px 14px 6px 14px;">';
                block.roundKeys.forEach(function (rk) {{
                    const isActive = rk === block.activeRoundKey;
                    const rkClass = isActive
                        ? 'p11-round-chip p11-round-chip-active'
                        : 'p11-round-chip';
                    html += '<button type="button" data-p11-round-key="' + _escapeText(rk) + '" data-p11-division="' + _escapeText(divisionKey) + '" class="' + rkClass + '" style="font-size:11px;padding:4px 10px;border-radius:12px;border:1px solid ' + (isActive ? '#60a5fa' : '#1f2b40') + ';background:' + (isActive ? '#60a5fa' : 'transparent') + ';color:' + (isActive ? '#0b1020' : '#cbd5e1') + ';cursor:pointer;font-weight:600;letter-spacing:0.04em;">' + _escapeText(rk) + '</button>';
                }});
                html += '</div>';
                // Match list for the currently selected round.
                html += '<div data-p11-round-body="' + _escapeText(divisionKey) + '" style="display:flex;flex-direction:column;gap:6px;padding:6px 14px 14px 14px;">';
                live.forEach(function (m) {{ html += renderMatchRow(m); }});
                html += '</div>';
                html += '</div>';
                html += '</div>';
            }});
            html += '</div>';
            body.innerHTML = html;

            // Delegated click handler for both the round picker toggle
            // and the per-division chip selector.
            const root = document.getElementById('p11-root');
            if (root && !root._wired) {{
                root.addEventListener('click', function (ev) {{
                    const header = ev.target.closest('[data-p11-toggle]');
                    if (header) {{
                        const pid = header.getAttribute('data-p11-toggle');
                        const panel = document.getElementById(pid);
                        const chev = root.querySelector('[data-p11-chevron="' + pid + '"]');
                        if (!panel) return;
                        const willOpen = panel.style.display === 'none' || getComputedStyle(panel).display === 'none';
                        panel.style.display = willOpen ? 'block' : 'none';
                        if (chev) chev.style.transform = willOpen ? 'rotate(90deg)' : '';
                        return;
                    }}
                    const chip = ev.target.closest('[data-p11-round-key]');
                    if (chip) {{
                        const division = chip.getAttribute('data-p11-division');
                        const rk = chip.getAttribute('data-p11-round-key');
                        if (!division || !rk) return;
                        // Update active chip styles.
                        root.querySelectorAll('[data-p11-round-key][data-p11-division="' + division + '"]').forEach(function (b) {{
                            const active = b === chip;
                            b.style.background = active ? '#60a5fa' : 'transparent';
                            b.style.color = active ? '#0b1020' : '#cbd5e1';
                            b.style.borderColor = active ? '#60a5fa' : '#1f2b40';
                        }});
                        // Find the block and re-render its body with
                        // the picked round's matches.
                        const block = divisionBlocks.find(function (b) {{ return b.divisionKey === division; }});
                        if (!block) return;
                        const picks = (block.byRound[rk] || [])
                            .filter(function (m) {{ return (m.timestamp + PAST_GRACE_SEC) >= nowSec; }})
                            .sort(function (a, b) {{ return (a.timestamp || 0) - (b.timestamp || 0); }});
                        const bodyDiv = root.querySelector('[data-p11-round-body="' + division + '"]');
                        if (bodyDiv) {{
                            let inner = '';
                            picks.forEach(function (m) {{ inner += renderMatchRow(m); }});
                            bodyDiv.innerHTML = inner || '<div style="color:#64748b;font-size:12px;padding:8px 2px;">No matches in this round yet.</div>';
                        }}
                    }}
                }});
                root._wired = true;
            }}

            if (footer) {{
                const teamCount = data.team_count || 0;
                const fetchedAt = data.fetched_at ? new Date(data.fetched_at * 1000) : null;
                const fetchedStr = fetchedAt ? pad2(fetchedAt.getDate()) + '.' + pad2(fetchedAt.getMonth() + 1) + ' ' + pad2(fetchedAt.getHours()) + ':' + pad2(fetchedAt.getMinutes()) : '?';
                footer.textContent = ''
            }}
        }}
        function _escapeText(s) {{
            return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {{
                return {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }}[c];
            }});
        }}

        function toggleFaq() {{
            var host = document.getElementById('faq-host');
            if (!host) return;
            var isVisible = host.style.display === 'flex';
            host.style.display = isVisible ? 'none' : 'flex';
        }}
        // 🔄 Reverse Odds calculator — Aug 26 2026 (Max).
        // Modal-only feature: open via the 🔄 Reverse Odds button next
        // to 🔮 Predicted XI, fill 3 inputs, press Calculate.
        // Pure client-side: no fetch, no DB, no persistence.
        function _roNotifyClosed() {{
            // Aug 30 2026 — single close-notification path: clear the
            // Match-mode dim on THIS frame (if any) and tell the parent
            // so it clears the dim on the OTHER frame too.
            document.body.classList.remove('ro-dim');
            try {{ window.parent.postMessage({{ type: 'reverseOddsClosed' }}, '*'); }} catch (e) {{ }}
        }}
        function toggleReverseOdds() {{
            var host = document.getElementById('reverse-odds-host');
            if (!host) return;
            var willOpen = host.style.display !== 'flex';
            host.style.display = willOpen ? 'flex' : 'none';
            // Aug 30 2026 — Match mode: when the modal closes, tell the
            // parent so it clears the gray highlight on the other frame.
            if (!willOpen) {{
                _roNotifyClosed();
            }}
        }}
        function _roFmt(n) {{
            // Standard mathematical rounding to 2 decimals. Avoid
            // toFixed's known quirks with floating point — round via
            // scaling to integer first.
            return (Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2);
        }}
        function _roParseField(el, label) {{
            var raw = (el && el.value ? el.value : '').trim();
            // Aug 26 2026 — Max asked: a user should be able to
            // calculate ONLY the Home side or ONLY the Away side
            // (i.e. leave one odd blank). Empty input is now a
            // valid "skip this side" signal, not an error.
            if (!raw) return {{ ok: true, value: null }};
            // Allow "1,83" (comma decimal) — replace with dot.
            var normalized = raw.replace(',', '.');
            var n = Number(normalized);
            if (typeof n !== 'number' || !isFinite(n) || isNaN(n)) {{
                return {{ ok: false, msg: label + ' must be a number.' }};
            }}
            if (n < 0) return {{ ok: false, msg: label + ' cannot be negative.' }};
            return {{ ok: true, value: n }};
        }}
        function calculateReverseOdds() {{
            var errEl = document.getElementById('ro-error');
            var resultEl = document.getElementById('ro-result');
            var h2aEl = document.getElementById('ro-h2a');
            var a2hEl = document.getElementById('ro-a2h');
            function hideError() {{
                if (errEl) {{ errEl.style.display = 'none'; errEl.textContent = ''; }}
            }}
            function showError(msg) {{
                if (!errEl) return;
                errEl.textContent = msg;
                errEl.style.display = 'block';
            }}
            function hideResult() {{
                if (resultEl) resultEl.style.display = 'none';
                if (h2aEl) h2aEl.textContent = '—';
                if (a2hEl) a2hEl.textContent = '—';
            }}
            var home = _roParseField(document.getElementById('ro-home-odd'), 'Home Odd');
            if (!home.ok) {{ hideResult(); showError(home.msg); return; }}
            var away = _roParseField(document.getElementById('ro-away-odd'), 'Away Odd');
            if (!away.ok) {{ hideResult(); showError(away.msg); return; }}
            // Aug 26 2026 — at least ONE of Home/Away must be filled,
            // otherwise there is nothing to calculate.
            if (home.value === null && away.value === null) {{
                hideResult();
                showError('Enter at least one of Home Odd or Away Odd.');
                return;
            }}
            var htl = _roParseField(document.getElementById('ro-htl-index'), 'ORI');
            if (!htl.ok) {{ hideResult(); showError(htl.msg); return; }}
            // ORI is still REQUIRED even for a single-side
            // calculation — the spec didn't drop this requirement
            // when adding partial support.
            if (htl.value === null) {{
                hideResult();
                showError('ORI is required.');
                return;
            }}
            if (htl.value === 0) {{ hideResult(); showError('ORI cannot be zero.'); return; }}
            // Aug 26 2026 — H2A / A2H are now independent:
            //   - H2A computed only when Home Odd + ORI are set
            //   - A2H computed only when Away Odd + ORI are set
            //   - missing side stays as "—" in the result panel.
            var h2a = (home.value !== null) ? (home.value - 1) * htl.value + 1 : null;
            var a2h = (away.value !== null) ? (away.value - 1) / htl.value + 1 : null;
            hideError();
            if (resultEl) resultEl.style.display = 'block';
            if (h2aEl) h2aEl.textContent = (h2a !== null) ? _roFmt(h2a) : '—';
            if (a2hEl) a2hEl.textContent = (a2h !== null) ? _roFmt(a2h) : '—';
        }}
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                var faq = document.getElementById('faq-host');
                if (faq && faq.style.display === 'flex') faq.style.display = 'none';
                var ro = document.getElementById('reverse-odds-host');
                if (ro && ro.style.display === 'flex') {{
                    ro.style.display = 'none';
                    // Aug 30 2026 — notify the parent so the OTHER frame's
                    // gray highlight is cleared too (Match mode).
                    _roNotifyClosed();
                }}
            }}
        }});
        document.addEventListener('click', function(e) {{
            // Aug 30 2026 — Match mode: THIS frame is dimmed (ro-dim)
            // while the Reverse Odds modal is open in the OTHER frame.
            // The dim overlay intercepts every click here; any click in
            // the dimmed frame should close that modal too (same UX as
            // Team mode's click-outside).
            if (document.body.classList.contains('ro-dim')) {{
                _roNotifyClosed();
                try {{ window.parent.postMessage({{ type: 'reverseOddsOutsideClick' }}, '*'); }} catch (e) {{ }}
                return;
            }}
            // Aug 26 2026 — Max asked the 🔄 Reverse Odds modal to close
            // on any click outside the white card (same pattern as the
            // FAQ modal below). Only trigger when the click target is
            // the host backdrop itself, NOT the card or its descendants,
            // so clicking inputs / buttons / labels keeps the modal open.
            var roHost = document.getElementById('reverse-odds-host');
            if (roHost && roHost.style.display === 'flex' && e.target === roHost) {{
                roHost.style.display = 'none';
                // Aug 30 2026 — Match mode: the parent must clear the
                // gray highlight on the OTHER frame as well.
                _roNotifyClosed();
            }}
            var host = document.getElementById('faq-host');
            if (host && host.style.display === 'flex' && e.target === host) {{
                host.style.display = 'none';
            }}
        }});
        function selectTab(el, name) {{
            document.querySelectorAll('.header-tabs .tab').forEach(function(t) {{ t.classList.remove('active'); }});
            el.classList.add('active');
            var bar = document.getElementById('coach-stadium-bar');
            if (bar) bar.style.display = (name === 'Squad') ? 'flex' : 'none';
        }}
        function showTooltip(el) {{ var t = el.querySelector('.tooltip-delay'); if(t){{ _tooltipTimer = setTimeout(function(){{ var r = el.getBoundingClientRect(); t.style.left = (r.left + r.width/2) + 'px'; t.style.top = (r.top - 8) + 'px'; t.style.transform = 'translate(-50%, -100%)'; t.style.visibility='visible'; t.style.opacity='1'; }}, 800); }} }}
        function hideTooltip(el) {{ if(_tooltipTimer){{ clearTimeout(_tooltipTimer); _tooltipTimer=null; }} var t = el.querySelector('.tooltip-delay'); if(t){{ t.style.opacity='0'; setTimeout(function(){{ t.style.visibility='hidden'; }}, 300); }} }}
        const MISSING_STATUSES = ['Injury', 'Red card', 'Yellow red card', 'Not playing (Called up)', 'Not playing (Other)'];
        const DOUBTFUL_STATUSES = ['Doubt', 'Doubt + Last yellow card'];
        const RETURNING_STATUSES = ['Return (Injury)', 'Return (Susp)', 'Return (Called up)', 'Return (Other)'];
        const TRANSFER_IN_STATUSES = ['New player'];
        const TRANSFER_OUT_STATUSES = ['Left the team'];

        const TEAM_ID = "{team_id}";
        const CACHE_AGE_SECONDS = {cache_age_seconds if cache_age_seconds else 'null'};
        const CACHE_TTL_SECONDS = 3600; // 1 hour
        const TOTAL_GOALS = {total_goals};
        const TOTAL_ASSISTS = {total_assists};

        function pad2(n) {{ return String(n).padStart(2, '0'); }}
        function snapshotStamp(d) {{ return pad2(d.getDate()) + '.' + pad2(d.getMonth()+1) + '.' + String(d.getFullYear()).slice(-2) + ' - ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()); }}
        function snapshotName(dateObj) {{ return "{team_name} — Last Update (" + snapshotStamp(dateObj) + ")"; }}
        function cellText(cells, idx) {{ return cells[idx] ? cells[idx].textContent.trim() : ''; }}

        function collectTeamState() {{
            const players = [];
            document.querySelectorAll('.main-table tbody tr[data-player-name]').forEach(row => {{
                const cells = row.querySelectorAll('td');
                const last3 = [];
                for (let i = 12; i <= 14; i++) last3.push(cells[i] ? cells[i].innerHTML : '');
                players.push({{
                    name: row.getAttribute('data-player-name') || cellText(cells, 2),
                    number: cellText(cells, 0),
                    nationality_html: cells[1] ? cells[1].innerHTML : '',
                    status: (row.querySelector('.status-select') || {{}}).value || 'Available',
                    age: cellText(cells, 4),
                    mv: cellText(cells, 5),
                    pos: cellText(cells, 6),
                    role_html: cells[7] ? cells[7].innerHTML : '',
                    impact: cellText(cells, 8),
                    squad: !!(row.querySelector('.squad-checkbox') || {{}}).checked,
                    pxi: !!(row.querySelector('.xi-checkbox') || {{}}).checked,
                    sxi: !!(row.querySelector('.starting-checkbox') || {{}}).checked,
                    last3_html: last3,
                    stats: {{apps: cellText(cells, 15), min: cellText(cells, 16), g: cellText(cells, 17), a: cellText(cells, 18), yc: cellText(cells, 19), rc: cellText(cells, 20)}},
                    row_html: row.innerHTML
                }});
            }});
            return {{
                version: 1,
                team_id: TEAM_ID,
                team_name: "{team_name}",
                meta: {{
                    saved_local: new Date().toISOString(),
                    cache_badge: document.querySelector('.cache-badge') ? document.querySelector('.cache-badge').textContent.trim() : '',
                    comparison_html: document.getElementById('comparison-table') ? document.getElementById('comparison-table').innerHTML : '',
                    info_squad_html: document.getElementById('info-bar-squad') ? document.getElementById('info-bar-squad').innerHTML : '',
                    last3_header: Array.from(document.querySelectorAll('thead tr:nth-child(2) th')).map(th => th.innerHTML)
                }},
                players: players,
                page_html: document.querySelector('.main-table') ? document.querySelector('.main-table').innerHTML : ''
            }};
        }}

        function restoreTeamState(data) {{
            if (!data || !Array.isArray(data.players)) return;
            const byName = new Map(data.players.map(p => [p.name, p]));
            document.querySelectorAll('.main-table tbody tr[data-player-name]').forEach(row => {{
                const st = byName.get(row.getAttribute('data-player-name'));
                if (!st) return;
                const cells = row.querySelectorAll('td');
                const status = row.querySelector('.status-select');
                const squad = row.querySelector('.squad-checkbox');
                const pxi = row.querySelector('.xi-checkbox');
                const sxi = row.querySelector('.starting-checkbox');
                if (status) {{ status.value = st.status || 'Available'; if (window.updateStatusIcon) updateStatusIcon(status); }}
                if (squad) {{ squad.checked = !!st.squad; squad.style.background = squad.checked ? '#000' : '#e0e0e0'; squad.style.border = squad.checked ? 'none' : '2px solid #333'; }}
                if (pxi) pxi.checked = !!st.pxi;
                if (sxi) sxi.checked = !!st.sxi;
                if (st.last3_html && Array.isArray(st.last3_html)) {{ for (let i=0; i<3; i++) if (cells[12+i]) cells[12+i].innerHTML = st.last3_html[i] || ''; }}
                if (st.stats) {{
                    if (cells[15]) cells[15].textContent = st.stats.apps || '';
                    if (cells[16]) cells[16].textContent = st.stats.min || '';
                    if (cells[17]) cells[17].textContent = st.stats.g || '';
                    if (cells[18]) cells[18].textContent = st.stats.a || '';
                    if (cells[19]) cells[19].textContent = st.stats.yc || '';
                    if (cells[20]) cells[20].textContent = st.stats.rc || '';
                }}
                if (cells[5] && st.mv) cells[5].textContent = st.mv;
                if (cells[7] && st.role_html) cells[7].innerHTML = st.role_html;
                if (cells[8] && st.impact) cells[8].textContent = st.impact;
            }});
            updateXICounter(document.querySelector('.xi-checkbox'));
            updateStartingCounter(document.querySelector('.starting-checkbox'));
            recalcPossibleXIStats();
            recalcSelectedStartingStats();
            recalcValueComparison();
        }}

        function setSnapshotMode(snapshotNameText) {{
            document.body.classList.add('snapshot-mode');
            const banner = document.getElementById('snapshot-mode-banner');
            if (banner) banner.firstChild.textContent = 'Snapshot mode: ' + snapshotNameText + ' ';
        }}
        function returnToLiveTeam() {{ window.location.href = window.location.pathname; }}

        function renderMySquads(items) {{
            const list = document.getElementById('my-squads-list');
            if (!list) return;
            if (!items || !items.length) {{ list.innerHTML = '<div class="snapshot-empty-list">No saved squads yet.</div>'; return; }}
            list.innerHTML = items.map(item => '<div class="snapshot-list-item" data-snapshot-id="' + item.id + '">' +
                '<div class="snapshot-list-name">' + item.name + '</div>' +
                '<div class="snapshot-list-actions">' +
                '<button type="button" onclick="openSnapshot(event,' + item.id + ')">Open</button>' +
                '<button type="button" onclick="renameSnapshot(event,' + item.id + ')">Rename</button>' +
                '<button type="button" class="snapshot-delete" onclick="deleteSnapshot(event,' + item.id + ')">Delete</button>' +
                '</div></div>').join('');
        }}

        async function loadSnapshotsList() {{
            try {{
                const res = await fetch('/lineup_ai/snapshots/' + encodeURIComponent(TEAM_ID));
                const json = await res.json();
                if (json && json.ok) renderMySquads(json.snapshots || []);
            }} catch(e) {{}}
        }}

        async function openSnapshot(evt, id) {{
            if (evt) evt.stopPropagation();
            const res = await fetch('/lineup_ai/snapshots/' + encodeURIComponent(TEAM_ID) + '/' + encodeURIComponent(id));
            const json = await res.json();
            if (!res.ok || !json.ok) {{ alert(json.error || 'snapshot not found'); return; }}
            document.querySelectorAll('.snapshot-list-item').forEach(el => el.classList.toggle('active', el.getAttribute('data-snapshot-id') == String(id)));
            restoreTeamState(json.snapshot.data);
            setSnapshotMode(json.snapshot.name);
        }}

        async function renameSnapshot(evt, id) {{
            if (evt) evt.stopPropagation();
            const current = (evt && evt.target.closest('.snapshot-list-item') && evt.target.closest('.snapshot-list-item').querySelector('.snapshot-list-name')) ? evt.target.closest('.snapshot-list-item').querySelector('.snapshot-list-name').textContent : '';
            const name = prompt('Rename snapshot', current);
            if (!name) return;
            const res = await fetch('/lineup_ai/snapshots/' + encodeURIComponent(TEAM_ID) + '/' + encodeURIComponent(id), {{method:'PATCH', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{name}})}});
            const json = await res.json();
            if (!res.ok || !json.ok) {{ alert(json.error || 'rename failed'); return; }}
            await loadSnapshotsList();
        }}

        async function deleteSnapshot(evt, id) {{
            if (evt) evt.stopPropagation();
            if (!confirm('Delete this saved squad?')) return;
            const res = await fetch('/lineup_ai/snapshots/' + encodeURIComponent(TEAM_ID) + '/' + encodeURIComponent(id), {{method:'DELETE'}});
            const json = await res.json();
            if (!res.ok || !json.ok) {{ alert(json.error || 'delete failed'); return; }}
            await loadSnapshotsList();
        }}

        async function updateData() {{
            const btn = document.getElementById('update-data-btn');
            const counterEl = document.getElementById('update-counter');
            if (!btn || btn.disabled) return;
            btn.disabled = true;
            btn.innerHTML = '⏳ Updating...';
            const startTime = Date.now();

            // Счётчик — справа от ♻️ Refresh
            let seconds = 0;
            const counterInterval = setInterval(() => {{
                seconds++;
                if (counterEl) {{ counterEl.textContent = '🔄 ' + seconds + 's'; counterEl.style.color = 'rgba(255,255,255,0.85)'; }}
            }}, 1000);

            try {{
                const r = await fetch('/lineup_ai/api/fetch/' + TEAM_ID + '?_t=' + Date.now(), {{ cache: 'no-store' }});
                clearInterval(counterInterval);
                console.log('[UpdateData] status=' + r.status);
                if (!r.ok) throw new Error('HTTP ' + r.status);
                const data = await r.json();
                console.log('[UpdateData] response:', data);

                const duration = ((Date.now() - startTime) / 1000).toFixed(1);
                const msg = data.changed
                    ? '✅ Updated in ' + duration + 's'
                    : '✓ Cache refreshed in ' + duration + 's';
                if (counterEl) {{ counterEl.textContent = msg; counterEl.style.color = '#7ee787'; }}
                btn.innerHTML = '♻️ Refresh';
                btn.disabled = false;

                // Reload page immediately with cache-bust.
                // IMPORTANT (Jul 23 2026): preserve ?embed=1 if present.
                // Without it, Match mode iframes lose the .embed-mode class
                // on the body, the .team-nav-sidebar becomes visible, and
                // the user sees a SECOND sidebar in Match mode.
                const url = location.pathname + location.search.replace(/^[^?]*\?/, '?_v=' + Date.now() + '&') + (location.search ? '' : '?_v=' + Date.now());
                window.location.href = url;
            }} catch (e) {{
                clearInterval(counterInterval);
                console.error('[UpdateData] error:', e);
                if (counterEl) {{ counterEl.textContent = '❌ ' + (e.message || 'Error'); counterEl.style.color = '#ff7b7b'; }}
                btn.disabled = false;
                btn.innerHTML = '♻️ Refresh';
            }}
        }}

        // ===================================================================
        // Tournament dropdown — per-tournament Apps/Min/G/A/YC/RC
        // Aug 20 2026 — replaces /tournaments/ (Flashscore-only) with
        // /per_tournament/ which is backed by /teams/squad on RapidAPI.
        // API-only: no HTML scraping. The endpoint walks the squad tab_name
        // groups (Allsvenskan / Europa League / Conference League / Total)
        // and exposes per-player per-tab stats. We only display the value
        // columns (15..20). DOM emoji and ⭐ / 👑 badges stay put — we just
        // need a single canonical lookup name per row, and the Flashscore
        // API returns clean "Surname Name" so all we have to do is swap
        // the DOM's "Name Surname" before matching.
        // ===================================================================
        function _escapeAttr(s) {{
            // Minimal escape for HTML attribute / option text. Tournament
            // names are plain ASCII so the only chars we really need to
            // handle are quotes / ampersand; the regex stays cheap.
            return String(s).replace(/[&<>"']/g, function (c) {{
                return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];
            }});
        }}

        async function loadTournaments() {{
            const sel = document.getElementById('tournament-select');
            if (!sel) return;
            const teamId = (typeof CURRENT_TEAM_ID !== 'undefined' && CURRENT_TEAM_ID) ||
                           (typeof TEAM_ID !== 'undefined' && TEAM_ID) || '';
            if (!teamId) return;
            sel.innerHTML = '<option value="" style="color:#333;">Loading…</option>';
            try {{
                const r = await fetch('/lineup_ai/api/per_tournament/' + encodeURIComponent(teamId), {{ cache: 'no-store' }});
                if (!r.ok) throw new Error('HTTP ' + r.status);
                const data = await r.json();
                const tabs = Array.isArray(data.tabs) ? data.tabs : [];
                if (tabs.length === 0) {{
                    sel.innerHTML = '<option value="" style="color:#333;">No tournaments</option>';
                    return;
                }}
                // Build options. "Total" first (default — drives IS / Squad Role),
                // then the rest in API order.
                const ordered = [];
                const total = tabs.find(t => t.key === 'Total');
                if (total) ordered.push(total);
                for (const t of tabs) {{
                    if (t.key !== 'Total') ordered.push(t);
                }}
                let html = '';
                for (const t of ordered) {{
                    const label = t.label || t.key;
                    html += '<option value="' + _escapeAttr(t.key) + '" style="color:#333;">' + _escapeAttr(label) + '</option>';
                }}
                sel.innerHTML = html;
                // Stash the per-player map so applyTournamentFilter can find it
                // without a second round-trip.
                const tbody = document.querySelector('.main-table tbody');
                if (tbody) {{
                    tbody.setAttribute('data-tournament-players', JSON.stringify(data.players || {{}}));
                }}
                sel.value = 'Total';
            }} catch (e) {{
                console.error('[tournament] load failed:', e);
                sel.innerHTML = '<option value="" style="color:#333;">—</option>';
            }}
        }}

        function onTournamentChange(value) {{
            const sel = document.getElementById('tournament-select');
            if (sel) sel.value = value;
            applyTournamentFilter(value);
        }}

        function _swapNameDomToApi(domName) {{
            // DOM stores "Name Surname ⭐" (sometimes with emoji / 👑 / ⚽ / 👟).
            // Flashscore returns "Surname Name" (clean). Strip emoji + badges
            // via the last-word heuristic: keep only letters / spaces / accent,
            // then move the LAST word to the front.
            // (We deliberately do NOT use \p{{L}} unicode regex here — different
            // browsers historically behaved differently with it. ASCII letters
            // + a small set of accented letters is enough for the current
            // Soccerway / Flashscore dataset, and keeps this code stable.)
            let cleaned = (domName || '').replace(/[^A-Za-zÀ-ÿŒœ' .-]/g, ' ').replace(/\s+/g, ' ').trim();
            if (cleaned.indexOf(' ') <= 0) return cleaned;
            const parts = cleaned.split(' ');
            // Move last token (the surname, in DOM format) to the front.
            return parts[parts.length - 1] + ' ' + parts.slice(0, -1).join(' ');
        }}

        function applyTournamentFilter(tournamentKey) {{
            const tbody = document.querySelector('.main-table tbody');
            if (!tbody) return;
            const playersByName = JSON.parse(tbody.getAttribute('data-tournament-players') || '{{}}');
            const isTotal = (tournamentKey === 'Total' || !tournamentKey);
            const rows = Array.from(tbody.querySelectorAll('tr'));

            // Capture original (Total) values AND original row order on first
            // touch. The original row order is what the user expects to see
            // when they switch back to Total — restoring the cells but
            // leaving rows in their sorted-by-Min order would be jarring.
            if (!tbody.getAttribute('data-initial-order')) {{
                tbody.setAttribute('data-initial-order', rows.map(function (r) {{ return r.getAttribute('data-player-name') || ''; }}).join('\u0001'));
            }}

            // Capture original (Total) values on first touch so we can restore.
            const captureRow = (row) => {{
                const cells = row.querySelectorAll('td');
                [15, 16, 17, 18, 19, 20].forEach(function (idx) {{
                    const c = cells[idx];
                    if (c && !c.getAttribute('data-orig')) {{
                        c.setAttribute('data-orig', c.textContent || '');
                    }}
                }});
            }};

            const STATS_MAP = [
                {{ idx: 15, field: 'apps' }},
                {{ idx: 16, field: 'minutes' }},
                {{ idx: 17, field: 'goals' }},
                {{ idx: 18, field: 'assists' }},
                {{ idx: 19, field: 'yellow' }},
                {{ idx: 20, field: 'red' }},
            ];

            // Track per-row minutes so we can sort rows by Min desc afterwards.
            const rowMinutes = [];

            rows.forEach(function (row) {{
                captureRow(row);
                const cells = row.querySelectorAll('td');
                const domName = cells[2] ? cells[2].textContent : '';
                const apiName = _swapNameDomToApi(domName);
                const perTab = (playersByName[apiName] || {{}})[tournamentKey];

                if (isTotal || !perTab) {{
                    if (isTotal) {{
                        // Total tab — restore the aggregated values that
                        // were on screen when the page first rendered.
                        STATS_MAP.forEach(function (m) {{
                            const c = cells[m.idx];
                            if (!c) return;
                            c.textContent = c.getAttribute('data-orig') || '';
                            c.style.color = '';
                        }});
                    }} else {{
                        // Non-Total tab + no per-tournament row for this
                        // player. They never appeared in this tournament,
                        // so the honest answer is "–", not the Total
                        // numbers — some teams (e.g. IDmErJCR / Besiktas
                        // Aug 2026) ship Total stats that are identical to
                        // their Europa League group, which makes the row
                        // look like the player played both competitions
                        // when they only played one. Showing "–" fixes
                        // that mismatch without hiding Total elsewhere.
                        STATS_MAP.forEach(function (m) {{
                            const c = cells[m.idx];
                            if (!c) return;
                            c.textContent = '–';
                            c.style.color = '';
                        }});
                    }}
                    rowMinutes.push({{ row: row, minutes: parseInt(((cells[16] && cells[16].textContent) || '0').replace(/[^\d]/g, ''), 10) || 0 }});
                    return;
                }}
                STATS_MAP.forEach(function (m) {{
                    const c = cells[m.idx];
                    if (!c) return;
                    const v = perTab[m.field];
                    if (v === undefined || v === null || v === '') {{
                        c.textContent = '–';
                    }} else {{
                        c.textContent = String(v);
                    }}
                    // Same color as Total cells — no blue tint.
                    c.style.color = '';
                }});
                rowMinutes.push({{ row: row, minutes: parseInt(String(perTab.minutes || '0').replace(/[^\d]/g, ''), 10) || 0 }});
            }});

            if (isTotal) {{
                // Restore original DOM order so the user gets back to what
                // they had before touching the dropdown. We re-find rows by
                // their data-player-name marker (the order captured above)
                // so this works even if the previous non-Total switch has
                // already shuffled the rows.
                const initialOrder = (tbody.getAttribute('data-initial-order') || '').split('\u0001');
                if (initialOrder.length > 0) {{
                    const rowByName = {{}};
                    rows.forEach(function (r) {{
                        const n = r.getAttribute('data-player-name') || '';
                        rowByName[n] = r;
                    }});
                    initialOrder.forEach(function (name) {{
                        const r = rowByName[name];
                        if (r) tbody.appendChild(r);
                    }});
                }}
            }} else if (rowMinutes.length > 0) {{
                // Non-Total — sort by Min desc so the most-used players
                // float to the top.
                rowMinutes.sort(function (a, b) {{ return b.minutes - a.minutes; }});
                rowMinutes.forEach(function (item) {{ tbody.appendChild(item.row); }});
            }}
        }}


        async function saveTeamState() {{
            const btn = document.getElementById('save-btn');
            const msg = document.getElementById('save-message');
            const savedAt = new Date();
            const payload = collectTeamState();
            payload.name = snapshotName(savedAt);
            btn.disabled = true; msg.style.color = '#667eea'; msg.textContent = 'Saving snapshot...';
            try {{
                const res = await fetch('/lineup_ai/snapshots/' + encodeURIComponent(TEAM_ID), {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(payload)}});
                const json = await res.json();
                if (!res.ok || !json.ok) throw new Error(json.error || 'save failed');
                msg.style.color = '#17843f'; msg.textContent = '✅ Snapshot saved';
                await loadSnapshotsList();
            }} catch (e) {{
                msg.style.color = '#dc3545'; msg.textContent = '❌ ' + e.message;
            }} finally {{ btn.disabled = false; }}
        }}

        async function loadSavedState() {{
            await loadSnapshotsList();
        }}

        function bulkNormalizeText(s) {{
            return String(s || '')
                .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
                .toLowerCase()
                .replace(/[’'`]/g, '')
                .replace(/[^a-z0-9\s-]/g, ' ')
                .replace(/\s+/g, ' ')
                .trim();
        }}

        function bulkNameParts(s) {{
            const n = bulkNormalizeText(s);
            if (!n) return [];
            const parts = n.split(/[\s-]+/).filter(Boolean);
            return Array.from(new Set(parts));
        }}

        function bulkParseInput(text) {{
            return String(text || '')
                .split(/[,;/\\n\\r]+|\s+-\s+/g)
                .map(x => x.trim())
                .filter(Boolean);
        }}

        function bulkParseToken(token) {{
            // Jul 31 2026: strip bracket markers like (G), (C), (GK), (VC), (FW).
            const rawT = String(token || "");
            const cleaned = rawT
                .replace(/\s*\([A-Za-z]{{1,3}}\)\s*/g, " ")
                .replace(/\s+/g, " ")
                .trim();
            const nums = String(cleaned || "").match(/\b\d+\b/g) || [];
            const number = nums.length ? nums[nums.length - 1] : "";
            const name = String(cleaned || "").replace(/\b\d+\b/g, " ").replace(/\s+/g, " ").trim();
            const norm = bulkNormalizeText(name || cleaned || token);
            return {{ raw: token, number: number, name: name, norm: norm, parts: bulkNameParts(name || cleaned || token) }};
        }}

        function bulkRowsIndex() {{
            return Array.from(document.querySelectorAll('.main-table tbody tr[data-player-name]')).map(row => {{
                const rawAttrName = row.getAttribute('data-player-name') || '';
                const stripBrackets = function(s) {{ return String(s || '').replace(/\s*\([A-Za-z]{{1,3}}\)\s*/g, ' ').replace(/\s+/g, ' ').trim(); }};
                const rawName = stripBrackets(rawAttrName);
                const cells = row.querySelectorAll('td');
                const displayName = cells[2] ?stripBrackets(cells[2].textContent.replace(/[🎯🎨⭐👑⚽👟️]/g, ' ').replace(/\s+/g, ' ').trim()): rawName;
                const number = String(row.getAttribute('data-player-number') || (cells[0] ? cells[0].textContent : '') || '').trim();
                const norm = bulkNormalizeText(rawName + ' ' + displayName);
                const parts = bulkNameParts(rawName + ' ' + displayName);
                const rawParts = bulkNameParts(rawName);
                const firstName = rawParts[0] || '';
                const lastName = rawParts.length ? rawParts[rawParts.length - 1] : '';
                const fullName = bulkNormalizeText(rawName);
                const fullNameReversed = rawParts.length > 1 ? rawParts.slice().reverse().join(' ') : fullName;
                // Jul 31 2026: present 'FirstName LastName' in the ambiguous
                // dropdown. API gives 'LastName FirstName' for 2-part names;
                // swap them. For 3+ parts (compound last names like
                // 'Sykes-Kenworthy George'), keep order. Then titlecase
                // each part for consistent display.
                // title-case helper: 'mCnAlLy' -> 'Mcnally', 'alfie' -> 'Alfie'
                const titleCasePart = function(w) {{
                    if (!w) return w;
                    return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
                }};
                const firstLastBase = rawParts.length === 2
                    ? rawParts.slice().reverse()
                    : rawParts.slice();
                const firstLastName = firstLastBase.map(titleCasePart).join(' ');
                return {{ row: row, rawName: rawAttrName, displayName: displayName.trim(), number: number, norm: norm, parts: parts, firstName: firstName, lastName: lastName, fullName: fullName, fullNameReversed: fullNameReversed, firstLastName: firstLastName }};
            }});
        }}

        function bulkUnique(rows) {{
            const seen = new Set();
            return rows.filter(r => {{ if (seen.has(r.row)) return false; seen.add(r.row); return true; }});
        }}

        function bulkFindMatches(parsed, rows) {{
            const hasName = !!parsed.norm;
            const hasNum = !!parsed.number;

            // 1) Фамилия + номер
            if (hasName && hasNum) {{
                let exact = rows.filter(r => r.number === parsed.number && (r.lastName === parsed.norm || parsed.parts.some(p => r.lastName === p)));
                exact = bulkUnique(exact);
                if (exact.length) return exact;
            }}

            // 2) Имя + Фамилия (точное совпадение)
            if (hasName) {{
                const exactFull = rows.filter(r => r.fullName === parsed.norm);
                if (exactFull.length) return bulkUnique(exactFull);
            }}

            // 3) Фамилия + Имя (обратный порядок)
            if (hasName) {{
                const exactRev = rows.filter(r => r.fullNameReversed === parsed.norm);
                if (exactRev.length) return bulkUnique(exactRev);
            }}

            // 4) Номер
            if (hasNum) {{
                const numOnly = rows.filter(r => r.number === parsed.number);
                if (numOnly.length) return bulkUnique(numOnly);
            }}

            // 5) Частичное совпадение
            if (hasName) {{
                const partial = rows.filter(r =>
                    r.norm.includes(parsed.norm) ||
                    parsed.parts.every(p => r.parts.includes(p)) ||
                    r.parts.includes(parsed.norm) ||
                    parsed.parts.some(p => r.parts.includes(p))
                );
                if (partial.length) return bulkUnique(partial);
            }}

            return [];
        }}

        function bulkSetCheckbox(cb, checked, color, borderColor) {{
            if (!cb) return;
            cb.checked = !!checked;
            cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}

        function bulkMarkRow(row, mode) {{
            if (!row) return;
            if (mode === 'possible') {{
                bulkSetCheckbox(row.querySelector('.xi-checkbox'), true, '#667eea', '#667eea');
            }} else if (mode === 'start') {{
                bulkSetCheckbox(row.querySelector('.starting-checkbox'), true, '#dc3545', '#dc3545');
            }} else if (mode === 'squad') {{
                const cb = row.querySelector('.squad-checkbox');
                if (cb) {{ cb.checked = true; cb.style.background = '#000'; cb.style.border = 'none'; }}
            }}
        }}

        function bulkRefreshStats() {{
            updateXICounter(null);
            updateStartingCounter(null);
            recalcPossibleXIStats();
            recalcSelectedStartingStats();
            recalcValueComparison();
        }}

        function bulkRenderEditable(tokens, notFound, ambiguous) {{
            const el = document.getElementById('bulk-lineup-text');
            if (!el) return;
            const esc = (s) => String(s).replace(/</g, '&lt;').replace(/>/g, '&gt;');
            const nfSet = new Set(notFound.map(nf => nf.raw));
            const ambSet = new Set(ambiguous.map(a => a.parsed.raw));
            // Jul 31 2026: sort NOT FOUND tokens to the top so the
            // user sees problem names first. Stable order preserved
            // within each group using the original tokens array index.
            const idxOf = new Map(tokens.map((t, i) => [t, i]));
            const sorted = tokens
                .map((t, i) => ({{ t: t, i: i, kind: nfSet.has(t) ? 0 : (ambSet.has(t) ? 1 : 2) }}))
                .sort((a, b) => a.kind - b.kind || a.i - b.i)
                .map(x => x.t);
            const html = sorted.map(t => {{
                if (nfSet.has(t)) return '<div style="color:#dc3545;font-weight:700;">' + esc(t) + ' — NOT FOUND</div>';
                if (ambSet.has(t)) return '<div style="color:#f59e0b;font-weight:700;">' + esc(t) + ' — AMBIGUOUS</div>';
                return '<div>' + esc(t) + '</div>';
            }}).join('');
            el.innerHTML = html;

                // Restore the pxi NOT FOUND list wiped by squad fetch
                try {{
                    if (_pxiNotFoundList && _pxiNotFoundList.length) {{
                var esc2 = (s) => String(s).replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    var nfHtml = _pxiNotFoundList.map(function(p) {{ return '<div data-pxi-nf="1" style="color:#dc3545;font-weight:700;">' + esc2(p.ff_name) + ' — NOT FOUND</div>'; }}).join('');
                        el.innerHTML = nfHtml + el.innerHTML;
                    }}
                }} catch (e) {{}}
        }}

        function bulkRenderReport(total, found, notFound, ambiguous) {{
            const el = document.getElementById('bulk-lineup-report');
            if (!el) return;
            let html = '';
            if (ambiguous && ambiguous.length) html += '<div>Ambiguous: ' + ambiguous.length + ' — choose below</div>';
            el.innerHTML = html;
        }}

        let bulkAmbiguousItems = [];
        function bulkRenderAmbiguous(items, mode) {{
            const box = document.getElementById('bulk-lineup-ambiguous');
            if (!box) return;
            bulkAmbiguousItems = items || [];
            if (!items || !items.length) {{ box.style.display = 'none'; box.innerHTML = ''; return; }}
            box.style.display = 'block';
            box.innerHTML = '<b>Multiple matches — choose manually:</b>' + items.map((item, idx) =>
                '<div class="bulk-ambiguous-row"><label>' + ((item.parsed.raw || '').toString().replace(/\s*\([A-Za-z]{{1,3}}\)\s*/g, ' ').replace(/\s+/g, ' ').trim()) + '</label><select data-bulk-amb-idx="' + idx + '">' +
                '<option value="">Skip</option>' + item.matches.map((m, mi) => '<option value="' + mi + '">#' + (m.number || '–') + ' ' + ((m.firstLastName || m.rawName || '').toString().replace(/\s*\([A-Za-z]{{1,3}}\)\s*/g, ' ').replace(/\s+/g, ' ').trim()) + '</option>').join('') +
                '</select></div>'
            ).join('') + '<button type="button" onclick="applyBulkAmbiguousChoices()">Apply choices</button>';
        }}

        function applyBulkAmbiguousChoices() {{
            const mode = document.getElementById('bulk-lineup-mode') ? document.getElementById('bulk-lineup-mode').value : 'possible';
            let applied = 0;
            document.querySelectorAll('[data-bulk-amb-idx]').forEach(sel => {{
                const idx = parseInt(sel.getAttribute('data-bulk-amb-idx'), 10);
                const mi = sel.value === '' ? -1 : parseInt(sel.value, 10);
                const item = bulkAmbiguousItems[idx];
                if (item && mi >= 0 && item.matches[mi]) {{ bulkMarkRow(item.matches[mi].row, mode); applied++; }}
            }});
            bulkRefreshStats();
            const box = document.getElementById('bulk-lineup-ambiguous');
            if (box) {{ box.style.display = 'none'; box.innerHTML = ''; }}
            const rep = document.getElementById('bulk-lineup-report');
            if (rep) rep.innerHTML += '\\n<span class="found">Manual choices applied: ' + applied + '</span>';
        }}

        function applyBulkLineupFromTokens(tokens, mode) {{
            const rows = bulkRowsIndex();
            let found = 0;
            const notFound = [];
            const ambiguous = [];
            tokens.forEach(token => {{
                const parsed = bulkParseToken(token);
                const matches = bulkFindMatches(parsed, rows);
                // Jul 31 2026: bracket markers in raw input (G/C/GK/VC/FW/DF/MF/CA/CB/SB)
                // signal a position/captain label, not a disambiguation hint.
                // If matching returns multiple candidates anyway, auto-pick
                // the first one instead of forcing a manual dropdown.
                const hasBracketMarker = /\((G|C|GK|VC|FW|DF|MF|CA|CB|SB)\)/.test(parsed.raw || '');
                // Jul 31 2026: drop 1-2 letter tokens silently.
                // These are CSV artifacts or initials — never real
                // player names. They shouldn't appear in any of the
                // result lists.
                const cleanedName = String(parsed.name || '').trim();
                if (cleanedName.length < 3) {{ return; }}
                if (matches.length === 1) {{
                    bulkMarkRow(matches[0].row, mode);
                    found++;
                }} else if (matches.length > 1 && hasBracketMarker) {{
                    bulkMarkRow(matches[0].row, mode);
                    found++;
                }} else if (matches.length > 1) {{
                    ambiguous.push({{ parsed: parsed, matches: matches }});
                }} else {{
                    notFound.push(parsed);
                }}
            }});
            bulkRefreshStats();
            // Jul 31 2026: if XI is already full (11 marked), suppress
            // the ambiguous dropdown. The user is not trying to add more
            // players; they're just labeling context. Forcing a manual
            // selection is noise.
            const xiSelected = document.querySelectorAll('.xi-checkbox:checked').length;
            const effectiveAmbiguous = (xiSelected === 11) ? [] : ambiguous;
            bulkRenderReport(tokens.length, found, notFound, effectiveAmbiguous);
            bulkRenderAmbiguous(effectiveAmbiguous, mode);
            bulkRenderEditable(tokens, notFound, effectiveAmbiguous);
            return {{ total: tokens.length, found: found, notFound: notFound.length, ambiguous: ambiguous.length }};
        }}

        function applyBulkLineup() {{
            const textEl = document.getElementById('bulk-lineup-text');
            const modeEl = document.getElementById('bulk-lineup-mode');
            const tokens = bulkParseInput(textEl ? textEl.innerText : '');
            const mode = modeEl ? modeEl.value : 'possible';
            applyBulkLineupFromTokens(tokens, mode);
        }}

        function clearBulkLineup() {{
            const textEl = document.getElementById('bulk-lineup-text');
            if (textEl) textEl.innerHTML = '';
            const rep = document.getElementById('bulk-lineup-report');
            if (rep) rep.innerHTML = '';
            const amb = document.getElementById('bulk-lineup-ambiguous');
            if (amb) {{ amb.style.display = 'none'; amb.innerHTML = ''; }}
            // Reset Vision counters
            const vt = document.getElementById('vision-total-count');
            const vf = document.getElementById('vision-found-count');
            const vn = document.getElementById('vision-notfound-count');
            const vstats = document.getElementById('vision-lineup-stats');
            if (vt) vt.textContent = '0';
            if (vf) vf.textContent = '0';
            if (vn) vn.textContent = '0';
            if (vstats) vstats.style.display = 'none';
            // Reset Vision file status
            const vstatus = document.getElementById('vision-lineup-status');
            const vfile = document.getElementById('vision-file-name');
            if (vstatus) vstatus.textContent = '';
            if (vfile) vfile.textContent = '💤';
            const vinput = document.getElementById('vision-lineup-image');
            if (vinput) vinput.value = '';
            // Reset global ambiguous list and stats
            bulkAmbiguousItems = [];
            bulkRefreshStats();
            // Tell iframe parent the panel size changed (Match mode)
            if (window.parent && window.parent !== window) {{
                try {{ window.parent.postMessage({{ type: 'formalert-resize-iframe' }}, '*'); }} catch (e) {{ }}
            }}
        }}

        document.addEventListener('DOMContentLoaded', function() {{
            const fileEl = document.getElementById('vision-lineup-image');
            const fileNameEl = document.getElementById('vision-file-name');
            if (fileEl && fileNameEl) {{
                fileEl.addEventListener('change', function() {{
                    // Show 🆗 when an image is uploaded, 💤 when none selected
                    fileNameEl.textContent = (fileEl.files && fileEl.files[0]) ? '🆗' : '💤';
                }});
            }}
            // Jul 31 2026: notify parent window when bulk-lineup-text grows/shrinks
            // so the iframe auto-resizes to match content. Without this, Match mode
            // shows the team table clipped after typing/pasting in the textarea.
            const bulkText = document.getElementById('bulk-lineup-text');
            if (bulkText && window.parent && window.parent !== window) {{
                let resizeTimer = null;
                const notifyParentResize = function() {{
                    if (resizeTimer) clearTimeout(resizeTimer);
                    resizeTimer = setTimeout(function() {{
                        try {{
                            window.parent.postMessage(
                                {{ type: 'formalert-resize-iframe' }},
                                '*'
                            );
                        }} catch (e) {{ /* parent unreachable */ }}
                    }}, 80);
                }};
                bulkText.addEventListener('input', notifyParentResize);
                // Also notify after programmatic renders (bulkRenderEditable sets
                // innerHTML, which doesn't fire 'input').
                const observer = new MutationObserver(notifyParentResize);
                observer.observe(bulkText, {{ childList: true, subtree: true, characterData: true }});
            }}
            // Team mode: wrap bulk-lineup-panel-host + comparison-table-host in a
            // shared flex-row (bl-compare-row) at page load, so toggling them via
            // header buttons doesn't cause layout shift. Mirrors Match mode layout.
            const bulkHost = document.getElementById('bulk-lineup-panel-host');
            const compareHost = document.getElementById('comparison-table-host');
            const pageMain = document.querySelector('.page-main');
            if (pageMain && bulkHost && compareHost && !document.getElementById('bl-compare-row')) {{
                const row = document.createElement('div');
                row.id = 'bl-compare-row';
                row.style.cssText = 'display:flex;gap:9px;align-items:flex-start;margin-bottom:12px;width:980px;max-width:100%;box-sizing:border-box;';
                pageMain.insertBefore(row, bulkHost);
                row.appendChild(bulkHost);
                // Move comparison-table-host into the same row, regardless of
                // which sidebar/aside it currently lives in (e.g. column-wrapper).
                row.appendChild(compareHost);
            }}
        }});

        // Aug 7 2026: Paste image from clipboard. Two paths:
        // (a) navigator.clipboard.read() — modern browsers, requires permission
        // (b) document.addEventListener('paste') — fires when user presses Ctrl+V with
        //     a clipboard image anywhere on the page
        async function pasteImageFromClipboard() {{
            const statusEl = document.getElementById('vision-lineup-status');
            if (statusEl) {{ statusEl.style.color = '#667eea'; statusEl.textContent = 'Reading clipboard...'; }}
            if (!navigator.clipboard || !navigator.clipboard.read) {{
                if (statusEl) {{ statusEl.style.color = '#dc3545'; statusEl.textContent = 'Clipboard API not supported — use Ctrl+V'; }}
                return;
            }}
            try {{
                const items = await navigator.clipboard.read();
                for (const item of items) {{
                    for (const type of item.types) {{
                        if (type && type.startsWith('image/')) {{
                            const blob = await item.getType(type);
                            const file = new File([blob], 'clipboard.' + (type.split('/')[1] || 'png'), {{ type: type }});
                            loadImageFile(file);
                            return;
                        }}
                    }}
                }}
                if (statusEl) {{ statusEl.style.color = '#dc3545'; statusEl.textContent = 'No image in clipboard'; }}
            }} catch (e) {{
                if (statusEl) {{ statusEl.style.color = '#dc3545'; statusEl.textContent = 'Paste failed: ' + (e.message || 'permission denied'); }}
            }}
        }}

        // Aug 7 2026: load a File/Blob into the file input, update UI, then run Vision.
        async function loadImageFile(file) {{
            if (!file) return;
            const fileEl = document.getElementById('vision-lineup-image');
            const fileNameEl = document.getElementById('vision-file-name');
            // Sync file input so subsequent Upload clicks show the same name.
            try {{
                if (fileEl && typeof DataTransfer !== 'undefined') {{
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    fileEl.files = dt.files;
                }}
            }} catch (e) {{ /* DataTransfer unavailable */ }}
            if (fileNameEl) fileNameEl.textContent = '🆗';
            await applyVisionLineup();
        }}

        // Global paste handler — if the user presses Ctrl+V while focused
        // anywhere on the bulk-lineup-panel, an image in the clipboard is
        // auto-loaded into the vision pipeline.
        document.addEventListener('paste', async function(e) {{
            // Only act when the bulk panel is visible.
            const panel = document.getElementById('bulk-lineup-panel-host');
            if (!panel || panel.style.display === 'none') return;
            const items = (e.clipboardData && e.clipboardData.items) || [];
            for (const item of items) {{
                if (item.type && item.type.startsWith('image/')) {{
                    e.preventDefault();
                    const file = item.getAsFile();
                    if (file) await loadImageFile(file);
                    return;
                }}
            }}
        }}, true);

        async function applyVisionLineup() {{
            const fileEl = document.getElementById('vision-lineup-image');
            const textEl = document.getElementById('bulk-lineup-text');
            const modeEl = document.getElementById('bulk-lineup-mode');
            const statusEl = document.getElementById('vision-lineup-status');
            const file = fileEl && fileEl.files && fileEl.files[0];
            if (!file) {{ if (statusEl) {{ statusEl.style.color = '#dc3545'; statusEl.textContent = 'Upload'; }} return; }}
            if (statusEl) {{ statusEl.style.color = '#667eea'; statusEl.textContent = 'Vision reading...'; }}
            try {{
                const imageDataUrl = await new Promise((resolve, reject) => {{
                    const reader = new FileReader();
                    reader.onload = () => resolve(reader.result);
                    reader.onerror = () => reject(new Error('image read failed'));
                    reader.readAsDataURL(file);
                }});
                const currentMode = modeEl ? (modeEl.value || 'possible') : 'possible';
                const res = await fetch('/lineup_ai/vision_lineup/' + encodeURIComponent(TEAM_ID), {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ image: imageDataUrl, mode: currentMode }})
                }});
                const ct = res.headers.get('content-type') || '';
                if (!res.ok || !ct.includes('application/json')) throw new Error('Server returned HTML (' + res.status + '). Image may be too large or Vision API timed out.');
                const json = await res.json();
                if (!json.ok) throw new Error(json.error || 'vision failed');
                const names = Array.isArray(json.players) ? json.players : [];
                // 1. Set plain-text into the div (escape to avoid HTML injection).
                if (textEl) {{
                    const esc = (s) => String(s).replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    textEl.innerHTML = names.map(n => '<div>' + esc(n) + '</div>').join('');
                }}
                // 2. Apply lineup: marks rows + bulkRenderEditable writes
                //    red "NOT FOUND" / orange "AMBIGUOUS" highlights over the div.
                const currentMode2 = modeEl ? modeEl.value : 'possible';
                const result = applyBulkLineupFromTokens(names, currentMode2);
                // 3. Defensive re-render: ensure the div ends up with the
                //    highlighted version, not the plain-text version
                //    (browsers can mutate contenteditable innerHTML via
                //    input events when text is set programmatically).
                if (textEl && typeof bulkRenderEditable === 'function') {{
                    // Re-derive notFound/ambiguous from rows + names for the re-render
                    const rows = bulkRowsIndex();
                    const notFound = [];
                    const ambiguous = [];
                    names.forEach(token => {{
                        const parsed = bulkParseToken(token);
                        const cleanedNameV = String(parsed.name || '').trim();
                        if (cleanedNameV.length < 3) return;
                        const matches = bulkFindMatches(parsed, rows);
                        if (matches.length === 0) notFound.push(parsed);
                        else if (matches.length > 1) ambiguous.push({{ parsed: parsed, matches: matches }});
                    }});
                    bulkRenderEditable(names, notFound, ambiguous);
                }}
                if (statusEl) {{
                    statusEl.style.color = result.found ? '#17843f' : '#dc3545';
                    if (currentMode2 === 'squad') {{
                        statusEl.textContent = 'Vision: ' + names.length + ' names found in image, added to List';
                    }} else {{
                        statusEl.textContent = 'Vision: ' + names.length + ' names, marked ' + result.found;
                    }}
                }}
                // Show stats
                const statsEl = document.getElementById('vision-lineup-stats');
                const totalEl = document.getElementById('vision-total-count');
                const foundEl = document.getElementById('vision-found-count');
                const notfoundEl = document.getElementById('vision-notfound-count');
                if (statsEl) statsEl.style.display = 'block';
                if (totalEl) totalEl.textContent = names.length;
                if (foundEl) foundEl.textContent = result.found;
                if (notfoundEl) notfoundEl.textContent = Math.max(0, names.length - result.found);
            }} catch (e) {{
                if (statusEl) {{ statusEl.style.color = '#dc3545'; statusEl.textContent = 'Vision error: ' + e.message; }}
            }}
        }}

        function switchTab(tabName) {{
            const squadBar = document.getElementById('info-bar-squad');
            const missingBar = document.getElementById('info-bar-missing');
            const doubtfulBar = document.getElementById('info-bar-doubtful');
            const returningBar = document.getElementById('info-bar-returning');
            const transferInBar = document.getElementById('info-bar-transfer-in');
            const transferOutBar = document.getElementById('info-bar-transfer-out');
            const compTable = document.getElementById('comparison-table');
            const bulkPanel = document.querySelector('.bulk-lineup-panel');
            const coachStadiumBar = document.getElementById('coach-stadium-bar');

            // Hide all bars
            squadBar.style.display = 'none';
            missingBar.style.display = 'none';
            doubtfulBar.style.display = 'none';
            returningBar.style.display = 'none';
            transferInBar.style.display = 'none';
            transferOutBar.style.display = 'none';
            compTable.style.display = 'none';

            // Show relevant bar
            if (tabName === 'Squad') {{
                squadBar.style.display = 'flex';
                compTable.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'block';
                document.body.classList.remove('hide-watermark');
                if (coachStadiumBar) coachStadiumBar.style.display = 'flex';
            }} else if (tabName === 'Missing Players') {{
                missingBar.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'none';
                document.body.classList.add('hide-watermark');
                calcGroupStats('missing', MISSING_STATUSES);
                if (coachStadiumBar) coachStadiumBar.style.display = 'none';
            }} else if (tabName === 'Doubtful Players') {{
                doubtfulBar.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'none';
                document.body.classList.add('hide-watermark');
                calcGroupStats('doubtful', DOUBTFUL_STATUSES);
                if (coachStadiumBar) coachStadiumBar.style.display = 'none';
            }} else if (tabName === 'Returning Players') {{
                returningBar.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'none';
                document.body.classList.add('hide-watermark');
                calcGroupStats('returning', RETURNING_STATUSES);
                if (coachStadiumBar) coachStadiumBar.style.display = 'none';
            }} else if (tabName === 'Transfer In') {{
                transferInBar.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'none';
                document.body.classList.add('hide-watermark');
                calcGroupStats('transfer-in', TRANSFER_IN_STATUSES);
                if (coachStadiumBar) coachStadiumBar.style.display = 'none';
            }} else if (tabName === 'Transfer Out') {{
                transferOutBar.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'none';
                document.body.classList.add('hide-watermark');
                calcGroupStats('transfer-out', TRANSFER_OUT_STATUSES);
                if (coachStadiumBar) coachStadiumBar.style.display = 'none';
            }}

            // Filter table rows
            const rows = document.querySelectorAll('.main-table tbody tr[data-last]');
            rows.forEach(row => {{
                const select = row.querySelector('.status-select');
                const status = select ? select.value : 'Available';
                let show = false;
                if (tabName === 'Squad') {{
                    show = true;
                }} else if (tabName === 'Missing Players') {{
                    show = MISSING_STATUSES.includes(status);
                }} else if (tabName === 'Doubtful Players') {{
                    show = DOUBTFUL_STATUSES.includes(status);
                }} else if (tabName === 'Returning Players') {{
                    show = RETURNING_STATUSES.includes(status);
                }} else if (tabName === 'Transfer In') {{
                    show = TRANSFER_IN_STATUSES.includes(status);
                }} else if (tabName === 'Transfer Out') {{
                    show = TRANSFER_OUT_STATUSES.includes(status);
                }}
                row.style.display = show ? '' : 'none';
            }});
        }}

        function onSquadModeChange(tabName) {{
            switchTab(tabName);
        }}

        function calcGroupStats(prefix, statuses) {{
            // Cell indices: MV=5, Impact=8, G=17, A=18
            let count = 0, totalMV = 0, totalImpact = 0, totalGoals = 0, totalAssists = 0;
            const rows = document.querySelectorAll('.main-table tbody tr[data-last]');
            rows.forEach(row => {{
                const select = row.querySelector('.status-select');
                const status = select ? select.value : '';
                if (!statuses.includes(status)) return;
                count++;
                const cells = row.querySelectorAll('td');
                // MV cell[5]: text like "€5.7m", "€500k" or "–"
                const mvText = cells[5] ? cells[5].textContent.trim() : '';
                let mvVal = 0;
                if (mvText.includes('m')) {{
                    const m = mvText.match(/([\d.]+)/);
                    if (m) mvVal = parseFloat(m[1]);
                }} else if (mvText.includes('k')) {{
                    const k = mvText.match(/([\d.]+)/);
                    if (k) mvVal = parseFloat(k[1]) / 1000;
                }} else if (mvText !== '–' && mvText !== '-') {{
                    const n = mvText.match(/([\d.]+)/);
                    if (n) mvVal = parseFloat(n[1]);
                }}
                totalMV += mvVal;
                // Impact cell[8]
                const impactText = cells[8] ? cells[8].textContent.trim() : '';
                const impMatch = impactText.match(/([\\d.]+)/);
                if (impMatch) totalImpact += parseFloat(impMatch[1]);
                // Goals cell[17]
                const gText = cells[17] ? cells[17].textContent.trim() : '0';
                totalGoals += parseInt(gText) || 0;
                // Assists cell[18]
                const aText = cells[18] ? cells[18].textContent.trim() : '0';
                totalAssists += parseInt(aText) || 0;
            }});
            document.getElementById(prefix + '-count').textContent = count;
            document.getElementById(prefix + '-value').textContent = totalMV >= 1000 ? '\\u20ac' + (totalMV / 1000).toFixed(2) + 'bn' : '\\u20ac' + totalMV.toFixed(1) + 'm';
            document.getElementById(prefix + '-impact').textContent = totalImpact.toFixed(2);
            document.getElementById(prefix + '-goals').textContent = totalGoals;
            document.getElementById(prefix + '-assists').textContent = totalAssists;
            // Calculate and display percentages
            const goalsPct = TOTAL_GOALS > 0 ? Math.round((totalGoals / TOTAL_GOALS) * 100) : 0;
            const assistsPct = TOTAL_ASSISTS > 0 ? Math.round((totalAssists / TOTAL_ASSISTS) * 100) : 0;
            document.getElementById(prefix + '-goals-pct').textContent = goalsPct;
            document.getElementById(prefix + '-assists-pct').textContent = assistsPct;
        }}

        document.querySelectorAll('.tab').forEach(tab => {{
            tab.addEventListener('click', () => {{
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                switchTab(tab.textContent.trim());
            }});
        }});
        
        // Possible XI counter - blue fill, max 11
        function updateXICounter(checkbox) {{
            const xiCheckboxes = document.querySelectorAll('.xi-checkbox');
            let selectedCount = 0;

            // Called without a concrete checkbox during initialization, snapshot restore,
            // and bulk lineup apply. Do NOT recurse here: just repaint all circles.
            if (!checkbox) {{
                xiCheckboxes.forEach(cb => {{
                    if (cb.checked) selectedCount++;
                    cb.style.background = cb.checked ? '#667eea' : '#e0e0e0';
                    cb.style.border = '2px solid #667eea';
                }});
                const counter = document.getElementById('xi-counter');
                if (counter) counter.textContent = selectedCount;
                return;
            }}
            
            
            xiCheckboxes.forEach(cb => {{
                if (cb.checked) {{
                    selectedCount++;
                }}
            }});
            
            if (checkbox.checked && selectedCount > 11) {{
                checkbox.checked = false;
                checkbox.style.background = '#e0e0e0';
                selectedCount--;
            }} else {{
                xiCheckboxes.forEach(cb => {{
                    if (cb.checked) {{
                        cb.style.background = '#667eea';
                        cb.style.border = '2px solid #667eea';
                    }} else {{
                        cb.style.background = '#e0e0e0';
                        cb.style.border = '2px solid #667eea';
                    }}
                }});
            }}
            
            const counter = document.getElementById('xi-counter');
            if (counter) {{
                counter.textContent = selectedCount;
            }}
        }}

        // Aug 22 2026 — when the compare-mode parent posts
        // {{type:'applyPredictedXI', match_id}} OR the user opens a
        // Match URL with ?autopxi=1, refresh the LV squad for this
        // team BEFORE matching if needed, then fetch the cached XI
        // and tick the matching .xi-checkbox rows.
        //
        // Aug 24 2026 — Max asked to stop wasting API calls on every
        // Open Match click. The T-18h auto-builder already populates
        // the predicted XI cache, and the squad cache for a team
        // rarely changes inside the 18 h window. So:
        //   1. Try a localStorage "pxi-applied" cache first. If a
        //      tick list is present AND the cache.fetched_at it
        //      remembers is still recent, tick the boxes SYNCHRONOUSLY
        //      (0 ms perceived delay) and skip the API entirely.
        //      Then optionally fire-and-forget a background refresh
        //      if the squad might be stale.
        //   2. Without a local cache, fetch /api/predicted_xi/<mid>
        //      WITHOUT refresh=1 (51 ms instead of 3-10 s) and tick
        //      the boxes from that. Still refresh the squad in the
        //      background if it's been more than 10 minutes since
        //      the last fetch (kept short enough that staleness
        //      doesn't bite inside the 18 h window).
        //   3. Skip the squad fetch entirely if we're more than 1 h
        //      before kickoff (squads are stable in that window).
        function _applyPredictedXIIframe(match_id) {{
            var _kickoff = (typeof window.PXI_KICKOFF_TS === 'number') ? window.PXI_KICKOFF_TS : 0;
            var _now = Math.floor(Date.now() / 1000);
            var _hoursUntilKickoff = _kickoff ? (_kickoff - _now) / 3600 : 999;

            // Helper: render unmatched PXI players in the bulk-lineup-text
            // textarea so the user sees exactly who could not be mapped to
            // the LV squad (e.g. transferred / injured players).
            function _renderPxiNotFound(players) {{
                var el = document.getElementById('bulk-lineup-text');
                if (!el) return;
                var esc = function(s) {{ return String(s).replace(/</g, '&lt;').replace(/>/g, '&gt;'); }};
                var nf = (players || []).filter(function(p) {{ return p && !p.matched && p.ff_name; }});
                if (!nf.length) {{
                    // Only clear if the textarea still contains our previous
                    // NOT FOUND markup; never wipe a user-typed manual list.
                    if (el.querySelector && el.querySelector('[data-pxi-nf="1"]')) el.innerHTML = '';
                    return;
                }}
                _pxiNotFoundList = nf;
                el.innerHTML = nf.map(function(p) {{
                    return '<div data-pxi-nf="1" style="color:#dc3545;font-weight:700;">' + esc(p.ff_name) + ' — NOT FOUND</div>';
                }}).join('');
                // Auto-open the bulk-lineup panel so the user sees the
                // unmatched names without clicking 👥 Add Lineups first.
                try {{
                    var host = document.getElementById('bulk-lineup-panel-host');
                    if (host && host.style.display === 'none') {{
                        host.style.display = 'block';
                    }}
                }} catch (e) {{}}
            }}

            // ---- Step 1: tick from localStorage immediately ----
            // TEAM_ID is the IIFE-scoped variable defined further
            // down in this same closure (see "var TEAM_ID = …" near
            // line 5334). Use it directly instead of window.TEAM_ID
            // because the parent page's `w.TEAM_ID` lookup wouldn't
            // see an IIFE-local var anyway.
            var _lsKey = 'pxi-applied:' + match_id + ':' + (TEAM_ID || '');
            var _lsAppliedTick = 0;
            var _lsCacheFetchedAt = 0;
            var _lsUsed = false;
            try {{
                var raw = localStorage.getItem(_lsKey);
                if (raw) {{
                    var obj = JSON.parse(raw);
                    // Aug 24 2026 — only trust the local cache if BOTH
                    // (a) the cached tick list is recent (< 6 h old)
                    // AND (b) the kickoff is still in the future. A
                    // past kickoff means the lineup is locked and the
                    // XI we cached is the final one — but a future
                    // kickoff more than 6 h after our cache was written
                    // means the auto-builder might have already rebuilt
                    // the cache and the squad might have shifted, so
                    // fall through to the network.
                    var _ageOk = (_now - (obj.cached_at || 0)) < 6 * 3600;
                    var _kickoffOk = !obj.kickoff_ts || (obj.kickoff_ts > _now - 6 * 3600);
                    if (_ageOk && _kickoffOk && obj.players && obj.players.length) {{
                        var cbs = document.querySelectorAll('input.xi-checkbox');
                        for (var i = 0; i < cbs.length; i++) {{
                            var cb = cbs[i];
                            var rowName = (cb.value || '').toLowerCase().trim();
                            if (obj.players.indexOf(rowName) !== -1 && !cb.checked) {{
                                cb.checked = true;
                                cb.dispatchEvent(new Event('change', {{bubbles:true}}));
                                _lsAppliedTick++;
                            }}
                        }}
                        _lsCacheFetchedAt = obj.cached_at || 0;
                        _lsUsed = true;
                        if (_lsAppliedTick) updateXICounter();
                    }}
                }}
            }} catch (e) {{ /* corrupt cache — ignore */ }}

            // ---- Step 2: fresh XI fetch (no refresh=1 — server
            // returns the cached payload directly, 50 ms) ----
            var _freshApplied = 0;
            var _refreshThenApply = function() {{
                fetch('/lineup_ai/api/predicted_xi/' + encodeURIComponent(match_id))
                    .then(function(r){{ return r.json(); }})
                    .then(function(d) {{
                        if (!d || !d.match_id) return;
                        var target = (d.home_players || []).concat(d.away_players || [])
                            .map(function(p){{ return (p.lv_name || '').toLowerCase().trim(); }})
                            .filter(function(n){{ return !!n; }});
                        if (!target.length) return;
                        var cbs = document.querySelectorAll('input.xi-checkbox');
                        for (var i = 0; i < cbs.length; i++) {{
                            var cb = cbs[i];
                            var rowName = (cb.value || '').toLowerCase().trim();
                            if (target.indexOf(rowName) !== -1 && !cb.checked) {{
                                cb.checked = true;
                                cb.dispatchEvent(new Event('change', {{bubbles:true}}));
                                _freshApplied++;
                            }}
                        }}
                        if (_freshApplied) updateXICounter();
                        // Aug 28 2026 — show unmatched players for THIS team's
                        // side in the bulk-lineup-text area, marked NOT FOUND.
                        var sideKey = (d.home_team_id === TEAM_ID) ? 'home_players' : 'away_players';
                        _renderPxiNotFound(d[sideKey]);
                        // Persist the tick list so the next Open Match
                        // click ticks without hitting the network.
                        // Aug 24 2026 — kickoff_ts is read from the
                        // server response so the next open knows when
                        // the lineup is locked.
                        try {{
                            localStorage.setItem(_lsKey, JSON.stringify({{
                                players: target,
                                cached_at: Math.floor(Date.now() / 1000),
                                kickoff_ts: d.kickoff_ts || 0,
                                source: 'fresh-fetch'
                            }}));
                        }} catch (e) {{ /* quota or disabled */ }}
                        try {{
                            if (window.parent && window.parent !== window) {{
                                window.parent.postMessage({{
                                    type: 'p11-autopxi',
                                    match_id: match_id,
                                    applied: _freshApplied,
                                    home_count: d.home_count,
                                    away_count: d.away_count,
                                    source: 'fresh'
                                }}, '*');
                            }}
                        }} catch(e) {{}}
                    }})
                    .catch(function(){{}});
            }};

            // ---- Step 3: refresh squad only if it's stale. ----
            // Squads move on injuries / transfers but stay flat inside
            // the T-18h window. The auto-builder already keeps the XI
            // cache fresh; the squad fetch (8-37 s) only matters when
            // (a) we have NO localStorage tick list yet OR
            // (b) our localStorage list is older than 10 min OR
            // (c) kickoff is within 1 h (lineups stabilize late).
            var _squadRefreshIntervalMs = 10 * 60 * 1000; // 10 min
            var _needsSquadRefresh = (
                !_lsUsed ||                       // first time, no local cache
                (_now * 1000 - _lsCacheFetchedAt * 1000) > _squadRefreshIntervalMs ||
                _hoursUntilKickoff < 1            // very close to kickoff
            );

            if (_needsSquadRefresh && typeof TEAM_ID === 'string' && TEAM_ID) {{
                fetch('/lineup_ai/api/fetch/' + encodeURIComponent(TEAM_ID) + '?_t=' + Date.now(), {{ cache: 'no-store' }})
                    .then(function(r){{ return r.ok ? r.json() : Promise.reject('http ' + r.status); }})
                    .then(function(){{ _refreshThenApply(); }})
                    .catch(function(){{ _refreshThenApply(); }});
            }} else {{
                // Aug 24 2026 — if we already ticked from localStorage
                // and the squad is fresh, skip the redundant /api/predicted_xi
                // fetch entirely. The XI was just verified a few seconds
                // ago when localStorage was written, so the user sees
                // the same tick list with zero network calls.
                if (_lsUsed && _lsAppliedTick > 0) {{
                    try {{
                        if (window.parent && window.parent !== window) {{
                            window.parent.postMessage({{
                                type: 'p11-autopxi',
                                match_id: match_id,
                                applied: _lsAppliedTick,
                                source: 'localstorage-cache'
                            }}, '*');
                        }}
                    }} catch(e) {{}}
                    return;
                }}
                _refreshThenApply();
            }}
        }}
        
        // Starting XI counter - red fill, max 11
        function updateStartingCounter(checkbox) {{
            const startingCheckboxes = document.querySelectorAll('.starting-checkbox');
            let selectedCount = 0;

            // Called without a concrete checkbox during initialization, snapshot restore,
            // and bulk lineup apply. Do NOT recurse here: just repaint all circles.
            if (!checkbox) {{
                startingCheckboxes.forEach(cb => {{
                    if (cb.checked) selectedCount++;
                    cb.style.background = cb.checked ? '#dc3545' : '#e0e0e0';
                    cb.style.border = '2px solid #dc3545';
                }});
                const counter = document.getElementById('starting-counter');
                if (counter) counter.textContent = selectedCount;

                const allRows = document.querySelectorAll('tbody tr[data-last]');
                allRows.forEach(row => row.classList.remove('missing-from-last'));
                if (selectedCount === 11) {{
                    allRows.forEach(row => {{
                        if (row.getAttribute('data-last') === 'START') {{
                            const cb = row.querySelector('.starting-checkbox');
                            if (cb && !cb.checked) row.classList.add('missing-from-last');
                        }}
                    }});
                }}
                return;
            }}
            
            
            startingCheckboxes.forEach(cb => {{
                if (cb.checked) {{
                    selectedCount++;
                }}
            }});
            
            if (checkbox.checked && selectedCount > 11) {{
                checkbox.checked = false;
                checkbox.style.background = '#e0e0e0';
                selectedCount--;
            }} else {{
                startingCheckboxes.forEach(cb => {{
                    if (cb.checked) {{
                        cb.style.background = '#dc3545';
                        cb.style.border = '2px solid #dc3545';
                    }} else {{
                        cb.style.background = '#e0e0e0';
                        cb.style.border = '2px solid #dc3545';
                    }}
                }});
            }}
            
            const counter = document.getElementById('starting-counter');
            if (counter) {{
                counter.textContent = selectedCount;
            }}
            
            // Highlight players who STARTED last match but NOT in current Starting XI
            const allRows = document.querySelectorAll('tbody tr[data-last]');
            allRows.forEach(row => {{
                row.classList.remove('missing-from-last');
            }});
            
            if (selectedCount === 11) {{
                allRows.forEach(row => {{
                    if (row.getAttribute('data-last') === 'START') {{
                        const cb = row.querySelector('.starting-checkbox');
                        if (cb && !cb.checked) {{
                            row.classList.add('missing-from-last');
                        }}
                    }}
                }});
            }}
        }}
        
        // Clear column function - uncheck all players in a column
        function clearColumn(colType) {{
            const checkboxClass = {{'squad': 'squad-checkbox', 'possible': 'xi-checkbox', 'start': 'starting-checkbox'}}[colType];
            if (!checkboxClass) return false;

            const checkboxes = document.querySelectorAll('input[type="checkbox"].' + checkboxClass);
            checkboxes.forEach(cb => {{
                if (cb.checked) {{
                    cb.checked = false;
                    // Reset style
                    cb.style.background = '#e0e0e0';
                    if (colType === 'squad') {{
                        cb.style.border = '2px solid #333';
                    }} else if (colType === 'possible') {{
                        cb.style.border = '2px solid #667eea';
                    }} else {{
                        cb.style.border = '2px solid #dc3545';
                    }}
                    cb.dispatchEvent(new Event('change'));
                }}
            }});
            return false;
        }}

        // Jul 23 2026 — Clear all player statuses back to "Available" (✅).
        // Triggered by the ✖️ button in the STATUS column header.
        // Mirrors the structure of clearColumn() above.
        function clearStatus() {{
            const selects = document.querySelectorAll('.status-select');
            let count = 0;
            selects.forEach(sel => {{
                if (sel.value !== 'Available') {{
                    sel.value = 'Available';
                    // Reuse the existing onchange handler to refresh emoji + styling.
                    if (typeof updateStatusIcon === 'function') {{
                        updateStatusIcon(sel);
                    }} else if (window.updateStatusIcon) {{
                        window.updateStatusIcon(sel);
                    }}
                    count++;
                }}
            }});
            console.log('[clearStatus] reset ' + count + ' player status(es) to Available');
            return false;
        }}

        // Add event listeners
        document.querySelectorAll('.xi-checkbox').forEach(checkbox => {{
            checkbox.addEventListener('change', function() {{
                updateXICounter(this);
            }});
        }});
        
        document.querySelectorAll('.starting-checkbox').forEach(checkbox => {{
            checkbox.addEventListener('change', function() {{
                updateStartingCounter(this);
            }});
        }});
        
        function fmtDelta(val, suffix) {{
            if (val === 0) return '0';
            const sign = val > 0 ? '▲ +' : '▼ ';
            const color = val > 0 ? '#17843f' : '#dc3545';
            return '<span style="color:' + color + ';font-weight:600;">' + sign + val.toFixed(2) + (suffix || '') + '</span>';
        }}
        function fmtPct(val) {{
            if (val === 0) return '0%';
            const sign = val > 0 ? '▲ +' : '▼ ';
            const color = val > 0 ? '#17843f' : '#dc3545';
            return '<span style="color:' + color + ';">' + sign + val.toFixed(1) + '%</span>';
        }}
        
        function recalcSelectedStartingStats() {{
            let impact = 0;
            let mv = 0;
            let ageSum = 0;
            let count = 0;

            document.querySelectorAll('tbody tr').forEach(row => {{
                const cb = row.querySelector('.starting-checkbox');
                if (!cb || !cb.checked) return;
                const cells = row.querySelectorAll('td');
                if (!cells || cells.length < 16) return;
                const age = parseFloat((cells[4].textContent || '').replace(/[^0-9.]/g, '')) || 0;
                const rawMarket = (cells[5].textContent || '').trim().toLowerCase().replace(/€/g, '');
                const impactScore = parseFloat((cells[8].textContent || '').replace(/[^0-9.]/g, '')) || 0;
                impact += impactScore;
                ageSum += age;
                count += 1;
                if (rawMarket.endsWith('m')) {{
                    mv += parseFloat(rawMarket) || 0;
                }} else if (rawMarket.endsWith('k')) {{
                    mv += (parseFloat(rawMarket) || 0) / 1000;
                }} else {{
                    mv += parseFloat(rawMarket) || 0;
                }}
            }});

            const impactEl = document.getElementById('starting-xi-impact-score-value');
            const mvEl = document.getElementById('mv-starting-xi-value');
            const ageEl = document.getElementById('av-age-starting-xi-value');
            if (impactEl) impactEl.textContent = impact.toFixed(2);
            if (mvEl) mvEl.textContent = mv >= 1000 ? (mv / 1000).toFixed(2) + 'bn' : mv.toFixed(1) + 'm';
            if (ageEl) ageEl.textContent = (count ? (ageSum / count) : 0).toFixed(1);
            
            // Update S-XI Comparison Table
            const lastImpact = {last_match_impact:.2f};
            const lastMv = {last_match_mv:.1f};
            const lastAge = {last_match_age:.1f};
            const sxiImpact = impact;
            const sxiMv = mv;
            const sxiAge = count ? (ageSum / count) : 0;
            
            const sxiImpactEl = document.getElementById('cmp-sxi-impact');
            if (sxiImpactEl) sxiImpactEl.textContent = sxiImpact.toFixed(2);
            const pctImpactEl = document.getElementById('cmp-sxi-pct-impact');
            if (pctImpactEl) {{
                const d = sxiImpact - lastImpact;
                pctImpactEl.innerHTML = lastImpact > 0 ? fmtPct(d / lastImpact * 100) : '–';
            }}
            
            const sxiMvEl = document.getElementById('cmp-sxi-mv');
            if (sxiMvEl) sxiMvEl.textContent = sxiMv >= 1000 ? (sxiMv / 1000).toFixed(2) + 'bn' : sxiMv.toFixed(1) + 'm';
            const pctMvEl = document.getElementById('cmp-pct-mv');
            if (pctMvEl) {{
                const d = sxiMv - lastMv;
                pctMvEl.innerHTML = lastMv > 0 ? fmtPct(d / lastMv * 100) : '–';
            }}
            
            const sxiAgeEl = document.getElementById('cmp-sxi-age');
            if (sxiAgeEl) sxiAgeEl.textContent = sxiAge.toFixed(1);
            const pctAgeEl = document.getElementById('cmp-pct-age');
            if (pctAgeEl) {{
                const d = sxiAge - lastAge;
                pctAgeEl.innerHTML = lastAge > 0 ? fmtPct(d / lastAge * 100) : '–';
            }}
        }}

        function recalcPossibleXIStats() {{
            let impact = 0, mv = 0, ageSum = 0, count = 0;
            document.querySelectorAll('tbody tr').forEach(row => {{
                const cb = row.querySelector('.xi-checkbox');
                if (!cb || !cb.checked) return;
                const cells = row.querySelectorAll('td');
                if (!cells || cells.length < 9) return;
                const age = parseFloat((cells[4].textContent || '').replace(/[^0-9.]/g, '')) || 0;
                const rawMarket = (cells[5].textContent || '').trim().toLowerCase().replace(/€/g, '');
                const impactScore = parseFloat((cells[8].textContent || '').replace(/[^0-9.]/g, '')) || 0;
                impact += impactScore;
                ageSum += age;
                count += 1;
                if (rawMarket.endsWith('m')) {{
                    mv += parseFloat(rawMarket) || 0;
                }} else if (rawMarket.endsWith('k')) {{
                    mv += (parseFloat(rawMarket) || 0) / 1000;
                }} else {{
                    mv += parseFloat(rawMarket) || 0;
                }}
            }});
            const lastImpact = {last_match_impact:.2f};
            const lastMv = {last_match_mv:.1f};
            const lastAge = {last_match_age:.1f};
            const pxiAge = count ? (ageSum / count) : 0;

            const el1 = document.getElementById('cmp-pxi-impact');
            if (el1) el1.textContent = impact.toFixed(2);
            const el2 = document.getElementById('cmp-pxi-pct-impact');
            if (el2) {{
                const d = impact - lastImpact;
                el2.innerHTML = lastImpact > 0 ? fmtPct(d / lastImpact * 100) : '–';
            }}
            const el3 = document.getElementById('cmp-pxi-mv');
            if (el3) el3.textContent = mv >= 1000 ? (mv / 1000).toFixed(2) + 'bn' : mv.toFixed(1) + 'm';
            const el4 = document.getElementById('cmp-pxi-pct-mv');
            if (el4) {{
                const d = mv - lastMv;
                el4.innerHTML = lastMv > 0 ? fmtPct(d / lastMv * 100) : '–';
            }}
            const el5 = document.getElementById('cmp-pxi-age');
            if (el5) el5.textContent = pxiAge.toFixed(1);
            const el6 = document.getElementById('cmp-pxi-pct-age');
            if (el6) {{
                const d = pxiAge - lastAge;
                el6.innerHTML = lastAge > 0 ? fmtPct(d / lastAge * 100) : '–';
            }}
        }}

        document.querySelectorAll('.xi-checkbox').forEach(checkbox => {{
            checkbox.addEventListener('change', function() {{
                updateXICounter(this);
                recalcPossibleXIStats();
                recalcValueComparison();
            }});
        }});

        document.querySelectorAll('.starting-checkbox').forEach(checkbox => {{
            checkbox.addEventListener('change', function() {{
                updateStartingCounter(this);
                recalcSelectedStartingStats();
                recalcValueComparison();
            }});
        }});

        loadSavedState();

        // Initialize counters
        updateXICounter(null);
        updateStartingCounter(null);
        recalcSelectedStartingStats();
        recalcPossibleXIStats();
        recalcValueComparison();

        function recalcValueComparison() {{
            // Recompute S-XI impact from selected checkboxes
            let sxiImpact = 0;
            document.querySelectorAll('tbody tr').forEach(row => {{
                const cb = row.querySelector('.starting-checkbox');
                if (!cb || !cb.checked) return;
                const cells = row.querySelectorAll('td');
                if (!cells || cells.length < 16) return;
                sxiImpact += parseFloat((cells[8].textContent || '').replace(/[^0-9.]/g, '')) || 0;
            }});
            // Recompute P-XI impact from selected checkboxes
            let pxiImpact = 0;
            document.querySelectorAll('tbody tr').forEach(row => {{
                const cb = row.querySelector('.xi-checkbox');
                if (!cb || !cb.checked) return;
                const cells = row.querySelectorAll('td');
                if (!cells || cells.length < 16) return;
                pxiImpact += parseFloat((cells[8].textContent || '').replace(/[^0-9.]/g, '')) || 0;
            }});

            // Impact Δ (%) — S-XI vs P-XI
            var el2 = document.getElementById('cmp-val-pct-impact');
            if (el2) {{
                if (pxiImpact > 0 && sxiImpact > 0) {{
                    var d = (sxiImpact - pxiImpact) / pxiImpact * 100;
                    el2.innerHTML = fmtPct(d);
                }} else el2.textContent = '–';
            }}
        }}

        function _replaceCheckboxesWithCircles(container) {{
            // Replace <input type="checkbox"> with <div> circles that html2canvas can render
            const checkboxes = container.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(cb => {{
                const div = document.createElement('div');
                div.style.cssText = 'width:20px;height:20px;border-radius:50%;display:inline-block;vertical-align:middle;';
                const cls = cb.className;
                if (cls.includes('squad-checkbox')) {{
                    div.style.background = cb.checked ? '#000' : '#e0e0e0';
                    if (!cb.checked) div.style.border = '2px solid #333';
                }} else if (cls.includes('xi-checkbox')) {{
                    div.style.background = cb.checked ? '#667eea' : '#e0e0e0';
                    if (!cb.checked) div.style.border = '2px solid #667eea';
                }} else if (cls.includes('starting-checkbox')) {{
                    div.style.background = cb.checked ? '#dc3545' : '#e0e0e0';
                    if (!cb.checked) div.style.border = '2px solid #dc3545';
                }} else {{
                    div.style.background = cb.checked ? '#000' : '#e0e0e0';
                    if (!cb.checked) div.style.border = '2px solid #333';
                }}
                // Add ✓ for checked state (white text)
                if (cb.checked) {{
                    div.style.display = 'inline-flex';
                    div.style.alignItems = 'center';
                    div.style.justifyContent = 'center';
                    div.innerHTML = '<span style="color:white;font-size:13px;line-height:1;">✓</span>';
                }}
                cb.parentNode.replaceChild(div, cb);
            }});
        }}

        async function exportScreenshot() {{
            const btn = document.getElementById('btn-export');
            btn.disabled = true;
            btn.style.opacity = '0.4';
            try {{
                // Clone the actual .page-main that the user sees — this preserves the
                // exact column widths, coach-stadium bar, and table layout as displayed.
                // The gradient title bar with team name is part of .main-table and is captured here.
                const pageMain = document.querySelector('.page-main');
                const h1 = document.querySelector('.main-table h1');
                const teamName = h1 ? h1.textContent.trim() : 'team';

                // Create off-screen capture div
                const capture = document.createElement('div');
                capture.style.cssText = 'position:absolute;left:-9999px;top:0;background:#f4f6f9;padding:16px;width:fit-content;';

                // Clone .page-main wholesale — includes bulk-lineup, info-bar, comparison-table,
                // and main-layout (gradient title + table + coach-stadium).
                if (pageMain) {{
                    const pmClone = pageMain.cloneNode(true);
                    // Force-show coach-stadium in the clone (if hidden by tab switch)
                    const csInClone = pmClone.querySelector('#coach-stadium-bar');
                    if (csInClone) csInClone.style.display = 'flex';
                    capture.appendChild(pmClone);
                }}

                // Replace checkboxes with circle divs in the clone
                _replaceCheckboxesWithCircles(capture);

                document.body.appendChild(capture);

                const canvas = await html2canvas(capture, {{
                    backgroundColor: '#f4f6f9',
                    scale: 2,
                    useCORS: true,
                    logging: false
                }});

                document.body.removeChild(capture);

                const link = document.createElement('a');
                link.download = teamName.replace(/\s+/g, '_') + '_squad.png';
                link.href = canvas.toDataURL('image/png');
                link.click();
            }} catch(e) {{
                console.error('Export failed:', e);
                alert('Export failed: ' + e.message);
            }} finally {{
                btn.disabled = false;
                btn.style.opacity = '1';
            }}
        }}

        // Returns a Promise<canvas> for use by parent (Match mode).
        // Mirrors Team mode exportScreenshot() — clones .page-main wholesale
        // (includes bulk-lineup panel, info-bar, comparison-table, builder,
        // gradient title bar, tabs, full table, coach-stadium) so the saved
        // PNG looks exactly like what the user sees in Team mode.
        async function getScreenshotCanvas() {{
            try {{
                const pageMain = document.querySelector('.page-main');
                if (!pageMain) return null;

                // Create off-screen capture div (same as Team mode)
                const capture = document.createElement('div');
                capture.style.cssText = 'position:absolute;left:-9999px;top:0;background:#f4f6f9;padding:16px;width:fit-content;';

                // Clone .page-main wholesale — preserves the exact column widths,
                // coach-stadium bar, and table layout as displayed in Team mode.
                const pmClone = pageMain.cloneNode(true);
                // Force-show coach-stadium in the clone (if hidden by tab switch)
                const csInClone = pmClone.querySelector('#coach-stadium-bar');
                if (csInClone) csInClone.style.display = 'flex';
                capture.appendChild(pmClone);

                _replaceCheckboxesWithCircles(capture);
                document.body.appendChild(capture);

                const canvas = await html2canvas(capture, {{
                    backgroundColor: '#f4f6f9',
                    scale: 2,
                    useCORS: true,
                    logging: false
                }});

                document.body.removeChild(capture);
                return canvas;
            }} catch(e) {{
                console.error('Capture failed:', e);
                return null;
            }}
        }}

        // === Auto-update DISABLED (Jul 22 2026) ===
        // User wants manual-only mode. The ♻️ Refresh button is the
        // single entry point for fetching fresh data from FlashScore.
        // No background sync, no reload loops, no auto-fetch on stale cache.
        // CACHE_AGE_SECONDS / CACHE_TTL_SECONDS are still computed for
        // the cache badge in the sidebar; they just no longer trigger
        // an automatic API call.

    // Export for iframe communication (Match mode)
    // Store reference to inner function before exporting to avoid recursion
    var _applySavedStateInner = restoreTeamState;
    window.getCurrentTeamData = function() {{ return collectTeamState(); }};
    window.applySavedState = function(data) {{ if (data && Array.isArray(data.players)) _applySavedStateInner(data); }};

</script>
<script>
        (function() {{
            const CURRENT_TEAM_ID = {team_id!r};
            let navData = null;
            let navFixtures = null;

            async function loadNavData() {{
                try {{
                    const response = await fetch('/lineup_ai/data.json');
                    navData = await response.json();
                    populateNavCountries();
                }} catch (error) {{
                    console.error('Error loading lineup data:', error);
                }}
            }}

            function populateNavCountries() {{
                const countrySelect = document.getElementById('nav-country');
                const countryList = document.getElementById('nav-country-list');
                const trigger = document.getElementById('nav-country-trigger');
                // Move the country list to <body> so it escapes any parent stacking context
                if (countryList && countryList.parentElement !== document.body) {{
                    document.body.appendChild(countryList);
                }}
                // Jul 26 2026: country favorites — favorites first, alphabetical after.
                // Each row has a ☆/★ button that toggles favorite (localStorage).
                const countries = window.countryFavorites
                    ? window.countryFavorites.sortCountries(Object.keys(navData))
                    : Object.keys(navData).sort();
                // Populate hidden native select (kept for compatibility with onNavCountryChange)
                countrySelect.innerHTML = '<option value=""></option>';
                // Populate custom dropdown list with flag images
                countryList.innerHTML = '';
                countries.forEach(country => {{
                    // Hidden select option (for compatibility)
                    const option = document.createElement('option');
                    option.value = country;
                    option.textContent = country;
                    countrySelect.appendChild(option);
                    // Visible list item: flag + name + star (all inline)
                    const li = document.createElement('li');
                    li.setAttribute('data-value', country);
                    li.setAttribute('role', 'option');
                    // No getFlagHtml in this template — show plain text only.
                    li.textContent = country + ' ';
                    if (window.countryFavorites) {{
                        li.appendChild(window.countryFavorites.buildStarButton(country));
                    }}
                    li.onclick = function(ev) {{
                        if (ev.target && ev.target.classList && ev.target.classList.contains('country-fav-star')) return;
                        selectCountry(country);
                    }};
                    countryList.appendChild(li);
                }});
                // Auto-select current country based on team_id.
                // Jul 25 2026: scan ALL championships under the country, not just the first.
                // Previously this only checked Object.keys(leagues)[0], which works when
                // the team is in the top-tier league (e.g. France > Ligue 1) but FAILS
                // for teams in a second/third championship (e.g. France > Ligue 2 — St
                // Etienne, Reims, etc. were never auto-selected because the firstChamp
                // was always "Ligue 1" which doesn't contain them).
                let foundCountry = null;
                for (const [country, leagues] of Object.entries(navData)) {{
                    if (!leagues || typeof leagues !== 'object') continue;
                    // Iterate championships in navData insertion order (top-tier first)
                    // and accept the FIRST match.
                    for (const champ of Object.keys(leagues)) {{
                        if (leagues[champ] && leagues[champ].some(t => t.id === CURRENT_TEAM_ID)) {{
                            foundCountry = country;
                            break;
                        }}
                    }}
                    if (foundCountry) break;
                }}
                if (foundCountry) {{
                    selectCountry(foundCountry);
                }}

                // Re-populate list when a favorite is added/removed so the
                // country that was just starred moves to the top in real time.
                document.addEventListener('countryFavoritesChanged', function() {{
                    var wasOpen = countryList.style.display === 'block';
                    populateNavCountries();
                    if (wasOpen) {{
                        countryList.style.display = 'block';
                        trigger.setAttribute('aria-expanded', 'true');
                    }}
                }});
            }}

            function selectCountry(country) {{
                const countrySelect = document.getElementById('nav-country');
                const countryList = document.getElementById('nav-country-list');
                const trigger = document.getElementById('nav-country-trigger');
                countrySelect.value = country;
                // Mark selected
                countryList.querySelectorAll('li').forEach(li => {{
                    li.classList.toggle('selected', li.getAttribute('data-value') === country);
                }});
                // Update trigger label
                updateCountryFlag(country);
                // Close dropdown
                countryList.style.display = 'none';
                trigger.setAttribute('aria-expanded', 'false');
                // Trigger existing handler
                onNavCountryChange();
            }}

            window.toggleCountryDropdown = function() {{
                const countryList = document.getElementById('nav-country-list');
                const trigger = document.getElementById('nav-country-trigger');
                const isOpen = countryList.style.display === 'block';
                if (isOpen) {{
                    countryList.style.display = 'none';
                    trigger.setAttribute('aria-expanded', 'false');
                }} else {{
                    // Position dropdown just below the trigger (fixed positioning)
                    const rect = trigger.getBoundingClientRect();
                    countryList.style.top = (rect.bottom + 2) + 'px';
                    countryList.style.left = rect.left + 'px';
                    countryList.style.minWidth = rect.width + 'px';
                    countryList.style.display = 'block';
                    trigger.setAttribute('aria-expanded', 'true');
                }}
            }};

            // Close dropdown when clicking outside
            document.addEventListener('click', function(event) {{
                const dropdown = document.getElementById('nav-country-dropdown');
                if (dropdown && !dropdown.contains(event.target)) {{
                    const list = document.getElementById('nav-country-list');
                    const trigger = document.getElementById('nav-country-trigger');
                    if (list) list.style.display = 'none';
                    if (trigger) trigger.setAttribute('aria-expanded', 'false');
                }}
            }});

            // ISO 3166-1 alpha-2 country codes (mirrors get_flag_html mapping)
            const COUNTRY_CODES = {{
                Afghanistan:'af',Albania:'al',Algeria:'dz',Andorra:'ad',Angola:'ao',
                Argentina:'ar',Armenia:'am',Australia:'au',Austria:'at',Azerbaijan:'az',
                Bahrain:'bh',Bangladesh:'bd',Belarus:'by',Belgium:'be',Bolivia:'bo',
                'Bosnia and Herzegovina':'ba',Brazil:'br',Bulgaria:'bg',Cameroon:'cm',
                Canada:'ca',Chile:'cl',China:'cn',Colombia:'co','Costa Rica':'cr',
                Croatia:'hr',Cyprus:'cy','Czech Republic':'cz',Denmark:'dk',
                Ecuador:'ec',Egypt:'eg','El Salvador':'sv',England:'gb',
                Estonia:'ee','Faroe Islands':'fo',Finland:'fi',France:'fr',
                Georgia:'ge',Germany:'de',Ghana:'gh',Gibraltar:'gi',Greece:'gr',
                Guatemala:'gt',Honduras:'hn','Hong Kong':'hk',Hungary:'hu',
                Iceland:'is',India:'in',Indonesia:'id',Iran:'ir',Iraq:'iq',
                Ireland:'ie',Israel:'il',Italy:'it','Ivory Coast':'ci',
                Jamaica:'jm',Japan:'jp',Kazakhstan:'kz',Kenya:'ke',Kosovo:'xk',
                Kuwait:'kw',Kyrgyzstan:'kg',Latvia:'lv',Liechtenstein:'li',
                Lithuania:'lt',Luxembourg:'lu',Malaysia:'my',Mali:'ml',Malta:'mt',
                Mexico:'mx',Moldova:'md',Mongolia:'mn',Montenegro:'me',Morocco:'ma',
                Netherlands:'nl','New Zealand':'nz',Nicaragua:'ni',Nigeria:'ng',
                'Northern Ireland':'gb-nir','North Macedonia':'mk',Norway:'no',
                Panama:'pa',Paraguay:'py',Peru:'pe',Philippines:'ph',Poland:'pl',
                Portugal:'pt',Qatar:'qa',Romania:'ro',Russia:'ru','San Marino':'sm',
                'Saudi Arabia':'sa',Scotland:'gb-sct',Senegal:'sn',Serbia:'rs',
                Singapore:'sg',Slovakia:'sk',Slovenia:'si','South Africa':'za',
                'South Korea':'kr',Spain:'es',Sweden:'se',Switzerland:'ch',
                Taiwan:'tw',Tajikistan:'tj',Thailand:'th',
                'Trinidad and Tobago':'tt',Tunisia:'tn',Turkey:'tr',
                Turkmenistan:'tm',Ukraine:'ua','United Arab Emirates':'ae',
                Uruguay:'uy',USA:'us','Uzbekistan':'uz',Venezuela:'ve',
                Vietnam:'vn',Wales:'gb-wls'
            }};

            function updateCountryFlag(country) {{
                const flagSpan = document.getElementById('nav-country-flag');
                const nameSpan = document.getElementById('nav-country-name');
                if (!nameSpan) return;
                if (flagSpan) flagSpan.innerHTML = '';
                if (!country) {{
                    nameSpan.textContent = 'Country';
                    return;
                }}
                nameSpan.textContent = country;
            }}

            window.onNavCountryChange = function() {{
                const country = document.getElementById('nav-country').value;
                updateCountryFlag(country);
                const championshipSelect = document.getElementById('nav-championship');
                const teamSelect = document.getElementById('nav-team');
                const matchSelect = document.getElementById('nav-match');
                const matchGroup = document.getElementById('nav-match-group');
                const matchActions = document.getElementById('nav-actions');

                championshipSelect.innerHTML = '<option value="">-- Select Championship --</option>';
                teamSelect.innerHTML = '<option value="">-- Select Team --</option>';
                matchSelect.innerHTML = '<option value="">-- Select Match --</option>';
                teamSelect.disabled = true;
                // Jul 30 2026: Match block stays visible (always shown).
                if (matchActions) matchActions.style.display = 'none';

                if (!country || !navData[country]) {{
                    championshipSelect.disabled = true;
                    return;
                }}

                // Jul 26 2026: render championships in navData insertion order
                // (top-tier first, lower tiers after, cups/super-cups last).
                // Previously this used Object.keys(...).sort() which is
                // ALPHABETICAL — and that pushed "Albanian Cup", "Super Cup",
                // "Division Profesional" etc. ahead of the real top-tier league.
                // The insertion order in leagues_data.json is maintained by hand
                // (e.g. England = ["Premier League", "Championship"]), so we
                // trust it as the source of truth for "highest league first".
                const championships = Object.keys(navData[country]);
                let currentChamp = null;
                for (const ch of championships) {{
                    if (navData[country][ch].some(t => t.id === CURRENT_TEAM_ID)) {{
                        currentChamp = ch;
                        break;
                    }}
                }}
                championships.forEach(championship => {{
                    const option = document.createElement('option');
                    option.value = championship;
                    option.textContent = championship;
                    if (championship === currentChamp) option.selected = true;
                    championshipSelect.appendChild(option);
                }});
                championshipSelect.disabled = false;
                onNavChampionshipChange();
            }};

            window.onNavChampionshipChange = function() {{
                const country = document.getElementById('nav-country').value;
                const championship = document.getElementById('nav-championship').value;
                const teamSelect = document.getElementById('nav-team');
                const matchSelect = document.getElementById('nav-match');
                const matchGroup = document.getElementById('nav-match-group');
                const matchActions = document.getElementById('nav-actions');

                teamSelect.innerHTML = '<option value="">-- Select Team --</option>';
                matchSelect.innerHTML = '<option value="">-- Select Match --</option>';
                // Jul 30 2026: Match block stays visible (always shown).
                if (matchActions) matchActions.style.display = 'none';

                if (!country || !championship || !navData[country][championship]) {{
                    teamSelect.disabled = true;
                    return;
                }}

                const teams = navData[country][championship];
                teams.forEach(team => {{
                    const option = document.createElement('option');
                    option.value = team.id;
                    option.textContent = team.name;
                    if (team.id === CURRENT_TEAM_ID) option.selected = true;
                    teamSelect.appendChild(option);
                }});
                teamSelect.disabled = false;
            }};

            window.onNavTeamChange = async function() {{
                const teamSelect = document.getElementById('nav-team');
                const teamId = teamSelect.value;
                const matchSelect = document.getElementById('nav-match');
                const matchGroup = document.getElementById('nav-match-group');
                const matchActions = document.getElementById('nav-actions');

                if (!teamId) {{
                    // Match block stays visible (Jul 30 2026).
                    // Just clear the dropdown and hide actions.
                    matchSelect.innerHTML = '<option value="">-- Select Match --</option>';
                    matchSelect.disabled = true;
                    if (matchActions) matchActions.style.display = 'none';
                    // Hide Fixture Overview too (no team = no data).
                    const fcBlock = document.getElementById('nav-fc-block');
                    if (fcBlock) fcBlock.style.display = 'none';
                    return;
                }}

                if (matchGroup) matchGroup.style.display = 'block';
                if (matchActions) matchActions.style.display = 'block';

                matchSelect.innerHTML = '<option value="">Loading fixtures...</option>';
                matchSelect.disabled = true;

                try {{
                    const resp = await fetch('/lineup_ai/api/fixtures/' + teamId);
                    const data = await resp.json();
                    navFixtures = data.fixtures || [];

                    matchSelect.innerHTML = '<option value="">-- Select a match --</option>';
                    navFixtures.forEach((f, i) => {{
                        const opt = document.createElement('option');
                        opt.value = i;
                        const tShort = f.tournament_name_short ? '[' + f.tournament_name_short + '] ' : '';
                        opt.textContent = tShort + f.date + '  ' + f.home + ' - ' + f.away;
                        matchSelect.appendChild(opt);
                    }});
                    matchSelect.disabled = false;
                    // Jul 30 2026: fetch Fixture Overview and render under match dropdown.
                    try {{
                        const fcResp = await fetch('/lineup_ai/api/fixture-congestion/' + teamId);
                        const fcData = await fcResp.json();
                        renderFixtureCongestion(fcData);
                    }} catch (e) {{
                        console.error('Failed to load fixture congestion:', e);
                    }}
                }} catch (e) {{
                    console.error('Failed to load fixtures:', e);
                    matchSelect.innerHTML = '<option value="">Failed to load</option>';
                }}
            }};

            // Jul 30 2026: render Fixture Overview block (calendar density metric).
            function renderFixtureCongestion(fc) {{
                const block = document.getElementById('nav-fc-block');
                if (!block) return;
                if (!fc || fc.next_matches_count < 2) {{
                    block.style.display = 'none';
                    return;
                }}
                block.style.display = 'block';
                const pct = (fc.fixture_congestion || 0) + '%';
                const bar = document.getElementById('nav-fc-bar');
                const pctEl = document.getElementById('nav-fc-pct');
                const statusEl = document.getElementById('nav-fc-status');
                const avgEl = document.getElementById('nav-fc-avg');
                const minEl = document.getElementById('nav-fc-min');
                const riskEl = document.getElementById('nav-fc-risk');
                if (bar) bar.innerHTML = (fc.progress_bar || '') + ' <span id="nav-fc-pct">' + pct + '</span>';
                const awayEl = document.getElementById('nav-fc-away');
                if (awayEl) {{
                    const away = (fc.away_matches || 0);
                    const total = (fc.total_matches || fc.next_matches_count || 0);
                    awayEl.textContent = away + '/' + total;
                    // Jul 31 2026: bold red when 4/5 or 5/5 of the
                    // next matches are away. Highlights heavy travel
                    // burden in the Fixture Overview block.
                    if (total >= 5 && away >= 4) {{
                        awayEl.style.fontWeight = '700';
                        awayEl.style.color = '#dc3545';
                    }} else {{
                        awayEl.style.fontWeight = '';
                        awayEl.style.color = '';
                    }}
                }}
                if (pctEl) pctEl.textContent = pct;
                const status = fc.status || 'LOW';
                const statusEmoji = status === 'EXTREME' ? '🔴'
                    : status === 'HIGH' ? '🟠'
                    : status === 'NORMAL' ? '🟡'
                    : '🟢';
                if (statusEl) {{
                    statusEl.textContent = statusEmoji + ' ' + status;
                    statusEl.style.color = status === 'EXTREME' ? '#dc3545'
                        : status === 'HIGH' ? '#f59e0b'
                        : status === 'NORMAL' ? '#eab308'
                        : '#16a34a';
                }}
                if (avgEl) avgEl.textContent = (fc.average_recovery_days || 0) + ' days';
                if (minEl) {{
                    // Show hours if < 24h (critical, same-day), else days.
                    // Points (avg/min) are floats so don't pluralize when displaying hours.
                    const hrs = fc.minimum_recovery_hours;
                    const days = fc.minimum_recovery_days;
                    if (hrs != null && hrs < 24) {{
                        const h = hrs < 1 ? '<1' : Math.round(hrs);
                        minEl.textContent = h + 'h ⚠️';
                        minEl.style.color = '#dc3545';
                    }} else {{
                        const d = (days || 0).toFixed(1);
                        minEl.textContent = d + ' days';
                        minEl.style.color = '';
                    }}
                }}
                const next14El = document.getElementById('nav-fc-next14');
                if (next14El) {{
                    // Jul 30 2026: Next 14 Days density.
                    // fc.next_14_days_matches is int 0..5
                    // (uses ONLY fixtures[:5], no extra API calls).
                    const n = (fc.next_14_days_matches != null)
                        ? fc.next_14_days_matches : 0;
                    const word = n === 1 ? 'match' : 'matches';
                    next14El.textContent = n + ' ' + word;
                }}
                if (riskEl) {{
                    // Display: "Rotation Risk — Low/Medium/High/Very High".
                    // fc.rotation_risk (Jul 30 2026) returns just the level.
                    const lvl = fc.rotation_risk || fc.risk_label || '—';
                    riskEl.textContent = 'Rotation Risk — ' + lvl;
                }}
            }};

            window.onNavMatchChange = function() {{
                const teamId = document.getElementById('nav-team').value;
                const idx = document.getElementById('nav-match').value;
                if (!teamId || idx === '' || !navFixtures) return;

                const fixture = navFixtures[parseInt(idx)];
                if (fixture) {{
                    const homeId = fixture.home_id || '';
                    const awayId = fixture.away_id || '';
                    const homeNm = fixture.home || '';
                    const awayNm = fixture.away || '';
                    const params = new URLSearchParams({{
                        mid: fixture.mid,
                        home_id: homeId,
                        away_id: awayId,
                        home_name: homeNm,
                        away_name: awayNm
                    }});
                    window.location.href = '/lineup_ai/compare/' + teamId + '?' + params.toString();
                }}
            }};

            window.openNavTeamAnalysis = function() {{
                const teamId = document.getElementById('nav-team').value;
                if (teamId) window.location.href = '/lineup_ai/' + teamId;
            }};

            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', loadNavData);
            }} else {{
                loadNavData();
            }}
            // Aug 20 2026: kick off the Tournament dropdown load in parallel.
            // Total is the default tab and the dropdown is rendered into the
            // header — populating it doesn't touch the player table until the
            // user changes the selection, so doing it in parallel is safe.
            if (typeof loadTournaments === 'function') {{
                if (document.readyState === 'loading') {{
                    document.addEventListener('DOMContentLoaded', loadTournaments);
                }} else {{
                    loadTournaments();
                }}
            }}
        }})();

        // ===== Builder Lineup =====
        const BL_PITCH_W = 540, BL_PITCH_H = 675, BL_CIRCLE = 47;
        // Coordinates as percentage of pitch (x%, y%); 100% = bottom/right, 0% = top/left
        const BL_FORMATIONS = {{
            '4-3-3': [
                {{role:'GK', x:50, y:90}},
                {{role:'LB', x:15, y:75}}, {{role:'CB', x:35, y:75}}, {{role:'CB', x:65, y:75}}, {{role:'RB', x:85, y:75}},
                {{role:'CM', x:25, y:55}}, {{role:'CM', x:50, y:55}}, {{role:'CM', x:75, y:55}},
                {{role:'LW', x:20, y:25}}, {{role:'CF', x:50, y:18}}, {{role:'RW', x:80, y:25}}
            ],
            '4-4-2': [
                {{role:'GK', x:50, y:90}},
                {{role:'LB', x:15, y:75}}, {{role:'CB', x:35, y:75}}, {{role:'CB', x:65, y:75}}, {{role:'RB', x:85, y:75}},
                {{role:'LM', x:10, y:50}}, {{role:'CM', x:38, y:50}}, {{role:'CM', x:62, y:50}}, {{role:'RM', x:90, y:50}},
                {{role:'ST', x:38, y:20}}, {{role:'ST', x:62, y:20}}
            ],
            '4-2-3-1': [
                {{role:'GK', x:50, y:90}},
                {{role:'LB', x:15, y:75}}, {{role:'CB', x:35, y:75}}, {{role:'CB', x:65, y:75}}, {{role:'RB', x:85, y:75}},
                {{role:'CDM', x:35, y:58}}, {{role:'CDM', x:65, y:58}},
                {{role:'LW', x:18, y:38}}, {{role:'CAM', x:50, y:35}}, {{role:'RW', x:82, y:38}},
                {{role:'ST', x:50, y:18}}
            ],
            '4-1-4-1': [
                {{role:'GK', x:50, y:90}},
                {{role:'LB', x:15, y:75}}, {{role:'CB', x:35, y:75}}, {{role:'CB', x:65, y:75}}, {{role:'RB', x:85, y:75}},
                {{role:'CDM', x:50, y:60}},
                {{role:'LM', x:10, y:45}}, {{role:'CM', x:38, y:45}}, {{role:'CM', x:62, y:45}}, {{role:'RM', x:90, y:45}},
                {{role:'ST', x:50, y:18}}
            ],
            '4-2-4': [
                {{role:'GK', x:50, y:90}},
                {{role:'LB', x:15, y:70}}, {{role:'CB', x:35, y:70}}, {{role:'CB', x:65, y:70}}, {{role:'RB', x:85, y:70}},
                {{role:'CM', x:35, y:48}}, {{role:'CM', x:65, y:48}},
                {{role:'LW', x:18, y:22}}, {{role:'ST', x:38, y:15}}, {{role:'ST', x:62, y:15}}, {{role:'RW', x:82, y:22}}
            ],
            '4-4-1-1': [
                {{role:'GK', x:50, y:90}},
                {{role:'LB', x:15, y:75}}, {{role:'CB', x:35, y:75}}, {{role:'CB', x:65, y:75}}, {{role:'RB', x:85, y:75}},
                {{role:'LM', x:10, y:50}}, {{role:'CM', x:38, y:50}}, {{role:'CM', x:62, y:50}}, {{role:'RM', x:90, y:50}},
                {{role:'CAM', x:50, y:32}},
                {{role:'ST', x:50, y:15}}
            ],
            '4-4-2-diamond': [
                {{role:'GK', x:50, y:90}},
                {{role:'LB', x:15, y:72}}, {{role:'CB', x:35, y:75}}, {{role:'CB', x:65, y:75}}, {{role:'RB', x:85, y:72}},
                {{role:'CDM', x:50, y:58}},
                {{role:'LM', x:18, y:42}}, {{role:'CM', x:38, y:42}}, {{role:'RM', x:82, y:42}},
                {{role:'CF', x:50, y:30}},
                {{role:'ST', x:50, y:15}}
            ],
            '3-1-4-2': [
                {{role:'GK', x:50, y:90}},
                {{role:'CB', x:25, y:75}}, {{role:'CB', x:50, y:75}}, {{role:'CB', x:75, y:75}},
                {{role:'CDM', x:50, y:60}},
                {{role:'LM', x:10, y:45}}, {{role:'CM', x:35, y:45}}, {{role:'CM', x:65, y:45}}, {{role:'RM', x:90, y:45}},
                {{role:'ST', x:38, y:18}}, {{role:'ST', x:62, y:18}}
            ],
            '3-4-3': [
                {{role:'GK', x:50, y:90}},
                {{role:'CB', x:25, y:75}}, {{role:'CB', x:50, y:75}}, {{role:'CB', x:75, y:75}},
                {{role:'LM', x:10, y:50}}, {{role:'CM', x:35, y:50}}, {{role:'CM', x:65, y:50}}, {{role:'RM', x:90, y:50}},
                {{role:'LW', x:20, y:22}}, {{role:'CF', x:50, y:15}}, {{role:'RW', x:80, y:22}}
            ],
            '3-5-2': [
                {{role:'GK', x:50, y:90}},
                {{role:'CB', x:25, y:75}}, {{role:'CB', x:50, y:75}}, {{role:'CB', x:75, y:75}},
                {{role:'LWB', x:8, y:50}}, {{role:'CM', x:30, y:50}}, {{role:'CDM', x:50, y:52}}, {{role:'CM', x:70, y:50}}, {{role:'RWB', x:92, y:50}},
                {{role:'ST', x:38, y:18}}, {{role:'ST', x:62, y:18}}
            ],
            '5-3-2': [
                {{role:'GK', x:50, y:90}},
                {{role:'LWB', x:8, y:72}}, {{role:'CB', x:25, y:75}}, {{role:'CB', x:50, y:75}}, {{role:'CB', x:75, y:75}}, {{role:'RWB', x:92, y:72}},
                {{role:'CM', x:30, y:50}}, {{role:'CM', x:50, y:50}}, {{role:'CM', x:70, y:50}},
                {{role:'ST', x:38, y:18}}, {{role:'ST', x:62, y:18}}
            ],
            '5-4-1': [
                {{role:'GK', x:50, y:90}},
                {{role:'LWB', x:8, y:72}}, {{role:'CB', x:25, y:75}}, {{role:'CB', x:50, y:75}}, {{role:'CB', x:75, y:75}}, {{role:'RWB', x:92, y:72}},
                {{role:'LM', x:10, y:48}}, {{role:'CM', x:35, y:48}}, {{role:'CM', x:65, y:48}}, {{role:'RM', x:90, y:48}},
                {{role:'ST', x:50, y:18}}
            ]
        }};

        function blBuildPlayerMap() {{
            // Read squad from main table data-player-name attributes
            // Format: "LastName FirstName" → reorder to "FirstName LastName"
            const map = {{}};
            const swap = function(name) {{
                const parts = (name || '').trim().split(/\s+/);
                if (parts.length < 2) return name;
                return parts.slice(1).join(' ') + ' ' + parts[0];
            }};
            document.querySelectorAll('.main-table tbody tr[data-player-name]').forEach(row => {{
                const cells = row.querySelectorAll('td');
                if (!cells || cells.length < 16) return;
                const numEl = cells[0].querySelector('.player-number-circle') || cells[0];
                const num = parseInt((numEl.textContent || '').trim(), 10);
                const name = (row.getAttribute('data-player-name') || cells[2].textContent || '').trim();
                if (num && !isNaN(num)) {{
                    map[num] = swap(name);
                }}
            }});
            return map;
        }}

        function blMakePlayerCircle(idx, role, x, y) {{
            const wrap = document.createElement('div');
            wrap.className = 'bl-player';
            wrap.dataset.idx = idx;
            wrap.dataset.role = role;
            wrap.style.cssText = `position:absolute;left:${{x}}%;top:${{y}}%;transform:translate(-50%,-50%);cursor:move;user-select:none;`;
            const circle = document.createElement('div');
            circle.style.cssText = `width:${{BL_CIRCLE}}px;height:${{BL_CIRCLE}}px;background:#000;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,0.4);border:2px solid #2e7af8;`;
            const numInput = document.createElement('input');
            numInput.type = 'text';
            numInput.maxLength = 3;
            numInput.dataset.idx = idx;
            numInput.style.cssText = 'width:100%;height:100%;background:transparent;border:none;color:#fff;font-size:18px;font-weight:700;text-align:center;outline:none;';
            numInput.addEventListener('input', function() {{ blUpdatePlayerName(idx); }});
            numInput.addEventListener('click', function(e) {{ e.stopPropagation(); }});
            circle.appendChild(numInput);
            const nameLabel = document.createElement('div');
            nameLabel.id = 'bl-name-' + idx;
            nameLabel.style.cssText = 'position:absolute;left:50%;top:100%;transform:translateX(-50%);color:#fff;font-size:14px;font-weight:600;white-space:nowrap;margin-top:4px;text-shadow:0 1px 3px rgba(0,0,0,0.8);text-align:center;';
            nameLabel.textContent = role;
            wrap.appendChild(circle);
            wrap.appendChild(nameLabel);
            blMakeDraggable(wrap);
            return wrap;
        }}

        function blMakeDraggable(el) {{
            // GK cannot be dragged
            if (el.dataset.role === 'GK') {{
                el.style.cursor = 'default';
                return;
            }}
            el.addEventListener('mousedown', function(e) {{
                if (e.target.tagName === 'INPUT') return;
                e.preventDefault();
                e.stopPropagation();
                const parentRect = el.parentElement.getBoundingClientRect();
                const rect = el.getBoundingClientRect();
                const startLeft = rect.left - parentRect.left;
                const startTop = rect.top - parentRect.top;
                const offsetX = e.clientX - rect.left;
                const offsetY = e.clientY - rect.top;
                el.style.transform = 'none';
                el.style.zIndex = '100';
                function onMove(ev) {{
                    const newLeft = ev.clientX - parentRect.left - offsetX;
                    const newTop = ev.clientY - parentRect.top - offsetY;
                    const clampedLeft = Math.max(0, Math.min(parentRect.width - BL_CIRCLE, newLeft));
                    const clampedTop = Math.max(0, Math.min(parentRect.height - BL_CIRCLE, newTop));
                    el.style.left = clampedLeft + 'px';
                    el.style.top = clampedTop + 'px';
                }}
                function onUp() {{
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onUp);
                    el.style.zIndex = '';
                }}
                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onUp);
            }});
        }}

        function blUpdatePlayerName(idx) {{
            const input = document.querySelector(`.bl-player[data-idx="${{idx}}"] input`);
            const label = document.getElementById('bl-name-' + idx);
            if (!input || !label) return;
            const num = parseInt(input.value.trim(), 10);
            if (isNaN(num)) {{
                label.textContent = label.dataset.role || '–';
                return;
            }}
            const playerMap = blBuildPlayerMap();
            if (playerMap[num]) {{
                label.textContent = playerMap[num];
            }} else {{
                label.textContent = '—';
            }}
        }}

        function applyFormation(name) {{
            const formation = BL_FORMATIONS[name];
            if (!formation) return;
            const container = document.getElementById('bl-players');
            if (!container) return;
            container.innerHTML = '';
            formation.forEach((p, i) => {{
                const circle = blMakePlayerCircle(i, p.role, p.x, p.y);
                circle.dataset.role = p.role;
                container.appendChild(circle);
            }});
        }}

        function clearFormation() {{
            const sel = document.getElementById('bl-formation');
            if (sel) {{
                applyFormation(sel.value);
            }}
        }}

        async function saveLineupPNG() {{
            const pitch = document.getElementById('bl-pitch');
            if (!pitch) return;
            // Temporarily remove drag shadow
            const canvas = await html2canvas(pitch, {{
                backgroundColor: null,
                scale: 2,
                useCORS: true,
                logging: false
            }});
            const link = document.createElement('a');
            const tname = document.getElementById('bl-team-name');
            const name = tname ? (tname.textContent || 'lineup').trim() : 'lineup';
            link.download = name.replace(/\s+/g, '_') + '_lineup.png';
            link.href = canvas.toDataURL('image/png');
            link.click();
        }}

        // Initialize builder on load with default 4-3-3
        (function() {{
            applyFormation('4-3-3');
        }})();

        // Team-squad-emoji (📊) tooltip: show info-bar-squad as a fixed-position
        // tooltip when hovering the emoji next to the team name. Tooltip is 255x258.4px.
        (function() {{
            const squadSource = document.getElementById('info-bar-squad');
            if (!squadSource) return;
            const emoji = document.querySelector('.team-squad-emoji');
            if (!emoji) return;
            // Create the tooltip element (sibling of emoji inside the team-name div)
            const tip = document.createElement('div');
            tip.className = 'team-squad-tooltip';
            // Clone the rendered info-bar-squad contents
            tip.innerHTML = squadSource.innerHTML;
            emoji.parentElement.appendChild(tip);
            // Position the tooltip next to the emoji on hover
            let isHover = false;
            function show() {{
                isHover = true;
                const r = emoji.getBoundingClientRect();
                // Default: place to the right of emoji
                let left = r.right + 8;
                let top = r.top - 4;
                // If tooltip would overflow viewport on the right, place to the left
                if (left + 255 > window.innerWidth) {{
                    left = r.left - 255 - 8;
                }}
                // If still off-screen, clamp to viewport
                if (left < 4) left = 4;
                if (top + 258.4 > window.innerHeight) {{
                    top = window.innerHeight - 258.4 - 4;
                }}
                if (top < 4) top = 4;
                tip.style.left = left + 'px';
                tip.style.top = top + 'px';
                tip.style.display = 'block';
            }}
            function hide() {{
                // Delay hide so user can move cursor into the tooltip itself
                setTimeout(function() {{
                    if (!isHover) tip.style.display = 'none';
                }}, 100);
                isHover = false;
            }}
            emoji.addEventListener('mouseenter', show);
            emoji.addEventListener('mouseleave', function() {{ isHover = false; hide(); }});
            tip.addEventListener('mouseenter', function() {{ isHover = true; tip.style.display = 'block'; }});
            tip.addEventListener('mouseleave', function() {{ isHover = false; hide(); }});
        }})();
        </script>
    </div>
    </div>
    </div>
    <!-- Reverse Odds Modal (Aug 26 2026) -->
    <div id="reverse-odds-host" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);z-index:99999;justify-content:flex-end;align-items:flex-end;padding:40px 20px;overflow-y:auto;box-sizing:border-box;">
        <div style="background:white;border-radius:12px;width:480px;max-width:100%;padding:22px 26px 24px 26px;box-shadow:0 10px 40px rgba(0,0,0,0.25);position:relative;font-family:inherit;">
            <button type="button" onclick="toggleReverseOdds()" style="position:absolute;top:10px;right:10px;background:transparent;border:none;font-size:22px;cursor:pointer;color:#888;line-height:1;padding:2px 8px;" title="Close">&times;</button>
            <h2 style="margin:0 0 16px 0;color:#043fb6;font-size:19px;text-align:center;">🔄 Reverse Odds</h2>
            <div style="font-size:13px;color:#333;line-height:1.5;">
                <label for="ro-home-odd" style="display:block;font-weight:600;margin:8px 0 4px 0;font-size:13px;">Home Odd</label>
                <input id="ro-home-odd" type="text" inputmode="decimal" placeholder="Enter home odd" style="width:100%;box-sizing:border-box;padding:8px 10px;font-size:14px;border:1px solid #cbd5e1;border-radius:6px;outline:none;" />

                <label for="ro-away-odd" style="display:block;font-weight:600;margin:12px 0 4px 0;font-size:13px;">Away Odd</label>
                <input id="ro-away-odd" type="text" inputmode="decimal" placeholder="Enter away odd" style="width:100%;box-sizing:border-box;padding:8px 10px;font-size:14px;border:1px solid #cbd5e1;border-radius:6px;outline:none;" />

                <label for="ro-htl-index" style="display:block;font-weight:600;margin:12px 0 4px 0;font-size:13px;">ORI</label>
                <input id="ro-htl-index" type="text" inputmode="decimal" placeholder="Enter league index" style="width:100%;box-sizing:border-box;padding:8px 10px;font-size:14px;border:1px solid #cbd5e1;border-radius:6px;outline:none;" />

                <div id="ro-error" style="display:none;color:#c53030;font-size:12px;margin:10px 0 0 0;"></div>

                <div style="display:flex;justify-content:center;margin:18px 0 14px 0;">
                    <button type="button" id="ro-calculate" onclick="calculateReverseOdds()" style="background:#043fb6;color:#fff;border:none;padding:9px 28px;font-size:14px;font-weight:600;border-radius:6px;cursor:pointer;">Calculate</button>
                </div>

                <div id="ro-result" style="display:none;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;margin-bottom:14px;">
                    <div style="font-size:13px;color:#043fb6;font-weight:700;text-align:center;margin-bottom:10px;">Result</div>
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;font-size:14px;">
                        <span style="color:#475569;">H2A (Home → Away)</span>
                        <span id="ro-h2a" style="font-weight:700;font-size:15px;color:#0f172a;">—</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;font-size:14px;">
                        <span style="color:#475569;">A2H (Away → Home)</span>
                        <span id="ro-a2h" style="font-weight:700;font-size:15px;color:#0f172a;">—</span>
                    </div>
                </div>

                <div style="border-top:1px solid #e2e8f0;padding-top:12px;color:#64748b;font-size:12px;line-height:1.55;">
                    <div style="font-weight:600;color:#475569;margin-bottom:3px;">ℹ️ ORI (Odds Reversal Index)</div>
                    <div>100% / Total Home Winning Rate (Previous Season)</div>
                </div>
            </div>
        </div>
    </div>

    <!-- FAQ Modal -->
    <div id="faq-host" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);z-index:99999;justify-content:center;align-items:flex-start;padding:40px 20px;overflow-y:auto;box-sizing:border-box;">
        <div style="background:white;border-radius:12px;max-width:930px;width:100%;padding:24px 28px;box-shadow:0 10px 40px rgba(0,0,0,0.25);position:relative;">
            <button type="button" onclick="toggleFaq()" style="position:absolute;top:12px;right:12px;background:transparent;border:none;font-size:24px;cursor:pointer;color:#888;line-height:1;padding:4px 10px;">&times;</button>
            <h2 style="margin:0 0 18px 0;color:#043fb6;font-size:22px;">📋 FREQUENTLY ASKED QUESTIONS</h2>
            <div style="font-size:14px;color:#333;line-height:1.6;">

                <h3 style="color:#043fb6;margin:18px 0 6px 0;font-size:15px;">1. What do the player status icons mean?</h3>
                <p style="margin:4px 0;">❓ — Doubt<br>❌ — Injury<br>🟥 — Red card<br>🟨 — Last yellow card<br>✈️ — Called up<br>🚫 — Not playing<br>🔙 — Return<br>🆕 — New player<br>🚪 — Left the team</p>

                <h3 style="color:#043fb6;margin:18px 0 6px 0;font-size:15px;">2. What do the player role badges represent?</h3>
                <p style="margin:4px 0;">⚽️ — Top Scorer<br>👟 — Top Assist<br>🎯 — Attacking Defender (IS &gt;6)<br>🎨 — Creative Midfielder (IS &gt;5)<br>⭐️ — Very Strong Player (IS &gt; 7)<br>👑 — World-Class Player (IS &gt; 9)</p>

                <h3 style="color:#043fb6;margin:18px 0 6px 0;font-size:15px;">3. How is the Impact Score (IS) calculated?</h3>
                <p style="margin:4px 0;">Impact Score — comprehensive indicator that measures a player's real impact on the team's outcome. Goals, assists, playing time and field position are taken into account. The formula gives different weights to goals, assists, and playing time for each role, so it's incorrect to compare a defender and a striker directly — it's important to look at the value relative to the position.</p>

                <h3 style="color:#043fb6;margin:18px 0 6px 0;font-size:15px;">4. What's the difference between Squad List, Possible XI, and Starting XI?</h3>
                <p style="margin:4px 0;">⚫️ Squad List — full squad of all available players<br>🔵 Possible XI — predicted lineup on match<br>🔴 Starting XI — starting lineup on match</p>

                <h3 style="color:#043fb6;margin:18px 0 6px 0;font-size:15px;">5. How do I add my own lineup?</h3>
                <p style="margin:4px 0;">Use the 👥 Add Lineups feature. You can paste text (separated by commas) or upload an image — the system uses AI to detect and match the lineup from the image to squad list.</p>

                <h3 style="color:#043fb6;margin:18px 0 6px 0;font-size:15px;">6. Can I compare lineups?</h3>
                <p style="margin:4px 0;">Yes! You can compare:<br>Starting XI — Possible XI — See how the predicted lineup stacks up against the actual lineup (Δ8% = possible odds move).<br>Starting XI — Last Match — Compare starting lineup with the previous game.<br>Possible XI — Last Match — Evaluate the predicted lineup with the previous game.</p>

                <h3 style="color:#043fb6;margin:18px 0 6px 0;font-size:15px;">7. What are the requirements for a player to receive a badge?</h3>
                <p style="margin:4px 0;">Minimum of 10 matches or 900 minutes played (excluding Top Scorer and Top Assist). Badges are assigned based on current calculations at the time of viewing.</p>

                <h3 style="color:#043fb6;margin:18px 0 6px 0;font-size:15px;">8. What stats are shown in the team overview 📊?</h3>
                <p style="margin:4px 0;">Total Value — Combined market worth.<br>Avg. Age — Average age of all players.<br>Players — Total squad count.<br>Pos. Overview — Breakdown by position (GK, DF, MF, FW).<br>Players on Fire — Top performers based on recent stats.</p>

                <h3 style="color:#043fb6;margin:18px 0 6px 0;font-size:15px;">9. How do I save a lineup as an image?</h3>
                <p style="margin:4px 0;">📸 Screenshot — Save any lineup as a high-resolution PNG image directly to your computer's Downloads folder.</p>

                <h3 style="color:#043fb6;margin:18px 0 6px 0;font-size:15px;">10. What is Build Lineup and how does it work?</h3>
                <p style="margin:4px 0;">🧩 Build Lineup — interactive tool that lets you create your own custom XI.<br><strong>How to use it:</strong><br>Choose a formation — Select from popular formations like 4-3-3, and more.<br>Assign players — Tap on any position circle and insert the player's shirt number. The system will automatically match it to the squad list.<br>Save PNG — Once your lineup is complete, save it and download as an image to share or use elsewhere.</p>

            </div>
        </div>
    </div>
<aside class="tweets-sidebar" id="tweets-sidebar">
        <div class="tweets-sidebar-header">
            <span>Latest News</span>
            <span class="tweets-count" id="tweets-count">0</span>
        </div>
        <div class="tweets-sidebar-list" id="tweets-list">
            <div class="tweet-empty">Loading news...</div>
        </div>
    </aside>

<script>
(function() {{
    var TEAM_ID = (new URLSearchParams(location.search).get('team_id')) || ((location.pathname.match(/\/lineup_ai\/([^/?]+)/) || [])[1]) || '';
    // Aug 24 2026 — Max asked to skip squad refreshes for matches
    // that are still > 1 h away. Read kickoff_ts from the parent
    // page URL (the parent passes ?kickoff_ts=<epoch> when opening
    // a match via ▶ Open Match). This lets _applyPredictedXIIframe
    // know whether the lineup is still being reshuffled (within 1 h)
    // or stable (further out) so it can skip the 8-37 s squad fetch.
    var PXI_KICKOFF_TS = parseInt(new URLSearchParams(location.search).get('kickoff_ts') || '0', 10) || 0;
    window.PXI_KICKOFF_TS = PXI_KICKOFF_TS;
    var SIDEBAR = document.getElementById('tweets-sidebar');
    var LIST = document.getElementById('tweets-list');
    var COUNT_EL = document.getElementById('tweets-count');
    // Aug 22 2026 — flag consumed by applyBuilderVisibility so it
    // doesn't strip the .hidden class while 🔮 Predicted XI owns
    // the layout. Exposed on window for one-way consumption.
    window._predictedXIOpen = function () {{
        var host = document.getElementById('predicted11-panel-host');
        if (!host) return false;
        var cs = window.getComputedStyle(host);
        return cs.display !== 'none' && host.offsetParent !== null;
    }};

    function escapeHtml(s) {{
        return String(s).replace(/[&<>"]/g, function(c) {{ return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]; }});
    }}

    function highlightText(text, players, keywords, opts) {{
        // Aug 23 2026 — Max asked to render Markdown-style
        // **bold** as actual <strong> tags so the player name
        // inside live-event posts (e.g. red-card templates) shows
        // up bold without a yellow highlight background. The bold
        // runs are processed BEFORE the player/keyword scans so
        // the regex below can't accidentally grab a substring
        // from inside the <strong>…</strong> we just emitted.
        var out = escapeHtml(text);
        out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        // Aug 7 2026: convert literal newline chars to <br> for line breaks.
        out = out.split('\\n').join('<br>');
        var sortedP = [...players].sort(function(a, b) {{ return b.length - a.length; }});
        var sortedK = [...keywords].sort(function(a, b) {{ return b.length - a.length; }});
        var escRe = function(s) {{ return String(s).replace(/[.*+?^$()|\[\]\\/]/g, '\\$&'); }};
        // Aug 23 2026 — Max asked to drop the yellow
        // <mark class="player"> highlight on live-event posts
        // (red cards, substitutions). The card CSS already paints
        // the background orange-ish so the additional yellow pill
        // was redundant and noisy. Player highlights on regular
        // tweets remain unchanged. Opt-out via opts.live = true.
        var isLive = !!(opts && opts.live);
        if (!isLive) {{
            for (var i = 0; i < sortedP.length; i++) {{
                var p = sortedP[i];
                if (!p) continue;
                var re = new RegExp('(' + escRe(p) + ')', 'gi');
                out = out.replace(re, '<mark class="player">$1</mark>');
            }}
        }}
        for (var i = 0; i < sortedK.length; i++) {{
            var k = sortedK[i];
            if (!k) continue;
            var re = new RegExp('(' + escRe(k) + ')', 'gi');
            out = out.replace(re, '<mark class="keyword">$1</mark>');
        }}
        return out;
    }}

    function fmtTime(iso) {{
        if (!iso) return '';
        try {{
            var d = new Date(iso);
            var now = new Date();
            var diff = Math.floor((now - d) / 60000);
            if (diff < 60) return diff + 'm';
            if (diff < 1440) return Math.floor(diff / 60) + 'h';
            return Math.floor(diff / 1440) + 'd';
        }} catch (e) {{ return ''; }}
    }}

    function render(tweets) {{
        if (!tweets || tweets.length === 0) {{
            LIST.innerHTML = '<div class="tweet-empty">No news for this team yet.</div>';
            COUNT_EL.textContent = '0';
            return;
        }}
        COUNT_EL.textContent = tweets.length;
        var readIds = getReadTweetIds();
        var html = '';
        for (var i = 0; i < tweets.length; i++) {{
            var t = tweets[i];
            var highlighted;
            try {{
                // Aug 23 2026 — live-event posts (red cards,
                // substitutions) opt out of the yellow
                // <mark class="player"> highlight via the
                // opts.live flag. Regular tweets still get the
                // highlight.
                highlighted = highlightText(t.text || '', t.matched_players || [], t.matched_keywords || [], {{ live: !!t.is_live_event }});
            }} catch (he) {{
                // Aug 9 2026: highlightText throws on pathological player text
                // (e.g. un-escaped regex chars). Fall back to plain escaped text.
                console.warn('[tweets-sidebar] highlightText error, falling back to plain text:', he && he.message);
                highlighted = escapeHtml(t.text || '').split(String.fromCharCode(10)).join('<br>');
            }}
            var user = escapeHtml(t.source_username || '@unknown');
            var url = escapeHtml(t.url || '#');
            var ago = fmtTime(t.created_at);
            var tid = escapeHtml(t.tweet_id || '');
            var isRead = tid && readIds[tid] ? ' read' : '';
            var extraClass = t.is_live_event ? ' live-event' : '';
            html += '<div class="tweet-card' + extraClass + isRead + '" data-tweet-id="' + tid + '">'
                + '<div class="tweet-source">' + user + '</div>'
                + '<div class="tweet-text">' + highlighted + '</div>'
                + '<div class="tweet-meta"><span>' + ago + '</span><a href="' + url + '" target="_blank" rel="noopener">View on X ↗</a></div>'
                + '</div>';
        }}
        LIST.innerHTML = html;
        // Aug 7 2026: update counter to "read/total".
        var readCount = 0;
        var cards = LIST.querySelectorAll('.tweet-card');
        for (var k = 0; k < cards.length; k++) {{
            if (cards[k].classList.contains('read')) readCount++;
        }}
        COUNT_EL.textContent = readCount + '/' + cards.length;
        // Attach click handler — toggle read state on the tweet card.
        // Don't trigger when the user clicked the "View on X" link.
        var cardsArr = LIST.querySelectorAll('.tweet-card');
        for (var c = 0; c < cardsArr.length; c++) {{
            cardsArr[c].addEventListener('click', function(e) {{
                if (e.target.tagName === 'A') return;
                var id = this.getAttribute('data-tweet-id');
                if (!id) return;
                this.classList.toggle('read');
                toggleReadTweet(id, this.classList.contains('read'));
                var totalCards = LIST.querySelectorAll('.tweet-card').length;
                var rc = LIST.querySelectorAll('.tweet-card.read').length;
                COUNT_EL.textContent = rc + '/' + totalCards;
            }});
        }}
    }}

    // Aug 7 2026: persist read tweet IDs in localStorage so they remain read across reloads.
    var READ_STORAGE_KEY = 'formalert_read_tweets';
    function getReadTweetIds() {{
        try {{
            var raw = localStorage.getItem(READ_STORAGE_KEY);
            if (!raw) return {{}};
            var obj = JSON.parse(raw);
            return (obj && typeof obj === 'object') ? obj : {{}};
        }} catch (e) {{ return {{}}; }}
    }}
    function toggleReadTweet(id, isRead) {{
        var ids = getReadTweetIds();
        if (isRead) ids[id] = 1; else delete ids[id];
        try {{
            // Aug 7 2026: cap storage at 500 most-recent entries to prevent bloat.
            var keys = Object.keys(ids);
            if (keys.length > 500) {{
                var trimmed = {{}};
                keys.slice(-500).forEach(function(k) {{ trimmed[k] = 1; }});
                ids = trimmed;
            }}
            localStorage.setItem(READ_STORAGE_KEY, JSON.stringify(ids));
        }} catch (e) {{ /* localStorage unavailable */ }}
    }}

    function applyBuilderVisibility() {{
        var builder = document.getElementById('builder-lineup-host');
        if (!builder) return;
        var style = window.getComputedStyle(builder);
        var visible = style.display !== 'none' && builder.offsetParent !== null;
        if (visible) {{
            SIDEBAR.classList.add('hidden');
        }} else {{
            // Aug 22 2026 — when 🔮 Predicted XI is the open panel,
            // it replaces the tweets sidebar instead of the builder.
            // Don't let this routine strip the .hidden class the
            // togglePredicted11 handler just applied. We check via a
            // global flag rather than reading our own state — keeps the
            // coupling one-way (P11 manages the flag, this just obeys).
            if (typeof window._predictedXIOpen === 'function' && window._predictedXIOpen()) return;
            SIDEBAR.classList.remove('hidden');
        }}
    }}

    async function fetchTweets() {{
        if (!TEAM_ID) return;
        try {{
            console.log('[tweets-sidebar] fetchTweets starting for team', TEAM_ID);
            // Fetch BOTH the team-specific tweets AND the global recent tweets,
            // then merge them. Recent tweets that match the current team
            // (player name or keyword) are highlighted first.
            var teamP = fetch('/lineup_ai/api/team_tweets?team_id=' + encodeURIComponent(TEAM_ID) + '&limit=10').then(function(r) {{
                console.log('[tweets-sidebar] team_tweets response', r.status);
                if (!r.ok) return {{ tweets: [] }};
                return r.json();
            }});
            var recentP = fetch('/lineup_ai/api/recent_tweets?limit=10').then(function(r) {{
                if (!r.ok) return {{ tweets: [] }};
                return r.json();
            }});
            // Aug 7 2026: live events (red cards + early subs) from Telegram mirror.
            var liveP = fetch('/lineup_ai/api/live_events?limit=10').then(function(r) {{
                if (!r.ok) return {{ events: [] }};
                return r.json();
            }});
            var results = await Promise.all([teamP, recentP, liveP]);
            var teamTweets = (results[0] && results[0].tweets) || [];
            var recentTweets = (results[1] && results[1].tweets) || [];
            var liveEvents = (results[2] && results[2].events) || [];
            var seen = {{}};
            var merged = [];
            // Team-specific tweets first (they're already sorted by relevance).
            for (var i = 0; i < teamTweets.length; i++) {{
                if (!seen[teamTweets[i].tweet_id]) {{
                    seen[teamTweets[i].tweet_id] = true;
                    merged.push(teamTweets[i]);
                }}
            }}
            // Then recent tweets (any team, but only those that passed all 5 filters).
            for (var j = 0; j < recentTweets.length; j++) {{
                if (!seen[recentTweets[j].tweet_id]) {{
                    seen[recentTweets[j].tweet_id] = true;
                    merged.push(recentTweets[j]);
                }}
            }}
            // Aug 7 2026: convert live events to pseudo-tweets and merge.
            for (var k = 0; k < liveEvents.length; k++) {{
                var ev = liveEvents[k];
                var pseudoId = 'live-' + ev.event_id;
                if (seen[pseudoId]) continue;
                seen[pseudoId] = true;
                var evtText;
                var evtMatchLabel = ev.match_label || '';
                // Aug 9 2026: clean up match label — strip markdown (**), soccer ball emoji,
                // trailing colon. Splits on ' - ' (with spaces) or ' -' (no trailing space)
                // because mirror bot sometimes sends "A - ⚽ B:" with emoji embedded.
                var evtHeader = '';
                if (evtMatchLabel) {{
                    var cleanLabel = evtMatchLabel
                        .replace(/\*/g, '')
                        .replace(/⚽|⚽️/g, '')
                        .replace(/:\s*$/, '')
                        .trim();
                    var parts = cleanLabel.split(/\s+[-–—]\s+/);
                    if (parts.length === 2) {{
                        evtHeader = parts[0].trim() + ' - ' + parts[1].trim();
                    }} else {{
                        evtHeader = cleanLabel;
                    }}
                }}
                var evtIcon = ev.event_type === 'red_card' ? '🟥' : '🔁';
                var evtMinute = (ev.minute || 0) + ' min';
                var evtTeam = ev.team || '';
                var evtPlayer = ev.player || '';
                // Aug 9 2026: strip prefix like "57': 🟥 Красная карточка игроку " or
                // "🔁 Замена " from player text. Keep only the actual player name.
                // Patterns observed: red_card = "<min>': 🟥 <word> игроку <NAME>";
                // substitution = "🔁 Замена <NAME>"; yellow = "🟨 <word> <NAME>".
                // Aug 23 2026 — expanded: also drop the full "90+3': 🟥 Красная
                // карточка игроку " blob that some sources pack into the
                // player field, plus a leading ⏪ (rewind-symbol) sometimes
                // prepended by the mirror. The regex walks through every
                // possible prefix the upstream can attach; what remains is
                // assumed to be the bare player name.
                evtPlayer = evtPlayer
                    .replace(/^[⏪🔁🟥🟨🔴🟠]\s*/u, '')
                    .replace(/^[\d+\s']*'?[:\s]*/u, '')
                    .replace(/^[🟥🟨🔴🟠🔁⏪⏮️]\s*/u, '')
                    .replace(/^Красная\s+карточка\s+игроку\s+/iu, '')
                    .replace(/^Жёлтая\s+карточка\s+игроку\s+/iu, '')
                    .replace(/^Желтая\s+карточка\s+игроку\s+/iu, '')
                    .replace(/^Замена\s+в\s+команде\s+[^:]*:\s*/iu, '')
                    .replace(/^Замена\s+/iu, '')
                    .replace(/^Удаление\s+/iu, '')
                    .replace(/^Удалён\s+/iu, '')
                    .replace(/^[🟥🟨🔴🟠🔁⏪⏮️]\s*/u, '')
                    .replace(/\*/g, '')
                    .trim();
                // Aug 23 2026 — Max asked for one canonical red-card
                // post template:
                //   <Home Team> - <Away Team>
                //
                //   RED-CARD <minute> min - <Player> (<Team>)
                // Player name is bold (Markdown **), minute is the
                // bare game-minute (e.g. 90+13 becomes 90), no
                // Russian text is emitted, no leading ORANGE marker
                // (that is for substitutions only), and the
                // highlightText call below must NOT wrap this
                // player in a yellow <mark class="player">.
                var evtIcon = ev.event_type === 'red_card' ? '🟥' : '🔁';
                var rawMinute = String(ev.minute || 0);
                var evtMinute = rawMinute.replace(/^\s*\d+\s*/, function (m) {{
                    // Keep just the leading integer - drops the "+13" stoppage
                    // time suffix and any stray quote or whitespace.
                    return m.replace(/[^0-9]/g, '');
                }}) + ' min';
                var evtTeam = ev.team || '';
                var evtPrefix = ev.event_type === 'red_card' ? '' : '🟠 ';
                var evtLine1 = evtHeader;
                var evtLine2 = evtIcon + ' ' + evtMinute + ' — ' + evtPrefix + '**' + evtPlayer + '**' +
                    (evtTeam ? ' (' + evtTeam + ')' : '');
                // Use String.fromCharCode(10) to embed newline char. highlightText converts it to <br>.
                var nl = String.fromCharCode(10);
                evtText = (evtLine1 ? evtLine1 + nl + nl : '') + evtLine2;
                merged.push({{
                    tweet_id: pseudoId,
                    created_at: ev.created_at,
                    source_username: '@LineupValue_LIVE',
                    text: evtText,
                    url: '',
                    media_url: '',
                    media_type: '',
                    matched_players: evtPlayer ? [evtPlayer] : [],
                    matched_keywords: [],
                    is_live_event: true,
                    event_type: ev.event_type
                }});
            }}
            // Aug 7 2026: sort merged tweets by created_at DESC (newest first).
            merged.sort(function(a, b) {{
                var ta = a.created_at ? new Date(a.created_at).getTime() : 0;
                var tb = b.created_at ? new Date(b.created_at).getTime() : 0;
                return tb - ta;
            }});

            render(merged);
        }} catch (e) {{
            LIST.innerHTML = '<div class="tweet-empty">Loading error</div>';
        }}
    }}

    fetchTweets();
    setInterval(fetchTweets, 5000);

    function syncHeight() {{
        var nav = document.getElementById('team-nav-sidebar');
        if (!nav || !SIDEBAR) return;
        var r = nav.getBoundingClientRect();
        // .tweets-sidebar is position:fixed, so top must be VIEWPORT-relative.
        // Do NOT add window.scrollY here — that made the sidebar drift down
        // while scrolling (scrollY offset kept growing). Align its top edge
        // exactly with the team-nav-sidebar top edge.
        SIDEBAR.style.top = r.top + 'px';
    }}

    syncHeight();
    setInterval(syncHeight, 2000);
    if (window.ResizeObserver) {{
        var nav = document.getElementById('team-nav-sidebar');
        if (nav) {{
            new ResizeObserver(syncHeight).observe(nav);
        }}
    }}
    window.addEventListener('scroll', syncHeight, {{ passive: true }});
    window.addEventListener('resize', syncHeight);

    var observer = new MutationObserver(applyBuilderVisibility);
    var target = document.getElementById('builder-lineup-host');
    if (target) {{
        observer.observe(target, {{ attributes: true, attributeFilter: ['style', 'class'] }});
        applyBuilderVisibility();
    }}
    setInterval(applyBuilderVisibility, 1000);

    // Aug 14 2026: listen for Collapse Details toggles from the parent (Match mode).
    // The compare-template owns the global state and broadcasts a
    // "setDetailsCollapsed" event on load and on every click. We mirror the
    // state via `detail-hidden` on <body>; a single CSS rule
    // (.detail-hidden .col-mv/.col-role/.col-is) hides the three columns
    // across thead and tbody without touching layout. We also cache locally
    // so the state survives a same-tab reload.
    var DETAILS_KEY = 'fa_detail_collapsed_v1';
    var applyDetailHidden = function(collapsed) {{
        try {{
            if (collapsed) document.body.classList.add('detail-hidden');
            else document.body.classList.remove('detail-hidden');
            try {{ sessionStorage.setItem(DETAILS_KEY, collapsed ? '1' : '0'); }} catch (e) {{ }}
        }} catch (e) {{ /* noop */ }}
    }};
    window.addEventListener('message', function(ev) {{
        try {{
            var d = ev.data;
            if (!d || typeof d !== 'object') return;
            if (d.type === 'setDetailsCollapsed') {{
                applyDetailHidden(!!d.collapsed);
            }} else if (d.type === 'applyPredictedXI' && d.match_id) {{
                _applyPredictedXIIframe(d.match_id);
            }} else if (d.type === 'setBulkMode' && d.value) {{
                // Aug 26 2026 — Max asked: when a user opens a match
                // via the ▶ Open Match link in 🔮 Predicted XI
                // (which sets ?autopxi=1 in the URL), the bulk
                // lineup panel should default to "🔴 S-XI" instead
                // of the regular "🔵 P-XI". The compare-template
                // parent fires this postMessage to every iframe
                // right after it fires applyPredictedXI, so both
                // iframes flip their dropdown to S-XI in lockstep.
                try {{
                    var sel = document.getElementById('bulk-lineup-mode');
                    if (sel) {{
                        sel.value = d.value;
                        // Fire a synthetic change event so any
                        // downstream listeners (counters, etc.)
                        // pick up the new value.
                        var ev2 = document.createEvent('Event');
                        ev2.initEvent('change', true, true);
                        sel.dispatchEvent(ev2);
                    }}
                }} catch (e) {{ /* noop */ }}
            }} else if (d.type === 'togglePredictedXI') {{
                // Aug 22 2026 — Match-mode header button delegates
                // to the team-mode iframe via postMessage so the
                // Predicted XI panel can be opened/closed from
                // either mode without duplicating the rendering
                // logic.
                if (typeof window.togglePredicted11 === 'function') {{
                    window.togglePredicted11();
                }}
            }} else if (d.type === 'openReverseOdds') {{
                // Aug 30 2026 — 🔄 Reverse Odds header button in Match
                // mode delegates to this iframe via postMessage; open
                // the Reverse Odds modal inside whichever frame the
                // user works with.
                if (typeof window.toggleReverseOdds === 'function') {{
                    window.toggleReverseOdds();
                }}
            }} else if (d.type === 'setReverseOddsDim') {{
                // Aug 30 2026 — the parent dims the frame that hosts NO
                // modal, so BOTH frames read as "behind the modal".
                try {{
                    if (d.on) document.body.classList.add('ro-dim');
                    else document.body.classList.remove('ro-dim');
                }} catch (e) {{ /* noop */ }}
            }} else if (d.type === 'closeReverseOdds') {{
                // Aug 30 2026 — the user clicked anywhere in the OTHER
                // (dimmed) frame; close the modal here if it is open.
                var roHostX = document.getElementById('reverse-odds-host');
                if (roHostX && roHostX.style.display === 'flex' && typeof window.toggleReverseOdds === 'function') {{
                    window.toggleReverseOdds();
                }}
            }} else if (d.type === 'hidePredictedXI') {{
                // Aug 22 2026 — Match-mode parent renders a single
                // Predicted XI panel across both team tables. When
                // that panel opens, the parent posts this message to
                // every iframe so each iframe hides its own panel —
                // otherwise the same list would appear three times.
                try {{
                    var host = document.getElementById('predicted11-panel-host');
                    if (host && host.style.display !== 'none') {{
                        host.style.display = 'none';
                    }}
                    if (_p11CountdownTimer) {{
                        clearInterval(_p11CountdownTimer);
                        _p11CountdownTimer = null;
                    }}
                    var b = document.getElementById('btn-predicted-11');
                    if (b) b.classList.remove('active');
                }} catch (e) {{ /* noop */ }}
            }} else if (d.type === 'checkPredictedXI' && d.match_id) {{
                // Aug 22 2026 — 🔍 Check Predicted XI button (inside
                // Predicted XI panel). Same logic as applyPredictedXI
                // but we ack back to the sender with the number of
                // checkboxes ticked, so the row button can show
                // "✓ Checked N" feedback.
                var mid = d.match_id;
                _applyPredictedXIIframe(mid);
                // Count + ack after the async chain inside
                // _applyPredictedXIIframe settles. Re-query the DOM
                // a moment later — _applyPredictedXIIframe fires
                // fetch(/api/predicted_xi?refresh=1) and ticks boxes
                // inside its .then().
                // Aug 22 2026 — bumped from 2.5 s → 5 s. The parent panel's
                // aggregation logic uses the FIRST p11-checked-ack
                // to close out the row (it deletes _mp11Acks[mid]
                // and resets the label). With the old 2.5 s
                // timeout the ack often landed before
                // _applyPredictedXIIframe's fetch chain had a
                // chance to tick any boxes, so the parent saw
                // applied=0 → "🔒 0 checked — different team"
                // even when the second `p11-autopxi` ack a moment
                // later would have shown applied=10. Waiting 5 s
                // lets the XI tick complete first; the post is
                // still best-effort and the parent has its own
                // 8 s failsafe in case this iframe never ticks.
                setTimeout(function() {{
                    try {{
                        var cbCount = document.querySelectorAll('input.xi-checkbox:checked').length;
                        if (ev && ev.source && typeof ev.source.postMessage === 'function') {{
                            ev.source.postMessage({{
                                type: 'p11-checked-ack',
                                match_id: mid,
                                applied: cbCount
                            }}, '*');
                        }}
                    }} catch (e) {{}}
                }}, 5000);
            }}
        }} catch (e) {{ /* noop */ }}
    }});
    // Aug 22 2026 — Max asked the toolbar button to read
    // "🔼 Expand Details" by default. We honour an explicit cached
    // collapse preference (set by a prior click in this tab), but
    // when nothing is cached we now default to COLLAPSED so the
    // button label and the visible columns match on first paint.
    try {{
        var cached = sessionStorage.getItem(DETAILS_KEY);
        if (cached === '1') applyDetailHidden(true);
        else if (cached === null) applyDetailHidden(true);  // default = hidden
    }} catch (e) {{ /* noop */ }}

    // Aug 14 2026: Team-mode toolbar button. The header button mirrors the
    // sessionStorage-backed state — toggle, update the label, and re-apply.
    // Match-mode parent frames broadcast the same event on every iframe load,
    // so when this page is rendered as an iframe in Match Mode the parent's
    // state wins and overrides whatever we set here.
    var refreshDetailsBtn = function() {{
        var btn = document.getElementById('btn-collapse-details');
        if (!btn) return;
        var collapsed = (document.body.className || '').indexOf('detail-hidden') !== -1;
        btn.textContent = collapsed ? '🔼 Expand Details' : '🔽 Collapse Details';
        btn.setAttribute('title', collapsed
            ? 'Show MV, Squad Role and Impact Score columns'
            : 'Hide MV, Squad Role and Impact Score columns');
    }};
    window.toggleDetailsCollapsed = function() {{
        var collapsed = (document.body.className || '').indexOf('detail-hidden') !== -1;
        applyDetailHidden(!collapsed);
        refreshDetailsBtn();
    }};
    refreshDetailsBtn();
}})();
</script>

<!-- Sep 1 2026 — Travel analytics popover (🚌 button next to Stadium).
     NOT a full-screen overlay: a small anchored card near the button,
     so the away table stays visible and untouched. -->
<div id="travel-pop" style="display:none;position:absolute;z-index:10000;background:white;border:1px solid #d5d9e8;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,0.18);padding:12px 16px;min-width:230px;">
    <div id="travel-pop-header" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;gap:12px;">
        <div style="font-size:13px;font-weight:700;color:#333;">🚌 Travel Analytics</div>
        <button type="button" onclick="closeTravelPop()" style="background:transparent;border:none;font-size:15px;cursor:pointer;color:#888;line-height:1;padding:0 2px;">✕</button>
    </div>
    <div id="travel-pop-body" style="font-size:13px;color:#333;line-height:1.65;white-space:pre-line;">Loading…</div>
</div>
<script>
/* Sep 3 2026 — during Loading the card shows ONLY the word
   "Loading…" centered (header ✕ hidden); once data arrives the header
   ✕ and the analytics lines appear. */
function travelLoadingMode() {{
    var h = document.getElementById('travel-pop-header');
    var b = document.getElementById('travel-pop-body');
    var pop = document.getElementById('travel-pop');
    if (h) h.style.display = 'none';
    pop.style.display = 'flex';
    pop.style.alignItems = 'center';
    pop.style.justifyContent = 'center';
    b.style.fontSize = '15px';
    b.style.fontWeight = '700';
    b.textContent = 'Loading…';
}}
function travelDataMode() {{
    var h = document.getElementById('travel-pop-header');
    var b = document.getElementById('travel-pop-body');
    var pop = document.getElementById('travel-pop');
    if (h) h.style.display = 'flex';
    pop.style.display = 'block';
    pop.style.alignItems = '';
    pop.style.justifyContent = '';
    b.style.fontSize = '13px';
    b.style.fontWeight = '';
}}
function openTravelModal() {{
    var btn = document.getElementById('travel-btn');
    var pop = document.getElementById('travel-pop');
    var body = document.getElementById('travel-pop-body');
    // FULL block during Loading (Sep 2 2026): the whole card shows with
    // "⏳ Loading…" centered inside — NOT a thin strip. Fixed loading
    // size (240x130) so the user sees the full card immediately; once
    // the data arrives the card auto-sizes to the real content and is
    // repositioned above the button.
    var r = btn.getBoundingClientRect();
    var sx = window.scrollX || 0, sy = window.scrollY || 0;
    pop.style.width = '240px';
    pop.style.height = '130px';
    pop.style.left = (Math.max(4, r.right - 240) + sx) + 'px';
    // Anchor ABOVE the button during Loading: below the 🚌 there is no
    // room in the iframe (button sits near the bottom of the document),
    // so the 130px card was cut off by the iframe edge and the user saw
    // only a sliver of the border. Above the button is the table — full
    // block visible immediately.
    var topLoading = r.top - 130 - 10;  // 130 = loading card height
    if (topLoading < 4) topLoading = r.bottom + 10;
    pop.style.top = (topLoading + sy) + 'px';
    // ONLY the word "Loading…" centered in the card (header ✕ hidden)
    travelLoadingMode();
    fetch('/lineup_ai/api/travel?home_id={team_id}&away_id={_travel_opp}')
        .then(function(r) {{ return r.json(); }})
        .then(function(d) {{
            body.textContent = d.text || 'Stadium not found';
            // release the loading size — auto-size to the real content
            pop.style.width = '';
            pop.style.height = '';
            // header ✕ + analytics lines appear
            travelDataMode();
            // size known now — position above the button
            var pw = pop.offsetWidth, ph = pop.offsetHeight;
            var left = r.right - pw;
            if (left < 4) left = 4;
            var top = r.top - ph - 10;
            if (top < 4) top = r.bottom + 10;
            // document.body offsetParent: page scrolls, use absolute page coords
            pop.style.left = (left + sx) + 'px';
            pop.style.top = (top + sy) + 'px';
        }})
        .catch(function() {{
            body.textContent = 'Stadium not found';
            pop.style.width = '';
            pop.style.height = '';
            travelDataMode();
        }});
    // click-outside closes
    setTimeout(function() {{
        document.addEventListener('click', _travelOutsideHandler, {{ once: true }});
    }}, 0);
}}
function closeTravelPop() {{
    var pop = document.getElementById('travel-pop');
    if (pop) pop.style.display = 'none';
}}
function _travelOutsideHandler(e) {{
    // Clicks anywhere on the PAGE must close the popover — including
    // clicks in the parent Match page and in the sibling (home) iframe,
    // which never reach this iframe's document. Those are covered by
    // the window-blur listener + the explicit sibling-close below.
    _closeSiblingTravelPop();
    var pop = document.getElementById('travel-pop');
    var btn = document.getElementById('travel-btn');
    if (!pop || pop.style.display === 'none') return;
    if (pop.contains(e.target) || (btn && btn.contains(e.target))) return;
    closeTravelPop();
}}
function _closeSiblingTravelPop() {{
    try {{
        var w = window.parent;
        if (!w || w === window) return;
        var frames = w.document.querySelectorAll('iframe.team-frame');
        for (var i = 0; i < frames.length; i++) {{
            var win = frames[i].contentWindow;
            if (win && win !== window && win.closeTravelPop) win.closeTravelPop();
        }}
    }} catch (err) {{}}
}}
document.addEventListener('click', _travelOutsideHandler);
window.addEventListener('blur', function() {{
    // Focus moved outside this iframe (parent page or the other iframe)
    closeTravelPop();
}});
window.openTravelModal = openTravelModal;
</script>

</body>
</html>"""
    
    response = HTMLResponse(html)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
