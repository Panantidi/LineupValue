#!/bin/bash
# Batch fetch last3+lineups for all teams
cd /home/openclaw/FormAlert

TEAMS=(
"SAlF91iL:Angers"
"MTLr36WA:Auxerre"
"Cr4VGaUl:Brest"
"CIEe04GT:Le Havre"
"IBmris38:Lens"
"pfDZL71o:Lille"
"jgNAYRGi:Lorient"
"2akflumR:Lyon"
"SblU3Hee:Marseille"
"4v0yqlWc:Metz"
"2PIvr8o4:Monaco"
"veuetnGG:Nantes"
"YagoQJpq:Nice"
"CjhkPw0k:PSG"
"0OEHEprs:Paris FC"
"d2nnj1IE:Rennes"
"nP6UzIU1:Strasbourg"
"MLmY2yB1:Toulouse"
"Iw7eKK25:Inter"
"69Dxbc61:Napoli"
"8Sa8HInO:AC Milan"
"zVqqL0ma:AS Roma"
"ttyLthOA:Como"
"C06aJvIB:Juventus"
"8C9JjMXu:Atalanta"
"0M9xNN8N:Bologna"
"URcSl02h:Lazio"
"rXw8YKDE:Udinese"
"QDdvI0zl:Sassuolo"
"MZFZnvX4:Torino"
"6DxlaxHN:Parma"
"d0PJxeie:Genoa"
"Q3A3IbXH:Fiorentina"
"SCGVmKHb:Cagliari"
"G8lYsMgU:Lecce"
"KUzfp5N3:Cremonese"
"rJVAIaHo:Verona"
"roasMsOT:Pisa"
"SKbpVP5K:Barcelona"
"W8mj7MDD:Real Madrid"
"lUatW5jE:Villarreal"
"jaarqpLQ:Atl. Madrid"
"vJbTeCGP:Betis"
"8pvUZFhf:Celta Vigo"
"dboeiWOt:Getafe"
"8bcjFy6O:Rayo Vallecano"
"CQeaytrD:Valencia"
"jNvak2f3:Real Sociedad"
"QFfPdh1J:Espanyol"
"IP5zl0cJ:Ath Bilbao"
"h8oAv4Ts:Sevilla"
"hxt57t2q:Alaves"
"G8FL0ShI:Levante"
"ETdxjU8a:Osasuna"
"4jl02tPF:Elche"
"nNNpcUSL:Girona"
"4jDQxrbf:Mallorca"
"SzYzw34K:Oviedo"
)

TOTAL=${#TEAMS[@]}
OK=0
FAIL=0
FAIL_LIST=""

for entry in "${TEAMS[@]}"; do
    TID="${entry%%:*}"
    TNAME="${entry#*:}"
    
    # Check if cache already has lineup data
    CACHE="/home/openclaw/.openclaw/workspace/_live_cache_${TID}.json"
    if [ -f "$CACHE" ]; then
        HAS_LINEUP=$(python3 -c "
import json
with open('$CACHE') as f:
    c = json.load(f)
for m in c.get('matches', []):
    if m.get('lineup'):
        print('yes')
        break
else:
    print('no')
" 2>/dev/null)
        if [ "$HAS_LINEUP" = "yes" ]; then
            echo "SKIP (already has lineups): $TNAME ($TID)"
            OK=$((OK+1))
            continue
        fi
    fi
    
    echo "[$(($OK+$FAIL+1))/$TOTAL] Fetching: $TNAME ($TID)..."
    
    timeout 180 .venv/bin/python3 -u fetch_team.py "$TID" --team-name "$TNAME" 2>&1
    RC=$?
    
    if [ $RC -eq 0 ]; then
        echo "  -> OK: $TNAME"
        OK=$((OK+1))
    else
        echo "  -> FAIL (rc=$RC): $TNAME"
        FAIL=$((FAIL+1))
        FAIL_LIST="$FAIL_LIST $TNAME($TID)"
    fi
done

echo ""
echo "========================================="
echo "DONE: $OK OK, $FAIL FAIL out of $TOTAL"
if [ -n "$FAIL_LIST" ]; then
    echo "Failed:$FAIL_LIST"
fi
