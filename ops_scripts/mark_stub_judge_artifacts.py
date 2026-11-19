"""Read-only scanner for stub-derived and real X1D judge rows (Wave 0).

A "stub row" is a judge row whose raw provider response carries a responseId starting `argon-`
(the signature of resume_graph_engine/src/apps_rg/runtime/judges/inprocess_proof_judge.py, which builds
the response from constants instead of calling a model). Rows are only READ; nothing under the artifacts
root is modified. Outputs are written to --out-dir only.

Usage:
  mark_stub_judge_artifacts.py --scan --artifacts-root <runtime_proofs dir> --out-dir <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

STUB_ID = re.compile(r'responseId\\?"\s*:\s*\\?"argon-')


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _lane_of(path: Path, root: Path) -> str:
    parts = path.relative_to(root).parts
    if "lanes" in parts:
        return parts[parts.index("lanes") + 1]
    if "sections" in parts:
        return parts[parts.index("sections") + 1]
    return "unknown"


def _is_stub(row: dict[str, Any]) -> tuple[bool, str]:
    ref = row.get("raw_response_ref")
    if ref:
        p = Path(str(ref))
        if p.is_file():
            try:
                return (bool(STUB_ID.search(p.read_text(encoding="utf-8", errors="replace"))), "raw_response")
            except OSError:
                pass
    model = str(row.get("model_actual") or row.get("model_name") or "").lower()
    return ("argon" in model, "model_name_fallback")


def scan(root: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stub_rows: list[dict[str, Any]] = []
    real_rows: list[dict[str, Any]] = []
    unreadable: list[str] = []
    files = sorted(root.glob("**/x1d_llm_judge_outputs.json"))
    for fpath in files:
        try:
            doc = json.loads(fpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            unreadable.append(str(fpath))
            continue
        lane = _lane_of(fpath, root)
        packets = sorted(p.name for p in fpath.parent.glob("*judge_packet*.json"))
        for row in doc.get("judges", []):
            if row.get("advisory_only"):
                continue
            stub, how = _is_stub(row)
            rec = {
                "file": str(fpath), "file_sha256": _sha256(fpath), "run": fpath.relative_to(root).parts[0],
                "lane": lane, "judge_id": row.get("judge_id"),
                "model": row.get("model_actual") or row.get("model_name"),
                "score": row.get("score"), "scale": row.get("score_scale"), "pass": row.get("pass"),
                "detected_by": how, "packets_in_dir": packets,
            }
            if stub:
                stub_rows.append(rec)
            elif isinstance(row.get("score"), (int, float)) and packets:
                real_rows.append(rec)
    per_lane: dict[str, list[float]] = defaultdict(list)
    for r in real_rows:
        per_lane[r["lane"]].append(float(r["score"]))
    corpus = {
        "real_rows": len(real_rows),
        "by_model": dict(Counter(str(r["model"]) for r in real_rows)),
        "failing_rows": sum(1 for r in real_rows if r["pass"] is False),
        "per_lane": {k: {"n": len(v), "min": min(v), "max": max(v)} for k, v in sorted(per_lane.items())},
        "rows": real_rows,
    }
    inventory = {
        "artifacts_root": str(root), "judge_output_files_scanned": len(files), "unreadable_files": unreadable,
        "stub_rows": len(stub_rows), "stub_by_model": dict(Counter(str(r["model"]) for r in stub_rows)),
        "stub_detected_by": dict(Counter(r["detected_by"] for r in stub_rows)),
        "stub_score_values": sorted({r["score"] for r in stub_rows if r["score"] is not None}),
        "rows": stub_rows,
    }
    (out_dir / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    (out_dir / "corpus.json").write_text(json.dumps(corpus, indent=2), encoding="utf-8")
    return {"inventory": inventory, "corpus": corpus}


def _load_canned_functions(stub_path: Path) -> dict[str, Any]:
    """Load the canned-content generator functions by file path (no apps_rg package import needed)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_canned_generator_stub", stub_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_canned_generator_stub"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    names = {
        "executive_summary": "_synthesize_executive_summary", "headline": "_synthesize_headline",
        "competencies": "_synthesize_competencies", "slalom_bullets": "_synthesize_slalom_bullets",
        "unify_bullets": "_synthesize_unify_bullets", "ibm_bullets": "_synthesize_ibm_bullets",
        "insurtech_bullets": "_synthesize_insurtech_bullets", "ey_bullets": "_synthesize_ey_bullets",
    }
    return {lane: getattr(mod, fn)() for lane, fn in names.items() if hasattr(mod, fn)}


