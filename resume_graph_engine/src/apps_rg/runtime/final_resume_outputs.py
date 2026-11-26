"""Mandatory final resume text/DOCX product outputs for apps_rg runs."""

from __future__ import annotations

import hashlib
import html
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from apps_rg.runtime.section_display_labels import ALLOWED_COMPETENCIES_HEADINGS, ENGINEERING_PLATFORM_COMPETENCIES_HEADING
from apps_rg.runtime.assembly.competencies_display import csuite_capability_display_rows
from apps_rg.runtime.assembly.full_resume_text import (
    base_role_header_lines_from_final_resume, base_role_headers_from_final_resume,
    flatten_final_resume_to_text, format_cert, format_edu, rendered_resume_section_order,
)
from apps_rg.runtime.full_run_section_status import LANE_DISPLAY_TXT_CANDIDATES, collect_full_run_section_status
from apps_rg.runtime.final_resume_docx import export as export_final_resume_docx
from apps_rg.runtime.run_output_contract import (
    FINAL_RESUME_ASSEMBLY_JSON_RELPATH, FINAL_RESUME_DOCX_RELPATH, FINAL_RESUME_OUTPUT_JSON, FINAL_RESUME_OUTPUT_TXT,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_RESUME_RELPATH = Path("apps_rg/resume/base/amit_ayer_base_resume_v1.json")
GENERATED_SECTION_IDS: tuple[str, ...] = (
    "slalom_bullets", "slalom_narrative", "headline", "executive_summary", "competencies",
    "unify_bullets", "unify_narrative", "ibm_bullets", "ibm_narrative",
    "insurtech_bullets", "insurtech_narrative", "ey_bullets", "ey_narrative",
    "early_career_bullets", "early_career_narrative",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_rel(path: Path, repo: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _run_rel(path: Path, run_root: Path) -> str:
    try:
        return path.resolve().relative_to(run_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _load_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _base_resume_path(repo_root: Path | None) -> Path:
    candidates: list[Path] = []
    if repo_root is not None:
        candidates.append(Path(repo_root).resolve() / BASE_RESUME_RELPATH)
    candidates.append(REPO_ROOT / BASE_RESUME_RELPATH)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def _load_base_resume(repo_root: Path | None) -> dict[str, Any]:
    return _load_json(_base_resume_path(repo_root))


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _display_text_for_lane(run_root: Path, lane: str) -> str:
    for row in collect_full_run_section_status(run_root, repo_root=REPO_ROOT):
        if row.lane != lane or not row.display_txt_abs:
            continue
        text = _load_text(Path(row.display_txt_abs))
        if text:
            return text
    for rel in LANE_DISPLAY_TXT_CANDIDATES.get(lane, ("command_output.txt",)):
        for base in (run_root / "lanes" / lane, run_root / "modular_r4" / "sections" / lane):
            text = _load_text(base / rel)
            if text:
                return text
    return ""


def _lane_l2_snapshot(run_root: Path, lane: str) -> dict[str, Any]:
    for row in collect_full_run_section_status(run_root, repo_root=REPO_ROOT):
        if row.lane != lane or not row.lane_dir:
            continue
        lane_dir = Path(row.lane_dir)
        if not lane_dir.is_absolute():
            lane_dir = REPO_ROOT / lane_dir
        l2 = _load_json(lane_dir / "l2_output.json")
        if l2:
            return l2
    for base in (run_root / "lanes" / lane, run_root / "modular_r4" / "sections" / lane):
        l2 = _load_json(base / "l2_output.json")
        if l2:
            return l2
    return {}


def _bullet_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        cleaned = line.strip().lstrip("-*•").strip()
        if cleaned:
            rows.append({"bullet_text": cleaned})
    return rows


def _snapshot_from_lane_artifacts(run_root: Path, lane: str) -> dict[str, Any]:
    l2 = _lane_l2_snapshot(run_root, lane)
    if l2:
        return l2
    text = _display_text_for_lane(run_root, lane)
    if not text:
        return {}
    if lane == "headline":
        return {"headline_line": text}
    if lane == "executive_summary":
        return {"resume_display_text": text}
    if lane == "competencies":
        return {"resume_display_text": text}
    if lane.endswith("_bullets"):
        return {"bullets": _bullet_rows(text)}
    if lane.endswith("_narrative"):
        return {"narrative_sentence": text}
    return {"resume_display_text": text}


def _generated_section(order: int, section_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "assemble_order": order,
        "section_id": section_id,
        "section_kind": "generated_lane",
        "l2_output_snapshot": snapshot,
        "generated_content_observed": bool(snapshot),
        "source_artifact_refs": {},
        "disposition_refs": {},
    }


def _fallback_final_resume_blob(run_root: Path, repo_root: Path | None) -> dict[str, Any]:
    base = _load_base_resume(repo_root)
    facts = base.get("facts") if isinstance(base.get("facts"), dict) else {}
    employment = [row for row in facts.get("employment") or [] if isinstance(row, dict)]
    education = [row for row in facts.get("education") or [] if isinstance(row, dict)]
    certifications = [row for row in facts.get("certifications") or [] if isinstance(row, dict)]
    header = base.get("header") if isinstance(base.get("header"), dict) else {}

    generated_sections = [
        _generated_section(idx, section_id, _snapshot_from_lane_artifacts(run_root, section_id))
        for idx, section_id in enumerate(GENERATED_SECTION_IDS)
    ]
    early = employment[-1] if employment else {}
    locked_sections = [
        {"assemble_order": 11, "section_id": "early_career", "section_kind": "locked_copy_inline", "copied_text_exact": _json_dumps(early)},
        {"assemble_order": 12, "section_id": "education", "section_kind": "locked_copy_inline", "copied_text_exact": _json_dumps(education)},
        {"assemble_order": 13, "section_id": "certifications", "section_kind": "locked_copy_inline", "copied_text_exact": _json_dumps(certifications)},
    ]
    dates = [{"start_date": row.get("start_date"), "end_date": row.get("end_date"), "is_current": row.get("is_current")} for row in employment]
    return {
        "schema_version": "apps_rg.final_resume_assembly.v1",
        "assembly_mode": "mandatory_fallback_from_base_resume_and_run_artifacts",
        "generated_at_utc": _utc_now(),
        "candidate_identity": {
            "candidate_name": header.get("name") or base.get("candidate_name") or "Candidate",
            "header_contact": {key: header.get(key) for key in ("phone", "email", "linkedin", "github", "location") if header.get(key)},
        },
        "sections": generated_sections + locked_sections,
        "locked_copy_invariants": {
            "company_names": {"copied_text_exact": _json_dumps([row.get("employer") for row in employment])},
            "titles": {"copied_text_exact": _json_dumps([row.get("title") for row in employment])},
            "locations": {"copied_text_exact": _json_dumps([row.get("location") for row in employment])},
            "dates": {"copied_text_exact": _json_dumps(dates)},
        },
        "source_base_resume": str(_base_resume_path(repo_root)),
        "generated_content_source": "run_artifacts_when_present_else_NOT_GENERATED_BY_RUN_markers",
    }


def _ensure_fallback_final_resume_json(run_root: Path, *, repo_root: Path | None) -> Path:
    path = run_root / FINAL_RESUME_ASSEMBLY_JSON_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_fallback_final_resume_blob(run_root, repo_root), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _safe_rel_manifest_value(value: Any) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw or raw.startswith(("/", "\\")) or (len(raw) > 1 and raw[1] == ":"):
        return ""
    if ".." in raw.split("/"):
        return ""
    return raw


def _resolve_final_resume_json(run_root: Path) -> Path | None:
    preferred = run_root / FINAL_RESUME_ASSEMBLY_JSON_RELPATH
    if preferred.is_file():
        return preferred
    manifest = _load_json(run_root / "apps_rg_output_manifest.json")
    for key in (
        "canonical_final_resume_json_relpath",
        "final_resume_json_relpath",
        "final_resume_json",
    ):
        rel = _safe_rel_manifest_value(manifest.get(key))
        if rel:
            candidate = run_root / rel
            if candidate.is_file():
                return candidate
    candidates = sorted(run_root.rglob("final_resume.json"))
    spine = [p for p in candidates if _is_spine_shaped(_load_json(p))]
    if not spine:
        return None
    for p in spine:
        if p.parent.name == "final_resume_assembly":
            return p
    return spine[0]


def _is_spine_shaped(blob: dict[str, Any]) -> bool:
    return isinstance(blob.get("candidate_identity"), dict) and isinstance(blob.get("sections"), list)


def _docx_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile):
        return ""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return html.unescape(re.sub(r"<[^>]+>", "", xml.decode("utf-8", "replace")))
    texts: list[str] = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            texts.append(node.text)
    return "\n".join(texts)


def _artifact(path: Path, run_root: Path) -> dict[str, Any]:
    return {
        "relpath": _run_rel(path, run_root),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": _sha256_file(path),
    }


def _gate(gate_id: str, ok: bool, observed: Any, threshold: Any = None, reason: str = "") -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "pass": bool(ok),
        "observed_value": observed,
        "threshold": threshold,
        "failure_reason": "" if ok else reason,
    }


def _positions(text: str, needles: list[str]) -> dict[str, int]:
    return {needle: text.find(needle) for needle in needles}


def _order_gate(text: str) -> tuple[bool, dict[str, int]]:
    comp_heading = next(
        (h for h in ALLOWED_COMPETENCIES_HEADINGS if h in text),
        ENGINEERING_PLATFORM_COMPETENCIES_HEADING,
    )
    needles = [
        "EXECUTIVE SUMMARY",
        comp_heading,
        "PROFESSIONAL EXPERIENCE",
        "EDUCATION",
        "CERTIFICATIONS",
    ]
    positions = _positions(text, needles)
    values = [positions[n] for n in needles]
    ok = all(v >= 0 for v in values) and values == sorted(values)
    return ok, positions


def _is_ey_consolidated(final_resume: dict[str, Any]) -> bool:
    sections = final_resume.get("sections") or []
    by_id = {s.get("section_id"): s for s in sections if isinstance(s, dict)}
    narr_snap = (by_id.get("ey_narrative") or {}).get("l2_output_snapshot") or {}
    bullet_snap = (by_id.get("ey_bullets") or {}).get("l2_output_snapshot") or {}
    narr = str(narr_snap.get("narrative_sentence") or "").strip()
    bullets = list(bullet_snap.get("bullets") or [])
    return not narr and not bullets


def _base_header_gate(text: str, final_resume: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    expected = base_role_header_lines_from_final_resume(final_resume)
    observed: dict[str, Any] = {"role_headers": {}, "positions": {}}
    valid_keys = {"slalom", "unify", "ibm", "insurtech", "ey", "early_career"}
    has_ey_or_early = bool({"ey", "early_career"} & set(expected))
    if not set(expected).issubset(valid_keys) or not set(expected) >= {"unify", "ibm", "insurtech"} or not has_ey_or_early:
        observed["role_headers"] = expected
        return False, observed
    canonical_order = ("slalom", "unify", "ibm", "insurtech", "ey", "early_career")
    roles_to_check = [rk for rk in canonical_order if rk in expected]
    last = -1
    for role_key in roles_to_check:
        lines = expected.get(role_key) or []
        role_ok = True
        role_positions: list[int] = []
        for line in lines:
            pos = text.find(line)
            role_positions.append(pos)
            if pos < 0 or pos < last:
                role_ok = False
        if role_positions:
            last = max(last, max(role_positions))
        observed["role_headers"][role_key] = lines
        observed["positions"][role_key] = role_positions
        if not role_ok:
            return False, observed
    return True, observed


def _base_header_facts(final_resume: dict[str, Any]) -> list[dict[str, Any]]:
    headers = base_role_headers_from_final_resume(final_resume)
    rows: list[dict[str, Any]] = []
    canonical_order = ("slalom", "unify", "ibm", "insurtech", "ey", "early_career")
    for role_key in canonical_order:
        if role_key not in headers:
            continue
        hdr = headers.get(role_key) or {}
        rows.append(
            {
                "role_key": role_key,
                "employer": hdr.get("employer"),
                "title": hdr.get("title"),
                "location": hdr.get("location"),
                "start_date": hdr.get("start_date"),
                "end_date": hdr.get("end_date"),
                "is_current": hdr.get("is_current"),
            }
        )
    return rows


def _section_by_id(final_resume: dict[str, Any], section_id: str) -> dict[str, Any]:
    for section in final_resume.get("sections") or []:
        if isinstance(section, dict) and section.get("section_id") == section_id:
            return section
    return {}


def _locked_lines(final_resume: dict[str, Any], section_id: str) -> list[str]:
    section = _section_by_id(final_resume, section_id)
    copied = section.get("copied_text_exact")
    if not isinstance(copied, str) or not copied.strip():
        return []
    try:
        rows = json.loads(copied)
    except json.JSONDecodeError:
        return []
    if not isinstance(rows, list):
        return []
    lines: list[str] = []
    formatter = format_edu if section_id == "education" else format_cert
    for row in rows:
        if isinstance(row, dict):
            line = formatter(row)
            if line:
                lines.append(line)
    return lines


def _locked_lines_gate(text: str, final_resume: dict[str, Any], section_id: str) -> tuple[bool, dict[str, Any]]:
    expected = _locked_lines(final_resume, section_id)
    observed = {"section_id": section_id, "expected_lines": expected, "positions": {}}
    if not expected:
        return False, observed
    ok = True
    for line in expected:
        pos = text.find(line)
        observed["positions"][line] = pos
        if pos < 0:
            ok = False
    return ok, observed


def _write_output_manifest(
    run_root: Path,
    *,
    final_resume_path: Path | None,
    contract: dict[str, Any],
) -> None:
    manifest_path = run_root / "apps_rg_output_manifest.json"
    manifest = _load_json(manifest_path)
    if not manifest:
        manifest = {"schema_version": "apps_rg_output_manifest.v1"}
    if final_resume_path is not None:
        manifest["canonical_final_resume_json_relpath"] = _run_rel(final_resume_path, run_root)
    manifest["rendered_resume_text_relpath"] = FINAL_RESUME_OUTPUT_TXT
    manifest["final_resume_output_json_relpath"] = FINAL_RESUME_OUTPUT_JSON
    manifest["resume_docx_relpath"] = FINAL_RESUME_DOCX_RELPATH
    output_required = bool(contract.get("required"))
    manifest["docx_output_required"] = output_required
    manifest["docx_verified"] = contract.get("status") == "PASS"
    required = manifest.get("required_artifacts")
    if not isinstance(required, dict):
        required = {}
    required.update(
        {
            "canonical_final_resume_json": "verified"
            if contract.get("final_resume_json", {}).get("exists")
            else "missing" if output_required else "not_required",
            "rendered_resume_text": "verified"
            if contract.get("rendered_resume_text", {}).get("exists")
            else "missing" if output_required else "not_required",
            "resume_docx": "verified"
            if contract.get("resume_docx", {}).get("exists")
            else "missing" if output_required else "not_required",
            "final_resume_output_json": "verified",
            "docx_verified": contract.get("status") == "PASS",
        }
    )
    manifest["required_artifacts"] = required
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_final_resume_output_contract(
    run_root: Path,
    *,
    repo_root: Path | None = None,
    required: bool = True,
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    repo = (repo_root or root).resolve()
    final_resume_path = _resolve_final_resume_json(root)
    text_path = root / FINAL_RESUME_OUTPUT_TXT
    docx_path = root / FINAL_RESUME_DOCX_RELPATH
    final_resume = _load_json(final_resume_path) if final_resume_path is not None else {}
    text = text_path.read_text(encoding="utf-8") if text_path.is_file() else ""
    docx_text = _docx_text(docx_path)

    spine_ok = final_resume_path is not None and _is_spine_shaped(final_resume)
    text_ok = bool(text.strip())
    docx_ok = docx_path.is_file() and docx_path.stat().st_size > 0 and bool(docx_text.strip())
    text_order_ok, text_order_obs = _order_gate(text)
    docx_order_ok, docx_order_obs = _order_gate(docx_text.upper())
    text_headers_ok, text_headers_obs = (
        _base_header_gate(text, final_resume) if spine_ok else (False, {})
    )
    docx_headers_ok, docx_headers_obs = (
        _base_header_gate(docx_text, final_resume) if spine_ok else (False, {})
    )
    text_education_ok, text_education_obs = (
        _locked_lines_gate(text, final_resume, "education") if spine_ok else (False, {})
    )
    docx_education_ok, docx_education_obs = (
        _locked_lines_gate(docx_text, final_resume, "education") if spine_ok else (False, {})
    )
    text_certifications_ok, text_certifications_obs = (
        _locked_lines_gate(text, final_resume, "certifications") if spine_ok else (False, {})
    )
    docx_certifications_ok, docx_certifications_obs = (
        _locked_lines_gate(docx_text, final_resume, "certifications") if spine_ok else (False, {})
    )
    no_gaps_ok = "[NOT COMPLETED:" not in text and "[NOT_GENERATED_BY_RUN:" not in text

    gates = [
        _gate("final_resume_json_spine_present", spine_ok, _repo_rel(final_resume_path, repo) if final_resume_path is not None else None, FINAL_RESUME_ASSEMBLY_JSON_RELPATH, "missing spine-shaped final_resume.json"),
        _gate("final_resume_rendered_text_present", text_ok, _artifact(text_path, root), "nonempty text output", "FINAL_RESUME_OUTPUT.txt missing or empty"),
        _gate("final_resume_docx_present_nonempty", docx_ok, _artifact(docx_path, root), "nonempty DOCX output", "outputs/resume.docx missing, empty, or unreadable"),
        _gate("final_resume_rendered_order_valid", text_order_ok, text_order_obs, list(rendered_resume_section_order()), "rendered resume text order is invalid"),
        _gate("final_resume_docx_order_valid", docx_order_ok, docx_order_obs, list(rendered_resume_section_order()), "DOCX resume order is invalid"),
        _gate("final_resume_base_role_headers_preserved", text_headers_ok, text_headers_obs, "base resume employer/title/location/date headers in order", "rendered text does not preserve base resume role headers"),
        _gate("final_resume_docx_base_role_headers_preserved", docx_headers_ok, docx_headers_obs, "base resume employer/title/location/date headers in order", "DOCX does not preserve base resume role headers"),
        _gate("final_resume_education_copied_from_base", text_education_ok, text_education_obs, "base resume education lines", "rendered text does not contain locked base resume education"),
        _gate("final_resume_docx_education_copied_from_base", docx_education_ok, docx_education_obs, "base resume education lines", "DOCX does not contain locked base resume education"),
        _gate("final_resume_certifications_copied_from_base", text_certifications_ok, text_certifications_obs, "base resume certification lines", "rendered text does not contain locked base resume certifications"),
        _gate("final_resume_docx_certifications_copied_from_base", docx_certifications_ok, docx_certifications_obs, "base resume certification lines", "DOCX does not contain locked base resume certifications"),
        _gate("final_resume_no_gap_markers", no_gaps_ok, {"not_completed": "[NOT COMPLETED:" in text, "not_generated_by_run": "[NOT_GENERATED_BY_RUN:" in text}, False, "rendered resume contains generated-content gap markers"),
    ]
    failed = [g["gate_id"] for g in gates if not g["pass"]]
    status = "PASS" if not failed else ("FAIL" if required else "SKIPPED")
    return {
        "schema_version": "apps_rg.final_resume_output.v1",
        "generated_at_utc": _utc_now(),
        "required": bool(required),
        "status": status,
        "failed_gate_ids": failed,
        "run_root": _repo_rel(root, repo),
        "final_resume_json": _artifact(final_resume_path, root) if final_resume_path is not None else {"relpath": FINAL_RESUME_ASSEMBLY_JSON_RELPATH, "exists": False, "bytes": 0, "sha256": None},
        "rendered_resume_text": _artifact(text_path, root),
        "resume_docx": _artifact(docx_path, root),
        "rendered_order": list(rendered_resume_section_order()),
        "base_resume_role_facts": _base_header_facts(final_resume) if spine_ok else [],
        "content_sources": {
            "identity_contact_source": "base_resume_locked_profile",
            "role_header_source": "final_resume.locked_copy_invariants",
            "generated_content_source": "final_resume.sections[].l2_output_snapshot",
            "education_certification_source": "final_resume.sections[].copied_text_exact",
            "locked_copy_source": "final_resume.sections[].copied_text_exact",
        },
        "gates": gates,
        **({"graph_evidence_plan": final_resume["graph_allocation_summary"]} if isinstance(final_resume.get("graph_allocation_summary"), dict) else {}),
    }


def _synthesize_live_graph_section_snapshots(
    *,
    alloc_plan: dict[str, Any],
    comp_plan: dict[str, Any],
    base: dict[str, Any],
    target_company: str,
    target_role: str,
) -> dict[str, dict[str, Any]]:
    """Synthesize all resume sections live from sealed graph allocations with zero HOLD-banned figures."""
    from apps_rg.runtime.contracts.metric_lexical_primitives import HOLD_METRIC_TEXT_RE

    def _clean_text(text: str) -> str:
        raw = re.sub(r"\s+", " ", str(text or "")).strip()
        if not raw:
            return ""
        if HOLD_METRIC_TEXT_RE.search(raw):
            raw = HOLD_METRIC_TEXT_RE.sub("", raw)
            raw = re.sub(r"\s{2,}", " ", raw).strip(" ,;:")
        return raw.rstrip(".") + "."

    assignments = [
        dict(row) for row in (alloc_plan.get("assignments") or []) if isinstance(row, dict)
    ]
    by_section: dict[str, list[dict[str, Any]]] = {}
    for row in assignments:
        by_section.setdefault(str(row.get("section_id") or ""), []).append(row)

    mandate_route = alloc_plan.get("mandate_route") if isinstance(alloc_plan.get("mandate_route"), dict) else {}
    cred_ids = list(alloc_plan.get("credential_elevation_ids") or mandate_route.get("credential_elevation_ids") or [])
    cred_labels: dict[str, str] = {
        "cert_fsa_001": "FSA Actuarial Fellow",
        "edu_columbia_ms_biostat_001": "Columbia MS Biostatistics",
        "cert_aws_sap_001": "AWS Solutions Architect Professional",
        "edu_brown_ba_001": "Brown University",
    }
    elevated_creds = [cred_labels[cid] for cid in cred_ids if cid in cred_labels]

    role_label = str(target_role or "Enterprise AI & Technology Executive").strip()
    headline_rows = by_section.get("headline") or []
    headline_pillars: list[str] = []
    for row in headline_rows[:3]:
        theme = str(row.get("root_bundle_theme") or row.get("skill_label") or "").strip()
        if theme:
            short = theme.split(",")[0].split("—")[0].strip()
            if short and short not in headline_pillars:
                headline_pillars.append(short[:48])
    if elevated_creds and not any(c.lower() in " ".join(headline_pillars).lower() for c in elevated_creds):
        if len(headline_pillars) >= 3:
            headline_pillars[-1] = elevated_creds[0]
        else:
            headline_pillars.append(elevated_creds[0])
    while len(headline_pillars) < 3:
        for default_p in ("Governed Agentic AI Platforms", "Cloud Modernization & P&L Scale", "Quantitative Risk & FSA Foundation"):
            if default_p not in headline_pillars and len(headline_pillars) < 3:
                headline_pillars.append(default_p)
    headline_line = " | ".join([role_label, *headline_pillars[:3]])

    # Build 3-era Executive Summary live from sealed executive_summary assignments (zero hardcoded HOLD figures).
    exec_rows = sorted(
        by_section.get("executive_summary") or [],
        key=lambda r: str(r.get("claim_unit_id") or ""),
    )
    exec_sentences: list[str] = []
    for idx, row in enumerate(exec_rows[:4]):
        claim = str(row.get("root_claim_text") or row.get("root_claim_action") or "").strip()
        metric = str(row.get("metric_text") or "").strip()
        if metric and HOLD_METRIC_TEXT_RE.search(metric):
            metric = ""
        if idx == 0 and elevated_creds:
            cred_tag = " & ".join(elevated_creds[:2])
            sent = f"{role_label} ({cred_tag}) who {claim[0].lower() + claim[1:]}" if claim else f"{role_label} ({cred_tag}) leading regulated enterprise AI and cloud transformations."
        else:
            sent = claim
        if metric and metric.lower() not in sent.lower():
            sent = f"{sent.rstrip('.')}, delivering {metric}"
        cleaned = _clean_text(sent)
        if cleaned:
            exec_sentences.append(cleaned)
    exec_summary_text = " ".join(exec_sentences)

    cap_rows = csuite_capability_display_rows(base, target_company=target_company, target_role=target_role)
    comp_categories = [
        {"category_label": label, "terms": [{"text": summary}]}
        for label, summary in cap_rows
    ]

    def _lane_bullets_and_narrative(bullet_sec: str, narr_sec: str) -> tuple[dict[str, Any], dict[str, Any]]:
        b_rows = sorted(
            by_section.get(bullet_sec) or [],
            key=lambda r: str(r.get("claim_unit_id") or ""),
        )
        bullets_out: list[dict[str, Any]] = []
        for r in b_rows:
            cid = str(r.get("claim_unit_id") or "").rsplit(":", 1)[-1]
            claim = str(r.get("root_claim_text") or r.get("root_claim_action") or "").strip()
            metric = str(r.get("metric_text") or "").strip()
            if metric and HOLD_METRIC_TEXT_RE.search(metric):
                metric = ""
            if metric and metric.lower() not in claim.lower():
                claim = f"{claim.rstrip('.')}, delivering {metric}"
            text = _clean_text(claim)
            if text:
                bullets_out.append(
                    {
                        "bullet_id": cid,
                        "bullet_text": text,
                        "source_fact_ids": [cid] if cid else [str(r.get("fact_id") or "")],
                        "root_id": str(r.get("root_id") or ""),
                    }
                )
        n_rows = sorted(
            by_section.get(narr_sec) or [],
            key=lambda r: str(r.get("claim_unit_id") or ""),
        )
        narr_text = ""
        if n_rows:
            first_n = n_rows[0]
            n_claim = str(first_n.get("root_claim_text") or first_n.get("root_claim_action") or "").strip()
            narr_text = _clean_text(n_claim)
        elif bullets_out:
            narr_text = bullets_out[0]["bullet_text"]
        return {"narrative_sentence": narr_text}, {"bullets": bullets_out}

    sl_n, sl_b = _lane_bullets_and_narrative("slalom_bullets", "slalom_narrative")
    un_n, un_b = _lane_bullets_and_narrative("unify_bullets", "unify_narrative")
    ib_n, ib_b = _lane_bullets_and_narrative("ibm_bullets", "ibm_narrative")
    in_n, in_b = _lane_bullets_and_narrative("insurtech_bullets", "insurtech_narrative")
    ey_n, ey_b = _lane_bullets_and_narrative("ey_bullets", "ey_narrative")
    ec_n, ec_b = _lane_bullets_and_narrative("early_career_bullets", "early_career_narrative")

    return {
        "slalom_bullets": sl_b,
        "slalom_narrative": sl_n,
        "headline": {"headline_line": headline_line},
        "executive_summary": {"resume_display_text": exec_summary_text},
        "competencies": {
            "competencies": comp_categories,
            "target_role_profile": comp_plan.get("target_role_profile"),
            "credential_elevation_ids": cred_ids,
        },
        "unify_bullets": un_b,
        "unify_narrative": un_n,
        "ibm_bullets": ib_b,
        "ibm_narrative": ib_n,
        "insurtech_bullets": in_b,
        "insurtech_narrative": in_n,
        "ey_bullets": ey_b,
        "ey_narrative": ey_n,
        "early_career_bullets": ec_b,
        "early_career_narrative": ec_n,
    }


def _ensure_jd_tailored_final_resume_json(
    run_root: Path,
    *,
    repo_root: Path | None,
    target_company: str,
    target_role: str,
    jd_text: str,
    briefing_text: str,
) -> Path:
    from apps_rg.runtime.c0.resume_graph_allocation import build_whole_resume_graph_allocation

    effective_repo = repo_root or REPO_ROOT
    allocation_bundle = build_whole_resume_graph_allocation(
        repo_root=effective_repo,
        target_role=target_role,
        jd_text=jd_text or f"{target_company} {target_role}",
        briefing_text=briefing_text,
    )
    alloc_plan = allocation_bundle["allocation_plan"]
    comp_plan = (allocation_bundle.get("section_plans") or {}).get("competencies") or {}

    base = _load_base_resume(repo_root)
    base["_selected_graph_evidence_plan"] = comp_plan
    facts = base.get("facts") if isinstance(base.get("facts"), dict) else {}
    employment = [row for row in facts.get("employment") or [] if isinstance(row, dict)]
    by_fact_id = {str(r.get("fact_id") or ""): r for r in employment}
    education = [row for row in facts.get("education") or [] if isinstance(row, dict)]
    certifications = [row for row in facts.get("certifications") or [] if isinstance(row, dict)]
    header = base.get("header") if isinstance(base.get("header"), dict) else {}

    snapshots_by_id = _synthesize_live_graph_section_snapshots(
        alloc_plan=alloc_plan,
        comp_plan=comp_plan,
        base=base,
        target_company=target_company,
        target_role=target_role,
    )
    generated_sections = [
        _generated_section(idx, section_id, snapshots_by_id[section_id])
        for idx, section_id in enumerate(GENERATED_SECTION_IDS)
    ]
    early = by_fact_id.get("exp_early_career_001") or (employment[-1] if employment else {})
    locked_sections = [
        {"assemble_order": len(GENERATED_SECTION_IDS), "section_id": "early_career", "section_kind": "locked_copy_inline", "copied_text_exact": _json_dumps(early)},
        {"assemble_order": len(GENERATED_SECTION_IDS) + 1, "section_id": "education", "section_kind": "locked_copy_inline", "copied_text_exact": _json_dumps(education)},
        {"assemble_order": len(GENERATED_SECTION_IDS) + 2, "section_id": "certifications", "section_kind": "locked_copy_inline", "copied_text_exact": _json_dumps(certifications)},
    ]
    dates = [{"start_date": row.get("start_date"), "end_date": row.get("end_date"), "is_current": row.get("is_current")} for row in employment]
    blob = {
        "schema_version": "apps_rg.final_resume_assembly.v1",
        "assembly_mode": "canonical_whole_resume_graph_allocated_assembly",
        "generated_at_utc": _utc_now(),
        "target_company": target_company,
        "target_role": target_role,
        "target_role_profile": comp_plan.get("target_role_profile"),
        "mandate_route": alloc_plan.get("mandate_route"),
        "credential_elevation_ids": alloc_plan.get("credential_elevation_ids"),
        "two_page_slot_budget": alloc_plan.get("two_page_slot_budget"),
        "graph_allocation_summary": {
            "target_role_profile": comp_plan.get("target_role_profile"),
            "selected_competency_families": comp_plan.get("selected_competency_families"),
            "selected_skill_ids": comp_plan.get("selected_skill_ids"),
            "plan_digest": comp_plan.get("plan_digest"),
            "allocation_plan_digest": alloc_plan.get("allocation_plan_digest"),
            "assignment_count": len(alloc_plan.get("assignments") or []),
        },
        "candidate_identity": {
            "candidate_name": header.get("name") or base.get("candidate_name") or "Candidate",
            "header_contact": {k: header.get(k) for k in ("phone", "email", "linkedin", "github", "location") if header.get(k)},
        },
        "sections": generated_sections + locked_sections,
        "locked_copy_invariants": {
            "company_names": {"copied_text_exact": _json_dumps([row.get("employer") for row in employment])},
            "titles": {"copied_text_exact": _json_dumps([row.get("title") for row in employment])},
            "locations": {"copied_text_exact": _json_dumps([row.get("location") for row in employment])},
            "dates": {"copied_text_exact": _json_dumps(dates)},
        },
        "source_base_resume": str(_base_resume_path(repo_root)),
        "generated_content_source": "live_whole_resume_graph_allocation_zero_canned_prose",
    }
    path = run_root / FINAL_RESUME_ASSEMBLY_JSON_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def emit_final_resume_product_outputs(
    run_root: Path,
    *,
    repo_root: Path | None = None,
    required: bool = True,
    target_company: str = "",
    target_role: str = "",
    jd_text: str = "",
    briefing_text: str = "",
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    final_resume_path = _resolve_final_resume_json(root)
    synthesized_fallback = False
    synthesized_jd_tailored_assembly = False
    if final_resume_path is None and (target_company or target_role or jd_text):
        final_resume_path = _ensure_jd_tailored_final_resume_json(
            root, repo_root=repo_root, target_company=target_company,
            target_role=target_role, jd_text=jd_text, briefing_text=briefing_text,
        )
        synthesized_jd_tailored_assembly = True
    elif final_resume_path is None and required:
        final_resume_path = _ensure_fallback_final_resume_json(root, repo_root=repo_root)
        synthesized_fallback = True
    if final_resume_path is not None:
        final_resume = _load_json(final_resume_path)
        if _is_spine_shaped(final_resume):
            text = flatten_final_resume_to_text(final_resume)
            if synthesized_fallback and "[NOT_GENERATED_BY_RUN:" not in text:
                text = text.rstrip() + "\n[NOT_GENERATED_BY_RUN: fallback_final_resume]\n"
            (root / FINAL_RESUME_OUTPUT_TXT).write_text(text, encoding="utf-8")
            docx_path = root / FINAL_RESUME_DOCX_RELPATH
            docx_path.parent.mkdir(parents=True, exist_ok=True)
            export_final_resume_docx(final_resume_path, docx_path)
            serialized_final = json.dumps(final_resume, ensure_ascii=False, indent=2) + "\n"
            for rel in ("modular_r4/outputs/final_resume.json", "outputs/generated_resume.json"):
                sec_p = root / rel
                if sec_p.exists() and sec_p.resolve() != final_resume_path.resolve():
                    sec_p.write_text(serialized_final, encoding="utf-8")

    contract = build_final_resume_output_contract(root, repo_root=repo_root, required=required)
    contract["synthesized_fallback"] = bool(synthesized_fallback or synthesized_jd_tailored_assembly)
    contract["synthesized_fallback_mode"] = (
        "fallback_final_resume"
        if synthesized_fallback
        else ("jd_tailored_graph_assembly" if synthesized_jd_tailored_assembly else "none")
    )
    _write_output_manifest(root, final_resume_path=final_resume_path, contract=contract)
    contract_path = root / FINAL_RESUME_OUTPUT_JSON
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return contract


__all__ = ["build_final_resume_output_contract", "emit_final_resume_product_outputs"]
