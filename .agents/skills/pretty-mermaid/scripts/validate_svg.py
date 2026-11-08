#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Usage: validate_svg.py <file.svg>")
        return 2
    p = Path(sys.argv[1])
    try:
        root = ET.fromstring(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: invalid SVG/XML: {e}")
        return 1
    errors = []
    tag = root.tag.split('}')[-1]
    if tag != "svg": errors.append("root element must be svg")
    if not root.get("viewBox"): errors.append("missing viewBox")
    children = [c.tag.split('}')[-1] for c in root]
    if "title" not in children: errors.append("missing <title>")
    if "desc" not in children: errors.append("missing <desc>")
    text = p.read_text(encoding="utf-8").lower()
    if "http://" in text or "https://" in text:
        # xmlns is allowed; reject other remote references conservatively.
        cleaned = text.replace('http://www.w3.org/2000/svg', '')
        if "http://" in cleaned or "https://" in cleaned:
            errors.append("external URL detected")
    if errors:
        for e in errors: print(f"ERROR: {e}")
        return 1
    print(f"OK: {p}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
