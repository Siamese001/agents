"""P2-W1 / P2-W1A competencies graph-skills proof pool — augmented_skills_graph only.

Product proof authority for competencies is **only** augmented_skills_graph (P2-W1A).
``broad_skills_ledger`` is deprecated and unreachable from ``resolve_section_proof_pool``.
No silent fallback. Graph authority failure fails closed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.augmented_skills_graph import (
    SOURCE_AUTHORITY_AUGMENTED_SKILLS_GRAPH,
    assert_skills_not_broad_ledger_authority,
    default_augmented_skills_graph_path,
    load_augmented_skills_graph,
)
from apps_rg.fact_inventory.candidate_fact_ledger import (
    default_ledger_path,
    load_master_candidate_fact_ledger,
)
from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    HYBRID_JD_FIXTURE,
    ROOT,
    REPORTS_DIR,
    build_track_weighted_expansion,
    infer_projection_role_family_key,
)
from apps_rg.runtime.proof_pool_resolver import PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH

P1_W4_CLOSEOUT_RECEIPT_REF = "docs/reports/apps_rg/career_track_p1_w4_closeout_receipt.json"
P1_W5_RECEIPT_REF = "docs/reports/apps_rg/career_track_p1_w5_track_balanced_sections_receipt.json"
P2_W1_RECEIPT_REF = "docs/reports/apps_rg/competencies_graph_proof_pool_p2_w1_receipt.json"
P2_W1_RECEIPT_JSON = REPORTS_DIR / "competencies_graph_proof_pool_p2_w1_receipt.json"
P2_W1_RECEIPT_MD = REPORTS_DIR / "competencies_graph_proof_pool_p2_w1.md"
P2_W1A_RECEIPT_JSON = REPORTS_DIR / "competencies_graph_proof_pool_p2_w1a_default_graph_authority_receipt.json"
P2_W1A_RECEIPT_MD = REPORTS_DIR / "competencies_graph_proof_pool_p2_w1a_default_graph_authority.md"

C03_STATUS_COMPETENCIES_GRAPH_PROOF = "NOT_CLAIMED_FOR_P2_W1A"  # superseded when bind_c03 receipt reports BOUND
C03_STATUS_P2_W1 = C03_STATUS_COMPETENCIES_GRAPH_PROOF  # backward compat for tests

DEPRECATED_LEDGER_CODE_PATHS: tuple[str, ...] = (
    "apps_rg/runtime/proof_pool_resolver.py::_build_competencies_ledger_plan",
    "apps_rg/runtime/proof_pool_resolver.py::_allocate_from_ledger (removed — graph-only product)",
    "selection_method=broad_skills_ledger_competencies",
)


class CompetenciesGraphProofPoolError(ValueError):
    """Competencies graph proof pool contract violation."""


_TEST_ONLY_RECEIPT_MODE = "TEST_ONLY_NONCANONICAL_OUTPUT"
_CANONICAL_RECEIPT_MODE = "CANONICAL"


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt_ref(*, root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return str(resolved_path)


def _load_upstream_receipt(
    *,
    root: Path,
    logical_ref: str,
    override_path: Path | None,
    expected_schema: str,
    test_only_output: bool,
) -> tuple[Path, str, str]:
    if override_path is not None and not test_only_output:
        raise CompetenciesGraphProofPoolError(
            f"noncanonical upstream override is allowed only for TEST_ONLY output: {logical_ref}"
        )
    path = Path(override_path) if override_path is not None else root / logical_ref
    if not path.is_file():
        raise CompetenciesGraphProofPoolError(f"missing required upstream receipt: {path}")
    if override_path is None:
        try:
            path.resolve(strict=True).relative_to(root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise CompetenciesGraphProofPoolError(
                f"canonical upstream receipt escapes repository authority: {logical_ref}"
            ) from exc
        cursor = root
        for part in Path(logical_ref).parts:
            cursor /= part
            if cursor.is_symlink():
                raise CompetenciesGraphProofPoolError(
                    f"canonical upstream receipt path must not traverse a symlink: {logical_ref}"
                )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompetenciesGraphProofPoolError(
            f"invalid required upstream receipt {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise CompetenciesGraphProofPoolError(
            f"invalid required upstream receipt {path}: root must be a JSON object"
        )
    if str(payload.get("schema") or "") != expected_schema:
        raise CompetenciesGraphProofPoolError(
            f"invalid required upstream receipt {path}: schema must be {expected_schema}"
        )
    expected_mode = _TEST_ONLY_RECEIPT_MODE if override_path is not None else _CANONICAL_RECEIPT_MODE
    expected_eligibility = override_path is None
    if (
        payload.get("receipt_mode") != expected_mode
        or payload.get("certification_eligible") is not expected_eligibility
    ):
        raise CompetenciesGraphProofPoolError(
            f"upstream receipt must be marked {expected_mode} and "
            f"certification_eligible={str(expected_eligibility).lower()}: {path}"
        )
    receipt_ref = logical_ref if override_path is None else _receipt_ref(root=root, path=path)
    return path, receipt_ref, _raw_sha256(path)


def _resolve_receipt_path(*, root: Path, receipt_ref: str) -> Path:
    path = Path(receipt_ref)
    return path if path.is_absolute() else root / path


def _validate_receipt_digest(
    *,
    root: Path,
    receipt: dict[str, Any],
    ref_field: str,
    digest_field: str,
    expected_schema: str,
    required_mode: str | None,
    errors: list[str],
) -> None:
    ref = str(receipt.get(ref_field) or "").strip()
    digest = str(receipt.get(digest_field) or "").strip()
    if not ref:
        errors.append(f"missing {ref_field}")
        return
    path = _resolve_receipt_path(root=root, receipt_ref=ref)
    if not path.is_file():
        errors.append(f"missing receipt bound by {ref_field}: {ref}")
        return
    actual = _raw_sha256(path)
    if digest != actual:
        errors.append(f"{digest_field} mismatch for {ref}: expected {actual}, got {digest or '<blank>'}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid receipt bound by {ref_field}: {exc}")
        return
    if not isinstance(payload, dict) or str(payload.get("schema") or "") != expected_schema:
        errors.append(f"receipt bound by {ref_field} must use schema {expected_schema}")
        return
    bound_mode = str(payload.get("receipt_mode") or "")
    bound_eligibility = payload.get("certification_eligible")
    if bound_mode not in (_CANONICAL_RECEIPT_MODE, _TEST_ONLY_RECEIPT_MODE):
        errors.append(f"receipt bound by {ref_field} has unexpected receipt_mode {bound_mode!r}")
    elif bound_eligibility is not (bound_mode == _CANONICAL_RECEIPT_MODE):
        errors.append(f"receipt bound by {ref_field} has inconsistent certification_eligible")
    if required_mode is not None and bound_mode != required_mode:
        errors.append(f"receipt bound by {ref_field} must use receipt_mode {required_mode}")


def competencies_graph_skills_proof_pool_requested(
    explicit: bool | None = None,
) -> bool:
    """Product path always uses graph-skills authority (P2-W1A). Explicit False is rejected upstream."""
    if explicit is False:
        return False
    return True


def _fact_claim_index(ledger: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in ledger.get("candidate_facts") or []:
        if not isinstance(row, dict):
            continue
        fid = str(row.get("candidate_fact_id") or "").strip()
        if fid:
            out[fid] = str(row.get("claim_text") or "").strip()
    return out


def _skill_rows_by_id(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in graph.get("skill_rows") or []:
        if isinstance(row, dict):
            sid = str(row.get("skill_id") or "")
            if sid:
                out[sid] = row
    return out


def enrich_selected_skill_rows(
    graph: dict[str, Any],
    track_expansion: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach fact_id_links and labels from graph SSOT to expansion skill picks."""
    rows_by_id = _skill_rows_by_id(graph)
    enriched: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sk in track_expansion.get("selected_skills") or []:
        sid = str(sk.get("skill_id") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        row = rows_by_id.get(sid) or {}
        links = [str(x) for x in (row.get("fact_id_links") or []) if str(x).strip()]
        hop = sk.get("graph_hop_path") or []
        phrases = row.get("allowed_phrases") or []
        label = str(phrases[0]).strip() if phrases else sid
        enriched.append(
            {
                "skill_id": sid,
                "label": label,
                "career_track": str(sk.get("career_track") or ""),
                "pillar": str(sk.get("pillar") or row.get("pillar") or ""),
                "fact_id_links": links,
                "graph_hop_path": hop,
                "graph_support_ref": SOURCE_AUTHORITY_AUGMENTED_SKILLS_GRAPH,
            }
        )
    return enriched


def build_competencies_graph_skills_proof_payload(
    *,
    repo_root: Path | None = None,
    jd_text: str = HYBRID_JD_FIXTURE,
    target_role: str = "SVP Engineering Agentic AI",
    briefing_text: str = "",
) -> dict[str, Any]:
    """Build graph-skills proof pool for competencies (no C0.3 BOUND until P2-W2)."""
    root = repo_root or ROOT
    graph = load_augmented_skills_graph(repo_root=root)
    graph_path = default_augmented_skills_graph_path(root)
    graph_ref = (
        str(graph_path.relative_to(root)) if graph_path.is_relative_to(root) else str(graph_path)
    )
    ledger_path = default_ledger_path(root)
    ledger = load_master_candidate_fact_ledger(repo_root=root, path=ledger_path)
    claims = _fact_claim_index(ledger)

    from apps_rg.fact_inventory.candidate_fact_ledger import load_master_role_family_taxonomy

    taxonomy = load_master_role_family_taxonomy(repo_root=root)
    role_key = infer_projection_role_family_key(
        target_role=target_role,
        jd_text=jd_text,
        taxonomy=taxonomy,
    )
    track_expansion = build_track_weighted_expansion(
        graph=graph,
        role_family_key=role_key,
        jd_text=jd_text,
        briefing_text=briefing_text,
        enforce_hybrid_contract=True,
        bind_c03=True,
        repo_root=root,
    )
    skill_rows = enrich_selected_skill_rows(graph, track_expansion)

    facts_by_id: dict[str, dict[str, Any]] = {}
    for fe in track_expansion.get("selected_facts") or []:
        fid = str(fe.get("fact_id") or "").strip()
        if not fid or fid in facts_by_id:
            continue
        claim = claims.get(fid) or claims.get(fid.split("_metric_")[0], "")
        if not claim:
            continue
        facts_by_id[fid] = {
            "fact_id": fid,
            "candidate_fact_id": fid,
            "claim_text": claim,
            "career_track": str(fe.get("career_track") or ""),
            "skill_id": str(fe.get("skill_id") or ""),
            "graph_hop_path": fe.get("graph_hop_path") or [],
        }

    facts = list(facts_by_id.values())
    if not facts:
        raise CompetenciesGraphProofPoolError("graph expansion produced no ledger-backed facts")

    payload = {
        "schema": "competencies_graph_skills_proof_pool_v1",
        "plan_id": "graph-skills-hardening-f3a8c1",
        "wave": "P2-W1A",
        "section_id": "competencies",
        "proof_pool_type": PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH,
        "proof_source": PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH,
        "graph_source": graph_ref,
        "default_proof_pool_type": PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH,
        "competencies_product_authority": PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH,
        "selection_method": "augmented_skills_graph_track_weighted_competencies",
        "source_authority": SOURCE_AUTHORITY_AUGMENTED_SKILLS_GRAPH,
        "broad_skills_ledger_used_as_authority": False,
        "broad_skills_ledger_default": False,
        "broad_skills_ledger_fallback": False,
        "broad_skills_ledger_compatibility_authority": False,
        "silent_fallback_possible": False,
        "fail_closed_if_graph_unavailable": True,
        "deprecated_ledger_code_paths_remaining": list(DEPRECATED_LEDGER_CODE_PATHS),
        "deprecated_ledger_code_reachable_from_product_path": False,
        "selected_tracks": list(track_expansion.get("tracks_with_facts") or []),
        "selected_skill_count_by_track": dict(
            track_expansion.get("selected_skill_count_by_track") or {}
        ),
        "selected_fact_count_by_track": dict(
            track_expansion.get("selected_fact_count_by_track") or {}
        ),
        "selected_skill_rows": skill_rows,
        "selected_facts": facts,
        "selected_skill_rows_sample": skill_rows[:5],
        "graph_hop_paths_sample": [s.get("graph_hop_path") for s in skill_rows[:5]],
        "track_weighted_expansion_ref": "apps_rg/fact_inventory/track_weighted_graph_expansion.py",
        "c03_graph_bound_status": (
            str(track_expansion.get("c03_graph_bound_status") or C03_STATUS_COMPETENCIES_GRAPH_PROOF)
            if int(track_expansion.get("c03_graph_hop_paths_count") or 0) > 0
            and str(track_expansion.get("c03_graph_bound_status") or "") == "BOUND"
            else C03_STATUS_COMPETENCIES_GRAPH_PROOF
        ),
        "c03_graph_hop_paths_count": track_expansion.get("c03_graph_hop_paths_count", 0),
        "non_graph_evidence_items_count": 0,
        "p1_w4_closeout_receipt_ref": P1_W4_CLOSEOUT_RECEIPT_REF,
        "p1_w5_projection_receipt_ref": P1_W5_RECEIPT_REF,
        "track_expansion": track_expansion,
        "selected_fact_plan": {
            "section_id": "competencies",
            "selection_method": "augmented_skills_graph_track_weighted_competencies",
            "facts": facts,
            "required_fact_ids": [f["fact_id"] for f in facts],
        },
    }
    validate_competencies_graph_skills_proof_payload(payload)
    return payload


def validate_competencies_graph_skills_proof_payload(payload: dict[str, Any]) -> None:
    errors: list[str] = []
    if str(payload.get("proof_pool_type") or "") != PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH:
        errors.append(f"proof_pool_type must be augmented_skills_graph; got {payload.get('proof_pool_type')!r}")
    if str(payload.get("section_id") or "") != "competencies":
        errors.append("section_id must be competencies")
    if not str(payload.get("graph_source") or "").strip():
        errors.append("graph_source required")
    if payload.get("broad_skills_ledger_used_as_authority") is True:
        errors.append("broad_skills_ledger_used_as_authority must be false")
    if payload.get("broad_skills_ledger_default") is True:
        errors.append("broad_skills_ledger_default must be false")
    if payload.get("broad_skills_ledger_fallback") is True:
        errors.append("broad_skills_ledger_fallback must be false")
    if payload.get("silent_fallback_possible") is True:
        errors.append("silent_fallback_possible must be false")
    if payload.get("deprecated_ledger_code_reachable_from_product_path") is True:
        errors.append("deprecated_ledger_code_reachable_from_product_path must be false")
    c03 = str(payload.get("c03_graph_bound_status") or "")
    hop_count = int(payload.get("c03_graph_hop_paths_count") or 0)
    non_graph = int(payload.get("non_graph_evidence_items_count") or 0)
    if c03 == "BOUND":
        if hop_count <= 0 or non_graph != 0:
            errors.append(
                f"BOUND requires c03_graph_hop_paths_count>0 and non_graph_evidence_items_count=0; "
                f"got hops={hop_count} non_graph={non_graph}"
            )
    elif c03 not in (C03_STATUS_COMPETENCIES_GRAPH_PROOF, "NOT_BOUND", "NOT_CLAIMED_FOR_P2_W1"):
        errors.append(f"unexpected c03_graph_bound_status: {c03!r}")
    for sk in payload.get("selected_skill_rows") or []:
        if not sk.get("fact_id_links"):
            errors.append(f"{sk.get('skill_id')} missing fact_id_links")
        hop = sk.get("graph_hop_path")
        ref = sk.get("graph_support_ref")
        if not hop and not ref:
            errors.append(f"{sk.get('skill_id')} missing graph_hop_path/graph_support_ref")
    try:
        assert_skills_not_broad_ledger_authority(payload)
    except ValueError as exc:
        errors.append(str(exc))
    if errors:
        raise CompetenciesGraphProofPoolError("; ".join(errors))


def validate_p2_w1a_default_graph_authority_receipt(
    receipt: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> None:
    """Fail-closed validator for P2-W1A default graph authority receipt."""
    root = repo_root or ROOT
    errors: list[str] = []
    required = (
        "receipt_mode",
        "certification_eligible",
        "default_proof_pool_type",
        "competencies_product_authority",
        "broad_skills_ledger_default",
        "broad_skills_ledger_fallback",
        "broad_skills_ledger_compatibility_authority",
        "broad_skills_ledger_used_as_authority",
        "silent_fallback_possible",
        "fail_closed_if_graph_unavailable",
        "deprecated_ledger_code_paths_remaining",
        "deprecated_ledger_code_reachable_from_product_path",
        "p2_w1_proof_pool_receipt_ref",
        "p2_w1_proof_pool_receipt_raw_sha256",
        "p1_w4_closeout_receipt_ref",
        "p1_w4_closeout_receipt_raw_sha256",
        "p1_w5_projection_receipt_ref",
        "p1_w5_projection_receipt_raw_sha256",
    )
    for key in required:
        if key not in receipt:
            errors.append(f"missing {key}")
    if str(receipt.get("default_proof_pool_type") or "") != PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH:
        errors.append("default_proof_pool_type must be augmented_skills_graph")
    if str(receipt.get("competencies_product_authority") or "") != PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH:
        errors.append("competencies_product_authority must be augmented_skills_graph")
    for flag in (
        "broad_skills_ledger_default",
        "broad_skills_ledger_fallback",
        "broad_skills_ledger_compatibility_authority",
        "broad_skills_ledger_used_as_authority",
        "silent_fallback_possible",
        "deprecated_ledger_code_reachable_from_product_path",
    ):
        if receipt.get(flag) is not False:
            errors.append(f"{flag} must be false")
    if receipt.get("fail_closed_if_graph_unavailable") is not True:
        errors.append("fail_closed_if_graph_unavailable must be true")
    receipt_mode = str(receipt.get("receipt_mode") or "")
    certification_eligible = receipt.get("certification_eligible")
    if receipt_mode not in (_CANONICAL_RECEIPT_MODE, _TEST_ONLY_RECEIPT_MODE):
        errors.append(f"unexpected receipt_mode: {receipt_mode!r}")
    if receipt_mode == _TEST_ONLY_RECEIPT_MODE and certification_eligible is not False:
        errors.append("TEST_ONLY receipt must set certification_eligible=false")
    if receipt_mode == _CANONICAL_RECEIPT_MODE and certification_eligible is not True:
        errors.append("CANONICAL receipt must set certification_eligible=true")
    if receipt_mode == _CANONICAL_RECEIPT_MODE:
        canonical_refs = {
            "p2_w1_proof_pool_receipt_ref": P2_W1_RECEIPT_REF,
            "p1_w4_closeout_receipt_ref": P1_W4_CLOSEOUT_RECEIPT_REF,
            "p1_w5_projection_receipt_ref": P1_W5_RECEIPT_REF,
        }
        for field, expected_ref in canonical_refs.items():
            if receipt.get(field) != expected_ref:
                errors.append(f"canonical {field} must be {expected_ref}")
    for ref_field, digest_field, expected_schema, required_mode in (
        (
            "p2_w1_proof_pool_receipt_ref",
            "p2_w1_proof_pool_receipt_raw_sha256",
            "competencies_graph_proof_pool_p2_w1_receipt_v1",
            receipt_mode,
        ),
        (
            "p1_w4_closeout_receipt_ref",
            "p1_w4_closeout_receipt_raw_sha256",
            "career_track_p1_w4_closeout_receipt_v1",
            _CANONICAL_RECEIPT_MODE if receipt_mode == _CANONICAL_RECEIPT_MODE else None,
        ),
        (
            "p1_w5_projection_receipt_ref",
            "p1_w5_projection_receipt_raw_sha256",
            "career_track_p1_w5_track_balanced_sections_receipt_v1",
            _CANONICAL_RECEIPT_MODE if receipt_mode == _CANONICAL_RECEIPT_MODE else None,
        ),
    ):
        _validate_receipt_digest(
            root=root,
            receipt=receipt,
            ref_field=ref_field,
            digest_field=digest_field,
            expected_schema=expected_schema,
            required_mode=required_mode,
            errors=errors,
        )
    if errors:
        raise CompetenciesGraphProofPoolError("; ".join(errors))


def write_p2_w1_competencies_graph_proof_pool_receipt(
    *,
    repo_root: Path | None = None,
    out_dir: Path | None = None,
    p1_w4_closeout_path: Path | None = None,
    p1_w5_projection_path: Path | None = None,
) -> dict[str, Any]:
    """Emit the P2-W1 receipts.

    ``out_dir`` (RCA 2026-06-10, plan apps-rg-aig-remaining-lanes-closeout-d4e1f7): operator/CLI
    emission defaults to the tracked ``docs/reports/apps_rg`` SSOT, but TEST runs must pass an
    untracked dir (pytest ``tmp_path``) — receipt regeneration as a pytest side effect kept the
    tree chronically dirty and broke a mid-session ``git stash pop``.
    """
    root = repo_root or ROOT
    out_base = Path(out_dir) if out_dir is not None else REPORTS_DIR
    test_only_output = out_dir is not None
    receipt_mode = _TEST_ONLY_RECEIPT_MODE if test_only_output else _CANONICAL_RECEIPT_MODE
    _, p1_w4_ref, p1_w4_digest = _load_upstream_receipt(
        root=root,
        logical_ref=P1_W4_CLOSEOUT_RECEIPT_REF,
        override_path=p1_w4_closeout_path,
        expected_schema="career_track_p1_w4_closeout_receipt_v1",
        test_only_output=test_only_output,
    )
    _, p1_w5_ref, p1_w5_digest = _load_upstream_receipt(
        root=root,
        logical_ref=P1_W5_RECEIPT_REF,
        override_path=p1_w5_projection_path,
        expected_schema="career_track_p1_w5_track_balanced_sections_receipt_v1",
        test_only_output=test_only_output,
    )
    receipt_json_path = out_base / P2_W1_RECEIPT_JSON.name
    receipt_md_path = out_base / P2_W1_RECEIPT_MD.name
    payload = build_competencies_graph_skills_proof_payload(repo_root=root)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    receipt = {
        "schema": "competencies_graph_proof_pool_p2_w1_receipt_v1",
        "generated_at": ts,
        "receipt_mode": receipt_mode,
        "certification_eligible": not test_only_output,
        "proof_pool_type": payload["proof_pool_type"],
        "section_id": payload["section_id"],
        "graph_source": payload["graph_source"],
        "default_proof_pool_type": PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH,
        "competencies_product_authority": PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH,
        "selected_tracks": payload["selected_tracks"],
        "selected_skill_count_by_track": payload["selected_skill_count_by_track"],
        "selected_fact_count_by_track": payload["selected_fact_count_by_track"],
        "selected_skill_rows_sample": payload["selected_skill_rows_sample"],
        "graph_hop_paths_sample": payload["graph_hop_paths_sample"],
        "every_skill_has_fact_id_links": all(
            bool(s.get("fact_id_links")) for s in (payload.get("selected_skill_rows") or [])
        ),
        "every_skill_has_graph_support": all(
            bool(s.get("graph_hop_path")) or bool(s.get("graph_support_ref"))
            for s in (payload.get("selected_skill_rows") or [])
        ),
        "broad_skills_ledger_used_as_authority": False,
        "broad_skills_ledger_default": False,
        "c03_graph_bound_status": payload["c03_graph_bound_status"],
        "p1_w4_closeout_receipt_ref": p1_w4_ref,
        "p1_w4_closeout_receipt_raw_sha256": p1_w4_digest,
        "p1_w5_projection_receipt_ref": p1_w5_ref,
        "p1_w5_projection_receipt_raw_sha256": p1_w5_digest,
    }
    validate_competencies_graph_skills_proof_payload({**payload, **receipt})

    out_base.mkdir(parents=True, exist_ok=True)
    receipt_json_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    md = [
        "# P2-W1 — Competencies graph-skills proof pool",
        "",
        f"**Generated:** {ts}",
        f"**Receipt mode:** {receipt_mode}",
        f"**Certification eligible:** {not test_only_output}",
        "",
        f"- proof_pool_type: **{receipt['proof_pool_type']}** (default product authority P2-W1A)",
        f"- graph_source: `{receipt['graph_source']}`",
        f"- broad_skills_ledger_used_as_authority: **{receipt['broad_skills_ledger_used_as_authority']}**",
        f"- c03_graph_bound_status: **{receipt['c03_graph_bound_status']}**",
        "",
        "## Authority (P2-W1A)",
        "",
        "Default `resolve_section_proof_pool(section=competencies)` uses augmented_skills_graph only.",
        "No broad_skills_ledger product authority path. Fail closed if graph unavailable.",
        "",
        "## Part 1 refs",
        "",
        f"- `{p1_w4_ref}` (raw sha256 `{p1_w4_digest}`)",
        f"- `{p1_w5_ref}` (raw sha256 `{p1_w5_digest}`)",
        "",
    ]
    for track, n in (receipt.get("selected_skill_count_by_track") or {}).items():
        md.append(f"- skills `{track}`: {n}")
    receipt_md_path.write_text("\n".join(md), encoding="utf-8")
    return {"receipt_json": str(receipt_json_path), "receipt_md": str(receipt_md_path), "payload": payload, "receipt": receipt}


def write_p2_w1a_default_graph_authority_receipt(
    *,
    repo_root: Path | None = None,
    out_dir: Path | None = None,
    p1_w4_closeout_path: Path | None = None,
    p1_w5_projection_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or ROOT
    out_base = Path(out_dir) if out_dir is not None else REPORTS_DIR
    test_only_output = out_dir is not None
    receipt_mode = _TEST_ONLY_RECEIPT_MODE if test_only_output else _CANONICAL_RECEIPT_MODE
    receipt_json_path = out_base / P2_W1A_RECEIPT_JSON.name
    receipt_md_path = out_base / P2_W1A_RECEIPT_MD.name
    w1 = write_p2_w1_competencies_graph_proof_pool_receipt(
        repo_root=root,
        out_dir=out_dir,
        p1_w4_closeout_path=p1_w4_closeout_path,
        p1_w5_projection_path=p1_w5_projection_path,
    )
    payload = w1["payload"]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    p2_w1_receipt_ref = (
        str(Path(w1["receipt_json"]).resolve())
        if out_dir is not None
        else P2_W1_RECEIPT_REF
    )
    receipt = {
        "schema": "competencies_graph_proof_pool_p2_w1a_default_graph_authority_receipt_v1",
        "generated_at": ts,
        "receipt_mode": receipt_mode,
        "certification_eligible": not test_only_output,
        "plan_id": "graph-skills-hardening-f3a8c1",
        "wave": "P2-W1A",
        "default_proof_pool_type": PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH,
        "competencies_product_authority": PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH,
        "broad_skills_ledger_default": False,
        "broad_skills_ledger_fallback": False,
        "broad_skills_ledger_compatibility_authority": False,
        "broad_skills_ledger_used_as_authority": False,
        "silent_fallback_possible": False,
        "fail_closed_if_graph_unavailable": True,
        "deprecated_ledger_code_paths_remaining": list(DEPRECATED_LEDGER_CODE_PATHS),
        "deprecated_ledger_code_reachable_from_product_path": False,
        "proof_pool_type": payload["proof_pool_type"],
        "graph_source": payload["graph_source"],
        "selected_tracks": payload["selected_tracks"],
        "selected_skill_count_by_track": payload["selected_skill_count_by_track"],
        "selected_fact_count_by_track": payload["selected_fact_count_by_track"],
        "every_skill_has_fact_id_links": w1["receipt"]["every_skill_has_fact_id_links"],
        "every_skill_has_graph_support": w1["receipt"]["every_skill_has_graph_support"],
        "c03_graph_bound_status": payload.get("c03_graph_bound_status", C03_STATUS_COMPETENCIES_GRAPH_PROOF),
        "c03_graph_hop_paths_count": payload.get("c03_graph_hop_paths_count", 0),
        "non_graph_evidence_items_count": payload.get("non_graph_evidence_items_count", 0),
        "p2_w1_proof_pool_receipt_ref": p2_w1_receipt_ref,
        "p2_w1_proof_pool_receipt_raw_sha256": _raw_sha256(Path(w1["receipt_json"])),
        "p1_w4_closeout_receipt_ref": w1["receipt"]["p1_w4_closeout_receipt_ref"],
        "p1_w4_closeout_receipt_raw_sha256": w1["receipt"][
            "p1_w4_closeout_receipt_raw_sha256"
        ],
        "p1_w5_projection_receipt_ref": w1["receipt"]["p1_w5_projection_receipt_ref"],
        "p1_w5_projection_receipt_raw_sha256": w1["receipt"][
            "p1_w5_projection_receipt_raw_sha256"
        ],
    }
    validate_p2_w1a_default_graph_authority_receipt(receipt, repo_root=root)
    validate_competencies_graph_skills_proof_payload(payload)

    out_base.mkdir(parents=True, exist_ok=True)
    receipt_json_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    md = [
        "# P2-W1A — Competencies default graph authority (ledger removed)",
        "",
        f"**Generated:** {ts}",
        f"**Receipt mode:** {receipt_mode}",
        f"**Certification eligible:** {not test_only_output}",
        "",
        "GAP-P2-1 (broad_skills_ledger as competencies product authority) closed by P2-W1A.",
        "",
        f"- default_proof_pool_type: **{receipt['default_proof_pool_type']}**",
        f"- broad_skills_ledger_used_as_authority: **{receipt['broad_skills_ledger_used_as_authority']}**",
        f"- silent_fallback_possible: **{receipt['silent_fallback_possible']}**",
        f"- fail_closed_if_graph_unavailable: **{receipt['fail_closed_if_graph_unavailable']}**",
        f"- deprecated_ledger_code_reachable_from_product_path: **{receipt['deprecated_ledger_code_reachable_from_product_path']}**",
        f"- p2_w1_proof_pool_receipt_ref: `{receipt['p2_w1_proof_pool_receipt_ref']}`",
        f"- p2_w1_proof_pool_receipt_raw_sha256: `{receipt['p2_w1_proof_pool_receipt_raw_sha256']}`",
        f"- p1_w4_closeout_receipt_ref: `{receipt['p1_w4_closeout_receipt_ref']}`",
        f"- p1_w4_closeout_receipt_raw_sha256: `{receipt['p1_w4_closeout_receipt_raw_sha256']}`",
        f"- p1_w5_projection_receipt_ref: `{receipt['p1_w5_projection_receipt_ref']}`",
        f"- p1_w5_projection_receipt_raw_sha256: `{receipt['p1_w5_projection_receipt_raw_sha256']}`",
        "",
    ]
    receipt_md_path.write_text("\n".join(md), encoding="utf-8")
    return {
        "receipt_json": str(receipt_json_path),
        "receipt_md": str(receipt_md_path),
        "receipt": receipt,
        "payload": payload,
    }


def main() -> None:
    out = write_p2_w1a_default_graph_authority_receipt()
    print(
        json.dumps(
            {
                "receipt": out["receipt_json"],
                "default_proof_pool_type": out["receipt"]["default_proof_pool_type"],
                "competencies_product_authority": out["receipt"]["competencies_product_authority"],
                "broad_skills_ledger_used_as_authority": out["receipt"]["broad_skills_ledger_used_as_authority"],
                "c03_graph_bound_status": out["receipt"]["c03_graph_bound_status"],
            },
            indent=2,
        )
    )
