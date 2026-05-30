// ════════════════════════════════════════════════════
//   SAVE / LOAD lineup state
//   Вставить ПЕРЕД закрывающим </script> в lineup_team_view.py
//
//   ВАЖНО: в Python f-string замени строку:
//     const _TEAM_ID = "{{team_id}}";
//   (двойные {{ }} в f-string станут одинарными { })
// ════════════════════════════════════════════════════

const _TEAM_ID = "{{team_id}}";  // ← Python подставит реальный ID

// ────────────────────────────────
//  Сбор состояния страницы
// ────────────────────────────────
function _collectState() {{
    const s = {{ statuses: {{}}, squad: [], pxi: [], sxi: [] }};
    document.querySelectorAll(".main-table tbody tr[data-last]").forEach(row => {{
        const nc = row.querySelector(".player-name strong");
        if (!nc) return;
        const name = nc.textContent.replace(/[\u26BD\u1F97F⚽️👟]/gu, "").trim();
        if (!name) return;

        const sel = row.querySelector(".status-select");
        if (sel) s.statuses[name] = sel.value;

        if (row.querySelector(".squad-checkbox:checked")) s.squad.push(name);
        if (row.querySelector(".xi-checkbox:checked"))    s.pxi.push(name);
        if (row.querySelector(".starting-checkbox:checked")) s.sxi.push(name);
    }});
    return s;
}}

// ────────────────────────────────
//  Применение сохранённого состояния
// ────────────────────────────────
function _applyState(s) {{
    if (!s) return;

    document.querySelectorAll(".main-table tbody tr[data-last]").forEach(row => {{
        const nc = row.querySelector(".player-name strong");
        if (!nc) return;
        const name = nc.textContent.replace(/[\u26BD\u1F97F⚽️👟]/gu, "").trim();
        if (!name) return;

        // Статус
        if (s.statuses && s.statuses[name] !== undefined) {{
            const sel = row.querySelector(".status-select");
            if (sel) {{ sel.value = s.statuses[name]; updateStatusIcon(sel); }}
        }}

        // Squad checkbox
        const sqCb = row.querySelector(".squad-checkbox");
        if (sqCb) {{
            sqCb.checked = (s.squad || []).includes(name);
            sqCb.style.background = sqCb.checked ? "#000" : "#e0e0e0";
            sqCb.style.border = sqCb.checked ? "none" : "2px solid #333";
        }}

        // P-XI checkbox
        const xiCb = row.querySelector(".xi-checkbox");
        if (xiCb) {{
            xiCb.checked = (s.pxi || []).includes(name);
            xiCb.style.background = xiCb.checked ? "#667eea" : "#e0e0e0";
            xiCb.style.border = "2px solid #667eea";
        }}

        // S-XI checkbox
        const stCb = row.querySelector(".starting-checkbox");
        if (stCb) {{
            stCb.checked = (s.sxi || []).includes(name);
            stCb.style.background = stCb.checked ? "#dc3545" : "#e0e0e0";
            stCb.style.border = "2px solid #dc3545";
        }}
    }});

    // Пересчёт счётчиков P-XI и S-XI
    let xiN = 0, sxiN = 0;
    document.querySelectorAll(".xi-checkbox:checked").forEach(() => xiN++);
    document.querySelectorAll(".starting-checkbox:checked").forEach(() => sxiN++);

    const xiEl = document.getElementById("xi-counter");
    if (xiEl) xiEl.textContent = xiN + "/11";
    const sxiEl = document.getElementById("starting-counter");
    if (sxiEl) sxiEl.textContent = sxiN + "/11";

    // Пересчитать таблицы сравнения если функции существуют
    if (typeof updateXIStats === "function") updateXIStats();
    if (typeof updateStartingXIStats === "function") updateStartingXIStats();
}}

// ────────────────────────────────
//  Утилита: статус-строка
// ────────────────────────────────
function _setSaveStatus(msg, ms = 3000) {{
    const el = document.getElementById("save-status");
    if (!el) return;
    el.textContent = msg;
    if (ms > 0) setTimeout(() => el.textContent = "", ms);
}}

// ────────────────────────────────
//  СОХРАНИТЬ
// ────────────────────────────────
async function saveLineupState() {{
    const saveName = (document.getElementById("save-name-input")?.value || "Default").trim() || "Default";
    _setSaveStatus("⏳ Сохраняю...", 0);
    try {{
        const r = await fetch("/lineup_ai/save/" + _TEAM_ID, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ save_name: saveName, data: _collectState() }})
        }});
        const j = await r.json();
        _setSaveStatus(j.ok ? "✅ Готово" : "❌ Ошибка");
        if (j.ok) await loadSavesList();
    }} catch (e) {{
        _setSaveStatus("❌ " + (e.message || "Ошибка сети"));
    }}
}}

// ────────────────────────────────
//  ЗАГРУЗИТЬ
// ────────────────────────────────
async function loadLineupState(saveName) {{
    const name = (saveName || "Default").trim() || "Default";
    _setSaveStatus("⏳ Загружаю...", 0);
    try {{
        const r = await fetch(
            "/lineup_ai/load/" + _TEAM_ID + "?save_name=" + encodeURIComponent(name)
        );
        const j = await r.json();
        if (j.ok && j.data) {{
            _applyState(j.data);
            _setSaveStatus("✅ Загружено");
        }} else {{
            _setSaveStatus("ℹ️ Нет сохранения");
        }}
        _renderSavesList(j.saves || []);
    }} catch (e) {{
        _setSaveStatus("❌ " + (e.message || "Ошибка сети"));
    }}
}}

// ────────────────────────────────
//  Обновить список сохранений
// ────────────────────────────────
async function loadSavesList() {{
    try {{
        const r = await fetch("/lineup_ai/load/" + _TEAM_ID + "?save_name=__none__");
        const j = await r.json();
        _renderSavesList(j.saves || []);
    }} catch (e) {{}}
}}

// ────────────────────────────────
//  Рендер списка сохранений
// ────────────────────────────────
function _renderSavesList(saves) {{
    const block = document.getElementById("saves-list-block");
    const items = document.getElementById("saves-list-items");
    if (!block || !items) return;

    if (!saves || !saves.length) {{
        block.style.display = "none";
        return;
    }}
    block.style.display = "block";

    items.innerHTML = saves.map(s => {{
        const dt = s.saved_at
            ? new Date(s.saved_at).toLocaleString("ru-RU", {{
                day: "2-digit", month: "2-digit",
                hour: "2-digit", minute: "2-digit"
              }})
            : "";
        const esc = s.name.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
        return `<div
            onclick="document.getElementById('save-name-input').value='${{esc}}';
                     loadLineupState('${{esc}}');"
            style="padding:5px 7px;border:1px solid #eee;border-radius:6px;
                   cursor:pointer;font-size:10px;background:#fafafa;
                   transition:background 0.12s;"
            onmouseenter="this.style.background='#f0f0f0'"
            onmouseleave="this.style.background='#fafafa'">
            <b style="color:#333;">${{s.name}}</b>
            <span style="float:right;color:#bbb;font-size:9px;">${{dt}}</span>
        </div>`;
    }}).join("");
}}

// ────────────────────────────────
//  Автозагрузка "Default" при открытии
// ────────────────────────────────
(async function _autoLoad() {{
    try {{
        const r = await fetch("/lineup_ai/load/" + _TEAM_ID + "?save_name=Default");
        const j = await r.json();
        if (j.ok && j.data) {{
            _applyState(j.data);
        }}
        _renderSavesList(j.saves || []);
    }} catch (e) {{
        // Тихий фейл — нет сохранения или нет сети
    }}
}})();
