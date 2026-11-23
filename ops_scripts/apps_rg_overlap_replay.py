#!/usr/bin/env python3
"""Replay all past apps_rg FINAL_RESUME_OUTPUT.txt runs to build baseline flaw ledger and verify Overlap Engine parity."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RG_SRC = REPO_ROOT / "resume_graph_engine" / "src"
if str(RG_SRC) not in sys.path:
    sys.path.insert(0, str(RG_SRC))


_EMPLOYER_SECTION_MAP: tuple[tuple[str, str], ...] = (
    ("slalom", "slalom"),
    ("unify consulting", "unify"),
    ("ibm", "ibm"),
    ("insurtech cloud solutions", "insurtech"),
    ("ernst & young", "ey"),
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_NUMBER_UNIT_RE = re.compile(
    r"(?:\$\s*\d+(?:\.\d+)?\s*(?:m|mm|b|bn|k|million|billion|thousand)?\b|\b\d+(?:\.\d+)?\s*(?:%|(?:percent|x)\b))",
    re.IGNORECASE,
)


def normalize_number_token(raw: str) -> str:
    s = re.sub(r"\s+", "", raw.strip().lower())
    s = s.replace("million", "m").replace("mm", "m").replace("billion", "b").replace("bn", "b").replace("thousand", "k")
    s = s.replace("percent", "%")
    return s


def extract_number_tokens(text: str) -> list[str]:
    out: list[str] = []
    for m in _NUMBER_UNIT_RE.finditer(text or ""):
        norm = normalize_number_token(m.group(0))
        if norm and norm not in out:
            out.append(norm)
    return out


def parse_final_resume_units(text: str) -> list[dict[str, Any]]:
    """Parse a rendered FINAL_RESUME_OUTPUT.txt into section-tagged units."""
    lines = [ln.strip() for ln in (text or "").splitlines()]
    units: list[dict[str, Any]] = []
    mode = "header"
    current_employer: str | None = None
    emp_narrative_seen: set[str] = set()
    emp_bullet_counts: dict[str, int] = {}

    for idx, ln in enumerate(lines):
        if not ln:
            continue
        upper = ln.upper()
        if upper == "EXECUTIVE SUMMARY":
            mode = "executive_summary"
            continue
        if upper in ("ENGINEERING & PLATFORM COMPETENCIES", "CORE COMPETENCIES", "TECHNICAL & EXECUTIVE COMPETENCIES"):
            mode = "competencies"
            continue
        if upper == "PROFESSIONAL EXPERIENCE":
            mode = "experience"
            current_employer = None
            continue
        if upper in ("EDUCATION", "CERTIFICATIONS & CREDENTIALS", "CERTIFICATIONS"):
            mode = "footer"
            current_employer = None
            continue

        if mode == "header" and idx >= 2 and "|" in ln and "@" not in ln and "linkedin.com" not in ln.lower():
            segs = [s.strip() for s in ln.split("|") if s.strip()]
            for s_i, seg in enumerate(segs, start=1):
                units.append({
                    "unit_id": f"headline:seg_{s_i}",
                    "section_id": "headline",
                    "employer": None,
                    "unit_kind": "headline_segment",
                    "text": seg,
                })
            units.append({
                "unit_id": "headline:full",
                "section_id": "headline",
                "employer": None,
                "unit_kind": "headline_full",
                "text": ln,
            })
        elif mode == "executive_summary":
            sents = [s.strip() for s in _SENTENCE_SPLIT_RE.split(ln) if s.strip()]
            for s_i, sent in enumerate(sents, start=1):
                units.append({
                    "unit_id": f"executive_summary:S{s_i}",
                    "section_id": "executive_summary",
                    "employer": None,
                    "unit_kind": "summary_sentence",
                    "text": sent,
                })
        elif mode == "competencies":
            if ":" in ln:
                cat, rest = ln.split(":", 1)
                terms = [t.strip() for t in rest.split(",") if t.strip()]
                for t_i, term in enumerate(terms, start=1):
                    units.append({
                        "unit_id": f"competencies:{cat.strip()}:T{t_i}",
                        "section_id": "competencies",
                        "employer": None,
                        "unit_kind": "competency_term",
                        "text": term,
                    })
        elif mode == "experience":
            lower = ln.lower()
            matched_emp: str | None = None
            if ("—" in ln or " - " in ln) and not ln.startswith(("•", "-", "*")):
                for prefix, emp_key in _EMPLOYER_SECTION_MAP:
                    if lower.startswith(prefix):
                        matched_emp = emp_key
                        break
            if matched_emp:
                current_employer = matched_emp
                continue
            if current_employer is None:
                continue
            # Skip location | date line
            if "|" in ln and any(m in ln for m in ("20", "19", "Present")):
                continue
            if ln.startswith(("•", "-", "*")):
                b_text = ln.lstrip("•-*").strip()
                b_idx = emp_bullet_counts.get(current_employer, 0) + 1
                emp_bullet_counts[current_employer] = b_idx
                units.append({
                    "unit_id": f"{current_employer}_bullets:B{b_idx}",
                    "section_id": f"{current_employer}_bullets",
                    "employer": current_employer,
                    "unit_kind": "bullet",
                    "text": b_text,
                })
            elif current_employer not in emp_narrative_seen:
                emp_narrative_seen.add(current_employer)
                units.append({
                    "unit_id": f"{current_employer}_narrative:N1",
                    "section_id": f"{current_employer}_narrative",
                    "employer": current_employer,
                    "unit_kind": "narrative",
                    "text": ln,
                })

    return units


def collect_existing_gate_verdicts(run_dir: Path) -> dict[str, Any]:
    """Read existing cross_section_x2_gate_outputs.json from a past run directory."""
    cross_path = run_dir / "modular_r4" / "final_resume_assembly" / "cross_section_x2_gate_outputs.json"
    if not cross_path.is_file():
        return {"present": False, "warn_gates": [], "fail_gates": [], "details": {}}
    try:
        data = json.loads(cross_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"present": False, "warn_gates": [], "fail_gates": [], "details": {}}
    gates = data.get("gates") if isinstance(data, dict) else data
    warn_gates: list[str] = []
    fail_gates: list[str] = []
    details: dict[str, Any] = {}
    if isinstance(gates, list):
        for g in gates:
            if not isinstance(g, dict):
                continue
            gid = str(g.get("gate_id") or "")
            verdict = str(g.get("verdict") or ("PASS" if g.get("pass") else "FAIL"))
            if verdict == "WARN":
                warn_gates.append(gid)
                details[gid] = g.get("details")
            elif verdict in ("FAIL", "UNKNOWN") or not g.get("pass", True):
                fail_gates.append(gid)
                details[gid] = g.get("details")
    return {
        "present": True,
        "warn_gates": warn_gates,
        "fail_gates": fail_gates,
        "details": details,
    }


def scan_baseline_flaws_for_units(units: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect repeated numbers, repeated acronyms/codes, and high token overlap across prose units."""
    prose_units = [
        u for u in units
        if u["unit_kind"] in ("summary_sentence", "narrative", "bullet")
    ]
    number_locations: dict[str, list[str]] = {}
    acronym_code_re = re.compile(r"\b(?:[A-Z]{2,6}\s+\d{1,4}(?:-\d+)?|SOC\s*2|BCBS\s*239|SR\s*11-7|AG\s*43|Solvency\s*II|Basel\s*III|CCAR|MEDDPICC|SCADA|Guidewire|Maximo|Salesforce)\b")
    code_locations: dict[str, list[str]] = {}

    for u in prose_units:
        uid = u["unit_id"]
        txt = u["text"]
        for num in extract_number_tokens(txt):
            number_locations.setdefault(num, []).append(uid)
        for m in acronym_code_re.finditer(txt):
            key = re.sub(r"\s+", " ", m.group(0).strip().lower())
            if uid not in code_locations.setdefault(key, []):
                code_locations[key].append(uid)

    repeated_numbers = {k: v for k, v in sorted(number_locations.items()) if len(v) > 1}
    repeated_codes = {k: v for k, v in sorted(code_locations.items()) if len(v) > 1}

    return {
        "prose_unit_count": len(prose_units),
        "total_unit_count": len(units),
        "repeated_numbers": repeated_numbers,
        "repeated_codes": repeated_codes,
        "has_flaws": bool(repeated_numbers or repeated_codes),
    }


