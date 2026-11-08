#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

ROUTES = {
    "miro-board-writer": {"miro": 12, "whiteboard": 5, "editable": 3, "direct": 5},
    "figma-canvas-writer": {"figma": 12, "figjam": 12, "whiteboard": 4, "pixel": 6, "editable": 5, "direct": 5},
    "slides": {"powerpoint": 12, "presentation": 9, "pixel": 5, "editable": 5, "microsoft": 4},
    "widescreen-svg-studio": {"pixel": 9, "presentation": 5, "portable": 8, "editable": 4},
    "drawio-diagram": {"technical": 9, "portable": 6, "editable": 9},
    "excalidraw-diagram": {"whiteboard": 9, "portable": 8, "editable": 9},
    "mermaid-architecture": {"technical": 10, "portable": 8, "editable": 8},
    "interactive-architecture": {"technical": 6, "interactive": 10, "portable": 7},
    "interactive-walkthrough": {"interactive": 10, "portable": 7},
    "frontend-storytelling": {"interactive": 7, "pixel": 8, "portable": 7},
}


def score(req):
    target = (req.get("target_app") or "none").lower()
    needs = req.get("needs", {})
    constraints = req.get("constraints", {})
    scored = []
    for name, weights in ROUTES.items():
        s = weights.get(target, 0)
        s += weights.get("presentation", 0) if needs.get("presentation") else 0
        s += weights.get("whiteboard", 0) if needs.get("whiteboard") else 0
        s += weights.get("technical", 0) if needs.get("technical_truth") else 0
        s += weights.get("interactive", 0) if needs.get("interactive") else 0
        s += weights.get("pixel", 0) if needs.get("pixel_polish") else 0
        s += weights.get("editable", 0) if needs.get("editable") else 0
        s += weights.get("portable", 0) if needs.get("portable") else 0
        s += weights.get("microsoft", 0) if constraints.get("microsoft_first") else 0
        reasons = []
        blocked = False
        if name == "miro-board-writer" and target == "miro":
            if constraints.get("mcp_unavailable", True) and not constraints.get("miro_approved_auth", False):
                blocked = True
                reasons.append("Miro direct write requires approved non-MCP authorization")
        if name == "figma-canvas-writer" and target in {"figma", "figjam"}:
            if not constraints.get("figma_plugin_allowed", False):
                blocked = True
                reasons.append("Figma local/private plugin path is not approved")
        if needs.get("direct_write_required") and target in {"miro", "figma", "figjam", "powerpoint"}:
            s += weights.get("direct", 0)
        if blocked:
            s -= 100
        scored.append({"route": name, "score": s, "blocked": blocked, "reasons": reasons})
    return sorted(scored, key=lambda x: x["score"], reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("requirements")
    args = ap.parse_args()
    req = json.loads(Path(args.requirements).read_text())
    print(json.dumps(score(req), indent=2))

if __name__ == "__main__":
    main()
