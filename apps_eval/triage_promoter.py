"""Human-gated ADR-040 triage candidate promoter for apps_eval fixture suites.

Pure JSON/filesystem module inside ``apps_eval/`` (excluded from production purity
fixture bans, zero SQLite imports to honor domain storage isolation).

Never runs automatically during evaluation; requires explicit human invocation via
``python -m agents learning promote-candidate <candidate_id>``.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.bootstrap_baselines import compute_snapshot_hash
from apps_eval.contracts.digests import canonical_sha256, stable_id
from apps_eval.contracts.schemas import EvalCase, FailureCluster, RunTrace, utc_now_iso
from apps_eval.scenarios import validate_suite_fixtures

GOLDEN_DATASET_CONTRACT_ID = "urn:agents:eval:golden-eval-dataset:1.0.0"

_PII_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PII_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")
_PII_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PII_SECRET_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{16,}|AIza[0-9A-Za-z_-]{20,}|ghp_[A-Za-z0-9]{20,})",
    re.IGNORECASE,
)


def _scrub_pii_recursive(value: Any) -> Any:
    if isinstance(value, str):
        out = _PII_SECRET_RE.sub("[REDACTED_SECRET]", value)
        out = _PII_EMAIL_RE.sub("[REDACTED_EMAIL]", out)
        out = _PII_SSN_RE.sub("[REDACTED_SSN]", out)
        out = _PII_PHONE_RE.sub("[REDACTED_PHONE]", out)
        return out
    if isinstance(value, Mapping):
        return {
            str(k): ("[REDACTED_SECRET]" if any(t in str(k).lower() for t in ("secret", "api_key", "token", "password")) else _scrub_pii_recursive(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub_pii_recursive(i) for i in value]
    return value

_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{2,80}$")

_ALL_GRADERS: list[str] = [
    "schema",
    "artifact_presence",
    "x3_disposition",
    "forbidden_content",
    "grounded_claim",
    "provenance",
    "section_structure",
    "length_bounds",
    "side_effect",
    "escalation",
    "determinism",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sanitize_scenario_id(raw: str, app_id: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]+", "_", raw.lower()).strip("_")
    prefix = "rg_" if app_id == "apps_rg" else "lic_"
    if not cleaned.startswith(prefix):
        cleaned = f"{prefix}{cleaned}"
    cleaned = cleaned[:78].rstrip("_")
    if len(cleaned) < 4:
        cleaned = f"{prefix}triage_case"
    return cleaned


def _build_fixture_payloads(
    packet: dict[str, Any],
    scenario_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
    app_id = str(packet.get("app_id", "apps_rg"))
    reason = str(packet.get("trigger_reason") or "flywheel_triage_candidate")
    expected_x3 = str(packet.get("expected_x3") or "X3B_ESCALATE_HITL")
    escalation_req = expected_x3 == "X3B_ESCALATE_HITL"

    if app_id == "apps_rg":
        raw_req = packet.get("input_payload")
        if isinstance(raw_req, Mapping) and raw_req:
            req = _scrub_pii_recursive(dict(raw_req))
        else:
            req = {
                "generation_mode": "strategic_tailor",
                "jd": _scrub_pii_recursive(str(packet.get("input_summary") or "Promoted resume governance regression case.")),
                "target_company": _scrub_pii_recursive(str(packet.get("target_company") or "TriageTargetCo")),
                "target_role": _scrub_pii_recursive(str(packet.get("target_role") or "VP AI Architecture")),
            }
        exp = {
            "allow_side_effects": False,
            "escalation_required": escalation_req,
            "expected_x3": expected_x3,
            "forbidden_terms": ["salary", "age", "photo", "married", "race", "religion"],
            "grounded_claims_required": True,
            "length_bounds": {"max_words": 160, "min_words": 12},
            "required_artifacts": ["resume.md"],
            "required_output_keys": ["sections"],
            "required_provenance": ["policy:triage"],
            "required_sections": ["executive_summary", "experience", "skills"],
        }
        snap: dict[str, Any] = {
            "app_id": "apps_rg",
            "artifacts": ["resume.md"],
            "claims": [
                {
                    "id": f"{scenario_id}_claim_1",
                    "source_ids": ["policy:triage"],
                    "supported": True,
                    "text": f"Promoted triage regression case: {reason}",
                }
            ],
            "output": {
                "sections": {
                    "executive_summary": f"Governed resume output for promoted triage scenario covering {reason}.",
                    "experience": "Verified delivery record enforcing strict grounding and failure-mode non-regression.",
                    "skills": "AI governance, grounding enforcement, deterministic evaluation, risk controls.",
                }
            },
            "provenance": {"evidence_refs": ["policy:triage"], "rubric_refs": ["apps_rg_resume_generation_v1"]},
            "scenario_id": scenario_id,
            "side_effects": {"product_state_mutated": False, "writes": []},
            "x3_disposition": expected_x3,
        }
        snap["deterministic_hash"] = compute_snapshot_hash(snap)
        return req, exp, snap, "resume.md", f"{scenario_id} promoted triage artifact\n"

    req = {
        "channel": "linkedin",
        "lead_profile": {"name": "Alex", "role_context": str(packet.get("input_summary") or "Executive AI role")},
        "manual_brief": f"Promoted outreach regression case: {reason}",
        "outreach_mode": "cold",
        "recipient_class": "executive_contact",
    }
    exp = {
        "allow_side_effects": False,
        "escalation_required": escalation_req,
        "expected_x3": expected_x3,
        "forbidden_terms": ["guarantee", "fake connection", "we met", "urgent secret", "bypass policy"],
        "grounded_claims_required": True,
        "length_bounds": {"max_words": 120, "min_words": 12},
        "required_artifacts": ["outreach.md"],
        "required_output_keys": ["message", "rationale", "compliance_notes"],
        "required_provenance": ["policy:triage"],
        "required_sections": ["message", "rationale", "compliance_notes"],
    }
    snap = {
        "app_id": "apps_lic",
        "artifacts": ["outreach.md"],
        "claims": [
            {
                "id": f"{scenario_id}_claim_1",
                "source_ids": ["policy:triage"],
                "supported": True,
                "text": f"Promoted outreach triage case: {reason}",
            }
        ],
        "output": {
            "compliance_notes": f"Promoted triage regression guard active for {reason}.",
            "message": "Hi Alex, sharing verified executive AI delivery background aligned strictly with supplied opportunity context.",
            "rationale": f"Bounded outreach regression scenario capturing {reason}.",
        },
        "provenance": {"evidence_refs": ["policy:triage"], "rubric_refs": ["apps_lic_outreach_v1"]},
        "scenario_id": scenario_id,
        "side_effects": {"product_state_mutated": False, "writes": []},
        "x3_disposition": expected_x3,
    }
    snap["deterministic_hash"] = compute_snapshot_hash(snap)
    return req, exp, snap, "outreach.md", f"{scenario_id} promoted triage artifact\n"


def promote_staged_triage_packet(
    packet_path: str | Path,
    *,
    target_split: str = "dev",
    reviewer: str = "operator",
    fixtures_base_dir: str | Path | None = None,
    suites_registry_path: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Promote a human-reviewed ADR-040 triage packet into an apps_eval fixture suite."""
    if target_split not in ("dev", "holdout"):
        raise ValueError(f"target_split must be 'dev' or 'holdout', got {target_split!r}")
    if not reviewer or not str(reviewer).strip():
        raise ValueError("human reviewer identifier is required for ADR-040 gated promotion")

    src = Path(packet_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"triage packet not found: {src}")
    packet = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("triage packet must be a JSON object")

    app_id = str(packet.get("app_id") or "")
    if app_id not in ("apps_rg", "apps_lic"):
        raise ValueError(f"unsupported app_id in triage packet: {app_id!r}")

    candidate_id = str(packet.get("candidate_id") or src.stem)
    scenario_id = _sanitize_scenario_id(candidate_id, app_id)
    if not _SAFE_ID_RE.fullmatch(scenario_id):
        raise ValueError(f"invalid sanitized scenario_id: {scenario_id!r}")

    suite_id = (
        f"apps_rg.{target_split}.resume_generation"
        if app_id == "apps_rg"
        else f"apps_lic.{target_split}.outreach_message"
    )
    repo_root = Path(__file__).resolve().parents[1]
    base_dir = (
        Path(fixtures_base_dir).resolve()
        if fixtures_base_dir is not None
        else (repo_root / "apps_eval" / "fixtures" / target_split / app_id).resolve()
    )
    scenario_dir = base_dir / scenario_id

    if dry_run:
        return {
            "status": "DRY_RUN",
            "candidate_id": candidate_id,
            "scenario_id": scenario_id,
            "suite_id": suite_id,
            "target_dir": scenario_dir.as_posix(),
            "reviewer": reviewer,
        }

    req, exp, snap, art_name, art_text = _build_fixture_payloads(packet, scenario_id)
    _write_json(
        scenario_dir / "scenario.yaml",
        {
            "description": str(packet.get("description") or f"Human-promoted triage case ({candidate_id})."),
            "graders": _ALL_GRADERS,
            "scenario_id": scenario_id,
        },
    )
    _write_json(scenario_dir / "input" / "request.json", req)
    _write_json(scenario_dir / "expected" / "expectations.json", exp)
    _write_json(scenario_dir / "snapshots" / "app_output_snapshot.json", snap)
    art_path = scenario_dir / "snapshots" / "artifacts" / art_name
    art_path.parent.mkdir(parents=True, exist_ok=True)
    art_path.write_text(art_text, encoding="utf-8")

    # Optionally update suites.yaml when targeting registry
    reg_path = (
        Path(suites_registry_path).resolve()
        if suites_registry_path is not None
        else (repo_root / "apps_eval" / "registry" / "suites.yaml").resolve()
    )
    registered = False
    if reg_path.is_file():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        suites = reg.get("suites") or {}
        if suite_id in suites:
            scenarios = list(suites[suite_id].get("scenarios") or [])
            if scenario_id not in scenarios:
                scenarios.append(scenario_id)
                suites[suite_id]["scenarios"] = scenarios
                reg_path.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
            registered = True

    # Mark triage packet promoted (audit trail preserved)
    packet["status"] = "PROMOTED"
    packet["promoted_at"] = _utc_now()
    packet["promoted_by"] = reviewer
    packet["promoted_suite_id"] = suite_id
    packet["promoted_scenario_id"] = scenario_id
    src.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validation_problems: list[str] = []
    if fixtures_base_dir is None and registered:
        validation_problems = validate_suite_fixtures(suite_id)

    return {
        "status": "PROMOTED" if not validation_problems else "PROMOTED_WITH_WARNINGS",
        "candidate_id": candidate_id,
        "scenario_id": scenario_id,
        "suite_id": suite_id,
        "target_dir": scenario_dir.as_posix(),
        "registered": registered,
        "reviewer": reviewer,
        "validation_problems": validation_problems,
    }


