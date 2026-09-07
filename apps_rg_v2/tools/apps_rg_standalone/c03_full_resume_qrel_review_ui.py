"""Serve the W3 blinded full-resume owner QREL review UI on localhost."""

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

from apps_rg.evals.owner_solo.c03_full_resume_qrel_review_ui import (  # noqa: E402
    FullResumeQrelReviewError,
    append_batch_judgments,
    load_blinded_review_packet,
    render_batch_html,
    selected_rationale,
    ungraded_candidates,
    _read_jsonl,
)
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w3 import (  # noqa: E402
    DEFAULT_PACKET_DIR,
)


def _handler(packet_dir: Path, ledger_path: Path, batch_size: int):
    class ReviewHandler(BaseHTTPRequestHandler):
        def _page(self, status: HTTPStatus = HTTPStatus.OK, message: str = "") -> None:
            try:
                packet = load_blinded_review_packet(packet_dir)
                remaining = ungraded_candidates(
                    packet["candidates"],
                    _read_jsonl(ledger_path),
                    packet_manifest_sha256=packet["packet_manifest_sha256"],
                )
                body = render_batch_html(
                    remaining[:batch_size],
                    completed=len(packet["candidates"]) - len(remaining),
                    total=len(packet["candidates"]),
                    message=message,
                )
            except FullResumeQrelReviewError as exc:
                status = HTTPStatus.BAD_REQUEST
                body = f"<h1>Review paused</h1><p>{exc}</p>"
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            saved = parse_qs(urlsplit(self.path).query).get("saved") == ["1"]
            self._page(
                message="Your explicit grades and rationales were saved."
                if saved
                else ""
            )

        def do_POST(self) -> None:  # noqa: N802
            try:
                raw_length = int(self.headers.get("Content-Length") or "0")
                form = parse_qs(
                    self.rfile.read(raw_length).decode("utf-8"), keep_blank_values=True
                )
                packet = load_blinded_review_packet(packet_dir)
                remaining = ungraded_candidates(
                    packet["candidates"],
                    _read_jsonl(ledger_path),
                    packet_manifest_sha256=packet["packet_manifest_sha256"],
                )
                batch = remaining[:batch_size]
                if not batch:
                    raise FullResumeQrelReviewError(
                        "There are no remaining evidence items in this packet"
                    )
                submissions = []
                for position, candidate in enumerate(batch, 1):
                    raw_grade = form.get(f"grade_{position}", [""])[0]
                    if raw_grade not in {"0", "1", "2", "3"}:
                        raise FullResumeQrelReviewError(
                            "Every displayed evidence item needs a selected grade"
                        )
                    submissions.append(
                        {
                            "item_ref": candidate["item_ref"],
                            "candidate_ref": candidate["candidate_ref"],
                            "grade": int(raw_grade),
                            "rationale": selected_rationale(
                                form.get(f"reason_{position}", [""])[0],
                                form.get(f"note_{position}", [""])[0],
                            ),
                        }
                    )
                append_batch_judgments(
                    ledger_path,
                    packet["candidates"],
                    submissions,
                    packet_manifest_sha256=packet["packet_manifest_sha256"],
                )
            except (FullResumeQrelReviewError, UnicodeDecodeError, ValueError) as exc:
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
    parser.add_argument("--packet-dir", type=Path, default=REPO_ROOT / DEFAULT_PACKET_DIR)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=REPO_ROOT
        / ".runtime/c03-owner-solo-qrel/w3/owner_solo_full_resume_qrel_events.v1.jsonl",
    )
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 12:
        parser.error("--batch-size must be between 1 and 12")
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        _handler(args.packet_dir, args.ledger, args.batch_size),
    )
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Blinded full-resume owner review UI: {url}")
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
