"""Wave 6 unit and integration tests for 4-format 0644 exports and 9-subcommand CLI parity."""

from __future__ import annotations

import csv
import json
import os
import stat
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from agents.cli import main as agents_cli_main
from apps_lic.__main__ import main as apps_lic_main
from apps_lic.runtime.final_outreach_docx import (
    ECMA376_PPR_CHILD_ORDER,
    REQUIRED_DOCX_OPENXML_PARTS,
    W_NS,
    build_executive_outreach_docx,
    verify_docx_ecma376_compliance,
)
from apps_lic.runtime.final_outreach_outputs import (
    FinalOutreachExportBundle,
    export_final_outreach_bundle,
)


def test_export_final_outreach_bundle_emits_4_formats_with_0644_and_posix_paths(tmp_path: Path) -> None:
    bundle = export_final_outreach_bundle(
        tmp_path,
        run_id="run_w6_test",
        mission_id="mission_citi_01",
        candidate_name="Amit Ayer",
        candidate_title="Enterprise AI & Platform Executive",
        target_company="Citi",
        target_role="Head of AI Strategy",
        recipient_name="Managing Director",
        x3_disposition="PROMOTE",
    )
    assert isinstance(bundle, FinalOutreachExportBundle)
    assert bundle.x3_disposition == "PROMOTE"

    expected_names = {
        "bundle_json": "outreach_sequence_bundle.json",
        "review_md": "outreach_sequence_review.md",
        "crm_csv": "crm_sequence_import.csv",
        "packet_docx": "executive_outreach_packet.docx",
    }
    for key, filename in expected_names.items():
        path_str = getattr(bundle, f"{key}_path")
        assert "\\" not in path_str, f"Non-POSIX path detected for {key}: {path_str}"
        assert path_str.endswith(f"/{filename}")
        artifact_file = tmp_path / filename
        assert artifact_file.is_file(), f"Missing exported artifact: {filename}"
        assert artifact_file.stat().st_size > 0
        mode = stat.S_IMODE(artifact_file.stat().st_mode)
        assert mode == 0o644, f"Expected 0o644 on {filename}, got {oct(mode)}"

    # 1. Inspect outreach_sequence_bundle.json
    bundle_payload = json.loads((tmp_path / "outreach_sequence_bundle.json").read_text(encoding="utf-8"))
    assert bundle_payload["run_id"] == "run_w6_test"
    assert bundle_payload["mission_id"] == "mission_citi_01"
    assert bundle_payload["x3_disposition"] == "PROMOTE"
    assert len(bundle_payload["touches"]) == 4
    assert len(bundle_payload["c0_allocations"]) >= 1
    assert len(bundle_payload["pct_certificates"]) >= 1
    assert bundle_payload["x2_report"]["passed"] is True
    assert bundle_payload["x1d_quorum_summary"]["quorum_passed"] is True
    for p_val in bundle_payload["artifact_paths"].values():
        assert "\\" not in p_val

    # 2. Inspect outreach_sequence_review.md
    review_text = (tmp_path / "outreach_sequence_review.md").read_text(encoding="utf-8")
    assert "# Executive Outreach Sequence Review Packet" in review_text
    assert "## Sequence Touches" in review_text
    assert "## X2 Cross-Touch Coherence & X1D Quorum Summary" in review_text

    # 3. Inspect crm_sequence_import.csv
    with (tmp_path / "crm_sequence_import.csv").open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == [
            "touch_number",
            "channel",
            "subject",
            "body",
            "cited_fact_ids",
            "x3_disposition",
        ]
        rows = list(reader)
    assert len(rows) == 4
    assert rows[0]["touch_number"] == "1"
    assert rows[0]["x3_disposition"] == "PROMOTE"
    assert rows[0]["cited_fact_ids"] != ""


