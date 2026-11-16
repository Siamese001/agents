"""Fork-join wave DAG numbering, dependency validation, and shard-manifest annex parser."""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from tools.prompt_scope_isolation import paths_overlap

RE_WAVE_DAG_ID = re.compile(r"^(\d+)([A-Z]{0,2})$", re.IGNORECASE)
_DEPENDS_ON_RE = re.compile(
    r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Depends\s+On(?:\*\*)?\s*:\s*(.+)$",
    re.IGNORECASE,
)
_SHARD_MANIFEST_BLOCK_RE = re.compile(
    r"```(?:yaml|json)\s+shard-manifest\s*\n([\s\S]*?)```",
    re.IGNORECASE,
)
_MAX_SHARD_STR_LEN = 4096


def _parse_wave_token(raw_token: str) -> tuple[int, str, str] | None:
    cleaned = re.sub(r"^wave\s+", "", raw_token.strip(), flags=re.IGNORECASE).strip()
    m = RE_WAVE_DAG_ID.match(cleaned)
    if not m:
        return None
    num = int(m.group(1))
    sfx = (m.group(2) or "").upper()
    return num, sfx, f"{num}{sfx}"


def _extract_depends_on(wave: object) -> list[str]:
    deps: list[str] = []
    for _lineno, line in getattr(wave, "lines", []):
        m = _DEPENDS_ON_RE.match(line.strip())
        if not m:
            continue
        raw_val = m.group(1).strip()
        if raw_val.lower() in ("none", "n/a", "-", "root"):
            continue
        for part in re.split(r"[,;/]+", raw_val):
            parsed = _parse_wave_token(part)
            if parsed is not None:
                deps.append(parsed[2])
            elif part.strip():
                deps.append(part.strip().upper())
    return deps


def _detect_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    state: dict[str, int] = {}
    path: list[str] = []

    def _dfs(node: str) -> list[str] | None:
        state[node] = 1
        path.append(node)
        for nxt in graph.get(node, []):
            if nxt not in graph:
                continue
            if state.get(nxt) == 1:
                idx = path.index(nxt)
                return [*path[idx:], nxt]
            if state.get(nxt, 0) == 0:
                cyc = _dfs(nxt)
                if cyc:
                    return cyc
        path.pop()
        state[node] = 2
        return None

    for k in graph:
        if state.get(k, 0) == 0:
            res = _dfs(k)
            if res:
                return res
    return None


def validate_wave_dag_sequence(waves: Sequence[object], filename: str) -> list[str]:
    """Validate sequential or fork-join sharded wave numbering and optional Depends On DAG."""
    errors: list[str] = []
    if not waves:
        return errors

    start_num = int(getattr(waves[0], "number", -1))
    if start_num not in (0, 1):
        errors.append(
            f"{filename}: First wave must be numbered Wave 0 or Wave 1. "
            f"Found Wave {getattr(waves[0], 'wave_id', start_num)} at line {getattr(waves[0], 'start_line', 1)}."
        )

    expected_num = start_num
    seen_ids: set[str] = set()
    by_number: dict[int, list[tuple[str, str, int]]] = {}

    for idx, w in enumerate(waves):
        num = int(getattr(w, "number", 0))
        sfx = str(getattr(w, "shard_suffix", "") or "").upper()
        wid = str(getattr(w, "wave_id", f"{num}{sfx}"))
        line_no = int(getattr(w, "start_line", 1))

        if idx > 0:
            prev_num = int(getattr(waves[idx - 1], "number", 0))
            if num == prev_num:
                pass
            elif num == prev_num + 1:
                expected_num = num
            else:
                errors.append(
                    f"{filename}: Non-sequential wave numbering at line {line_no}. "
                    f"Expected Wave {prev_num + 1}, found Wave {wid}."
                )
                expected_num = num
        elif num != expected_num:
            expected_num = num

        if wid in seen_ids:
            errors.append(f"{filename}: Duplicate Wave {wid} declared at line {line_no}.")
        seen_ids.add(wid)
        by_number.setdefault(num, []).append((wid, sfx, line_no))

    for num, entries in by_number.items():
        has_plain = any(sfx == "" for _, sfx, _ in entries)
        has_sharded = any(sfx != "" for _, sfx, _ in entries)
        if has_plain and has_sharded:
            line_no = entries[-1][2]
            errors.append(
                f"{filename}: Line {line_no}: Cannot mix unsharded 'Wave {num}' and sharded "
                f"'Wave {num}A/B' at the same wave number."
            )

    dep_graph: dict[str, list[str]] = {}
    for w in waves:
        wid = str(getattr(w, "wave_id", getattr(w, "number", "")))
        line_no = int(getattr(w, "start_line", 1))
        deps = _extract_depends_on(w)
        dep_graph[wid] = deps
        for d in deps:
            if d not in seen_ids:
                errors.append(
                    f"{filename}: Line {line_no} (Wave {wid}): Depends On references unknown Wave '{d}'."
                )

    cycle = _detect_cycle(dep_graph)
    if cycle:
        errors.append(f"{filename}: Dependency cycle detected in Wave Depends On graph: {' -> '.join(cycle)}.")

    return errors


