"""Local batch-review helpers for the W3 blinded full-resume QREL packet.

The browser only receives W3's reviewer-visible file.  Opaque references stay
on the local server and are used only when a human explicitly saves a grade and
rationale to the append-only owner ledger.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps_rg.evals.c03_human_eval._safety import unsafe_reviewer_keys
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w3 import (
    OWNER_COHORT,
    PACKET_STATUS,
    REVIEWER_MANIFEST_SCHEMA_VERSION,
    REVIEW_ITEM_SCHEMA_VERSION,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)


EVENT_SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_qrel_review_event.v1"
OWNER_IDENTITY = "human-reviewer://amit-owner"
ALLOWED_GRADES = frozenset({0, 1, 2, 3})
RATIONALE_OPTIONS = (
    "Not useful for this target résumé section",
    "Transferable, but indirect or too generic for this section",
    "Relevant source material for this section",
    "Direct, core source material for this target and section",
    "Other — I added my own note",
)


class FullResumeQrelReviewError(ValueError):
    """Raised when the local owner-review UI cannot safely handle a return."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FullResumeQrelReviewError(f"Required packet file is unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise FullResumeQrelReviewError(f"JSON object required: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise FullResumeQrelReviewError(
                    f"JSON object required in review ledger at line {line_no}"
                )
            rows.append(value)
    except json.JSONDecodeError as exc:
        raise FullResumeQrelReviewError("Review ledger is malformed") from exc
    return rows


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FullResumeQrelReviewError(f"Required packet file is unavailable: {path}") from exc
    return digest.hexdigest()


def _packet_manifest(packet_dir: Path) -> tuple[Path, dict[str, Any]]:
    manifests = sorted(packet_dir.glob("packet_manifest.*.json"))
    if len(manifests) != 1:
        raise FullResumeQrelReviewError("Exactly one W3 packet manifest is required")
    path = manifests[0]
    manifest = _read_json(path)
    unsigned = dict(manifest)
    supplied = unsigned.pop("packet_manifest_sha256", None)
    if (
        manifest.get("status") != PACKET_STATUS
        or not isinstance(supplied, str)
        or canonical_sha256(unsigned) != supplied
    ):
        raise FullResumeQrelReviewError("W3 packet manifest integrity check failed")
    return path, manifest


def load_blinded_review_packet(packet_dir: Path | str) -> dict[str, Any]:
    """Load and check only reviewer-visible W3 material for local presentation."""

    directory = Path(packet_dir).resolve()
    _manifest_path, manifest = _packet_manifest(directory)
    reviewer_dir = directory / OWNER_COHORT
    manifests = sorted(reviewer_dir.glob("reviewer_manifest.*.json"))
    if len(manifests) != 1:
        raise FullResumeQrelReviewError("Exactly one W3 reviewer manifest is required")
    reviewer_manifest = _read_json(manifests[0])
    items_path = reviewer_dir / "review_items.jsonl"
    file_digest = _file_sha256(items_path)
    unsigned = dict(reviewer_manifest)
    supplied = unsigned.pop("reviewer_manifest_sha256", None)
    expected = {
        "schema_version": REVIEWER_MANIFEST_SCHEMA_VERSION,
        "status": PACKET_STATUS,
        "cohort": OWNER_COHORT,
        "review_item_count": 66,
        "candidate_judgment_count": 600,
        "review_items_file_sha256": file_digest,
        "reviewer_visible_only": True,
        "ranks_scores_splits_cluster_ids_and_model_choice_present": False,
        "human_grades_present": False,
    }
    if unsigned != expected or not isinstance(supplied, str) or canonical_sha256(unsigned) != supplied:
        raise FullResumeQrelReviewError("W3 reviewer manifest integrity check failed")
    packet_files = manifest.get("files") or {}
    if (
        packet_files.get("review_items_file_sha256") != file_digest
        or packet_files.get("reviewer_manifest_sha256") != supplied
        or packet_files.get("reviewer_manifest_file_sha256") != _file_sha256(manifests[0])
    ):
        raise FullResumeQrelReviewError("W3 reviewer packet binding check failed")

    rows = _read_jsonl(items_path)
    if len(rows) != 66 or sum(int(row.get("candidate_count") or 0) for row in rows) != 600:
        raise FullResumeQrelReviewError("W3 reviewer packet denominator check failed")
    seen_items: set[str] = set()
    seen_candidates: set[tuple[str, str]] = set()
    candidates: list[dict[str, str]] = []
    for item in rows:
        item_ref = str(item.get("item_ref") or "")
        if (
            item.get("schema_version") != REVIEW_ITEM_SCHEMA_VERSION
            or not item_ref
            or item_ref in seen_items
            or unsafe_reviewer_keys(item)
        ):
            raise FullResumeQrelReviewError("W3 reviewer item violates the blinding contract")
        seen_items.add(item_ref)
        context = str(item.get("target_context") or "").strip()
        section = str(item.get("resume_section") or "").strip()
        prompt = str(item.get("section_prompt") or "").strip()
        raw_candidates = item.get("candidates")
        if not context or not section or not prompt or not isinstance(raw_candidates, list):
            raise FullResumeQrelReviewError("W3 reviewer item is incomplete")
        for candidate in raw_candidates:
            if not isinstance(candidate, Mapping):
                raise FullResumeQrelReviewError("W3 reviewer candidate is malformed")
            candidate_ref = str(candidate.get("candidate_ref") or "")
            text = str(candidate.get("evidence_cluster_text") or "").strip()
            key = (item_ref, candidate_ref)
            if not candidate_ref or not text or key in seen_candidates:
                raise FullResumeQrelReviewError("W3 reviewer candidate is incomplete")
            seen_candidates.add(key)
            candidates.append(
                {
                    "item_ref": item_ref,
                    "candidate_ref": candidate_ref,
                    "target_context": context,
                    "resume_section": section,
                    "section_prompt": prompt,
                    "evidence_cluster_text": text,
                }
            )
    if len(candidates) != 600:
        raise FullResumeQrelReviewError("W3 reviewer candidate conservation failed")
    return {
        "packet_manifest_sha256": manifest["packet_manifest_sha256"],
        "items": rows,
        "candidates": candidates,
    }


