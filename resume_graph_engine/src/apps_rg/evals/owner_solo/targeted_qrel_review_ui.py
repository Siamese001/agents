"""Local, blinded browser UI for a narrowly scoped owner review batch.

This helper is intentionally *not* the authoritative W9 intake lane and it
does not create a finalized QREL artifact.  It exists to make a human's
targeted, append-only calibration review practical while preserving the W8
reviewer-A blinding boundary.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


TARGET_SCOPE = "BROWN_BROWN_COMPETENCIES"
EVENT_SCHEMA_VERSION = "apps_rg.owner_solo_targeted_qrel_event.v1"
OWNER_IDENTITY = "human-reviewer://amit-owner"
ALLOWED_GRADES = {0, 1, 2, 3}
RATIONALE_OPTIONS = (
    "Direct evidence for this role and section",
    "Relevant, but supporting rather than central",
    "Only contextual or transferable",
    "Generic; does not distinguish this candidate",
    "Wrong role, industry, or resume section",
    "Not useful or not supported",
)


class TargetedReviewError(ValueError):
    """Raised when a local targeted-review input fails closed."""


def canonical_sha256(value: Mapping[str, Any]) -> str:
    """Return the repository's stable JSON digest form."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    try:
        return [json.loads(line) for line in lines if line.strip()]
    except json.JSONDecodeError as exc:
        raise TargetedReviewError(f"Malformed append-only review ledger: {path}") from exc


def prior_confirmed_candidate_keys(
    link_ledger_path: Path, candidates: Sequence[Mapping[str, str]]
) -> set[tuple[str, str]]:
    """Accept only an explicit owner confirmation of an existing human label."""
    allowed_by_candidate = {candidate["candidate_ref"]: candidate["item_ref"] for candidate in candidates}
    confirmed: set[tuple[str, str]] = set()
    for index, event in enumerate(_read_jsonl(link_ledger_path), start=1):
        unsigned = {key: value for key, value in event.items() if key != "event_digest"}
        candidate_ref = str((event.get("frozen_candidate") or {}).get("candidate_ref") or "")
        prior_label = event.get("prior_label") or {}
        if (
            event.get("schema_version") != "apps_rg.owner_solo_prior_label_link_event.v1"
            or event.get("event_type") != "OWNER_CONFIRMED_SAME_UNDERLYING_EVIDENCE"
            or event.get("owner_identity_ref") != OWNER_IDENTITY
            or event.get("grade_reused_verbatim") is not True
            or event.get("qrel_created") is not False
            or prior_label.get("grade") not in ALLOWED_GRADES
            or not str(prior_label.get("rationale") or "").strip()
            or event.get("event_digest") != canonical_sha256(unsigned)
            or candidate_ref not in allowed_by_candidate
        ):
            raise TargetedReviewError(f"Prior-label link event {index} is invalid")
        key = (allowed_by_candidate[candidate_ref], candidate_ref)
        if key in confirmed:
            raise TargetedReviewError(f"Prior-label link event {index} duplicates a candidate")
        confirmed.add(key)
    return confirmed


def _cluster_fields(text: str) -> tuple[str, str, str]:
    """Extract existing reviewer-visible text without adding interpretation."""
    def value(name: str, next_name: str | None) -> str:
        ending = rf"(?= {re.escape(next_name)}:|$)" if next_name else "$"
        match = re.search(rf"{re.escape(name)}: (.*?){ending}", text, re.DOTALL)
        return " ".join(match.group(1).split()) if match else ""

    return value("Action", "Scope"), value("Scope", "Outcome"), value("Evidence", None)