def _validate_safe_dataset_path(target_path: Path, repo_root: Path | None = None) -> None:
    """Block writing golden datasets into production output/ directories."""
    resolved = Path(target_path).resolve()
    parts = [p.lower() for p in resolved.parts]
    if "output" in parts:
        raise ValueError(f"Refusing to write golden eval dataset inside production output path: {resolved}")
    if repo_root is not None:
        prod_out = (Path(repo_root).resolve() / "output").resolve()
        try:
            resolved.relative_to(prod_out)
            raise ValueError(f"Refusing to write golden eval dataset inside {prod_out}")
        except ValueError as exc:
            if "Refusing" in str(exc):
                raise


def _assign_stratified_splits(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign deterministic 80/20 hash-stratified dev/holdout splits honoring locked seeds and per-category floors."""
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in cases:
        if item.get("locked_split") is True and item.get("split") in {"development", "holdout"}:
            continue
        cid = str(item["case_id"])
        bucket = int(hashlib.sha256(cid.encode("utf-8")).hexdigest()[:8], 16) % 5
        item["split"] = "holdout" if bucket == 0 else "development"
        by_cat[str(item.get("app_id") or "general")].append(item)

    # Enforce per-category floor: any category with >= 2 unlocked items has >= 1 dev and >= 1 holdout.
    for cat_items in by_cat.values():
        if len(cat_items) < 2:
            continue
        cat_items.sort(key=lambda x: str(x["case_id"]))
        splits = {c["split"] for c in cat_items}
        if "holdout" not in splits:
            cat_items[-1]["split"] = "holdout"
        elif "development" not in splits:
            cat_items[0]["split"] = "development"
    return cases


def promote_golden_cases(
    *,
    output_dataset_path: Path,
    traces: Sequence[RunTrace] = (),
    eligible_clusters: Sequence[FailureCluster] = (),
    operator_corrections: Sequence[Mapping[str, Any]] = (),
    curated_holdout_seeds: Sequence[Mapping[str, Any]] = (),
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Promote PII-scrubbed real payloads from eligible clusters, corrections, and locked seeds into golden_eval_cases.json."""
    target = Path(output_dataset_path).resolve()
    _validate_safe_dataset_path(target, repo_root=repo_root)

    eligible_trace_ids: set[str] = set()
    for cl in eligible_clusters:
        if cl.eligible_for_golden_promotion and not cl.conflict_detected:
            eligible_trace_ids.update(str(rid) for rid in cl.unique_run_ids)

    dedup: dict[str, dict[str, Any]] = {}

    # 1. Locked curated holdout seeds (never drift into development).
    for seed in curated_holdout_seeds:
        app_id = str(seed.get("app_id") or "agents_core")
        clean_in = _scrub_pii_recursive(dict(seed.get("unlabeled_input") or {"prompt": seed.get("input_text", "")}))
        exp_contract = dict(seed.get("expected_contract") or {"reference_label": seed.get("ground_truth_label", "PASS")})
        cid = str(seed.get("case_id") or stable_id("golden-case", "curated", app_id, clean_in, exp_contract, length=20))
        ec = EvalCase(
            case_id=cid,
            suite_id=f"{app_id}.golden.v1",
            app_id=app_id,
            split=str(seed.get("split") or "holdout"),  # type: ignore[arg-type]
            locked_split=True,
            execution_mode="snapshot",
            source_kind="curated",
            grounding_tier="OFFLINE_BENCHMARK_GROUNDED",
            unlabeled_input=clean_in,
            expected_contract=exp_contract,
        )
        dedup[ec.case_id] = ec.to_dict()

    # 2. Authentic failed RunTraces gated by eligible_clusters (preserving real redacted input payloads).
    for tr in traces:
        if tr.terminal_status == "PASS":
            continue
        if eligible_clusters and (tr.trace_id not in eligible_trace_ids and tr.run_id not in eligible_trace_ids):
            continue
        clean_in = _scrub_pii_recursive(dict(tr.input_redacted.get("redacted_snapshot") or {}))
        if not clean_in:
            clean_in = {"app_id": tr.app_id, "run_id": tr.run_id}
        exp_contract = {
            "reference_label": "PASS",
            "required_gates": {"terminal_success": True},
            "source_terminal_status": tr.terminal_status,
        }
        cid = stable_id("golden-case", "online_eval_failure", tr.app_id, clean_in, tr.gate_outcomes, length=20)
        ec = EvalCase(
            case_id=cid,
            suite_id=f"{tr.app_id}.golden.v1",
            app_id=tr.app_id,
            split="development",
            locked_split=False,
            execution_mode="snapshot",
            source_kind="online_eval_failure",
            source_trace_id=tr.trace_id,
            grounding_tier="LIVE_CORPUS_GROUNDED",
            unlabeled_input={"payload": clean_in, "pii_redacted": True},
            expected_contract=exp_contract,
        )
        dedup[ec.case_id] = ec.to_dict()

    # 3. Confirmed operator corrections (using canonical source_identifier with fallback alias).
    for corr in operator_corrections:
        if corr.get("retracted") is True:
            continue
        src_val = str(corr.get("source_identifier") or corr.get("original_identifier") or "").strip()
        tgt_val = str(corr.get("corrected_identifier") or "").strip()
        if not src_val or not tgt_val:
            continue
        app_id = str(corr.get("app_id") or "agents_core")
        clean_in = _scrub_pii_recursive({"source_identifier": src_val, "category": str(corr.get("category") or "general")})
        exp_contract = {"reference_label": _scrub_pii_recursive(tgt_val), "negative_labels": [clean_in["source_identifier"]]}
        cid = stable_id("golden-case", "operator_correction", app_id, clean_in, exp_contract, length=20)
        ec = EvalCase(
            case_id=cid,
            suite_id=f"{app_id}.golden.v1",
            app_id=app_id,
            split="development",
            locked_split=False,
            execution_mode="snapshot",
            source_kind="operator_correction",
            source_trace_id=str(corr.get("correction_id") or ""),
            grounding_tier="LIVE_CORPUS_GROUNDED",
            unlabeled_input=clean_in,
            expected_contract=exp_contract,
        )
        dedup[ec.case_id] = ec.to_dict()

    cases_list = _assign_stratified_splits(sorted(dedup.values(), key=lambda c: str(c["case_id"])))
    # Re-seal canonical_digest after split assignment.
    sealed_cases: list[dict[str, Any]] = []
    for item in cases_list:
        item.pop("canonical_digest", None)
        item["canonical_digest"] = canonical_sha256(item)
        sealed_cases.append(item)

    counts_by_split: dict[str, int] = {"development": 0, "holdout": 0}
    counts_by_source: dict[str, int] = {}
    counts_by_app: dict[str, int] = {}
    for c in sealed_cases:
        sp = str(c["split"])
        counts_by_split[sp] = counts_by_split.get(sp, 0) + 1
        sk = str(c["source_kind"])
        counts_by_source[sk] = counts_by_source.get(sk, 0) + 1
        ap = str(c["app_id"])
        counts_by_app[ap] = counts_by_app.get(ap, 0) + 1

    dataset = {
        "contract_id": GOLDEN_DATASET_CONTRACT_ID,
        "schema_version": "1.0.0",
        "generated_at_utc": utc_now_iso(),
        "dataset_digest": canonical_sha256(sealed_cases),
        "total_cases": len(sealed_cases),
        "counts_by_split": counts_by_split,
        "counts_by_source": counts_by_source,
        "counts_by_app": counts_by_app,
        "cases": sealed_cases,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return dataset


def load_holdout_cases(
    dataset_path: Path,
    *,
    app_id: str | None = None,
) -> tuple[str, list[EvalCase]]:
    """Load strictly split == 'holdout' EvalCases along with dataset_digest; never leaks development cases."""
    target = Path(dataset_path).resolve()
    if not target.is_file():
        return "", []
    data = json.loads(target.read_text(encoding="utf-8"))
    digest = str(data.get("dataset_digest") or "")
    holdouts: list[EvalCase] = []
    for raw in data.get("cases") or []:
        if str(raw.get("split") or "") != "holdout":
            continue
        if app_id is not None and str(raw.get("app_id") or "") != app_id:
            continue
        holdouts.append(EvalCase.from_dict(raw))
    return digest, holdouts
