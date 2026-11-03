"""Retrieval caching, top-k capping, and frozen-allocation helpers for C0 runtime."""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import threading
from typing import Any, Mapping, Sequence

_COLLECTION_SCAN_LOCK = threading.Lock()
_COLLECTION_SCAN_CACHE: dict[tuple[str, int], dict[str, Any]] = {}
_YAML_PROFILE_LOCK = threading.Lock()
_YAML_PROFILE_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}
_VERIFIED_COLLECTION_LOCK = threading.Lock()
_VERIFIED_COLLECTION_CACHE: dict[tuple[str, str, int], Any] = {}
_QUERY_VECTOR_LOCK = threading.Lock()
_QUERY_VECTOR_CACHE: dict[tuple[str, str], list[float]] = {}
_QUERY_VECTOR_INFLIGHT: dict[tuple[str, str], threading.Event] = {}
_MAX_QUERY_VECTOR_CACHE = 512

_SECTION_EMBEDDING_TOP_K_CAPS: dict[str, int] = {
    "executive_summary": 96,
    "headline": 96,
    "competencies": 160,
}


def resolve_effective_section_id_filter(
    section_id_filter: str | None,
    section_profile: Any,
) -> str | None:
    if not section_id_filter:
        return None
    resolved_sid = section_profile.resolve_section_id(section_id_filter)
    known_sids = {str(s.get("section_id") or "") for s in section_profile.get_sections()}
    if section_id_filter in known_sids or resolved_sid in known_sids:
        return section_id_filter
    return None


def get_or_scan_fact_vectors_collection(
    *,
    chroma_path: str,
    collection: Any,
    count: int,
    limit: int,
    metadata_counter_fn: Any,
) -> dict[str, Any]:
    cache_key = (str(Path(chroma_path).resolve()), count)
    with _COLLECTION_SCAN_LOCK:
        cached_scan = _COLLECTION_SCAN_CACHE.get(cache_key)
        if cached_scan is not None:
            return cached_scan
        metadata = getattr(collection, "metadata", None)
        collection_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        rows = collection.get(limit=limit, include=["metadatas"]) if limit else {"metadatas": []}
        metas = [m for m in (rows.get("metadatas") or []) if isinstance(m, dict)]
        source_id_counts: Counter[str] = Counter()
        for meta in metas:
            sid = str(meta.get("source_document_id") or meta.get("candidate_fact_id") or "").strip()
            if sid:
                source_id_counts[sid] += 1
        cached_scan = {
            "collection_metadata": collection_metadata,
            "metas": metas,
            "source_id_counts": dict(sorted(source_id_counts.items())),
            "model_counts": metadata_counter_fn(metas, "embedding_model_id", fallback_key="embedding_model"),
            "dim_counts": metadata_counter_fn(metas, "embedding_dim", fallback_key="embedding_dimension"),
            "source_class_counts": metadata_counter_fn(metas, "source_class"),
            "tier_counts": metadata_counter_fn(metas, "tier"),
        }
        _COLLECTION_SCAN_CACHE[cache_key] = cached_scan
        return cached_scan


def load_cached_yaml_profile(profile_path: Path) -> dict[str, Any]:
    resolved = profile_path.resolve()
    stat = resolved.stat()
    key = (str(resolved), int(stat.st_mtime_ns), int(stat.st_size))
    with _YAML_PROFILE_LOCK:
        cached = _YAML_PROFILE_CACHE.get(key)
        if cached is not None:
            return cached
    import yaml

    loaded = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    data = dict(loaded) if isinstance(loaded, dict) else {}
    with _YAML_PROFILE_LOCK:
        _YAML_PROFILE_CACHE[key] = data
    return data


