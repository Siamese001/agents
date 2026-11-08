#!/usr/bin/env python3
import re
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Usage: validate_walkthrough.py <file.html>")
        return 2
    p = Path(sys.argv[1])
    t = p.read_text(encoding="utf-8")
    low = t.lower()
    errors = []
    if "<svg" not in low: errors.append("missing inline SVG overview map")
    if "<script" not in low: errors.append("missing interaction script")
    if "<title" not in low: errors.append("missing document title")
    if re.search(r'(?:src|href)=["\']https?://', t, flags=re.I):
        errors.append("external http(s) dependency detected")
    if "tabindex" not in low and "<button" not in low:
        errors.append("no obvious keyboard-focusable interactive nodes")
    if errors:
        for e in errors: print(f"ERROR: {e}")
        return 1
    print(f"OK: {p}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
