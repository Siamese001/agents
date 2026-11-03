"""R1A exact-hash cache helpers (deterministic O(1) indexed store under runs_dir).

Contract:
- Stamp JSON envelope ``r1a_stamp.json`` alongside ``outputs/generated_resume.json``
  (or root ``generated_resume.json`` for legacy harnesses) plus ``r1a_index.json`` in ``runs_dir``.
- Preserve read-compat for legacy 3-tuple keys and ``r1a_key.txt`` stamps.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

CACHE_SCHEMA_VERSION = "2026-05-02-r1a-v2"
R1A_INDEX_FILENAME = "r1a_index.json"


def compute_r1a_key(
    *,
    source_resume_hash: str,
    target_company: str,
    target_role: str,
    jd_hash: str = "",
    briefing_hash: str = "",
) -> str:
    """Return a deterministic 64-hex fingerprint for resume + target (+ optional JD/briefing)."""
    corp = target_company.strip().lower()
    role = target_role.strip().lower()
    resume = source_resume_hash.strip()
    jd_clean = jd_hash.strip()
    br_clean = briefing_hash.strip()
    if not jd_clean and not br_clean:
        envelope = f"r1a|v1|{resume}|{corp}|{role}"
    else:
        envelope = f"r1a|v2|{resume}|{corp}|{role}|{jd_clean}|{br_clean}"
    return hashlib.sha256(envelope.encode("utf-8")).hexdigest()


def _has_generated_resume(run_dir: Path) -> bool:
    return (run_dir / "outputs" / "generated_resume.json").is_file() or (
        run_dir / "generated_resume.json"
    ).is_file()


def _load_r1a_index(runs_root: Path) -> dict[str, str]:
    idx_path = runs_root / R1A_INDEX_FILENAME
    if not idx_path.is_file():
        return {}
    try:
        doc = json.loads(idx_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError):
        return {}
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, dict):
        return {}
    return {str(k): str(v) for k, v in entries.items() if str(k).strip() and str(v).strip()}


def _save_r1a_index(runs_root: Path, entries: dict[str, str]) -> None:
    try:
        runs_root.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": CACHE_SCHEMA_VERSION, "entries": dict(sorted(entries.items()))}
        tmp = runs_root / f".{R1A_INDEX_FILENAME}.tmp"
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(runs_root / R1A_INDEX_FILENAME)
    except OSError:
        # guardian: allow-silent-swallow -- index is an O(1) accelerator over authoritative stamps
        pass


def stamp_r1a_cache(
    key: str,
    run_dir: str | Path,
    *,
    policy_hash: str | None = None,
    blueprint_hash: str | None = None,
    jd_hash: str | None = None,
    briefing_hash: str | None = None,
    extra_keys: list[str] | None = None,
) -> None:
    """Write ``r1a_stamp.json`` into ``run_dir`` and update ``r1a_index.json`` in its parent."""
    rd = Path(run_dir)
    rd.mkdir(parents=True, exist_ok=True)
    blob: dict[str, Any] = {
        "key": key,
        "schema_version": CACHE_SCHEMA_VERSION,
        "stamped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if extra_keys:
        blob["extra_keys"] = [str(k).strip() for k in extra_keys if str(k).strip()]
    if policy_hash is not None:
        blob["policy_hash"] = policy_hash
    if blueprint_hash is not None:
        blob["blueprint_hash"] = blueprint_hash
    if jd_hash is not None:
        blob["jd_hash"] = jd_hash
    if briefing_hash is not None:
        blob["briefing_hash"] = briefing_hash
    stamp_path = rd / "r1a_stamp.json"
    stamp_path.write_text(json.dumps(blob, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    parent = rd.parent
    if parent.is_dir():
        entries = _load_r1a_index(parent)
        entries[str(key).strip()] = rd.name
        for ek in blob.get("extra_keys") or []:
            entries[str(ek).strip()] = rd.name
        _save_r1a_index(parent, entries)


def _stamp_matches_requested(
    stamp: dict[str, Any],
    key: str,
    *,
    policy_hash: str | None,
    blueprint_hash: str | None,
    jd_hash: str | None = None,
    briefing_hash: str | None = None,
) -> bool:
    req_key = str(key).strip()
    valid_keys = {str(stamp.get("key", "")).strip()}
    for ek in stamp.get("extra_keys") or []:
        valid_keys.add(str(ek).strip())
    if req_key not in valid_keys:
        return False
    if policy_hash is not None:
        stamped = stamp.get("policy_hash")
        if stamped is not None and str(stamped) != str(policy_hash):
            return False
    if blueprint_hash is not None:
        stamped = stamp.get("blueprint_hash")
        if stamped is not None and str(stamped) != str(blueprint_hash):
            return False
    if jd_hash is not None and str(jd_hash).strip():
        stamped_jd = stamp.get("jd_hash")
        if stamped_jd is not None and str(stamped_jd).strip() and str(stamped_jd).strip() != str(jd_hash).strip():
            return False
    if briefing_hash is not None and str(briefing_hash).strip():
        stamped_br = stamp.get("briefing_hash")
        if stamped_br is not None and str(stamped_br).strip() and str(stamped_br).strip() != str(briefing_hash).strip():
            return False
    return True


def _check_candidate_child(
    child: Path,
    key: str,
    *,
    policy_hash: str | None,
    blueprint_hash: str | None,
    jd_hash: str | None,
    briefing_hash: str | None,
) -> str | None:
    if not child.is_dir() or not _has_generated_resume(child):
        return None
    stamp_file = child / "r1a_stamp.json"
    if stamp_file.is_file():
        try:
            stamp = json.loads(stamp_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError):
            return None
        if isinstance(stamp, dict) and _stamp_matches_requested(
            stamp,
            key,
            policy_hash=policy_hash,
            blueprint_hash=blueprint_hash,
            jd_hash=jd_hash,
            briefing_hash=briefing_hash,
        ):
            return str(child.resolve())
        return None

    txt = child / "r1a_key.txt"
    if txt.is_file():
        legacy = txt.read_text(encoding="utf-8").strip()
        if legacy == key.strip():
            if policy_hash is not None or blueprint_hash is not None:
                return None
            return str(child.resolve())
    return None


def check_r1a_cache(
    key: str,
    *,
    runs_dir: Path | str,
    policy_hash: str | None = None,
    blueprint_hash: str | None = None,
    jd_hash: str | None = None,
    briefing_hash: str | None = None,
) -> str | None:
    """Return artifact directory containing a stamped hit, or ``None``."""
    root = Path(runs_dir)
    if not root.is_dir():
        return None

    entries = _load_r1a_index(root)
    indexed_name = entries.get(str(key).strip())
    if indexed_name:
        hit = _check_candidate_child(
            root / indexed_name,
            key,
            policy_hash=policy_hash,
            blueprint_hash=blueprint_hash,
            jd_hash=jd_hash,
            briefing_hash=briefing_hash,
        )
        if hit is not None:
            return hit

    for child in sorted(root.iterdir()):
        hit = _check_candidate_child(
            child,
            key,
            policy_hash=policy_hash,
            blueprint_hash=blueprint_hash,
            jd_hash=jd_hash,
            briefing_hash=briefing_hash,
        )
        if hit is not None:
            entries[str(key).strip()] = child.name
            _save_r1a_index(root, entries)
            return hit

    return None


def prune_stale_r1a_entries(
    *,
    runs_dir: Path | str,
    policy_hash: str | None = None,
    blueprint_hash: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Remove run directories stamped with mismatched hashes (destructive helper)."""
    root = Path(runs_dir)
    if not root.is_dir():
        return []

    pruned: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        stamp_file = child / "r1a_stamp.json"
        if not stamp_file.is_file():
            continue
        try:
            stamp = json.loads(stamp_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError):
            continue
        if not isinstance(stamp, dict):
            continue

        stale = False
        if policy_hash is not None and "policy_hash" in stamp:
            if str(stamp.get("policy_hash")) != str(policy_hash):
                stale = True
        if blueprint_hash is not None and "blueprint_hash" in stamp:
            if str(stamp.get("blueprint_hash")) != str(blueprint_hash):
                stale = True

        if stale:
            pruned.append(child.name)
            if not dry_run:
                shutil.rmtree(child, ignore_errors=True)  # guardian: allow-missing-hitl-on-irreversible -- stale cache-dir prune; ephemeral blueprint artifacts only

    if pruned and not dry_run:
        entries = _load_r1a_index(root)
        pruned_set = set(pruned)
        cleaned = {k: v for k, v in entries.items() if v not in pruned_set}
        _save_r1a_index(root, cleaned)

    return pruned
