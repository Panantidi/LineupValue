"""Add detailed logging for substitution filter."""
path = "/home/openclaw/telegram-mirror/bot.py"
with open(path) as f:
    src = f.read()

old = '''def should_forward(text: str) -> bool:
    if not text:
        return False
    if is_yellow_card(text):
        return True
    if is_red_card_explicit(text):
        return True
    if is_substitution(text):
        minute = extract_minute(text)
        if 0 <= minute <= SUBST_MINUTE_LIMIT:
            return True
    return False'''

new = '''def should_forward(text: str) -> bool:
    if not text:
        return False
    if is_yellow_card(text):
        log.debug(f"Filter: yellow card match")
        return True
    if is_red_card_explicit(text):
        log.debug(f"Filter: red card match")
        return True
    if is_substitution(text):
        minute = extract_minute(text)
        # Aug 7 2026: Log every substitution attempt so we can audit the 30' cutoff.
        if minute == -1:
            log.info(f"Filter: sub marker found but no minute parsed: {text[:120]!r}")
            return False
        if minute <= SUBST_MINUTE_LIMIT:
            log.info(f"Filter: sub {minute}' <= {SUBST_MINUTE_LIMIT}' PASS: {text[:120]!r}")
            return True
        log.info(f"Filter: sub {minute}' > {SUBST_MINUTE_LIMIT}' SKIP: {text[:120]!r}")
        return False
    return False'''

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