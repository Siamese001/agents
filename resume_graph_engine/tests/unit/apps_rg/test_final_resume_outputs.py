from __future__ import annotations

import json
from pathlib import Path

from apps_rg.runtime.final_resume_outputs import emit_final_resume_product_outputs
from apps_rg.runtime.run_output_contract import (
    FINAL_RESUME_ASSEMBLY_JSON_RELPATH,
    FINAL_RESUME_DOCX_RELPATH,
    FINAL_RESUME_OUTPUT_JSON,
    FINAL_RESUME_OUTPUT_TXT,
)


def _section(order: int, section_id: str, snapshot: dict) -> dict:
    return {
        "assemble_order": order,
        "section_id": section_id,
        "section_kind": "generated_lane",
        "l2_output_snapshot": snapshot,
        "section_hash": "h",
        "section_digest": "d",
        "source_artifact_refs": {"l2_output.json": "x"},
        "disposition_refs": {"generated_lane": {"x3_disposition_json": "x", "rollup_lane_key": section_id}},
    }


def _final_resume_blob() -> dict:
    base_companies = [
        "Slalom",
        "Unify Consulting",
        "IBM",
        "InsurTech Cloud Solutions",
        "Ernst & Young",
        "Early Career Roles",
    ]
    base_titles = [
        "Senior Director",
        "SVP Engineering, Agentic AI Platforms",
        "Partner",
        "Chief Technology Officer",
        "Principal",
        "Actuarial Consultant and Quantitative Roles",
    ]
    base_locations = ["Boca Raton, FL", "Boca Raton, FL", "Edgewater, NJ", "New York, NY", "New York, NY", "Philadelphia, PA"]
    base_dates = [
        {"start_date": "2026-06", "end_date": "present", "is_current": True},
        {"start_date": "2023-02", "end_date": "2026-06", "is_current": False},
        {"start_date": "2017-04", "end_date": "2022-10", "is_current": False},
        {"start_date": "2014-04", "end_date": "2017-03", "is_current": False},
        {"start_date": "2009-10", "end_date": "2014-03", "is_current": False},
        {"start_date": "2002-10", "end_date": "2009-09", "is_current": False},
    ]
    wrong = {"employer": "WrongCo", "title": "WrongTitle", "location": "Nowhere", "start_date": "1900-01", "end_date": "1901-01"}
    education = [
        {"degree": "Master of Science in Biostatistics", "institution": "Columbia University", "honors": "Graduated with Distinction"},
        {"degree": "Bachelor of Arts in Biology", "institution": "Brown University", "honors": "Graduated Cum Laude"},
    ]
    certifications = [
        {"name": "Certified Machine Learning Engineer - Associate", "issuing_organization": "AWS", "year": "2025"},
        {"name": "Databricks Lakehouse Fundamentals Accreditation", "year": "2023"},
        {"name": "Certified Solutions Architect - Professional", "issuing_organization": "AWS", "year": "2023"},
        {"name": "Fellow of the Society of Actuaries", "year": "2010"},
    ]
    return {
        "candidate_identity": {
            "candidate_name": "Amit Ayer",
            "header_contact": {
                "phone": "+1-917-239-3830",
                "email": "amitayer1@gmail.com",
                "linkedin": "linkedin.com/in/amitayer1",
                "github": "https://github.com/Siamese001/",
                "location": "Boca Raton, FL",
            },
        },
        "sections": [
            _section(0, "slalom_narrative", {"slalom_header": wrong, "narrative_sentence": "Generated Slalom narrative."}),
            _section(1, "slalom_bullets", {"slalom_header": wrong, "bullets": [{"bullet_text": "Generated Slalom bullet."}]}),
            _section(2, "headline", {"headline_line": "Generated Headline"}),
            _section(3, "executive_summary", {"resume_display_text": "Generated executive summary."}),
            _section(
                4,
                "competencies",
                {"competencies": [{"category_label": "AI Platforms", "terms": [{"text": "Agentic AI platforms"}]}]},
            ),
            _section(5, "unify_narrative", {"unify_header": wrong, "narrative_sentence": "Generated Unify narrative."}),
            _section(6, "unify_bullets", {"unify_header": wrong, "bullets": [{"bullet_text": "Generated Unify bullet."}]}),
            _section(7, "ibm_narrative", {"ibm_header": wrong, "narrative_sentence": "Generated IBM narrative."}),
            _section(8, "ibm_bullets", {"ibm_header": wrong, "bullets": [{"bullet_text": "Generated IBM bullet."}]}),
            _section(9, "insurtech_narrative", {"insurtech_header": wrong, "narrative_sentence": "Generated InsurTech narrative."}),
            _section(10, "insurtech_bullets", {"insurtech_header": wrong, "bullets": [{"bullet_text": "Generated InsurTech bullet."}]}),
            _section(11, "ey_narrative", {"ey_header": wrong, "narrative_sentence": "Generated EY narrative."}),
            _section(12, "ey_bullets", {"ey_header": wrong, "bullets": [{"bullet_text": "Generated EY bullet."}]}),
            {
                "assemble_order": 13,
                "section_id": "early_career",
                "section_kind": "locked_copy_inline",
                "copied_text_exact": json.dumps({"role_narrative": "Base early career narrative.", "bullets": [{"text": "Base early bullet."}]}),
            },
            {
                "assemble_order": 14,
                "section_id": "education",
                "section_kind": "locked_copy_inline",
                "copied_text_exact": json.dumps(education),
            },
            {
                "assemble_order": 15,
                "section_id": "certifications",
                "section_kind": "locked_copy_inline",
                "copied_text_exact": json.dumps(certifications),
            },
        ],
        "locked_copy_invariants": {
            "company_names": {"copied_text_exact": json.dumps(base_companies)},
            "titles": {"copied_text_exact": json.dumps(base_titles)},
            "locations": {"copied_text_exact": json.dumps(base_locations)},
            "dates": {"copied_text_exact": json.dumps(base_dates)},
        },
    }


