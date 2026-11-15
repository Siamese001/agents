"""ECMA-376 OpenXML `.docx` renderer and compliance verifier for `apps_lic`.

Emits `executive_outreach_packet.docx` with `0o644` permissions, normalized POSIX `/`
paths, all required OpenXML package parts/relationships, and strict ECMA-376
`<w:pPr>` child element ordering (`w:pStyle -> w:keepNext -> w:pBdr -> w:spacing -> w:ind -> w:jc`).
"""

from __future__ import annotations

import os
import posixpath
import stat
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree

W_NS: Final[str] = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_NS: Final[str] = W_NS
_R_NS: Final[str] = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS: Final[str] = "http://schemas.openxmlformats.org/package/2006/relationships"
_XML_NS: Final[str] = "http://www.w3.org/XML/1998/namespace"

ElementTree.register_namespace("w", _W_NS)
ElementTree.register_namespace("r", _R_NS)

REQUIRED_DOCX_OPENXML_PARTS: Final[tuple[str, ...]] = (
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/_rels/document.xml.rels",
    "word/styles.xml",
    "word/settings.xml",
    "word/webSettings.xml",
    "word/fontTable.xml",
    "word/numbering.xml",
    "docProps/core.xml",
    "docProps/app.xml",
)

ECMA376_PPR_CHILD_ORDER: Final[tuple[str, ...]] = (
    "pStyle",
    "keepNext",
    "pBdr",
    "spacing",
    "ind",
    "jc",
)

_PPR_ORDER_INDEX: Final[dict[str, int]] = {
    name: idx for idx, name in enumerate(ECMA376_PPR_CHILD_ORDER)
}


def _qname(namespace: str, local_name: str) -> str:
    return f"{{{namespace}}}{local_name}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _append_paragraph(
    body: ElementTree.Element,
    text: str,
    *,
    style: str | None = None,
    keep_next: bool = False,
    bottom_border: bool = False,
    space_before: int | None = None,
    space_after: int | None = None,
    ind_left: int | None = None,
    ind_hanging: int | None = None,
    align: str | None = None,
) -> ElementTree.Element:
    """Append `<w:p>` with `<w:pPr>` children in strict ECMA-376 schema sequence."""
    paragraph = ElementTree.SubElement(body, _qname(_W_NS, "p"))
    if any((style is not None, keep_next, bottom_border, space_before is not None, space_after is not None, ind_left is not None, ind_hanging is not None, align is not None)):
        ppr = ElementTree.SubElement(paragraph, _qname(_W_NS, "pPr"))
        if style is not None:
            ElementTree.SubElement(ppr, _qname(_W_NS, "pStyle"), {_qname(_W_NS, "val"): style})
        if keep_next:
            ElementTree.SubElement(ppr, _qname(_W_NS, "keepNext"))
        if bottom_border:
            pbdr = ElementTree.SubElement(ppr, _qname(_W_NS, "pBdr"))
            ElementTree.SubElement(
                pbdr, _qname(_W_NS, "bottom"),
                {_qname(_W_NS, "val"): "single", _qname(_W_NS, "sz"): "6", _qname(_W_NS, "space"): "2", _qname(_W_NS, "color"): "1F3A5F"},
            )
        if space_before is not None or space_after is not None:
            attrs: dict[str, str] = {}
            if space_before is not None:
                attrs[_qname(_W_NS, "before")] = str(int(space_before))
            if space_after is not None:
                attrs[_qname(_W_NS, "after")] = str(int(space_after))
            ElementTree.SubElement(ppr, _qname(_W_NS, "spacing"), attrs)
        if ind_left is not None or ind_hanging is not None:
            ind_attrs: dict[str, str] = {}
            if ind_left is not None:
                ind_attrs[_qname(_W_NS, "left")] = str(int(ind_left))
            if ind_hanging is not None:
                ind_attrs[_qname(_W_NS, "hanging")] = str(int(ind_hanging))
            ElementTree.SubElement(ppr, _qname(_W_NS, "ind"), ind_attrs)
        if align is not None:
            ElementTree.SubElement(ppr, _qname(_W_NS, "jc"), {_qname(_W_NS, "val"): align})

    if text:
        run = ElementTree.SubElement(paragraph, _qname(_W_NS, "r"))
        node = ElementTree.SubElement(run, _qname(_W_NS, "t"))
        node.set(_qname(_XML_NS, "space"), "preserve")
        node.text = text
    return paragraph


