#!/usr/bin/env python3
"""6-Vector Multi-SSOT Judge & Gate Drift Auditor for `agents`.

Cross-checks:
- Vector 1 (V1_RUBRIC_TO_CONFIG): config/judges/rubrics.yaml & trace_rubric.yaml integrity.
- Vector 2 (V2_PROVIDER_PROFILES_PARITY): config/provider_profiles.yaml orthogonal judge families.
- Vector 3 (V3_LIVE_NEGATIVE_PROBES): executable negative probes against Tier-1/Tier-2 judge gates.
- Vector 4 (V4_AUTO_APPLY_POLICY_BOUNDS): auto_apply_policy.yaml bounds vs routing_calibration.yaml live defaults.
- Vector 5 (V5_PINNED_REGRESSIONS_PARITY): pinned_fix_regressions.json covers all eval shield domains.
- Vector 6 (V6_FLYWHEEL_HITL_REMEDIATION_PARITY): INV-FLYWHEEL-AUTO-REMEDIATE parity across policy_registry.yaml,
  auto_apply_policy.yaml, and flywheel_hitl_dispatcher.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps_eval.graders.judge import (
    LensSpec,
    LensVerdict,
    evaluate_multi_lens_panel,
    load_approved_judge_families,
    run_tier1_deterministic_pre_judge,
    validate_blind_judge_verdict_provenance,
)
from tools.eval_shield_core.domain_eval_checks import DOMAIN_RUNNERS


def _get_nested(data: dict[str, Any], dotted: str) -> tuple[bool, Any]:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def audit_multi_ssot_judge_gate_drift(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    violations: list[dict[str, str]] = []
    vectors: dict[str, str] = {}

    # Vector 1: Rubrics & trace rubric parse cleanly.
    v1_errs: list[str] = []
    for rel in ("config/judges/rubrics.yaml", "config/judges/trace_rubric.yaml"):
        p = root / rel
        if not p.is_file():
            v1_errs.append(f"missing:{rel}")
        else:
            parsed = yaml.safe_load(p.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict) or not parsed:
                v1_errs.append(f"empty_or_invalid:{rel}")
    vectors["V1_RUBRIC_TO_CONFIG"] = "PASS" if not v1_errs else "FAIL"
    for e in v1_errs:
        violations.append({"vector": "V1_RUBRIC_TO_CONFIG", "message": e})

    # Vector 2: Provider profiles expose >= 2 orthogonal approved judge families.
    v2_errs: list[str] = []
    families = load_approved_judge_families(root)
    if len(families) < 2:
        v2_errs.append(f"fewer_than_2_orthogonal_judge_families:{sorted(families.keys())}")
    vectors["V2_PROVIDER_PROFILES_PARITY"] = "PASS" if not v2_errs else "FAIL"
    for e in v2_errs:
        violations.append({"vector": "V2_PROVIDER_PROFILES_PARITY", "message": e})

    # Vector 3: Executable live negative probes against deterministic & blind judge validators.
    v3_errs: list[str] = []
    # Probe A: Tier-1 must reject AI buzzwords.
    t1 = run_tier1_deterministic_pre_judge("A holistic tapestry to delve into synergy.")
    if t1.passed:
        v3_errs.append("tier1_pre_judge_failed_to_reject_ai_buzzwords")
    # Probe B: Blind judge must reject self-grading + primed keys.
    ok_bad, _ = validate_blind_judge_verdict_provenance(
        {
            "evaluator_kind": "llm_judge",
            "judge_model_id": "claude-sonnet-4",
            "author_model_family": "anthropic",
            "judge_model_family": "anthropic",
            "deterministic_priming_stripped": True,
            "judge_input_keys": ["text", "deterministic_gate_summary"],
        }
    )
    if ok_bad:
        v3_errs.append("blind_judge_accepted_self_grading_and_priming")
    # Probe C: Multi-lens panel must enforce single-lens floor veto even with high weighted average.
    panel = evaluate_multi_lens_panel(
        [LensSpec("a", 5.0, min_floor=8.0), LensSpec("b", 1.0, min_floor=8.0)],
        [LensVerdict("a", 9.9, "openai"), LensVerdict("b", 6.5, "google")],
        pass_threshold=8.5,
    )
    if panel.verdict != "FAIL":
        v3_errs.append(f"multi_lens_panel_missed_single_lens_veto:{panel.verdict}")
    vectors["V3_LIVE_NEGATIVE_PROBES"] = "PASS" if not v3_errs else "FAIL"
    for e in v3_errs:
        violations.append({"vector": "V3_LIVE_NEGATIVE_PROBES", "message": e})

    # Vector 4: Auto-apply policy bounds match live routing_calibration.yaml defaults and forbid .py.
    v4_errs: list[str] = []
    policy_path = root / "config" / "governance" / "auto_apply_policy.yaml"
    routing_path = root / "config" / "routing_calibration.yaml"
    if not policy_path.is_file():
        v4_errs.append("missing_auto_apply_policy_yaml")
    elif not routing_path.is_file():
        v4_errs.append("missing_routing_calibration_yaml")
    else:
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        routing = yaml.safe_load(routing_path.read_text(encoding="utf-8")) or {}
        forbidden_exts = set((policy.get("tier_c_pr_only") or {}).get("forbidden_auto_apply_extensions") or ())
        if ".py" not in forbidden_exts:
            v4_errs.append("auto_apply_policy_missing_py_ban")
        bounds = (policy.get("tier_a_auto_apply") or {}).get("bounded_numeric_parameters") or {}
        for ref, b in bounds.items():
            if not ref.startswith("config/routing_calibration.yaml::"):
                continue
            key = ref.split("::", 1)[1]
            found, live = _get_nested(routing, key)
            if not found:
                v4_errs.append(f"bounded_param_missing_in_routing_yaml:{key}")
            elif float(live) < float(b["min"]) or float(live) > float(b["max"]):
                v4_errs.append(f"live_default_outside_policy_bounds:{key}={live}")
    vectors["V4_AUTO_APPLY_POLICY_BOUNDS"] = "PASS" if not v4_errs else "FAIL"
    for e in v4_errs:
        violations.append({"vector": "V4_AUTO_APPLY_POLICY_BOUNDS", "message": e})

    # Vector 5: pinned_fix_regressions.json covers all eval shield domains.
    v5_errs: list[str] = []
    pin_path = root / "apps_eval" / "suites" / "pinned_fix_regressions.json"
    if not pin_path.is_file():
        v5_errs.append("missing_pinned_fix_regressions_json")
    else:
        pinned = json.loads(pin_path.read_text(encoding="utf-8"))
        pinned_domains = {str(c.get("domain") or "") for c in pinned.get("cases") or []}
        missing_domains = sorted(set(DOMAIN_RUNNERS.keys()) - pinned_domains)
        if missing_domains:
            v5_errs.append(f"unpinned_shield_domains:{missing_domains}")
    vectors["V5_PINNED_REGRESSIONS_PARITY"] = "PASS" if not v5_errs else "FAIL"
    for e in v5_errs:
        violations.append({"vector": "V5_PINNED_REGRESSIONS_PARITY", "message": e})

    # Vector 6: INV-FLYWHEEL-AUTO-REMEDIATE parity across policy_registry.yaml, auto_apply_policy.yaml, and dispatcher.
    v6_errs: list[str] = []
    registry_path = root / "config" / "governance" / "policy_registry.yaml"
    if not registry_path.is_file():
        v6_errs.append("missing_policy_registry_yaml")
    else:
        reg_data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        policies_by_id = {
            str(p.get("id")): p
            for p in (reg_data.get("policies") or [])
            if isinstance(p, dict) and p.get("id")
        }
        inv_entry = policies_by_id.get("INV-FLYWHEEL-AUTO-REMEDIATE")
        if inv_entry is None:
            v6_errs.append("missing_INV-FLYWHEEL-AUTO-REMEDIATE_in_policy_registry")
        else:
            enforcer_rel = str(inv_entry.get("enforcer") or "").strip()
            rule_rel = str(inv_entry.get("rule_reference") or "").strip()
            if not enforcer_rel or not (root / enforcer_rel).is_file():
                v6_errs.append(f"missing_flywheel_enforcer:{enforcer_rel}")
            if not rule_rel or not (root / rule_rel).is_file():
                v6_errs.append(f"missing_flywheel_rule_reference:{rule_rel}")

        hitl_margin_pol = policies_by_id.get("INV-HITL-AMBIGUITY-MARGIN") or {}
        canon_margin = float(hitl_margin_pol.get("threshold", 0.20))

        if policy_path.is_file():
            pol_doc = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
            interactive = pol_doc.get("interactive_remediation") or {}
            cool = pol_doc.get("cooldown_and_hysteresis") or {}
            if not interactive.get("one_at_a_time", False):
                v6_errs.append("interactive_remediation.one_at_a_time_must_be_true")
            if not interactive.get("auto_execute_on_approval", False):
                v6_errs.append("interactive_remediation.auto_execute_on_approval_must_be_true")
            if not interactive.get("auto_promote_approved_fixes", False):
                v6_errs.append("interactive_remediation.auto_promote_approved_fixes_must_be_true")
            inter_margin = float(interactive.get("min_autonomous_confidence_margin", -1.0))
            cool_margin = float(cool.get("hysteresis_min_confidence_margin", -1.0))
            if inter_margin != canon_margin or cool_margin != canon_margin:
                v6_errs.append(
                    f"margin_drift:interactive={inter_margin},cooldown={cool_margin},registry={canon_margin}"
                )

    try:
        from agents.learning.flywheel_hitl_dispatcher import (
            build_atomic_remediation_question,
            record_remediation_decision,
        )
        from agents.learning.worktree_promoter import apply_and_verify_with_worktree_isolation
        from apps_eval.contracts.schemas import FindingRecord, ImprovementProposal
        from tools.hitl_governance import validate_hitl_presentation

        priors_path = root / "config" / "prompt_governance" / "priors.yaml"
        if not priors_path.is_file():
            v6_errs.append("missing_prompt_governance_priors_yaml")
        if (
            not callable(build_atomic_remediation_question)
            or not callable(record_remediation_decision)
            or not callable(apply_and_verify_with_worktree_isolation)
        ):
            v6_errs.append("flywheel_dispatcher_missing_required_callables")
        else:
            probe_f = FindingRecord(
                finding_id="find-ssot-probe",
                fingerprint_sha256="a" * 64,
                source_surface="online_eval",
                app_id="apps_rg",
                failed_gate_signature="x2_gates_passed",
                root_cause_bucket="probe_snake_case_bucket",
                owner_subsystem="resume_graph_engine",
                track="TRACK_2_CODE_FIX",
                priority="P1",
                status="OPEN",
                title="apps_rg x2_gates failure in tools/probe_file.py",
                summary="SSOT probe summary",
                recommended_action="Fix probe",
                occurrence_count=3,
                impact_score=18.5,
            )
            probe_p = ImprovementProposal(
                proposal_id="prop-ssot-probe",
                cluster_id="clst-ssot-probe",
                artifact_class="validator_or_code",
                autonomy_tier="TIER_C_PR_ONLY",
                risk_lane="LANE_2",
                target_path="resume_graph_engine/src/apps_rg/runtime/validators/x2.py",
                target_key=None,
                expected_current_value=None,
                proposed_value_or_patch={"action": "open_pr_for_root_cause_fix"},
                step_delta_magnitude=0.0,
                evidence_trace_ids=["probe-1"],
                source_receipt_digests=[],
                provenance_digest="b" * 64,
                evaluation_plan=["isolated_worktree_fix"],
                status="PROPOSED",
                expires_at_utc="2026-12-31T00:00:00Z",
            )
            q_probe = build_atomic_remediation_question(probe_f, probe_p)
            if len(q_probe.get("questions") or []) != 1:
                v6_errs.append("flywheel_dispatcher_emitted_non_atomic_question_count")
            pres_errs = validate_hitl_presentation(q_probe, enforce_visibility_and_jargon=True)
            if pres_errs:
                v6_errs.append(f"flywheel_dispatcher_jargon_or_length_violation:{pres_errs[0]}")
    except Exception as exc:  # guardian: allow-broad-exception -- fail closed on dispatcher parity import or probe error
        v6_errs.append(f"flywheel_dispatcher_probe_error:{exc}")

    vectors["V6_FLYWHEEL_HITL_REMEDIATION_PARITY"] = "PASS" if not v6_errs else "FAIL"
    for e in v6_errs:
        violations.append({"vector": "V6_FLYWHEEL_HITL_REMEDIATION_PARITY", "message": e})

    # Vector 7: External-Rubric Human Calibration, Nuanced Gold Corpus & Drift Receipt Parity (DIE Parity).
    v7_errs: list[str] = []
    try:
        from apps_eval.graders.judge.external_rubric_store import (
            DEFAULT_EXTERNAL_RUBRIC_REL_PATH,
            DEFAULT_HUMAN_GOLD_STORE_REL_PATH,
            ExternalRubricHumanStore,
            load_and_verify_external_rubric,
        )
        from apps_eval.graders.judge.gold_corpus import load_gold_candidates_jsonl, validate_stratification
        from apps_eval.graders.judge.ide_judge_drift_evaluator import verify_drift_receipt_digest

        rubric_path = root / DEFAULT_EXTERNAL_RUBRIC_REL_PATH
        rubric = load_and_verify_external_rubric(rubric_path)
        rubric_sha = str(rubric["rubric_sha256"])

        store_path = root / DEFAULT_HUMAN_GOLD_STORE_REL_PATH
        if store_path.is_file():
            ExternalRubricHumanStore(store_path=store_path, rubric_path=rubric_path).load_records()

        rg_gold_path = root / "data" / "judge_calibration" / "resume_gold_candidates.v1.jsonl"
        lic_gold_path = root / "data" / "judge_calibration" / "outreach_gold_candidates.v1.jsonl"
        if not rg_gold_path.is_file() or not lic_gold_path.is_file():
            v7_errs.append("missing_curated_48_item_gold_corpora")
        else:
            rg_errs = validate_stratification(load_gold_candidates_jsonl(rg_gold_path), engine="resume_engine")
            lic_errs = validate_stratification(load_gold_candidates_jsonl(lic_gold_path), engine="outreach_engine")
            v7_errs.extend(rg_errs)
            v7_errs.extend(lic_errs)

        rep_dir = root / "reports" / "ide_judge_calibration"
        if rep_dir.is_dir():
            for r_path in sorted(rep_dir.glob("*_drift_receipt.json")):
                raw_obj = json.loads(r_path.read_text(encoding="utf-8"))
                if not verify_drift_receipt_digest(raw_obj):
                    v7_errs.append(f"tampered_drift_receipt_digest:{r_path.name}")
                elif str(raw_obj.get("external_rubric_sha256") or "") != rubric_sha:
                    v7_errs.append(f"drift_receipt_rubric_sha256_mismatch:{r_path.name}")
                elif bool(raw_obj.get("drift_detected")) or not bool(raw_obj.get("passed", False)):
                    v7_errs.append(f"unresolved_ide_judge_drift_receipt:{r_path.name}")
    except Exception as exc:  # guardian: allow-broad-exception -- fail closed on V7 external rubric or gold corpus audit error
        v7_errs.append(f"external_rubric_human_drift_audit_error:{exc}")

    vectors["V7_EXTERNAL_RUBRIC_HUMAN_DRIFT"] = "PASS" if not v7_errs else "FAIL"
    for e in v7_errs:
        violations.append({"vector": "V7_EXTERNAL_RUBRIC_HUMAN_DRIFT", "message": e})

    return {
        "schema_version": "agents.multi_ssot_judge_gate_drift.v1",
        "status": "PASS" if not violations else "FAIL",
        "vectors": vectors,
        "violation_count": len(violations),
        "violations": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit 5-vector multi-SSOT judge and gate drift.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    report = audit_multi_ssot_judge_gate_drift(Path(args.repo_root).resolve())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"[multi-ssot-judge-gate-drift] status={report['status']} violations={report['violation_count']}")
        for vec, st in report["vectors"].items():
            print(f"  - {vec}: {st}")
        for v in report["violations"]:
            print(f"      FAIL [{v['vector']}]: {v['message']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
