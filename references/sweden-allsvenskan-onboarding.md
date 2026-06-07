# Sweden Allsvenskan onboarding from Soccerway standings/overall

## Source URL
- `https://www.soccerway.com/sweden/allsvenskan/standings/ltrtRhko/standings/overall/`
- League page: 16 teams as of 2026-06-07.

## Extraction method
Curl-based ZA-chunk parsing. The HTML contains **4 separate ZA chunks** for "SWEDEN: Allsvenskan":

| Chunk | Pos | Size | CX count | Notes |
| --- | --- | --- | --- | --- |
| 1 | 365399 | 6064 | 13 | partial subgroup |
| 2 | 371463 | 6516 | 15 | partial subgroup |
| 3 | 377979 | 31123 | 16 | full standings |
| 4 | 409102 | 144502 | 16 | full standings (largest, includes extra data) |

**Pitfall**: chunks 1 and 2 are smaller subgroup views (championship/relegation groups) and only contain a subset of the 16 teams. The full team list is in chunks 3 and 4 (both contain all 16 CX names). Always pick the **largest** chunk or one that has 16 CX entries to get the complete league roster.

All 16 squads verified HTTP 200.

## Teams captured (16)

| Name | ID | Official slug |
| --- | --- | --- |
| AIK | lzqk4S68 | aik |
| Brommapojkarna | ELVAW0WQ | brommapojkarna |
| Degerfors | zNSwBuue | degerfors |
| Djurgarden | 4Kh5hPE1 | djurgarden |
| Elfsborg | rBi9iqU7 | elfsborg |
| GAIS | bJewAOTf | gais |
| Goteborg | UovQtopk | ifk-goteborg |
| Hacken | W6u0d7B3 | hacken |
| Halmstad | Mmsc26yL | halmstad |
| Hammarby | SQsg3nME | hammarby |
| Kalmar | rkrUu5ae | kalmar |
| Malmo FF | tYNTdpar | malmo-ff |
| Mjallby | S0XtXM1E | mjallby |
| Orgryte | CGT7Kq4j | orgryte |
| Sirius | vXr8fotG | sirius |
| Vasteras SK | l8oLwJhB | vasteras-sk |

Insert into `leagues_data.json` as country key `Sweden` placed alphabetically between `Spain` and `Switzerland`.

## league_mapping

`sweden_allsvenskan` is already in `lineup_data_complete.py` (pre-existing mapping) — no change needed.

```python
"sweden_allsvenskan": ("Sweden", "Allsvenskan"),
```

## Prefill

```bash
cd /home/openclaw/FormAlert
nohup .venv/bin/python3 -u prefill_league_cache.py "Sweden" "Allsvenskan" \
  > /tmp/prefill_se.log 2>&1 &
```