def _normalize_touches_for_docx(sequence: Any = None, touches: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    raw_items: Any = touches
    if raw_items is None and sequence is not None:
        raw_items = sequence.get("touches") if isinstance(sequence, Mapping) else getattr(sequence, "touches", ())
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        raw_items = ()

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_items, start=1):
        draft_obj = getattr(item, "draft", item)
        t_num = int(getattr(item, "touch_number", idx) or idx)
        channel = getattr(item, "channel", None)
        day_offset = int(getattr(item, "day_offset", (idx - 1) * 4) or 0)
        objective = str(getattr(item, "objective", "") or "")
        if isinstance(item, Mapping):
            t_num = int(item.get("touch_number", t_num) or t_num)
            channel = item.get("channel", channel)
            day_offset = int(item.get("day_offset", day_offset) or 0)
            objective = str(item.get("objective", objective) or "")
        ch_str = str(getattr(channel, "value", channel) or "inmail")
        if isinstance(draft_obj, Mapping):
            subject = str(draft_obj.get("subject") or "")
            body = str(draft_obj.get("body") or "")
            raw_fids = draft_obj.get("cited_fact_ids") or draft_obj.get("grounded_facts_used") or draft_obj.get("fact_ids") or ()
        else:
            subject = str(getattr(draft_obj, "subject", "") or "")
            body = str(getattr(draft_obj, "body", "") or "")
            raw_fids = getattr(draft_obj, "cited_fact_ids", None) or getattr(draft_obj, "grounded_facts_used", None) or ()
        normalized.append({
            "touch_number": t_num,
            "day_offset": day_offset,
            "channel": ch_str,
            "objective": objective or f"Touch {t_num} executive outreach",
            "subject": subject or f"Executive Alignment — Touch {t_num}",
            "body": body,
            "cited_fact_ids": [str(f).strip() for f in raw_fids if str(f).strip()],
        })
    return normalized


def _build_document_xml(
    *,
    candidate_name: str,
    candidate_title: str,
    target_company: str,
    target_role: str,
    recipient_name: str,
    x3_disposition: str,
    touches: Sequence[Mapping[str, Any]],
    pct_certificates: Sequence[Mapping[str, Any]] = (),
    text: str = "",
) -> bytes:
    document = ElementTree.Element(_qname(_W_NS, "document"))
    body = ElementTree.SubElement(document, _qname(_W_NS, "body"))

    _append_paragraph(body, f"EXECUTIVE OUTREACH PACKET — {target_company.upper()}", style="Title", keep_next=True, space_before=0, space_after=40, align="center")
    _append_paragraph(body, f"{candidate_name} ({candidate_title}) | Target Role: {target_role} | Recipient: {recipient_name} | X3: {x3_disposition}", style="ContactLine", keep_next=True, space_before=0, space_after=100, align="center")
    _append_paragraph(body, "MULTI-TOUCH OUTREACH SEQUENCE", style="Heading1", keep_next=True, bottom_border=True, space_before=140, space_after=60, ind_left=0, align="left")

    if touches:
        for touch in touches:
            t_num = touch.get("touch_number", 1)
            ch = str(touch.get("channel") or "inmail").upper()
            day_off = touch.get("day_offset", 0)
            fids = ", ".join(touch.get("cited_fact_ids") or ()) or "verified_fact"
            _append_paragraph(body, f"Touch {t_num} (Day {day_off} | {ch}) — Subject: {touch.get('subject', '')}", style="RoleHeader", keep_next=True, space_before=100, space_after=20, ind_left=0, align="left")
            _append_paragraph(body, f"Cited Candidate Fact IDs: {fids} | Disposition: {x3_disposition}", style="RoleMeta", keep_next=True, space_before=0, space_after=40, ind_left=0, align="left")
            for para_line in str(touch.get("body") or "").splitlines():
                if para_line.strip():
                    _append_paragraph(body, para_line.strip(), style="Normal", space_before=20, space_after=45, ind_left=120, align="left")
    elif text.strip():
        for line in text.splitlines():
            if line.strip():
                _append_paragraph(body, line.strip(), style="Normal", space_before=20, space_after=45, ind_left=0, align="left")

    if pct_certificates:
        _append_paragraph(body, "PROOF-CARRYING TELEMETRY (PCT) CERTIFICATES", style="Heading1", keep_next=True, bottom_border=True, space_before=140, space_after=60, ind_left=0, align="left")
        for cert in pct_certificates:
            _append_paragraph(
                body,
                f"• {cert.get('certificate_id', 'pct_cert')}: metric={cert.get('metric_token', '')} | fact_id={cert.get('fact_id', '')} | in_cand={cert.get('in_cand', True)} | verified={cert.get('verified', True)}",
                style="Bullet", space_before=20, space_after=40, ind_left=240, ind_hanging=160, align="left",
            )

    section = ElementTree.SubElement(body, _qname(_W_NS, "sectPr"))
    ElementTree.SubElement(section, _qname(_W_NS, "pgSz"), {_qname(_W_NS, "w"): "12240", _qname(_W_NS, "h"): "15840"})
    ElementTree.SubElement(
        section, _qname(_W_NS, "pgMar"),
        {_qname(_W_NS, "top"): "720", _qname(_W_NS, "right"): "720", _qname(_W_NS, "bottom"): "720", _qname(_W_NS, "left"): "720", _qname(_W_NS, "header"): "360", _qname(_W_NS, "footer"): "360", _qname(_W_NS, "gutter"): "0"},
    )
    return ElementTree.tostring(document, encoding="utf-8", xml_declaration=True)


