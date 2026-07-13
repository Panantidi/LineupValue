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
    stadium_display = stadium_name if stadium_name else "–"
    
    # Calculate stats
    squad_size = len(players)
    total_age = sum(int(p.get("age", 0)) for p in players if p.get("age", "").isdigit())
    avg_age = round(total_age / squad_size, 1) if squad_size > 0 else 0
    total_apps = sum(int(p.get("apps", 0)) for p in players if p.get("apps", "").isdigit())
    total_goals = sum(int(p.get("goal", 0)) for p in players if p.get("goal", "").isdigit())
    total_assists = sum(int(p.get("assist", 0)) for p in players if p.get("assist", "").isdigit())
    total_yellow = sum(int(p.get("yellow_card", 0)) for p in players if p.get("yellow_card", "").isdigit())
    total_red = sum(int(p.get("red_card", 0)) for p in players if p.get("red_card", "").isdigit())
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
                <td class="player-name" style="white-space:nowrap;">{f"<strong>{player_display_name}{df_fire}{mf_lightning}{star_impact}{top_impact}{top_scorer_badge}</strong>" if unique_goal_leader and player_display_name == unique_goal_leader else (f"<strong>{player_display_name}{df_fire}{mf_lightning}{star_impact}{top_impact}{top_assist_badge}</strong>" if unique_assist_leader and player_display_name == unique_assist_leader else f"{player_display_name}{df_fire}{mf_lightning}{star_impact}{top_impact}")}</td>
                <td class="status-cell"><div class="status-wrapper"><span class="status-emoji-display">✅</span><span class="status-chevron">▼</span><select class="status-select" onchange="updateStatusIcon(this)"><option value="Available">✅ Available</option><option value="Doubt">❓ Doubt</option><option value="Injury">❌ Injury</option><option value="Red card">🟥 Red card</option><option value="Yellow red card">🟥 Yellow/red card</option><option value="Last Yellow card">🟨 Last Yellow card</option><option value="Not playing (Called up)">✈️ Not playing (Called up)</option><option value="Not playing (Other)">🚫 Not playing (Other)</option><option value="Return (Injury)">🔙 Return (Injury)</option><option value="Return (Susp)">🔙 Return (Susp)</option><option value="Return (Called up)">🔙 Return (Called up)</option><option value="Return (Other)">🔙 Return (Other)</option><option value="New player">🆕 New player</option><option value="Left the team">🚪 Left the team</option></select></div></td>
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
        date_str = m.get("date", "")
        comp_str = m.get("comp", "") or m.get("tournament", "")
        score_str = m.get("score", "")
        full_comp = _full_comp_name(comp_str)
        tooltip_text = f"{full_comp}: {score_str}" if score_str else full_comp
        tooltip_html = html_lib.escape(tooltip_text, quote=True)
        
        # Determine match result color for selected team
        bg_color = ""
        if score_str:
            # Parse score: "Team1 1-0 Team2" or "ABR1 1-1 ABR2"
            score_match = re.match(r'(.+?)\s+(\d+)\s*-\s*(\d+)\s+(.+)', score_str)
            if score_match:
                team1_name = score_match.group(1).strip()
                goals1 = int(score_match.group(2))
                goals2 = int(score_match.group(3))
                team2_name = score_match.group(4).strip()
                
                # Check if our team is team1 or team2
                team_name_lower = team_name.lower()
                is_team1 = team_name_lower in team1_name.lower() or team1_name.lower() in team_name_lower
                is_team2 = team_name_lower in team2_name.lower() or team2_name.lower() in team_name_lower
                
                if is_team1 and not is_team2:
                    # Our team is HOME (team1)
                    if goals1 > goals2:
                        bg_color = "background:#d4edda;"  # Win - green
                    elif goals1 < goals2:
                        bg_color = "background:#f8d7da;"  # Loss - red
                    else:
                        bg_color = "background:#fff3cd;"  # Draw - orange
                elif is_team2 and not is_team1:
                    # Our team is AWAY (team2)
                    if goals2 > goals1:
                        bg_color = "background:#d4edda;"  # Win - green
                    elif goals2 < goals1:
                        bg_color = "background:#f8d7da;"  # Loss - red
                    else:
                        bg_color = "background:#fff3cd;"  # Draw - orange
        
        last3_header_cells += f'<th class="last3-tooltip" style="text-align:center;font-size:10px;padding:2px 2px;line-height:1.2;white-space:nowrap;border-top:none;cursor:default;width:37px;{bg_color}" data-tooltip="{tooltip_html}">{date_str}<br><span style="font-weight:400;color:#888;">{comp_str}</span></th>'
    
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
            overflow-x: auto;
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
        .hide-watermark .table-container {{
            overflow-y: hidden;
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
            width: 240px;
            flex-shrink: 0;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            padding: 12px;
            z-index: 50;
            font-size: 13px;
            position: sticky;
            top: 16px;
            max-height: calc(100vh - 32px);
            overflow-y: auto;
        }}
        .page-main {{
            flex: 1;
            min-width: 0;
        }}

        .team-nav-sidebar select {{
            width: 100%;
            padding: 6px 8px;
            border: 1px solid #d5d9e8;
            border-radius: 6px;
            font-size: 13px;
            margin-bottom: 8px;
            background: #f8f9fc;
            color: #333;
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
        .my-squads-sidebar {{
            width: 240px;
            flex-shrink: 0;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            padding: 12px;
            font-size: 13px;
            position: sticky;
            top: 16px;
            max-height: calc(100vh - 32px);
            overflow-y: auto;
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
<script src="/static/favorites.js?v=5"></script>

</head>
<body class="{('embed-mode' if embed else '')}">
    <div class="header">
        <div style="display:flex;align-items:center;gap:8px;margin-left:auto;">
            <button type="button" id="btn-add-lineups" class="header-action-btn" onclick="toggleSection('bulk-lineup-panel-host', this)">👥 Add Lineups</button>
            <button type="button" id="btn-compare-lineups" class="header-action-btn" onclick="toggleSection('comparison-table-host', this)">⚖️ Compare Lineups</button>
            <button type="button" id="btn-squad-overview" class="header-action-btn" onclick="toggleSection('info-bar-squad-host', this)">📊 Squad Overview</button>
            <button type="button" class="header-action-btn" onclick="exportScreenshot()" id="btn-export">📸 Screenshot</button>
            <a href="/lineup_ai/select">← Back to teams</a>
            <a href="/lineup_ai/favorites" style="background:#28a745;color:white;padding:6px 12px;border-radius:6px;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:4px;"><span>💎</span> My Favorites</a>
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

        <label for="nav-country">Country</label>
        <select id="nav-country" onchange="onNavCountryChange()">
            <option value="">-- Select Country --</option>
        </select>
        <label for="nav-championship">Championship</label>
        <select id="nav-championship" onchange="onNavChampionshipChange()" disabled>
            <option value="">-- Select Championship --</option>
        </select>
        <label for="nav-team">Team</label>
        <select id="nav-team" onchange="onNavTeamChange()" disabled>
            <option value="">-- Select Team --</option>
        </select>
        <div id="nav-match-group" style="display:none;">
            <label for="nav-match" id="nav-match-label">Match</label>
            <select id="nav-match" onchange="onNavMatchChange()" disabled>
                <option value="">-- Select Match --</option>
            </select>
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
            <span style="font-weight:600;color:#333;font-size:12px;margin-left:6px;position:relative;display:inline-block;" onmouseenter="showTooltip(this)" onmouseleave="hideTooltip(this)">Starting XI 🆚 Possible XI<span class="tooltip-delay" style="visibility:hidden;opacity:0;transition:opacity 0.3s;position:fixed;background:#333;color:#fff;padding:6px 10px;border-radius:6px;font-size:11px;font-weight:500;white-space:nowrap;z-index:9999;pointer-events:none;">&gt;8% = possible odds move</span></span>
        </div>
        <div style="background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:10px 12px;display:flex;align-items:center;justify-content:flex-start;min-height:42px;">
            <span id="cmp-sxi-pct-impact" style="font-size:15px;font-weight:600;">–</span>
            <span style="font-weight:600;color:#dc3545;font-size:12px;margin-left:6px;">Starting XI 🆚 Last Match XI</span>
        </div>
        <div style="background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:10px 12px;display:flex;align-items:center;justify-content:flex-start;min-height:42px;">
            <span id="cmp-pxi-pct-impact" style="font-size:15px;font-weight:600;">–</span>
            <span style="font-weight:600;color:#667eea;font-size:12px;margin-left:6px;">Possible XI 🆚 Last Match XI</span>
        </div>
    </div>
    </div>

    <!-- Info Bar Squad Overview (toggled by header button, appears below my-squads-sidebar) -->
    <div id="info-bar-squad-host" style="display:none;">
<div id="info-bar-squad" style="display:flex;flex-direction:column;gap:12px;">
            <div style="background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;">
                <div style="text-align:center;font-weight:bold;color:#667eea;font-size:11px;margin-bottom:6px;white-space:nowrap;">Total Value</div>
                <div style="font-weight:normal;color:#333;font-size:20px;text-align:center;">{total_value_display}</div>
            </div>
            <div style="background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;">
                <div style="text-align:center;font-weight:bold;color:#667eea;font-size:11px;margin-bottom:4px;white-space:nowrap;">Avg Age</div>
                <div style="font-weight:normal;color:#333;font-size:20px;text-align:center;">{avg_age}</div>
            </div>
            <div style="background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;">
                <div style="text-align:center;font-weight:bold;color:#667eea;font-size:11px;margin-bottom:4px;white-space:nowrap;">Players</div>
                <div style="font-weight:normal;color:#333;font-size:20px;text-align:center;">{squad_size}</div>
            </div>
            <div style="background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;">
                <div style="text-align:center;font-weight:bold;color:#667eea;font-size:11px;margin-bottom:6px;white-space:nowrap;">Pos.Overview</div>
                {positional_overview_html}
            </div>
            <div style="background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;">
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
                    <button type="button" onclick="applyBulkLineup()">Apply</button>
                    <div class="vision-lineup-row" style="margin-left:auto;">
                        <input type="file" id="vision-lineup-image" accept="image/*" aria-label="Vision lineup image" style="display:none;">
                        <button type="button" class="vision-lineup-btn" onclick="document.getElementById('vision-lineup-image').click()">Upload Image</button>
                        <span id="vision-file-name" class="vision-lineup-status">File not selected</span>
                        <button type="button" class="vision-lineup-btn" onclick="applyVisionLineup()">🤖 AI Vision</button>
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

        <!-- Missing Players Stats (hidden by default) -->
        <div id="info-bar-missing" style="display:none;gap:12px;margin-bottom:12px;">
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-impact">0.00</span><br><span style="color:#888;font-size:11px;">IS</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;"><span id="missing-goals">0</span><span style="font-size:14px;color:#999;"> / <span id="missing-goals-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;"><span id="missing-assists">0</span><span style="font-size:14px;color:#999;"> / <span id="missing-assists-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
        </div>

        <!-- Doubtful Players Stats (hidden by default) -->
        <div id="info-bar-doubtful" style="display:none;gap:12px;margin-bottom:12px;">
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-impact">0.00</span><br><span style="color:#888;font-size:11px;">IS</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;"><span id="doubtful-goals">0</span><span style="font-size:14px;color:#999;"> / <span id="doubtful-goals-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;"><span id="doubtful-assists">0</span><span style="font-size:14px;color:#999;"> / <span id="doubtful-assists-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
        </div>

        <!-- Returning Players Stats (hidden by default) -->
        <div id="info-bar-returning" style="display:none;gap:12px;margin-bottom:12px;">
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-impact">0.00</span><br><span style="color:#888;font-size:11px;">IS</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;"><span id="returning-goals">0</span><span style="font-size:14px;color:#999;"> / <span id="returning-goals-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;"><span id="returning-assists">0</span><span style="font-size:14px;color:#999;"> / <span id="returning-assists-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
        </div>



        <!-- Transfer In Stats (hidden by default) -->
        <div id="info-bar-transfer-in" style="display:none;gap:12px;margin-bottom:12px;">
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="transfer-in-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="transfer-in-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="transfer-in-impact">0.00</span><br><span style="color:#888;font-size:11px;">IS</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;"><span id="transfer-in-goals">0</span><span style="font-size:14px;color:#999;"> / <span id="transfer-in-goals-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;"><span id="transfer-in-assists">0</span><span style="font-size:14px;color:#999;"> / <span id="transfer-in-assists-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
        </div>

        <!-- Transfer Out Stats (hidden by default) -->
        <div id="info-bar-transfer-out" style="display:none;gap:12px;margin-bottom:12px;">
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="transfer-out-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="transfer-out-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="transfer-out-impact">0.00</span><br><span style="color:#888;font-size:11px;">IS</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;"><span id="transfer-out-goals">0</span><span style="font-size:14px;color:#999;"> / <span id="transfer-out-goals-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;"><span id="transfer-out-assists">0</span><span style="font-size:14px;color:#999;"> / <span id="transfer-out-assists-pct">0</span>%</span></span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
        </div>

        <!-- Hidden -->
        <div style="display:none;">
        {last_match_impact:.2f}
        </div>

        <div class="main-layout">
            <div class="main-table">
                <!-- Team name + tabs moved up from header to sit flush above the table -->
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:12px;flex-wrap:wrap;background:linear-gradient(to right, #043fb6 0%, #2e7af8 100%);padding:16px 20px;border-radius:12px;">
                    <h1 style="margin:0;font-size:24px;font-weight:600;color:white;">{team_name}</h1>
                    <div class="header-tabs">
                        <div class="tab active" onclick="selectTab(this, 'Squad')">Squad</div>
                        <div class="tab" onclick="selectTab(this, 'Missing Players')">Missing Players</div>
                        <div class="tab" onclick="selectTab(this, 'Doubtful Players')">Doubtful Players</div>
                        <div class="tab" onclick="selectTab(this, 'Returning Players')">Returning Players</div>
                        <div class="tab" onclick="selectTab(this, 'Transfer In')">Transfer In</div>
                        <div class="tab" onclick="selectTab(this, 'Transfer Out')">Transfer Out</div>
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
                <!-- Coach (left) + Stadium (right) below main table, auto-width, aligned to table edges -->
                <div id="coach-stadium-bar" style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;gap:10px;">
                    <div style="display:inline-block;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;"><span style="color:#667eea;font-weight:600;">Coach:</span> {coach_name_display}</div>
                    <div style="display:inline-block;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;"><span style="color:#667eea;font-weight:600;">Stadium:</span> {stadium_display}</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        var _tooltipTimer = null;
        function toggleSection(hostId, btn) {{
            var host = document.getElementById(hostId);
            if (!host) return;
            var isVisible = host.style.display !== 'none';
            // ⚖️ Compare Lineups and 📊 Squad Overview are mutually exclusive (both live in left column)
            var pairedHosts = ['comparison-table-host', 'info-bar-squad-host'];
            if (!isVisible && pairedHosts.indexOf(hostId) !== -1) {{
                pairedHosts.forEach(function(id) {{
                    var h = document.getElementById(id);
                    if (h) h.style.display = 'none';
                }});
                document.querySelectorAll('#btn-compare-lineups, #btn-squad-overview').forEach(function(b) {{
                    if (b) b.classList.remove('active');
                }});
            }}
            if (!isVisible) {{
                host.style.display = 'block';
                if (btn) btn.classList.add('active');
            }} else {{
                host.style.display = 'none';
                if (btn) btn.classList.remove('active');
            }}
        }}
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
                    fileNameEl.textContent = (fileEl.files && fileEl.files[0]) ? fileEl.files[0].name : 'File not selected';
                }});
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
            }} else if (tabName === 'Missing Players') {{
                missingBar.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'none';
                document.body.classList.add('hide-watermark');
                calcGroupStats('missing', MISSING_STATUSES);
            }} else if (tabName === 'Doubtful Players') {{
                doubtfulBar.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'none';
                document.body.classList.add('hide-watermark');
                calcGroupStats('doubtful', DOUBTFUL_STATUSES);
            }} else if (tabName === 'Returning Players') {{
                returningBar.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'none';
                document.body.classList.add('hide-watermark');
                calcGroupStats('returning', RETURNING_STATUSES);
            }} else if (tabName === 'Transfer In') {{
                transferInBar.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'none';
                document.body.classList.add('hide-watermark');
                calcGroupStats('transfer-in', TRANSFER_IN_STATUSES);
            }} else if (tabName === 'Transfer Out') {{
                transferOutBar.style.display = 'flex';
                if (bulkPanel) bulkPanel.style.display = 'none';
                document.body.classList.add('hide-watermark');
                calcGroupStats('transfer-out', TRANSFER_OUT_STATUSES);
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
                const pageMain = document.querySelector('.page-main');
                const h1 = document.querySelector('.main-table h1');
                const teamName = h1 ? h1.textContent.trim() : 'team';
                const coachStadium = document.getElementById('coach-stadium-bar');

                // Create off-screen capture div
                const capture = document.createElement('div');
                capture.style.cssText = 'position:absolute;left:-9999px;top:0;background:#f4f6f9;padding:16px;width:fit-content;';

                // Team name (no tabs)
                const hdr = document.createElement('div');
                hdr.style.cssText = 'font-size:22px;font-weight:700;color:#333;margin-bottom:12px;font-family:system-ui;';
                hdr.textContent = teamName;
                capture.appendChild(hdr);

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

        // Returns a Promise<canvas> for use by parent (Match mode)
        async function getScreenshotCanvas() {{
            try {{
                const teamName = document.querySelector('.header h1').textContent.trim();
                const infoBar = document.getElementById('info-bar-squad');
                const compTable = document.getElementById('comparison-table');
                const mainTable = document.querySelector('.table-container');
                const realTable = mainTable ? mainTable.querySelector('table') : null;

                // Measure the NATURAL width of the table (sum of all column widths)
                let fullW = 1200;
                if (realTable) {{
                    // Clone just the table, set width to auto, measure natural width
                    const probe = realTable.cloneNode(true);
                    probe.style.width = 'auto';
                    probe.style.position = 'absolute';
                    probe.style.visibility = 'hidden';
                    probe.style.left = '-9999px';
                    document.body.appendChild(probe);
                    fullW = Math.max(probe.offsetWidth, mainTable.scrollWidth, 1200);
                    document.body.removeChild(probe);
                }}

                // Build capture container at natural table width
                const capture = document.createElement('div');
                capture.style.cssText = 'position:absolute;left:-9999px;top:0;background:#f4f6f9;padding:16px;width:' + fullW + 'px;';

                const hdr = document.createElement('div');
                hdr.style.cssText = 'font-size:22px;font-weight:700;color:#333;margin-bottom:12px;font-family:system-ui;';
                hdr.textContent = teamName;
                capture.appendChild(hdr);

                if (infoBar) capture.appendChild(infoBar.cloneNode(true));
                if (compTable) capture.appendChild(compTable.cloneNode(true));
                if (mainTable) {{
                    const mtClone = mainTable.cloneNode(true);
                    // Force the clone and its table to expand fully
                    mtClone.style.overflow = 'visible';
                    mtClone.style.width = fullW + 'px';
                    const innerTable = mtClone.querySelector('table');
                    if (innerTable) innerTable.style.width = fullW + 'px';
                    capture.appendChild(mtClone);
                }}

                _replaceCheckboxesWithCircles(capture);
                document.body.appendChild(capture);

                const canvas = await html2canvas(capture, {{
                    backgroundColor: '#f4f6f9',
                    scale: 2,
                    useCORS: true,
                    logging: false,
                    width: capture.scrollWidth,
                    height: capture.scrollHeight,
                    windowWidth: capture.scrollWidth + 200
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
                const countries = Object.keys(navData).sort();
                countries.forEach(country => {{
                    const option = document.createElement('option');
                    option.value = country;
                    option.textContent = country;
                    countrySelect.appendChild(option);
                }});
                // Auto-select current country based on team_id
                for (const [country, leagues] of Object.entries(navData)) {{
                    for (const teams of Object.values(leagues)) {{
                        if (teams.some(t => t.id === CURRENT_TEAM_ID)) {{
                            countrySelect.value = country;
                            onNavCountryChange();
                            return;
                        }}
                    }}
                }}
            }}

            window.onNavCountryChange = function() {{
                const country = document.getElementById('nav-country').value;
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
                let currentChamp = null;
                for (const [ch, teams] of Object.entries(navData[country])) {{
                    if (teams.some(t => t.id === CURRENT_TEAM_ID)) currentChamp = ch;
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
        </script>
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
