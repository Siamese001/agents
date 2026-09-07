"""W7 frozen-scope and protected-holdout qualification receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


MANIFEST_VERSION = "apps_rg.protected_holdout_qualification.v1"
SUMMARY_VERSION = "apps_rg.protected_holdout_qualification_summary.v1"
DEFAULT_MANIFEST_PATH = Path(__file__).with_name("protected_holdout_qualification.v1.json")
REPO_ROOT = Path(__file__).resolve().parents[3]
PRIMARY_OUTCOMES = ("P1", "P2")
DIAGNOSTICS = ("G1", "G2", "G3", "G4", "G5", "G6")
ABLATIONS = ("retrieval", "grounding", "section_generation", "whole_resume_assembly")
ZERO_GUARDRAILS = ("unsupported_material_claim_rate", "critical_binding_error_rate", "authority_bypass_count", "holdout_leak_count", "pii_leak_count")


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    return value


def _commit(root: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _scope_without_digest(scope: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in scope.items() if key != "preregistration_digest"}


def _scope_issues(scope: Any, root: Path, observed_commit: str | None) -> tuple[set[str], set[str]]:
    blocking: set[str] = set()
    stale: set[str] = set()
    if not isinstance(scope, Mapping):
        return {"P7_FROZEN_SCOPE_INVALID"}, stale
    required = ("source_commit", "preregistered_at", "holdout_accessed_at", "preregistration_digest", "provider_model_pins_digest", "baseline_config_digest", "candidate_config_digest", "decision_rules_digest", "holdout_index_digest", "scope_files")
    if any(not scope.get(field) for field in required[:-1]) or not isinstance(scope.get("scope_files"), list):
        blocking.add("P7_FROZEN_SCOPE_INCOMPLETE")
        return blocking, stale
    if scope.get("preregistration_digest") != canonical_digest(_scope_without_digest(scope)):
        blocking.add("P7_PREREGISTRATION_DIGEST_INVALID")
    preregistered, accessed = _time(scope.get("preregistered_at")), _time(scope.get("holdout_accessed_at"))
    if preregistered is None or accessed is None:
        blocking.add("P7_HOLDOUT_TIMESTAMPS_INVALID")
    elif preregistered >= accessed:
        blocking.add("P7_PREREGISTRATION_DOES_NOT_PREDATE_HOLDOUT")
    if observed_commit is not None and scope.get("source_commit") != observed_commit:
        stale.add("P7_SOURCE_COMMIT_MISMATCH")
    files = scope.get("scope_files")
    if not isinstance(files, list) or not files:
        blocking.add("P7_SCOPE_FILES_REQUIRED")
    else:
        paths: set[str] = set()
        for binding in files:
            if not isinstance(binding, Mapping) or not isinstance(binding.get("path"), str) or not isinstance(binding.get("sha256"), str):
                blocking.add("P7_SCOPE_FILE_BINDING_INVALID")
                continue
            relative = binding["path"]
            if relative in paths:
                blocking.add("P7_SCOPE_FILE_DUPLICATE")
                continue
            paths.add(relative)
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root.resolve())
                actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except OSError:
                stale.add("P7_SCOPE_FILE_MISSING")
            except ValueError:
                blocking.add("P7_SCOPE_FILE_ESCAPES_REPOSITORY")
            else:
                if actual != binding["sha256"]:
                    stale.add("P7_SCOPE_FILE_DIGEST_MISMATCH")
    return blocking, stale


def _result_issues(results: Any) -> tuple[set[str], set[str]]:
    blocking: set[str] = set()
    failures: set[str] = set()
    if not isinstance(results, Mapping):
        return {"P7_HOLDOUT_RESULTS_INVALID"}, failures
    receipts = results.get("upstream_receipts")
    if not isinstance(receipts, Mapping) or set(receipts) != set((*PRIMARY_OUTCOMES, *DIAGNOSTICS, "guardrails")) or any(not str(value or "") for value in receipts.values()):
        blocking.add("P7_UPSTREAM_RECEIPTS_INCOMPLETE")
    if results.get("synthetic_human_labels_created") is not False:
        blocking.add("P7_SYNTHETIC_HUMAN_LABELS_FORBIDDEN")
    if results.get("holdout_evaluation_count") != 1:
        blocking.add("P7_HOLDOUT_MUST_BE_EVALUATED_ONCE")
    outcomes = results.get("primary_outcomes")
    if not isinstance(outcomes, Mapping) or set(outcomes) != set(PRIMARY_OUTCOMES):
        blocking.add("P7_PRIMARY_OUTCOMES_INCOMPLETE")
    else:
        for name, row in outcomes.items():
            if not isinstance(row, Mapping) or not all(isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool) for field in ("estimate", "ci_lower", "threshold")):
                blocking.add("P7_PRIMARY_OUTCOME_INVALID")
            elif row.get("status") != "PASS" or float(row["ci_lower"]) < float(row["threshold"]):
                failures.add(f"P7_{name}_FAILED")
    diagnostics = results.get("diagnostics")
    if not isinstance(diagnostics, Mapping) or set(diagnostics) != set(DIAGNOSTICS) or any(row != "PASS" for row in diagnostics.values()):
        failures.add("P7_DIAGNOSTIC_GATE_FAILED")
    ablations = results.get("ablations")
    if not isinstance(ablations, Mapping) or set(ablations) != set(ABLATIONS):
        blocking.add("P7_ABLATION_COVERAGE_INCOMPLETE")
    else:
        for row in ablations.values():
            if not isinstance(row, Mapping) or row.get("design") not in {"PAIRED", "RANDOMIZED", "PAIRED_RANDOMIZED"}:
                blocking.add("P7_CAUSAL_ABLATION_DESIGN_INVALID")
            elif row.get("status") != "PASS":
                failures.add("P7_ABLATION_FAILED")
    guardrails = results.get("guardrails")
    if not isinstance(guardrails, Mapping) or any(guardrails.get(name) != 0 for name in ZERO_GUARDRAILS):
        failures.add("P7_CRITICAL_GUARDRAIL_FAILED")
    slices = results.get("slices")
    if not isinstance(slices, list) or not slices:
        blocking.add("P7_SLICE_RESULTS_REQUIRED")
    elif any(not isinstance(row, Mapping) or not str(row.get("slice_id") or "") or row.get("status") != "PASS" for row in slices):
        failures.add("P7_SLICE_GATE_FAILED")
    return blocking, failures


def validate_protected_holdout_qualification(path: Path = DEFAULT_MANIFEST_PATH, *, repo_root: Path = REPO_ROOT, observed_source_commit: str | None = None) -> dict[str, Any]:
    try:
        manifest = _read(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        manifest, blocking = {}, {"P7_MANIFEST_UNREADABLE"}
    else:
        blocking = set()
    failures: set[str] = set()
    stale: set[str] = set()
    not_measured: set[str] = set()
    if manifest.get("schema_version") != MANIFEST_VERSION or not str(manifest.get("qualification_id") or ""):
        blocking.add("P7_MANIFEST_SCHEMA_INVALID")
    state = manifest.get("status")
    if state == "PENDING":
        not_measured.update({"P7_PREREGISTRATION_PENDING", "P7_PROTECTED_HOLDOUT_NOT_ACCESSED"})
    elif state == "COMPLETE":
        scope_blocking, stale = _scope_issues(manifest.get("frozen_scope"), repo_root, observed_source_commit or _commit(repo_root))
        blocking.update(scope_blocking)
        result_blocking, result_failures = _result_issues(manifest.get("results"))
        blocking.update(result_blocking)
        failures.update(result_failures)
    else:
        blocking.add("P7_STATUS_INVALID")
    status = "BLOCKED" if blocking else "STALE_SCOPE" if stale else "FAIL" if failures else "NOT_MEASURED" if not_measured else "PASS"
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_VERSION, "qualification_id": str(manifest.get("qualification_id") or path.stem), "status": status,
        "scope_state": "STALE" if stale else "PENDING" if state == "PENDING" else "CURRENT",
        "authority": {"technical_validation": True, "human_qualified": False, "release_authorizing": False, "production_authorizing": False},
        "blocking_reasons": sorted(blocking), "stale_scope_reasons": sorted(stale), "failure_reasons": sorted(failures), "not_measured_reasons": sorted(not_measured),
    }
    summary["record_digest"] = canonical_digest(summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Apps RG W7 protected-holdout qualification")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args(argv)
    result = validate_protected_holdout_qualification(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2