def active_judgments(
    events: Sequence[Mapping[str, Any]],
    *,
    allowed_keys: set[tuple[str, str]],
    packet_manifest_sha256: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Materialize active grades while validating the append-only correction chain."""

    active: dict[tuple[str, str], dict[str, Any]] = {}
    for index, event in enumerate(events, 1):
        unsigned = {key: value for key, value in event.items() if key != "event_digest"}
        if event.get("event_digest") != canonical_sha256(unsigned):
            raise FullResumeQrelReviewError(f"Review ledger event {index} digest is invalid")
        key = (str(event.get("item_ref") or ""), str(event.get("candidate_ref") or ""))
        grade = event.get("relevance_grade")
        if (
            event.get("schema_version") != EVENT_SCHEMA_VERSION
            or event.get("owner_identity_ref") != OWNER_IDENTITY
            or event.get("packet_manifest_sha256") != packet_manifest_sha256
            or key not in allowed_keys
            or not isinstance(grade, int)
            or isinstance(grade, bool)
            or grade not in ALLOWED_GRADES
            or not str(event.get("raw_human_rationale") or "").strip()
            or event.get("qrel_finalized") is not False
            or event.get("release_authorizing") is not False
        ):
            raise FullResumeQrelReviewError(
                f"Review ledger event {index} is outside the owner-review contract"
            )
        prior = active.get(key)
        if event.get("event_type") == "OWNER_EXPLICIT_QREL_GRADE":
            if prior is not None or event.get("prior_event_id") is not None:
                raise FullResumeQrelReviewError(
                    f"Review ledger event {index} duplicates an active candidate"
                )
        elif event.get("event_type") == "OWNER_QREL_CORRECTION":
            if prior is None or event.get("prior_event_id") != prior.get("event_id"):
                raise FullResumeQrelReviewError(
                    f"Review ledger event {index} has an invalid correction chain"
                )
        else:
            raise FullResumeQrelReviewError(
                f"Review ledger event {index} has an unsupported event type"
            )
        active[key] = dict(event)
    return active


def ungraded_candidates(
    candidates: Sequence[Mapping[str, str]],
    events: Sequence[Mapping[str, Any]],
    *,
    packet_manifest_sha256: str,
) -> list[dict[str, str]]:
    allowed = {
        (str(candidate["item_ref"]), str(candidate["candidate_ref"]))
        for candidate in candidates
    }
    active = active_judgments(
        events,
        allowed_keys=allowed,
        packet_manifest_sha256=packet_manifest_sha256,
    )
    return [
        dict(candidate)
        for candidate in candidates
        if (str(candidate["item_ref"]), str(candidate["candidate_ref"])) not in active
    ]


def selected_rationale(reason: str, note: str) -> str:
    """Save the exact human-selected rationale, optionally with their own words."""

    if reason not in RATIONALE_OPTIONS:
        raise FullResumeQrelReviewError("Every evidence item needs a selected rationale")
    human_note = note.strip()
    if reason == "Other — I added my own note" and not human_note:
        raise FullResumeQrelReviewError("The Other rationale requires your note")
    return reason if not human_note else f"{reason}\nHuman note: {human_note}"


def append_batch_judgments(
    ledger_path: Path | str,
    candidates: Sequence[Mapping[str, str]],
    submissions: Sequence[Mapping[str, Any]],
    *,
    packet_manifest_sha256: str,
) -> list[dict[str, Any]]:
    """Atomically append an all-valid batch of explicit owner return events."""

    path = Path(ledger_path)
    candidate_by_key = {
        (str(candidate["item_ref"]), str(candidate["candidate_ref"])): candidate
        for candidate in candidates
    }
    existing = _read_jsonl(path)
    active = active_judgments(
        existing,
        allowed_keys=set(candidate_by_key),
        packet_manifest_sha256=packet_manifest_sha256,
    )
    seen: set[tuple[str, str]] = set()
    events: list[dict[str, Any]] = []
    for submission in submissions:
        key = (
            str(submission.get("item_ref") or ""),
            str(submission.get("candidate_ref") or ""),
        )
        grade = submission.get("grade")
        rationale = str(submission.get("rationale") or "").strip()
        if key not in candidate_by_key or key in active or key in seen:
            raise FullResumeQrelReviewError(
                "A submitted evidence item is unknown, already graded, or duplicated"
            )
        if not isinstance(grade, int) or isinstance(grade, bool) or grade not in ALLOWED_GRADES:
            raise FullResumeQrelReviewError(
                "Every evidence item needs one explicit grade: 0, 1, 2, or 3"
            )
        if not rationale:
            raise FullResumeQrelReviewError(
                "Every evidence item needs a nonempty human rationale"
            )
        unsigned: dict[str, Any] = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_id": f"owner-solo-full-resume-qrel-{uuid.uuid4()}",
            "event_type": "OWNER_EXPLICIT_QREL_GRADE",
            "recorded_at_utc": _now(),
            "owner_identity_ref": OWNER_IDENTITY,
            "packet_manifest_sha256": packet_manifest_sha256,
            "item_ref": key[0],
            "candidate_ref": key[1],
            "relevance_grade": grade,
            "raw_human_rationale": rationale,
            "prior_event_id": None,
            "reviewer_visible_packet_only": True,
            "qrel_finalized": False,
            "release_authorizing": False,
        }
        events.append({**unsigned, "event_digest": canonical_sha256(unsigned)})
        seen.add(key)
    if not events:
        raise FullResumeQrelReviewError("No human evidence-item grades were submitted")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return events


def _render_evidence_split(text: str) -> tuple[str, str]:
    """Separate prominent core cluster statement from reference-only Scope/Context metadata without altering wording."""
    escaped = html.escape(text)
    core_segments: list[str] = []
    ref_segments: list[str] = []
    markers = (" Scope:", " Outcome:", " Operating context:", " Capabilities:", " Evidence:")
    marked = escaped
    for marker in markers:
        marked = marked.replace(marker, f"\n@@SPLIT@@{marker.strip()}")
    for chunk in marked.split("\n@@SPLIT@@"):
        part = chunk.strip()
        if not part:
            continue
        if part.startswith(("Scope:", "Operating context:", "Capabilities:")):
            label, _, rest = part.partition(":")
            ref_segments.append(f"<p><strong>{label}:</strong>{rest}</p>")
        else:
            label, sep, rest = part.partition(":")
            if sep and label in ("Action", "Outcome", "Evidence"):
                core_segments.append(f"<p><strong>{label}:</strong>{rest}</p>")
            else:
                core_segments.append(f"<p>{part}</p>")
    return "".join(core_segments) or f"<p>{escaped}</p>", "".join(ref_segments)


def render_batch_html(
    candidates: Sequence[Mapping[str, str]],
    *,
    completed: int,
    total: int,
    message: str = "",
) -> str:
    """Render a pure-white (#ffffff) DIE-parity reference-free local HTML page for owner review."""

    cards: list[str] = []
    current_item: str | None = None
    grade_specs = (
        (3, "Authoritative / Core", "Core statement directly and completely serves this target and resume section"),
        (2, "Supporting / Relevant", "Relevant supporting source material, though secondary or partial"),
        (1, "Marginal / Indirect", "High-level transferable background or generic framing without core proof"),
        (0, "Irrelevant / Confounder", "Wrong role, section mismatch, or not useful source material"),
    )
    for position, candidate in enumerate(candidates, 1):
        item_ref = str(candidate["item_ref"])
        if item_ref != current_item:
            current_item = item_ref
            cards.append(
                f'''<section class="context"><div class="kicker">Target Resume Section &amp; Question</div><h2>{html.escape(str(candidate["resume_section"]))}</h2>
<p class="question">{html.escape(str(candidate["section_prompt"]))}</p>
<details open><summary>Target job and application brief</summary><pre>{html.escape(str(candidate["target_context"]))}</pre></details></section>'''
            )
        grades = "".join(
            f'<label class="grade" title="{html.escape(desc, quote=True)}">'
            f'<input required type="radio" name="grade_{position}" value="{grade}">'
            f'<b>Grade {grade}</b> <span class="g-sub">{html.escape(label)}</span></label>'
            for grade, label, desc in grade_specs
        )
        reasons = "".join(
            f'<label class="reason"><input required type="radio" name="reason_{position}" value="{html.escape(reason, quote=True)}">{html.escape(reason)}</label>'
            for reason in RATIONALE_OPTIONS
        )
        core_html, ref_html = _render_evidence_split(str(candidate["evidence_cluster_text"]))
        ref_drawer = (
            f'<details class="ref-drawer"><summary>Reference Only: Scope, Operating Context &amp; Capabilities (do not grade boilerplate)</summary>'
            f'{ref_html}</details>'
            if ref_html
            else ""
        )
        cards.append(
            f'''<article class="card"><div class="card-head"><h3>Evidence item {position}</h3><span class="badge">Blinded Cluster</span></div>
<div class="core-box"><div class="kicker">Core Graph-Evidence Statement (Grade Only This Text)</div><div class="evidence">{core_html}</div></div>{ref_drawer}
<div class="decision-box"><div class="kicker">Step 1: Relevance Grade for Named Section (3-2-1-0)</div>
<p class="box-guide">Hover any grade option to inspect behavior-anchored criteria.</p>
<fieldset>{grades}</fieldset></div>
<div class="decision-box"><div class="kicker">Step 2: Explicit Human Rationale (Required)</div>
<p class="box-guide">Select one rationale below; choosing Other requires your own note.</p>
<fieldset class="reasons">{reasons}</fieldset>
<label class="note">Optional note <span>Use this only when you want to add your own detail.</span>
<textarea name="note_{position}" rows="2" maxlength="1000" placeholder="Optional detail in your own words"></textarea></label></div></article>'''
        )
    notice = f'<p class="notice">{html.escape(message)}</p>' if message else ""
    empty = (
        '<p class="notice">No remaining evidence items are waiting in this packet.</p>'
        if not candidates
        else ""
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light only">
<title>Full-Resume QRELS Evidence Review</title><style>
:root{{color-scheme:light only;--border:#cbd5e1;--border-strong:#94a3b8;--text:#0f172a;--muted:#475569;--pass:#047857;}}
*{{box-sizing:border-box;}}
html,body{{margin:0;background:#ffffff !important;background-color:#ffffff !important;color:var(--text);color-scheme:light only;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}}
main{{max-width:1060px;margin:0 auto;padding:20px 24px 32px;background:#ffffff;}}
h1{{margin:0 0 4px;font-size:19px;}}
.sub{{color:var(--muted);margin:0 0 12px;font-size:13px;}}
details.guide-banner{{background:#ffffff;border:1px solid var(--border-strong);border-left:4px solid var(--text);border-radius:10px;padding:10px 14px;margin-bottom:14px;font-size:12.5px;}}
details.guide-banner summary{{cursor:pointer;font-weight:700;}}
.guide-steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:8px;}}
@media(max-width:860px){{.guide-steps{{grid-template-columns:1fr;}}}}
.guide-step{{background:#ffffff;border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:12px;}}
.notice{{background:#ffffff;border:1px solid var(--pass);color:var(--pass);padding:10px 12px;border-radius:8px;font-size:13px;}}
.context,.card{{background:#ffffff;border:1px solid var(--border);border-radius:10px;margin:16px 0;padding:16px;box-shadow:0 1px 2px rgba(15,23,42,0.04);}}
.context{{border-left:4px solid var(--text);}}
.card-head{{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:10px;}}
h2,h3{{margin:0 0 6px;font-size:15.5px;}}
.badge{{background:#ffffff;border:1px solid var(--border);padding:2px 8px;border-radius:6px;font-size:11px;font-family:ui-monospace,Menlo,monospace;}}
.kicker{{font-size:11px;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;color:var(--text);margin-bottom:4px;}}
.box-guide{{font-size:12px;color:var(--muted);margin:0 0 8px;}}
.question{{font-size:15px;font-weight:600;margin:6px 0 10px;}}
details{{margin-top:10px;}}
summary{{cursor:pointer;font-weight:600;}}
pre{{font:13px/1.45 ui-monospace,Menlo,monospace;white-space:pre-wrap;background:#ffffff;border:1px solid var(--border);padding:12px;border-radius:8px;max-height:380px;overflow:auto;}}
.core-box{{background:#ffffff;border:1px solid var(--border-strong);border-radius:8px;padding:12px;margin-bottom:10px;}}
.evidence p{{margin:6px 0;}}
details.ref-drawer{{background:#ffffff;border:1px dashed var(--border-strong);border-radius:8px;padding:8px 12px;margin-bottom:10px;font-size:12px;color:var(--muted);}}
.decision-box{{background:#ffffff;border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-top:10px;}}
fieldset{{border:0;padding:0;margin:0;display:flex;gap:8px;flex-wrap:wrap;}}
.grade,.reason{{background:#ffffff;border:1px solid var(--border-strong);border-radius:7px;padding:7px 10px;cursor:pointer;font-size:13px;}}
.g-sub{{color:var(--muted);font-size:11.5px;}}
.grade:has(input:checked),.reason:has(input:checked){{background:#0f172a;color:#ffffff;border-color:#0f172a;}}
.grade:has(input:checked) .g-sub{{color:#e2e8f0;}}
.reasons{{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));margin-bottom:8px;}}
textarea{{display:block;width:100%;margin-top:5px;padding:8px;border:1px solid var(--border-strong);border-radius:6px;background:#ffffff;color:var(--text);font:inherit;}}
.note span{{font-size:12px;color:var(--muted);}}
button{{font:700 14px system-ui;padding:11px 18px;border:1px solid var(--pass);border-radius:8px;background:var(--pass);color:#ffffff;cursor:pointer;}}
</style></head><body><main><h1>Full-Resume QRELS Evidence Review</h1>
<p class="sub">Completed: {completed} of {total} | Blinded Owner-Solo Full-Resume Packet (Ranks, Splits &amp; Cluster IDs Hidden)</p>{notice}
<details open class="guide-banner"><summary>Quick Start Guide: How to Grade Each Cluster (~30 seconds) - click to collapse</summary>
<div class="guide-steps">
<div class="guide-step"><strong>1. Read Section &amp; Core Evidence:</strong> Check the named resume section and read the Core Statement box. Dimmed Scope/Context drawers are reference-only.</div>
<div class="guide-step"><strong>2. Grade 3-2-1-0:</strong> <strong>3</strong> Authoritative/Core, <strong>2</strong> Supporting/Relevant, <strong>1</strong> Marginal/Indirect, <strong>0</strong> Irrelevant/Confounder.</div>
<div class="guide-step"><strong>3. Pick Rationale &amp; Save:</strong> Choose one explicit rationale per item; every saved grade appends immutably with SHA-256 verification.</div>
</div></details>{empty}
<form method="post">{''.join(cards)}{'<button type="submit">Save this batch</button>' if candidates else ''}</form></main></body></html>'''


__all__ = [
    "ALLOWED_GRADES",
    "EVENT_SCHEMA_VERSION",
    "FullResumeQrelReviewError",
    "OWNER_IDENTITY",
    "RATIONALE_OPTIONS",
    "active_judgments",
    "append_batch_judgments",
    "load_blinded_review_packet",
    "render_batch_html",
    "selected_rationale",
    "ungraded_candidates",
]
