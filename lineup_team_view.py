"""
Lineup Team View - Displays squad table with all columns
"""
import json
import glob
import os
import re
from fastapi.responses import HTMLResponse

def swap_name_order(name):
    """Always swap to: First Name Last Name"""
    injury_words = ['Injury', 'Illness', 'Knee', 'Ankle', 'Muscle', 'Leg', 'Foot', 'Thigh', 'Hamstring', 'Groin', 'Shoulder', 'Back', 'Hip']
    for word in injury_words:
        name = re.sub(rf'\b{word}\b', '', name, flags=re.IGNORECASE)
    
    name = re.sub(r'\s*\([^)]*\)\s*', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    parts = name.split()
    if len(parts) < 2:
        return name
    
    prefixes = {'El', 'La', 'Le', 'De', 'Di', 'Van', 'Von', 'Da', "D'"}
    
    last_name = parts[0]
    first_name = ' '.join(parts[1:])
    
    if last_name in prefixes and len(parts) >= 3:
        last_name = parts[1] + ' ' + last_name
        first_name = ' '.join(parts[2:])
    
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
        'Colombia': 'co', 'Comoros': 'km', 'Congo': 'cg', 'DR Congo': 'cd',
        'Congo DR': 'cd', 'Democratic Republic of the Congo': 'cd',
        'Costa Rica': 'cr', 'Croatia': 'hr', 'Cuba': 'cu', 'Cyprus': 'cy',
        'Czech Republic': 'cz', 'Czechia': 'cz', 'Denmark': 'dk', 'Djibouti': 'dj',
        'Dominica': 'dm', 'Dominican Republic': 'do', 'Ecuador': 'ec', 'Egypt': 'eg',
        'El Salvador': 'sv', 'Equatorial Guinea': 'gq', 'Eritrea': 'er', 'Estonia': 'ee',
        'Eswatini': 'sz', 'Swaziland': 'sz', 'Ethiopia': 'et', 'Fiji': 'fj',
        'Finland': 'fi', 'France': 'fr', 'Gabon': 'ga', 'Gambia': 'gm',
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

def _parse_mv(value):
    s = str(value or "").strip()
    if not s or s in {"-", "—"}:
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

def render_team_view(team_id: str) -> HTMLResponse:
    """Render team squad page"""
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    
    # --- Попробовать live-кеш (свежие данные от Soccerway) ---
    import time as _time
    live_cache_path = os.path.join(DATA_DIR, f"_live_cache_{team_id}.json")
    team_file = None
    
    # Сначала проверяем live-кеш (свежие данные)
    if os.path.exists(live_cache_path):
        try:
            with open(live_cache_path, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            if True:  # always use live cache if exists
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
        return HTMLResponse("Team not found", status_code=404)
    
    try:
        with open(team_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return HTMLResponse(f"Error loading team data: {e}", status_code=500)
    
    team_name = data.get("team", {}).get("name", "Unknown")
    players = data.get("players", [])
    
    # Get coach data
    coach = data.get("coach", {})
    coach_name = coach.get("name", "–")
    coach_nationality = coach.get("nationality", "")
    coach_name_display = swap_name_order(coach_name) if coach_name != "–" else "–"
    if coach_nationality:
        coach_flag_html = get_flag_html(coach_nationality).replace('width:30px;height:30px;', 'width:16px;height:16px;').replace('vertical-align:middle;', 'vertical-align:middle;margin-right:4px;')
        coach_name_display = f'{coach_flag_html} {coach_name_display}'
    
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
        float(p.get("impact_score", 0) or 0)
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
        float(p.get("age", 0) or 0)
        for p in sorted_players
        if p.get("last3") and len(p["last3"]) > 0 and p["last3"][0] == "START" and p.get("age")
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
                    cells += '<td style="text-align:center;vertical-align:middle;"><div style="width:20px;height:20px;border-radius:50%;background:#17843f;display:inline-flex;vertical-align:middle;align-items:center;justify-content:center;"><span style="color:white;font-size:11px;font-weight:bold;line-height:1;">c</span></div></td>'
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
        player_row = f"""
            <tr data-last="{last_start}">
                <td style="text-align:center;padding:4px 2px;">{p.get("number", "–")}</td>
                <td style="text-align:center;">{get_flag_html(p.get("national", "–"))}</td>
                <td class="player-name" style="white-space:nowrap;"><strong>{swap_name_order(p.get("name", "–"))}{' ⚽️' if unique_goal_leader and swap_name_order(p.get("name", "–")) == unique_goal_leader else ''}{' 👟' if unique_assist_leader and swap_name_order(p.get("name", "–")) == unique_assist_leader else ''}</strong></td>
                <td class="status-cell"><div class="status-wrapper"><span class="status-emoji-display">✅</span><span class="status-chevron">▼</span><select class="status-select" onchange="updateStatusIcon(this)"><option value="Available">✅ Available</option><option value="Doubt">❓ Doubt</option><option value="Injury">❌ Injury</option><option value="Red card">🟥 Red card</option><option value="Yellow red card">🟥 Yellow/red card</option><option value="Last Yellow card">🟨 Last Yellow card</option><option value="Not playing (Called up)">✈️ Not playing (Called up)</option><option value="Not playing (Other)">🚫 Not playing (Other)</option><option value="Return (Injury)">🔙 Return (Injury)</option><option value="Return (Susp)">🔙 Return (Susp)</option><option value="Return (Called up)">🔙 Return (Called up)</option><option value="Return (Other)">🔙 Return (Other)</option></select></div></td>
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
    # --- Last 3: заголовок (две строки) ---
    # Строка 1: "Last 3" (colspan=3)
    # Строка 2: дата + турнир для каждого матча
    last3_header_row1 = '<th colspan="3" style="text-align:center;font-size:11px;padding:6px 4px;border-bottom:none;">Last 3</th>'
    last3_header_cells = ""
    for m in last3_matches:
        date_str = m.get("date", "")
        comp_str = m.get("comp", "") or m.get("tournament", "")
        score_str = m.get("score", "")
        tooltip = f"Ligue 1: {score_str}" if score_str else ""
        last3_header_cells += f'<th style="text-align:center;font-size:10px;padding:2px 4px;line-height:1.2;white-space:nowrap;border-top:none;cursor:default;" title="{tooltip}">{date_str}<br><span style="font-weight:400;color:#888;">{comp_str}</span></th>'
    
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
        .squad-role.key {{ background: #d4edda; color: #155724; border: 2px solid #28a745; }}
        .squad-role.important {{ background: #d1ecf1; color: #0c5460; border: 2px solid #17a2b8; }}
        .squad-role.starter {{ background: #fff3cd; color: #856404; }}
                .squad-role.rotation {{ background: #e2e3e4; color: #383d41; }}
                .squad-role.bench {{ background: #f8d7da; color: #721c24; }}
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
    </style>


\n<script src="/icons/status-icons.js?v=2"></script>
</head>
<body>
    <div class="header">
        <h1>{team_name}</h1>
        <div class="header-tabs">
            <div class="tab active">Squad</div>
            <div class="tab">Missing Players</div>
            <div class="tab">Doubtful Players</div>
            <div class="tab">Returning Players</div>
        </div>
        <a href="/lineup_ai/select">← Back to teams</a>
    </div>

    <div class="container">
        <div class="tabs" style="display:none;">
            <div class="tab active">Squad</div>
            <div class="tab">Missing Players</div>
            <div class="tab">Doubtful Players</div>
            <div class="tab">Returning Players</div>
        </div>

        <!-- Info Bar: Coach, Stadium, Stats — full width (Squad mode) -->
        <div id="info-bar-squad" style="display:flex;gap:12px;margin-bottom:12px;">
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;text-align:center;"><span style="color:#667eea;font-weight:600;">Coach:</span> {coach_name_display}</div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;color:#333;text-align:center;"><span style="color:#667eea;font-weight:600;">Stadium:</span> {stadium_display}</div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#667eea;font-size:20px;">{squad_size}</span><br><span style="color:#888;font-size:11px;">Players</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#667eea;font-size:20px;">{avg_age}</span><br><span style="color:#888;font-size:11px;">Avg Age</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#667eea;font-size:20px;">€{total_value:.1f}m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
        </div>

        <!-- Missing Players Stats (hidden by default) -->
        <div id="info-bar-missing" style="display:none;gap:12px;margin-bottom:12px;">
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-impact">0.00</span><br><span style="color:#888;font-size:11px;">Impact Score</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-goals">0</span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#dc3545;font-size:20px;" id="missing-assists">0</span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
        </div>

        <!-- Doubtful Players Stats (hidden by default) -->
        <div id="info-bar-doubtful" style="display:none;gap:12px;margin-bottom:12px;">
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-impact">0.00</span><br><span style="color:#888;font-size:11px;">Impact Score</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-goals">0</span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#5F5D58;font-size:20px;" id="doubtful-assists">0</span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
        </div>

        <!-- Returning Players Stats (hidden by default) -->
        <div id="info-bar-returning" style="display:none;gap:12px;margin-bottom:12px;">
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-count">0</span><br><span style="color:#888;font-size:11px;">Players</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-value">€0.0m</span><br><span style="color:#888;font-size:11px;">Total Value</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-impact">0.00</span><br><span style="color:#888;font-size:11px;">Impact Score</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-goals">0</span><br><span style="color:#888;font-size:11px;">Total Goals</span></div>
            <div style="flex:1;background:white;padding:10px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);font-size:15px;text-align:center;"><span style="font-weight:bold;color:#17843f;font-size:20px;" id="returning-assists">0</span><br><span style="color:#888;font-size:11px;">Total Assists</span></div>
        </div>

        <!-- Comparison Tables: P-XI left, S-XI right — full width (Squad mode) -->
        <div id="comparison-table" style="display:flex;gap:12px;margin-bottom:16px;">
            <!-- Possible XI -->
            <div style="flex:1;background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);overflow:hidden;">
            <table style="width:100%;border-collapse:collapse;font-size:14px;">
                <thead>
                    <tr style="background:#f8f9fa;">
                        <th style="padding:8px 16px;text-align:right;color:#888;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;"></th>
                        <th style="padding:8px 16px;text-align:center;color:#667eea;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Possible XI</th>
                        <th style="padding:8px 16px;text-align:center;color:#555;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Δ (%)</th>
                        <th style="padding:8px 16px;text-align:center;color:#555;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Last Match</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-top:1px solid #eee;">
                        <td style="padding:8px 16px;font-weight:600;text-align:right;white-space:nowrap;">Impact Score</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pxi-impact">0.00</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pxi-pct-impact">–</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pxi-last-impact">{last_match_impact:.2f}</td>
                    </tr>
                    <tr style="border-top:1px solid #eee;">
                        <td style="padding:8px 16px;font-weight:600;text-align:right;white-space:nowrap;">Market Value</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pxi-mv">0.0m</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pxi-pct-mv">–</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pxi-last-mv">{last_match_mv:.1f}m</td>
                    </tr>
                    <tr style="border-top:1px solid #eee;">
                        <td style="padding:8px 16px;font-weight:600;text-align:right;white-space:nowrap;">Av.Age</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pxi-age">0.0</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pxi-pct-age">–</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pxi-last-age">{last_match_age:.1f}</td>
                    </tr>
                </tbody>
            </table>
            </div>
            <!-- Starting XI -->
            <div style="flex:1;background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);overflow:hidden;">
            <table style="width:100%;border-collapse:collapse;font-size:14px;">
                <thead>
                    <tr style="background:#f8f9fa;">
                        <th style="padding:8px 16px;text-align:right;color:#888;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;"></th>
                        <th style="padding:8px 16px;text-align:center;color:#dc3545;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Starting XI</th>
                        <th style="padding:8px 16px;text-align:center;color:#555;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Δ (%)</th>
                        <th style="padding:8px 16px;text-align:center;color:#555;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Last Match</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-top:1px solid #eee;">
                        <td style="padding:8px 16px;font-weight:600;text-align:right;white-space:nowrap;">Impact Score</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-sxi-impact">0.00</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pct-impact">–</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-last-impact">{last_match_impact:.2f}</td>
                    </tr>
                    <tr style="border-top:1px solid #eee;">
                        <td style="padding:8px 16px;font-weight:600;text-align:right;white-space:nowrap;">Market Value</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-sxi-mv">0.0m</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pct-mv">–</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-last-mv">{last_match_mv:.1f}m</td>
                    </tr>
                    <tr style="border-top:1px solid #eee;">
                        <td style="padding:8px 16px;font-weight:600;text-align:right;white-space:nowrap;">Av.Age</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-sxi-age">0.0</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-pct-age">–</td>
                        <td style="padding:8px 16px;text-align:center;" id="cmp-last-age">{last_match_age:.1f}</td>
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
            <div class="main-table">
                <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:11px;">№</th>
                        <th rowspan="2" style="text-align:center;width:18px;padding:0;">Nat</th>
                        <th rowspan="2" style="padding:0 2px;white-space:nowrap;">Player</th>
                        <th rowspan="2" style="text-align:left;width:70px;padding:0;font-size:11px;">Status</th>
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:11px;">Age</th>
                        <th rowspan="2" style="text-align:center;width:42px;padding:0;font-size:11px;">MV</th>
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:11px;">Pos</th>
                        <th rowspan="2" style="text-align:center;width:34px;padding:0;font-size:10px;">Squad<br>Role</th>
                        <th rowspan="2" style="text-align:center;width:34px;padding:0;font-size:10px;">Impact<br>Score</th>
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:10px;">Squad<br>List</th>
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:10px;">P-XI<br><span id="xi-counter" style="color:#667eea;font-size:9px;">0/11</span></th>
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:10px;">S-XI<br><span id="starting-counter" style="color:#dc3545;font-size:9px;">0/11</span></th>
                        {last3_header_row1}
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:11px;">Apps</th>
                        <th rowspan="2" style="text-align:center;width:28px;padding:0;font-size:11px;">Min</th>
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:11px;">G</th>
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:11px;">A</th>
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:11px;">YC</th>
                        <th rowspan="2" style="text-align:center;width:22px;padding:0;font-size:11px;">RC</th>
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
        const MISSING_STATUSES = ['Injury', 'Red card', 'Yellow red card', 'Not playing (Called up)', 'Not playing (Other)'];
        const DOUBTFUL_STATUSES = ['Doubt'];
        const RETURNING_STATUSES = ['Return (Injury)', 'Return (Susp)', 'Return (Called up)', 'Return (Other)'];

        function switchTab(tabName) {{
            const squadBar = document.getElementById('info-bar-squad');
            const missingBar = document.getElementById('info-bar-missing');
            const doubtfulBar = document.getElementById('info-bar-doubtful');
            const returningBar = document.getElementById('info-bar-returning');
            const compTable = document.getElementById('comparison-table');

            // Hide all bars
            squadBar.style.display = 'none';
            missingBar.style.display = 'none';
            doubtfulBar.style.display = 'none';
            returningBar.style.display = 'none';
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
            document.getElementById(prefix + '-value').textContent = '\\u20ac' + totalMV.toFixed(1) + 'm';
            document.getElementById(prefix + '-impact').textContent = totalImpact.toFixed(2);
            document.getElementById(prefix + '-goals').textContent = totalGoals;
            document.getElementById(prefix + '-assists').textContent = totalAssists;
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
            if (!checkbox) {{
                const checkboxes = document.querySelectorAll('.xi-checkbox');
                checkboxes.forEach(cb => {{
                    if (cb.checked) cb.style.background = '#667eea';
                }});
                updateXICounter(null);
                return;
            }}
            
            const xiCheckboxes = document.querySelectorAll('.xi-checkbox');
            let selectedCount = 0;
            
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
            if (!checkbox) {{
                const checkboxes = document.querySelectorAll('.starting-checkbox');
                checkboxes.forEach(cb => {{
                    if (cb.checked) cb.style.background = '#dc3545';
                }});
                updateStartingCounter(null);
                return;
            }}
            
            const startingCheckboxes = document.querySelectorAll('.starting-checkbox');
            let selectedCount = 0;
            
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
            if (mvEl) mvEl.textContent = mv.toFixed(1) + 'm';
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
            if (sxiMvEl) sxiMvEl.textContent = sxiMv.toFixed(1) + 'm';
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
            if (el3) el3.textContent = mv.toFixed(1) + 'm';
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
            }});
        }});

        document.querySelectorAll('.starting-checkbox').forEach(checkbox => {{
            checkbox.addEventListener('change', function() {{
                updateStartingCounter(this);
                recalcSelectedStartingStats();
            }});
        }});

        // Initialize counters
        updateXICounter(null);
        updateStartingCounter(null);
        recalcSelectedStartingStats();
        recalcPossibleXIStats();

    </script>
</body>
</html>"""
    
    return HTMLResponse(html)
