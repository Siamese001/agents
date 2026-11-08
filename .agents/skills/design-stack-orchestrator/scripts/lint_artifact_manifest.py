#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

CURRENT = {"confirmed", "approved", "effective", "current", "active"}
UNCERTAIN = {"proposed", "conditional", "unresolved", "candidate"}
SECRET_PATTERNS = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+\-/]+=*"),
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def iter_nodes(obj, path="$", out=None):
    if out is None:
        out = []
    out.append((path, obj))
    if isinstance(obj, dict):
        for k, v in obj.items():
            iter_nodes(v, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            iter_nodes(v, f"{path}[{i}]", out)
    return out


def hex_rgb(value):
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"#?([0-9A-Fa-f]{6})", value.strip())
    if not m:
        return None
    s = m.group(1)
    return tuple(int(s[i:i+2], 16) / 255 for i in (0, 2, 4))


def luminance(rgb):
    vals = []
    for c in rgb:
        vals.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def lint(data):
    errors, warnings = [], []
    for path, value in iter_nodes(data):
        if isinstance(value, str):
            for pattern in SECRET_PATTERNS:
                if pattern.search(value):
                    errors.append({"path": path, "code": "possible_secret", "message": "Credential-like content detected"})
            if value.startswith("http://"):
                warnings.append({"path": path, "code": "insecure_url", "message": "Use HTTPS for production links"})
            if value.startswith("file://") or value.startswith("/mnt/") or value.startswith("/tmp/"):
                errors.append({"path": path, "code": "local_only_link", "message": "Local path cannot be a production link"})
        if isinstance(value, dict):
            status = str(value.get("status", "")).lower()
            if status in CURRENT:
                missing = [k for k in ("owner", "source", "last_verified") if not value.get(k)]
                if missing:
                    warnings.append({"path": path, "code": "provenance_gap", "message": "Current factual object missing: " + ", ".join(missing)})
            if status in UNCERTAIN and not value.get("hitl", False):
                warnings.append({"path": path, "code": "uncertainty_not_hitl", "message": "Uncertain content should be visibly HITL"})
            fg = hex_rgb(value.get("foreground") or value.get("text_color"))
            bg = hex_rgb(value.get("background") or value.get("background_color"))
            if fg and bg:
                ratio = contrast(fg, bg)
                if ratio < 3.0:
                    errors.append({"path": path, "code": "contrast_fail", "message": f"Contrast {ratio:.2f}:1 is below 3:1"})
                elif ratio < 4.5:
                    warnings.append({"path": path, "code": "contrast_watch", "message": f"Contrast {ratio:.2f}:1 may fail for normal text"})
    return {"errors": errors, "warnings": warnings, "status": "BLOCKED" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--output")
    args = ap.parse_args()
    data = json.loads(Path(args.manifest).read_text())
    result = lint(data)
    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        print(text)
    raise SystemExit(1 if result["errors"] else 0)

if __name__ == "__main__":
    main()
