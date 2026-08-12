"""Add more substitution markers."""
path = "/home/openclaw/telegram-mirror/bot.py"
with open(path) as f:
    src = f.read()

old = '''SUBST_MARKERS = (
    "\\U0001F501",
    "Замена",
    "Substit",
    "substit",
)'''

new = '''SUBST_MARKERS = (
    "\\U0001F501",          # 🔁
    "Замена",                 # Russian singular
    "Замены",                 # Russian plural
    "Substit",                # English "Substitution"/"Substituted"
    "substit",
    "Replace",                # "Replaced by"
    "replace",
    "Changes",                # "Changes for [Team]"
)'''

count = src.count(old)
print(f"Found {count}")
if count != 1:
    print("ERROR")
    import sys
    sys.exit(1)

src = src.replace(old, new, 1)
with open(path, "w") as f:
    f.write(src)
print("OK")