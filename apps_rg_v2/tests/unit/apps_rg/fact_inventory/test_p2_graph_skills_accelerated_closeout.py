"""P2-ACCELERATED-CLOSEOUT unit and receipt validators."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import apps_rg.fact_inventory.p2_graph_skills_accelerated_closeout as closeout_module

from apps_rg.fact_inventory.p2_graph_skills_accelerated_closeout import (
    ALL_SECTIONS,
    run_full_closeout,
    write_p2_rebaseline,
    write_p2_w1a_all_sections,
)
from apps_rg.runtime.sections.graph_evidence_contract import SECTION_KEYS
from apps_rg.fact_inventory.track_weighted_graph_expansion import ROOT
from apps_rg.runtime.proof_pool_resolver import resolve_section_proof_pool
from apps_rg.runtime.section_graph_skills_proof_pool import (
    GraphSkillSelectorBindingError,
)
from apps_rg.runtime.validators.graph_skills_proof_common import (
    GraphSkillsProofError,
    assert_pool_not_ledger_authority,
    validate_section_graph_pool,
)

REPO = ROOT

_CLOSEOUT_OUTPUT_NAMES = (
    "REBASELINE_JSON",
    "REBASELINE_MD",
    "W1A_JSON",
    "W1A_MD",
    "W2_JSON",
    "W3_JSON",
    "W4_JSON",
    "W5_JSON",
    "W6_JSON",
    "W7_JSON",
    "W8_JSON",
    "W9_JSON",
    "W10_JSON",
    "CLOSEOUT_JSON",
    "CLOSEOUT_MD",
    "RCA_IBM_UNIFY_JSON",
    "RCA_UNIFY_BULLETS_JSON",
)

_TEST_ONLY_RECEIPT_MODE = "TEST_ONLY_NONCANONICAL_OUTPUT"
_EXPECTED_SELECTOR_BLOCKED = frozenset({"unify_bullets", "ibm_bullets"})
_EXPECTED_RECEIPT_BLOCKED = _EXPECTED_SELECTOR_BLOCKED
_EXPECTED_SELECTOR_CONSTRAINT = {
    "unify_bullets": "section_fact_role_episode_root_coverage",
    "ibm_bullets": "selector_root_section_fact_parity",
}


def _write_test_upstream_receipts(base: Path) -> tuple[Path, Path]:
    upstream_dir = base / "upstream"
    upstream_dir.mkdir()
    p1_w4 = upstream_dir / "career_track_p1_w4_closeout_receipt.json"
    p1_w5 = upstream_dir / "career_track_p1_w5_track_balanced_sections_receipt.json"
    common = {
        "receipt_mode": _TEST_ONLY_RECEIPT_MODE,
        "certification_eligible": False,
    }
    p1_w4.write_text(
        json.dumps(
            {
                **common,
                "schema": "career_track_p1_w4_closeout_receipt_v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    p1_w5.write_text(
        json.dumps(
            {
                **common,
                "schema": "career_track_p1_w5_track_balanced_sections_receipt_v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return p1_w4, p1_w5


def _assert_test_only_output(path: Path) -> None:
    assert path.is_file(), path
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["receipt_mode"] == _TEST_ONLY_RECEIPT_MODE
        assert payload["certification_eligible"] is False
    else:
        markdown = path.read_text(encoding="utf-8")
        assert f"Receipt mode:** {_TEST_ONLY_RECEIPT_MODE}" in markdown
        assert "Certification eligible:** False" in markdown


@pytest.fixture(autouse=True)
def _proof_pool_fixture_dev_bypass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.spine.front_contracts import (
        activate_fixture_dev_bypass,
        deactivate_fixture_dev_bypass,
    )

    activate_fixture_dev_bypass(non_product_certified=True)
    for name in _CLOSEOUT_OUTPUT_NAMES:
        original = Path(getattr(closeout_module, name))
        monkeypatch.setattr(closeout_module, name, tmp_path / original.name)
    monkeypatch.setenv(
        "APPS_RG_AUGMENTED_SKILLS_GRAPH_SQLITE_PATH",
        str(tmp_path / "augmented_skills_graph.sqlite"),
    )
    monkeypatch.setenv(
        "APPS_RG_C03_GRAPH_SQLITE_CONTEXT_RECEIPT_DIR",
        str(tmp_path / "c03_context_receipts"),
    )
    for name in (
        "APPS_RG_WHOLE_RUN_ENVELOPE",
        "APPS_RG_MODULAR_R4_SECTIONS_ROOT",
        "APPS_RG_RESUME_GRAPH_ALLOCATION_PLAN",
        "APPS_RG_SECTION_FINAL_GRAPH_EVIDENCE_CONTRACTS",
    ):
        monkeypatch.delenv(name, raising=False)
    yield
    deactivate_fixture_dev_bypass()


@pytest.mark.parametrize(
    "section_id",
    tuple(s for s in SECTION_KEYS if s != "executive_summary"),
)
def test_all_sections_default_graph_pool(section_id: str) -> None:
    if section_id in _EXPECTED_SELECTOR_BLOCKED:
        with pytest.raises(GraphSkillSelectorBindingError) as exc_info:
            resolve_section_proof_pool(
                section=section_id,
                repo_root=REPO,
                product_visible=False,
            )
        receipt = exc_info.value.receipt
        assert receipt["section_id"] == section_id
        assert receipt["fail_closed"] is True
        assert receipt["unsatisfied_constraints"] == [
            _EXPECTED_SELECTOR_CONSTRAINT[section_id]
        ]
        return
    pool = resolve_section_proof_pool(
        section=section_id,
        repo_root=REPO,
        product_visible=False,
    )
    summary = validate_section_graph_pool(pool)
    assert summary["proof_source"] == "augmented_skills_graph"
    assert summary["broad_skills_ledger_used_as_authority"] is False


def test_legacy_ledger_flag_rejected() -> None:
    with pytest.raises(ValueError, match="legacy_broad_skills_ledger"):
        resolve_section_proof_pool(
            section="headline",
            repo_root=REPO,
            legacy_broad_skills_ledger=True,
            product_visible=False,
        )


def test_p2_rebaseline_artifact() -> None:
    doc = write_p2_rebaseline(repo_root=REPO)
    assert doc["broad_skills_ledger_product_authority_prohibited"] is True
    assert doc["global_c03_bound_claimed"] is False
    _assert_test_only_output(closeout_module.REBASELINE_JSON)
    _assert_test_only_output(closeout_module.REBASELINE_MD)


def test_p2_w1a_all_sections_receipt() -> None:
    doc = write_p2_w1a_all_sections(repo_root=REPO)
    assert doc["status"] == "BLOCKED"
    assert doc["all_sections_default_to_augmented_skills_graph"] is False
    assert set(doc["blocked_sections"]) == _EXPECTED_RECEIPT_BLOCKED
    assert doc["broad_skills_ledger_used_as_authority_anywhere"] is False
    assert {
        section
        for section, row in doc["sections"].items()
        if row.get("status") == "BLOCKED"
    } == _EXPECTED_RECEIPT_BLOCKED
    for section, constraint in _EXPECTED_SELECTOR_CONSTRAINT.items():
        row = doc["sections"][section]
        assert row["blocker_type"] == "GraphSkillSelectorBindingError"
        assert row["failure_receipt"]["unsatisfied_constraints"] == [constraint]
        assert row["failure_receipt"]["fail_closed"] is True
    _assert_test_only_output(closeout_module.W1A_JSON)
    _assert_test_only_output(closeout_module.W1A_MD)


def test_accelerated_closeout_skip_live(tmp_path: Path) -> None:
    p1_w4, p1_w5 = _write_test_upstream_receipts(tmp_path)
    competencies_out_dir = tmp_path / "competencies_p2"
    out = run_full_closeout(
        repo_root=REPO,
        skip_live=True,
        competencies_out_dir=competencies_out_dir,
        p1_w4_closeout_path=p1_w4,
        p1_w5_projection_path=p1_w5,
    )
    assert out["status"] == "BLOCKED"
    assert set(out["blocked_authority_sections"]) == _EXPECTED_RECEIPT_BLOCKED
    assert set(out["wave_receipt_bindings"]) == set(closeout_module._WAVE_SCHEMAS)
    for name in _CLOSEOUT_OUTPUT_NAMES:
        _assert_test_only_output(Path(getattr(closeout_module, name)))
    for wave, binding in out["wave_receipt_bindings"].items():
        bound_path = closeout_module._wave_output_paths()[wave]
        bound_payload = json.loads(bound_path.read_text(encoding="utf-8"))
        assert binding["ref"] == str(bound_path.resolve()).replace("\\", "/")
        assert binding["raw_sha256"] == hashlib.sha256(bound_path.read_bytes()).hexdigest()
        assert binding["schema"] == bound_payload["schema"]
        assert binding["status"] == bound_payload["status"]
        assert binding["receipt_mode"] == _TEST_ONLY_RECEIPT_MODE
        assert binding["certification_eligible"] is False
    w2 = json.loads(closeout_module.W2_JSON.read_text(encoding="utf-8"))
    assert set(w2["sections"].keys()) == set(ALL_SECTIONS)
    competencies_receipt = Path(out["competencies_p2_w1a_receipt"])
    assert competencies_receipt.parent == competencies_out_dir
    assert out["competencies_p2_w1a_receipt_raw_sha256"] == hashlib.sha256(
        competencies_receipt.read_bytes()
    ).hexdigest()
    assert out["competencies_p2_w1a_receipt_mode"] == _TEST_ONLY_RECEIPT_MODE
    assert out["competencies_p2_w1a_certification_eligible"] is False
    for path in competencies_out_dir.iterdir():
        _assert_test_only_output(path)

    closeout_module.validate_p2_closeout_receipt(out, repo_root=REPO)
    missing_binding = json.loads(json.dumps(out))
    missing_binding["wave_receipt_bindings"].pop("P2-W4")
    with pytest.raises(
        closeout_module.P2CloseoutValidationError,
        match="wave_receipt_bindings must contain every P2 wave",
    ):
        closeout_module.validate_p2_closeout_receipt(missing_binding, repo_root=REPO)

    closeout_module.W4_JSON.write_text(
        closeout_module.W4_JSON.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        closeout_module.P2CloseoutValidationError,
        match="P2-W4 raw_sha256 mismatch",
    ):
        closeout_module.validate_p2_closeout_receipt(out, repo_root=REPO)


def test_blocked_graph_rows_cannot_claim_w1a_or_w10_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_rows = {
        section: {
            "section_id": section,
            "status": "BLOCKED",
            "proof_source": "augmented_skills_graph",
            "broad_skills_ledger_used_as_authority": False,
        }
        for section in ALL_SECTIONS
    }
    monkeypatch.setattr(
        closeout_module,
        "_resolve_all_section_pools",
        lambda **_kwargs: blocked_rows,
    )

    w1a = closeout_module.write_p2_w1a_all_sections(repo_root=REPO)
    w10 = closeout_module.write_p2_w10_audit(repo_root=REPO)

    assert w1a["status"] == "BLOCKED"
    assert w1a["all_sections_default_to_augmented_skills_graph"] is False
    assert set(w1a["blocked_sections"]) == set(ALL_SECTIONS)
    assert w10["status"] == "BLOCKED"
    assert w10["package_audit_status"] == "BLOCKED"
    assert set(w10["unsupported_or_blocked_sections"]) == set(ALL_SECTIONS)


def test_canonical_blocked_receipt_is_not_certification_eligible() -> None:
    canonical_path = next(
        path for path in closeout_module._CANONICAL_OUTPUT_PATHS if path.suffix == ".json"
    )
    doc = {"schema": "test_only_probe_v1", "status": "BLOCKED"}

    closeout_module._stamp_receipt(canonical_path, doc)

    assert doc["receipt_mode"] == "CANONICAL"
    assert doc["certification_eligible"] is False


def test_w9_all_pass_rows_with_ledger_authority_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _row(section: str) -> dict[str, object]:
        return {
            "section_id": section,
            "status": "PASS",
            "broad_skills_ledger_used_as_authority": section == "headline",
        }

    monkeypatch.setattr(
        closeout_module,
        "_executive_summary_accepted_live_row",
        lambda **_kwargs: _row("executive_summary"),
    )
    monkeypatch.setattr(
        closeout_module,
        "probe_latest_run_for_section",
        lambda section, **_kwargs: _row(section),
    )
    monkeypatch.setattr(
        closeout_module,
        "write_p2_w10_audit",
        lambda **_kwargs: {"status": "PASS"},
    )
    monkeypatch.setattr(
        closeout_module,
        "write_p2_w9_ibm_unify_runtime_rca",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        closeout_module,
        "write_p2_w9_unify_bullets_final_rca",
        lambda **_kwargs: {},
    )

    out = closeout_module.write_p2_w9_live_matrix_closeout(
        repo_root=REPO,
        run_live=False,
        emit_terminal_closeout=False,
    )

    assert out["status"] == "FAIL"
    assert out["w9"]["status"] == "FAIL"
    assert out["w9"]["broad_skills_ledger_used_as_authority_anywhere"] is True
    _assert_test_only_output(closeout_module.W9_JSON)


def test_false_c03_bound_rejected() -> None:
    from apps_rg.runtime.proof_pool_resolver import SectionProofPool

    pool = SectionProofPool(
        section="headline",
        proof_source="augmented_skills_graph",
        proof_pool_ref="g",
        proof_pool_digest="d",
        selected_fact_plan={},
        allowed_fact_ids_ordered=[],
        allowed_fact_ids=set(),
        bullet_rows=[],
        proof_pool_metadata={
            "c03_graph_bound_status": "BOUND",
            "c03_graph_hop_paths_count": 0,
            "non_graph_evidence_items_count": 0,
            "broad_skills_ledger_used_as_authority": False,
        },
        fallback_used=False,
        base_resume_fallback_used=False,
        broad_skills_ledger_present=False,
        srfs_present=False,
        base_resume_json_ref="",
        base_resume_json_hash="",
        broad_skills_ledger_ref="",
        broad_skills_ledger_digest="",
        srfs_ref="",
        base_resume_override_used=False,
    )
    from apps_rg.runtime.validators.graph_skills_proof_common import assert_c03_bound_claim_valid

    assert_pool_not_ledger_authority(pool)
    with pytest.raises(GraphSkillsProofError):
        assert_c03_bound_claim_valid(section_id="headline", meta=pool.proof_pool_metadata)
