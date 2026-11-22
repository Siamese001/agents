"""external model-aware Phase-1 lane wave scheduling (plan apps-rg-parallel-section-orchestration-f2a8c4)."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import heapq
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from apps_rg.repository_layout import repository_root, resolve_repository_path
from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES

_MANIFEST_REL = (
    Path("apps_rg") / "config" / "domain_contract" / "workflow_manifest.resume_sections.v1.yaml"
)
_ENV_MAX_PARALLEL = "APPS_RG_PHASE1_MAX_PARALLEL"
_ENV_PARALLEL = "APPS_RG_PARALLEL_PHASE1_LANES"


@dataclass(frozen=True)
class LaneWave:
    wave_id: int
    lanes: tuple[str, ...]
    max_parallel: int


import functools


def _repo_root() -> Path:
    return repository_root(Path(__file__))


@functools.lru_cache(maxsize=1)
def load_section_dag_manifest() -> dict[str, Any]:
    path = resolve_repository_path(_repo_root(), _MANIFEST_REL)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"invalid manifest: {path}")
    return raw


def phase1_parallel_enabled(*, profile_flag: bool = False) -> bool:
    env = str(os.environ.get(_ENV_PARALLEL, "")).strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    return bool(profile_flag)


def resolve_max_parallel(*, default: int = 6) -> int:
    raw = str(os.environ.get(_ENV_MAX_PARALLEL, "")).strip()
    if raw.isdigit():
        return max(1, min(12, int(raw)))
    return max(1, min(12, default))


def assert_section_dag_wave_order(manifest: dict[str, Any]) -> None:
    """Every lane ``depends_on`` must appear in a strictly earlier wave than the dependent lane."""
    lanes_raw = manifest.get("lanes") or []
    lane_meta: dict[str, dict[str, Any]] = {}
    for entry in lanes_raw:
        if not isinstance(entry, dict):
            continue
        lid = str(entry.get("id") or "").strip()
        if lid:
            lane_meta[lid] = entry

    lane_wave: dict[str, int] = {}
    for wave in manifest.get("waves") or []:
        if not isinstance(wave, dict):
            continue
        wid = int(wave.get("id", 0))
        for lane_id in wave.get("lanes") or []:
            lane_wave[str(lane_id)] = wid

    for lane_id, entry in lane_meta.items():
        for dep in entry.get("depends_on") or []:
            dep_id = str(dep).strip()
            if dep_id not in lane_meta:
                raise ValueError(f"lane '{lane_id}' depends_on unknown lane '{dep_id}'")
            w_lane = lane_wave.get(lane_id)
            w_dep = lane_wave.get(dep_id)
            if w_lane is None:
                raise ValueError(f"lane '{lane_id}' missing from waves schedule")
            if w_dep is None:
                raise ValueError(f"lane '{lane_id}' depends_on '{dep_id}' missing from waves schedule")
            if w_dep >= w_lane:
                raise ValueError(
                    f"lane '{lane_id}' (wave {w_lane}) must run after '{dep_id}' (wave {w_dep})"
                )


def section_dag_dependencies(*, lanes: tuple[str, ...] | None = None) -> dict[str, tuple[str, ...]]:
    """Return the selected Phase-1 lanes' direct dependencies from the manifest SSOT.

    ``waves`` remain useful operator-facing rollups, but they are not execution
    barriers: a lane can become ready as soon as each direct dependency has a
    certified outcome.  Dependencies outside ``lanes`` are deliberately omitted
    so the existing single-section and subset dispatch callers retain their
    self-contained semantics.
    """
    manifest = load_section_dag_manifest()
    assert_section_dag_wave_order(manifest)
    selected = set(lanes or GENERATED_LANES)
    out: dict[str, tuple[str, ...]] = {}
    for entry in manifest.get("lanes") or []:
        if not isinstance(entry, dict):
            continue
        lane = str(entry.get("id") or "").strip()
        if lane not in selected:
            continue
        deps = tuple(
            dependency_id
            for dependency_id in (
                str(dep).strip() for dep in (entry.get("depends_on") or [])
            )
            if dependency_id in selected
        )
        out[lane] = deps
    return out


def topological_lane_order(
    lanes: Sequence[str],
    *,
    deps_by_lane: Mapping[str, Sequence[str]] | None = None,
) -> tuple[str, ...]:
    """Return ``lanes`` in topological dependency order, preserving input order as tie-breaker."""
    ordered = tuple(dict.fromkeys(str(lane) for lane in lanes if str(lane)))
    if not ordered:
        return ()
    deps_map = deps_by_lane if deps_by_lane is not None else section_dag_dependencies(lanes=ordered)
    index_of = {lane: idx for idx, lane in enumerate(ordered)}
    in_degree: dict[str, int] = {}
    dependents: dict[str, list[str]] = {lane: [] for lane in ordered}
    for lane in ordered:
        valid_deps = [
            dep
            for dep in dict.fromkeys(deps_map.get(lane, ()))
            if dep in index_of and dep != lane
        ]
        in_degree[lane] = len(valid_deps)
        for dep in valid_deps:
            dependents[dep].append(lane)

    ready: list[tuple[int, str]] = [
        (index_of[lane], lane) for lane in ordered if in_degree[lane] == 0
    ]
    heapq.heapify(ready)
    result: list[str] = []
    while ready:
        _idx, lane = heapq.heappop(ready)
        result.append(lane)
        for child in dependents[lane]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                heapq.heappush(ready, (index_of[child], child))

    if len(result) != len(ordered):
        remaining = [lane for lane in ordered if lane not in set(result)]
        raise ValueError(f"Cycle detected in section lane DAG: {remaining}")
    return tuple(result)


def build_phase1_waves() -> tuple[LaneWave, ...]:
    """Ordered waves respecting DAG; wave 0 exec solo when parallel mode on."""
    manifest = load_section_dag_manifest()
    assert_section_dag_wave_order(manifest)
    waves_raw = manifest.get("waves") or []
    out: list[LaneWave] = []
    for w in waves_raw:
        if not isinstance(w, dict):
            continue
        wid = int(w.get("id", 0))
        lanes = tuple(str(x) for x in (w.get("lanes") or []) if str(x) in GENERATED_LANES)
        mp = int(w.get("max_parallel", 0) or 0)
        if mp <= 0:
            mp = resolve_max_parallel(default=int(w.get("default_max_parallel", 6) or 6))
        out.append(LaneWave(wave_id=wid, lanes=lanes, max_parallel=mp))
    if not out:
        return (LaneWave(wave_id=1, lanes=GENERATED_LANES, max_parallel=1),)
    return tuple(sorted(out, key=lambda x: x.wave_id))


__all__ = [
    "LaneWave",
    "assert_section_dag_wave_order",
    "build_phase1_waves",
    "load_section_dag_manifest",
    "phase1_parallel_enabled",
    "resolve_max_parallel",
    "section_dag_dependencies",
    "topological_lane_order",
]
