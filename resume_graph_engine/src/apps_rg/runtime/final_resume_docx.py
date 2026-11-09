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
    ENGINEERING_PLATFORM_COMPETENCIES_HEADING,
)
from apps_rg.runtime.assembly.full_resume_text import (
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
        "PROFESSIONAL EXPERIENCE",
        "EDUCATION",
        CERTIFICATIONS_AND_CREDENTIALS_HEADING,
    }
    raw_lines = [ln for ln in text.splitlines() if ln.strip()]
    for index, line in enumerate(raw_lines):
        stripped = line.strip()
        if index == 0:
            style: str | None = "Title"
        elif index == 1 and ("@" in stripped or "linkedin.com" in stripped or "github.com" in stripped or "+1" in stripped):
            style = "ContactLine"
        elif stripped in heading_lines:
            style = "Heading1"
        elif " \u2014 " in stripped and not stripped.startswith("\u2022") and len(stripped) < 120:
            style = "RoleHeader"
        elif " | " in stripped and ("\u2013" in stripped or "Present" in stripped) and len(stripped) < 90:
            style = "RoleMeta"
        elif stripped.startswith("\u2022"):
            style = "Bullet"
        else:
            style = None
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
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/webSettings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml"/>
</Types>
"""

_PACKAGE_RELS_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""

_DOCUMENT_RELS_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/webSettings" Target="webSettings.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/>
</Relationships>
"""

_CORE_PROPS_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Executive Resume</dc:title>
  <dc:creator>Resume Engine</dc:creator>
  <cp:revision>1</cp:revision>
</cp:coreProperties>
"""

_APP_PROPS_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Template>Normal.dotm</Template>
  <TotalTime>0</TotalTime>
  <Pages>2</Pages>
  <Application>Microsoft Office Word</Application>
  <DocSecurity>0</DocSecurity>
  <ScaleCrop>false</ScaleCrop>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>16.0000</AppVersion>
</Properties>
"""

_SETTINGS_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/>
  <w:defaultTabStop w:val="720"/>
  <w:characterSpacingControl w:val="doNotCompress"/>
  <w:compat>
    <w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
  </w:compat>
</w:settings>
"""

_WEB_SETTINGS_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:webSettings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:allowPNG/>
</w:webSettings>
"""

_FONT_TABLE_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:fonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:font w:name="Calibri">
    <w:panose1 w:val="020F0502020204030204"/>
    <w:charset w:val="00"/>
    <w:family w:val="swiss"/>
    <w:pitch w:val="variable"/>
  </w:font>
</w:fonts>
"""

_STYLES_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:color w:val="1A202C"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="60" w:line="256" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="0" w:after="30"/><w:jc w:val="center"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="0F2537"/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ContactLine">
    <w:name w:val="Contact Line"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="0" w:after="100"/><w:jc w:val="center"/></w:pPr>
    <w:rPr><w:color w:val="334E68"/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:keepNext/><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="1F3A5F"/></w:pBdr><w:spacing w:before="140" w:after="60"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="1F3A5F"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="RoleHeader">
    <w:name w:val="Role Header"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="100" w:after="20"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="0F2537"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="RoleMeta">
    <w:name w:val="Role Meta"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="0" w:after="40"/></w:pPr>
    <w:rPr><w:i/><w:color w:val="4A5568"/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Bullet">
    <w:name w:val="Bullet"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="20" w:after="45"/><w:ind w:left="240" w:hanging="160"/></w:pPr>
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
            archive.writestr("docProps/core.xml", _CORE_PROPS_XML)
            archive.writestr("docProps/app.xml", _APP_PROPS_XML)
            archive.writestr("word/document.xml", _document_xml(rendered))
            archive.writestr("word/_rels/document.xml.rels", _DOCUMENT_RELS_XML)
            archive.writestr("word/styles.xml", _STYLES_XML)
            archive.writestr("word/settings.xml", _SETTINGS_XML)
            archive.writestr("word/webSettings.xml", _WEB_SETTINGS_XML)
            archive.writestr("word/fontTable.xml", _FONT_TABLE_XML)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


__all__ = [
    "_is_spine_shaped",
    "_resolve_final_resume",
    "export",
]
