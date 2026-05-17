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
    
    country_codes = {
        'Belgium': 'be', 'France': 'fr', 'Germany': 'de', 'Spain': 'es',
        'Italy': 'it', 'Portugal': 'pt', 'England': 'gb', 'Sweden': 'se',
        'Argentina': 'ar', 'Brazil': 'br', 'Paraguay': 'py', 'Ivory Coast': 'ci',
        'Algeria': 'dz', 'Norway': 'no', 'Netherlands': 'nl', 'Denmark': 'dk',
        'Poland': 'pl', 'Ireland': 'ie', 'Croatia': 'hr', 'Serbia': 'rs',
        'Switzerland': 'ch', 'Austria': 'at', 'Czech Republic': 'cz', 'Russia': 'ru',
        'Ukraine': 'ua', 'Romania': 'ro', 'Greece': 'gr', 'Turkey': 'tr',
        'Belarus': 'by', 'Morocco': 'ma', 'Tunisia': 'tn', 'Senegal': 'sn',
        'Nigeria': 'ng', 'Egypt': 'eg', 'Japan': 'jp', 'South Korea': 'kr',
        'Australia': 'au', 'USA': 'us', 'Mexico': 'mx', 'Colombia': 'co',
        'Uruguay': 'uy', 'Chile': 'cl', 'Peru': 'pe', 'Costa Rica': 'cr',
        'Cameroon': 'cm', 'Ghana': 'gh', 'Saudi Arabia': 'sa', 'Iran': 'ir',
        'Qatar': 'qa', 'China': 'cn', 'Kazakhstan': 'kz', 'Guinea': 'gn',
        'Scotland': 'gb-sct', 'Wales': 'gb-wls', 'Northern Ireland': 'gb-nir'
    }
    
    code = country_codes.get(country_name.strip())
    
    if not code:
        for cn, cd in country_codes.items():
            if cn.lower() == country_name.strip().lower():
                code = cd
                break
    
    if not code:
        return "–"
    
    return f'<img src="https://flagcdn.com/w40/{code}.png" alt="{country_name.strip()}" style="width:30px;height:30px;vertical-align:middle;border-radius:3px;">'

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
    
    team_file = None
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
    
    # Format coach HTML
    coach_html = ""
    if coach_name != "–" and coach_nationality:
        formatted_coach_name = swap_name_order(coach_name)
        coach_flag_html = get_flag_html(coach_nationality).replace('width:30px;height:30px;', 'width:20px;height:20px;').replace('vertical-align:middle;', 'vertical-align:middle;margin-right:6px;')
        coach_html = f' <span style="color:rgba(255,255,255,0.9);font-size:18px;margin-left:12px;vertical-align:middle;">{coach_flag_html} Coach: {formatted_coach_name}</span>'
    
    # Calculate stats
    squad_size = len(players)
    total_age = sum(int(p.get("age", 0)) for p in players if p.get("age", "").isdigit())
    avg_age = round(total_age / squad_size, 1) if squad_size > 0 else 0
    total_apps = sum(int(p.get("apps", 0)) for p in players if p.get("apps", "").isdigit())
    total_goals = sum(int(p.get("goal", 0)) for p in players if p.get("goal", "").isdigit())
    total_assists = sum(int(p.get("assist", 0)) for p in players if p.get("assist", "").isdigit())
    total_yellow = sum(int(p.get("yellow_card", 0)) for p in players if p.get("yellow_card", "").isdigit())
    total_red = sum(int(p.get("red_card", 0)) for p in players if p.get("red_card", "").isdigit())
    starting_players = [p for p in players if str(p.get("squad_role", "")).lower() == "starting xi"]
    starting_xi_impact_score = round(sum(float(p.get("impact_score", 0) or 0) for p in starting_players), 2)
    total_value = round(sum(_parse_mv(p.get("market_value", 0)) for p in players) / 1_000_000.0, 1)
    mv_starting_xi = round(sum(_parse_mv(p.get("market_value", 0)) for p in starting_players) / 1_000_000.0, 1)
    av_age_starting_xi = round(sum(float(p.get("age", 0) or 0) for p in starting_players) / len(starting_players), 1) if starting_players else 0.0
    
    # Sort players by minutes played (descending)
    sorted_players = sorted(players, key=lambda x: int(x.get('min', '0')) if x.get('min', '0') and str(x['min']).isdigit() else 0, reverse=True)
    
    # Verify all fields are present before rendering
    for p in sorted_players:
        # Ensure all required fields exist
        if 'squad_role' not in p:
            p['squad_role'] = 'Bench'
        if 'impact_score' not in p:
            p['impact_score'] = 0
    
    players_rows = ""
    for p in sorted_players:
        last3_html = ""
        
        player_row = f"""
            <tr>
                <td>{p.get("number", "–")}</td>
                <td>{get_flag_html(p.get("national", "–"))}</td>
                <td><strong>{swap_name_order(p.get("name", "–"))}</strong></td>
                <td class="status-cell"><img class="status-icon-img" src="" width="20" height="20" style="vertical-align:middle;margin-right:4px;"><select class="status-select" style="vertical-align:middle;padding:2px;font-size:12px;border:1px solid #ddd;border-radius:4px;max-width:170px;" onchange="updateStatusIcon(this)"><option value="Available">Available</option><option value="Doubt">Doubt</option><option value="Injury">Injury</option><option value="Red card">Red card</option><option value="Yellow red card">Yellow red card</option><option value="Last Yellow card">Last Yellow card</option><option value="Not playing (Called up)">Not playing (Called up)</option><option value="Not playing (Other)">Not playing (Other)</option><option value="Return (Injury)">Return (Injury)</option><option value="Return (Susp)">Return (Susp)</option><option value="Return (Called up)">Return (Called up)</option><option value="Return (Other)">Return (Other)</option></select></td>
                <td>{p.get("age", "–")}</td>
                <td>{p.get("market_value", "–")}</td>
                <td class="pos-{p.get("position", "").lower()}">{p.get("position", "–")}</td>
                <td><span class="squad-role {p.get('squad_role', '').lower()}">{p.get("squad_role", "–") if p.get("squad_role") else "–"}</span></td>
                <td>{p.get("impact_score", "–") if p.get("impact_score") is not None else "–"}</td>
                <td style="text-align:center;"><input type="checkbox" name="player" value="{p.get("name", "–")}" class="squad-checkbox" style="width:20px;height:20px;border-radius:50%;border:2px solid #333;background:#e0e0e0;cursor:pointer;appearance:none;-webkit-appearance:none;-moz-appearance:none;" onchange="if(this.checked){{this.style.background='#000';this.style.border='none';}}else{{this.style.background='#e0e0e0';this.style.border='2px solid #333';}}"></td>
                <td style="text-align:center;"><input type="checkbox" name="possible_xi" value="{p.get("name", "–")}" class="xi-checkbox" style="width:20px;height:20px;border-radius:50%;border:2px solid #667eea;background:#e0e0e0;cursor:pointer;appearance:none;-webkit-appearance:none;-moz-appearance:none;transition:all 0.2s;" onchange="updateXICounter(this)"></td>
                <td style="text-align:center;"><input type="checkbox" name="starting_xi" value="{p.get("name", "–")}" class="starting-checkbox" style="width:20px;height:20px;border-radius:50%;border:2px solid #dc3545;background:#e0e0e0;cursor:pointer;appearance:none;-webkit-appearance:none;-moz-appearance:none;transition:all 0.2s;" onchange="updateStartingCounter(this)"></td>
                <td class="last-5">{last3_html}</td>
                <td style="text-align:center;">{p.get("apps", "–")}</td>
                <td style="text-align:center;">{p.get("min", "–")}</td>
                <td>{p.get("goal", "–")}</td>
                <td>{p.get("assist", "–")}</td>
                <td>{p.get("yellow_card", "–")}</td>
                <td>{p.get("red_card", "–")}</td>
            </tr>
        """
        players_rows += player_row
    
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
            padding: 24px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
            font-weight: 600;
        }}
        .header a {{
            color: white;
            text-decoration: none;
            padding: 8px 16px;
            background: rgba(255,255,255,0.2);
            border-radius: 6px;
            transition: background 0.2s;
        }}
        .header a:hover {{
            background: rgba(255,255,255,0.3);
        }}
        .container {{
            padding: 32px;
            max-width: 1600px;
            margin: 0 auto;
        }}
        .tabs {{
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            flex-wrap: wrap;
        }}
        .tab {{
            padding: 10px 20px;
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
        }}
        .tab:hover {{
            background: #f8f9fa;
            border-color: #667eea;
        }}
        .tab.active {{
            background: #667eea;
            color: white;
            border-color: #667eea;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
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
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
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
        .squad-role.rotation {{ background: #f8d7da; color: #721c24; }}
        .squad-role.bench {{ background: #e2e3e4; color: #383d41; }}
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
    </style>


\n<script src="/icons/status-icons.js"></script>
</head>
<body>
    <div class="header">
        <h1>
            {team_name}
            {coach_html}
        </h1>
        <a href="/lineup_ai/select">← Back to teams</a>
    </div>

    <div class="container">
        <div class="tabs">
            <div class="tab active">Squad</div>
            <div class="tab">Fixtures</div>
            <div class="tab">Results</div>
            <div class="tab">Statistics</div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{squad_size}</div>
                <div class="stat-label">Squad Size</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{avg_age}</div>
                <div class="stat-label">Average Age</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_value:.1f}m</div>
                <div class="stat-label">Total Value</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_goals}</div>
                <div class="stat-label">Total Goals</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{starting_xi_impact_score:.2f}</div>
                <div class="stat-label">Starting XI Impact Score</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{av_age_starting_xi:.1f}</div>
                <div class="stat-label">Av.Age Starting XI</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_red}</div>
                <div class="stat-label">Red Cards</div>
            </div>
        </div>

        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Nat</th>
                        <th>Player</th>
                        <th>Status</th>
                        <th>Age</th>
                        <th>MV</th>
                        <th>Pos</th>
                        <th>Squad<br>Role</th>
                        <th>Impact<br>Score</th>
                        <th style="text-align:center;">Squad<br>List</th>
                        <th style="text-align:center;">Possible XI<br><span id="xi-counter" style="color:#667eea;font-size:10px;">0/11</span></th>
                        <th style="text-align:center;">Starting XI<br><span id="starting-counter" style="color:#dc3545;font-size:10px;">0/11</span></th>
                        <th>Last 3</th>
                        <th style="text-align:center;">Apps</th>
                        <th style="text-align:center;">Min</th>
                        <th>G</th>
                        <th>A</th>
                        <th>YC</th>
                        <th>RC</th>
                    </tr>
                </thead>
                <tbody>
                    {players_rows}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        document.querySelectorAll('.tab').forEach(tab => {{
            tab.addEventListener('click', () => {{
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
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
        
        // Initialize counters
        updateXICounter(null);
        updateStartingCounter(null);
        

    </script>
</body>
</html>"""
    
    return HTMLResponse(html)
