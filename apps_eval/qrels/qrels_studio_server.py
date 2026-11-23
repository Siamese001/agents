"""Governed Pure-White (#ffffff) Click-to-Grade Blind QRELS Studio Server (DIE Parity).

Serves `/`, `/api/state`, `/api/grade`, and `/api/quarantine` on localhost with:
- Strict `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` headers
- Blind stripping of all channel ranks/scores before sending items to the browser
- Seeded deterministic presentation ordering
- Fail-closed rubric consistency & Grade-0 rationale enforcement via `ExternalQrelsHumanStore`
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from apps_eval.qrels.qrels_human_store import (
    DEFAULT_QRELS_HUMAN_STORE_REL_PATH,
    ExternalQrelsHumanStore,
    validate_human_qrels_annotator_id,
)
from apps_eval.qrels.qrels_rubric_contract import (
    QRELS_ATOMIC_CHECKS,
    QRELS_REJECTION_TAGS,
    load_and_verify_qrels_rubric,
    shuffle_qrels_pool_seeded,
    strip_blind_forbidden_fields,
)
from apps_eval.qrels.qrels_studio_template import QRELS_STUDIO_HTML


@dataclass(frozen=True)
class QrelsStudioConfig:
    pool_path: Path
    store_path: Path
    rubric_path: Path | None
    annotator_id: str
    seed: int | None
    max_items: int | None = None


class QrelsStudioServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], studio_cfg: QrelsStudioConfig) -> None:
        self.studio_cfg = studio_cfg
        super().__init__(server_address, QrelsStudioHandler)


def _flatten_blind_pool_items(pool: dict[str, Any], seed: int | None, max_items: int | None) -> list[dict[str, Any]]:
    """Flatten either pre-flattened `items` or nested `queries[].candidates[]` with strict blinding."""
    raw_items: list[dict[str, Any]] = []
    if isinstance(pool.get("items"), list):
        for it in pool["items"]:
            raw_items.append(strip_blind_forbidden_fields(it))
    else:
        for q in pool.get("queries") or []:
            for cand in q.get("candidates") or []:
                merged = strip_blind_forbidden_fields(cand)
                merged.setdefault("pair_id", f"{q['query_id']}::{cand['record_id']}")
                merged.setdefault("query_id", str(q["query_id"]))
                merged.setdefault("query_text", str(q.get("query_text") or ""))
                merged.setdefault("surface", str(cand.get("surface") or q.get("surface") or "candidate_graph"))
                merged.setdefault("target_section", str(q.get("target_section") or "general"))
                merged.setdefault("topic_family", str(q.get("topic_family") or q.get("topic_id") or ""))
                merged.setdefault("partition", str(q.get("partition") or "dev"))
                raw_items.append(merged)
    shuffled = shuffle_qrels_pool_seeded(raw_items, seed)
    if max_items is not None and max_items > 0:
        return shuffled[:max_items]
    return shuffled


def build_qrels_studio_state_payload(cfg: QrelsStudioConfig) -> dict[str, Any]:
    """Assemble the sanitized `/api/state` JSON payload for the Pure-White QRELS Studio."""
    rubric = load_and_verify_qrels_rubric(cfg.rubric_path)
    pool = json.loads(cfg.pool_path.read_text(encoding="utf-8"))
    items = _flatten_blind_pool_items(pool, cfg.seed, cfg.max_items)
    store = ExternalQrelsHumanStore(store_path=cfg.store_path, rubric_path=cfg.rubric_path)
    return {
        "status": "PASS",
        "surface": pool.get("surface", "multi_surface"),
        "presentation_seed": cfg.seed if cfg.seed is not None else pool.get("presentation_seed"),
        "items": items,
        "rubric": rubric,
        "atomic_checks": list(QRELS_ATOMIC_CHECKS),
        "rejection_tags": list(QRELS_REJECTION_TAGS),
        "savedByPair": {r.pair_id: r.to_dict() for r in store.load_records()},
        "quarantinedByPair": {q.pair_id: q.to_dict() for q in store.load_quarantined()},
        "store_path": str(cfg.store_path),
    }


def persist_qrels_grade_request(
    cfg: QrelsStudioConfig,
    body: dict[str, Any],
    now_utc: str,
) -> dict[str, Any]:
    store = ExternalQrelsHumanStore(store_path=cfg.store_path, rubric_path=cfg.rubric_path)
    rec = store.append_grade(
        {
            "pair_id": str(body["pair_id"]),
            "query_id": str(body["query_id"]),
            "record_id": str(body["record_id"]),
            "surface": str(body.get("surface") or "candidate_graph"),
            "topic_family": str(body.get("topic_family") or ""),
            "partition": str(body.get("partition") or "dev"),
            "artifact_sha256": str(body["artifact_sha256"]),
            "relevance_grade": int(body["relevance_grade"]),
            "atomic_checks": body.get("atomic_checks") or {},
            "rejection_tags": body.get("rejection_tags") or [],
            "critique_rationale": str(body.get("critique_rationale") or body.get("notes") or ""),
            "annotator_id": cfg.annotator_id,
            "graded_at_utc": now_utc,
            "notes": str(body.get("notes") or ""),
        },
        require_grade0_rationale=True,
    )
    return {"status": "PASS", "record": rec.to_dict()}


def persist_qrels_quarantine_request(
    cfg: QrelsStudioConfig,
    body: dict[str, Any],
    now_utc: str,
) -> dict[str, Any]:
    store = ExternalQrelsHumanStore(store_path=cfg.store_path, rubric_path=cfg.rubric_path)
    q = store.append_quarantine(
        {
            "pair_id": str(body["pair_id"]),
            "query_id": str(body["query_id"]),
            "record_id": str(body["record_id"]),
            "surface": str(body.get("surface") or "candidate_graph"),
            "topic_family": str(body.get("topic_family") or ""),
            "partition": str(body.get("partition") or "dev"),
            "artifact_sha256": str(body["artifact_sha256"]),
            "reason": str(body["reason"]),
            "annotator_id": cfg.annotator_id,
            "recorded_at_utc": now_utc,
            "notes": str(body.get("notes") or ""),
        }
    )
    return {"status": "PASS", "quarantined": q.to_dict()}


class QrelsStudioHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send_bytes(self, raw: bytes, content_type: str, status: int = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        self._send_bytes(
            json.dumps(payload, sort_keys=True).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def do_GET(self) -> None:  # noqa: N802
        cfg: QrelsStudioConfig = self.server.studio_cfg  # type: ignore[attr-defined]
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            self._send_bytes(QRELS_STUDIO_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if route == "/api/state":
            self._send_json(build_qrels_studio_state_payload(cfg))
            return
        self._send_json({"status": "NOT_FOUND"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        cfg: QrelsStudioConfig = self.server.studio_cfg  # type: ignore[attr-defined]
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            length = int(self.headers.get("Content-Length") or "0")
            body = dict(json.loads(self.rfile.read(length).decode("utf-8")))
            if self.path == "/api/grade":
                self._send_json(persist_qrels_grade_request(cfg, body, now_utc))
                return
            if self.path == "/api/quarantine":
                self._send_json(persist_qrels_quarantine_request(cfg, body, now_utc))
                return
            self._send_json({"status": "NOT_FOUND"}, status=HTTPStatus.NOT_FOUND)
        except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
            self._send_json({"status": "FAIL", "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)


def create_qrels_studio_server(
    pool_path: Path,
    *,
    store_path: Path | None = None,
    rubric_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8767,
    annotator_id: str = "amit.ayer",
    seed: int | None = 42,
    max_items: int | None = None,
) -> QrelsStudioServer:
    """Create a configured Pure-White (#ffffff) Blind QRELS Calibration Studio HTTP server."""
    clean_annotator = validate_human_qrels_annotator_id(annotator_id)
    resolved_pool = Path(pool_path).resolve()
    if not resolved_pool.is_file():
        raise FileNotFoundError(f"QRELS candidate pool not found: '{resolved_pool}'.")
    repo_root = Path(__file__).resolve().parents[2]
    resolved_store = (
        Path(store_path).resolve()
        if store_path is not None
        else (repo_root / DEFAULT_QRELS_HUMAN_STORE_REL_PATH)
    )
    cfg = QrelsStudioConfig(
        pool_path=resolved_pool,
        store_path=resolved_store,
        rubric_path=Path(rubric_path).resolve() if rubric_path is not None else None,
        annotator_id=clean_annotator,
        seed=seed,
        max_items=max_items,
    )
    return QrelsStudioServer((host, int(port)), cfg)


__all__ = [
    "QrelsStudioConfig",
    "QrelsStudioHandler",
    "QrelsStudioServer",
    "build_qrels_studio_state_payload",
    "create_qrels_studio_server",
    "persist_qrels_grade_request",
    "persist_qrels_quarantine_request",
]
