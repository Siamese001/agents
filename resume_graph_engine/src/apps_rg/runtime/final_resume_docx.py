"""Standalone DOCX renderer for the authoritative final-resume spine.

The standalone repository does not ship the historical ``ops_scripts``
exporter.  This module keeps DOCX production inside the importable runtime and
uses only the Python standard library to write the small OOXML package.  Text
comes exclusively from the same flattener used by the full-resume judges, so
the renderer cannot invent, omit, or reorder resume claims.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from apps_rg.runtime.section_display_labels import (
    ALLOWED_COMPETENCIES_HEADINGS,
    CERTIFICATIONS_AND_CREDENTIALS_HEADING,
    CSUITE_FIVE_SECTION_HEADINGS,
    ENGINEERING_PLATFORM_COMPETENCIES_HEADING,
)
from apps_rg.runtime.assembly.full_resume_text import (
    flatten_csuite_five_section_resume_to_text,
    flatten_final_resume_to_text,
)

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XML_NS = "http://www.w3.org/XML/1998/namespace"

ElementTree.register_namespace("w", _W_NS)
ElementTree.register_namespace("r", _R_NS)


def _qname(namespace: str, local_name: str) -> str:
    return f"{{{namespace}}}{local_name}"


def _load_spine(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read final resume JSON at {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"final resume JSON at {path} is not an object")
    return raw


def _is_spine_blob(blob: dict[str, Any]) -> bool:
    identity = blob.get("candidate_identity")
    sections = blob.get("sections")
    return (
        isinstance(identity, dict)
        and bool(str(identity.get("candidate_name") or "").strip())
        and isinstance(sections, list)
        and any(isinstance(section, dict) for section in sections)
    )


def _is_spine_shaped(path: Path) -> bool:
    """Return whether ``path`` is a non-hollow final-resume spine."""

    try:
        return _is_spine_blob(_load_spine(Path(path)))
    except ValueError:
        return False


def _resolve_final_resume(arg: str | Path) -> Path:
    """Resolve a file or run directory to its authoritative spine JSON."""

    path = Path(arg)
    if path.is_file():
        if _is_spine_shaped(path):
            return path
        raise ValueError(
            f"final_resume.json at {path} is not spine-shaped "
            "(candidate identity and nonempty list sections are required)"
        )

    candidates = sorted(path.rglob("final_resume.json"))
    spine = [candidate for candidate in candidates if _is_spine_shaped(candidate)]
    if not spine:
        raise ValueError(
            "No spine-shaped final_resume.json (candidate_identity + list sections) "
            f"under {path}; found {[str(candidate) for candidate in candidates]}."
        )
    preferred = [candidate for candidate in spine if candidate.parent.name == "final_resume_assembly"]
    return preferred[0] if preferred else spine[0]


def _paragraph(body: ElementTree.Element, text: str, *, style: str | None = None) -> None:
    paragraph = ElementTree.SubElement(body, _qname(_W_NS, "p"))
    if style:
        properties = ElementTree.SubElement(paragraph, _qname(_W_NS, "pPr"))
        ElementTree.SubElement(
            properties,
            _qname(_W_NS, "pStyle"),
            {_qname(_W_NS, "val"): style},
        )
    if not text:
        return
    run = ElementTree.SubElement(paragraph, _qname(_W_NS, "r"))
    node = ElementTree.SubElement(run, _qname(_W_NS, "t"))
    node.set(_qname(_XML_NS, "space"), "preserve")
    node.text = text


def _document_xml(text: str) -> bytes:
    document = ElementTree.Element(_qname(_W_NS, "document"))
    body = ElementTree.SubElement(document, _qname(_W_NS, "body"))
    heading_lines = {
        "HEADLINE",
        "EXECUTIVE SUMMARY",
        *ALLOWED_COMPETENCIES_HEADINGS,
        *CSUITE_FIVE_SECTION_HEADINGS,
        *(f"{idx}. {h}" for idx, h in enumerate(CSUITE_FIVE_SECTION_HEADINGS, start=1)),
        "PROFESSIONAL EXPERIENCE",
        "EDUCATION",
        CERTIFICATIONS_AND_CREDENTIALS_HEADING,
    }
    for index, line in enumerate(text.splitlines()):
        style = "Title" if index == 0 else "Heading1" if line in heading_lines else None
        _paragraph(body, line, style=style)

    section = ElementTree.SubElement(body, _qname(_W_NS, "sectPr"))
    ElementTree.SubElement(
        section,
        _qname(_W_NS, "pgSz"),
        {_qname(_W_NS, "w"): "12240", _qname(_W_NS, "h"): "15840"},
    )
    ElementTree.SubElement(
        section,
        _qname(_W_NS, "pgMar"),
        {
            _qname(_W_NS, "top"): "720",
            _qname(_W_NS, "right"): "720",
            _qname(_W_NS, "bottom"): "720",
            _qname(_W_NS, "left"): "720",
            _qname(_W_NS, "header"): "360",
            _qname(_W_NS, "footer"): "360",
            _qname(_W_NS, "gutter"): "0",
        },
    )
    return ElementTree.tostring(document, encoding="utf-8", xml_declaration=True)


_CONTENT_TYPES_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""

_PACKAGE_RELS_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

_DOCUMENT_RELS_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

_STYLES_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="80"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:jc w:val="center"/><w:spacing w:after="80"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="180" w:after="60"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="1F3A5F"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>
  </w:style>
</w:styles>
"""


