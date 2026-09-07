"""Serve the blinded rendered-unit BGE-M3 QREL review UI locally."""

from __future__ import annotations

import argparse
import html
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.owner_solo.c03_rendered_unit_qrel import (  # noqa: E402
    RenderedUnitQrelError, _active_events, _read_jsonl, append_human_judgments,
    build_blinded_packet, load_contract, resolved_active_events, validate_registry,
)

REASONS = ("Direct and strong fit", "Relevant but supporting", "Weak, generic, or misplaced", "Not useful for this target section")


def _load(registry_path: Path, packet_path: Path | None = None):
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    contract = load_contract(REPO_ROOT)
    issues = validate_registry(registry, contract)
    if issues:
        raise RenderedUnitQrelError("Registry is blocked: " + ", ".join(issues))
    if packet_path:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        # The frozen packet is intentionally reviewer-visible only.  Its digest
        # and schema are checked here; the rank map stays outside the UI.
        unsigned = {key: value for key, value in packet.items() if key != "packet_sha256"}
        if packet.get("status") != "FROZEN_FOR_BLINDED_OWNER_QREL_REVIEW" or packet.get("packet_sha256") != __import__("hashlib").sha256(json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest():
            raise RenderedUnitQrelError("Frozen reviewer packet is malformed")
        return packet, None
    return build_blinded_packet(registry, contract)


def _target_label(target_context):
    lines = [line.strip() for line in str(target_context or "").splitlines() if line.strip()]
    if lines and lines[0].casefold() == "target job description:":
        lines = lines[1:]
    if not lines:
        return "Target résumé"
    title = lines[0]
    known_companies = ("Anthropic", "OpenAI", "Truist", "Neo4j", "AVEVA", "Brown & Brown")
    if any(company.casefold() in title.casefold() for company in known_companies):
        return title
    second = lines[1] if len(lines) > 1 else ""
    if second and len(second) <= 60 and not second.casefold().startswith(("about ", "location", "remote ", "the ")):
        return f"{second} — {title}"
    context = str(target_context or "")
    company = next((value for value in known_companies if value.casefold() in context.casefold()), "")
    return f"{company} — {title}" if company else title


def _flat(packet, active):
    return [
        {"item_ref": item["item_ref"], "candidate_ref": candidate["candidate_ref"], "target_context": item["target_context"], "target_label": _target_label(item["target_context"]), "resume_section": item["resume_section"], "text": candidate["complete_rendered_resume_unit"]}
        for item in packet["items"] for candidate in item["candidates"]
        if (item["item_ref"], candidate["candidate_ref"]) not in active
    ]


def _active_for_review(packet, events, args):
    if not any((args.transition, args.predecessor_packet, args.predecessor_ledger)):
        return _active_events(events, packet=packet)
    if not all((args.transition, args.predecessor_packet, args.predecessor_ledger)):
        raise RenderedUnitQrelError("Successor review requires --transition, --predecessor-packet, and --predecessor-ledger together")
    transition = json.loads(args.transition.read_text(encoding="utf-8"))
    predecessor_packet = json.loads(args.predecessor_packet.read_text(encoding="utf-8"))
    predecessor_events = _read_jsonl(args.predecessor_ledger)
    predecessor_active = None
    chain_args = (args.predecessor_transition, args.ancestor_packet, args.ancestor_ledger)
    if any(chain_args):
        if not all(chain_args):
            raise RenderedUnitQrelError("A predecessor chain requires --predecessor-transition --ancestor-packet and --ancestor-ledger together")
        ancestor_packet = json.loads(args.ancestor_packet.read_text(encoding="utf-8"))
        ancestor_events = _read_jsonl(args.ancestor_ledger)
        ancestor_active = None
        root_args = (args.ancestor_transition, args.root_packet, args.root_ledger)
        if any(root_args):
            if not all(root_args):
                raise RenderedUnitQrelError("A root chain requires --ancestor-transition --root-packet and --root-ledger together")
            ancestor_active = resolved_active_events(
                successor_packet=ancestor_packet,
                successor_events=ancestor_events,
                transition=json.loads(args.ancestor_transition.read_text(encoding="utf-8")),
                predecessor_packet=json.loads(args.root_packet.read_text(encoding="utf-8")),
                predecessor_events=_read_jsonl(args.root_ledger),
            )
        predecessor_active = resolved_active_events(
            successor_packet=predecessor_packet,
            successor_events=predecessor_events,
            transition=json.loads(args.predecessor_transition.read_text(encoding="utf-8")),
            predecessor_packet=ancestor_packet,
            predecessor_events=ancestor_events,
            predecessor_active_events=ancestor_active,
        )
    return resolved_active_events(
        successor_packet=packet,
        successor_events=events,
        transition=transition,
        predecessor_packet=predecessor_packet,
        predecessor_events=predecessor_events,
        predecessor_active_events=predecessor_active,
    )


def _page(batch, completed, total, message=""):
    cards = []
    for index, row in enumerate(batch, 1):
        grades = "".join(f'<label><input required type="radio" name="grade_{index}" value="{grade}"><b>{grade}</b></label>' for grade in range(4))
        reasons = "".join(f'<label><input required type="radio" name="reason_{index}" value="{html.escape(reason, quote=True)}">{html.escape(reason)}</label>' for reason in REASONS)
        is_competency = row["resume_section"] == "competencies"
        unit_label = "Complete résumé competency — category and every term are one unit" if is_competency else "Complete final résumé unit"
        question = "How well does this complete competency fit the target role's Competencies section?" if is_competency else "How useful is this complete résumé unit for the target and section?"
        cards.append(f'''<article><h2>{html.escape(row["target_label"])}</h2><p class="section">Résumé section: {html.escape(row["resume_section"])}</p><details><summary>Full target job context</summary><pre>{html.escape(row["target_context"])}</pre></details><p class="label">{html.escape(unit_label)}</p><div class="unit">{html.escape(row["text"])}</div><fieldset><legend>{html.escape(question)}</legend>{grades}</fieldset><fieldset><legend>Why did you choose that grade?</legend>{reasons}</fieldset><textarea name="note_{index}" placeholder="Optional note" maxlength="1000"></textarea><input type="hidden" name="item_{index}" value="{row["item_ref"]}"><input type="hidden" name="candidate_{index}" value="{row["candidate_ref"]}"></article>''')
    notice = f'<p class="notice">{html.escape(message)}</p>' if message else ""
    return f'''<!doctype html><meta charset="utf-8"><title>Final résumé QREL review</title><style>body{{font:16px system-ui;max-width:1050px;margin:auto;padding:22px;background:#f5f7fb}}article{{background:#fff;border:1px solid #ccd5e3;border-radius:10px;margin:16px 0;padding:18px}}pre,.unit{{white-space:pre-wrap;line-height:1.5}}.unit{{font-size:1.1em}}.section{{font-weight:bold;color:#334155}}fieldset{{border:0;margin:16px 0;display:flex;gap:12px;flex-wrap:wrap}}label{{padding:6px;border:1px solid #cbd5e1;border-radius:6px}}textarea{{display:block;width:100%;box-sizing:border-box}}button{{padding:12px 20px;background:#1264a3;color:white;border:0;border-radius:7px;font-weight:bold}}.label{{font-size:.85em;font-weight:bold;color:#475569}}.notice{{background:#dff5e7;padding:10px}}</style><h1>Final résumé output review</h1><p><strong>What to compare:</strong> compare the named target job with the complete résumé line shown on each card. For competencies, the category label and every phrase after the colon are one finished competency. Each unique competency appears only once per target résumé.</p><p>Completed: {completed} of {total}. Rank, score, split, graph IDs, and embedding details are hidden.</p>{notice}<form method="post">{''.join(cards)}{'<button>Save this batch</button>' if batch else '<p>All candidates are graded.</p>'}</form>'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--packet", type=Path, help="R3 frozen reviewer-visible packet")
    parser.add_argument("--transition", type=Path, help="Optional R4 corrected-packet transition")
    parser.add_argument("--predecessor-packet", type=Path)
    parser.add_argument("--predecessor-ledger", type=Path)
    parser.add_argument("--predecessor-transition", type=Path)
    parser.add_argument("--ancestor-packet", type=Path)
    parser.add_argument("--ancestor-ledger", type=Path)
    parser.add_argument("--ancestor-transition", type=Path)
    parser.add_argument("--root-packet", type=Path)
    parser.add_argument("--root-ledger", type=Path)
    parser.add_argument("--ledger", type=Path, default=REPO_ROOT / ".runtime/c03-rendered-unit-qrel/owner_events.jsonl")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--batch-size", type=int, default=6)
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 10: parser.error("--batch-size must be 1..10")
    try: packet, _sealed = _load(args.registry, args.packet)
    except (OSError, json.JSONDecodeError, RenderedUnitQrelError) as exc: parser.error(str(exc))
    class Handler(BaseHTTPRequestHandler):
        def page(self, status=HTTPStatus.OK, message=""):
            try:
                packet, _ = _load(args.registry, args.packet); events = _read_jsonl(args.ledger) if args.ledger.exists() else []
                active = _active_for_review(packet, events, args)
                remaining = _flat(packet, active); body = _page(remaining[:args.batch_size], len(active), sum(len(i["candidates"]) for i in packet["items"]), message)
            except (OSError, json.JSONDecodeError, RenderedUnitQrelError) as exc: status, body = HTTPStatus.BAD_REQUEST, f"<h1>Blocked</h1><p>{html.escape(str(exc))}</p>"
            raw = body.encode(); self.send_response(status); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_GET(self): self.page(message="Saved." if parse_qs(urlsplit(self.path).query).get("saved") else "")
        def do_POST(self):
            try:
                form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode(), keep_blank_values=True); packet, _ = _load(args.registry, args.packet); events = _read_jsonl(args.ledger) if args.ledger.exists() else []; batch = _flat(packet, _active_for_review(packet, events, args))[:args.batch_size]; submissions=[]
                for index, _row in enumerate(batch, 1):
                    grade=form.get(f"grade_{index}",[""])[0]; rationale=form.get(f"reason_{index}",[""])[0]; note=form.get(f"note_{index}",[""])[0].strip()
                    if grade not in {"0","1","2","3"} or not rationale: raise RenderedUnitQrelError("Every displayed unit needs an explicit grade and rationale")
                    submissions.append({"item_ref":form.get(f"item_{index}",[""])[0],"candidate_ref":form.get(f"candidate_{index}",[""])[0],"grade":int(grade),"rationale":rationale if not note else rationale+"\nHuman note: "+note})
                append_human_judgments(args.ledger, packet=packet, submissions=submissions); self.send_response(HTTPStatus.SEE_OTHER); self.send_header("Location","/?saved=1"); self.end_headers()
            except (UnicodeDecodeError, OSError, json.JSONDecodeError, RenderedUnitQrelError) as exc: self.page(HTTPStatus.BAD_REQUEST, "Nothing saved: "+str(exc))
        def log_message(self, *_): pass
    print(f"Rendered-unit QREL UI: http://127.0.0.1:{args.port}/")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__": main()