def _write_final_resume(run: Path) -> Path:
    path = run / FINAL_RESUME_ASSEMBLY_JSON_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_final_resume_blob(), indent=2) + "\n", encoding="utf-8")
    return path


def test_final_resume_outputs_preserve_base_facts_and_docx_order(tmp_path: Path) -> None:
    _write_final_resume(tmp_path)

    contract = emit_final_resume_product_outputs(tmp_path, repo_root=tmp_path, required=True)

    assert contract["status"] == "PASS"
    assert (tmp_path / FINAL_RESUME_OUTPUT_TXT).is_file()
    assert (tmp_path / FINAL_RESUME_OUTPUT_JSON).is_file()
    assert (tmp_path / FINAL_RESUME_DOCX_RELPATH).is_file()
    text = (tmp_path / FINAL_RESUME_OUTPUT_TXT).read_text(encoding="utf-8")
    assert text.index("EXECUTIVE SUMMARY") < text.index("ENGINEERING & PLATFORM COMPETENCIES")
    assert text.index("ENGINEERING & PLATFORM COMPETENCIES") < text.index("PROFESSIONAL EXPERIENCE")
    assert "Slalom \u2014 Senior Director" in text
    assert "Unify Consulting - SVP Engineering" not in text
    assert "Unify Consulting \u2014 SVP Engineering, Agentic AI Platforms" in text
    assert "IBM \u2014 Partner" in text
    assert "WrongCo" not in text
    assert "Master of Science in Biostatistics, Columbia University" in text
    assert "Fellow of the Society of Actuaries, 2010" in text
    gate_ids = {g["gate_id"]: g["pass"] for g in contract["gates"]}
    assert gate_ids["final_resume_docx_order_valid"] is True
    assert gate_ids["final_resume_docx_base_role_headers_preserved"] is True
    assert gate_ids["final_resume_docx_education_copied_from_base"] is True
    assert gate_ids["final_resume_docx_certifications_copied_from_base"] is True


