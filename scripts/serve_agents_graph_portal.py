#!/usr/bin/env python3
"""Live Local Knowledge Graph Explorer Portal Server for the agents repository.

Mirrors the Decision Intelligence Engine (DIE) Knowledge Graph Portal Server
(``serve_explorer_portal.py``) with live SQLite/template hot-reload, REST slice
APIs (``/api/v1/bootstrap``, ``/api/v1/lens/<scope>``, ``/api/v1/node/<id>``,
``/api/v1/search``), and health endpoint (``/healthz``).
"""

from __future__ import annotations

import argparse
import http.server
import json
import logging
import socketserver
import sqlite3
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.interactive_graph_export_core.dataset_builder import (
    DEFAULT_TEMPLATE_PATH,
    build_agents_explorer_dataset,
    compute_multihop_subgraph,
    filter_bundle_lens,
    render_portal_shell_html,
    resolve_default_graph_db_path,
    search_bundle_nodes,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PortalSnapshot:
    """Immutable snapshot of the hydrated graph dataset and its source mtime signature."""

    bundle: dict[str, Any]
    node_by_id: dict[str, dict[str, Any]]
    db_path: Path
    source_sig: tuple[int, int, int]
    template_mtime: int


def _compute_source_signature(db_path: Path) -> tuple[int, int, int]:
    st = db_path.stat()
    wal = db_path.with_name(db_path.name + "-wal")
    wal_mtime = wal.stat().st_mtime_ns if wal.is_file() else 0
    return (st.st_mtime_ns, st.st_size, wal_mtime)


class AgentsGraphPortalState:
    """Thread-safe in-memory graph bundle with automatic SQLite/template staleness reload."""

    def __init__(
        self,
        db_path: Path,
        *,
        template_path: Path = DEFAULT_TEMPLATE_PATH,
    ) -> None:
        self._lock = threading.RLock()
        self.db_path = db_path.resolve()
        self.template_path = template_path.resolve()
        self._snapshot = self._load_snapshot()

    def _load_snapshot(self) -> PortalSnapshot:
        sig = _compute_source_signature(self.db_path)
        tpl_mtime = self.template_path.stat().st_mtime_ns
        bundle = build_agents_explorer_dataset(self.db_path)
        node_by_id = {str(n["id"]): n for n in bundle.get("nodes", [])}
        return PortalSnapshot(
            bundle=bundle,
            node_by_id=node_by_id,
            db_path=self.db_path,
            source_sig=sig,
            template_mtime=tpl_mtime,
        )

    def get_snapshot(self) -> PortalSnapshot:
        with self._lock:
            try:
                cur_sig = _compute_source_signature(self.db_path)
                cur_tpl = self.template_path.stat().st_mtime_ns
                if cur_sig != self._snapshot.source_sig or cur_tpl != self._snapshot.template_mtime:
                    self._snapshot = self._load_snapshot()
            except (OSError, sqlite3.Error, ValueError) as exc:
                _LOGGER.warning("Portal reload skipped due to transient read error: %s", exc)
            return self._snapshot


class AgentsGraphRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler serving the 6-workspace explorer shell and live JSON graph APIs."""

    portal_state: AgentsGraphPortalState

    def _send_bytes(
        self,
        status: int,
        content_type: str,
        body: bytes,
        *,
        head_only: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, private")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _send_json(self, status: int, payload: Any, *, head_only: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", body, head_only=head_only)

    def _handle_request(self, *, head_only: bool) -> None:
        parsed = urlparse(self.path)
        clean_path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        snap = self.portal_state.get_snapshot()

        if clean_path == "/healthz":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "repo": "agents",
                    "total_nodes": snap.bundle.get("total_nodes", 0),
                    "total_edges": snap.bundle.get("total_edges", 0),
                    "generation_id": snap.bundle.get("generation_id", ""),
                },
                head_only=head_only,
            )
            return

        if clean_path in ("/", "/graph", "/explorer", "/portal"):
            default_mode = "graph" if clean_path in ("/", "/graph") else "opmodel"
            shell_html = render_portal_shell_html(
                snap.bundle,
                bootstrap_endpoint="/api/v1/bootstrap",
                template_path=self.portal_state.template_path,
                default_mode=default_mode,
            ).encode("utf-8")
            self._send_bytes(200, "text/html; charset=utf-8", shell_html, head_only=head_only)
            return

        if clean_path == "/api/v1/bootstrap":
            self._send_json(200, snap.bundle, head_only=head_only)
            return

        if clean_path.startswith("/api/v1/lens/"):
            lens_id = unquote(clean_path.split("/api/v1/lens/", 1)[1])
            self._send_json(200, filter_bundle_lens(snap.bundle, lens_id), head_only=head_only)
            return

        if clean_path.startswith("/api/v1/node/"):
            node_id = unquote(clean_path.split("/api/v1/node/", 1)[1])
            node_obj = snap.node_by_id.get(node_id)
            if node_obj is None:
                self._send_json(404, {"error": "Node not found", "node_id": node_id}, head_only=head_only)
                return
            raw_hops = (query.get("hops") or ["1"])[0]
            try:
                hops = int(raw_hops)
            except ValueError:
                hops = 1
            sub = compute_multihop_subgraph(snap.bundle, node_id, hops=max(1, min(3, hops)))
            self._send_json(200, {"node": node_obj, **sub}, head_only=head_only)
            return

        if clean_path == "/api/v1/search":
            q = (query.get("q") or [""])[0]
            self._send_json(200, search_bundle_nodes(snap.bundle, q), head_only=head_only)
            return

        self._send_json(404, {"error": "Not found", "path": clean_path}, head_only=head_only)

    def do_HEAD(self) -> None:
        self._handle_request(head_only=True)

    def do_GET(self) -> None:
        self._handle_request(head_only=False)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        clean_path = parsed.path.rstrip("/")
        if clean_path != "/api/v1/telemetry":
            self._send_json(403, {"error": "Forbidden"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(400, {"error": "Invalid Content-Length"})
            return
        if 0 < length <= 65536:
            self.rfile.read(min(length, 2048))
        self._send_bytes(204, "text/plain; charset=utf-8", b"")

    def log_message(self, format: str, *args: Any) -> None:
        pass


class ReusableThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def create_agents_graph_portal_server(
    *,
    db_path: Path | str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
) -> ReusableThreadingHTTPServer:
    """Create a configured threaded HTTP portal server bound to the live SQLite skills graph."""
    resolved_db = Path(db_path).resolve() if db_path else resolve_default_graph_db_path(ROOT)
    state = AgentsGraphPortalState(resolved_db, template_path=template_path)

    class BoundHandler(AgentsGraphRequestHandler):
        portal_state = state

    return ReusableThreadingHTTPServer((host, port), BoundHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the Agents Repo Interactive Knowledge Graph Explorer Portal"
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db-path", default=None, help="Explicit path to augmented_skills_graph.sqlite")
    args = parser.parse_args(argv)

    server = create_agents_graph_portal_server(
        db_path=args.db_path,
        host=args.host,
        port=args.port,
    )
    bound_host, bound_port = server.server_address[:2]
    print(
        json.dumps(
            {
                "status": "listening",
                "url": f"http://{bound_host}:{bound_port}/graph",
                "architecture_url": f"http://{bound_host}:{bound_port}/explorer",
                "healthz": f"http://{bound_host}:{bound_port}/healthz",
                "bootstrap": f"http://{bound_host}:{bound_port}/api/v1/bootstrap",
            },
            indent=2,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