def load_brown_brown_competency_candidates(packet_dir: Path) -> list[dict[str, str]]:
    """Load only reviewer-A text; use the sealed map solely to constrain scope."""
    reviewer_items_path = packet_dir / "reviewer_a" / "review_items.jsonl"
    mapping_path = packet_dir / "sealed_internal" / "identity_and_rank_mapping.v1.json"
    reviewer_items = _read_jsonl(reviewer_items_path)
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise TargetedReviewError("Required sealed mapping is missing or malformed") from exc

    allowed: set[tuple[str, str]] = set()
    for item in ((mapping.get("cohorts") or {}).get("reviewer_a") or []):
        if item.get("query_id") == "insurance_brown" and item.get("section_id") == "competencies":
            allowed.update(
                (str(item.get("item_ref") or ""), str(candidate.get("candidate_ref") or ""))
                for candidate in item.get("candidates") or []
            )
    if len(allowed) != 22:
        raise TargetedReviewError("Brown & Brown competency scope must contain exactly 22 candidates")

    candidates: list[dict[str, str]] = []
    for item in reviewer_items:
        for candidate in item.get("candidates") or []:
            key = (str(item.get("item_ref") or ""), str(candidate.get("candidate_ref") or ""))
            if key not in allowed:
                continue
            text = str(candidate.get("evidence_cluster_text") or "")
            action, scope, evidence = _cluster_fields(text)
            if not text or not action or not evidence:
                raise TargetedReviewError("A reviewer-A evidence card is incomplete")
            candidates.append(
                {
                    "item_ref": key[0],
                    "candidate_ref": key[1],
                    "evidence_cluster_text": text,
                    "action": action,
                    "scope": scope,
                    "evidence": evidence,
                }
            )
    if len(candidates) != len(allowed):
        raise TargetedReviewError("Reviewer-A/sealed-scope conservation failed")
    return candidates


def active_judgments(events: Sequence[Mapping[str, Any]], allowed_keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Validate the targeted append-only correction chain and materialize active rows."""
    active: dict[tuple[str, str], dict[str, Any]] = {}
    for index, event in enumerate(events, start=1):
        unsigned = {key: value for key, value in event.items() if key != "event_digest"}
        if event.get("event_digest") != canonical_sha256(unsigned):
            raise TargetedReviewError(f"Ledger event {index} has an invalid digest")
        key = (str(event.get("item_ref") or ""), str(event.get("candidate_ref") or ""))
        grade = event.get("relevance_grade")
        if (
            event.get("schema_version") != EVENT_SCHEMA_VERSION
            or key not in allowed_keys
            or grade not in ALLOWED_GRADES
            or not str(event.get("raw_human_rationale") or "").strip()
            or event.get("owner_identity_ref") != OWNER_IDENTITY
        ):
            raise TargetedReviewError(f"Ledger event {index} is outside the approved review contract")
        previous = active.get(key)
        if event.get("event_type") == "OWNER_EXPLICIT_QREL_GRADE":
            if previous is not None:
                raise TargetedReviewError(f"Ledger event {index} duplicates an active candidate")
        elif event.get("event_type") == "OWNER_QREL_CORRECTION":
            if previous is None or event.get("prior_event_id") != previous.get("event_id"):
                raise TargetedReviewError(f"Ledger event {index} has an invalid correction chain")
        else:
            raise TargetedReviewError(f"Ledger event {index} has an unsupported event type")
        active[key] = dict(event)
    return active


def ungraded_candidates(
    candidates: Sequence[Mapping[str, str]],
    events: Sequence[Mapping[str, Any]],
    *,
    precovered_keys: set[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    allowed = {(candidate["item_ref"], candidate["candidate_ref"]) for candidate in candidates}
    active = active_judgments(events, allowed)
    covered = set(active).union(precovered_keys or set())
    if not covered.issubset(allowed):
        raise TargetedReviewError("Prior coverage falls outside the approved review scope")
    return [dict(candidate) for candidate in candidates if (candidate["item_ref"], candidate["candidate_ref"]) not in covered]


def append_batch_judgments(
    ledger_path: Path,
    candidates: Sequence[Mapping[str, str]],
    submissions: Sequence[Mapping[str, Any]],
    *,
    precovered_keys: set[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Append a fully validated batch as one human's individual review events."""
    candidates_by_key = {(candidate["item_ref"], candidate["candidate_ref"]): candidate for candidate in candidates}
    existing = _read_jsonl(ledger_path)
    active = active_judgments(existing, set(candidates_by_key))
    covered = set(active).union(precovered_keys or set())
    seen: set[tuple[str, str]] = set()
    events: list[dict[str, Any]] = []
    for submission in submissions:
        key = (str(submission.get("item_ref") or ""), str(submission.get("candidate_ref") or ""))
        grade = submission.get("grade")
        rationale = str(submission.get("rationale") or "").strip()
        if key not in candidates_by_key or key in covered or key in seen:
            raise TargetedReviewError("A submitted candidate is unknown, already graded, or duplicated")
        if not isinstance(grade, int) or isinstance(grade, bool) or grade not in ALLOWED_GRADES:
            raise TargetedReviewError("Every card needs one explicit grade: 0, 1, 2, or 3")
        if not rationale:
            raise TargetedReviewError("Every card needs a nonempty human rationale")
        unsigned: dict[str, Any] = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_id": f"targeted-qrel-{uuid.uuid4()}",
            "event_type": "OWNER_EXPLICIT_QREL_GRADE",
            "recorded_at_utc": _utc_now(),
            "owner_identity_ref": OWNER_IDENTITY,
            "item_ref": key[0],
            "candidate_ref": key[1],
            "relevance_grade": grade,
            "raw_human_rationale": rationale,
            "target_scope": TARGET_SCOPE,
            "reviewer_a_packet_only": True,
            "qrel_finalized": False,
        }
        events.append({**unsigned, "event_digest": canonical_sha256(unsigned)})
        seen.add(key)
    if not events:
        raise TargetedReviewError("No human judgments were submitted")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return events


