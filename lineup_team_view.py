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
        'Georgia': 'ge', 'Germany': 'de', 'Ghana': 'gh', 'Greece': 'gr',
        'Grenada': 'gd', 'Guatemala': 'gt', 'Guinea': 'gn', 'Guinea-Bissau': 'gw',
        'Guyana': 'gy', 'Haiti': 'ht', 'Honduras': 'hn', 'Hungary': 'hu',
        'Iceland': 'is', 'India': 'in', 'Indonesia': 'id', 'Iran': 'ir',
        'Iraq': 'iq', 'Ireland': 'ie', 'Israel': 'il', 'Italy': 'it',
        'Ivory Coast': 'ci', "Côte d'Ivoire": 'ci', 'Jamaica': 'jm', 'Japan': 'jp',
        'Jordan': 'jo', 'Kazakhstan': 'kz', 'Kenya': 'ke', 'Kiribati': 'ki',
        'Kosovo': 'xk', 'Kuwait': 'kw', 'Kyrgyzstan': 'kg', 'Laos': 'la',
        'Latvia': 'lv', 'Lebanon': 'lb', 'Lesotho': 'ls', 'Liberia': 'lr',
        'Libya': 'ly', 'Liechtenstein': 'li', 'Lithuania': 'lt', 'Luxembourg': 'lu',
        'Madagascar': 'mg', 'Malawi': 'mw', 'Malaysia': 'my', 'Maldives': 'mv',
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
        'Saint Vincent and the Grenadines': 'vc', 'Samoa': 'ws', 'San Marino': 'sm',
        'Sao Tome and Principe': 'st', 'Saudi Arabia': 'sa', 'Senegal': 'sn',
        'Serbia': 'rs', 'Seychelles': 'sc', 'Sierra Leone': 'sl', 'Singapore': 'sg',
        'Slovakia': 'sk', 'Slovenia': 'si', 'Solomon Islands': 'sb', 'Somalia': 'so',
        'South Africa': 'za', 'South Korea': 'kr', 'South Sudan': 'ss', 'Spain': 'es',
        'Sri Lanka': 'lk', 'Sudan': 'sd', 'Suriname': 'sr', 'Sweden': 'se',
        'Switzerland': 'ch', 'Syria': 'sy', 'Taiwan': 'tw', 'Tajikistan': 'tj',
        'Tanzania': 'tz', 'Thailand': 'th', 'Togo': 'tg', 'Tonga': 'to',
        'Trinidad and Tobago': 'tt', 'Tunisia': 'tn', 'Turkey': 'tr',
        'Turkmenistan': 'tm', 'Tuvalu': 'tv', 'Uganda': 'ug', 'Ukraine': 'ua',
        'United Arab Emirates': 'ae', 'United Kingdom': 'gb', 'England': 'gb',
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
    """Return flag (club teams) or club badge (national teams)"""
    club = p.get("club", "")
    if club:
        club_logo = p.get("club_logo", "")
        if club_logo:
            return f'<span class="club-badge" data-tooltip="{club}"><img src="{club_logo}" alt="{club}" style="width:14px;height:14px;vertical-align:middle;"></span>'
        # No club_logo -- club might be a country name (club team)
        flag_html = get_flag_html(club)
        if flag_html != "–" and "flagcdn" in flag_html:
            return flag_html
        # Real club name without logo
        return f'<span class="club-badge" data-tooltip="{club}">{club[:3]}</span>'
    # Fallback: use national field
    national = p.get("national", "")
    if national and national != "–":
        flag_html = get_flag_html(national)
        if flag_html != "–" and "flagcdn" in flag_html:
            return flag_html
        # Club name in national field
        club_logo = p.get("club_logo", "")
        if club_logo:
            return f'<span class="club-badge" data-tooltip="{national}"><img src="{club_logo}" alt="{national}" style="width:14px;height:14px;vertical-align:middle;"></span>'
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


