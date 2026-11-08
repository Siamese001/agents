#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Usage: validate_drawio.py <file.drawio>")
        return 2
    path = Path(sys.argv[1])
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: invalid XML: {e}")
        return 1
    errors = []
    if root.tag != "mxfile": errors.append("root element must be mxfile")
    diagrams = root.findall("diagram")
    if not diagrams: errors.append("missing diagram element")
    ids = set()
    for cell in root.iter("mxCell"):
        cid = cell.get("id")
        if not cid: errors.append("mxCell missing id")
        elif cid in ids: errors.append(f"duplicate mxCell id: {cid}")
        else: ids.add(cid)
    if "0" not in ids or "1" not in ids:
        errors.append("reserved mxCell ids 0 and 1 are required")
    for cell in root.iter("mxCell"):
        for attr in ("source", "target", "parent"):
            ref = cell.get(attr)
            if ref and ref not in ids:
                errors.append(f"cell {cell.get('id')} {attr} references missing id {ref}")
    if errors:
        for e in errors: print(f"ERROR: {e}")
        return 1
    print(f"OK: {path} ({len(ids)} cells)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