def _parse_manifest_text(raw_body: str) -> Any:
    stripped = raw_body.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    import yaml  # type: ignore

    return yaml.safe_load(stripped)


def _validate_single_shard_manifest(data: Any, filename: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(data, dict):
        return [f"{filename}: shard-manifest block must parse to a dictionary object."]
    shards = data.get("shards")
    if not isinstance(shards, list) or len(shards) < 1:
        return [f"{filename}: shard-manifest must declare a non-empty 'shards' list (minItems: 1)."]

    seen_shard_ids: set[str] = set()
    shard_scopes: list[tuple[str, list[str]]] = []

    for idx, item in enumerate(shards):
        if not isinstance(item, dict):
            errs.append(f"{filename}: shard-manifest shards[{idx}] must be an object.")
            continue
        sid = str(item.get("shard_id") or item.get("id") or "").strip()
        if not sid:
            errs.append(f"{filename}: shard-manifest shards[{idx}] missing non-empty 'shard_id'.")
            continue
        if len(sid) > _MAX_SHARD_STR_LEN:
            errs.append(f"{filename}: shard-manifest shard '{sid[:32]}' exceeds {_MAX_SHARD_STR_LEN}-char cap.")
        if sid in seen_shard_ids:
            errs.append(f"{filename}: shard-manifest declares duplicate shard_id '{sid}'.")
        seen_shard_ids.add(sid)

        scope_in = item.get("scope_in")
        if not isinstance(scope_in, list) or not scope_in or not all(isinstance(p, str) and p.strip() for p in scope_in):
            errs.append(f"{filename}: shard-manifest shard '{sid}' requires non-empty 'scope_in' path list.")
            continue
        clean_scope = [p.strip() for p in scope_in]
        if any(len(p) > _MAX_SHARD_STR_LEN for p in clean_scope):
            errs.append(f"{filename}: shard-manifest shard '{sid}' has scope_in entry exceeding {_MAX_SHARD_STR_LEN} chars.")
        shard_scopes.append((sid, clean_scope))

        verify_cmd = str(item.get("verify_independently") or item.get("verification") or "").strip()
        if not verify_cmd:
            errs.append(f"{filename}: shard-manifest shard '{sid}' requires non-empty 'verify_independently'.")
        elif len(verify_cmd) > _MAX_SHARD_STR_LEN:
            errs.append(f"{filename}: shard-manifest shard '{sid}' verify_independently exceeds {_MAX_SHARD_STR_LEN} chars.")

    if bool(data.get("require_disjoint", False)):
        for i, (sid_a, paths_a) in enumerate(shard_scopes):
            for sid_b, paths_b in shard_scopes[i + 1 :]:
                for pa in paths_a:
                    for pb in paths_b:
                        if paths_overlap(pa, pb):
                            errs.append(
                                f"{filename}: shard-manifest scope_in overlap between '{sid_a}' ('{pa}') "
                                f"and '{sid_b}' ('{pb}')."
                            )
    return errs


def strip_and_validate_shard_manifests(content: str, filename: str = "plan.md") -> tuple[str, list[str]]:
    """Validate any fenced ```yaml/json shard-manifest blocks and strip only valid blocks before word count."""
    errors: list[str] = []
    valid_spans: list[tuple[int, int]] = []

    for match in _SHARD_MANIFEST_BLOCK_RE.finditer(content):
        raw_body = match.group(1)
        try:
            parsed = _parse_manifest_text(raw_body)
        except Exception as exc:
            errors.append(f"{filename}: Failed to parse shard-manifest block: {exc}")
            continue
        block_errs = _validate_single_shard_manifest(parsed, filename)
        if block_errs:
            errors.extend(block_errs)
        else:
            valid_spans.append(match.span())

    if not valid_spans:
        return content, errors

    chunks: list[str] = []
    last_idx = 0
    for start, end in valid_spans:
        chunks.append(content[last_idx:start])
        last_idx = end
    chunks.append(content[last_idx:])
    return "".join(chunks), errors
