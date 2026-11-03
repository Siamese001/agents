"""Content-addressed Phase-1 section lane cache for modular resume generation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from apps_rg.cache.whole_run_fast_cache import is_no_cache_requested
from apps_rg.config.runtime_env import get_runtime_env_str, get_runtime_environ
from apps_rg.runtime.c0.graph_skill_embedding_allocation import (
    GRAPH_SKILL_EMBEDDING_ALLOWLISTS_ENV,
)
from apps_rg.runtime.c0.resume_graph_allocation import SECTION_EVIDENCE_CONTRACTS_ENV
from apps_rg.runtime.product_output_policy import lane_run_dir_meets_product_bar
from apps_rg.runtime.section_execution_plan import NARRATIVE_UPSTREAM_BULLET_LANE

_STAGE_0_AND_1_COMPANIONS: tuple[str, ...] = (
    "competencies",
    "slalom_bullets",
    "unify_bullets",
    "ibm_bullets",
    "insurtech_bullets",
    "slalom_narrative",
    "unify_narrative",
    "ibm_narrative",
    "insurtech_narrative",
)
_SYNTHESIS_LANES: frozenset[str] = frozenset({"headline", "executive_summary"})
_SKIP_CACHE_COPY_NAMES: frozenset[str] = frozenset(
    {"lane_dispatch_attempt.json", "section_lane_cache_hit_receipt.json"}
)
_POINTER_REWRITE_NAMES: tuple[str, ...] = (
    "latest_successful_real_run.json",
    "latest_real_run.json",
    "run_manifest.json",
)
_JSON_FILE_MEMO_LOCK = threading.Lock()
_JSON_FILE_MEMO: dict[str, tuple[int, int, dict[str, Any]]] = {}


def section_lane_cache_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = get_runtime_environ() if environ is None else environ
    if is_no_cache_requested(env):
        return False
    if str(env.get("APPS_RG_SECTION_CACHE_DISABLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    if env.get("PYTEST_CURRENT_TEST"):
        return str(env.get("APPS_RG_SECTION_CACHE_ENABLE") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    return True


def resolve_section_cache_root(repo: Path) -> Path:
    explicit = str(get_runtime_env_str("APPS_RG_SECTION_CACHE_ROOT") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    root = repo.resolve()
    if (root / "artifacts" / "apps_rg").exists() or root.name == "resume_graph_engine":
        return (root / "artifacts" / "apps_rg" / "cache" / "section_lanes_v1").resolve()
    return (
        root / "resume_graph_engine" / "artifacts" / "apps_rg" / "cache" / "section_lanes_v1"
    ).resolve()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_obj(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_bytes(payload.encode("utf-8"))


def _load_json_memoized(path_str: str) -> dict[str, Any]:
    if not path_str:
        return {}
    p = Path(path_str)
    try:
        st = p.stat()
    except OSError:
        return {}
    key = str(p.resolve())
    with _JSON_FILE_MEMO_LOCK:
        cached = _JSON_FILE_MEMO.get(key)
        if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return cached[2]
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    data = raw if isinstance(raw, dict) else {}
    with _JSON_FILE_MEMO_LOCK:
        _JSON_FILE_MEMO[key] = (st.st_mtime_ns, st.st_size, data)
    return data


def _extract_section_evidence_slice_digest(section_id: str) -> str:
    contracts = _load_json_memoized(str(get_runtime_env_str(SECTION_EVIDENCE_CONTRACTS_ENV) or ""))
    sec_contract = contracts.get(section_id)
    contract_projection: dict[str, Any] = {}
    if isinstance(sec_contract, Mapping):
        assignments_proj = []
        for row in sec_contract.get("assignments") or []:
            if not isinstance(row, Mapping):
                continue
            cleaned = {
                k: v
                for k, v in row.items()
                if k
                not in {
                    "selection_margin",
                    "selection_margin_available",
                    "selection_margin_basis",
                    "best_eligible_rejected_candidate_id",
                }
            }
            assignments_proj.append(cleaned)
        contract_projection = {
            "source_section_plan_digest": str(
                sec_contract.get("source_section_plan_digest") or ""
            ),
            "graph_digest": str(sec_contract.get("graph_digest") or ""),
            "representation_mode": str(sec_contract.get("representation_mode") or ""),
            "assignments": assignments_proj,
        }
    allowlists = _load_json_memoized(
        str(get_runtime_env_str(GRAPH_SKILL_EMBEDDING_ALLOWLISTS_ENV) or "")
    )
    by_sec = allowlists.get("allowlists_by_section")
    sec_allow = by_sec.get(section_id) if isinstance(by_sec, Mapping) else None
    allow_proj: Any = None
    if isinstance(sec_allow, Mapping):
        allow_proj = {
            k: v
            for k, v in sec_allow.items()
            if k not in {"allocation_plan_digest", "allowlists_digest"}
        }
    return _sha256_obj({"contract": contract_projection, "allowlist": allow_proj})


def _extract_upstream_companion_digest(sections_root: Path, section_id: str) -> str:
    upstream_bullet = NARRATIVE_UPSTREAM_BULLET_LANE.get(section_id)
    if upstream_bullet:
        p = sections_root / upstream_bullet / "l2_output.json"
        return _sha256_bytes(p.read_bytes()) if p.is_file() else "missing"
    if section_id in _SYNTHESIS_LANES:
        parts: dict[str, str] = {}
        for comp in _STAGE_0_AND_1_COMPANIONS:
            p = sections_root / comp / "l2_output.json"
            parts[comp] = _sha256_bytes(p.read_bytes()) if p.is_file() else "missing"
        return _sha256_obj(parts)
    return ""


def _resolve_text_or_path_digest(inline_text: str, ref_path: str) -> str:
    txt = str(inline_text or "").strip()
    if txt:
        return _sha256_bytes(txt.encode("utf-8"))
    ref = str(ref_path or "").strip()
    if ref:
        p = Path(ref)
        try:
            if p.is_file():
                return _sha256_bytes(p.read_bytes())
        except OSError:
            pass
        return _sha256_bytes(ref.encode("utf-8"))
    return _sha256_bytes(b"")


def compute_section_lane_cache_key(
    *,
    sections_root: Path,
    kwargs: Mapping[str, Any],
) -> str:
    section_id = str(kwargs.get("section") or "").strip()
    jd_sha = _resolve_text_or_path_digest(
        str(kwargs.get("job_description_text") or ""),
        str(kwargs.get("job_description_ref") or kwargs.get("jd") or ""),
    )
    brief_raw = str(kwargs.get("manual_brief") or "").strip()
    brief_sha = _resolve_text_or_path_digest("", brief_raw)
    return _sha256_obj(
        {
            "schema": "apps_rg.section_lane_cache_key.v1",
            "section_id": section_id,
            "target_company": str(kwargs.get("target_company") or "").strip().lower(),
            "target_role": str(kwargs.get("target_role") or "").strip().lower(),
            "generation_mode": str(kwargs.get("generation_mode") or "").strip(),
            "jd_sha256": jd_sha,
            "briefing_sha256": brief_sha,
            "lane_provider": str(kwargs.get("lane_provider") or "").strip(),
            "lane_x1d_judges": str(
                kwargs.get("lane_x1d_judges") or kwargs.get("x1d_judges") or ""
            ).strip(),
            "lane_mock_judges": bool(kwargs.get("lane_mock_judges", False)),
            "section_fec_digest": _extract_section_evidence_slice_digest(section_id),
            "upstream_companion_digest": _extract_upstream_companion_digest(
                sections_root, section_id
            ),
        }
    )


def _repo_rel_posix(path: Path, repo: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _copy_tree_unlinked(src_dir: Path, dst_dir: Path) -> None:
    for item in src_dir.rglob("*"):
        rel = item.relative_to(src_dir)
        if rel.parts and rel.parts[0] in _SKIP_CACHE_COPY_NAMES:
            continue
        target = dst_dir / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            try:
                os.link(item, target)
            except OSError:
                shutil.copy2(item, target)


def _rewrite_pointer_json(path: Path, old_rel: str, new_rel: str) -> None:
    if not path.is_file() or not old_rel or not new_rel or old_rel == new_rel:
        return
    try:
        raw_txt = path.read_text(encoding="utf-8")
        if old_rel not in raw_txt:
            return
        updated_txt = raw_txt.replace(old_rel, new_rel)
        json.loads(updated_txt)
        path.unlink()
        path.write_text(updated_txt, encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        return


def populate_section_lane_cache_entry(
    *,
    cache_root: Path,
    cache_key: str,
    repo: Path,
    lane_dir: Path,
    section_id: str,
    dispatch_result: Mapping[str, Any],
) -> bool:
    if not lane_dir.is_dir():
        return False
    ok, _ = lane_run_dir_meets_product_bar(lane_dir)
    if not ok:
        return False
    entry_dir = cache_root / cache_key
    if (entry_dir / "meta.json").is_file():
        return True
    cache_root.mkdir(parents=True, exist_ok=True)
    staging = cache_root / f".tmp_{section_id}_{uuid.uuid4().hex[:10]}"
    try:
        files_dir = staging / "lane_files"
        files_dir.mkdir(parents=True, exist_ok=True)
        _copy_tree_unlinked(lane_dir, files_dir)
        clean_res = {
            k: v
            for k, v in dict(dispatch_result).items()
            if isinstance(v, (str, int, float, bool, list, dict)) or v is None
        }
        clean_res.setdefault("exit_status", "success")
        meta = {
            "schema_version": "apps_rg.section_lane_cache_entry.v1",
            "section_id": section_id,
            "cache_key": cache_key,
            "source_rel_posix": _repo_rel_posix(lane_dir, repo),
            "dispatch_result": clean_res,
            "stored_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        (staging / "meta.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if entry_dir.exists():
            shutil.rmtree(staging, ignore_errors=True)
            return True
        staging.rename(entry_dir)
        return True
    except OSError:
        shutil.rmtree(staging, ignore_errors=True)
        return False


def dispatch_lane_with_section_cache(
    *,
    dispatch_fn: Callable[..., Any],
    repo: Path,
    sections_root: Path,
    kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    if not section_lane_cache_enabled():
        raw = dispatch_fn(**kwargs)
        return dict(raw) if isinstance(raw, dict) else {}

    t0 = time.perf_counter()
    section_id = str(kwargs.get("section") or "").strip()
    cache_root = resolve_section_cache_root(repo)
    cache_key = compute_section_lane_cache_key(sections_root=sections_root, kwargs=kwargs)
    entry_dir = cache_root / cache_key
    meta_path = entry_dir / "meta.json"
    files_dir = entry_dir / "lane_files"

    target_lane_dir = Path(
        str(kwargs.get("artifact_dir") or (sections_root / section_id))
    ).resolve()

    if meta_path.is_file() and files_dir.is_dir():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        if isinstance(meta, dict) and meta.get("cache_key") == cache_key:
            target_lane_dir.mkdir(parents=True, exist_ok=True)
            _copy_tree_unlinked(files_dir, target_lane_dir)
            old_rel = str(meta.get("source_rel_posix") or "")
            new_rel = _repo_rel_posix(target_lane_dir, repo)
            for ptr_name in _POINTER_REWRITE_NAMES:
                _rewrite_pointer_json(target_lane_dir / ptr_name, old_rel, new_rel)
            if (get_runtime_env_str("APPS_RG_WHOLE_RUN_ENVELOPE", "") or "").strip() in ("1", "true", "yes"):
                try:
                    from apps_rg.runtime.runtime_proof_layout import finalize_runtime_proof_run

                    rm_doc = _load_json_memoized(str(target_lane_dir / "run_manifest.json"))
                    prov_req = str(
                        rm_doc.get("provider_requested") or kwargs.get("lane_provider") or ""
                    )
                    rt_stat = str(rm_doc.get("runtime_generation_status") or "REAL_LLM")
                    if prov_req:
                        finalize_runtime_proof_run(
                            repo,
                            section_id,
                            prov_req,
                            target_lane_dir,
                            run_id=str(rm_doc.get("run_id") or f"{section_id}_cached"),
                            section_id=section_id,
                            runtime_generation_status=rt_stat,
                            provider_requested=prov_req,
                            provider_attempted=True,
                        )
                except Exception:  # guardian: allow-silent-swallow -- minimal test fixtures may omit optional telemetry
                    pass
            ok, _ = lane_run_dir_meets_product_bar(target_lane_dir)
            if ok:
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                receipt = {
                    "schema_version": "apps_rg.section_lane_cache_hit_receipt.v1",
                    "section_id": section_id,
                    "cache_key": cache_key,
                    "provider_call_count": 0,
                    "elapsed_ms": elapsed_ms,
                    "source_rel_posix": old_rel,
                    "target_rel_posix": new_rel,
                }
                (target_lane_dir / "section_lane_cache_hit_receipt.json").write_text(
                    json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                saved = meta.get("dispatch_result")
                out = dict(saved) if isinstance(saved, dict) else {}
                out.update(
                    {
                        "artifact_dir": str(target_lane_dir),
                        "exit_status": str(out.get("exit_status") or "success"),
                        "section_cache_hit": True,
                        "provider_call_count": 0,
                    }
                )
                return out

    raw = dispatch_fn(**kwargs)
    res = dict(raw) if isinstance(raw, dict) else {}
    from apps_rg.l2_recipe.modular_lane_adapter import resolve_latest_lane_run_dir

    try:
        resolved_dir = resolve_latest_lane_run_dir(
            repo,
            sections_root,
            section_id,
            lane_provider=str(kwargs.get("lane_provider") or ""),
        )
    except FileNotFoundError:
        resolved_dir = target_lane_dir
    populate_section_lane_cache_entry(
        cache_root=cache_root,
        cache_key=cache_key,
        repo=repo,
        lane_dir=resolved_dir,
        section_id=section_id,
        dispatch_result=res,
    )
    return res


__all__ = [
    "compute_section_lane_cache_key",
    "dispatch_lane_with_section_cache",
    "populate_section_lane_cache_entry",
    "resolve_section_cache_root",
    "section_lane_cache_enabled",
]
