#!/usr/bin/env python3
import sys
from pathlib import Path

STARTERS = (
    "flowchart ", "graph ", "sequenceDiagram", "stateDiagram", "stateDiagram-v2",
    "classDiagram", "erDiagram", "journey", "gantt", "pie", "timeline", "mindmap"
)

def main():
    if len(sys.argv) != 2:
        print("Usage: check_mermaid.py <file.mmd>")
        return 2
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8").strip()
    errors = []
    if not text: errors.append("file is empty")
    first = text.splitlines()[0].strip() if text else ""
    if text and not any(first.startswith(s) for s in STARTERS):
        errors.append(f"unrecognized Mermaid diagram header: {first}")
    pairs = [("[", "]"), ("(", ")"), ("{", "}")]
    for a, b in pairs:
        if text.count(a) != text.count(b):
            errors.append(f"unbalanced {a}{b} delimiters")
    if errors:
        for e in errors: print(f"ERROR: {e}")
        return 1
    print(f"OK: {path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
