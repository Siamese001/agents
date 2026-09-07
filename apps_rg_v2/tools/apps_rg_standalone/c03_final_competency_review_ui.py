"""Serve the final graph-competency review UI for Brown & Brown."""

from __future__ import annotations

import argparse
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.owner_solo.final_competency_review_ui import (  # noqa: E402
    FinalCompetencyReviewError,
    append_reviews,
    load_final_competencies,
    render_html,
    selected_rationale,
    unreviewed,
    write_restart_receipt,
    _read_jsonl,
)


def _handler(repo_root: Path, ledger: Path, batch_size: int):
    class Handler(BaseHTTPRequestHandler):
        def _page(self, status: HTTPStatus = HTTPStatus.OK, message: str = "") -> None:
            try:
                candidates = load_final_competencies(repo_root)
                remaining = unreviewed(candidates, _read_jsonl(ledger))
                body = render_html(remaining[:batch_size], completed=len(candidates) - len(remaining), total=len(candidates), message=message)
            except FinalCompetencyReviewError as exc:
                status, body = HTTPStatus.BAD_REQUEST, f"<h1>Review blocked</h1><p>{exc}</p>"
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            saved = parse_qs(urlsplit(self.path).query).get("saved") == ["1"]
            self._page(message="Your final-competency ratings were saved." if saved else "")

        def do_POST(self) -> None:  # noqa: N802
            try:
                form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or "0")).decode("utf-8"), keep_blank_values=True)
                candidates = load_final_competencies(repo_root)
                batch = unreviewed(candidates, _read_jsonl(ledger))[:batch_size]
                submissions = []
                for index, candidate in enumerate(batch, start=1):
                    grade = form.get(f"grade_{index}", [""])[0]
                    if grade not in {"0", "1", "2", "3"}:
                        raise FinalCompetencyReviewError("Every displayed competency needs a selected rating")
                    submissions.append({"bundle_id": candidate["bundle_id"], "grade": int(grade), "rationale": selected_rationale(form.get(f"reason_{index}", [""])[0], form.get(f"note_{index}", [""])[0])})
                append_reviews(ledger, candidates, submissions)
            except (FinalCompetencyReviewError, UnicodeDecodeError, ValueError) as exc:
                self._page(HTTPStatus.BAD_REQUEST, f"Nothing was saved: {exc}")
                return
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/?saved=1")
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, default=REPO_ROOT / ".runtime/c03-owner-solo-qrel/reconciliation")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--batch-size", type=int, default=6)
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 8:
        parser.error("--batch-size must be between 1 and 8")
    ledger = args.runtime_dir / "brown_brown_final_competency_projection_events.v1.jsonl"
    write_restart_receipt(args.runtime_dir / "brown_brown_competencies_w1_qrel_events.v1.jsonl", args.runtime_dir / "brown_brown_competencies_restart_receipt.v1.json")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _handler(REPO_ROOT, ledger, args.batch_size))
    print(f"Final competency review UI: http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
