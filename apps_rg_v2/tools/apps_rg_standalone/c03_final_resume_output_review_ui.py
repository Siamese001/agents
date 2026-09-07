"""Serve a local review UI for a source-bound completed final résumé output."""

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

from apps_rg.evals.owner_solo.final_resume_output_review import (  # noqa: E402
    FinalResumeOutputReviewError,
    REVIEW_UNIT_OUTPUT,
    REVIEW_UNIT_SECTION,
    _read_jsonl,
    append_reviews,
    load_final_resume_output_bundle,
    render_html,
    selected_rationale,
    unreviewed,
    write_progress_receipt,
)


def _ledger_path(runtime_dir: Path, bundle: dict[str, object]) -> Path:
    source = bundle["source"]
    assert isinstance(source, dict)
    review_unit = str(bundle["review_unit"])
    return runtime_dir / (
        f"final_resume_output_{review_unit}_events."
        f"{str(source['final_resume_sha256'])[:16]}.jsonl"
    )


def _handler(
    run_root: Path,
    runtime_dir: Path,
    batch_size: int,
    review_unit: str,
):
    class Handler(BaseHTTPRequestHandler):
        def _bundle(self) -> dict[str, object]:
            return load_final_resume_output_bundle(
                run_root,
                repo_root=REPO_ROOT,
                review_unit=review_unit,
            )

        def _page(self, status: HTTPStatus = HTTPStatus.OK, message: str = "") -> None:
            try:
                bundle = self._bundle()
                ledger = _ledger_path(runtime_dir, bundle)
                remaining = unreviewed(bundle, _read_jsonl(ledger))
                body = render_html(
                    bundle,
                    remaining[:batch_size],
                    completed=len(bundle["candidates"]) - len(remaining),
                    message=message,
                )
            except FinalResumeOutputReviewError as exc:
                status = HTTPStatus.BAD_REQUEST
                body = f"<h1>Review blocked</h1><p>{exc}</p>"
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            saved = parse_qs(urlsplit(self.path).query).get("saved") == ["1"]
            self._page(
                message="Your final-resume output ratings were saved." if saved else ""
            )

        def do_POST(self) -> None:  # noqa: N802
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length") or "0"))
                form = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
                bundle = self._bundle()
                ledger = _ledger_path(runtime_dir, bundle)
                batch = unreviewed(bundle, _read_jsonl(ledger))[:batch_size]
                if not batch:
                    raise FinalResumeOutputReviewError(
                        "There are no remaining final-output units in this frozen résumé"
                    )
                submissions = []
                for index, candidate in enumerate(batch, start=1):
                    raw_grade = form.get(f"grade_{index}", [""])[0]
                    if raw_grade not in {"0", "1", "2", "3"}:
                        raise FinalResumeOutputReviewError(
                            "Every displayed final-output unit needs a selected rating"
                        )
                    submissions.append(
                        {
                            "unit_ref": candidate["unit_ref"],
                            "grade": int(raw_grade),
                            "rationale": selected_rationale(
                                form.get(f"reason_{index}", [""])[0],
                                form.get(f"note_{index}", [""])[0],
                            ),
                        }
                    )
                append_reviews(ledger, bundle, submissions)
                source = bundle["source"]
                assert isinstance(source, dict)
                write_progress_receipt(
                    ledger,
                    bundle,
                    runtime_dir
                    / f"final_resume_output_progress.{str(source['final_resume_sha256'])[:16]}.json",
                )
            except (FinalResumeOutputReviewError, UnicodeDecodeError, ValueError) as exc:
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
    parser.add_argument(
        "--run-root",
        type=Path,
        required=True,
        help="Completed apps_rg full-resume run directory",
    )
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=REPO_ROOT / ".runtime/c03-owner-solo-final-output",
    )
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument(
        "--review-unit",
        choices=(REVIEW_UNIT_SECTION, REVIEW_UNIT_OUTPUT),
        default=REVIEW_UNIT_SECTION,
        help=(
            "Human review unit. 'section' is the default and shows the full "
            "rendered résumé section; 'output_unit' retains the legacy "
            "per-line view."
        ),
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Retained for local launch-script compatibility",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 8:
        parser.error("--batch-size must be between 1 and 8")
    try:
        bundle = load_final_resume_output_bundle(
            args.run_root,
            repo_root=REPO_ROOT,
            review_unit=args.review_unit,
        )
    except FinalResumeOutputReviewError as exc:
        parser.error(str(exc))
    ledger = _ledger_path(args.runtime_dir, bundle)
    source = bundle["source"]
    assert isinstance(source, dict)
    receipt = write_progress_receipt(
        ledger,
        bundle,
        args.runtime_dir
        / f"final_resume_output_progress.{str(source['final_resume_sha256'])[:16]}.json",
    )
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Final résumé output review UI: {url}")
    print(
        "status="
        f"{receipt['status']} completed={receipt['completed_final_output_units']} "
        f"total={receipt['total_final_output_units']} review_unit={args.review_unit}"
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        _handler(args.run_root, args.runtime_dir, args.batch_size, args.review_unit),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
