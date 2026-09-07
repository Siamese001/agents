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


def _render_evidence(text: str) -> str:
    """Format the full stored cluster text without changing any of its wording."""

    escaped = html.escape(text)
    for marker in (
        " Scope:",
        " Outcome:",
        " Operating context:",
        " Capabilities:",
        " Evidence:",
    ):
        escaped = escaped.replace(marker, f"</p><p><strong>{marker.strip()}</strong>")
    return f"<p>{escaped}</p>"


def render_batch_html(
    candidates: Sequence[Mapping[str, str]],
    *,
    completed: int,
    total: int,
    message: str = "",
) -> str:
    """Render a reference-free local HTML page for a small owner review batch."""

    cards: list[str] = []
    current_item: str | None = None
    for position, candidate in enumerate(candidates, 1):
        item_ref = str(candidate["item_ref"])
        if item_ref != current_item:
            current_item = item_ref
            cards.append(
                f'''<section class="context"><h2>{html.escape(str(candidate["resume_section"]))}</h2>
<p class="question">{html.escape(str(candidate["section_prompt"]))}</p>
<details open><summary>Target job and application brief</summary><pre>{html.escape(str(candidate["target_context"]))}</pre></details></section>'''
            )
        grades = "".join(
            f'<label class="grade"><input required type="radio" name="grade_{position}" value="{grade}"><b>{grade}</b> {label}</label>'
            for grade, label in (
                (0, "not useful"),
                (1, "weak / indirect"),
                (2, "relevant"),
                (3, "core"),
            )
        )
        reasons = "".join(
            f'<label class="reason"><input required type="radio" name="reason_{position}" value="{html.escape(reason, quote=True)}">{html.escape(reason)}</label>'
            for reason in RATIONALE_OPTIONS
        )
        cards.append(
            f'''<article class="card"><h3>Evidence item {position}</h3>
<p class="label">Complete graph-evidence cluster</p><div class="evidence">{_render_evidence(str(candidate["evidence_cluster_text"]))}</div>
<fieldset><legend>Usefulness for the resume section above</legend>{grades}</fieldset>
<fieldset class="reasons"><legend>Your rationale</legend>{reasons}</fieldset>
<label class="note">Optional note <span>Use this only when you want to add your own detail.</span>
<textarea name="note_{position}" rows="2" maxlength="1000" placeholder="Optional detail in your own words"></textarea></label></article>'''
        )
    notice = f'<p class="notice">{html.escape(message)}</p>' if message else ""
    empty = (
        '<p class="notice">No remaining evidence items are waiting in this packet.</p>'
        if not candidates
        else ""
    )
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Full-resume evidence review</title><style>
body{{font:16px/1.48 system-ui,sans-serif;max-width:1040px;margin:0 auto;padding:24px;background:#f5f7fb;color:#162033}}h1{{margin-bottom:4px}}.sub{{color:#526177;margin-top:0}}.notice{{background:#e9f7ee;padding:12px;border-radius:8px}}.intro{{background:#fff4d6;border-left:4px solid #c88700;padding:12px}}.context,.card{{background:#fff;border:1px solid #d6deeb;border-radius:12px;margin:18px 0;padding:18px;box-shadow:0 1px 3px #0001}}.context{{border-left:5px solid #1769aa}}h2,h3{{margin-top:0}}.question{{font-size:1.1em;font-weight:650}}details{{margin-top:12px}}summary{{cursor:pointer;font-weight:650}}pre{{font:14px/1.42 ui-monospace,Consolas,monospace;white-space:pre-wrap;background:#f5f7fb;padding:12px;border-radius:8px;max-height:430px;overflow:auto}}.label{{font-size:.85em;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#526177;margin-bottom:2px}}.evidence{{font-size:1.03em}}.evidence p{{margin:8px 0}}fieldset{{border:0;padding:0;margin:18px 0 10px;display:flex;gap:8px;flex-wrap:wrap}}.grade,.reason{{border:1px solid #adb9cb;border-radius:7px;padding:7px 9px;cursor:pointer}}.grade:has(input:checked),.reason:has(input:checked){{background:#dceeff;border:2px solid #1769aa;padding:6px 8px}}.reasons{{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr))}}textarea{{display:block;width:100%;box-sizing:border-box;margin-top:5px;font:inherit}}.note span{{font-size:.9em;color:#526177}}button{{font:600 17px system-ui;padding:13px 18px;border:0;border-radius:8px;background:#0b63a3;color:white;cursor:pointer}}</style>
<body><h1>Full-resume evidence review</h1><p class="sub">Completed: {completed} of {total}. Each selection is saved as one explicit owner QREL return.</p>{notice}
<p class="intro">Read the full target context and complete evidence cluster. Then grade how useful that source material is for the named résumé section: 0 = not useful, 1 = weak/indirect, 2 = relevant, 3 = core.</p>{empty}
<form method="post">{''.join(cards)}{'<button type="submit">Save this batch</button>' if candidates else ''}</form></body></html>'''


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
