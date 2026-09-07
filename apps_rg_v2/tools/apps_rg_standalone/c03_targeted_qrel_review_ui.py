"""Serve a local, blinded checkbox-style review UI for Brown & Brown W1."""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.owner_solo.targeted_qrel_review_ui import (  # noqa: E402
    TargetedReviewError,
    append_batch_judgments,
    load_brown_brown_competency_candidates,
    prior_confirmed_candidate_keys,
    render_batch_html,
    selected_rationale,
    ungraded_candidates,
    _read_jsonl,
)


def _handler(packet_dir: Path, ledger_path: Path, prior_link_ledger_path: Path, batch_size: int):
    class ReviewHandler(BaseHTTPRequestHandler):
        def _page(self, status: HTTPStatus = HTTPStatus.OK, message: str = "") -> None:
            try:
                candidates = load_brown_brown_competency_candidates(packet_dir)
                prior = prior_confirmed_candidate_keys(prior_link_ledger_path, candidates)
                ungraded = ungraded_candidates(candidates, _read_jsonl(ledger_path), precovered_keys=prior)
                body = render_batch_html(
                    ungraded[:batch_size], completed=len(candidates) - len(ungraded), total=len(candidates), message=message
                )
            except TargetedReviewError as exc:
                status, body = HTTPStatus.BAD_REQUEST, f"<h1>Review blocked</h1><p>{exc}</p>"
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            saved = parse_qs(urlsplit(self.path).query).get("saved") == ["1"]
            self._page(message="Your eight explicit grades and rationales were saved." if saved else "")

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length") or "0")
                form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
                candidates = load_brown_brown_competency_candidates(packet_dir)
                prior = prior_confirmed_candidate_keys(prior_link_ledger_path, candidates)
                ungraded = ungraded_candidates(candidates, _read_jsonl(ledger_path), precovered_keys=prior)[:batch_size]
                if not ungraded:
                    raise TargetedReviewError("There are no remaining cards in this target scope")
                submissions = []
                for position, candidate in enumerate(ungraded, start=1):
                    raw_grade = form.get(f"grade_{position}", [""])[0]
                    raw_reason = form.get(f"reason_{position}", [""])[0]
                    raw_note = form.get(f"note_{position}", [""])[0]
                    if raw_grade not in {"0", "1", "2", "3"}:
                        raise TargetedReviewError("Every displayed card must have a selected grade")
                    submissions.append({
                        **candidate,
                        "grade": int(raw_grade),
                        "rationale": selected_rationale(raw_reason, raw_note),
                    })
                append_batch_judgments(ledger_path, candidates, submissions, precovered_keys=prior)
            except (TargetedReviewError, UnicodeDecodeError, ValueError) as exc:
                self._page(HTTPStatus.BAD_REQUEST, f"Nothing was saved: {exc}")
                return
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/?saved=1")
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return ReviewHandler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, default=REPO_ROOT / ".runtime/c03-cluster-w8/prelabel_packet")
    parser.add_argument("--ledger", type=Path, default=REPO_ROOT / ".runtime/c03-owner-solo-qrel/reconciliation/brown_brown_competencies_w1_qrel_events.v1.jsonl")
    parser.add_argument("--prior-link-ledger", type=Path, default=REPO_ROOT / ".runtime/c03-owner-solo-qrel/reconciliation/brown_brown_competencies_link_events.v1.jsonl")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 10:
        parser.error("--batch-size must be between 1 and 10")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _handler(args.packet_dir, args.ledger, args.prior_link_ledger, args.batch_size))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Blinded local review UI: {url}")
    print("Press Ctrl+C when you are finished.")
    if not args.no_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