_CONTENT_TYPES_XML: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    b'<Default Extension="xml" ContentType="application/xml"/>'
    b'<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    b'<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    b'<Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>'
    b'<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
    b'<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
    b'<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    b'<Override PartName="/word/webSettings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml"/>'
    b"</Types>"
)

_PACKAGE_RELS_XML: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
    b'<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
    b"</Relationships>"
)

_DOCUMENT_RELS_XML: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
    b'<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/webSettings" Target="webSettings.xml"/>'
    b'<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/>'
    b'<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
    b"</Relationships>"
)

_CORE_PROPS_XML: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
    b"<dc:title>Executive Outreach Packet</dc:title><dc:creator>Outreach Engine</dc:creator><cp:revision>1</cp:revision></cp:coreProperties>"
)

_APP_PROPS_XML: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
    b"<Template>Normal.dotm</Template><Pages>1</Pages><Application>Microsoft Office Word</Application><AppVersion>16.0000</AppVersion></Properties>"
)

_SETTINGS_XML: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b'<w:zoom w:percent="100"/><w:defaultTabStop w:val="720"/><w:characterSpacingControl w:val="doNotCompress"/></w:settings>'
)

_WEB_SETTINGS_XML: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<w:webSettings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:allowPNG/></w:webSettings>'
)

_FONT_TABLE_XML: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<w:fonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b'<w:font w:name="Calibri"><w:panose1 w:val="020F0502020204030204"/><w:charset w:val="00"/><w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font></w:fonts>'
)

_NUMBERING_XML: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b'<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
    b'<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="&#8226;"/><w:lvlJc w:val="left"/>'
    b'<w:pPr><w:spacing w:before="20" w:after="40"/><w:ind w:left="360" w:hanging="180"/><w:jc w:val="left"/></w:pPr>'
    b'</w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'
)

