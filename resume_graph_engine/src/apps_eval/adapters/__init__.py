"""Narrow optional live adapters for product runtimes."""

from apps_eval.adapters.outreach_engine import run_apps_lic_live, run_outreach_engine_live
from apps_eval.adapters import resume_graph_engine as _resume_graph_engine
from apps_eval.adapters import outreach_engine as _outreach_engine

# Canonical apps_rg L2 E1-E5 artifacts. Keeping this additive here avoids
# duplicating the live adapter while making every direct/submodule import see
# the same role map (package __init__ runs before the submodule import returns).
_resume_graph_engine._LANE_ARTIFACT_ROLE_BY_NAME.update(
    {
        "l2_execution_packet.json": "l2_execution_packet",
        "frozen_execution_context.json": "frozen_execution_context",
        "prep_receipt.json": "prep_receipt",
        "validation_receipt.json": "validation_receipt",
        "attempt_receipt.json": "attempt_receipt",
        "heal_receipt.json": "heal_receipt",
        "seal_receipt.json": "seal_receipt",
        "l2_receipt_bundle.json": "l2_receipt_bundle",
        "sealed_l2_artifact.json": "sealed_l2_artifact",
        "l2_handoff_receipt.json": "l2_handoff_receipt",
    }
)

run_apps_rg_live = _resume_graph_engine.run_apps_rg_live
run_resume_graph_engine_live = _resume_graph_engine.run_resume_graph_engine_live

# Compatibility module aliases
apps_rg = _resume_graph_engine
apps_lic = _outreach_engine
resume_graph_engine = _resume_graph_engine
outreach_engine = _outreach_engine

__all__ = [
    "run_apps_lic_live",
    "run_apps_rg_live",
    "run_outreach_engine_live",
    "run_resume_graph_engine_live",
    "apps_rg",
    "apps_lic",
    "resume_graph_engine",
    "outreach_engine",
]