def get_or_open_verified_collection(
    *,
    chroma_path: str,
    collection_name: str,
    ensure_client_fn: Any,
    open_collection_fn: Any,
    assert_parity_fn: Any,
) -> Any:
    resolved_dir = str(Path(chroma_path).resolve())
    client = ensure_client_fn(resolved_dir)
    key = (resolved_dir, str(collection_name), id(client))
    with _VERIFIED_COLLECTION_LOCK:
        cached = _VERIFIED_COLLECTION_CACHE.get(key)
        if cached is not None:
            return cached
        collection = open_collection_fn(client, collection_name)
        assert_parity_fn(collection)
        _VERIFIED_COLLECTION_CACHE[key] = collection
        return collection


def encode_queries_with_shared_cache(
    *,
    embedding_runtime: Any,
    queries: Sequence[str],
    batch_size_fn: Any,
    workload_id: str = "c02_section_queries",
) -> list[list[float]]:
    if not queries:
        return []
    runtime_key = str(getattr(embedding_runtime, "key", None) or id(embedding_runtime))
    results: list[list[float] | None] = [None] * len(queries)
    to_compute: dict[tuple[str, str], tuple[str, list[int], threading.Event]] = {}
    wait_events: list[tuple[int, tuple[str, str], threading.Event]] = []

    with _QUERY_VECTOR_LOCK:
        for idx, query in enumerate(queries):
            q_text = str(query)
            q_hash = hashlib.sha256(q_text.encode("utf-8")).hexdigest()
            ckey = (runtime_key, q_hash)
            cached = _QUERY_VECTOR_CACHE.get(ckey)
            if cached is not None:
                results[idx] = list(cached)
            elif ckey in to_compute:
                to_compute[ckey][1].append(idx)
            elif ckey in _QUERY_VECTOR_INFLIGHT:
                wait_events.append((idx, ckey, _QUERY_VECTOR_INFLIGHT[ckey]))
            else:
                ev = threading.Event()
                _QUERY_VECTOR_INFLIGHT[ckey] = ev
                to_compute[ckey] = (q_text, [idx], ev)

    if to_compute:
        ordered_keys = list(to_compute.keys())
        texts = [to_compute[k][0] for k in ordered_keys]
        try:
            bsize = batch_size_fn(workload_id, len(texts))
            computed_vecs = embedding_runtime.encode(texts, batch_size=bsize)
            if len(computed_vecs) != len(texts):
                raise RuntimeError("C0.2 section-query embedding cardinality changed")
            with _QUERY_VECTOR_LOCK:
                if len(_QUERY_VECTOR_CACHE) + len(computed_vecs) > _MAX_QUERY_VECTOR_CACHE:
                    _QUERY_VECTOR_CACHE.clear()
                for ckey, vec in zip(ordered_keys, computed_vecs, strict=True):
                    vec_copy = [float(x) for x in vec]
                    _QUERY_VECTOR_CACHE[ckey] = vec_copy
                    for slot_idx in to_compute[ckey][1]:
                        results[slot_idx] = list(vec_copy)
        finally:
            with _QUERY_VECTOR_LOCK:
                for ckey in ordered_keys:
                    ev = _QUERY_VECTOR_INFLIGHT.pop(ckey, None)
                    if ev is not None:
                        ev.set()

    for idx, ckey, ev in wait_events:
        ev.wait(timeout=30.0)
        with _QUERY_VECTOR_LOCK:
            cached = _QUERY_VECTOR_CACHE.get(ckey)
        if cached is not None:
            results[idx] = list(cached)
        else:
            q_text = str(queries[idx])
            bsize = batch_size_fn(workload_id, 1)
            vec = embedding_runtime.encode([q_text], batch_size=bsize)[0]
            results[idx] = [float(x) for x in vec]

    return [vec if vec is not None else [] for vec in results]


def c06_bindings_changed(
    initial_bindings: Sequence[Mapping[str, Any]],
    refined_c03: Mapping[str, Any],
    c06_receipt: Mapping[str, Any],
) -> bool:
    """Return True only when C0.6 attempted, passed, and changed C0.3 bindings."""
    if not (c06_receipt.get("attempted") and c06_receipt.get("pass")):
        return False
    refined_bindings = list(refined_c03.get("bindings") or [])
    return list(initial_bindings) != refined_bindings


