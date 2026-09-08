"""Blinded local review of resume-facing competency bundles, not retrieval evidence.

The graph's Action, Scope, and Evidence fields remain provenance for a
competency.  This lane asks the human only to rate the final competency that
would appear in the resume.  It is therefore a competency-projection review,
not a BGE-M3 retrieval QREL evaluation.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


OWNER_IDENTITY = "human-reviewer://amit-owner"
SCOPE = "BROWN_BROWN_FINAL_COMPETENCY_PROJECTION"
EVENT_SCHEMA = "apps_rg.owner_solo_final_competency_review_event.v1"
RESTART_SCHEMA = "apps_rg.owner_solo_review_restart_receipt.v1"
GRADES = {0, 1, 2, 3}
RATIONALES = (
    "Core competency for this target role",
    "Relevant, but supporting rather than central",
    "Transferable but too generic",
    "Wrong role, industry, or resume section",
    "Exclude from this competencies section",
)


class FinalCompetencyReviewError(ValueError):
    """A final-competency review input is invalid or incomplete."""


def canonical_sha256(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise FinalCompetencyReviewError("Review ledger is malformed") from exc


def load_final_competencies(repo_root: Path) -> list[dict[str, Any]]:
    """Load the exact resume-facing line emitted for each graph bundle."""
    path = repo_root / "src/apps_rg/fact_inventory/competency_capability_bundles.json"
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalCompetencyReviewError("Graph competency bundle source is unavailable") from exc
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bundle in source.get("bundles") or []:
        bundle_id = str(bundle.get("competency_bundle_id") or "")
        label = str(bundle.get("display_label_candidate") or "").strip()
        anchors = [str(value).strip() for value in bundle.get("vocabulary_anchors") or [] if str(value).strip()]
        if (
            bundle.get("activation_status") == "ACTIVE"
            and "competencies" in (bundle.get("allowed_sections") or [])
            and bundle_id
            and label
            and anchors
        ):
            if bundle_id in seen:
                raise FinalCompetencyReviewError("Graph competency bundle identity is duplicated")
            seen.add(bundle_id)
            # This is the same final rendering shape as competencies_display_text():
            # ``resume_display_label: term 1, term 2, term 3``.
            candidates.append(
                {
                    "bundle_id": bundle_id,
                    "resume_line": f"{label}: {', '.join(anchors)}",
                }
            )
    if len(candidates) != 12:
        raise FinalCompetencyReviewError("Expected exactly 12 active final competency bundles")
    return candidates


def active_reviews(events: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    known = {str(candidate["bundle_id"]) for candidate in candidates}
    active: dict[str, dict[str, Any]] = {}
    for index, event in enumerate(events, start=1):
        unsigned = {key: value for key, value in event.items() if key != "event_digest"}
        bundle_id = str(event.get("bundle_id") or "")
        if (
            event.get("schema_version") != EVENT_SCHEMA
            or event.get("event_type") != "OWNER_FINAL_COMPETENCY_GRADE"
            or event.get("owner_identity_ref") != OWNER_IDENTITY
            or event.get("review_scope") != SCOPE
            or bundle_id not in known
            or event.get("grade") not in GRADES
            or not str(event.get("raw_human_rationale") or "").strip()
            or event.get("event_digest") != canonical_sha256(unsigned)
            or bundle_id in active
        ):
            raise FinalCompetencyReviewError(f"Final-competency ledger event {index} is invalid")
        active[bundle_id] = dict(event)
    return active


def unreviewed(candidates: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    active = active_reviews(events, candidates)
    return [dict(candidate) for candidate in candidates if candidate["bundle_id"] not in active]


def selected_rationale(reason: str, note: str) -> str:
    if reason not in RATIONALES:
        raise FinalCompetencyReviewError("Select one explicit human rationale")
    return reason if not note.strip() else f"{reason}\nHuman note: {note.strip()}"


def append_reviews(ledger_path: Path, candidates: Sequence[Mapping[str, Any]], submitted: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    active = active_reviews(_read_jsonl(ledger_path), candidates)
    known = {str(candidate["bundle_id"]) for candidate in candidates}
    new_ids: set[str] = set()
    events: list[dict[str, Any]] = []
    for row in submitted:
        bundle_id = str(row.get("bundle_id") or "")
        grade = row.get("grade")
        rationale = str(row.get("rationale") or "").strip()
        if bundle_id not in known or bundle_id in active or bundle_id in new_ids:
            raise FinalCompetencyReviewError("A competency is unknown, already rated, or duplicated")
        if not isinstance(grade, int) or isinstance(grade, bool) or grade not in GRADES:
            raise FinalCompetencyReviewError("Every competency needs an explicit 0, 1, 2, or 3 rating")
        if not rationale:
            raise FinalCompetencyReviewError("Every competency needs a human rationale")
        unsigned: dict[str, Any] = {
            "schema_version": EVENT_SCHEMA,
            "event_id": f"final-competency-{uuid.uuid4()}",
            "event_type": "OWNER_FINAL_COMPETENCY_GRADE",
            "recorded_at_utc": _now(),
            "owner_identity_ref": OWNER_IDENTITY,
            "review_scope": SCOPE,
            "bundle_id": bundle_id,
            "grade": grade,
            "raw_human_rationale": rationale,
            "retrieval_qrel": False,
            "release_authorizing": False,
        }
        events.append({**unsigned, "event_digest": canonical_sha256(unsigned)})
        new_ids.add(bundle_id)
    if not events:
        raise FinalCompetencyReviewError("No competency ratings were submitted")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return events


def write_restart_receipt(old_ledger: Path, receipt_path: Path) -> dict[str, Any]:
    """Preserve, but explicitly disqualify, the wrong-unit evidence reviews."""
    prior = _read_jsonl(old_ledger)
    receipt: dict[str, Any] = {
        "schema_version": RESTART_SCHEMA,
        "status": "SUPERSEDED_WRONG_UNIT_OF_JUDGMENT",
        "owner_identity_ref": OWNER_IDENTITY,
        "prior_ledger_path": str(old_ledger).replace("\\", "/"),
        "prior_ledger_sha256": hashlib.sha256(old_ledger.read_bytes()).hexdigest() if old_ledger.exists() else None,
        "prior_event_count": len(prior),
        "human_direction": "Rate the final competency from the graph; Action, Scope, and Evidence are underlying provenance only.",
        "prior_human_events_preserved_unchanged": True,
        "prior_events_eligible_for_retrieval_qrels": False,
        "prior_events_eligible_for_final_competency_metrics": False,
        "replacement_review_scope": SCOPE,
        "release_authorizing": False,
        "recorded_at_utc": _now(),
    }
    receipt["receipt_digest"] = canonical_sha256(receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def write_selection_receipt(
    repo_root: Path, ledger_path: Path, receipt_path: Path
) -> dict[str, Any]:
    """Freeze the owner-approved final competency selection, not retrieval QRELs."""
    candidates = load_final_competencies(repo_root)
    events = _read_jsonl(ledger_path)
    active = active_reviews(events, candidates)
    if len(active) != len(candidates):
        raise FinalCompetencyReviewError(
            f"Cannot freeze selection before all {len(candidates)} competencies are rated"
        )
    selected = [
        {
            "bundle_id": candidate["bundle_id"],
            "resume_line": candidate["resume_line"],
            "human_grade": active[candidate["bundle_id"]]["grade"],
            "raw_human_rationale": active[candidate["bundle_id"]]["raw_human_rationale"],
        }
        for candidate in candidates
        if active[candidate["bundle_id"]]["grade"] >= 2
    ]
    excluded = [
        {
            "bundle_id": candidate["bundle_id"],
            "resume_line": candidate["resume_line"],
            "human_grade": active[candidate["bundle_id"]]["grade"],
            "raw_human_rationale": active[candidate["bundle_id"]]["raw_human_rationale"],
        }
        for candidate in candidates
        if active[candidate["bundle_id"]]["grade"] < 2
    ]
    receipt: dict[str, Any] = {
        "schema_version": "apps_rg.owner_solo_final_competency_selection_receipt.v1",
        "status": "FROZEN_OWNER_SOLO_PROVISIONAL_FINAL_COMPETENCY_SELECTION",
        "owner_identity_ref": OWNER_IDENTITY,
        "review_scope": SCOPE,
        "selection_rule": "human_grade >= 2",
        "expected_competency_count": len(candidates),
        "completed_human_rating_count": len(active),
        "selected_competency_count": len(selected),
        "excluded_competency_count": len(excluded),
        "selected_competencies": selected,
        "excluded_competencies": excluded,
        "source_event_ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        "retrieval_qrels_created": False,
        "bge_retrieval_metrics_computable": False,
        "release_authorizing": False,
        "production_promotion_authorized": False,
        "recorded_at_utc": _now(),
    }
    receipt["receipt_digest"] = canonical_sha256(receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def render_html(candidates: Sequence[Mapping[str, Any]], *, completed: int, total: int, message: str = "") -> str:
    cards: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        grade_controls = "".join(
            f'<label class="choice"><input required type="radio" name="grade_{index}" value="{grade}"><b>{grade}</b> {label}</label>'
            for grade, label in ((0, "exclude"), (1, "weak"), (2, "relevant"), (3, "core"))
        )
        rationale_controls = "".join(
            f'<label class="reason"><input required type="radio" name="reason_{index}" value="{html.escape(reason, quote=True)}">{html.escape(reason)}</label>'
            for reason in RATIONALES
        )
        cards.append(f'''<article class="card"><h2>Competency {chr(64 + index)}</h2>
<p class="label">Whole competency as it appears on the résumé</p><p class="competency">{html.escape(str(candidate["resume_line"]))}</p>
<fieldset><legend>Should this final competency appear in Brown &amp; Brown’s competencies section?</legend>{grade_controls}</fieldset>
<fieldset class="reasons"><legend>Why?</legend>{rationale_controls}</fieldset>
<label>Optional note <textarea name="note_{index}" rows="2" maxlength="1000" placeholder="Only if the reason buttons do not capture it"></textarea></label></article>''')
    notice = f'<p class="notice">{html.escape(message)}</p>' if message else ""
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Final competency review</title><style>
body{{font:16px/1.45 system-ui,sans-serif;max-width:920px;margin:0 auto;padding:24px;background:#f5f7fb;color:#162033}}h1{{margin-bottom:4px}}.sub{{color:#526177;margin-top:0}}.notice{{background:#e9f7ee;padding:12px;border-radius:8px}}.warning{{background:#fff4d6;border-left:4px solid #c88700;padding:12px}}.card{{background:#fff;border:1px solid #d6deeb;border-radius:12px;margin:18px 0;padding:18px;box-shadow:0 1px 3px #0001}}h2{{margin-top:0}}.label{{font-size:.85em;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#526177;margin-bottom:2px}}.competency{{font-size:1.25em;font-weight:700;margin-top:0}}fieldset{{border:0;padding:0;margin:16px 0 10px;display:flex;gap:8px;flex-wrap:wrap}}.choice,.reason{{border:1px solid #adb9cb;border-radius:7px;padding:7px 9px;cursor:pointer}}.choice:has(input:checked),.reason:has(input:checked){{background:#dceeff;border:2px solid #1769aa;padding:6px 8px}}.reasons{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}}textarea{{display:block;width:100%;box-sizing:border-box;margin-top:5px;font:inherit}}button{{font:600 17px system-ui;padding:13px 18px;border:0;border-radius:8px;background:#0b63a3;color:white;cursor:pointer}}</style><body>
<h1>Brown &amp; Brown — final competencies</h1><p class="sub">Completed: {completed} of {total}. This is a final-competency projection review, not a BGE-M3 retrieval QREL.</p>{notice}
<p class="warning">Rate the complete résumé line only. The graph’s Action, Scope, and Evidence are deliberately not shown here; they are provenance, not the item you are grading.</p><form method="post">{''.join(cards)}<button type="submit">Save this batch</button></form></body></html>'''