def _classify_generator_output(lane: str, raw: dict[str, Any], canned: dict[str, Any]) -> tuple[str, str]:
    """Return (classification, reason). Rules are exact-match based and never guess."""
    if "inprocess_ide" in json.dumps(raw.get("change_log")):
        return "stub_origin", "change_log carries the stub's inprocess_ide tag"
    c = canned.get(lane)
    if c is None:
        return "no_stub_path_for_lane", "the canned generator has no function for this lane"
    if lane == "executive_summary":
        eq = raw.get("resume_display_text") == c.get("resume_display_text")
    elif lane == "headline":
        eq = raw.get("headline_line") == c.get("headline_line")
    elif lane.endswith("_bullets"):
        rb, cb = raw.get("bullets") or [], c.get("bullets") or []
        eq = bool(rb and cb) and str(rb[0].get("bullet_text", ""))[:80] == str(cb[0].get("bullet_text", ""))[:80]
    else:
        eq = False
    return ("stub_origin", "primary text equals the canned text") if eq else ("not_stub_origin", "no tag, primary text differs")


def scan_generators(root: Path, stub_path: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    canned = _load_canned_functions(stub_path)
    rows: list[dict[str, Any]] = []
    for fpath in sorted(root.glob("**/raw_model_output.txt")):
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        lane = _lane_of(fpath, root)
        cls, why = _classify_generator_output(lane, raw, canned)
        prov = fpath.parent / "provider_response.json"
        model = status = None
        if prov.is_file():
            try:
                pj = json.loads(prov.read_text(encoding="utf-8"))
                model, status = pj.get("model"), pj.get("runtime_generation_status")
            except (OSError, json.JSONDecodeError):
                pass
        rows.append({
            "run": fpath.relative_to(root).parts[0], "lane": lane, "file": str(fpath),
            "file_sha256": _sha256(fpath), "classification": cls, "reason": why,
            "provider_model": model, "provider_status": status,
        })
    by_class = Counter(r["classification"] for r in rows)
    stub_runs = sorted({r["run"] for r in rows if r["classification"] == "stub_origin"})
    keyed_corpus = [r for r in rows if r["classification"] == "not_stub_origin" and r["provider_status"] == "REAL_LLM"]
    summary = {
        "outputs_classified": len(rows), "by_classification": dict(by_class),
        "runs_with_stub_origin_outputs": stub_runs,
        "stub_origin_by_lane": dict(Counter(r["lane"] for r in rows if r["classification"] == "stub_origin")),
        "real_generation_corpus_by_lane": dict(Counter(r["lane"] for r in keyed_corpus)),
        "real_generation_corpus_models": dict(Counter(str(r["provider_model"]) for r in keyed_corpus)),
        "rows": rows,
    }
    (out_dir / "generator_inventory.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", action="store_true", help="read-only judge scan")
    ap.add_argument("--scan-generators", action="store_true", help="read-only generator-stub classification")
    ap.add_argument("--stub-file", type=Path, help="path to inprocess_ide_provider.py (needed for --scan-generators)")
    ap.add_argument("--artifacts-root", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    if not (args.scan or args.scan_generators):
        ap.error("--scan and/or --scan-generators is required (this tool never modifies artifacts)")
    if args.scan:
        res = scan(args.artifacts_root, args.out_dir)
        inv, cor = res["inventory"], res["corpus"]
        print(f"files scanned={inv['judge_output_files_scanned']} stub_rows={inv['stub_rows']} "
              f"stub_scores={inv['stub_score_values']} real_rows={cor['real_rows']} failing={cor['failing_rows']}")
    if args.scan_generators:
        if not args.stub_file:
            ap.error("--stub-file is required with --scan-generators")
        g = scan_generators(args.artifacts_root, args.stub_file, args.out_dir)
        print(f"generator outputs classified={g['outputs_classified']} by_class={g['by_classification']} "
              f"stub_runs={len(g['runs_with_stub_origin_outputs'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