def selected_rationale(reason: str, note: str) -> str:
    """Preserve the exact human-selected reason; retain an optional own-note."""
    if reason not in RATIONALE_OPTIONS:
        raise TargetedReviewError("Every card needs one selected human rationale")
    note = note.strip()
    return reason if not note else f"{reason}\nHuman note: {note}"


def render_batch_html(candidates: Sequence[Mapping[str, str]], *, completed: int, total: int, message: str = "") -> str:
    """Render pure-white (#ffffff) DIE-parity local HTML; candidate references remain server-side."""
    cards: list[str] = []
    grade_specs = (
        (3, "Authoritative / Core", "Directly and completely demonstrates a core competency for this role"),
        (2, "Supporting / Relevant", "Relevant supporting proof, but secondary or missing a key detail"),
        (1, "Marginal / Contextual", "High-level background or transferable context without direct proof"),
        (0, "Irrelevant / Confounder", "Wrong role, generic filler, or off-topic keyword overlap"),
    )
    for position, candidate in enumerate(candidates, start=1):
        grade_options = "".join(
            f'<label class="grade" title="{html.escape(desc, quote=True)}">'
            f'<input required type="radio" name="grade_{position}" value="{grade}">'
            f'<b>Grade {grade}</b> <span class="g-sub">{html.escape(label)}</span></label>'
            for grade, label, desc in grade_specs
        )
        reason_options = "".join(
            f'<label class="reason"><input required type="radio" name="reason_{position}" value="{html.escape(reason, quote=True)}">{html.escape(reason)}</label>'
            for reason in RATIONALE_OPTIONS
        )
        scope_drawer = (
            f'<details class="ref-drawer"><summary>Reference Only: Scope Context (do not grade boilerplate)</summary>'
            f'<p>{html.escape(candidate["scope"])}</p></details>'
            if candidate["scope"]
            else ""
        )
        cards.append(
            f'''<article class="card"><div class="card-head"><h2>Card {chr(64 + position)}</h2><span class="badge">Blinded Candidate</span></div>
<div class="core-box"><div class="kicker">Core Statement &amp; Evidence (Grade Only This Text)</div>
<p><strong>Action:</strong> {html.escape(candidate["action"])}</p>
<p><strong>Evidence:</strong> {html.escape(candidate["evidence"])}</p></div>{scope_drawer}
<div class="decision-box"><div class="kicker">Step 1: Relevance Grade (3-2-1-0)</div>
<p class="box-guide">Hover any grade button for full behavior-anchored criteria.</p>
<fieldset>{grade_options}</fieldset></div>
<div class="decision-box"><div class="kicker">Step 2: Explicit Human Rationale (Required)</div>
<p class="box-guide">Pick the single reason that best explains your grade; add optional detail below.</p>
<fieldset class="reasons">{reason_options}</fieldset>
<label class="rationale">Optional note <span>Only if the buttons do not capture it</span>
<textarea name="note_{position}" rows="2" maxlength="1000" placeholder="Optional detail in your own words"></textarea></label></div>
</article>'''
        )
    notice = f'<p class="notice">{html.escape(message)}</p>' if message else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light only">