def test_final_resume_outputs_replace_stale_failed_contract(tmp_path: Path) -> None:
    """A later deterministic assembly must replace, not trust, old output verdicts."""
    _write_final_resume(tmp_path)
    (tmp_path / "apps_rg_output_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "apps_rg_output_manifest.v1",
                "docx_output_required": True,
                "docx_verified": False,
                "required_artifacts": {"docx_verified": False},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / FINAL_RESUME_OUTPUT_JSON).write_text(
        json.dumps({"status": "FAIL", "failed_gate_ids": ["final_resume_no_gap_markers"]}),
        encoding="utf-8",
    )

    contract = emit_final_resume_product_outputs(tmp_path, repo_root=tmp_path, required=True)

    assert contract["status"] == "PASS"
    manifest = json.loads((tmp_path / "apps_rg_output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["docx_verified"] is True
    assert manifest["required_artifacts"]["docx_verified"] is True


def test_final_resume_outputs_synthesize_required_failed_run_package(tmp_path: Path) -> None:
    contract = emit_final_resume_product_outputs(tmp_path, repo_root=tmp_path, required=True)

    assert contract["required"] is True
    assert contract["status"] == "FAIL"
    assert (tmp_path / FINAL_RESUME_ASSEMBLY_JSON_RELPATH).is_file()
    assert (tmp_path / FINAL_RESUME_OUTPUT_TXT).is_file()
    assert (tmp_path / FINAL_RESUME_OUTPUT_JSON).is_file()
    assert (tmp_path / FINAL_RESUME_DOCX_RELPATH).is_file()

    text = (tmp_path / FINAL_RESUME_OUTPUT_TXT).read_text(encoding="utf-8")
    assert "AMIT AYER" in text.upper()
    assert "+1-917-239-3830" in text
    assert "Slalom \u2014 Senior Director" in text
    assert "Boca Raton, FL | Jun 2026 \u2013 Present" in text
    assert "Unify Consulting \u2014 SVP Engineering, Agentic AI Platforms" in text
    assert "Boca Raton, FL | Feb 2023 \u2013 Jun 2026" in text
    assert "Master of Science in Biostatistics, Columbia University" in text
    assert "Fellow of the Society of Actuaries, 2010" in text
    assert "[NOT_GENERATED_BY_RUN:" in text

    gate_ids = {g["gate_id"]: g["pass"] for g in contract["gates"]}
    assert gate_ids["final_resume_json_spine_present"] is True
    assert gate_ids["final_resume_rendered_text_present"] is True
    assert gate_ids["final_resume_docx_present_nonempty"] is True
    assert gate_ids["final_resume_no_gap_markers"] is False


def test_final_resume_docx_ecma376_ppr_order_and_python_docx_load(tmp_path: Path) -> None:
    import zipfile
    from xml.etree import ElementTree
    import docx

    _write_final_resume(tmp_path)
    contract = emit_final_resume_product_outputs(tmp_path, repo_root=tmp_path, required=True)
    assert contract["status"] == "PASS"

    docx_path = tmp_path / FINAL_RESUME_DOCX_RELPATH
    doc = docx.Document(str(docx_path))
    assert len(doc.paragraphs) >= 10
    assert doc.paragraphs[0].text == "Amit Ayer"
    assert doc.paragraphs[2].style.name == "Role Header"
    assert doc.paragraphs[2].alignment == docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER

    order_rank = {"pStyle": 1, "keepNext": 2, "pBdr": 3, "spacing": 4, "ind": 5, "jc": 6}
    with zipfile.ZipFile(docx_path) as zf:
        names = set(zf.namelist())
        for required_part in (
            "[Content_Types].xml",
            "_rels/.rels",
            "docProps/core.xml",
            "docProps/app.xml",
            "word/document.xml",
            "word/_rels/document.xml.rels",
            "word/styles.xml",
            "word/settings.xml",
            "word/webSettings.xml",
            "word/fontTable.xml",
        ):
            assert required_part in names

        for xml_part in ("word/styles.xml", "word/document.xml"):
            root = ElementTree.fromstring(zf.read(xml_part))
            for ppr in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr"):
                child_ranks = [
                    order_rank[child.tag.split("}")[-1]]
                    for child in list(ppr)
                    if child.tag.split("}")[-1] in order_rank
                ]
                assert child_ranks == sorted(child_ranks), f"Out-of-order <w:pPr> children in {xml_part}: {child_ranks}"


def test_cross_section_x2_locked_copy_escaped_em_dash_and_self_collision(tmp_path: Path) -> None:
    from apps_rg.runtime.aggregation.cross_section_x2 import build_overlap_artifacts, run_cross_section_x2_gates

    blob = _final_resume_blob()
    # Add identical claim_ledger and bullets in slalom_bullets to verify zero intra-section self-collision
    for sec in blob["sections"]:
        if sec.get("section_id") == "slalom_bullets":
            sec["l2_output_snapshot"]["claim_ledger"] = [
                {"claim_text": "Generated Slalom bullet.", "source_fact_ids": ["bul_slalom_001"]}
            ]
            sec["l2_output_snapshot"]["bullets"] = [
                {"bullet_id": "b1", "bullet_text": "Generated Slalom bullet.", "source_fact_ids": ["bul_slalom_001"]}
            ]
        elif sec.get("section_id") == "early_career":
            # Default json.dumps escapes \u2014 as \\u2014
            sec["copied_text_exact"] = json.dumps(
                {"role_narrative": "Base early career narrative.", "bullets": [{"text": "Base early bullet \u2014 my work."}]}
            )

    _, removed, _, decisions = build_overlap_artifacts(final_resume_blob=blob, sealed_index={}, repo=tmp_path)
    assert removed == []
    assert decisions == []

    gates, *_ = run_cross_section_x2_gates(repo=tmp_path, final_resume_blob=blob, fingerprint={}, sealed_index={})
    em_gate = next(g for g in gates if g.gate_id == "x2_cross_section_no_em_dash")
    assert em_gate.verdict == "FAIL"
    assert em_gate.decisive_reason == "em dash and first-person pronoun present in assembled corpus"


def test_cross_section_x2_no_undefined_mga_acronym(tmp_path: Path) -> None:
    from apps_rg.runtime.aggregation.cross_section_x2 import run_cross_section_x2_gates

    # Test 1: Bare MGAs without definition must fail
    blob_fail = _final_resume_blob()
    for sec in blob_fail["sections"]:
        if sec.get("section_id") == "insurtech_narrative":
            sec["l2_output_snapshot"]["narrative_sentence"] = (
                "Directed cloud-native architecture across P&C carriers and MGAs."
            )
            sec["l2_output_snapshot"]["claim_ledger"] = [
                {"claim_text": "Directed cloud-native architecture across P&C carriers and MGAs.", "source_fact_ids": ["f1"]}
            ]

    gates_fail, *_ = run_cross_section_x2_gates(repo=tmp_path, final_resume_blob=blob_fail, fingerprint={}, sealed_index={})
    mga_gate_fail = next(g for g in gates_fail if g.gate_id == "x2_cross_section_no_undefined_mga_acronym")
    assert mga_gate_fail.verdict == "FAIL"
    assert "undefined acronym MGA/MGAs" in mga_gate_fail.decisive_reason

    # Test 2: Defined MGAs (e.g. managing general agents (MGAs)) must pass
    blob_pass = _final_resume_blob()
    for sec in blob_pass["sections"]:
        if sec.get("section_id") == "insurtech_narrative":
            sec["l2_output_snapshot"]["narrative_sentence"] = (
                "Directed cloud-native architecture across P&C carriers and managing general agents (MGAs)."
            )
            sec["l2_output_snapshot"]["claim_ledger"] = [
                {"claim_text": "Directed cloud-native architecture across P&C carriers and managing general agents (MGAs).", "source_fact_ids": ["f1"]}
            ]

    gates_pass, *_ = run_cross_section_x2_gates(repo=tmp_path, final_resume_blob=blob_pass, fingerprint={}, sealed_index={})
    mga_gate_pass = next(g for g in gates_pass if g.gate_id == "x2_cross_section_no_undefined_mga_acronym")
    assert mga_gate_pass.verdict == "PASS"
    assert mga_gate_pass.decisive_reason is None