def reset_c0_shared_retrieval_caches_for_tests() -> None:
    with _COLLECTION_SCAN_LOCK:
        _COLLECTION_SCAN_CACHE.clear()
    with _YAML_PROFILE_LOCK:
        _YAML_PROFILE_CACHE.clear()
    with _VERIFIED_COLLECTION_LOCK:
        _VERIFIED_COLLECTION_CACHE.clear()
    with _QUERY_VECTOR_LOCK:
        _QUERY_VECTOR_CACHE.clear()
        _QUERY_VECTOR_INFLIGHT.clear()


def resolve_section_embedding_top_k(authority_section_id: str, assertion_count: int) -> int:
    count = int(assertion_count)
    return min(count, _SECTION_EMBEDDING_TOP_K_CAPS.get(authority_section_id, count))


def compute_distinct_root_sections(
    slots: list[Any],
    eligible_by_slot: dict[str, list[dict[str, Any]]],
) -> set[str]:
    slot_counts_by_section = Counter(slot.section_id for slot in slots)
    distinct_root_sections: set[str] = set()
    for sec_id, sec_slot_count in slot_counts_by_section.items():
        if sec_id.endswith("_bullets"):
            distinct_root_sections.add(sec_id)
        elif sec_id in {"executive_summary", "headline"}:
            sec_roots = {
                str(r.get("root_id") or "")
                for s in slots
                if s.section_id == sec_id
                for r in eligible_by_slot.get(s.slot_id, ())
                if str(r.get("root_id") or "")
            }
            if len(sec_roots) >= sec_slot_count:
                distinct_root_sections.add(sec_id)
    return distinct_root_sections


def slot_priority_tier(slot: Any) -> int:
    if slot.section_id == "executive_summary":
        return 0
    if slot.section_id == "headline":
        return 1
    if slot.required_root_id:
        return 2
    if slot.section_id.endswith("_bullets"):
        return 3
    return 4


def compute_career_band_filter(
    *,
    section_id: str,
    sec_plan: dict[str, Any],
    grouped_section_buckets: dict[str, dict[str, list[dict[str, Any]]]],
) -> tuple[dict[str, float], dict[str, float], bool, set[str]]:
    employer_root_weights = {
        str(k): float(v) for k, v in dict(sec_plan.get("employer_root_weights") or {}).items()
    }
    employer_weights = {
        str(k): float(v)
        for k, v in dict(((sec_plan.get("graph_weight_profile") or {}).get("employer_weights")) or {}).items()
    }
    is_shared_top_section = section_id in {"executive_summary", "headline", "competencies"}
    primary_secondary_roots = {
        r_id
        for r_id, bkt in grouped_section_buckets.items()
        for r_row in bkt["root"]
        if r_row.get("authority_pass") is True
        and float(
            employer_root_weights.get(
                r_id,
                employer_weights.get(str(r_row.get("employer_lane") or ""), 1.0),
            )
        )
        >= 0.55
    }
    enforce_career_band = is_shared_top_section and len(primary_secondary_roots) >= 3
    return employer_root_weights, employer_weights, enforce_career_band, primary_secondary_roots


def compute_candidate_alignment_and_independence(
    *,
    root: dict[str, Any],
    skill: dict[str, Any],
    metric: dict[str, Any] | None,
    root_weight: float,
    citation_refs: list[str],
    skill_sources: list[str],
) -> tuple[float, float, float]:
    raw_proof = float(skill.get("proof_strength_raw") or 0.0)
    raw_align = (
        float(root.get("target_alignment_score") or 0.0)
        + float(skill.get("target_alignment_score") or 0.0)
        + float((metric or {}).get("target_alignment_score") or 0.0)
    ) / (3 if metric is not None else 2)
    proof_score = 1.0 if raw_proof >= 1.0 else raw_proof
    align_score = round(raw_align * root_weight, 6)
    indep_score = (
        1.0
        if citation_refs and skill_sources
        else round(min(len(set(citation_refs + skill_sources)), 4) / 4, 6)
    )
    return proof_score, align_score, indep_score