def test_executive_outreach_packet_docx_ecma376_parts_and_ppr_ordering(tmp_path: Path) -> None:
    docx_path = tmp_path / "executive_outreach_packet.docx"
    posix_out = build_executive_outreach_docx(
        docx_path,
        candidate_name="Amit Ayer",
        candidate_title="Enterprise AI & Platform Executive",
        target_company="Citi",
        target_role="Head of AI Strategy",
        recipient_name="Managing Director",
        x3_disposition="PROMOTE",
        touches=[
            {
                "touch_number": 1,
                "day_offset": 0,
                "channel": "inmail",
                "objective": "Primary executive thesis",
                "subject": "Citi AI governance architecture",
                "body": "Scaled distributed banking platforms processing $4.2B annual volume with 99.995% reliability.",
                "cited_fact_ids": ["fact_01", "fact_02"],
                "x3_disposition": "PROMOTE",
            }
        ],
    )
    assert "\\" not in posix_out
    assert stat.S_IMODE(docx_path.stat().st_mode) == 0o644

    compliance = verify_docx_ecma376_compliance(docx_path)
    assert compliance["passed"] is True
    assert compliance["missing_parts"] == []
    assert compliance["ppr_order_violations"] == []

    required_ten_parts = {
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
    }
    assert required_ten_parts.issubset(set(REQUIRED_DOCX_OPENXML_PARTS))

    with zipfile.ZipFile(docx_path, "r") as zf:
        archive_names = set(zf.namelist())
        assert required_ten_parts.issubset(archive_names)
        for xml_part in ("word/document.xml", "word/styles.xml", "word/numbering.xml"):
            root = ET.fromstring(zf.read(xml_part))
            for ppr in root.iter(f"{{{W_NS}}}pPr"):
                ranks: list[int] = []
                for child in list(ppr):
                    local_name = child.tag.split("}", 1)[-1] if "}" in child.tag else child.tag
                    if local_name in ECMA376_PPR_CHILD_ORDER:
                        ranks.append(ECMA376_PPR_CHILD_ORDER.index(local_name))
                assert ranks == sorted(ranks), f"Out-of-order <w:pPr> children in {xml_part}: {ranks}"


