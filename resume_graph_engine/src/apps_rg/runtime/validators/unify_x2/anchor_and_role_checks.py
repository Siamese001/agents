"""Mechanism density, metric anchor, and role-episode contract helpers for Unify bullets."""
from __future__ import annotations

from typing import Any

from apps_rg.runtime.validators.unify_x2.constants import (
    UNIFY_MECHANISM_STACK_TERMS,
    UNIFY_METRIC_ANCHOR_RULES,
)


def _combined_bullet_text(bullets: list[dict[str, Any]]) -> str:
    return "\n".join(str(b.get("bullet_text", "")) for b in bullets)


def _mechanism_term_hits_in_text(text: str) -> list[str]:
    tl = text.lower()
    hits: list[str] = []
    for term in UNIFY_MECHANISM_STACK_TERMS:
        if term in tl:
            hits.append(term)
    return hits


def _mechanism_dense_bullet_ids(
    bullets: list[dict[str, Any]],
    *,
    min_hits: int = 3,
) -> list[str]:
    dense: list[str] = []
    for b in bullets:
        bid = str(b.get("bullet_id") or "")
        hits = _mechanism_term_hits_in_text(str(b.get("bullet_text") or ""))
        if len(hits) >= min_hits:
            dense.append(bid or hits[0])
    return dense


def _unify_metric_anchors_on_assigned_bullets(
    bullets: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    by_id = {str(b.get("bullet_id")): b for b in bullets if b.get("bullet_id")}
    failures: list[str] = []
    for needles, root in UNIFY_METRIC_ANCHOR_RULES:
        bullet = by_id.get(root)
        if bullet is None:
            failures.append(f"missing_bullet:{root}")
            continue
        tl = str(bullet.get("bullet_text") or "").lower()
        if root == "bul_unify_006" and needles[0] in ("8", "28"):
            if not ("8" in tl and "28" in tl):
                failures.append("bul_unify_006_missing_8_to_28_scale")
            continue
        if not any(n.lower() in tl for n in needles):
            failures.append(f"{root}_missing_{needles[0]}")
    return (not failures, failures)


def _role_episode_metric_contract_active(meta: dict[str, Any] | None) -> bool:
    return bool(
        isinstance(meta, dict)
        and meta.get("role_episode_bundle_consumption")
        and meta.get("unify_role_episode_section_packet")
    )


__all__ = [
    "_combined_bullet_text",
    "_mechanism_dense_bullet_ids",
    "_mechanism_term_hits_in_text",
    "_role_episode_metric_contract_active",
    "_unify_metric_anchors_on_assigned_bullets",
]
