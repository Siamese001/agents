#!/usr/bin/env python3
import re
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Usage: validate_self_contained_html.py <file.html>")
        return 2
    p = Path(sys.argv[1])
    text = p.read_text(encoding="utf-8")
    errors = []
    low = text.lower()
    for required in ("<!doctype html", "<html", "<head", "<body"):
        if required not in low: errors.append(f"missing {required}")
    if 'name="viewport"' not in low and "name='viewport'" not in low:
        errors.append("missing responsive viewport meta tag")
    external = re.findall(r'(?:src|href)=["\']https?://', text, flags=re.I)
    if external: errors.append("external http(s) dependencies detected")
    if "<title" not in low: errors.append("missing document title")
    if errors:
        for e in errors: print(f"ERROR: {e}")
        return 1
    print(f"OK: {p}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
