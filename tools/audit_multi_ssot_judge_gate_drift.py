#!/usr/bin/env python3
"""5-Vector Multi-SSOT Judge & Gate Drift Auditor for `agents`.

Cross-checks:
- Vector 1 (V1_RUBRIC_TO_CONFIG): config/judges/rubrics.yaml & trace_rubric.yaml integrity.
- Vector 2 (V2_PROVIDER_PROFILES_PARITY): config/provider_profiles.yaml orthogonal judge families.
- Vector 3 (V3_LIVE_NEGATIVE_PROBES): executable negative probes against Tier-1/Tier-2 judge gates.
- Vector 4 (V4_AUTO_APPLY_POLICY_BOUNDS): auto_apply_policy.yaml bounds vs routing_calibration.yaml live defaults.
- Vector 5 (V5_PINNED_REGRESSIONS_PARITY): pinned_fix_regressions.json covers all eval shield domains.
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
