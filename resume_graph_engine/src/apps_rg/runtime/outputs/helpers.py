"""Utility and helper functions for mandatory outputs."""
from __future__ import annotations

import hashlib
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import *

__all__ = ['_utc_now', '_load_json', '_repo_rel', '_write_text', '_read_text', '_as_list', '_x2_summary_doc', '_score_text', '_first_nonempty', '_briefing_blob', '_short_digest', '_payload_dict', '_artifact_input_value', '_resolve_input_ref', '_first_existing_json', '_research_handoff_receipt', '_research_artifact_dirs', '_research_handoff_v2', '_exact_key_order', '_markdown_table_escape']

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _repo_rel(path: Path, repo: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _x2_summary_doc(x2: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    gates = x2.get("gates")
    if not isinstance(gates, list):
        failed = x2.get("failed_gates") or x2.get("x2_failed_gate_ids")
        if isinstance(failed, list) and failed:
            return (
                "FAIL",
                [
                    {
                        "gate_id": str(gate_id),
                        "failure_reason": "",
                        "observed_value": None,
                        "threshold": None,
                    }
                    for gate_id in failed
                ],
            )
        return "UNKNOWN", []
    failed_rows: list[dict[str, Any]] = []
    for gate in gates:
        if not isinstance(gate, dict) or gate.get("pass", True):
            continue
        failed_rows.append(
            {
                "gate_id": str(gate.get("gate_id") or gate.get("id") or "unknown_gate"),
                "failure_reason": gate.get("failure_reason") or "",
                "observed_value": gate.get("observed_value"),
                "threshold": gate.get("threshold"),
                "evidence_ref": gate.get("evidence_ref"),
            }
        )
    return ("FAIL" if failed_rows else "PASS"), failed_rows


def _score_text(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _briefing_blob(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"briefing_text": text}
    return parsed if isinstance(parsed, dict) else {"briefing_text": text}


def _short_digest(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "NOT_OBSERVED"
    return text[:12]


def _payload_dict(blob: dict[str, Any]) -> dict[str, Any]:
    payload = blob.get("payload")
    return payload if isinstance(payload, dict) else {}


def _artifact_input_value(blob: dict[str, Any], *keys: str) -> str:
    payload = _payload_dict(blob)
    for source in (blob, payload):
        for key in keys:
            value = str(source.get(key) or "").strip()
            if value:
                return value
    return ""


def _resolve_input_ref(ref: str, *, run_root: Path, repo_root: Path) -> str:
    text = str(ref or "").strip()
    if not text or text.startswith(("http://", "https://")):
        return text
    path = Path(text).expanduser()
    if path.is_absolute():
        return str(path)
    for base in (run_root, repo_root, Path.cwd()):
        try:
            candidate = (base / path).resolve()
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return text


def _first_existing_json(paths: list[Path]) -> tuple[Path | None, dict[str, Any]]:
    for path in paths:
        data = _load_json(path)
        if data:
            return path, data
    return None, {}


def _research_handoff_receipt(run_root: Path) -> dict[str, Any]:
    candidates = [run_root / "apps_research_handoff_validation_receipt.json"]
    try:
        candidates.extend(sorted(run_root.rglob("apps_research_handoff_validation_receipt.json")))
    except OSError:
        pass
    _path, data = _first_existing_json(candidates)
    return data


def _research_artifact_dirs(run_root: Path) -> list[Path]:
    dirs: list[Path] = []
    for ref_path in (
        run_root / "research" / "research_artifact_ref.json",
        run_root / "research_bridge_response.json",
    ):
        data = _load_json(ref_path)
        raw = str(data.get("research_artifact_dir") or "").strip()
        if raw:
            dirs.append(Path(raw).expanduser())
    return dirs


def _research_handoff_v2(
    run_root: Path,
    *,
    repo_root: Path,
    brief_ref: str,
) -> dict[str, Any]:
    candidates: list[Path] = [
        run_root / "apps_research_apps_rg_handoff_v2.json"
    ]
    resolved_brief = _resolve_input_ref(brief_ref, run_root=run_root, repo_root=repo_root)
    if resolved_brief and not resolved_brief.startswith(("http://", "https://")):
        brief_path = Path(resolved_brief)
        candidates.extend(
            [
                brief_path.parent / "apps_research_apps_rg_handoff_v2.json",
            ]
        )
    for artifact_dir in _research_artifact_dirs(run_root):
        candidates.append(artifact_dir / "apps_research_apps_rg_handoff_v2.json")
    _path, data = _first_existing_json(candidates)
    return data


def _exact_key_order(value: Any, keys: tuple[str, ...]) -> bool:
    return isinstance(value, dict) and tuple(value.keys()) == keys


def _markdown_table_escape(value: Any) -> str:
    return str(value if value is not None else "-").replace("|", "\\|").replace("\n", " ")

