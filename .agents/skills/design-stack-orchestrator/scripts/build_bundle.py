#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

EXCLUDE_NAMES = {".DS_Store", "Thumbs.db"}
EXCLUDE_SUFFIXES = {".woff", ".woff2", ".ttf", ".otf"}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_file(path):
    if path.name in EXCLUDE_NAMES or path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    lower = path.name.lower()
    if lower in {".env", "credentials.json", "secrets.json"} or lower.endswith(".pem") or lower.endswith(".key"):
        return False
    return True


def copy_tree(src, dst):
    copied = []
    for path in sorted(src.rglob("*")):
        if path.is_file() and safe_file(path):
            rel = path.relative_to(src)
            target = dst / "source" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied.append(target)
    return copied


def build(args):
    src = Path(args.input_dir).resolve()
    if not src.is_dir():
        raise SystemExit("input directory does not exist")
    root = Path(args.output_dir).resolve() / "handoff"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    copied = copy_tree(src, root)
    for folder, file_arg in (("preview", args.preview), ("qa", args.qa_report), ("provenance", args.provenance), ("deployment", args.deployment_notes)):
        if file_arg:
            source = Path(file_arg).resolve()
            if not source.is_file() or not safe_file(source):
                raise SystemExit(f"invalid {folder} file")
            dest = root / folder / source.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            copied.append(dest)
    inventory = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        inventory.append({"path": str(path.relative_to(root)), "sha256": sha256(path), "bytes": path.stat().st_size})
    manifest = {
        "title": args.title,
        "artifact_type": args.artifact_type,
        "intended_destination": args.destination,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "qa_status": args.qa_status,
        "unresolved_hitl_count": args.hitl_count,
        "files": inventory,
    }
    (root / "handoff_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    readme = f"# {args.title}\n\nArtifact type: {args.artifact_type}\n\nDestination: {args.destination}\n\nQA status: {args.qa_status}\n\nUnresolved HITL: {args.hitl_count}\n\n## Next action\n\n{args.next_action}\n"
    (root / "README.md").write_text(readme)
    (root / "CHANGELOG.md").write_text("# Changelog\n\n- Initial handoff bundle created.\n")
    zip_path = Path(args.output_dir).resolve() / "design_handoff.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            zf.write(path, Path("handoff") / path.relative_to(root))
    return zip_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--artifact-type", required=True)
    ap.add_argument("--destination", required=True)
    ap.add_argument("--qa-status", default="not_run")
    ap.add_argument("--hitl-count", type=int, default=0)
    ap.add_argument("--next-action", default="Review the editable source and follow the deployment notes.")
    ap.add_argument("--preview")
    ap.add_argument("--qa-report")
    ap.add_argument("--provenance")
    ap.add_argument("--deployment-notes")
    args = ap.parse_args()
    print(build(args))

if __name__ == "__main__":
    main()
