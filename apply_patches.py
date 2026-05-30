#!/usr/bin/env python3
"""Apply all patches from instruction to FormAlert"""
import re

with open("lineup_team_view.py", "r") as f:
    content = f.read()

# ============ STEP 1: Fix cache TTL ============
old_cache_pattern = (
    "    if os.path.exists(live_cache_path):\n"
    "        try:\n"
    "            with open(live_cache_path, 'r', encoding='utf-8') as f:\n"
    "                cached = json.load(f)\n"
    "            if True:  # always use live cache if exists\n"
    "                team_file = live_cache_path\n"
    "        except Exception:\n"
    "            pass"
)

new_cache = (
    "    LIVE_CACHE_TTL = 6 * 3600\n"
    "    cache_age_hours = 999.0\n"
    "\n"
    "    if os.path.exists(live_cache_path):\n"
    "        try:\n"
    "            age_s = _time.time() - os.path.getmtime(live_cache_path)\n"
    "            if age_s < LIVE_CACHE_TTL:\n"
    "                team_file = live_cache_path\n"
    "                cache_age_hours = age_s / 3600\n"
    "        except Exception:\n"
    "            pass"
)

if old_cache_pattern in content:
    content = content.replace(old_cache_pattern, new_cache)
    print("STEP 1: Cache TTL fix applied")
elif "LIVE_CACHE_TTL" in content:
    print("STEP 1: Already applied, skipping")
else:
    print("STEP 1: WARNING - cache block NOT found!")

# ============ STEP 2: Badge freshness ============
if "cache_badge" not in content:
    # Find the line with html = f""" and insert badge code before it
    badge_code = '''    # Badge freshness indicator
    if cache_age_hours < 1:
        cache_badge = "\\U0001f7e2 Свежие данные"
    elif cache_age_hours < 6:
        h = int(cache_age_hours)
        m = int((cache_age_hours - h) * 60)
        cache_badge = f"\\U0001f7e1 {h}ч {m}м назад"
    else:
        cache_badge = "\\U0001f534 Устарело — жми \\U0001f504"

'''
    # Insert before html = f"""
    html_marker = '    html = f"""\n'
    if html_marker in content:
        content = content.replace(html_marker, badge_code + html_marker)
        print("STEP 2: Badge code inserted")
    else:
        print("STEP 2: WARNING - html f-string marker not found!")
else:
    print("STEP 2: Already applied, skipping")

# ============ STEP 2b: Badge in HTML ============
badge_html = ' <span style="font-size:11px;background:rgba(255,255,255,0.18);padding:3px 10px;border-radius:12px;">{{cache_badge}}</span>'
h1_marker = "<h1>{team_name}</h1>"
if h1_marker in content and "cache_badge" not in content.split("<h1>{team_name}</h1>")[1][:200]:
    # Insert badge after h1
    content = content.replace(
        h1_marker,
        h1_marker + badge_html
    )
    print("STEP 2b: Badge HTML inserted after h1")
elif "cache_badge" in content.split("</h1>")[0][-200:]:
    print("STEP 2b: Already applied, skipping")
else:
    print("STEP 2b: WARNING - could not insert badge HTML")

# ============ STEP 3: Refresh button ============
refresh_btn = '''    <form method="post"
          action="/lineup_ai/refresh/{team_id}"
          style="display:inline;margin:0 4px 0 0;">
      <button type="submit"
              title="Обновить данные Last 3"
              style="background:none;border:1px solid rgba(255,255,255,0.4);border-radius:6px;cursor:pointer;font-size:20px;padding:3px 8px;color:white;">&#x1F504;</button>
    </form>
'''
btn_export_marker = 'class="btn-export"'
if "lineup_ai/refresh" not in content:
    # Find first occurrence of btn-export and insert before it
    idx = content.find(btn_export_marker)
    if idx > 0:
        # Find start of that line
        line_start = content.rfind('\n', 0, idx) + 1
        content = content[:line_start] + refresh_btn + content[line_start:]
        print("STEP 3: Refresh button inserted")
    else:
        print("STEP 3: WARNING - btn-export not found!")
else:
    print("STEP 3: Already applied, skipping")

# ============ STEP 4: Save panel HTML ============
with open("save_panel_block.html", "r") as f:
    save_panel_html = f.read()

main_layout_marker = '<div class="main-layout">'
if "save-panel" not in content:
    # Replace <div class="main-layout"> with itself + save panel
    content = content.replace(
        main_layout_marker + "\n",
        main_layout_marker + "\n" + save_panel_html + "\n",
        1  # only first occurrence
    )
    print("STEP 4: Save panel HTML inserted")
else:
    print("STEP 4: Already applied, skipping")

# ============ STEP 5: JavaScript save/load ============
with open("save_load.js", "r") as f:
    save_load_js = f.read()

# Fix the placeholder - since this is inside an f-string, we need {{team_id}}
save_load_js = save_load_js.replace('"__PLACEHOLDER__"', '"{{team_id}}"')

# Insert before </script> (last occurrence)
last_script_idx = content.rfind("</script>")
if last_script_idx > 0 and "saveSquadState" not in content:
    content = content[:last_script_idx] + "\n" + save_load_js + "\n" + content[last_script_idx:]
    print("STEP 5: JS save/load inserted")
else:
    print("STEP 5: Already applied or not found, skipping")

with open("lineup_team_view.py", "w") as f:
    f.write(content)

print("\n=== lineup_team_view.py patched ===")
