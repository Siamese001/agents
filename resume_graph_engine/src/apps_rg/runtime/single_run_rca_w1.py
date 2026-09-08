"""Extract one verified historical run from the W5 integrated evidence bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PACKET_FILENAME = "single_run_w1_evidence_packet.json"
SCHEMA_VERSION = "apps_rg.single_run_rca_w1.v1"


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    parsed = json.loads(payload.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON object: {path}")
    return parsed, payload


def _file_binding(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "artifact_ref": path.name,
        "byte_length": len(payload),
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "semantic_digest": str(json.loads(payload.decode("utf-8")).get("semantic_digest", "")),
    }


def _bound_artifacts(case: dict[str, Any], evidence_root: Path) -> list[dict[str, Any]]:
    artifacts = case.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("integrated case has no replay artifact bindings")
    verified: list[dict[str, Any]] = []
    for row in artifacts:
        if not isinstance(row, dict):
            raise ValueError("integrated artifact binding is not an object")
        ref = str(row.get("artifact_ref") or "")
        candidate = (evidence_root / ref).resolve()
        try:
            candidate.relative_to(evidence_root)
        except ValueError as exc:
            raise ValueError(f"artifact ref escapes W5 evidence root: {ref}") from exc
        if not candidate.is_file():
            raise ValueError(f"bound W5 artifact is missing: {ref}")
        payload = candidate.read_bytes()
        actual_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        if row.get("byte_length") != len(payload) or row.get("sha256") != actual_digest:
            raise ValueError(f"bound W5 artifact digest mismatch: {ref}")
        verified.append({**row, "verified": True})
    return verified


def _require_case_scope(case: dict[str, Any]) -> dict[str, int]:
    checks = case.get("checks")
    if case.get("status") != "PASS" or not isinstance(checks, dict) or not all(checks.values()):
        raise ValueError("integrated case did not pass all W5 checks")
    l0 = case.get("l0_parallel")
    judges = case.get("historical_saved_judges")
    contracts = case.get("contract_handoffs")
    apps_eval = case.get("apps_eval")
    l6 = case.get("l6")
    terminal = case.get("terminal")
    if not all(isinstance(value, dict) for value in (l0, judges, contracts, apps_eval, l6, terminal)):
        raise ValueError("integrated case is missing required RCA sections")
    lane_count = len(l0.get("lane_results", []))
    judge_count = len(judges.get("results", []))
    handoff_count = len(contracts.get("entries", []))
    if lane_count != 11 or judge_count != 21 or handoff_count != 21:
        raise ValueError(
            f"unexpected single-run scope: lanes={lane_count}, judges={judge_count}, handoffs={handoff_count}"
        )
    if not all(row.get("artifact_replay_complete") is True for row in l0["lane_results"]):
        raise ValueError("not every saved generation lane is replay-complete")
    if judges.get("passing_result_count") != 21:
        raise ValueError("historical judge inventory is not 21 passing results")
    if apps_eval.get("execution_complete") is not True or l6.get("execution_complete") is not True:
        raise ValueError("post-runtime stages were not executed")
    if terminal.get("terminal_closed") is not True or terminal.get("terminal_outcome") != "BLOCKED_NON_PRODUCT":
        raise ValueError("historical run is not sealed as BLOCKED_NON_PRODUCT")
    if terminal.get("x2_aggregation_status") != "PASS":
        raise ValueError("X2 aggregation completion is not bound")
    return {"generation_lanes": lane_count, "judges": judge_count, "contract_handoffs": handoff_count}


def emit_single_run_w1_evidence_packet(
    *,
    w0_freeze_path: Path,
    integrated_manifest_path: Path,
    w5_evidence_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Write one immutable RCA evidence packet from existing W5 evidence."""

    freeze_path = w0_freeze_path.resolve(strict=True)
    integrated_path = integrated_manifest_path.resolve(strict=True)
    evidence_root = w5_evidence_root.resolve(strict=True)
    freeze, freeze_bytes = _read_json(freeze_path)
    integrated, integrated_bytes = _read_json(integrated_path)
    if freeze.get("status") != "PASS" or freeze.get("wave") != "W0" or freeze.get("next_wave_authorized") is not True:
        raise ValueError("W0 freeze does not authorize W1")
    if integrated.get("status") != "PASS":
        raise ValueError("integrated W5 manifest is not PASS")
    source_run_id = str(freeze.get("source_run_id") or "")
    cases = [
        row for row in integrated.get("cases", [])
        if isinstance(row, dict) and row.get("source_run_id") == source_run_id
    ]
    if len(cases) != 1:
        raise ValueError(f"expected exactly one integrated case for {source_run_id}")
    case = cases[0]
    counts = _require_case_scope(case)
    artifacts = _bound_artifacts(case, evidence_root)
    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "wave": "W1",
        "status": "PASS",
        "scope": "SINGLE_RUN_RCA_EVIDENCE_EXTRACTION",
        "replay_mode": "POST_RUNTIME_ARTIFACT_ONLY",
        "source_run_id": source_run_id,
        "source_manifest_sha256": freeze["source_manifest_sha256"],
        "w0_freeze": _file_binding(freeze_path, freeze_bytes),
        "integrated_manifest": _file_binding(integrated_path, integrated_bytes),
        "extracted_counts": counts,
        "verified_w5_artifacts": artifacts,
        "historical_run": case,
        "production_authority_granted": False,
        "publication_allowed": False,
        "next_wave_authorized": True,
    }
    packet["semantic_digest"] = _canonical_digest(packet)
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / PACKET_FILENAME
    packet_path.write_text(json.dumps(packet, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {**packet, "packet_path": packet_path.as_posix()}


__all__ = ["PACKET_FILENAME", "SCHEMA_VERSION", "emit_single_run_w1_evidence_packet"]