_STYLES_XML: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b"<w:docDefaults>"
    b'<w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:color w:val="1A202C"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:rPrDefault>'
    b'<w:pPrDefault><w:pPr><w:spacing w:after="60" w:line="256" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
    b"</w:docDefaults>"
    b'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    b'<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="0" w:after="30"/><w:jc w:val="center"/></w:pPr></w:style>'
    b'<w:style w:type="paragraph" w:styleId="ContactLine"><w:name w:val="Contact Line"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="0" w:after="100"/><w:jc w:val="center"/></w:pPr></w:style>'
    b'<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="1F3A5F"/></w:pBdr><w:spacing w:before="140" w:after="60"/><w:ind w:left="0"/><w:jc w:val="left"/></w:pPr></w:style>'
    b'<w:style w:type="paragraph" w:styleId="RoleHeader"><w:name w:val="Role Header"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="100" w:after="20"/><w:ind w:left="0"/><w:jc w:val="left"/></w:pPr></w:style>'
    b'<w:style w:type="paragraph" w:styleId="RoleMeta"><w:name w:val="Role Meta"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="0" w:after="40"/><w:ind w:left="0"/><w:jc w:val="left"/></w:pPr></w:style>'
    b'<w:style w:type="paragraph" w:styleId="Bullet"><w:name w:val="Bullet"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="20" w:after="45"/><w:ind w:left="240" w:hanging="160"/><w:jc w:val="left"/></w:pPr></w:style>'
    b"</w:styles>"
)


def build_executive_outreach_docx(
    out_path: Path | str,
    *,
    sequence: Any = None,
    touches: Sequence[Any] | None = None,
    candidate_name: str = "Amit Ayer",
    candidate_title: str = "Enterprise AI & Platform Executive",
    target_company: str = "Citi",
    target_role: str = "Head of AI Strategy",
    recipient_name: str = "Executive Stakeholder",
    x3_disposition: str = "X3D_ALLOW_FINISH",
    pct_certificates: Sequence[Any] | None = None,
    text: str = "",
) -> str:
    """Build ECMA-376 compliant `executive_outreach_packet.docx` with `0o644` permissions and return POSIX path."""
    destination = Path(out_path).resolve()
    if destination.is_dir() or destination.suffix.lower() != ".docx":
        destination = destination / "executive_outreach_packet.docx"
    destination.parent.mkdir(parents=True, exist_ok=True)

    norm_touches = _normalize_touches_for_docx(sequence=sequence, touches=touches)
    norm_certs = [
        dict(c.to_dict()) if hasattr(c, "to_dict") and callable(c.to_dict) else dict(c)
        for c in (pct_certificates or ())
        if (hasattr(c, "to_dict") and callable(c.to_dict)) or isinstance(c, Mapping)
    ]

    doc_xml = _build_document_xml(
        candidate_name=candidate_name, candidate_title=candidate_title, target_company=target_company,
        target_role=target_role, recipient_name=recipient_name, x3_disposition=x3_disposition,
        touches=norm_touches, pct_certificates=norm_certs, text=text,
    )

    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
            archive.writestr("_rels/.rels", _PACKAGE_RELS_XML)
            archive.writestr("word/document.xml", doc_xml)
            archive.writestr("word/_rels/document.xml.rels", _DOCUMENT_RELS_XML)
            archive.writestr("word/styles.xml", _STYLES_XML)
            archive.writestr("word/settings.xml", _SETTINGS_XML)
            archive.writestr("word/webSettings.xml", _WEB_SETTINGS_XML)
            archive.writestr("word/fontTable.xml", _FONT_TABLE_XML)
            archive.writestr("word/numbering.xml", _NUMBERING_XML)
            archive.writestr("docProps/core.xml", _CORE_PROPS_XML)
            archive.writestr("docProps/app.xml", _APP_PROPS_XML)
        temporary.replace(destination)
        os.chmod(destination, 0o644)
    finally:
        temporary.unlink(missing_ok=True)
    return destination.as_posix()


