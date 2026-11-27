"""Thin L0 bridge binding `agents` to centralized core-governance and eval-flywheel SSOTs via importlib."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Sequence

from infrastructure.config.env_loader import get_env_optional_path

_DEFAULT_MCP_DIR = Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp"
_MCP_DIR = (get_env_optional_path("CORE_GOVERNANCE_MCP_DIR") or _DEFAULT_MCP_DIR).resolve()
_DEFAULT_EVAL_FLYWHEEL_MCP_DIR = Path.home() / ".gemini" / "config" / "plugins" / "eval-flywheel" / "mcp"
_EVAL_FLYWHEEL_MCP_DIR = (
    get_env_optional_path("EVAL_FLYWHEEL_MCP_DIR") or _DEFAULT_EVAL_FLYWHEEL_MCP_DIR
).resolve()


def _load_plugin_module(name: str, search_dirs: Sequence[Path]) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    candidates = [d / f"{name}.py" for d in search_dirs]
    target = next((p for p in candidates if p.is_file()), candidates[0])
    if not target.is_file():
        raise FileNotFoundError(f"Unable to load centralized module {name} from {target}")
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load centralized module {name} from {target}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


for _dep in (
    "atomic_concurrency",
    "workspace_parity_engine",
    "session_contract",
):
    _load_plugin_module(_dep, (_MCP_DIR,))

for _dep in (
    "atomic_io",
    "eval_flywheel_lifecycle",
    "eval_flywheel_longitudinal",
    "eval_flywheel_store",
    "eval_flywheel_harvester",
    "eval_flywheel_shield_core",
):
    _load_plugin_module(_dep, (_EVAL_FLYWHEEL_MCP_DIR, _MCP_DIR))

_life = _load_plugin_module("eval_flywheel_lifecycle", (_EVAL_FLYWHEEL_MCP_DIR, _MCP_DIR))
_store = _load_plugin_module("eval_flywheel_store", (_EVAL_FLYWHEEL_MCP_DIR, _MCP_DIR))
_harv = _load_plugin_module("eval_flywheel_harvester", (_EVAL_FLYWHEEL_MCP_DIR, _MCP_DIR))
_shld = _load_plugin_module("eval_flywheel_shield_core", (_EVAL_FLYWHEEL_MCP_DIR, _MCP_DIR))

PEAK_EROSION_FLOOR_PCT = _life.PEAK_EROSION_FLOOR_PCT
POST_FIX_BASELINE_CLEAN_STREAK = _life.POST_FIX_BASELINE_CLEAN_STREAK
SHIELD_SLA_SECONDS = _life.SHIELD_SLA_SECONDS
STALE_APPROVED_HOURS = _life.STALE_APPROVED_HOURS
UNIVERSAL_FLYWHEEL_POLICY = _life.UNIVERSAL_FLYWHEEL_POLICY
collect_stale_approved_findings = _life.collect_stale_approved_findings
evaluate_dual_anchor_rolling_drift = _life.evaluate_dual_anchor_rolling_drift
load_universal_flywheel_policy = _life.load_universal_flywheel_policy
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
verify_unmocked_runtime_environment = _shld.verify_unmocked_runtime_environment

__all__ = [
    "PEAK_EROSION_FLOOR_PCT",
    "POST_FIX_BASELINE_CLEAN_STREAK",
    "SHIELD_SLA_SECONDS",
    "STALE_APPROVED_HOURS",
    "UNIVERSAL_FLYWHEEL_POLICY",
    "collect_judge_and_aux_drift_findings",
    "collect_stale_approved_findings",
    "compute_finding_fingerprint",
    "core_compute_impact_score",
    "evaluate_dual_anchor_rolling_drift",
    "expand_reverse_python_importers",
    "extract_correction_source_id",
    "harvest_borderline_candidates",
    "load_universal_flywheel_policy",
    "normalize_iso_z",
    "resolve_lifecycle_transition",
    "resolve_runtime_version_stamps",
    "select_post_fix_baseline_scores",
    "stamp_resolution_watermark",
    "verify_finding_closeout_proof",
    "verify_judge_drift_receipt",
    "verify_unmocked_runtime_environment",
]
