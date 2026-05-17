#!/usr/bin/env python3
"""
LineUp AI UI - Simple web interface for viewing squad tables
Like Soccerway squad overview
"""

import os
import json
import glob
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="LineUp AI UI")
templates = Jinja2Templates(directory="templates")

DATA_DIR = "/home/openclaw/.openclaw/workspace"


def get_available_teams():
    """Get list of available team data files"""
    teams = []
    pattern = os.path.join(DATA_DIR, "lineup_ai_*.json")
    for f in glob.glob(pattern):
        filename = os.path.basename(f)
        # Extract team info from filename
        parts = filename.replace("lineup_ai_", "").replace(".json", "").split("_team_")
        if len(parts) == 2:
            league = parts[0]
            team_slug = parts[1]
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    teams.append({
                        "file": f,
                        "league": league.replace("-", " ").title(),
                        "team_name": data["team"]["name"],
                        "team_slug": team_slug,
                        "team_id": data["team"]["id"]
                    })
            except Exception:
                pass
    return sorted(teams, key=lambda x: (x["league"], x["team_name"]))


class SquadView(BaseModel):
    team: dict
    league: str
    players: list
    last5_matches: list
    squad_stats: dict


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, team_id: str = Query(None)):
    if not team_id:
        teams = get_available_teams()
        html = """
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>LineUp AI - Squad Overview</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
                       margin: 40px; background: #f5f5f5; }
                h1 { color: #333; }
                .team-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); 
                            gap: 20px; margin-top: 30px; }
                .team-card { background: white; padding: 20px; border-radius: 8px; 
                            box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-decoration: none;
                            color: inherit; transition: transform 0.2s; }
                .team-card:hover { transform: translateY(-2px); }
                .league { color: #888; font-size: 12px; text-transform: uppercase; }
                .team-name { font-size: 18px; font-weight: bold; margin-top: 5px; }
            </style>
        </head>
        <body>
            <h1>📊 LineUp AI - Squad Overview</h1>
            <p>Select a team to view squad</p>
            <div class="team-grid">
        """
        for t in teams:
            html += f'''
            <a href="?team_id={t["team_id"]}" class="team-card">
                <div class="league">{t["league"]}</div>
                <div class="team-name">{t["team_name"]}</div>
            </a>
            '''
        html += """
            </div>
        </body>
        </html>
        """
        return HTMLResponse(html)

    # Show squad table for specific team
    teams = get_available_teams()
    team_data = None
    for t in teams:
        if t["team_id"] == team_id:
            team_data = t
            break

    if not team_data:
        return HTMLResponse("<p>Team not found</p>", status_code=404)

    with open(team_data["file"], 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Calculate squad stats
    players = data["players"]
    total_value = 0
    total_apps = 0
    total_goals = 0
    starters = 0
    rotation = 0
    bench = 0
    avg_age = 0

    for p in players:
        if p["market_value"] != "—":
            try:
                val = p["market_value"].replace("€", "").replace("m", "").replace("k", "")
                if "m" in p["market_value"]:
                    total_value += float(val) * 1_000_000
                elif "k" in p["market_value"]:
                    total_value += float(val) * 1_000
                else:
                    total_value += float(val)
            except:
                pass
        total_apps += int(p["apps"]) if p["apps"].isdigit() else 0
        total_goals += int(p["goal"]) if p["goal"].isdigit() else 0
        avg_age += int(p["age"]) if p["age"].isdigit() else 0

        # Count by squad role
        role = "Starter"
        for last in p["last5"]:
            if last == "SUB":
                role = "Rotation"
                break
            elif last == "—":
                role = "Bench"

        if role == "Starter":
            starters += 1
        elif role == "Rotation":
            rotation += 1
        else:
            bench += 1

    n_players = len(players)
    avg_age = avg_age / n_players if n_players > 0 else 0
    total_value_str = f"€{total_value/1_000_000:.1f}m" if total_value > 0 else "—"

    # Build player table HTML
    player_rows = ""
    def safe_int(val):
        try:
            return int(val) if val != "—" else 0
        except:
            return 0

    for p in players:
        # Determine status indicator
        status_dot = "⚪"  # default
        if p["red_card"] and safe_int(p["red_card"]) > 0:
            status_dot = "🔴"  # red card
        elif p["yellow_card"] and safe_int(p["yellow_card"]) >= 10:
            status_dot = "🟠"  # suspension risk
        elif p["last5"] == ["—", "—", "—", "—", "—"]:
            status_dot = "⚫"  # inactive

        # Last 5 indicators
        last5_html = ""
        for last in p["last5"]:
            if last == "START":
                last5_html += "<span style='color: #4CAF50; font-weight: bold;'>✓</span>"
            elif last == "SUB":
                last5_html += "<span style='color: #FF9800;'>△</span>"
            elif last == "—":
                last5_html += "<span style='color: #999;'>—</span>"
            else:
                last5_html += "<span style='color: #999;'>?</span>"

        player_rows += f"""
        <tr>
            <td>{p["number"]}</td>
            <td>{p["name"]}</td>
            <td><img src="{p['national']['flag']}" width="20" style="vertical-align: middle;"> {p["national"]["code"]}</td>
            <td>{p["position"]}</td>
            <td>{p["age"]}</td>
            <td>{status_dot}</td>
            <td>{p["market_value"]}</td>
            <td>{p["apps"]}</td>
            <td>{p["goal"]}</td>
            <td>{p["assist"]}</td>
            <td>{p["yellow_card"]}</td>
            <td>{p["red_card"]}</td>
            <td>{last5_html}</td>
        </tr>
        """

    html = f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{data["team"]["name"]} - Squad | LineUp AI</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
                   margin: 0; background: #fff; }}
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
            .position {{ font-weight: bold; color: #666; }}
            .flag {{ vertical-align: middle; margin-right: 5px; }}
            @media (max-width: 768px) {{
                .stats {{ grid-template-columns: repeat(2, 1fr); }}
                table {{ font-size: 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>
                {data["team"]["name"]} 
                <a href="/">← Back to teams</a>
            </h1>
        </div>
        <div class="container">
            <h2>📊 Squad Overview</h2>
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">{n_players}</div>
                    <div class="stat-label">Players</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{avg_age:.1f}</div>
                    <div class="stat-label">Avg Age</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_value_str}</div>
                    <div class="stat-label">Total Value</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_goals}</div>
                    <div class="stat-label">Total Goals</div>
                </div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Player</th>
                        <th>Nation</th>
                        <th>Pos</th>
                        <th>Age</th>
                        <th>Status</th>
                        <th>Value</th>
                        <th>Apps</th>
                        <th>G</th>
                        <th>A</th>
                        <th>YC</th>
                        <th>RC</th>
                        <th>Last 5</th>
                    </tr>
                </thead>
                <tbody>
                    {player_rows}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