def verify_docx_ecma376_compliance(docx_path: Path | str) -> dict[str, Any]:
    """Verify `.docx` archive parts, relationships, `0o644` permissions, and `<w:pPr>` child order."""
    path = Path(docx_path).resolve()
    posix_path = path.as_posix()
    violations: list[str] = []
    ppr_violations: list[str] = []

    if not path.is_file() or path.stat().st_size == 0:
        return {
            "passed": False, "is_valid": False, "status": "FAIL", "docx_path": posix_path,
            "mode_octal": "0000", "mode_is_0644": False, "permissions_0644": False,
            "required_parts_present": False, "missing_parts": list(REQUIRED_DOCX_OPENXML_PARTS),
            "present_parts": [], "part_count": 0, "ppr_order_valid": False,
            "ppr_violations": ["File missing or empty"], "ppr_order_violations": ["File missing or empty"],
            "ppr_checked_count": 0, "relationships_valid": False, "violations": ["DOCX file is missing or empty."],
        }

    imode = stat.S_IMODE(path.stat().st_mode)
    perms_ok = imode == 0o644
    if not perms_ok:
        violations.append(f"Expected file mode 0o644, observed {oct(imode)}")

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            if any("\\" in n for n in names):
                violations.append("Archive member paths contain Windows backslash separators.")
            missing = [req for req in REQUIRED_DOCX_OPENXML_PARTS if req not in names]
            if missing:
                violations.append(f"Missing required OpenXML parts: {missing}")

            rels_ok = True
            for rel_part, base_dir in (("_rels/.rels", ""), ("word/_rels/document.xml.rels", "word")):
                if rel_part not in names:
                    rels_ok = False
                    continue
                rel_root = ElementTree.fromstring(zf.read(rel_part))
                for rel_node in rel_root.findall(_qname(_PKG_REL_NS, "Relationship")):
                    target = str(rel_node.attrib.get("Target") or "").strip().lstrip("/")
                    resolved = posixpath.normpath(posixpath.join(base_dir, target)) if base_dir and not target.startswith("word/") else target
                    if resolved not in names:
                        rels_ok = False
                        violations.append(f"Unresolved relationship target '{target}' in {rel_part}")

            ppr_checked = 0
            for xml_part in ("word/document.xml", "word/styles.xml", "word/numbering.xml"):
                if xml_part not in names:
                    continue
                root = ElementTree.fromstring(zf.read(xml_part))
                for ppr in root.iter(_qname(_W_NS, "pPr")):
                    ppr_checked += 1
                    child_names = [_local_name(child.tag) for child in list(ppr)]
                    indices = [_PPR_ORDER_INDEX[name] for name in child_names if name in _PPR_ORDER_INDEX]
                    if indices != sorted(indices) or len(indices) != len(set(indices)):
                        seq_str = " -> ".join(f"w:{n}" for n in child_names)
                        msg = f"{xml_part}: <w:pPr> child sequence [{seq_str}] violates ECMA-376 order."
                        ppr_violations.append(msg)
                        violations.append(msg)
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        violations.append(f"Archive/XML parse failure: {exc}")
        return {
            "passed": False, "is_valid": False, "status": "FAIL", "docx_path": posix_path,
            "mode_octal": f"{imode:04o}", "mode_is_0644": perms_ok, "permissions_0644": perms_ok,
            "required_parts_present": False, "missing_parts": list(REQUIRED_DOCX_OPENXML_PARTS),
            "present_parts": [], "part_count": 0, "ppr_order_valid": False,
            "ppr_violations": ppr_violations, "ppr_order_violations": ppr_violations,
            "ppr_checked_count": 0, "relationships_valid": False, "violations": violations,
        }

    ppr_ok = len(ppr_violations) == 0 and ppr_checked > 0
    parts_ok = len(missing) == 0
    passed = perms_ok and parts_ok and rels_ok and ppr_ok and len(violations) == 0
    return {
        "passed": passed, "is_valid": passed, "status": "PASS" if passed else "FAIL",
        "docx_path": posix_path, "mode_octal": f"{imode:04o}", "mode_is_0644": perms_ok,
        "permissions_0644": perms_ok, "required_parts_present": parts_ok, "missing_parts": missing,
        "present_parts": list(names), "part_count": len(names), "ppr_order_valid": ppr_ok,
        "ppr_violations": ppr_violations, "ppr_order_violations": ppr_violations,
        "ppr_checked_count": ppr_checked, "relationships_valid": rels_ok, "violations": violations,
    }


export = build_executive_outreach_docx

__all__ = [
    "ECMA376_PPR_CHILD_ORDER",
    "REQUIRED_DOCX_OPENXML_PARTS",
    "W_NS",
    "build_executive_outreach_docx",
    "export",
    "verify_docx_ecma376_compliance",
]
