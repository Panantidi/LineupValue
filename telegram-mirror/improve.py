"""Improve extract_minute to handle all apostrophe types + log all parsed minutes."""
path = "/home/openclaw/telegram-mirror/bot.py"
with open(path) as f:
    src = f.read()

# 1. Improve regex - add unicode apostrophes
old_extract = '''def extract_minute(text: str) -> int:
    m = re.search(r"(\\d+)(?:\\+\\d+)?\\s*['\\u2032\\u2019]", text)
    if m:
        return int(m.group(1))
    return -1'''

new_extract = '''def extract_minute(text: str) -> int:
    # Aug 7 2026: match minute marker in all common apostrophe variants:
    # ASCII (\\'), right single quote (\\u2019), prime (\\u2032), modifier letter prime (\\u02B9),
    # fullwidth apostrophe (\\uFF07), and even the typographic \\u2032.
    pat = (
        r"(\\d+)"                     # minute digits
        r"(?:\\+\\d+)?"                # optional added time (45+2)
        r"\\s*"
        r"['\\u02B9\\u2032\\u2019\\uFF07\\u2035\\u2033]"  # any apostrophe variant
    )
    m = re.search(pat, text)
    if m:
        return int(m.group(1))
    return -1'''

count = src.count(old_extract)
print(f"Found {count}")
if count != 1:
    print("ERROR")
    import sys
    sys.exit(1)

src = src.replace(old_extract, new_extract, 1)

# 2. Add log of source text in handle() when message is forwarded
old_handle = '''        try:
            if not should_forward(text):
                log.info(f"Skip msg id={msg.id} (no match)")
                return
            log.info(f"Forward msg id={msg.id} {SOURCE_CHANNEL} -> {TARGET_CHANNEL}")'''

new_handle = '''        try:
            if not should_forward(text):
                log.info(f"Skip msg id={msg.id} (no match): {text[:120]!r}")
                return
            log.info(f"Forward msg id={msg.id} {SOURCE_CHANNEL} -> {TARGET_CHANNEL}: {text[:120]!r}")'''

count = src.count(old_handle)
print(f"Handle found {count}")
if count != 1:
    print("ERROR")
    import sys
    sys.exit(1)

src = src.replace(old_handle, new_handle, 1)
with open(path, "w") as f:
    f.write(src)
print("OK")