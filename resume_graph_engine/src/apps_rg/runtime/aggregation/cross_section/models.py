"""Shared models, constants, and claim extraction helpers for cross-section X2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.runtime.aggregation._digest_utils import normalize_claim_text, sha256_utf8, tokenize
from apps_rg.runtime.assembly.final_resume_x2 import GENERATED_LANE_IDS
from apps_rg.runtime.contracts.metric_lexical_primitives import METRIC_PATTERN

# Strongest placement wins (lower index = higher priority).
SECTION_PRIORITY: tuple[str, ...] = (
    "headline",
    "executive_summary",
    "slalom_narrative",
    "unify_narrative",
    "ibm_narrative",
    "insurtech_narrative",
    "ey_narrative",
    "slalom_bullets",
    "unify_bullets",
    "ibm_bullets",
    "insurtech_bullets",
    "ey_bullets",
    "competencies",
)

EM_DASH = "\u2014"

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_WARN = "WARN"
VERDICT_UNKNOWN = "UNKNOWN"
APP_X2_QUALITY_AUTHORITY_SCOPE = "apps_rg_cross_section_product_quality_not_core_exit_matrix"

GRAPH_COHERENCE_MIN_ACTIVE_SECTIONS = 3
GRAPH_COHERENCE_MIN_UNIQUE_SKILLS = 4


@dataclass
class CrossSectionGateResult:
    gate_id: str
    verdict: str
    decisive_reason: str | None = None
    threshold: Any = None
    observed: Any = None
    evidence_refs: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "verdict": self.verdict,
            "authority_scope": APP_X2_QUALITY_AUTHORITY_SCOPE,
            "core_x2_matrix_authority": False,
            "decisive_reason": self.decisive_reason,
            "threshold": self.threshold,
            "observed": self.observed,
            "evidence_refs": self.evidence_refs or [],
            "pass": self.verdict == VERDICT_PASS,
        }


def _priority(section_id: str) -> int:
    try:
        return SECTION_PRIORITY.index(section_id)
    except ValueError:
        return 999


def _extract_claim_rows(section: dict[str, Any]) -> list[dict[str, Any]]:
    sid = str(section.get("section_id") or "")
    snap = section.get("l2_output_snapshot")
    if not isinstance(snap, dict):
        return []
    rows: list[dict[str, Any]] = []
    seen_norms: set[str] = set()
    ledger = snap.get("claim_ledger")
    if isinstance(ledger, list):
        for i, row in enumerate(ledger):
            if not isinstance(row, dict):
                continue
            ct = str(row.get("claim_text") or row.get("claim_summary") or "").strip()
            norm = normalize_claim_text(ct) if ct else ""
            if not norm or norm in seen_norms:
                continue
            seen_norms.add(norm)
            sf = [str(x) for x in (row.get("source_fact_ids") or []) if x]
            key = sha256_utf8(f"{sid}|{i}|{norm}|{','.join(sorted(sf))}")
            rows.append({"claim_key": key, "section_id": sid, "claim_text": ct, "source_fact_ids": sf, "normalized_text": norm})
    bullets = snap.get("bullets")
    if isinstance(bullets, list) and not rows:
        for b in bullets:
            if not isinstance(b, dict):
                continue
            ct = str(b.get("bullet_text") or "").strip()
            norm = normalize_claim_text(ct) if ct else ""
            if not norm or norm in seen_norms:
                continue
            seen_norms.add(norm)
            sf = [str(x) for x in (b.get("source_fact_ids") or []) if x]
            key = sha256_utf8(f"{sid}|bullet|{str(b.get('bullet_id') or '')}|{norm}")
            rows.append({"claim_key": key, "section_id": sid, "claim_text": ct, "source_fact_ids": sf, "normalized_text": norm})
    return rows


def _section_plaintext(section: dict[str, Any]) -> str:
    snap = section.get("l2_output_snapshot")
    if not isinstance(snap, dict):
        copied_raw = section.get("copied_text_exact")
        copied_str = ""
        if isinstance(copied_raw, str) and copied_raw.strip():
            copied_str = copied_raw.strip()
            if copied_str.startswith(("{", "[")):
                try:
                    copied_str = json.dumps(json.loads(copied_str), ensure_ascii=False)
                except (json.JSONDecodeError, ValueError):
                    pass
        parts = [copied_str] if copied_str else []
        parts.extend(str(section.get(k)).strip() for k in ("role_narrative", "earlier_quantitative_foundation", "degree", "institution", "name") if isinstance(section.get(k), str) and str(section.get(k)).strip())
        for b in section.get("bullets") or []:
            if isinstance(b, dict) and str(b.get("text") or b.get("bullet_text") or "").strip():
                parts.append(str(b.get("text") or b.get("bullet_text") or "").strip())
        return "\n".join(parts)
    parts = [str(snap.get(k)).strip() for k in ("headline_line", "resume_display_text", "narrative_sentence") if isinstance(snap.get(k), str) and str(snap.get(k)).strip()]
    for b in snap.get("bullets") or []:
        if isinstance(b, dict):
            parts.append(str(b.get("bullet_text") or ""))
    for c in snap.get("competencies") or []:
        parts.append(c if isinstance(c, str) else str(c.get("term") or c.get("competency") or "") if isinstance(c, dict) else "")
    return "\n".join(parts)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _allowed_fact_union(sealed_index: dict[str, Any], repo: Path) -> set[str]:
    allowed: set[str] = set()
    for ptr in sealed_index.get("pointers") or []:
        if not isinstance(ptr, dict):
            continue
        receipt_rel = ptr.get("artifact_dir")
        if not isinstance(receipt_rel, str):
            continue
        receipt = repo / receipt_rel.replace("\\", "/") / "x2_source_fact_pool_receipt.json"
        if not receipt.is_file():
            continue
        try:
            blob = json.loads(receipt.read_text(encoding="utf-8"))
            for fid in blob.get("source_fact_ids_checked") or []:
                allowed.add(str(fid))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return allowed


def _iter_mappings(value: Any):
    if isinstance(value, Mapping):
        yield value
        for inner in value.values():
            yield from _iter_mappings(inner)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            yield from _iter_mappings(inner)


def _collect_string_values(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, str):
        text = value.strip()
        if text:
            out.add(text)
    elif isinstance(value, (list, tuple, set)):
        for inner in value:
            out.update(_collect_string_values(inner))
    return out


def _collect_values_for_keys(payloads: Sequence[Any], keys: set[str]) -> set[str]:
    out: set[str] = set()
    for payload in payloads:
        for row in _iter_mappings(payload):
            for key in keys:
                if key in row:
                    out.update(_collect_string_values(row.get(key)))
    return out


def _load_runtime_payload_for_section(
    *,
    repo: Path,
    sealed_index: dict[str, Any],
    section_id: str,
) -> dict[str, Any]:
    ptrs = sealed_index.get("pointers") or []
    for ptr in ptrs:
        if not isinstance(ptr, dict) or str(ptr.get("lane") or "") != section_id:
            continue
        artifact_dir = str(ptr.get("artifact_dir") or "").replace("\\", "/")
        if not artifact_dir:
            return {}
        payload_path = repo / artifact_dir / "runtime_payload.json"
        if not payload_path.is_file():
            return {}
        try:
            blob = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return {}
        return blob if isinstance(blob, dict) else {}
    return {}


_PRIMARY_COHERENCE_SECTIONS: frozenset[str] = frozenset(
    {
        "executive_summary",
        "competencies",
        "slalom_bullets",
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
        "ey_bullets",
        "slalom_narrative",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
        "ey_narrative",
    }
)
_PILLAR_COHERENCE_JACCARD_WARN_THRESHOLD = 0.4
