"""Owner-solo review of source-bound, rendered résumé output units.

This is deliberately a *final-output* review. A reviewer sees the finished
résumé text that a hiring manager would see, together with the complete
rendered section containing that text. It does not ask the reviewer to judge
retrieval clusters, graph nodes, ranks, or embedding scores.

The lane is separate from the authoritative C0.3 QREL contract. Its human
grades measure the usefulness of rendered résumé output; they cannot be
converted into BGE-M3 Recall@n, nDCG, or MRR.
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

from apps_rg.runtime.assembly.competencies_display import render_competencies


OWNER_IDENTITY = "human-reviewer://amit-owner"
SCOPE = "OWNER_SOLO_PROVISIONAL_FINAL_RESUME_OUTPUT"
EVENT_SCHEMA = "apps_rg.owner_solo_final_resume_output_review_event.v1"
PROGRESS_SCHEMA = "apps_rg.owner_solo_final_resume_output_progress_receipt.v1"
GRADES = {0, 1, 2, 3}
REVIEW_UNIT_SECTION = "section"
REVIEW_UNIT_OUTPUT = "output_unit"
REVIEW_UNITS = frozenset((REVIEW_UNIT_SECTION, REVIEW_UNIT_OUTPUT))
RATIONALES = (
    "Strong fit; keep as written",
    "Good fit; needs only a small edit",
    "Relevant idea, but needs a substantive rewrite",
    "Too generic, unsupported, or wrong fit for this target role",
    "Remove from this résumé section",
)

_FINAL_OUTPUT_MANIFEST = "FINAL_RESUME_OUTPUT.json"
_FINAL_OUTPUT_TEXT = "FINAL_RESUME_OUTPUT.txt"
_FINAL_RESUME = Path("modular_r4/final_resume_assembly/final_resume.json")
_ROLE_ORDER: tuple[tuple[str, str, str], ...] = (
    ("unify", "unify_narrative", "unify_bullets"),
    ("ibm", "ibm_narrative", "ibm_bullets"),
    ("insurtech", "insurtech_narrative", "insurtech_bullets"),
    ("ey", "ey_narrative", "ey_bullets"),
)
_ROLE_CARD_ORDER: tuple[tuple[str, str], ...] = (
    ("unify", "Unify Consulting — Experience"),
    ("ibm", "IBM — Experience"),
    ("insurtech", "InsurTech Cloud Solutions — Experience"),
    ("ey", "Ernst & Young — Experience"),
)
_COMPETENCIES_HEADING = "ENGINEERING & PLATFORM COMPETENCIES"


class FinalResumeOutputReviewError(ValueError):
    """A claimed final résumé output cannot be safely reviewed."""


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalResumeOutputReviewError(f"{label} is unavailable or malformed") from exc
    if not isinstance(value, dict):
        raise FinalResumeOutputReviewError(f"{label} must be a JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise FinalResumeOutputReviewError("Final-output review ledger is malformed") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise FinalResumeOutputReviewError("Final-output review ledger has a non-object event")
    return rows


def _safe_artifact_path(run_root: Path, relpath: str, *, label: str) -> Path:
    path = (run_root / relpath).resolve()
    try:
        path.relative_to(run_root.resolve())
    except ValueError as exc:
        raise FinalResumeOutputReviewError(f"{label} escapes the declared run root") from exc
    return path


def _verify_manifest_artifact(
    run_root: Path,
    entry: Any,
    *,
    label: str,
    expected_relpath: str | None = None,
) -> tuple[Path, str]:
    if not isinstance(entry, dict) or entry.get("exists") is not True:
        raise FinalResumeOutputReviewError(
            f"Final-output contract does not attest a present {label}"
        )
    relpath = str(entry.get("relpath") or "").replace("\\", "/")
    if not relpath:
        raise FinalResumeOutputReviewError(f"Final-output contract has no path for {label}")
    if expected_relpath is not None and relpath != expected_relpath:
        raise FinalResumeOutputReviewError(
            f"Final-output contract has the wrong canonical path for {label}"
        )
    expected = str(entry.get("sha256") or "").strip().lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise FinalResumeOutputReviewError(
            f"Final-output contract has no valid SHA-256 for {label}"
        )
    path = _safe_artifact_path(run_root, relpath, label=label)
    if not path.is_file():
        raise FinalResumeOutputReviewError(f"Final-output {label} is missing from the run")
    actual = _file_sha256(path)
    if actual != expected:
        raise FinalResumeOutputReviewError(
            f"Final-output {label} digest does not match its contract"
        )
    return path, actual


def _all_gates_pass(contract: Mapping[str, Any]) -> bool:
    gates = contract.get("gates")
    return isinstance(gates, list) and bool(gates) and all(
        isinstance(gate, dict) and gate.get("pass") is True for gate in gates
    )


def _has_no_gap_marker(text: str) -> bool:
    return "[NOT COMPLETED:" not in text and "[NOT_GENERATED_BY_RUN:" not in text


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _job_description_from_ref(ref: str, *, run_root: Path, repo_root: Path) -> str:
    raw = str(ref or "").strip()
    if not raw:
        return ""
    ref_path = Path(raw)
    candidates = [ref_path] if ref_path.is_absolute() else [run_root / ref_path, repo_root / ref_path]
    for candidate in candidates:
        if not (_within(candidate, run_root) or _within(candidate, repo_root)):
            continue
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if text:
                return text
    return ""


def _target_context(run_root: Path, repo_root: Path) -> dict[str, str]:
    """Resolve the target job context that the output was actually generated for."""
    sources: list[dict[str, Any]] = []
    for name in ("research_bridge_request.json", "validated_request.json"):
        path = run_root / name
        if not path.is_file():
            continue
        data = _read_json(path, label=name)
        payload = data.get("payload")
        sources.append(payload if isinstance(payload, dict) else data)

    company = ""
    role = ""
    description = ""
    for source in sources:
        company = company or str(
            source.get("company_name") or source.get("target_company") or ""
        ).strip()
        role = role or str(source.get("job_title") or source.get("target_role") or "").strip()
        description = description or str(
            source.get("job_description_text") or source.get("jd_text") or ""
        ).strip()
        if not description:
            description = _job_description_from_ref(
                str(source.get("job_description_ref") or source.get("jd_ref") or ""),
                run_root=run_root,
                repo_root=repo_root,
            )
    if not company or not role or not description:
        raise FinalResumeOutputReviewError(
            "A finished output must preserve its target company, role, and readable "
            "job description before human review"
        )
    return {
        "company": company,
        "role": role,
        "job_description": description,
    }


def _section_snapshot(final_resume: Mapping[str, Any], section_id: str) -> dict[str, Any]:
    for section in final_resume.get("sections") or []:
        if isinstance(section, dict) and section.get("section_id") == section_id:
            snapshot = section.get("l2_output_snapshot")
            if isinstance(snapshot, dict):
                if snapshot.get("assembly_gap") is True:
                    raise FinalResumeOutputReviewError(
                        f"The {section_id} output is an assembly-gap placeholder, not "
                        "finished résumé text"
                    )
                return snapshot
            return {}
    return {}


def _bullet_texts(snapshot: Mapping[str, Any]) -> list[str]:
    rows: list[str] = []
    for bullet in snapshot.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        text = str(bullet.get("bullet_text") or bullet.get("text") or "").strip()
        if text:
            rows.append(text)
    return rows


def _competency_text(snapshot: Mapping[str, Any]) -> str:
    direct = str(snapshot.get("resume_display_text") or "").strip()
    if direct:
        return direct
    return render_competencies(dict(snapshot))


def _locked_role_headers(final_resume: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    invariants = final_resume.get("locked_copy_invariants")
    if not isinstance(invariants, dict):
        return {}

    def parse(name: str) -> list[Any]:
        raw = invariants.get(name)
        copied = raw.get("copied_text_exact") if isinstance(raw, dict) else ""
        try:
            value = json.loads(copied) if isinstance(copied, str) else []
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    employers, titles, locations, dates = (
        parse(name) for name in ("company_names", "titles", "locations", "dates")
    )
    keys = ("unify", "ibm", "insurtech", "ey", "early_career")
    headers: dict[str, dict[str, Any]] = {}
    for index, key in enumerate(keys):
        if min(len(employers), len(titles), len(locations), len(dates)) <= index:
            continue
        date = dates[index] if isinstance(dates[index], dict) else {}
        headers[key] = {
            "employer": employers[index],
            "title": titles[index],
            "location": locations[index],
            "start_date": date.get("start_date"),
            "end_date": date.get("end_date"),
            "is_current": date.get("is_current"),
        }
    return headers


def _format_role_header(header: Mapping[str, Any]) -> str:
    employer = str(header.get("employer") or "").strip()
    title = str(header.get("title") or "").strip()
    location = str(header.get("location") or "").strip()
    start = str(header.get("start_date") or "").strip()
    end = str(header.get("end_date") or "").strip()
    first = " — ".join(value for value in (employer, title) if value)
    date = f"{start} – {end}".strip(" –")
    second = " | ".join(value for value in (location, date) if value)
    return "\n".join(value for value in (first, second) if value)


def _role_header(
    final_resume: Mapping[str, Any],
    role_key: str,
    narrative: Mapping[str, Any],
    bullets: Mapping[str, Any],
) -> str:
    header = _locked_role_headers(final_resume).get(role_key)
    if not header:
        for snapshot in (narrative, bullets):
            candidate = snapshot.get(f"{role_key}_header")
            if isinstance(candidate, dict):
                header = candidate
                break
    text = _format_role_header(header or {})
    if not text:
        raise FinalResumeOutputReviewError(
            f"Finished {role_key} output has no rendered role header"
        )
    return text


def _unit(
    *,
    source_digest: str,
    section_id: str,
    unit_type: str,
    ordinal: int,
    display_label: str,
    final_text: str,
    section_context: str,
) -> dict[str, Any]:
    text = final_text.strip()
    context = section_context.strip()
    if not text or not context:
        raise FinalResumeOutputReviewError(
            f"Finished {display_label} has no complete rendered text"
        )
    text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    identity = {
        "source_digest": source_digest,
        "section_id": section_id,
        "unit_type": unit_type,
        "ordinal": ordinal,
        "final_text_sha256": text_digest,
    }
    return {
        "unit_ref": f"resume-output-{canonical_sha256(identity)[:16]}",
        "section_id": section_id,
        "unit_type": unit_type,
        "ordinal": ordinal,
        "display_label": display_label,
        "final_text": text,
        "section_context": context,
        "final_text_sha256": text_digest,
    }


def _rendered_output_unit_candidates(
    final_resume: Mapping[str, Any], *, source_digest: str
) -> list[dict[str, Any]]:
    """Return the legacy fine-grained review units.

    Kept for compatibility with prior private review tooling.  The owner-facing
    default is deliberately the whole-section unit below: the owner judges the
    résumé content as it will be read, rather than being asked to score isolated
    sentences or graph material.
    """
    candidates: list[dict[str, Any]] = []

    headline = str(
        _section_snapshot(final_resume, "headline").get("headline_line") or ""
    ).strip()
    if headline:
        candidates.append(
            _unit(
                source_digest=source_digest,
                section_id="headline",
                unit_type="headline",
                ordinal=1,
                display_label="Headline",
                final_text=headline,
                section_context=headline,
            )
        )

    summary = str(
        _section_snapshot(final_resume, "executive_summary").get("resume_display_text")
        or ""
    ).strip()
    if summary:
        candidates.append(
            _unit(
                source_digest=source_digest,
                section_id="executive_summary",
                unit_type="executive_summary",
                ordinal=1,
                display_label="Executive summary",
                final_text=summary,
                section_context=summary,
            )
        )

    competency_text = _competency_text(_section_snapshot(final_resume, "competencies"))
    if competency_text:
        candidates.append(
            _unit(
                source_digest=source_digest,
                section_id="competencies",
                unit_type="competencies",
                ordinal=1,
                display_label="Competencies section",
                final_text=competency_text,
                section_context=competency_text,
            )
        )

    for role_key, narrative_id, bullets_id in _ROLE_ORDER:
        narrative_snapshot = _section_snapshot(final_resume, narrative_id)
        bullet_snapshot = _section_snapshot(final_resume, bullets_id)
        narrative = str(narrative_snapshot.get("narrative_sentence") or "").strip()
        bullets = _bullet_texts(bullet_snapshot)
        if not narrative and not bullets:
            continue
        header = _role_header(final_resume, role_key, narrative_snapshot, bullet_snapshot)
        context_lines = [header]
        if narrative:
            context_lines.append(narrative)
        context_lines.extend(f"• {bullet}" for bullet in bullets)
        context = "\n".join(context_lines)
        if narrative:
            candidates.append(
                _unit(
                    source_digest=source_digest,
                    section_id=narrative_id,
                    unit_type="role_narrative",
                    ordinal=1,
                    display_label=f"{role_key.upper()} role narrative",
                    final_text=narrative,
                    section_context=context,
                )
            )
        for ordinal, bullet in enumerate(bullets, start=1):
            candidates.append(
                _unit(
                    source_digest=source_digest,
                    section_id=bullets_id,
                    unit_type="resume_bullet",
                    ordinal=ordinal,
                    display_label=f"{role_key.upper()} résumé bullet {ordinal}",
                    final_text=f"• {bullet}",
                    section_context=context,
                )
            )
    if not candidates:
        raise FinalResumeOutputReviewError(
            "The completed final résumé contains no renderable output units"
        )
    refs = [str(candidate["unit_ref"]) for candidate in candidates]
    if len(refs) != len(set(refs)):
        raise FinalResumeOutputReviewError("Final résumé output-unit identities are not unique")
    return candidates


def _line_offsets(text: str, line: str) -> list[int]:
    """Return positions where ``line`` is an exact rendered-output line."""

    value = str(line or "").strip()
    if not value:
        return []
    offsets: list[int] = []
    cursor = 0
    while True:
        index = text.find(value, cursor)
        if index < 0:
            return offsets
        before_is_line_start = index == 0 or text[index - 1] == "\n"
        after = index + len(value)
        after_is_line_end = after == len(text) or text[after] == "\n"
        if before_is_line_start and after_is_line_end:
            offsets.append(index)
        cursor = index + len(value)


def _single_line_offset(text: str, line: str, *, label: str) -> int:
    offsets = _line_offsets(text, line)
    if len(offsets) != 1:
        raise FinalResumeOutputReviewError(
            f"Finished résumé has {len(offsets)} occurrences of required {label} line"
        )
    return offsets[0]


def _rendered_slice(
    text: str,
    *,
    start_line: str,
    end_lines: Sequence[str],
    label: str,
) -> str:
    """Extract one exact, complete final-resume section from rendered output."""

    start = _single_line_offset(text, start_line, label=f"{label} start")
    end_offsets: list[int] = []
    for line in end_lines:
        for offset in _line_offsets(text, line):
            if offset > start:
                end_offsets.append(offset)
    if not end_offsets:
        raise FinalResumeOutputReviewError(
            f"Finished résumé has no closing boundary for {label}"
        )
    result = text[start : min(end_offsets)].strip()
    if not result:
        raise FinalResumeOutputReviewError(f"Finished résumé has an empty {label}")
    return result


def _role_title_line(final_resume: Mapping[str, Any], role_key: str) -> str:
    header = _locked_role_headers(final_resume).get(role_key) or {}
    employer = str(header.get("employer") or "").strip()
    title = str(header.get("title") or "").strip()
    line = " — ".join(value for value in (employer, title) if value)
    if not line:
        raise FinalResumeOutputReviewError(
            f"Finished {role_key} output has no locked employer/title header"
        )
    return line


def _rendered_section_candidates(
    final_resume: Mapping[str, Any],
    *,
    rendered_resume_text: str,
    source_digest: str,
) -> list[dict[str, Any]]:
    """Return the six owner-review cards from the exact rendered résumé text.

    Each card is the complete section a hiring manager sees.  This is the
    correct human-review unit for the owner-solo output-quality lane; it is
    intentionally unrelated to C0.3 graph-evidence-cluster relevance.
    """

    rendered = rendered_resume_text.strip()
    role_lines = {
        role_key: _role_title_line(final_resume, role_key)
        for role_key, _display in _ROLE_CARD_ORDER
    }
    early_career_line = _role_title_line(final_resume, "early_career")
    top = _rendered_slice(
        rendered,
        start_line="HEADLINE",
        end_lines=(_COMPETENCIES_HEADING,),
        label="top-of-résumé positioning",
    )
    if "EXECUTIVE SUMMARY" not in top:
        raise FinalResumeOutputReviewError(
            "Finished résumé top-of-résumé section lacks EXECUTIVE SUMMARY"
        )
    competencies = _rendered_slice(
        rendered,
        start_line=_COMPETENCIES_HEADING,
        end_lines=("PROFESSIONAL EXPERIENCE",),
        label="competencies",
    )
    sections: list[tuple[str, str, str]] = [
        (
            "top_of_resume",
            "Top of Résumé — Headline & Executive Summary",
            top,
        ),
        (
            "competencies",
            "Engineering & Platform Competencies",
            competencies,
        ),
    ]
    role_keys = [role_key for role_key, _display in _ROLE_CARD_ORDER]
    for index, (role_key, display_label) in enumerate(_ROLE_CARD_ORDER):
        following = (
            role_lines[role_keys[index + 1]]
            if index + 1 < len(role_keys)
            else early_career_line
        )
        section = _rendered_slice(
            rendered,
            start_line=role_lines[role_key],
            end_lines=(following, "EDUCATION"),
            label=display_label,
        )
        sections.append((f"{role_key}_experience", display_label, section))

    candidates: list[dict[str, Any]] = []
    for ordinal, (section_id, display_label, rendered_section) in enumerate(
        sections, start=1
    ):
        candidates.append(
            _unit(
                source_digest=source_digest,
                section_id=section_id,
                unit_type="complete_resume_section",
                ordinal=ordinal,
                display_label=display_label,
                final_text=rendered_section,
                section_context=rendered_section,
            )
        )
    if len(candidates) != 6:
        raise FinalResumeOutputReviewError(
            "Whole-section final-output review must have exactly six cards"
        )
    return candidates


def load_final_resume_output_bundle(
    run_root: Path,
    *,
    repo_root: Path,
    review_unit: str = REVIEW_UNIT_SECTION,
) -> dict[str, Any]:
    """Load one completed final résumé and derive reviewable output units.

    The manifest has to be a passing output contract. This prevents a card
    from silently substituting a graph projection, an incomplete lane, or a
    fallback résumé containing gap markers.
    """
    if review_unit not in REVIEW_UNITS:
        raise FinalResumeOutputReviewError(
            f"Unsupported final-output review unit: {review_unit}"
        )
    root = Path(run_root).resolve()
    repo = Path(repo_root).resolve()
    if not root.is_dir():
        raise FinalResumeOutputReviewError("Declared output run root does not exist")
    manifest_path = root / _FINAL_OUTPUT_MANIFEST
    contract = _read_json(manifest_path, label="FINAL_RESUME_OUTPUT.json")
    if contract.get("schema_version") != "apps_rg.final_resume_output.v1":
        raise FinalResumeOutputReviewError("Unexpected final-output contract schema")
    if contract.get("status") != "PASS" or not _all_gates_pass(contract):
        raise FinalResumeOutputReviewError(
            "This run is not a completed final résumé output: its final-output contract "
            "is not PASS"
        )
    final_path, final_digest = _verify_manifest_artifact(
        root,
        contract.get("final_resume_json"),
        label="final_resume.json",
        expected_relpath=_FINAL_RESUME.as_posix(),
    )
    rendered_path, rendered_digest = _verify_manifest_artifact(
        root,
        contract.get("rendered_resume_text"),
        label="rendered resume text",
        expected_relpath=_FINAL_OUTPUT_TEXT,
    )
    rendered = rendered_path.read_text(encoding="utf-8")
    if not _has_no_gap_marker(rendered):
        raise FinalResumeOutputReviewError(
            "Completed final résumé text contains an explicit generated-content gap marker"
        )
    final_resume = _read_json(final_path, label="final_resume.json")
    target = _target_context(root, repo)
    source = {
        "output_contract_sha256": _file_sha256(manifest_path),
        "final_resume_sha256": final_digest,
        "rendered_resume_sha256": rendered_digest,
        "target_context_sha256": canonical_sha256(target),
    }
    candidates = (
        _rendered_section_candidates(
            final_resume,
            rendered_resume_text=rendered,
            source_digest=source["final_resume_sha256"],
        )
        if review_unit == REVIEW_UNIT_SECTION
        else _rendered_output_unit_candidates(
            final_resume, source_digest=source["final_resume_sha256"]
        )
    )
    return {
        "scope": SCOPE,
        "review_unit": review_unit,
        "source": source,
        "target": target,
        "candidates": candidates,
    }


def active_reviews(
    events: Sequence[Mapping[str, Any]], bundle: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    candidates = bundle.get("candidates")
    source = bundle.get("source")
    review_unit = bundle.get("review_unit")
    if (
        not isinstance(candidates, list)
        or not isinstance(source, dict)
        or review_unit not in REVIEW_UNITS
    ):
        raise FinalResumeOutputReviewError("Review bundle has an invalid shape")
    known = {
        str(candidate.get("unit_ref")): candidate
        for candidate in candidates
        if isinstance(candidate, dict)
    }
    active: dict[str, dict[str, Any]] = {}
    for index, raw_event in enumerate(events, start=1):
        event = dict(raw_event)
        unsigned = {key: value for key, value in event.items() if key != "event_digest"}
        unit_ref = str(event.get("unit_ref") or "")
        candidate = known.get(unit_ref)
        if (
            candidate is None
            or event.get("schema_version") != EVENT_SCHEMA
            or event.get("event_type") != "OWNER_FINAL_RESUME_OUTPUT_GRADE"
            or event.get("owner_identity_ref") != OWNER_IDENTITY
            or event.get("review_scope") != SCOPE
            or event.get("review_unit") != review_unit
            or event.get("grade") not in GRADES
            or not str(event.get("raw_human_rationale") or "").strip()
            or event.get("source") != source
            or event.get("final_text_sha256") != candidate.get("final_text_sha256")
            or event.get("event_digest") != canonical_sha256(unsigned)
            or unit_ref in active
        ):
            raise FinalResumeOutputReviewError(f"Final-output ledger event {index} is invalid")
        active[unit_ref] = event
    return active


def unreviewed(
    bundle: Mapping[str, Any], events: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    active = active_reviews(events, bundle)
    return [
        dict(candidate)
        for candidate in bundle["candidates"]
        if candidate["unit_ref"] not in active
    ]


def selected_rationale(reason: str, note: str) -> str:
    if reason not in RATIONALES:
        raise FinalResumeOutputReviewError("Select one explicit human rationale")
    return reason if not note.strip() else f"{reason}\nHuman note: {note.strip()}"


def append_reviews(
    ledger_path: Path,
    bundle: Mapping[str, Any],
    submitted: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    active = active_reviews(_read_jsonl(ledger_path), bundle)
    known = {str(candidate["unit_ref"]): candidate for candidate in bundle["candidates"]}
    events: list[dict[str, Any]] = []
    new_refs: set[str] = set()
    for row in submitted:
        unit_ref = str(row.get("unit_ref") or "")
        grade = row.get("grade")
        rationale = str(row.get("rationale") or "").strip()
        candidate = known.get(unit_ref)
        if candidate is None or unit_ref in active or unit_ref in new_refs:
            raise FinalResumeOutputReviewError(
                "A final-output unit is unknown, already rated, or duplicated"
            )
        if not isinstance(grade, int) or isinstance(grade, bool) or grade not in GRADES:
            raise FinalResumeOutputReviewError(
                "Every final-output unit needs an explicit 0, 1, 2, or 3 rating"
            )
        if not rationale:
            raise FinalResumeOutputReviewError(
                "Every final-output unit needs a human rationale"
            )
        unsigned: dict[str, Any] = {
            "schema_version": EVENT_SCHEMA,
            "event_id": f"final-resume-output-{uuid.uuid4()}",
            "event_type": "OWNER_FINAL_RESUME_OUTPUT_GRADE",
            "recorded_at_utc": _now(),
            "owner_identity_ref": OWNER_IDENTITY,
            "review_scope": SCOPE,
            "review_unit": bundle["review_unit"],
            "unit_ref": unit_ref,
            "section_id": candidate["section_id"],
            "unit_type": candidate["unit_type"],
            "ordinal": candidate["ordinal"],
            "final_text_sha256": candidate["final_text_sha256"],
            "source": bundle["source"],
            "grade": grade,
            "raw_human_rationale": rationale,
            "retrieval_qrel": False,
            "bge_retrieval_metrics_computable": False,
            "release_authorizing": False,
        }
        events.append({**unsigned, "event_digest": canonical_sha256(unsigned)})
        new_refs.add(unit_ref)
    if not events:
        raise FinalResumeOutputReviewError("No final-output ratings were submitted")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return events


def write_progress_receipt(
    ledger_path: Path,
    bundle: Mapping[str, Any],
    receipt_path: Path,
) -> dict[str, Any]:
    events = _read_jsonl(ledger_path)
    active = active_reviews(events, bundle)
    total = len(bundle["candidates"])
    completed = len(active)
    grades = [int(event["grade"]) for event in active.values()]
    receipt: dict[str, Any] = {
        "schema_version": PROGRESS_SCHEMA,
        "status": (
            "OWNER_SOLO_PROVISIONAL_FINAL_OUTPUT_COMPLETE"
            if completed == total
            else "OWNER_SOLO_PROVISIONAL_FINAL_OUTPUT_IN_PROGRESS"
        ),
        "owner_identity_ref": OWNER_IDENTITY,
        "review_scope": SCOPE,
        "review_unit": bundle["review_unit"],
        "total_final_output_units": total,
        "completed_final_output_units": completed,
        "remaining_final_output_units": total - completed,
        "mean_human_grade": round(sum(grades) / len(grades), 6) if grades else None,
        "keep_or_small_edit_rate": (
            round(sum(grade >= 2 for grade in grades) / len(grades), 6)
            if grades
            else None
        ),
        "source": bundle["source"],
        "ledger_sha256": _file_sha256(ledger_path) if ledger_path.is_file() else None,
        "retrieval_qrels_created": False,
        "bge_retrieval_metrics_computable": False,
        "release_authorizing": False,
        "production_promotion_authorized": False,
        "recorded_at_utc": _now(),
    }
    receipt["receipt_digest"] = canonical_sha256(receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def _grade_controls(index: int) -> str:
    choices = (
        (3, "keep as written"),
        (2, "keep with a small edit"),
        (1, "rewrite"),
        (0, "remove"),
    )
    return "".join(
        f'<label class="choice"><input required type="radio" name="grade_{index}" '
        f'value="{grade}"><b>{grade}</b> {html.escape(label)}</label>'
        for grade, label in choices
    )


def render_html(
    bundle: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    completed: int,
    message: str = "",
) -> str:
    target = bundle["target"]
    total = len(bundle["candidates"])
    review_unit = str(bundle.get("review_unit") or "")
    is_whole_section = review_unit == REVIEW_UNIT_SECTION
    cards: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        rationale_controls = "".join(
            f'<label class="reason"><input required type="radio" name="reason_{index}" '
            f'value="{html.escape(reason, quote=True)}">{html.escape(reason)}</label>'
            for reason in RATIONALES
        )
        context = (
            ""
            if is_whole_section
            else f'<details><summary>Whole résumé section for context</summary><pre class="context">{html.escape(str(candidate["section_context"]))}</pre></details>'
        )
        card_heading = (
            "Complete final résumé section to rate"
            if is_whole_section
            else "Finished résumé text to rate"
        )
        prompt_subject = "complete final résumé section" if is_whole_section else "exact final résumé text"
        cards.append(
            f'''<article class="card"><p class="label">{html.escape(str(candidate["display_label"]))}</p>
<h2>{card_heading}</h2><pre class="final-text">{html.escape(str(candidate["final_text"]))}</pre>{context}
<fieldset><legend>For this target job, what should happen to this {prompt_subject}?</legend>{_grade_controls(index)}</fieldset>
<fieldset class="reasons"><legend>Why?</legend>{rationale_controls}</fieldset>
<label>Optional note <textarea name="note_{index}" rows="2" maxlength="1000" placeholder="Only if the choices above do not capture your reason"></textarea></label></article>'''
        )
    notice = f'<p class="notice">{html.escape(message)}</p>' if message else ""
    empty = (
        '<p class="notice">All final-output units in this frozen résumé are rated.</p>'
        if not cards
        else ""
    )
    save_button = '<button type="submit">Save this batch</button>' if cards else ""
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Final résumé output review</title><style>
body{{font:16px/1.45 system-ui,sans-serif;max-width:980px;margin:0 auto;padding:24px;background:#f5f7fb;color:#162033}}h1{{margin-bottom:4px}}.sub{{color:#526177;margin-top:0}}.target{{background:#eaf1fb;border-left:4px solid #1769aa;padding:14px;border-radius:8px}}.notice{{background:#e9f7ee;padding:12px;border-radius:8px}}.card{{background:#fff;border:1px solid #d6deeb;border-radius:12px;margin:18px 0;padding:18px;box-shadow:0 1px 3px #0001}}.label{{font-size:.85em;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#526177;margin-bottom:2px}}h2{{margin-top:0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}}.final-text{{background:#fbfcff;border-left:4px solid #1769aa;padding:12px;font-weight:650}}.context{{background:#fafafa;border:1px solid #e2e8f0;padding:12px}}details{{margin:14px 0}}summary{{cursor:pointer;font-weight:650}}fieldset{{border:0;padding:0;margin:16px 0 10px;display:flex;gap:8px;flex-wrap:wrap}}.choice,.reason{{border:1px solid #adb9cb;border-radius:7px;padding:7px 9px;cursor:pointer}}.choice:has(input:checked),.reason:has(input:checked){{background:#dceeff;border:2px solid #1769aa;padding:6px 8px}}.reasons{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}}textarea{{display:block;width:100%;box-sizing:border-box;margin-top:5px;font:inherit}}button{{font:600 17px system-ui;padding:13px 18px;border:0;border-radius:8px;background:#0b63a3;color:white;cursor:pointer}}</style><body>
<h1>Final résumé output review</h1><p class="sub">Completed: {completed} of {total} {'whole résumé sections' if is_whole_section else 'finished output units'}.</p>{notice}
<section class="target"><strong>Target job</strong><br>{html.escape(str(target["company"]))} — {html.escape(str(target["role"]))}<details open><summary>Job description used for this résumé</summary><pre>{html.escape(str(target["job_description"]))}</pre></details></section>
<p class="sub">Rate the whole visible section. Use the optional note only to identify a specific line or needed change.</p>
<form method="post">{''.join(cards)}{empty}{save_button}</form></body></html>'''


__all__ = [
    "EVENT_SCHEMA",
    "FinalResumeOutputReviewError",
    "RATIONALES",
    "REVIEW_UNIT_OUTPUT",
    "REVIEW_UNIT_SECTION",
    "SCOPE",
    "active_reviews",
    "append_reviews",
    "canonical_sha256",
    "load_final_resume_output_bundle",
    "render_html",
    "selected_rationale",
    "unreviewed",
    "write_progress_receipt",
    "_read_jsonl",
]