def build_targeting_provenance(
    *,
    target_role: str | None,
    jd_text: str | None,
    briefing_text: str | None,
) -> dict[str, str]:
    return {
        "target_role": str(target_role or "").strip(),
        "jd_sha256": hashlib.sha256(str(jd_text or "").encode("utf-8")).hexdigest() if jd_text else "",
        "briefing_sha256": hashlib.sha256(str(briefing_text or "").encode("utf-8")).hexdigest() if briefing_text else "",
    }


def build_frozen_competencies_proof_payload(
    selected_graph_plan: dict[str, Any],
    *,
    graph_ref: str,
) -> dict[str, Any]:
    return {
        "graph_source": graph_ref,
        "selection_method": str(
            selected_graph_plan.get("selection_method") or "frozen_whole_resume_fact_allocation"
        ),
        "selected_skill_rows": list(selected_graph_plan.get("selected_skills") or []),
        "selected_tracks": list(selected_graph_plan.get("selected_tracks") or []),
        "selected_skill_count_by_track": dict(
            selected_graph_plan.get("selected_skill_count_by_track") or {}
        ),
        "selected_fact_count_by_track": dict(
            selected_graph_plan.get("selected_fact_count_by_track") or {}
        ),
        "legacy_broad_skills_ledger_path": None,
        "track_expansion": {
            "c03_graph_bound_status": "BOUND",
            "c03_graph_hop_paths_count": len(
                selected_graph_plan.get("allocation_assignments")
                or selected_graph_plan.get("facts")
                or []
            ),
            "tracks_with_facts": list(selected_graph_plan.get("selected_tracks") or []),
        },
        "track_weighted_expansion_ref": str(selected_graph_plan.get("allocation_plan_ref") or ""),
        "graph_hop_paths_sample": list(
            (selected_graph_plan.get("allocation_assignments") or [])[:5]
        ),
    }


RECOVERY_SEALED_C0_MANIFEST_ENV = "APPS_RG_RECOVERY_SEALED_C0_MANIFEST"
RECOVERY_SEALED_C0_MANIFEST_FILENAME = "x3_recovery_sealed_c0_manifest.json"


def extract_c0_targeting_inputs(front_spine: Any, pool: Any) -> tuple[str, str]:
    target_role, jd_text = "", ""
    if front_spine is not None and getattr(front_spine, "validated_request", None) is not None:
        app = getattr(front_spine.validated_request, "app_payload", None) or {}
        if isinstance(app, dict):
            target_role = str(app.get("target_role") or app.get("target_title") or "")
            jd_text = str(app.get("job_description_text") or app.get("jd_text") or "")
            if not jd_text and app.get("job_description_ref"):
                try:
                    jp = Path(str(app["job_description_ref"]))
                    if jp.is_file():
                        jd_text = jp.read_text(encoding="utf-8")
                except (OSError, ValueError):
                    pass
    if pool is not None:
        meta = getattr(pool, "proof_pool_metadata", None) or {}
        target_role = target_role or str(meta.get("target_role") or "")
        jd_text = jd_text or str(meta.get("jd_text") or "")
        if not jd_text and meta.get("job_description_ref"):
            try:
                jp = Path(str(meta["job_description_ref"]))
                if jp.is_file():
                    jd_text = jp.read_text(encoding="utf-8")
            except (OSError, ValueError):
                pass
    return target_role, jd_text


