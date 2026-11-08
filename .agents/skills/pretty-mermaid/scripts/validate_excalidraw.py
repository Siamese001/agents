#!/usr/bin/env python3
import json
import math
import sys
from pathlib import Path


def fail(msg):
    print(f"ERROR: {msg}")
    return 1

def main():
    if len(sys.argv) != 2:
        print("Usage: validate_excalidraw.py <file.excalidraw>")
        return 2
    path = Path(sys.argv[1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return fail(f"invalid JSON: {e}")
    errors = []
    if data.get("type") != "excalidraw": errors.append("root type must be 'excalidraw'")
    if not isinstance(data.get("elements"), list): errors.append("elements must be a list")
    ids = set()
    for i, el in enumerate(data.get("elements", [])):
        eid = el.get("id")
        if not isinstance(eid, str) or not eid:
            errors.append(f"element {i} has missing/invalid id")
        elif eid in ids:
            errors.append(f"duplicate id: {eid}")
        else:
            ids.add(eid)
        for key in ("x", "y", "width", "height"):
            if key in el and (not isinstance(el[key], (int, float)) or not math.isfinite(el[key])):
                errors.append(f"element {eid or i} has invalid {key}")
    for el in data.get("elements", []):
        for bind_key in ("startBinding", "endBinding"):
            b = el.get(bind_key)
            if isinstance(b, dict):
                target = b.get("elementId")
                if target and target not in ids:
                    errors.append(f"{el.get('id')} {bind_key} references missing id {target}")
    if errors:
        for e in errors: print(f"ERROR: {e}")
        return 1
    print(f"OK: {path} ({len(ids)} elements)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
