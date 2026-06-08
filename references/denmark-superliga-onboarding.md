# Denmark Superliga onboarding from Soccerway standings/overall

## Source URL
- `https://www.soccerway.com/denmark/superliga/standings/b3gDmFWi/standings/overall/`
- League page: 12 teams as of 2026-06-08.

## Extraction method
Curl-based ZA-chunk parsing. Two ZA chunks present, both identical (12 teams, full standings):
- Chunk 1: pos=366126, size=6926
- Chunk 2: pos=373052, size=145630 (largest, use this for full data)

## Teams captured (12)

| Name | ID | Official slug |
| --- | --- | --- |
| Aarhus | OOXnKGbO | aarhus |
| Brondby | 67R5vKqt | brondby |
| FC Copenhagen | hSPZwbEh | *** |
| Horsens | WIOwwITb | horsens |
| Lyngby | tjPFkxq5 | lyngby |
| Midtjylland | 8GZDmdbB | midtjylland |
| Nordsjaelland | 2wZHnGDH | nordsjaelland |
| Odense | tUXLozTN | odense |
| Randers FC | x0NnnfrU | randers-fc |
| Silkeborg | 4dCl8IE5 | silkeborg |
| Sonderjyske | 42ectuVa | sonderjyske |
| Viborg | v99EsEjo | viborg |

## FC Copenhagen slug pitfall

**Special case**: Soccerway returns `WU÷***¬` (literal `***`) for FC Copenhagen's slug in the ZA chunk. The squad URL `https://us.soccerway.com/team/***/hSPZwbEh/squad/` returns HTTP 200 — Soccerway accepts `***` as a wildcard for this team. None of the conventional slugs work (`fc-kobenhavn`, `kobenhavn`, `copenhagen`, `fck`, `f-c-k`, `fck-kobenhavn`, `københavn`, `f-c-københavn` — all 404).

**Decision**: store slug as `"***"` in `leagues_data.json`. The team ID `hSPZwbEh` is unique, so URL construction in `fetch_team.py` produces a working URL: `f'{BASE}/team/***/{team_id}/squad/'`.

All 12 squad URLs verified HTTP 200.

Insert into `leagues_data.json` as country key `Denmark` placed alphabetically between `Belgium` and `England`.

## league_mapping

`denmark_superliga` is already in `lineup_data_complete.py` (pre-existing mapping) — no change needed.

```python
"denmark_superliga": ("Denmark", "Superliga"),
```

## Prefill

```bash
cd /home/openclaw/FormAlert
nohup .venv/bin/python3 -u prefill_league_cache.py "Denmark" "Superliga" \
  > /tmp/prefill_dk.log 2>&1 &
```