def export(final_resume_path: Path, out_path: Path) -> Path:
    """Render a validated spine JSON to a self-contained DOCX package."""

    source = Path(final_resume_path).resolve()
    blob = _load_spine(source)
    if not _is_spine_blob(blob):
        raise ValueError(
            f"final_resume.json at {source} is not spine-shaped "
            "(missing candidate_identity.candidate_name or nonempty list sections); "
            "refusing to emit a hollow DOCX"
        )
    rendered = flatten_final_resume_to_text(blob)
    destination = Path(out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
            archive.writestr("_rels/.rels", _PACKAGE_RELS_XML)
            archive.writestr("word/document.xml", _document_xml(rendered))
            archive.writestr("word/_rels/document.xml.rels", _DOCUMENT_RELS_XML)
            archive.writestr("word/styles.xml", _STYLES_XML)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def export_csuite_five_section_docx(
    base_resume: dict[str, Any],
    out_path: Path,
    *,
    target_company: str = "",
    target_role: str = "",
) -> Path:
    """Render the 5-section Seven-Figure C-Suite Executive Resume to a DOCX package."""
    rendered = flatten_csuite_five_section_resume_to_text(
        base_resume,
        target_company=target_company,
        target_role=target_role,
    )
    destination = Path(out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
            archive.writestr("_rels/.rels", _PACKAGE_RELS_XML)
            archive.writestr("word/document.xml", _document_xml(rendered))
            archive.writestr("word/_rels/document.xml.rels", _DOCUMENT_RELS_XML)
            archive.writestr("word/styles.xml", _STYLES_XML)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def validate_csuite_five_section_text(text: str) -> dict[str, Any]:
    """Deterministically verify all 5 C-suite section gates on rendered text."""
    numbered_headings = [f"{idx}. {h}" for idx, h in enumerate(CSUITE_FIVE_SECTION_HEADINGS, start=1)]
    positions = {h: text.find(h) for h in numbered_headings}
    order_ok = all(v >= 0 for v in positions.values()) and list(positions.values()) == sorted(positions.values())
    value_bar_ok = all(
        token in text
        for token in (
            "$82M+ COMMERCIAL P&L",
            "+20% MARGIN & COST",
            "106-ENGINEER SCALE",
            "VELOCITY & SAFETY",
        )
    )
    flagship_absorbed_ok = (
        "FLAGSHIP PRODUCTION AI PLATFORMS" not in text.upper()
        and "<250ms" in text
        and "106-software-engineer" in text
        and "Universal Write Gateway" in text
    )
    sec3_pos = positions.get(numbered_headings[2], -1)
    sec4_pos = positions.get(numbered_headings[3], -1)
    sec5_pos = positions.get(numbered_headings[4], -1)
    sec3_body = text[sec3_pos:sec4_pos] if (sec3_pos >= 0 and sec4_pos > sec3_pos) else ""
    sec4_body = text[sec4_pos:sec5_pos] if (sec4_pos >= 0 and sec5_pos > sec4_pos) else ""
    sec5_body = text[sec5_pos:] if sec5_pos >= 0 else ""

    core_2017_split_ok = (
        all(emp in sec3_body for emp in ("Slalom", "Unify Consulting", "IBM"))
        and "Mandate:" in sec3_body
        and all(emp in sec4_body for emp in ("InsurTech Cloud Solutions", "Ernst & Young"))
        and "Earlier Quantitative Foundation:" in sec4_body
    )
    sec5_lines = [ln for ln in sec5_body.splitlines() if "EDUCATION, ACTUARIAL CHARTER" not in ln]
    sec5_years = re.findall(r"\b(?:19|20)\d{2}\b", "\n".join(sec5_lines))
    dateless_footer_ok = (
        bool(sec5_lines)
        and len(sec5_years) == 0
        and "Fellow of the Society of Actuaries (FSA)" in sec5_body
    )
    checks = {
        "five_section_order": order_ok,
        "four_column_value_bar": value_bar_ok,
        "flagship_platforms_absorbed": flagship_absorbed_ok,
        "experience_2017_split_and_capsule": core_2017_split_ok,
        "dateless_credentials_footer": dateless_footer_ok,
    }
    failed = [k for k, v in checks.items() if not v]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "heading_positions": positions,
        "section5_year_tokens": sec5_years,
    }


__all__ = [
    "_is_spine_shaped",
    "_resolve_final_resume",
    "export",
    "export_csuite_five_section_docx",
    "validate_csuite_five_section_text",
]