def resolve_proofs_dirs() -> list[Path]:
    """Find all runtime_proofs/full_resume_* directories containing FINAL_RESUME_OUTPUT.txt."""
    candidates = [
        REPO_ROOT / "resume_graph_engine" / "artifacts" / "apps_rg" / "runtime_proofs",
        Path("/Users/amitayer/Git/agents/resume_graph_engine/artifacts/apps_rg/runtime_proofs"),
    ]
    seen_runs: dict[str, Path] = {}
    for base in candidates:
        if not base.is_dir():
            continue
        for run_dir in sorted(base.iterdir()):
            if not run_dir.is_dir():
                continue
            final_txt = run_dir / "FINAL_RESUME_OUTPUT.txt"
            if final_txt.is_file() and run_dir.name not in seen_runs:
                seen_runs[run_dir.name] = run_dir
    return [seen_runs[k] for k in sorted(seen_runs)]


def run_baseline(out_path: Path) -> dict[str, Any]:
    run_dirs = resolve_proofs_dirs()
    records: list[dict[str, Any]] = []
    flawed_count = 0
    warn_escaped_count = 0

    for rdir in run_dirs:
        txt = (rdir / "FINAL_RESUME_OUTPUT.txt").read_text(encoding="utf-8")
        units = parse_final_resume_units(txt)
        existing = collect_existing_gate_verdicts(rdir)
        flaws = scan_baseline_flaws_for_units(units)
        if flaws["has_flaws"]:
            flawed_count += 1
        if existing["warn_gates"] and not existing["fail_gates"]:
            warn_escaped_count += 1
        records.append({
            "run_id": rdir.name,
            "sha16": hashlib.sha256(txt.encode("utf-8")).hexdigest()[:16],
            "existing_cross_section": existing,
            "baseline_flaws": flaws,
        })

    ledger = {
        "schema": "apps_rg.overlap_replay.baseline_ledger.v1",
        "total_resumes": len(records),
        "resumes_with_repeated_numbers_or_codes": flawed_count,
        "resumes_where_warn_escaped_without_fail": warn_escaped_count,
        "resumes": records,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    return ledger


def run_parity(baseline_path: Path, out_path: Path) -> dict[str, Any]:
    from apps_rg.runtime.quality.overlap_engine import (
        ResumeUnit,
        evaluate_resume_overlap,
        load_default_overlap_policy,
    )
    from apps_rg.runtime.quality.rare_term_lexicon import RareTermLexicon

    if not baseline_path.is_file():
        run_baseline(baseline_path)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    lexicon = RareTermLexicon.from_default_fact_inventory()
    policy = load_default_overlap_policy()
    run_dirs = {d.name: d for d in resolve_proofs_dirs()}

    parity_rows: list[dict[str, Any]] = []
    unmatched_legacy_flaws: list[dict[str, Any]] = []

    for rec in baseline.get("resumes", []):
        run_id = rec["run_id"]
        rdir = run_dirs.get(run_id)
        if rdir is None:
            continue
        txt = (rdir / "FINAL_RESUME_OUTPUT.txt").read_text(encoding="utf-8")
        raw_units = parse_final_resume_units(txt)
        r_units = [
            ResumeUnit(
                unit_id=u["unit_id"],
                section_id=u["section_id"],
                text=u["text"],
                employer=u["employer"],
                unit_kind=u["unit_kind"],
            )
            for u in raw_units
            if u["unit_kind"] != "headline_full"
        ]
        report = evaluate_resume_overlap(r_units, lexicon=lexicon, policy=policy)

        legacy_had_flaw = bool(
            rec["baseline_flaws"]["has_flaws"]
            or rec["existing_cross_section"]["warn_gates"]
            or rec["existing_cross_section"]["fail_gates"]
        )
        engine_caught = report.verdict != "PASS"
        if legacy_had_flaw and not engine_caught:
            unmatched_legacy_flaws.append({
                "run_id": run_id,
                "legacy_flaws": rec["baseline_flaws"],
                "legacy_warns": rec["existing_cross_section"]["warn_gates"],
            })
        parity_rows.append({
            "run_id": run_id,
            "legacy_had_flaw": legacy_had_flaw,
            "engine_verdict": report.verdict,
            "engine_finding_count": len(report.findings),
            "engine_repeated_signature_terms": list(report.repeated_signature_terms.keys()),
            "engine_repeated_numbers": list(report.repeated_numbers.keys()),
            "parity_ok": (not legacy_had_flaw) or engine_caught,
        })

    parity_payload = {
        "schema": "apps_rg.overlap_replay.parity.v1",
        "total_resumes": len(parity_rows),
        "unmatched_legacy_flaw_count": len(unmatched_legacy_flaws),
        "parity_100_percent": len(unmatched_legacy_flaws) == 0,
        "unmatched_legacy_flaws": unmatched_legacy_flaws,
        "resumes": parity_rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(parity_payload, indent=2, sort_keys=True), encoding="utf-8")
    return parity_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay past resumes for overlap baseline and parity.")
    parser.add_argument("--mode", choices=("baseline", "parity"), required=True)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "apps_rg" / "overlap_replay",
    )
    args = parser.parse_args(argv)
    baseline_path = args.out_dir / "baseline_ledger.json"
    parity_path = args.out_dir / "parity.json"

    if args.mode == "baseline":
        ledger = run_baseline(baseline_path)
        print(
            f"[BASELINE] total_resumes={ledger['total_resumes']} "
            f"flawed={ledger['resumes_with_repeated_numbers_or_codes']} "
            f"warn_escaped={ledger['resumes_where_warn_escaped_without_fail']} "
            f"path={baseline_path}"
        )
        return 0

    parity = run_parity(baseline_path, parity_path)
    print(
        f"[PARITY] total_resumes={parity['total_resumes']} "
        f"parity_100_percent={parity['parity_100_percent']} "
        f"unmatched={parity['unmatched_legacy_flaw_count']} "
        f"path={parity_path}"
    )
    return 0 if parity["parity_100_percent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
