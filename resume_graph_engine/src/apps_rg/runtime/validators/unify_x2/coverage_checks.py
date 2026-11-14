"""Structural text-claim coverage and source fact extraction for Unify bullets."""
from __future__ import annotations

from typing import Any

from apps_rg.runtime.validators.unify_x2.constants import (
    UNIFY_BULLET_IDS,
    _COVERAGE_WS_RE,
)


def _norm_claim_ws(text: str) -> str:
    return _COVERAGE_WS_RE.sub(" ", str(text or "").strip())


def _unify_root_from_source_fact_ids(source_fact_ids: list[Any]) -> str | None:
    for raw in source_fact_ids or []:
        s = str(raw)
        if s.startswith("bul_unify_"):
            return s.split("_metric_")[0]
    return None


def _all_source_fact_ids(
    parsed: dict[str, Any] | None,
    claim_ledger: list[dict[str, Any]],
) -> set[str]:
    ids: set[str] = set()
    for bullet in (parsed or {}).get("bullets") or []:
        for fid in bullet.get("source_fact_ids") or []:
            ids.add(str(fid))
    for claim in claim_ledger:
        for fid in claim.get("source_fact_ids") or []:
            ids.add(str(fid))
        if claim.get("source_fact_id"):
            ids.add(str(claim["source_fact_id"]))
    return ids


def build_unify_bullets_text_claim_coverage(
    bullets: list[dict[str, Any]],
    claim_ledger: list[dict[str, Any]],
    allowed_fact_ids: set[str],
) -> dict[str, Any]:
    """Structural bullet↔ledger coverage (one sentence row per canonical bullet_id).

    Unlike resume prose coverage (token overlap), unify bullets map deterministically:
    ``bul_unify_NNN`` ↔ exactly one ledger row sharing that root ``source_fact_ids`` prefix.
    """
    ledger_by_root: dict[str, dict[str, Any]] = {}
    duplicate_roots: list[str] = []
    unresolved_roots = 0
    for row in claim_ledger:
        if not isinstance(row, dict):
            continue
        ids = list(row.get("source_fact_ids") or [])
        root = _unify_root_from_source_fact_ids(ids)
        if root is None:
            if str(row.get("claim_text") or "").strip():
                unresolved_roots += 1
            continue
        if root in ledger_by_root:
            duplicate_roots.append(root)
        ledger_by_root[root] = row

    by_bullet_id = {str(b.get("bullet_id")): b for b in bullets if b.get("bullet_id")}
    coverage_rows: list[dict[str, Any]] = []
    overall_pass = True
    integrity_notes: list[str] = []

    if duplicate_roots:
        overall_pass = False
        integrity_notes.append(f"duplicate_ledger_roots:{sorted(set(duplicate_roots))}")
    if unresolved_roots:
        overall_pass = False
        integrity_notes.append(f"ledger_rows_missing_unify_root:{unresolved_roots}")

    for ordinal, bid in enumerate(UNIFY_BULLET_IDS, start=1):
        bullet = by_bullet_id.get(bid)
        ledger_row = ledger_by_root.get(bid)
        btxt = str((bullet or {}).get("bullet_text") or "").strip()
        sentence_text = f"- {bid}: {btxt}"

        if bullet is None or ledger_row is None:
            overall_pass = False
            coverage_rows.append(
                {
                    "sentence_index": ordinal,
                    "bullet_id": bid,
                    "sentence_text": sentence_text,
                    "material_claims": [
                        {
                            "claim_text": "",
                            "source_fact_ids": [],
                            "support_status": "UNSUPPORTED",
                            "reason": "missing bullet or claim_ledger row for bullet_id",
                        }
                    ],
                    "sentence_pass": False,
                }
            )
            continue

        ct = str(ledger_row.get("claim_text") or "").strip()
        source_ids = list(ledger_row.get("source_fact_ids") or [])
        valid_source_ids = [
            sid for sid in source_ids if sid in allowed_fact_ids or "_metric_" in str(sid)
        ]
        ids_ok = bool(valid_source_ids)
        text_align = _norm_claim_ws(ct) == _norm_claim_ws(btxt)

        sentence_pass = True
        material_claims: list[dict[str, Any]] = []
        if not text_align:
            overall_pass = False
            sentence_pass = False
            material_claims.append(
                {
                    "claim_text": ct,
                    "source_fact_ids": source_ids,
                    "support_status": "MISALIGNED_TEXT",
                    "reason": "claim_ledger claim_text must align with bullet_text (normalized whitespace).",
                }
            )
        elif not ids_ok:
            overall_pass = False
            sentence_pass = False
            material_claims.append(
                {
                    "claim_text": ct,
                    "source_fact_ids": source_ids,
                    "support_status": "UNSUPPORTED",
                    "reason": "source_fact_ids not in allowed_fact_ids.",
                }
            )
        else:
            material_claims.append(
                {
                    "claim_text": ct,
                    "source_fact_ids": source_ids,
                    "support_status": "SUPPORTED",
                    "reason": "Structural row aligned to bullet_id and claim_ledger.",
                }
            )

        coverage_rows.append(
            {
                "sentence_index": ordinal,
                "bullet_id": bid,
                "sentence_text": sentence_text,
                "material_claims": material_claims,
                "sentence_pass": sentence_pass,
            }
        )

    return {
        "coverage_schema": "unify_bullets_structural_v1",
        "sentences": coverage_rows,
        "overall_pass": overall_pass,
        "integrity_notes": integrity_notes,
    }


def check_unify_bullets_text_claim_coverage_integrity(
    bullets: list[dict[str, Any]],
    claim_ledger: list[dict[str, Any]],
    text_claim_coverage: dict[str, Any] | None,
    allowed_fact_ids: set[str],
) -> tuple[bool, str | None]:
    """Deterministic gate: stored coverage must match a structural rebuild (no stale loops)."""
    expected = build_unify_bullets_text_claim_coverage(bullets, claim_ledger, allowed_fact_ids)
    actual = text_claim_coverage if isinstance(text_claim_coverage, dict) else {}
    if actual.get("sentences") != expected.get("sentences"):
        return False, "text_claim_coverage.sentences mismatch vs structural rebuild"
    if actual.get("overall_pass") != expected.get("overall_pass"):
        return (
            False,
            f"overall_pass mismatch observed={actual.get('overall_pass')} expected={expected.get('overall_pass')}",
        )
    return True, None


__all__ = [
    "_all_source_fact_ids",
    "_norm_claim_ws",
    "_unify_root_from_source_fact_ids",
    "build_unify_bullets_text_claim_coverage",
    "check_unify_bullets_text_claim_coverage_integrity",
]
