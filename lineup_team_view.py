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
    LIVE_CACHE_TTL = 6 * 3600
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
    players = data.get("players", [])

    cache_age_seconds = None
    cache_badge_text = ""
    cache_badge_color = "#6c757d"
    try:
        if team_file == live_cache_path and os.path.exists(live_cache_path):
            cache_age_seconds = max(0, int(time.time() - os.path.getmtime(live_cache_path)))
            if cache_age_seconds < 3600:
                cache_badge_text = "🟢 Fresh data"
                cache_badge_color = "#17843f"
            elif cache_age_seconds < 6 * 3600:
                h = cache_age_seconds // 3600
                m = (cache_age_seconds % 3600) // 60
                cache_badge_text = f"🟡 {h}h {m}m ago"
                cache_badge_color = "#b7791f"
            else:
                cache_badge_text = "🔴 Stale — click Refresh"
                cache_badge_color = "#dc3545"
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
    
    # Sort players by minutes played (descending)
    sorted_players = sorted(players, key=lambda x: int(x.get('min', '0')) if x.get('min', '0') and str(x['min']).isdigit() else 0, reverse=True)
    
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
                    cells += '<td style="text-align:center;vertical-align:middle;"><div style="width:20px;height:20px;border-radius:50%;background:#17843f;display:inline-flex;vertical-align:middle;align-items:center;justify-content:center;"><span style="color:white;font-size:12px;line-height:1;">✓</span></div></td>'
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
        df_fire = " 🦾" if pos_code in df_aliases and player_impact >= 6 and player_minutes >= 900 else ""
        mf_lightning = " 🌀" if pos_code in mf_aliases and 5 <= player_impact <= 6.99 and player_minutes >= 900 else ""
        star_impact = " ⭐️" if 7 <= player_impact <= 8.99 and player_minutes >= 900 else ""
        top_impact = " 🔝" if player_impact >= 9 and player_minutes >= 900 else ""
        player_row = f"""
            <tr data-last="{last_start}" data-player-name="{p.get("name", "–")}" data-player-number="{p.get("number", "–")}">
                <td style="text-align:center;padding:4px 2px;">{p.get("number", "–")}</td>
                <td style="text-align:center;">{get_nat_html(p)}</td>
                <td class="player-name" style="white-space:nowrap;"><strong>{player_display_name}{df_fire}{mf_lightning}{star_impact}{top_impact}{' ⚽️' if unique_goal_leader and player_display_name == unique_goal_leader else ''}{' 👟' if unique_assist_leader and player_display_name == unique_assist_leader else ''}</strong></td>
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
                <td style="text-align:center;padding:4px 2px;">{p.get("apps", "–")}</td>
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

    last3_header_row1 = '<th colspan="3" style="text-align:center;font-size:11px;padding:6px 4px;border-bottom:none;">Last 3</th>'
    last3_header_cells = ""
    for m in last3_matches:
        date_str = m.get("date", "")
        comp_str = m.get("comp", "") or m.get("tournament", "")
        score_str = m.get("score", "")
        full_comp = _full_comp_name(comp_str)
        tooltip_text = f"{full_comp}: {score_str}" if score_str else full_comp
        tooltip_html = html_lib.escape(tooltip_text, quote=True)
        last3_header_cells += f'<th class="last3-tooltip" style="text-align:center;font-size:10px;padding:2px 2px;line-height:1.2;white-space:nowrap;border-top:none;cursor:default;width:37px;" data-tooltip="{tooltip_html}">{date_str}<br><span style="font-weight:400;color:#888;">{comp_str}</span></th>'
    
    # Team logo removed per user request
    team_logo_html = ""

    html = f"""<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>{team_name} - Squad | LineUp AI</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            margin: 0;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
            gap: 10px;
            min-width: 0;
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
        .container {{
            padding: 24px 32px;
            max-width: 1400px;
            margin: 0 auto;
        }}
        .main-layout {{
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }}
        .main-table {{
            flex: 1;
            min-width: 0;
            overflow-x: auto;
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
            background: white;
            border-radius: 12px;
            overflow-x: auto;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
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
            white-space: nowrap;
        }}
        td {{
            padding: 12px 16px;
            border-bottom: 1px solid #f0f0f0;
            color: #333;
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

        .my-squads-sidebar {{
            width: 230px;
            flex-shrink: 0;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            padding: 12px;
            max-height: calc(100vh - 150px);
            overflow-y: auto;
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
            margin: 0 0 12px 0;
            border-left: 4px solid #667eea;
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
            background: #667eea;
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

        /* Embed mode: remove inner scroll, parent handles it */
        body.embed-mode {{ overflow: visible; height: auto; }}
        body.embed-mode .table-container {{ overflow: visible; }}
        body.embed-mode .main-table {{ overflow: visible; }}
        body.embed-mode .content-wrapper {{ overflow: visible; height: auto; }}
        body.embed-mode .squad-table-wrapper {{ overflow: visible; height: auto; }}
        body.embed-mode .comparison-tables {{ overflow: visible; }}
        body.embed-mode .table-scroll-wrapper {{ overflow: visible; }}
        body.embed-mode .header {{ flex-wrap: nowrap; }}
        body.embed-mode .header-tabs {{ margin-left: auto; }}
    </style>



<script src="/icons/status-icons.js?v=3"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
</head>
<body class="{{"embed-mode" if embed else ""}}">
    <div class="header">
        <div class="team-title">
            <h1>{team_name}</h1>
        </div>
        <div class="header-tabs">
            <div class="tab active">Squad</div>
            <div class="tab">Missing Players</div>
            <div class="tab">Doubtful Players</div>
            <div class="tab">Returning Players</div>
            <div class="tab">Transfer In</div>
            <div class="tab">Transfer Out</div>
        </div>
        <a href="/lineup_ai/select" style="margin-left:auto;">← Back to teams</a>
        <div style="position:relative;display:inline-block;vertical-align:middle;" onmouseenter="showTooltip(this)" onmouseleave="hideTooltip(this)"><button onclick="exportScreenshot()" id="btn-export" style="background:none;border:none;cursor:pointer;font-size:24px;padding:4px 8px;">&#x1F4F8;</button><span class="tooltip-delay" style="visibility:hidden;opacity:0;position:absolute;bottom:130%;left:50%;transform:translateX(-50%);background:#333;color:#fff;font-size:12px;padding:5px 10px;border-radius:4px;white-space:nowrap;pointer-events:none;transition:opacity 0.3s ease;">Save Screenshot</span></div>
    </div>

    <div class="container">
        <div class="tabs" style="display:none;">
            <div class="tab active">Squad</div>
            <div class="tab">Missing Players</div>
            <div class="tab">Doubtful Players</div>
            <div class="tab">Returning Players</div>
            <div class="tab">Transfer In</div>
            <div class="tab">Transfer Out</div>
        </div>

        <div id="snapshot-mode-banner" class="snapshot-mode-banner">Snapshot mode: showing saved independent squad. <button type="button" onclick="returnToLiveTeam()" style="margin-left:10px;border:0;border-radius:5px;background:#667eea;color:white;font-weight:700;padding:4px 8px;cursor:pointer;">Back to current team</button></div>

        <div class="bulk-lineup-panel">
            <div class="bulk-lineup-controls">
                <div class="bulk-lineup-row">
                    <select id="bulk-lineup-mode" aria-label="Bulk lineup mode">
                        <option value="possible">🔵 P-XI</option>
                        <option value="start">🔴 S-XI</option>
                        <option value="squad">⚫️ List</option>
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

        <!-- Info Bar: Coach, Stadium, Stats — full width (Squad mode) -->
        <div id="info-bar-squad" style="display:flex;gap:12px;margin-bottom:12px;">
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;text-align:center;"><span style="color:#667eea;font-weight:600;">Coach:</span> {coach_name_display}</div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;text-align:center;"><span style="color:#667eea;font-weight:600;">Stadium:</span> {stadium_display}</div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#667eea;font-size:20px;">{squad_size}</span><br><span style="color:#888;font-size:11px;">Players</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#667eea;font-size:20px;">{avg_age}</span><br><span style="color:#888;font-size:11px;">Avg Age</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#667eea;font-size:20px;">{total_value_display}</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
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

        <!-- Comparison Tables: P-XI left, S-XI right — full width (Squad mode) -->
        <div id="comparison-table" style="display:flex;gap:12px;margin-bottom:16px;">
            <!-- Possible XI -->
            <div style="flex:1;background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);overflow:hidden;">
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                <thead>
                    <tr style="background:#f8f9fa;">
                        <th style="padding:0 6px;height:22px;line-height:22px;text-align:right;color:#888;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;"></th>
                        <th style="padding:0 6px;height:22px;line-height:22px;text-align:center;color:#667eea;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">P-XI</th>
                        <th style="padding:0 6px;height:22px;line-height:22px;text-align:center;color:#555;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Δ (%)</th>
                        <th style="padding:0 6px;height:22px;line-height:22px;text-align:center;color:#555;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Last Match</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-top:1px solid #eee;height:22px;">
                        <td style="padding:0 6px;font-weight:600;text-align:right;white-space:nowrap;line-height:22px;">IS</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pxi-impact">0.00</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pxi-pct-impact">–</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pxi-last-impact">{last_match_impact:.2f}</td>
                    </tr>
                    <tr style="border-top:1px solid #eee;height:22px;">
                        <td style="padding:0 6px;font-weight:600;text-align:right;white-space:nowrap;line-height:22px;">MV</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pxi-mv">0.0m</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pxi-pct-mv">–</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pxi-last-mv">{last_match_mv:.1f}m</td>
                    </tr>
                    <tr style="border-top:1px solid #eee;height:22px;">
                        <td style="padding:0 6px;font-weight:600;text-align:right;white-space:nowrap;line-height:22px;">Av.Age</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pxi-age">0.0</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pxi-pct-age">–</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pxi-last-age">{last_match_age:.1f}</td>
                    </tr>
                </tbody>
            </table>
            </div>
            <!-- Value S-XI: STARTING XI vs POSSIBLE XI Δ (%) only -->
            <div style="flex:1;background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);overflow:hidden;">
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                <thead>
                    <tr style="background:#f8f9fa;">
                        <th style="padding:0 6px;height:22px;line-height:22px;text-align:right;color:#888;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;"></th>
                        <th style="padding:0 6px;height:22px;line-height:22px;text-align:center;color:#333;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">STARTING XI vs POSSIBLE XI Δ (%)</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-top:1px solid #eee;height:22px;">
                        <td style="padding:0 6px;font-weight:600;text-align:right;white-space:nowrap;line-height:22px;">IS</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-val-pct-impact">–</td>
                    </tr>
                    <tr style="border-top:1px solid #eee;height:22px;">
                        <td style="padding:0 6px;font-weight:600;text-align:right;white-space:nowrap;line-height:22px;">MV</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-val-pct-mv">–</td>
                    </tr>
                    <tr style="border-top:1px solid #eee;height:22px;">
                        <td style="padding:0 6px;font-weight:600;text-align:right;white-space:nowrap;line-height:22px;">Av.Age</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-val-pct-age">–</td>
                    </tr>
                </tbody>
            </table>
            </div>
            <!-- Starting XI -->
            <div style="flex:1;background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);overflow:hidden;">
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                <thead>
                    <tr style="background:#f8f9fa;">
                        <th style="padding:0 6px;height:22px;line-height:22px;text-align:right;color:#888;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;"></th>
                        <th style="padding:0 6px;height:22px;line-height:22px;text-align:center;color:#dc3545;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">S-XI</th>
                        <th style="padding:0 6px;height:22px;line-height:22px;text-align:center;color:#555;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Δ (%)</th>
                        <th style="padding:0 6px;height:22px;line-height:22px;text-align:center;color:#555;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Last Match</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-top:1px solid #eee;height:22px;">
                        <td style="padding:0 6px;font-weight:600;text-align:right;white-space:nowrap;line-height:22px;">IS</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-sxi-impact">0.00</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pct-impact">–</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-last-impact">{last_match_impact:.2f}</td>
                    </tr>
                    <tr style="border-top:1px solid #eee;height:22px;">
                        <td style="padding:0 6px;font-weight:600;text-align:right;white-space:nowrap;line-height:22px;">MV</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-sxi-mv">0.0m</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pct-mv">–</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-last-mv">{last_match_mv:.1f}m</td>
                    </tr>
                    <tr style="border-top:1px solid #eee;height:22px;">
                        <td style="padding:0 6px;font-weight:600;text-align:right;white-space:nowrap;line-height:22px;">Av.Age</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-sxi-age">0.0</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-pct-age">–</td>
                        <td style="padding:0 6px;text-align:center;line-height:22px;" id="cmp-last-age">{last_match_age:.1f}</td>
                    </tr>
                </tbody>
            </table>
            </div>
        </div>

        <!-- Hidden -->
        <div style="display:none;">
        {last_match_impact:.2f}
        </div>

        <div class="main-layout">
            <aside class="my-squads-sidebar" id="my-squads-sidebar">
                <div class="actions-bar" style="margin:0 0 10px 0;align-items:flex-start;flex-direction:column;gap:6px;">
                    <button type="button" class="action-btn save-btn" id="save-btn" onclick="saveTeamState()">💾 Save</button>
                    <span class="cache-badge" style="color:{cache_badge_color};">{cache_badge_text or 'Cache status unknown'}</span>
                    <span id="save-message"></span>
                </div>
                <div class="my-squads-title">My Squads</div>
                <div class="my-squads-help">Saved snapshots are independent from future team data updates.</div>
                <div id="my-squads-list"><div class="snapshot-empty-list">No saved squads yet.</div></div>
            </aside>

            <div class="main-table">
                <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">№</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">Nat</th>
                        <th rowspan="2" style="width:200px;padding:0 2px;white-space:nowrap;">Player</th>
                        <th rowspan="2" style="text-align:left;width:40px;padding:0;">Status</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">Age</th>
                        <th rowspan="2" style="text-align:center;width:60px;padding:0;">MV</th>
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">Pos</th>
                        <th rowspan="2" style="text-align:center;width:60px;padding:0;font-size:11px;">Squad<br>Role</th>
                        <th rowspan="2" style="text-align:center;width:40px;padding:0;font-size:11px;">IS</th>
                        <th rowspan="2" style="text-align:center;width:37px;padding:0;font-size:10px;vertical-align:top;"><div style="display:flex;flex-direction:column;align-items:center;height:100%;"><button onclick="clearColumn('squad');return false;" style="background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin:0;" title="Clear List">🔄</button><span style="font-size:10px;margin-top:2px;">List</span></div></th>
                        <th rowspan="2" style="text-align:center;width:37px;padding:0;font-size:10px;vertical-align:top;"><div style="display:flex;flex-direction:column;align-items:center;height:100%;"><button onclick="clearColumn('possible');return false;" style="background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin:0;" title="Clear P-XI">🔄</button><span style="font-size:10px;margin-top:2px;">P-XI</span><span id="xi-counter" style="color:#667eea;font-size:9px;">0/11</span></div></th>
                        <th rowspan="2" style="text-align:center;width:37px;padding:0;font-size:10px;vertical-align:top;"><div style="display:flex;flex-direction:column;align-items:center;height:100%;"><button onclick="clearColumn('start');return false;" style="background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin:0;" title="Clear S-XI">🔄</button><span style="font-size:10px;margin-top:2px;">S-XI</span><span id="starting-counter" style="color:#dc3545;font-size:9px;">0/11</span></div></th>
                        {last3_header_row1}
                        <th rowspan="2" style="text-align:center;width:30px;padding:0;">Apps</th>
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
            </div>
        </div>
    </div>

    <script>
        var _tooltipTimer = null;
        function showTooltip(el) {{ var t = el.querySelector('.tooltip-delay'); if(t){{ _tooltipTimer = setTimeout(function(){{ t.style.visibility='visible'; t.style.opacity='1'; }}, 800); }} }}
        function hideTooltip(el) {{ if(_tooltipTimer){{ clearTimeout(_tooltipTimer); _tooltipTimer=null; }} var t = el.querySelector('.tooltip-delay'); if(t){{ t.style.opacity='0'; setTimeout(function(){{ t.style.visibility='hidden'; }}, 300); }} }}
        const MISSING_STATUSES = ['Injury', 'Red card', 'Yellow red card', 'Not playing (Called up)', 'Not playing (Other)'];
        const DOUBTFUL_STATUSES = ['Doubt'];
        const RETURNING_STATUSES = ['Return (Injury)', 'Return (Susp)', 'Return (Called up)', 'Return (Other)'];
        const TRANSFER_IN_STATUSES = ['New player'];
        const TRANSFER_OUT_STATUSES = ['Left the team'];

        const TEAM_ID = "{team_id}";
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
                const displayName = cells[2] ? cells[2].textContent.replace(/[🦾🌀⭐🔝⚽👟️]/g, ' ') : rawName;
                const number = String(row.getAttribute('data-player-number') || (cells[0] ? cells[0].textContent : '') || '').trim();
                const norm = bulkNormalizeText(rawName + ' ' + displayName);
                const parts = bulkNameParts(rawName + ' ' + displayName);
                const rawParts = bulkNameParts(rawName);
                const surname = rawParts.length ? rawParts[0] : (parts[0] || '');
                return {{ row: row, rawName: rawName, displayName: displayName.trim(), number: number, norm: norm, parts: parts, surname: surname }};
            }});
        }}

        function bulkUnique(rows) {{
            const seen = new Set();
            return rows.filter(r => {{ if (seen.has(r.row)) return false; seen.add(r.row); return true; }});
        }}

        function bulkFindMatches(parsed, rows) {{
            const hasName = !!parsed.norm;
            const hasNum = !!parsed.number;
            const surnameCandidates = hasName ? rows.filter(r =>
                r.surname === parsed.norm ||
                r.parts.includes(parsed.norm) ||
                parsed.parts.some(p => r.surname === p)
            ) : [];
            const numberCandidates = hasNum ? rows.filter(r => r.number === parsed.number) : [];
            const nameNumberCandidates = (hasName && hasNum) ? rows.filter(r => r.number === parsed.number && (r.norm.includes(parsed.norm) || parsed.parts.some(p => r.parts.includes(p)))) : [];

            // Priority: surname+number, surname, number, name+number. More exact matches first.
            if (hasName && hasNum) {{
                let exact = rows.filter(r => r.number === parsed.number && (r.surname === parsed.norm || parsed.parts.some(p => r.surname === p)));
                exact = bulkUnique(exact);
                if (exact.length) return exact;
            }}
            if (surnameCandidates.length) return bulkUnique(surnameCandidates);
            if (numberCandidates.length) return bulkUnique(numberCandidates);
            if (nameNumberCandidates.length) return bulkUnique(nameNumberCandidates);
            if (hasName) {{
                const full = rows.filter(r => r.norm.includes(parsed.norm) || parsed.parts.every(p => r.parts.includes(p)));
                return bulkUnique(full);
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
                const res = await fetch('/lineup_ai/vision_lineup/' + encodeURIComponent(TEAM_ID), {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ image: imageDataUrl, mode: modeEl ? (modeEl.value || 'possible') : 'possible' }})
                }});
                const json = await res.json();
                if (!res.ok || !json.ok) throw new Error(json.error || 'vision failed');
                const names = Array.isArray(json.players) ? json.players : [];
                if (textEl) textEl.value = names.join('\\n');
                const result = applyBulkLineupFromTokens(names, modeEl ? modeEl.value : 'possible');
                if (statusEl) {{
                    statusEl.style.color = result.found ? '#17843f' : '#dc3545';
                    statusEl.textContent = 'Vision: ' + names.length + ' names, marked ' + result.found;
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
            }} else if (tabName === 'Missing Players') {{
                missingBar.style.display = 'flex';
                calcGroupStats('missing', MISSING_STATUSES);
            }} else if (tabName === 'Doubtful Players') {{
                doubtfulBar.style.display = 'flex';
                calcGroupStats('doubtful', DOUBTFUL_STATUSES);
            }} else if (tabName === 'Returning Players') {{
                returningBar.style.display = 'flex';
                calcGroupStats('returning', RETURNING_STATUSES);
            }} else if (tabName === 'Transfer In') {{
                transferInBar.style.display = 'flex';
                calcGroupStats('transfer-in', TRANSFER_IN_STATUSES);
            }} else if (tabName === 'Transfer Out') {{
                transferOutBar.style.display = 'flex';
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
                // MV cell[5]: text like "€5.7m" or "–"
                const mvText = cells[5] ? cells[5].textContent.trim() : '';
                const mvMatch = mvText.match(/([\\d.]+)/);
                if (mvMatch) totalMV += parseFloat(mvMatch[1]);
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
            const pctImpactEl = document.getElementById('cmp-pct-impact');
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
            // Read S-XI values from already-updated comparison table
            var sxiImpact = parseFloat((document.getElementById('cmp-sxi-impact') || {{}}).textContent) || 0;
            var sxiMvText = (document.getElementById('cmp-sxi-mv') || {{}}).textContent || '0';
            var sxiAge = parseFloat((document.getElementById('cmp-sxi-age') || {{}}).textContent) || 0;

            // Read P-XI values
            var pxiImpact = parseFloat((document.getElementById('cmp-pxi-impact') || {{}}).textContent) || 0;
            var pxiMvText = (document.getElementById('cmp-pxi-mv') || {{}}).textContent || '0';
            var pxiAge = parseFloat((document.getElementById('cmp-pxi-age') || {{}}).textContent) || 0;

            // Parse MV values (handle "X.Xm" and "X.XXbn")
            function parseMV(s) {{
                s = (s || '').trim().toLowerCase().replace(/€/g, '');
                if (s.endsWith('bn')) return parseFloat(s) * 1000;
                if (s.endsWith('m')) return parseFloat(s);
                return parseFloat(s) || 0;
            }}
            var sxiMv = parseMV(sxiMvText);
            var pxiMv = parseMV(pxiMvText);

            // Impact Δ (%)
            var el2 = document.getElementById('cmp-val-pct-impact');
            if (el2) {{
                if (pxiImpact > 0 && sxiImpact > 0) {{
                    var d = (sxiImpact - pxiImpact) / pxiImpact * 100;
                    el2.innerHTML = fmtPct(d);
                }} else el2.textContent = '–';
            }}

            // MV Δ (%)
            var el4 = document.getElementById('cmp-val-pct-mv');
            if (el4) {{
                if (pxiMv > 0 && sxiMv > 0) {{
                    var d2 = (sxiMv - pxiMv) / pxiMv * 100;
                    el4.innerHTML = fmtPct(d2);
                }} else el4.textContent = '–';
            }}

            // Age Δ (%)
            var el6 = document.getElementById('cmp-val-pct-age');
            if (el6) {{
                if (pxiAge > 0 && sxiAge > 0) {{
                    var d3 = (sxiAge - pxiAge) / pxiAge * 100;
                    el6.innerHTML = fmtPct(d3);
                }} else el6.textContent = '–';
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
                // Build a wrapper that clones the visible sections
                const teamName = document.querySelector('.header h1').textContent.trim();
                const infoBar = document.getElementById('info-bar-squad');
                const compTable = document.getElementById('comparison-table');
                const mainTable = document.querySelector('.table-container');

                // Create off-screen capture div
                const capture = document.createElement('div');
                capture.style.cssText = 'position:absolute;left:-9999px;top:0;background:#f4f6f9;padding:16px;width:' + document.querySelector('.container').offsetWidth + 'px;';

                // Header with team name
                const hdr = document.createElement('div');
                hdr.style.cssText = 'font-size:22px;font-weight:700;color:#333;margin-bottom:12px;font-family:system-ui;';
                hdr.textContent = teamName;
                capture.appendChild(hdr);

                // Clone sections (deep clone to preserve all state)
                if (infoBar) capture.appendChild(infoBar.cloneNode(true));
                if (compTable) capture.appendChild(compTable.cloneNode(true));
                if (mainTable) capture.appendChild(mainTable.cloneNode(true));

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
                var teamId = window.location.pathname.split('/').pop();
                fetch('/lineup_ai/api/fetch/' + teamId)
                    .then(function(r) {{ return r.json(); }})
                    .then(function(data) {{
                        if (data && data.changed) {{
                            window.location.reload();
                        }}
                    }})
                    .catch(function(err) {{
                        console.log('Background live-data sync failed:', err);
                    }});
            }})();
        }}

    // Export for iframe communication (Match mode)
    // Store reference to inner function before exporting to avoid recursion
    var _applySavedStateInner = restoreTeamState;
    window.getCurrentTeamData = function() {{ return collectTeamState(); }};
    window.applySavedState = function(data) {{ if (data && Array.isArray(data.players)) _applySavedStateInner(data); }};

</script>
</body>
</html>"""
    
    response = HTMLResponse(html)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
