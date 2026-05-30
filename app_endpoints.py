
# ═══════════════════════════════════════════════════════════════
#  ВСТАВИТЬ В app.py после route /lineup_ai/view/{team_id}
#  Три endpoint: save / load / refresh
# ═══════════════════════════════════════════════════════════════


@app.post("/lineup_ai/save/{team_id}", response_class=JSONResponse)
async def lineup_save_state(team_id: str, request: Request):
    """Сохраняет статусы + чекбоксы для текущего пользователя.
    Данные изолированы: каждый пользователь видит только свои."""
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    save_name = str(body.get("save_name", "Default"))[:64].strip() or "Default"
    save_data_str = json.dumps(body.get("data", {}), ensure_ascii=False)
    ts = datetime.now(timezone.utc).isoformat()

    con = sqlite3.connect(DB_PATH)
    try:
        con.execute(
            """
            INSERT INTO user_lineup_saves
                (username, team_id, save_name, save_data, saved_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(username, team_id, save_name)
            DO UPDATE SET
                save_data = excluded.save_data,
                saved_at  = excluded.saved_at
            """,
            (username, team_id, save_name, save_data_str, ts)
        )
        con.commit()
    finally:
        con.close()

    return JSONResponse({"ok": True, "saved_at": ts})


@app.get("/lineup_ai/load/{team_id}", response_class=JSONResponse)
async def lineup_load_state(
    team_id: str,
    request: Request,
    save_name: str = "Default"
):
    """Загружает сохранение + список всех сохранений пользователя.
    save_name='__none__' вернёт только список без данных."""
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")

    con = sqlite3.connect(DB_PATH)
    try:
        saves_list = [
            {"name": r[0], "saved_at": r[1]}
            for r in con.execute(
                """SELECT save_name, saved_at
                   FROM user_lineup_saves
                   WHERE username=? AND team_id=?
                   ORDER BY saved_at DESC""",
                (username, team_id)
            ).fetchall()
        ]

        if save_name == "__none__":
            return JSONResponse({"ok": False, "data": None, "saves": saves_list})

        row = con.execute(
            """SELECT save_data, saved_at
               FROM user_lineup_saves
               WHERE username=? AND team_id=? AND save_name=?""",
            (username, team_id, save_name)
        ).fetchone()
    finally:
        con.close()

    if not row:
        return JSONResponse({"ok": False, "data": None, "saves": saves_list})

    try:
        data = json.loads(row[0])
    except Exception:
        data = {}

    return JSONResponse({
        "ok": True,
        "data": data,
        "saved_at": row[1],
        "saves": saves_list
    })


@app.post("/lineup_ai/refresh/{team_id}")
async def lineup_refresh_cache(team_id: str, request: Request):
    """Сбрасывает live-кэш команды.
    Следующий открытый запрос пересоздаст кэш со свежими данными от Soccerway."""
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    live_cache_path = os.path.join(DATA_DIR, f"_live_cache_{team_id}.json")

    if os.path.exists(live_cache_path):
        try:
            os.remove(live_cache_path)
        except OSError as e:
            # Не критично — логируем и продолжаем
            pass

    from fastapi.responses import RedirectResponse
    return RedirectResponse(
        url=f"/lineup_ai/view/{team_id}?refreshed=1",
        status_code=303
    )