def test_verify_docx_ecma376_compliance_rejects_bad_ppr_order_and_bad_permissions(tmp_path: Path) -> None:
    docx_path = tmp_path / "executive_outreach_packet.docx"
    build_executive_outreach_docx(
        docx_path,
        candidate_name="Amit Ayer",
        candidate_title="Enterprise AI & Platform Executive",
        target_company="Citi",
        target_role="Head of AI Strategy",
        recipient_name="Managing Director",
        x3_disposition="PROMOTE",
        touches=[
            {
                "touch_number": 1,
                "day_offset": 0,
                "channel": "inmail",
                "Subject": "Test",
                "body": "Grounded body.",
                "cited_fact_ids": ["fact_01"],
                "x3_disposition": "PROMOTE",
            }
        ],
    )
    os.chmod(docx_path, 0o600)
    perm_report = verify_docx_ecma376_compliance(docx_path)
    assert perm_report["passed"] is False
    assert perm_report["mode_is_0644"] is False

    # Mutate word/document.xml to place w:jc before w:pStyle inside w:pPr
    corrupt_docx = tmp_path / "corrupt_order.docx"
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(corrupt_docx, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                bad_xml = (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    f'<w:document xmlns:w="{W_NS}"><w:body><w:p>'
                    '<w:pPr><w:jc w:val="left"/><w:pStyle w:val="Normal"/></w:pPr>'
                    "</w:p></w:body></w:document>"
                ).encode("utf-8")
                zout.writestr(item, bad_xml)
            else:
                zout.writestr(item, data)
    os.chmod(corrupt_docx, 0o644)
    order_report = verify_docx_ecma376_compliance(corrupt_docx)
    assert order_report["passed"] is False
    assert len(order_report["ppr_order_violations"]) >= 1


def test_cli_9_subcommand_parity_and_validate_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = tmp_path / "cli_parity_run"

    # 1. run (offline-smoke + demo)
    rc_run = apps_lic_main(["run", "--demo", "--offline-smoke", "--artifact-dir", str(run_dir), "--json"])
    out_run = capsys.readouterr().out
    assert rc_run == 0
    run_payload = json.loads(out_run)
    assert run_payload["status"] == "PASSED"
    for fname in (
        "outreach_sequence_bundle.json",
        "outreach_sequence_review.md",
        "crm_sequence_import.csv",
        "executive_outreach_packet.docx",
    ):
        f_path = run_dir / fname
        assert f_path.is_file(), f"run did not emit {fname}"
        assert stat.S_IMODE(f_path.stat().st_mode) == 0o644

    # 2. show (test bundle, review, csv, docx, draft)
    for artifact_kind in ("draft", "bundle", "review", "csv", "docx"):
        rc_show = apps_lic_main(["show", "--run-dir", str(run_dir), "--artifact", artifact_kind, "--json"])
        out_show = capsys.readouterr().out
        assert rc_show == 0
        assert out_show.strip() != ""

    # 3. eval
    rc_eval = apps_lic_main(["eval", "--run-dir", str(run_dir), "--json"])
    out_eval = capsys.readouterr().out
    assert rc_eval == 0
    assert json.loads(out_eval)["status"] == "PASSED"

    # 4. validate (exits 0 on valid grounded input, non-zero on invalid/ungrounded input)
    valid_body = (
        "Charles, given Truist's focus on enterprise AI governance, I wanted to connect. "
        "As an AI/ML Engineering Leader, I have scaled distributed enterprise platforms processing "
        "$4.2B annual volume with 99.995% reliability across regulated financial ecosystems. "
        "Would you be open to a brief 15-minute exchange next week?"
    )
    rc_val_ok = apps_lic_main([
        "validate",
        "--company",
        "Truist",
        "--role",
        "EVP of Enterprise AI",
        "--priority",
        "enterprise AI governance",
        "--subject",
        "Truist enterprise AI governance",
        "--body",
        valid_body,
        "--json",
    ])
    out_val_ok = capsys.readouterr().out
    assert rc_val_ok == 0
    assert json.loads(out_val_ok)["passed"] is True

    rc_val_fail = apps_lic_main([
        "validate",
        "--company",
        "Truist",
        "--unverified",
        "--subject",
        "Guaranteed 10x ROI!",
        "--body",
        "I guarantee 999% revenue growth and $999T savings overnight for your quantum ledger team!",
        "--json",
    ])
    out_val_fail = capsys.readouterr().out
    assert rc_val_fail != 0
    assert json.loads(out_val_fail)["passed"] is False

    # 5. patch-run (subcommand and --patch-run flag alias)
    rc_patch = apps_lic_main(["patch-run", "--run-dir", str(run_dir), "--touches", "2", "--json"])
    out_patch = capsys.readouterr().out
    assert rc_patch == 0
    patch_data = json.loads(out_patch)
    assert patch_data["status"] == "PASSED"
    assert patch_data["patched_touches"] == [2]

    rc_patch_flag = apps_lic_main(["--patch-run", str(run_dir), "--touches", "3", "--json"])
    out_patch_flag = capsys.readouterr().out
    assert rc_patch_flag == 0
    assert json.loads(out_patch_flag)["patched_touches"] == [3]

    # 6. preflight (offline-smoke mode)
    rc_preflight = apps_lic_main(["preflight", "--offline-smoke", "--json"])
    out_preflight = capsys.readouterr().out
    assert rc_preflight == 0
    assert json.loads(out_preflight)["status"] == "PASSED"

    # 7. models
    rc_models = apps_lic_main(["models", "--json"])
    out_models = capsys.readouterr().out
    assert rc_models == 0
    models_data = json.loads(out_models)
    assert models_data["status"] == "PASSED"
    assert models_data["lane_count"] >= 4

    # 8. cache (stats + clear)
    cache_dir = tmp_path / "cache_test"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "entry.json").write_text("{}", encoding="utf-8")
    rc_cache_stats = apps_lic_main(["cache", "stats", "--cache-dir", str(cache_dir), "--json"])
    out_cache_stats = capsys.readouterr().out
    assert rc_cache_stats == 0
    assert json.loads(out_cache_stats)["entry_count"] == 1

    rc_cache_clear = apps_lic_main(["cache", "clear", "--cache-dir", str(cache_dir), "--json"])
    out_cache_clear = capsys.readouterr().out
    assert rc_cache_clear == 0
    assert json.loads(out_cache_clear)["cleared_entries"] == 1

    # 9. doctor (offline-smoke mode) and unified `agents outreach` routing
    rc_doctor = apps_lic_main(["doctor", "--offline-smoke", "--json"])
    out_doctor = capsys.readouterr().out
    assert rc_doctor == 0
    doctor_data = json.loads(out_doctor)
    assert doctor_data["overall_ok"] is True

    rc_agents_models = agents_cli_main(["outreach", "models", "--json"])
    out_agents_models = capsys.readouterr().out
    assert rc_agents_models == 0
    assert json.loads(out_agents_models)["status"] == "PASSED"