def render_team_view(team_id: str, embed: str = "") -> HTMLResponse:
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
        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{team_name_hint} - loading</title></head>
  <div style="max-width:760px;margin:60px auto;background:white;border-radius:14px;padding:28px;box-shadow:0 2px 12px rgba(0,0,0,.08);">
    <h2 style="margin-top:0;color:#333;">{team_name_hint}</h2>
    <p style="color:#666;line-height:1.5;">Team data has not been loaded yet</p>
    <a href="/lineup_ai/select" style="display:inline-block;text-decoration:none;border:0;border-radius:8px;background:#667eea;color:white;font-weight:700;padding:10px 16px;cursor:pointer;">← Back to teams</a>
  </div>

        

</body></html>"""
        return HTMLResponse(html)
    
    try:
        with open(team_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return HTMLResponse(f"Error loading team data: {e}", status_code=500)
    
    team_name = data.get("team", {}).get("name", "Unknown")
    team_emblem = data.get("team", {}).get("emblem", "")
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
    
    stadium_name = data.get("stadium", "") or data.get("team", {}).get("stadium", "")
    stadium_city = data.get("team", {}).get("city", "")
    if stadium_name and stadium_city:
        stadium_display = f"{stadium_name} ({stadium_city})"
    elif stadium_name:
        stadium_display = stadium_name
    elif stadium_city:
        stadium_display = f"({stadium_city})"
    else:
        stadium_display = "–"
    
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

        player_display_name = swap_name_order(p.get("name", "–"))
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

    # Missing player emoji by reason
    def _missing_emoji(reason):
        r = (reason or "").lower()
        if any(kw in r for kw in ['red card']):
            return '🟥', '#dc3545'
        elif any(kw in r for kw in ['yellow card']):
            return '🟨', '#ffc107'
        elif any(kw in r for kw in ['loan']):
            return '📄', '#6c757d'
        elif any(kw in r for kw in ['international', 'duty']):
            return '🛫', '#0d6efd'
        else:  # injury, illness, broken, etc
            return '❌', '#dc3545'

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
            if val == "START":
                if is_capt:
                    cells += '<td style="text-align:center;vertical-align:middle;"><div style="width:20px;height:20px;border-radius:50%;background:#17843f;display:inline-flex;vertical-align:middle;align-items:center;justify-content:center;" title="Captain"><span style="color:white;font-size:12px;line-height:1;">✓</span></div></td>'
                else:
                    cells += '<td style="text-align:center;vertical-align:middle;"><div style="width:20px;height:20px;border-radius:50%;background:#17843f;display:inline-block;vertical-align:middle;"></div></td>'
            elif val == "SUB":
                cells += '<td style="text-align:center;vertical-align:middle;"><div style="width:20px;height:20px;border-radius:50%;background:#e3a035;display:inline-block;vertical-align:middle;"></div></td>'
            elif miss:
                emoji, color = _missing_emoji(miss)
                cells += f'<td style="text-align:center;vertical-align:middle;" title="{miss}"><span style="font-size:14px;cursor:help;">{emoji}</span></td>'
            else:
                cells += '<td style="text-align:center;vertical-align:middle;"></td>'
        return cells

    players_rows = ""
    for p in sorted_players:
        last3 = p.get("last3", [])
        last_start = "START" if (last3 and len(last3) > 0 and last3[0] == "START") else ""
        player_display_name = swap_name_order(p.get("name", "–"))
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
                <td class="status-cell"><div class="status-wrapper"><span class="status-emoji-display">✅</span><span class="status-chevron">▼</span><select class="status-select" onchange="updateStatusIcon(this)"><option value="Available">✅ Available</option><option value="Doubt">❓ Doubt</option><option value="Injury">❌ Injury</option><option value="Red card">🟥 Red card</option><option value="Yellow red card">🟥 Yellow/red card</option><option value="Last Yellow card">🟨 Last yellow card</option><option value="Not playing (Called up)">✈️ Not playing (Called up)</option><option value="Not playing (Other)">🚫 Not playing (Other)</option><option value="Return (Injury)">🔙 Return (Injury)</option><option value="Return (Susp)">🔙 Return (Susp)</option><option value="Return (Called up)">🔙 Return (Called up)</option><option value="Return (Other)">🔙 Return (Other)</option><option value="New player">🆕 New player</option><option value="Left the team">🚪 Left the team</option></select></div></td>
                <td style="text-align:center;padding:4px 2px;">{p.get("age", "–")}</td>
                <td style="text-align:center;">{p.get("market_value", "–")}</td>
                <td class="pos-{p.get("position", "").lower()}" style="color:#000;font-weight:400;text-align:center;padding:4px 2px;">{p.get("position", "–")}</td>
                <td style="text-align:center;"><span class="squad-role {p.get('squad_role', '').lower()}">{p.get("squad_role", "–") if p.get("squad_role") else "–"}</span></td>
                <td style="text-align:center;">{p.get("impact_score", "–") if p.get("impact_score") is not None else "–"}</td>
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
        home_t = m.get("home_team", "")
        away_t = m.get("away_team", "")
        score_str = m.get("score", "")

        # Tooltip: full tournament name + teams + score
        if home_t and away_t:
            tooltip_text = f"{comp_full}\n{home_t} {score_str} {away_t}"
        else:
            tooltip_text = f"{comp_full}: {score_str}" if score_str else comp_full
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
        body.embed-mode .team-nav-sidebar {{ display: none !important; }}
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
        .bulk-lineup-controls textarea {{
            flex: 1;
            min-height: 58px;
            border: 1px solid #d5d9e8;
            border-radius: 8px;
            padding: 8px 10px;
            resize: vertical;
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
        /* Auto-width override for the renamed action buttons (Scan, Upload Image, Run AI).
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
            white-space: nowrap;
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




<script src="/icons/status-icons.js?v=3"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script src="/static/favorites.js?v=7"></script>

</head>
<body class="{('embed-mode' if embed else '')}">
    <div class="header">
        <!-- Left utility buttons: My Favorites + Screenshot -->
        <div style="display:flex;align-items:center;gap:8px;margin-right:auto;">
            <a href="/lineup_ai/favorites" class="header-action-btn"><span>💎</span> My Favorites</a>
            <button type="button" class="header-action-btn" onclick="exportScreenshot()" id="btn-export">📸 Screenshot</button>
        </div>
        <!-- Right action buttons: lineups toggles + back -->
        <div style="display:flex;align-items:center;gap:8px;">
            <button type="button" id="btn-add-lineups" class="header-action-btn" onclick="toggleSection('bulk-lineup-panel-host', this, ['comparison-table-host'])" title="Add Lineups + Compare (both panels together)">👥 Add Lineups</button>
            <button type="button" id="btn-builder" class="header-action-btn" onclick="toggleSection('builder-lineup-host', this)">🧩 Build Lineup</button>
            <button type="button" id="btn-faq" class="header-action-btn" onclick="toggleFaq()">❓ FAQ</button>
            <a href="/lineup_ai/select" class="header-action-btn">← Back to teams</a>
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
        <div id="nav-match-group" style="display:none;">
            <label for="nav-match" id="nav-match-label">Match</label>
            <div class="select-wrapper">
                <select id="nav-match" onchange="onNavMatchChange()" disabled>
                    <option value="">-- Select Match --</option>
                </select>
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
            <button type="button" class="action-btn update-btn" id="update-data-btn" onclick="updateData()" title="Fetch latest data from Soccerway">♻️ Update data</button>
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
            <span style="font-size:12px;margin-left:6px;position:relative;display:inline-block;" onmouseenter="showTooltip(this)" onmouseleave="hideTooltip(this)"><span style="font-weight:600;color:#dc3545;">Starting XI</span> 🆚 <span style="font-weight:600;color:#667eea;">Possible XI</span><span class="tooltip-delay" style="visibility:hidden;opacity:0;transition:opacity 0.3s;position:fixed;background:#333;color:#fff;padding:6px 10px;border-radius:6px;font-size:11px;font-weight:500;white-space:nowrap;z-index:9999;pointer-events:none;">&gt;8% = possible odds move</span></span>
        </div>
        <div style="background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:10px 12px;display:flex;align-items:center;justify-content:flex-start;min-height:42px;">
            <span id="cmp-sxi-pct-impact" style="font-size:15px;font-weight:600;">–</span>
            <span style="font-size:12px;margin-left:6px;"><span style="font-weight:600;color:#dc3545;">Starting XI</span> 🆚 <span style="font-weight:600;color:#000;">Last Match</span></span>
        </div>
        <div style="background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:10px 12px;display:flex;align-items:center;justify-content:flex-start;min-height:42px;">
            <span id="cmp-pxi-pct-impact" style="font-size:15px;font-weight:600;">–</span>
            <span style="font-size:12px;margin-left:6px;"><span style="font-weight:600;color:#667eea;">Possible XI</span> 🆚 <span style="font-weight:600;color:#000;">Last Match</span></span>
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
<div id="bulk-lineup-panel-host" style="display:none;margin-bottom:12px;">
            <div class="bulk-lineup-panel">
            <div class="bulk-lineup-controls">
                <div class="bulk-lineup-row">
                    <select id="bulk-lineup-mode" aria-label="Bulk lineup mode">
                        <option value="possible">🔵 P-XI</option>
                        <option value="start">🔴 S-XI</option>
                        <option value="squad">⚫️ List (all found)</option>
                    </select>
                    <button type="button" class="bl-action-btn" onclick="applyBulkLineup()">Scan</button>
                    <div class="vision-lineup-row" style="margin-left:auto;">
                        <input type="file" id="vision-lineup-image" accept="image/*" aria-label="Vision lineup image" style="display:none;">
                        <button type="button" class="vision-lineup-btn bl-action-btn" onclick="document.getElementById('vision-lineup-image').click()">Upload Image</button>
                        <span id="vision-file-name" class="vision-lineup-status">💤</span>
                        <button type="button" class="vision-lineup-btn bl-action-btn" onclick="applyVisionLineup()">Run AI</button>
                        <span id="vision-lineup-status" class="vision-lineup-status"></span>
                    </div>
                </div>
                <div class="bulk-lineup-text-row" style="display:flex;gap:8px;align-items:flex-start;margin-top:8px;">
                    <textarea id="bulk-lineup-text" placeholder="Paste players" style="flex:1;min-height:60px;resize:vertical;"></textarea>
                    <div id="vision-lineup-stats" class="vision-lineup-stats" style="display:none;min-width:120px;font-size:12px;color:#555;line-height:1.6;">
                        <div>Total: <span id="vision-total-count">0</span> players</div>
                        <div style="color:#17843f;">Found: <span id="vision-found-count">0</span> players</div>
                        <div style="color:#dc3545;">Not found: <span id="vision-notfound-count">0</span> players</div>
                    </div>
                </div>
            </div>
            <div id="bulk-lineup-report" class="bulk-lineup-report"></div>
            <div id="bulk-lineup-ambiguous" class="bulk-ambiguous" style="display:none;"></div>
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
                        <select id="squad-mode-select" onchange="onSquadModeChange(this.value)" style="padding:6px 12px;border:1px solid rgba(255,255,255,0.4);border-radius:6px;font-size:14px;background:rgba(255,255,255,0.15);color:white;cursor:pointer;font-weight:600;">
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
                        <th rowspan="2" style="text-align:center;width:70px;padding:0;">Status</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">Age</th>
                        <th rowspan="2" style="text-align:center;width:60px;padding:0;" title="Market Value">MV</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">Pos</th>
                        <th rowspan="2" style="text-align:center;width:60px;padding:0;font-size:11px;">Squad<br>Role</th>
                        <th rowspan="2" style="text-align:center;width:40px;padding:0;font-size:11px;" title="Impact Score">IS</th>
                        <th rowspan="2" style="text-align:center;width:37px;padding:0;font-size:10px;vertical-align:top;"><div style="display:flex;flex-direction:column;align-items:center;height:100%;"><button onclick="clearColumn('squad');return false;" style="background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin:0;" title="Clear List">✖️</button><span title="Squad List" style="font-size:10px;margin-top:2px;">List</span></div></th>
                        <th rowspan="2" style="text-align:center;width:37px;padding:0;font-size:10px;vertical-align:top;"><div style="display:flex;flex-direction:column;align-items:center;height:100%;"><button onclick="clearColumn('possible');return false;" style="background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin:0;" title="Clear P-XI">✖️</button><span title="Possible XI" style="font-size:10px;margin-top:2px;">P-XI</span><span id="xi-counter" style="color:#667eea;font-size:9px;">0/11</span></div></th>
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
                <!-- Coach (left) + Stadium (right) below main table, auto-width, aligned to table edges -->
                <div id="coach-stadium-bar" style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;gap:10px;">
                    <div style="display:inline-block;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;"><span style="color:#667eea;font-weight:600;">Coach:</span> {coach_name_display}</div>
                    <div style="display:inline-block;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;"><span style="color:#667eea;font-weight:600;">Stadium:</span> {stadium_display}</div>
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
        function toggleFaq() {{
            var host = document.getElementById('faq-host');
            if (!host) return;
            var isVisible = host.style.display === 'flex';
            host.style.display = isVisible ? 'none' : 'flex';
        }}
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                var host = document.getElementById('faq-host');
                if (host && host.style.display === 'flex') host.style.display = 'none';
            }}
        }});
        document.addEventListener('click', function(e) {{
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
        const DOUBTFUL_STATUSES = ['Doubt'];
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
            const msgEl = document.getElementById('save-message');
            if (!btn || btn.disabled) return;
            btn.disabled = true;
            btn.innerHTML = '⏳ Updating...';
            const startTime = Date.now();
            
            // Запускаем счётчик вверх
            let seconds = 0;
            const counterInterval = setInterval(() => {{
                seconds++;
                if (msgEl) {{ msgEl.textContent = '🔄 ' + seconds + 's'; msgEl.style.color = '#667eea'; }}
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
                if (msgEl) {{ msgEl.textContent = msg; msgEl.style.color = '#17843f'; }}
                btn.innerHTML = '♻️ Update data';
                btn.disabled = false;
                
                // Reload page immediately with cache-bust
                const url = location.pathname + '?_v=' + Date.now();
                window.location.href = url;
            }} catch (e) {{
                clearInterval(counterInterval);
                console.error('[UpdateData] error:', e);
                if (msgEl) {{ msgEl.textContent = '❌ ' + (e.message || 'Error'); msgEl.style.color = '#dc3545'; }}
                btn.disabled = false;
                btn.innerHTML = '♻️ Update data';
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
                .split(/[,;\\n\\r]+|\s+-\s+/g)
                .map(x => x.trim())
                .filter(Boolean);
        }}

        function bulkParseToken(token) {{
            const nums = String(token || '').match(/\b\d+\b/g) || [];
            const number = nums.length ? nums[nums.length - 1] : '';
            const name = String(token || '').replace(/\b\d+\b/g, ' ').replace(/\s+/g, ' ').trim();
            const norm = bulkNormalizeText(name || token);
            return {{ raw: token, number: number, name: name, norm: norm, parts: bulkNameParts(name || token) }};
        }}

        function bulkRowsIndex() {{
            return Array.from(document.querySelectorAll('.main-table tbody tr[data-player-name]')).map(row => {{
                const rawName = row.getAttribute('data-player-name') || '';
                const cells = row.querySelectorAll('td');
                const displayName = cells[2] ? cells[2].textContent.replace(/[🎯🎨⭐👑⚽👟️]/g, ' ').replace(/\s+/g, ' ').trim() : rawName;
                const number = String(row.getAttribute('data-player-number') || (cells[0] ? cells[0].textContent : '') || '').trim();
                const norm = bulkNormalizeText(rawName + ' ' + displayName);
                const parts = bulkNameParts(rawName + ' ' + displayName);
                const rawParts = bulkNameParts(rawName);
                const firstName = rawParts[0] || '';
                const lastName = rawParts.length ? rawParts[rawParts.length - 1] : '';
                const fullName = bulkNormalizeText(rawName);
                const fullNameReversed = rawParts.length > 1 ? rawParts.slice().reverse().join(' ') : fullName;
                return {{ row: row, rawName: rawName, displayName: displayName.trim(), number: number, norm: norm, parts: parts, firstName: firstName, lastName: lastName, fullName: fullName, fullNameReversed: fullNameReversed }};
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

        function bulkRenderReport(total, found, notFound, ambiguous) {{
            const el = document.getElementById('bulk-lineup-report');
            if (!el) return;
            let html = '';
            if (ambiguous && ambiguous.length) html += '\\nAmbiguous: ' + ambiguous.length + ' — choose below';
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
                '<div class="bulk-ambiguous-row"><label>' + item.parsed.raw + '</label><select data-bulk-amb-idx="' + idx + '">' +
                '<option value="">Skip</option>' + item.matches.map((m, mi) => '<option value="' + mi + '">#' + (m.number || '–') + ' ' + m.rawName + '</option>').join('') +
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
                if (matches.length === 1) {{
                    bulkMarkRow(matches[0].row, mode);
                    found++;
                }} else if (matches.length > 1) {{
                    ambiguous.push({{ parsed: parsed, matches: matches }});
                }} else {{
                    notFound.push(parsed);
                }}
            }});
            bulkRefreshStats();
            bulkRenderReport(tokens.length, found, notFound, ambiguous);
            bulkRenderAmbiguous(ambiguous, mode);
            return {{ total: tokens.length, found: found, notFound: notFound.length, ambiguous: ambiguous.length }};
        }}

        function applyBulkLineup() {{
            const textEl = document.getElementById('bulk-lineup-text');
            const modeEl = document.getElementById('bulk-lineup-mode');
            const tokens = bulkParseInput(textEl ? textEl.value : '');
            const mode = modeEl ? modeEl.value : 'possible';
            applyBulkLineupFromTokens(tokens, mode);
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

        async function applyVisionLineup() {{
            const fileEl = document.getElementById('vision-lineup-image');
            const textEl = document.getElementById('bulk-lineup-text');
            const modeEl = document.getElementById('bulk-lineup-mode');
            const statusEl = document.getElementById('vision-lineup-status');
            const file = fileEl && fileEl.files && fileEl.files[0];
            if (!file) {{ if (statusEl) {{ statusEl.style.color = '#dc3545'; statusEl.textContent = 'Upload Image'; }} return; }}
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
                if (textEl) textEl.value = names.join('\\n');
                const currentMode2 = modeEl ? modeEl.value : 'possible';
                const result = applyBulkLineupFromTokens(names, currentMode2);
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

        // === Background live-data sync: disabled in embed mode ===
        var IS_EMBED = window.location.search.indexOf('embed=1') !== -1;
        if (!IS_EMBED) {{
            (function() {{
                // Check if cache is stale (> 6 hours) and auto-update
                if (CACHE_AGE_SECONDS !== null && CACHE_AGE_SECONDS > CACHE_TTL_SECONDS) {{
                    console.log('[AutoUpdate] Cache is stale (' + Math.round(CACHE_AGE_SECONDS/3600) + 'h), updating...');
                    var teamId = window.location.pathname.split('/').pop();
                    var btn = document.getElementById('update-data-btn');
                    var msgEl = document.getElementById('save-message');
                    
                    // Show updating indicator
                    if (btn) {{
                        btn.disabled = true;
                        btn.innerHTML = '⏳ Auto-updating...';
                    }}
                    let seconds = 0;
                    const counterInterval = setInterval(function() {{
                        seconds++;
                        if (msgEl) {{ msgEl.textContent = '🔄 ' + seconds + 's'; msgEl.style.color = '#667eea'; }}
                    }}, 1000);
                    
                    fetch('/lineup_ai/api/fetch/' + teamId + '?_t=' + Date.now(), {{ cache: 'no-store' }})
                        .then(function(r) {{ return r.json(); }})
                        .then(function(data) {{
                            clearInterval(counterInterval);
                            const duration = Math.round(CACHE_AGE_SECONDS / 3600);
                            const msg = data.changed 
                                ? '✅ Auto-updated (was ' + duration + 'h old)'
                                : '✓ Refreshed (was ' + duration + 'h old)';
                            if (msgEl) {{ msgEl.textContent = msg; msgEl.style.color = '#17843f'; }}
                            if (btn) {{ btn.innerHTML = '♻️ Update data'; btn.disabled = false; }}
                            // No reload: auto-update already saved fresh cache.
                            // Reloading would re-trigger the auto-update and create a reload loop.
                        }})
                        .catch(function(err) {{
                            clearInterval(counterInterval);
                            console.log('[AutoUpdate] Failed:', err);
                            if (msgEl) {{ msgEl.textContent = '⚠️ Update failed'; msgEl.style.color = '#dc3545'; }}
                            if (btn) {{ btn.innerHTML = '♻️ Update data'; btn.disabled = false; }}
                        }});
                }} else {{
                    // Cache is fresh, no auto-update needed. Background sync disabled
                    // to avoid reload loops when other users update the cache.
                }}
            }})();
        }}

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
                // Move the country list to <body> so it escapes any parent stacking context
                if (countryList && countryList.parentElement !== document.body) {{
                    document.body.appendChild(countryList);
                }}
                const countries = Object.keys(navData).sort();
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
                    // Visible list item with flag
                    const li = document.createElement('li');
                    li.setAttribute('data-value', country);
                    li.setAttribute('role', 'option');
                    li.innerHTML = '<span>' + country + '</span>';
                    li.onclick = function() {{
                        selectCountry(country);
                    }};
                    countryList.appendChild(li);
                }});
                // Auto-select current country based on team_id.
                // Prefer the first championship in navData (top-tier league) over mirror copies
                // like Albania Cup / Super Cup that also contain this team.
                let foundCountry = null;
                for (const [country, leagues] of Object.entries(navData)) {{
                    const firstChamp = Object.keys(leagues)[0];
                    if (firstChamp && leagues[firstChamp].some(t => t.id === CURRENT_TEAM_ID)) {{
                        foundCountry = country;
                        break;
                    }}
                }}
                if (foundCountry) {{
                    selectCountry(foundCountry);
                }}
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
                if (matchGroup) matchGroup.style.display = 'none';
                if (matchActions) matchActions.style.display = 'none';

                if (!country || !navData[country]) {{
                    championshipSelect.disabled = true;
                    return;
                }}

                const championships = Object.keys(navData[country]).sort();
                // Prefer the first championship in the iteration order (which follows navData
                // insertion order from leagues_data.json) — that's the top-tier league.
                // The old code picked the last sorted one, which often landed on Super Cup
                // / Country Cup mirror copies of the same team.
                const iterationOrder = Object.keys(navData[country]);
                let currentChamp = null;
                for (const ch of iterationOrder) {{
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
                if (matchGroup) matchGroup.style.display = 'none';
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
                    if (matchGroup) matchGroup.style.display = 'none';
                    if (matchActions) matchActions.style.display = 'none';
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
                        opt.textContent = f.date + '  ' + f.home + ' - ' + f.away;
                        matchSelect.appendChild(opt);
                    }});
                    matchSelect.disabled = false;
                }} catch (e) {{
                    console.error('Failed to load fixtures:', e);
                    matchSelect.innerHTML = '<option value="">Failed to load</option>';
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
    <!-- FAQ Modal -->
    <div id="faq-host" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);z-index:99999;justify-content:center;align-items:flex-start;padding:40px 20px;overflow-y:auto;box-sizing:border-box;">
        <div style="background:white;border-radius:12px;max-width:780px;width:100%;padding:24px 28px;box-shadow:0 10px 40px rgba(0,0,0,0.25);position:relative;">
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
                <p style="margin:4px 0;">Yes! You can compare:<br>Starting XI 🆚 Possible XI — See how the predicted lineup stacks up against the actual lineup (Δ8% = possible odds move).<br>Starting XI 🆚 Last Match — Compare starting lineup with the previous game.<br>Possible XI 🆚 Last Match — Evaluate the predicted lineup with the previous game.</p>

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
</body>
</html>"""
    
    response = HTMLResponse(html)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