<title>Brown &amp; Brown Competency QRELS Review</title><style>
:root{{color-scheme:light only;--border:#cbd5e1;--border-strong:#94a3b8;--text:#0f172a;--muted:#475569;--pass:#047857;}}
*{{box-sizing:border-box;}}
html,body{{margin:0;background:#ffffff !important;background-color:#ffffff !important;color:var(--text);color-scheme:light only;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}}
main{{max-width:980px;margin:0 auto;padding:20px 24px 32px;background:#ffffff;}}
h1{{margin:0 0 4px;font-size:19px;}}
.sub{{color:var(--muted);margin:0 0 12px;font-size:13px;}}
details.guide-banner{{background:#ffffff;border:1px solid var(--border-strong);border-left:4px solid var(--text);border-radius:10px;padding:10px 14px;margin-bottom:14px;font-size:12.5px;}}
details.guide-banner summary{{cursor:pointer;font-weight:700;}}
.guide-steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:8px;}}
@media(max-width:860px){{.guide-steps{{grid-template-columns:1fr;}}}}
.guide-step{{background:#ffffff;border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:12px;}}
.notice{{background:#ffffff;border:1px solid var(--pass);color:var(--pass);padding:10px 12px;border-radius:8px;font-size:13px;}}
.card{{background:#ffffff;border:1px solid var(--border);border-radius:10px;margin:16px 0;padding:16px;box-shadow:0 1px 2px rgba(15,23,42,0.04);}}
.card-head{{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:10px;}}
.card-head h2{{margin:0;font-size:15px;}}
.badge{{background:#ffffff;border:1px solid var(--border);padding:2px 8px;border-radius:6px;font-size:11px;font-family:ui-monospace,Menlo,monospace;}}
.kicker{{font-size:11px;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;color:var(--text);margin-bottom:4px;}}
.box-guide{{font-size:12px;color:var(--muted);margin:0 0 8px;}}
.core-box{{background:#ffffff;border:1px solid var(--border-strong);border-radius:8px;padding:12px;margin-bottom:10px;}}
.core-box p{{margin:6px 0;}}
details.ref-drawer{{background:#ffffff;border:1px dashed var(--border-strong);border-radius:8px;padding:8px 12px;margin-bottom:10px;font-size:12px;color:var(--muted);}}
details.ref-drawer summary{{cursor:pointer;font-weight:600;}}
.decision-box{{background:#ffffff;border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-top:10px;}}
fieldset{{border:0;padding:0;margin:0;display:flex;gap:8px;flex-wrap:wrap;}}
.grade,.reason{{background:#ffffff;border:1px solid var(--border-strong);border-radius:7px;padding:7px 10px;cursor:pointer;font-size:13px;}}
.g-sub{{color:var(--muted);font-size:11.5px;}}
.grade:has(input:checked),.reason:has(input:checked){{background:#0f172a;color:#ffffff;border-color:#0f172a;}}
.grade:has(input:checked) .g-sub{{color:#e2e8f0;}}
.reasons{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));margin-bottom:8px;}}
textarea{{display:block;width:100%;margin-top:5px;padding:8px;border:1px solid var(--border-strong);border-radius:6px;background:#ffffff;color:var(--text);font:inherit;}}
.rationale span{{font-size:12px;color:var(--muted);}}
button{{font:700 14px system-ui;padding:11px 18px;border:1px solid var(--pass);border-radius:8px;background:var(--pass);color:#ffffff;cursor:pointer;}}
</style></head><body><main><h1>Brown &amp; Brown — Core Competencies QRELS Review</h1>
<p class="sub">Target: SVP, IT Strategy &amp; Innovation | Completed: {completed} of {total} | Blinded Owner-Solo Calibration (Not Release Qualification)</p>{notice}
<details open class="guide-banner"><summary>Quick Start Guide: How to Grade Each Card (~30 seconds) - click to collapse</summary>
<div class="guide-steps">
<div class="guide-step"><strong>1. Read Core Statement Only:</strong> Focus on Action and Evidence inside the solid box. Dimmed Scope drawers are reference-only.</div>
<div class="guide-step"><strong>2. Score 3-2-1-0:</strong> <strong>3</strong> Authoritative/Core, <strong>2</strong> Supporting, <strong>1</strong> Marginal/Contextual, <strong>0</strong> Irrelevant/Confounder.</div>
<div class="guide-step"><strong>3. Select Rationale &amp; Save:</strong> Pick one rationale per card and submit; selections append immutably to the owner ledger.</div>
</div></details>
<form method="post">{''.join(cards)}<button type="submit">Save this batch</button></form></main></body></html>'''