def compute_c0_input_identity(
    *,
    section_id: str,
    target_role: str,
    jd_text: str,
    pool: Any,
) -> dict[str, str]:
    import json

    pool_facts = getattr(pool, "selected_fact_plan", None) or getattr(pool, "facts", None) or {}
    pool_blob = json.dumps(pool_facts, sort_keys=True, default=str, separators=(",", ":"))
    return {
        "section_id": str(section_id or "").strip(),
        "target_role": str(target_role or "").strip(),
        "jd_sha256": hashlib.sha256(str(jd_text or "").strip().encode("utf-8")).hexdigest() if str(jd_text or "").strip() else "",
        "proof_pool_sha256": hashlib.sha256(pool_blob.encode("utf-8")).hexdigest(),
    }


def collect_sealed_c0_manifest_for_lanes(
    artifact_dir: Path,
    target_lanes: Sequence[str],
    *,
    raw_request: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    import json

    req = raw_request or {}
    jd_raw = str(req.get("job_description_text") or req.get("jd") or "").strip()
    if not jd_raw and isinstance(req.get("jd_payload"), Mapping):
        jd_raw = str(req["jd_payload"].get("description") or "").strip()
    req_jd_sha = hashlib.sha256(jd_raw.encode("utf-8")).hexdigest() if jd_raw else ""
    req_role = str(req.get("target_role") or "").strip()

    entries: dict[str, dict[str, Any]] = {}
    for lane in target_lanes:
        candidates: list[Path] = []
        for base in (artifact_dir / "modular_r4" / "sections" / lane, artifact_dir / "lanes" / lane):
            if not base.is_dir():
                continue
            if (base / "c0_evidence_room_receipt.json").is_file():
                candidates.append(base)
            for child in sorted(base.rglob("c0_evidence_room_receipt.json")):
                if child.parent not in candidates:
                    candidates.append(child.parent)
        chosen: Path | None = None
        chosen_ident: dict[str, Any] = {}
        for cand in reversed(candidates):
            room_path = cand / "c0_evidence_room_receipt.json"
            fec_path = cand / "final_evidence_contract.json"
            if not (room_path.is_file() and fec_path.is_file()):
                continue
            try:
                room_doc = json.loads(room_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            bridge_doc = room_doc.get("bridge_doc") if isinstance(room_doc, dict) else None
            if not isinstance(bridge_doc, dict):
                continue
            if str(bridge_doc.get("section_id") or "") != lane or not bridge_doc.get("c07_handoff_safe"):
                continue
            chosen = cand
            chosen_ident = dict(bridge_doc.get("c0_input_identity") or {})
            break
        if chosen is not None:
            entries[lane] = {
                "section_id": lane,
                "source_lane_dir": str(chosen.resolve()),
                "expected_target_role": chosen_ident.get("target_role") or req_role,
                "expected_jd_sha256": chosen_ident.get("jd_sha256") or req_jd_sha,
                "expected_proof_pool_sha256": chosen_ident.get("proof_pool_sha256") or "",
            }
    return entries


def try_reuse_recovery_sealed_c0_bridge(
    *,
    artifact_dir: Path,
    section_id: str,
    target_role: str,
    jd_text: str,
    pool: Any,
    runtime_payload: dict[str, Any],
) -> Any | None:
    import json
    import os
    import shutil

    manifest_raw = os.environ.get(RECOVERY_SEALED_C0_MANIFEST_ENV, "").strip()
    if not manifest_raw:
        return None
    manifest_path = Path(manifest_raw)
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    lanes_map = manifest.get("lanes") if isinstance(manifest, dict) else None
    entry = lanes_map.get(section_id) if isinstance(lanes_map, dict) else None
    if not isinstance(entry, dict):
        return None
    src_dir = Path(str(entry.get("source_lane_dir") or ""))
    room_path = src_dir / "c0_evidence_room_receipt.json"
    fec_path = src_dir / "final_evidence_contract.json"
    if not (src_dir.is_dir() and room_path.is_file() and fec_path.is_file()):
        return None
    try:
        room_doc = json.loads(room_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    bridge_doc = dict(room_doc.get("bridge_doc") or {}) if isinstance(room_doc, dict) else {}
    if str(bridge_doc.get("section_id") or "") != section_id or not bridge_doc.get("c07_handoff_safe"):
        return None

    ident = compute_c0_input_identity(
        section_id=section_id,
        target_role=target_role,
        jd_text=jd_text,
        pool=pool,
    )
    exp_role = str(entry.get("expected_target_role") or "").strip()
    exp_jd = str(entry.get("expected_jd_sha256") or "").strip()
    exp_pool = str(entry.get("expected_proof_pool_sha256") or "").strip()
    if exp_role and ident["target_role"] and exp_role != ident["target_role"]:
        return None
    if exp_jd and ident["jd_sha256"] and exp_jd != ident["jd_sha256"]:
        return None
    if exp_pool and ident["proof_pool_sha256"] and exp_pool != ident["proof_pool_sha256"]:
        return None

    artifact_dir.mkdir(parents=True, exist_ok=True)
    if src_dir.resolve() != artifact_dir.resolve():
        for src_file in src_dir.glob("*.json"):
            if src_file.name.startswith(("c0", "final_evidence_contract", "fact_vector_index_preflight")):
                shutil.copy2(src_file, artifact_dir / src_file.name)

    from apps_rg.runtime.c0.c0_section_authority import bridge_authority_fields
    from apps_rg.runtime.evidence.canonical_section_evidence_set import (
        apply_canonical_section_evidence_materialization,
        build_canonical_section_evidence_set,
        materialize_fec_allowed_from_c04,
    )
    from apps_rg.runtime.spine.c0_fec_compose import (
        FEC_BRIDGE_ARTIFACT,
        FEC_BRIDGE_RECEIPT,
        SectionFecBridge,
        emit_spine_c0_fec_artifacts,
    )

    canonical = build_canonical_section_evidence_set(pool)
    snap = dict(bridge_doc.get("final_evidence_contract_snapshot") or {})
    c04_allowed = list(snap.get("allowed_fact_ids") or [])
    allowed, fec_materialization_receipt = materialize_fec_allowed_from_c04(
        c04_allowed=c04_allowed,
        canonical=canonical,
    )
    runtime_payload["canonical_section_evidence_set"] = canonical.as_dict()
    runtime_payload["fec_materialization_receipt"] = fec_materialization_receipt
    bridge_doc["c0_recovery_reused_from"] = str(src_dir.resolve())
    bridge = SectionFecBridge(section_id=section_id, bridge_doc=bridge_doc)
    apply_canonical_section_evidence_materialization(
        pool=pool,
        runtime_payload=runtime_payload,
        bridge=bridge,
        fec_allowed=allowed,
        fec_materialization_receipt=fec_materialization_receipt,
    )
    authority = bridge_authority_fields()
    runtime_payload["section_fec_bridge"] = bridge.bridge_doc
    runtime_payload["fec_bridge_ref"] = FEC_BRIDGE_ARTIFACT
    runtime_payload["final_evidence_contract_ref"] = FEC_BRIDGE_ARTIFACT
    runtime_payload["c0_fec_bridge_receipt_ref"] = FEC_BRIDGE_RECEIPT
    runtime_payload["canonical_final_evidence_contract_snapshot"] = snap
    runtime_payload["raw_proof_pool_direct_to_pa"] = False
    runtime_payload["product_visible"] = True
    runtime_payload["c0_authority_mode"] = authority["c0_authority_mode"]
    emit_spine_c0_fec_artifacts(artifact_dir, bridge)
    (artifact_dir / "c0_recovery_reuse_receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "c0_recovery_reuse_receipt_v1",
                "section_id": section_id,
                "reused_from": str(src_dir.resolve()),
                "c0_input_identity": ident,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return bridge
