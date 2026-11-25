"""Diff-scoped PR gate verifying fresh, disk-hash-matched, unprimed blind judge receipts."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from apps_eval.graders.judge.blind_protocol import validate_blind_judge_verdict_provenance


@dataclass(frozen=True)
class JudgeGovernedSurface:
    surface_id: str
    source_globs: tuple[str, ...]
    receipt_rel_path: str
    artifact_rel_path: str
    min_distinct_families: int = 1


DEFAULT_JUDGE_GOVERNED_SURFACES: tuple[JudgeGovernedSurface, ...] = (
    JudgeGovernedSurface(
        surface_id="apps_rg_executive_summary",
        source_globs=(
            "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_*.py",
            "resume_graph_engine/src/apps_rg/runtime/sections/*_v2/*.py",
            "resume_graph_engine/src/apps_rg/runtime/judges/*.py",
            "resume_graph_engine/src/apps_rg/prompt_assembly/templates/executive_summary*.yaml",
        ),
        receipt_rel_path="artifacts/eval_harness/judge_receipts/apps_rg_executive_summary_receipt.json",
        artifact_rel_path="artifacts/eval_harness/judge_receipts/apps_rg_executive_summary_artifact.json",
        min_distinct_families=1,
    ),
    JudgeGovernedSurface(
        surface_id="apps_rg_whole_coherence",
        source_globs=(
            "resume_graph_engine/src/apps_rg/runtime/assembly/final_resume_assembly*.py",
            "resume_graph_engine/src/apps_rg/runtime/assembly/full_resume_llm_coherence*.py",
        ),
        receipt_rel_path="artifacts/eval_harness/judge_receipts/apps_rg_whole_coherence_receipt.json",
        artifact_rel_path="artifacts/eval_harness/judge_receipts/apps_rg_whole_coherence_artifact.json",
        min_distinct_families=1,
    ),
    JudgeGovernedSurface(
        surface_id="apps_lic_outreach_sequence",
        source_globs=(
            "outreach_engine/src/apps_lic/pipeline/orchestrator_pkg/*.py",
            "outreach_engine/src/apps_lic/judges/*.py",
            "outreach_engine/src/apps_lic/judges/*/*.py",
        ),
        receipt_rel_path="artifacts/eval_harness/judge_receipts/apps_lic_outreach_receipt.json",
        artifact_rel_path="artifacts/eval_harness/judge_receipts/apps_lic_outreach_artifact.json",
        min_distinct_families=1,
    ),
    JudgeGovernedSurface(
        surface_id="apps_research_company_brief",
        source_globs=(
            "apps_research/engines/company_brief_engine.py",
            "apps_research/engines/company_brief/*.py",
            "apps_research/engines/judges/*.py",
        ),
        receipt_rel_path="artifacts/eval_harness/judge_receipts/apps_research_company_brief_receipt.json",
        artifact_rel_path="artifacts/eval_harness/judge_receipts/apps_research_company_brief_artifact.json",
        min_distinct_families=1,
    ),
    JudgeGovernedSurface(
        surface_id="agents_graph_hygiene",
        source_globs=(
            "resume_graph_engine/src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json",
            "resume_graph_engine/src/apps_rg/fact_inventory/*_role_episode_bundles.json",
            "resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite",
            "tools/apply_graph_hygiene_remediation.py",
            "tools/graph_hygiene_judge_v3.py",
        ),
        receipt_rel_path="artifacts/eval_harness/judge_receipts/agents_graph_hygiene_receipt.json",
        artifact_rel_path="artifacts/eval_harness/judge_receipts/agents_graph_hygiene_artifact.json",
        min_distinct_families=2,
    ),
)


def _matches_any(path_str: str, globs: Sequence[str]) -> bool:
    norm = path_str.replace("\\", "/")
    return any(fnmatch.fnmatch(norm, g) for g in globs)


def verify_diff_judge_receipts(
    changed_files: Sequence[str],
    worktree_root: Path,
    *,
    surfaces: Sequence[JudgeGovernedSurface] = DEFAULT_JUDGE_GOVERNED_SURFACES,
) -> dict[str, Any]:
    """Verify every touched judge-governed surface carries a fresh, unprimed, hash-bound receipt."""
    root = Path(worktree_root).resolve()
    triggered: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []

    for surface in surfaces:
        matched = [f for f in changed_files if _matches_any(f, surface.source_globs)]
        if not matched:
            continue
        receipt_path = root / surface.receipt_rel_path
        artifact_path = root / surface.artifact_rel_path
        entry: dict[str, Any] = {
            "surface_id": surface.surface_id,
            "matched_files": matched,
            "receipt_path": surface.receipt_rel_path,
            "status": "PASS",
            "reasons": [],
        }

        if not receipt_path.is_file():
            entry["status"] = "FAIL"
            entry["reasons"] = ["MISSING_BOUND_JUDGE_RECEIPT"]
            violations.append({"surface_id": surface.surface_id, "reasons": entry["reasons"]})
            triggered.append(entry)
            continue

        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entry["status"] = "FAIL"
            entry["reasons"] = [f"INVALID_RECEIPT_JSON:{exc}"]
            violations.append({"surface_id": surface.surface_id, "reasons": entry["reasons"]})
            triggered.append(entry)
            continue

        if receipt.get("llm_judge_executed") is False:
            entry["status"] = "FAIL"
            entry["reasons"].append("STAGE_B_LLM_JUDGE_NOT_EXECUTED")

        if "normalized_unit_score" in receipt:
            nus = receipt.get("normalized_unit_score")
            if nus is None or isinstance(nus, bool) or not (0.0 <= float(nus) <= 1.0):
                entry["status"] = "FAIL"
                entry["reasons"].append(f"NON_UNIT_NORMALIZED_SCORE:{nus!r}")

        verdict_tok = str(receipt.get("verdict") or receipt.get("status") or "").upper()
        if verdict_tok != "PASS" or receipt.get("passed") is False:
            entry["status"] = "FAIL"
            entry["reasons"].append(f"RECEIPT_VERDICT_NOT_PASS:{verdict_tok or receipt.get('passed')}")

        prov_ok, prov_reasons = validate_blind_judge_verdict_provenance(
            receipt,
            artifact_disk_path=artifact_path,
            require_no_deterministic_priming=True,
            allow_external_http=False,
            min_distinct_families=surface.min_distinct_families,
        )
        if not prov_ok:
            entry["status"] = "FAIL"
            entry["reasons"].extend(prov_reasons)

        if entry["status"] != "PASS":
            violations.append({"surface_id": surface.surface_id, "reasons": entry["reasons"]})
        triggered.append(entry)

    return {
        "schema_version": "agents.judge_receipt_gate.v1",
        "status": "PASS" if not violations else "FAIL",
        "triggered_surfaces": triggered,
        "violations": violations,
        "surfaces_configured": [asdict(s) for s in surfaces],
    }
