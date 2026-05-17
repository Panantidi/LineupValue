import json, glob, os
from fastapi.responses import HTMLResponse

async def get_lineup_teams():
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    teams = []
    pattern = DATA_DIR + "/lineup_ai_*.json"
    for f in glob.glob(pattern):
        filename = os.path.basename(f)
        parts = filename.replace("lineup_ai_", "").replace(".json", "").split("_team_")
        if len(parts) == 2:
            league = parts[0]
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    teams.append({
                        "file": f,
                        "league": league.replace("-", " ").title(),
                        "team_name": data["team"]["name"],
                        "team_id": data["team"]["id"]
                    })
            except Exception:
                pass
    return sorted(teams, key=lambda x: (x["league"], x["team_name"]))

async def lineup_view(team_id: str):
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    pattern = DATA_DIR + "/lineup_ai_*.json"
    team_data = None
    for f in glob.glob(pattern):
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                if data["team"]["id"] == team_id:
                    team_data = data
                    break
        except:
            continue
    if not team_data:
        return None
    
    players = team_data["players"]
    total_value = 0
    total_goals = 0
    avg_age = 0
    
    def safe_int(val):
        try:
            return int(val) if val != "—" else 0
        except:
            return 0
    
    for p in players:
        if p["market_value"] != "—":
            try:
                val = p["market_value"].replace("€", "").replace("m", "").replace("k", "")
                if "m" in p["market_value"]: total_value += float(val) * 1_000_000
                elif "k" in p["market_value"]: total_value += float(val) * 1_000
                else: total_value += float(val)
            except: pass
        total_goals += safe_int(p["goal"])
        avg_age += safe_int(p["age"])
    
    n_players = len(players)
    avg_age = avg_age / n_players if n_players > 0 else 0
    total_value_str = f"€{total_value/1_000_000:.1f}m" if total_value > 0 else "—"
    
    player_rows = []
    for p in players:
        status_dot = "⚪"
        if p["red_card"] and safe_int(p["red_card"]) > 0: status_dot = "🔴"
        elif p["yellow_card"] and safe_int(p["yellow_card"]) >= 10: status_dot = "🟠"
        
        last5_html = ""
        for last in p["last5"]:
            if last == "START": last5_html += "<span style='color: #4CAF50; font-weight: bold;'>✓</span>"
            elif last == "SUB": last5_html += "<span style='color: #FF9800;'>△</span>"
            elif last == "—": last5_html += "<span style='color: #999;'>—</span>"
            else: last5_html += "<span style='color: #999;'>?</span>"
        
        row = f"""<tr>
            <td>{p["number"]}</td>
            <td>{p["name"]}</td>
            <td><img src="{p['national']['flag']}" width="20" style="vertical-align: middle;"> {p["national"]["code"]}</td>
            <td>{p["position"]}</td>
            <td>{safe_int(p["age"])}</td>
            <td>{status_dot}</td>
            <td>{p["market_value"]}</td>
            <td>{safe_int(p["apps"])}</td>
            <td>{safe_int(p["goal"])}</td>
            <td>{safe_int(p["assist"])}</td>
            <td>{safe_int(p["yellow_card"])}</td>
            <td>{safe_int(p["red_card"])}</td>
            <td>{last5_html}</td>
        </tr>"""
        player_rows.append(row)
    
    player_rows_html = "\n".join(player_rows)
    
    html = f"""<!doctype html>
    <html>
    <head><meta charset="utf-8"><title>{team_data["team"]["name"]} - Squad | LineUp AI</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #fff; }}
        .header {{ background: #1a73e8; color: white; padding: 20px 40px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .header a {{ color: white; text-decoration: none; margin-left: 20px; }}
        .container {{ padding: 40px; max-width: 1400px; margin: 0 auto; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 40px; }}
        .stat-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 28px; font-weight: bold; color: #1a73e8; }}
        .stat-label {{ font-size: 12px; color: #666; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th {{ background: #f1f3f4; padding: 12px; text-align: left; font-size: 13px; color: #444; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #eee; font-size: 14px; }}
        tr:hover {{ background: #f8f9fa; }}
    </style>
    </head>
    <body>
        <div class="header"><h1>{team_data["team"]["name"]} <a href="/lineup_ai">← Back</a></h1></div>
        <div class="container">
            <h2>📊 Squad Overview</h2>
            <div class="stats">
                <div class="stat-card"><div class="stat-value">{n_players}</div><div class="stat-label">Players</div></div>
                <div class="stat-card"><div class="stat-value">{avg_age:.1f}</div><div class="stat-label">Avg Age</div></div>
                <div class="stat-card"><div class="stat-value">{total_value_str}</div><div class="stat-label">Total Value</div></div>
                <div class="stat-card"><div class="stat-value">{total_goals}</div><div class="stat-label">Total Goals</div></div>
            </div>
            <table><thead><tr>
                <th>#</th><th>Player</th><th>Nation</th><th>Pos</th><th>Age</th><th>Status</th>
                <th>Value</th><th>Apps</th><th>G</th><th>A</th><th>YC</th><th>RC</th><th>Last 5</th>
            </tr></thead><tbody>{player_rows_html}</tbody></table>
        </div>
    </body>
    </html>"""
    return HTMLResponse(html)

@app = None  # Will be set by app.py
