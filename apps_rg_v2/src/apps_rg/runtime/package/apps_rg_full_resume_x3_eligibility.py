"""W3 — apps_rg L2 résumé product truth for package / X3 full-success eligibility (app-local)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from apps_rg.l2_recipe.resume_output_shape import (
    BLOCKED_PROVIDER_LANE,
    BLOCKED_STUB_PROVIDER,
    FAILED_ARTIFACT_GATE,
    FAILED_PROVIDER,
    REAL_RESUME,
    STUB_RECEIPT,
)
from apps_rg.runtime.product_output_policy import docx_output_required

_BLOCKED_FULL_SUCCESS: frozenset[str] = frozenset(
    {
        STUB_RECEIPT,
        FAILED_PROVIDER,
        BLOCKED_STUB_PROVIDER,
        BLOCKED_PROVIDER_LANE,
        FAILED_ARTIFACT_GATE,
    }
)


def evaluate_apps_rg_full_success_eligibility(
    *,
    manifest: Mapping[str, Any],
    run_root: Path,
) -> tuple[bool, list[str]]:
    """Return (eligible, reasons). *run_root* is the artifact directory containing the manifest file.

    Ineligible when W1/W2 product constraints are not satisfied for REAL_RESUME full success.
    """
    reasons: list[str] = []
    gs = manifest.get("apps_rg_generation_status")
    rs = manifest.get("resume_shape")
    fr = manifest.get("full_resume_generated")

    if gs is None or (isinstance(gs, str) and not str(gs).strip()):
        reasons.append("missing_generation_status")
    elif gs in _BLOCKED_FULL_SUCCESS:
        reasons.append(f"blocked_generation_status:{gs}")
    elif gs != REAL_RESUME:
        reasons.append(f"generation_status_not_real_resume:{gs!r}")

    if rs is None or (isinstance(rs, str) and not str(rs).strip()):
        reasons.append("missing_resume_shape")
    elif rs != REAL_RESUME:
        reasons.append(f"resume_shape_not_real_resume:{rs!r}")

    if fr is not True:
        reasons.append("full_resume_generated_not_true")

    require_docx = (
        docx_output_required() or manifest.get("docx_output_required") is True
    )
    if require_docx:
        dv = manifest.get("docx_verified")
        if dv is not True:
            reasons.append(f"docx_verified_not_true:{dv!r}")

    json_rel = str(
        manifest.get("generated_resume_json_relpath") or "outputs/generated_resume.json"
    )
    jp = (run_root / json_rel).resolve()

    if not jp.is_file():
        reasons.append(f"missing_generated_resume_json:{json_rel}")
    else:
        try:
            raw = jp.read_text(encoding="utf-8").strip()
            if not raw:
                reasons.append("empty_generated_resume_json")
            else:
                obj = json.loads(raw)
                if not isinstance(obj, dict) or len(obj) == 0:
                    reasons.append("generated_resume_json_not_nonempty_object")
        except (OSError, json.JSONDecodeError) as exc:
            reasons.append(f"generated_resume_json_invalid:{exc}")

    if require_docx:
        docx_rel = str(manifest.get("resume_docx_relpath") or "outputs/resume.docx")
        dp = (run_root / docx_rel).resolve()
        if not dp.is_file() or dp.stat().st_size <= 0:
            reasons.append(f"missing_or_empty_resume_docx:{docx_rel}")

    ra = manifest.get("required_artifacts")
    if isinstance(ra, dict) and ra:
        for key, val in ra.items():
            if key == "docx_verified":
                if require_docx and val is not True:
                    reasons.append(f"required_artifacts_docx_verified_false:{val!r}")
            elif val != "verified":
                reasons.append(f"required_artifact_not_verified:{key}={val!r}")

    return (len(reasons) == 0, reasons)


def evaluate_apps_rg_product_authority_eligibility(
    *,
    manifest: Mapping[str, Any],
    run_root: Path,
) -> tuple[bool, list[str]]:
    """Require output shape *and* the complete source-bound product authority chain.

    ``evaluate_apps_rg_full_success_eligibility`` remains the package-shape
    validator used by non-authorizing packaging code.  This function is the
    mandatory admission check before PRODUCT_ELIGIBILITY or a new UWG commit.
    """

    from apps_rg.runtime.authority_reconciliation import (
        derive_entry_authority,
        derive_final_assembly_authority,
    )
    from apps_rg.runtime.whole_run_exit import (
        WHOLE_RUN_EXIT_ARTIFACT,
        verify_whole_run_exit_review_packet,
    )

    root = Path(run_root).resolve()
    shape_eligible, shape_reasons = evaluate_apps_rg_full_success_eligibility(
        manifest=manifest,
        run_root=root,
    )
    reasons = list(shape_reasons)
    packet_path = root / WHOLE_RUN_EXIT_ARTIFACT
    try:
        packet_raw = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        packet: dict[str, Any] = {}
        reasons.append(f"whole_run_exit_unreadable:{type(exc).__name__}")
    else:
        packet = packet_raw if isinstance(packet_raw, dict) else {}
        if not packet:
            reasons.append("whole_run_exit_not_object")

    valid, verification_errors = verify_whole_run_exit_review_packet(root)
    if not valid:
        reasons.extend(
            f"whole_run_exit_verification:{error}" for error in verification_errors
        )
    if packet.get("status") != "PASS":
        reasons.append(f"whole_run_exit_status_not_pass:{packet.get('status')!r}")
    if packet.get("x3_disposition") != "X3D_ALLOW_FINISH":
        reasons.append(f"whole_run_exit_not_exact_x3d:{packet.get('x3_disposition')!r}")
    signals = packet.get("signals")
    signals = dict(signals) if isinstance(signals, Mapping) else {}
    if signals.get("authoritative_lane_contracts_pass") is not True:
        reasons.append("authoritative_lane_contracts_not_pass")
    if signals.get("final_assembly_product_release_eligible") is not True:
        reasons.append("final_assembly_product_release_not_eligible")

    entry = derive_entry_authority(root)
    if entry.get("entry_authorized") is not True:
        reasons.extend(
            f"entry_authority:{value}" for value in entry.get("failed_checks", [])
        )
    packet_identity = packet.get("identity")
    if not isinstance(packet_identity, Mapping) or dict(packet_identity) != entry.get(
        "identity"
    ):
        reasons.append("whole_run_exit_entry_identity_mismatch")

    final_assembly = derive_final_assembly_authority(root)
    if final_assembly.get("product_release_eligible") is not True:
        reasons.extend(
            f"final_assembly:{value}"
            for value in final_assembly.get("failed_checks", [])
        )
    unique_reasons = list(dict.fromkeys(reasons))
    return bool(shape_eligible and not unique_reasons), unique_reasons


__all__ = [
    "evaluate_apps_rg_full_success_eligibility",
    "evaluate_apps_rg_product_authority_eligibility",
]
