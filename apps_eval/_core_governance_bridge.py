"""Thin L0 bridge binding `agents` to the centralized core-governance evaluation flywheel SSOT via importlib."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType

from infrastructure.config.env_loader import get_env_optional_path

_DEFAULT_MCP_DIR = Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp"
_MCP_DIR = (get_env_optional_path("CORE_GOVERNANCE_MCP_DIR") or _DEFAULT_MCP_DIR).resolve()


def _load_core_gov_module(name: str) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    target = _MCP_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load core-governance module {name} from {target}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


for _dep in (
    "workspace_parity_engine",
    "session_contract",
    "eval_flywheel_lifecycle",
    "eval_flywheel_longitudinal",
    "eval_flywheel_store",
    "eval_flywheel_harvester",
    "eval_flywheel_shield_core",
):
    _load_core_gov_module(_dep)

_life = _load_core_gov_module("eval_flywheel_lifecycle")
_store = _load_core_gov_module("eval_flywheel_store")
_harv = _load_core_gov_module("eval_flywheel_harvester")
_shld = _load_core_gov_module("eval_flywheel_shield_core")

PEAK_EROSION_FLOOR_PCT = _life.PEAK_EROSION_FLOOR_PCT
POST_FIX_BASELINE_CLEAN_STREAK = _life.POST_FIX_BASELINE_CLEAN_STREAK
STALE_APPROVED_HOURS = _life.STALE_APPROVED_HOURS
collect_stale_approved_findings = _life.collect_stale_approved_findings
evaluate_dual_anchor_rolling_drift = _life.evaluate_dual_anchor_rolling_drift
normalize_iso_z = _life.normalize_iso_z
resolve_lifecycle_transition = _life.resolve_lifecycle_transition
resolve_runtime_version_stamps = _life.resolve_runtime_version_stamps
select_post_fix_baseline_scores = _life.select_post_fix_baseline_scores
stamp_resolution_watermark = _life.stamp_resolution_watermark
verify_finding_closeout_proof = _life.verify_finding_closeout_proof

compute_finding_fingerprint = _store.compute_finding_fingerprint
core_compute_impact_score = _store.compute_impact_score
extract_correction_source_id = _store.extract_correction_source_id

collect_judge_and_aux_drift_findings = _harv.collect_judge_and_aux_drift_findings
harvest_borderline_candidates = _harv.harvest_borderline_candidates
verify_judge_drift_receipt = _harv.verify_judge_drift_receipt

expand_reverse_python_importers = _shld.expand_reverse_python_importers

__all__ = [
    "PEAK_EROSION_FLOOR_PCT",
    "POST_FIX_BASELINE_CLEAN_STREAK",
    "STALE_APPROVED_HOURS",
    "collect_judge_and_aux_drift_findings",
    "collect_stale_approved_findings",
    "compute_finding_fingerprint",
    "core_compute_impact_score",
    "evaluate_dual_anchor_rolling_drift",
    "expand_reverse_python_importers",
    "extract_correction_source_id",
    "harvest_borderline_candidates",
    "normalize_iso_z",
    "resolve_lifecycle_transition",
    "resolve_runtime_version_stamps",
    "select_post_fix_baseline_scores",
    "stamp_resolution_watermark",
    "verify_finding_closeout_proof",
    "verify_judge_drift_receipt",
]
