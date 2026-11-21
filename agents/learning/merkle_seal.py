"""Six-stage sequential Merkle hash chain sealer (LP0..LP5) for post-runtime learning runs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.contracts.digests import canonical_sha256, stable_id
from apps_eval.contracts.schemas import utc_now_iso

MANDATORY_LEARNING_STAGES: tuple[str, ...] = ("LP0", "LP1", "LP2", "LP3", "LP4", "LP5")


def compute_merkle_chain(stage_events: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]]:
    """Compute sequential Merkle chain root H_i = sha256(H_{i-1} + sha256(canon(event_i)))."""
    if not stage_events:
        raise ValueError("Cannot seal empty stage_events list")
    event_hashes: list[str] = []
    running = ""
    for ev in stage_events:
        ev_hash = canonical_sha256(ev)
        event_hashes.append(ev_hash)
        if not running:
            running = ev_hash
        else:
            running = hashlib.sha256(f"{running}{ev_hash}".encode("utf-8")).hexdigest()
    return running, event_hashes


def seal_learning_stages(
    *,
    proposal_id: str,
    run_id: str,
    stage_events: Sequence[Mapping[str, Any]],
    terminal_outcome: str = "PASS",
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Verify all mandatory stages LP0..LP5 are present, compute Merkle root, and persist seal JSON."""
    observed = [str(ev.get("stage") or "") for ev in stage_events]
    missing = [st for st in MANDATORY_LEARNING_STAGES if st not in observed]
    if missing:
        raise ValueError(f"Missing mandatory learning stages for Merkle seal: {missing}")

    merkle_root, event_hashes = compute_merkle_chain(stage_events)
    seal = {
        "schema_version": "agents.learning_merkle_seal.v1",
        "seal_id": stable_id("seal", proposal_id, run_id, merkle_root, length=16),
        "run_id": run_id,
        "proposal_id": proposal_id,
        "stages_sealed": observed,
        "stage_count": len(observed),
        "terminal_outcome": terminal_outcome,
        "merkle_root": merkle_root,
        "event_hashes": event_hashes,
        "stage_events": [dict(ev) for ev in stage_events],
        "sealed_at_utc": utc_now_iso(),
    }
    if output_dir is not None:
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        seal_path = out_dir / f"run_seal_{proposal_id}.json"
        tmp = seal_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, seal_path)
        seal["seal_path"] = seal_path.as_posix()
    return seal


def verify_merkle_seal(seal: Mapping[str, Any]) -> bool:
    """Independently recompute Merkle chain from stage_events and verify equality with merkle_root."""
    events = seal.get("stage_events") or []
    recorded_root = str(seal.get("merkle_root") or "")
    if not events or len(recorded_root) != 64:
        return False
    observed = [str(ev.get("stage") or "") for ev in events]
    if any(st not in observed for st in MANDATORY_LEARNING_STAGES):
        return False
    recomputed_root, recomputed_hashes = compute_merkle_chain(events)
    return recomputed_root == recorded_root and recomputed_hashes == list(seal.get("event_hashes") or [])
