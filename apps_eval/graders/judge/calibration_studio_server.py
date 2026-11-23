"""Governed Pure-White (#ffffff) Click-to-Grade Blind Human Calibration Studio Server (DIE Parity).

Serves `judge-calibrate-ui` on a crisp pure-white (`#ffffff`) daylight surface
incorporating strictly 2025-2026 frontier human-calibration standards (Google Cloud
`grounding_v2` & Adaptive Rubrics, Anthropic Demystifying Evals, OpenAI HealthBench).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any

from apps_eval.graders.judge.calibration_studio_template import STUDIO_HTML
from apps_eval.graders.judge.external_rubric_store import (
    DEFAULT_HUMAN_GOLD_STORE_REL_PATH,
    EXTERNAL_RUBRIC_DIMENSIONS,
    ExternalRubricHumanStore,
    load_and_verify_external_rubric,
    validate_human_annotator_id,
)
from apps_eval.graders.judge.frontier_rubric_contract import (
    ATOMIC_RUBRIC_CHECKS,
    FAILURE_TAXONOMY_TAGS,
    shuffle_pool_items_seeded,
)


@dataclass(frozen=True)
class StudioConfig:
    pool_path: Path
    store_path: Path
    rubric_path: Path | None
    annotator_id: str
    seed: int | None


class CalibrationStudioServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], studio_cfg: StudioConfig) -> None:
        self.studio_cfg = studio_cfg
        super().__init__(server_address, CalibrationStudioHandler)


def _build_state_payload(cfg: StudioConfig) -> dict[str, Any]:
    rubric = load_and_verify_external_rubric(cfg.rubric_path)
    pool = json.loads(cfg.pool_path.read_text(encoding="utf-8"))
    items = shuffle_pool_items_seeded(pool.get("items", []), cfg.seed)
    store = ExternalRubricHumanStore(store_path=cfg.store_path, rubric_path=cfg.rubric_path)
    return {
        "status": "PASS",
        "partition": pool.get("partition", "dev"),
        "judge_surface": pool.get("judge_surface", "resume_engine"),
        "presentation_seed": cfg.seed if cfg.seed is not None else pool.get("presentation_seed"),
        "deduplication_stats": pool.get("deduplication_stats", {}),
        "items": items,
        "rubric": rubric,
        "atomic_checks": list(ATOMIC_RUBRIC_CHECKS),
        "failure_tags": list(FAILURE_TAXONOMY_TAGS),
        "savedByCase": {r.case_id: r.to_dict() for r in store.load_records()},
        "quarantinedByCase": {q.case_id: q.to_dict() for q in store.load_quarantined()},
        "store_path": str(cfg.store_path),
    }


def _persist_grade_request(cfg: StudioConfig, body: dict[str, Any], now_utc: str) -> dict[str, Any]:
    store = ExternalRubricHumanStore(store_path=cfg.store_path, rubric_path=cfg.rubric_path)
    rec = store.append_label(
        {
            "case_id": str(body["case_id"]),
            "judge_surface": str(body["judge_surface"]),
            "topic_family": str(body["topic_family"]),
            "partition": str(body["partition"]),
            "artifact_sha256": str(body["artifact_sha256"]),
            "external_rubric_id": "external_judge_rubric_v1",
            "external_rubric_sha256": store.rubric_sha256,
            "dimension_grades": {k: int(body["dimension_grades"][k]) for k in EXTERNAL_RUBRIC_DIMENSIONS},
            "atomic_checks": body.get("atomic_checks") or {},
            "failure_tags": body.get("failure_tags") or [],
            "critique_rationale": str(body.get("critique_rationale") or body.get("notes") or ""),
            "evidence_context_sha256": str(body.get("evidence_context_sha256") or ""),
            "human_verdict": str(body["human_verdict"]).upper(),
            "annotator_id": cfg.annotator_id,
            "graded_at_utc": now_utc,
            "notes": str(body.get("notes") or ""),
        },
        candidate_text=str(body.get("blinded_text") or "") if not body.get("artifact_sha256") else None,
        require_fail_critique=True,
    )
    return {"status": "PASS", "record": rec.to_dict()}


def _persist_quarantine_request(cfg: StudioConfig, body: dict[str, Any], now_utc: str) -> dict[str, Any]:
    store = ExternalRubricHumanStore(store_path=cfg.store_path, rubric_path=cfg.rubric_path)
    q_rec = store.append_quarantine(
        {
            "case_id": str(body["case_id"]),
            "judge_surface": str(body["judge_surface"]),
            "topic_family": str(body["topic_family"]),
            "partition": str(body["partition"]),
            "artifact_sha256": str(body["artifact_sha256"]),
            "reason": str(body["reason"]),
            "annotator_id": cfg.annotator_id,
            "recorded_at_utc": now_utc,
            "notes": str(body.get("notes") or ""),
        }
    )
    return {"status": "PASS", "quarantined": q_rec.to_dict()}


class CalibrationStudioHandler(BaseHTTPRequestHandler):
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

    def do_GET(self) -> None:
        cfg: StudioConfig = self.server.studio_cfg  # type: ignore[attr-defined]
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            self._send_bytes(STUDIO_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if route == "/api/state":
            self._send_json(_build_state_payload(cfg))
            return
        self._send_json({"status": "NOT_FOUND"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        cfg: StudioConfig = self.server.studio_cfg  # type: ignore[attr-defined]
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            length = int(self.headers.get("Content-Length") or "0")
            body = dict(json.loads(self.rfile.read(length).decode("utf-8")))
            if self.path == "/api/grade":
                self._send_json(_persist_grade_request(cfg, body, now_utc))
                return
            if self.path == "/api/quarantine":
                self._send_json(_persist_quarantine_request(cfg, body, now_utc))
                return
            self._send_json({"status": "NOT_FOUND"}, status=HTTPStatus.NOT_FOUND)
        except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
            self._send_json({"status": "FAIL", "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)


def create_calibration_studio_server(
    pool_path: Path,
    *,
    store_path: Path | None = None,
    rubric_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    annotator_id: str = "amit.ayer",
    seed: int | None = None,
) -> CalibrationStudioServer:
    """Create a configured pure-white (#ffffff) Blind Calibration Studio HTTP server."""
    clean_annotator = validate_human_annotator_id(annotator_id)
    resolved_pool = Path(pool_path).resolve()
    if not resolved_pool.is_file():
        raise FileNotFoundError(f"Blind calibration pool file not found: '{resolved_pool}'.")
    repo_root = Path(__file__).resolve().parents[3]
    resolved_store = (
        Path(store_path).resolve()
        if store_path
        else (repo_root / DEFAULT_HUMAN_GOLD_STORE_REL_PATH)
    )
    cfg = StudioConfig(resolved_pool, resolved_store, rubric_path, clean_annotator, seed)
    return CalibrationStudioServer((host, int(port)), cfg)


def handle_judge_calibrate_ui(args: argparse.Namespace) -> dict[str, Any]:
    """CLI handler for `judge-calibrate-ui` serving the pure-white (#ffffff) Studio."""
    server = create_calibration_studio_server(
        args.pool,
        store_path=getattr(args, "store_path", None),
        rubric_path=getattr(args, "rubric_path", None),
        host=str(getattr(args, "host", "127.0.0.1")),
        port=int(getattr(args, "port", 8765)),
        annotator_id=str(getattr(args, "annotator", "amit.ayer")),
        seed=getattr(args, "seed", None),
    )
    bound_host, bound_port = server.server_address[:2]
    print(
        f"Blind Human Calibration Studio (white #ffffff) listening on http://{bound_host}:{bound_port}",
        flush=True,
    )
    if bool(getattr(args, "check_only", False)):
        server.server_close()
        return {
            "status": "PASS",
            "command": "judge-calibrate-ui",
            "url": f"http://{bound_host}:{bound_port}",
        }
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return {"status": "PASS", "command": "judge-calibrate-ui"}


__all__ = [
    "CalibrationStudioHandler",
    "CalibrationStudioServer",
    "StudioConfig",
    "create_calibration_studio_server",
    "handle_judge_calibrate_ui",
]
