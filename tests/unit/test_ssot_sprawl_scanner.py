"""Fault-injection and sandbox unit tests for Wave 1 multi-folder configuration sprawl scanner."""

from __future__ import annotations

import json
from pathlib import Path

from tools.check_config_ssot_drift import analyze_drift
from tools.ssot_sprawl_scanner import (
    run_sprawl_scan,
    scan_cross_format_bound_drift,
    scan_intra_file_contradictions,
    scan_shadow_config_drift,
    scan_twin_profile_sprawl,
)


def _seed_centralization_registry(sandbox: Path) -> None:
    gov_dir = sandbox / "config" / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    (gov_dir / "centralization_registry.yaml").write_text(
        "version: '1.0.0'\n"
        "domain_threshold_owners:\n"
        "  resume_executive_summary_shape:\n"
        "    canonical_symbols:\n"
        "      EXEC_SUMMARY_MAX_WORDS: 150\n"
        "      EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE: 45\n",
        encoding="utf-8",
    )


def test_shadow_config_drift_catches_nested_provider_profiles_and_pytest_mismatch(tmp_path: Path) -> None:
    _seed_centralization_registry(tmp_path)
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "provider_profiles.yaml").write_text("version: 1\n", encoding="utf-8")

    nested_cfg = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "config"
    nested_cfg.mkdir(parents=True)
    (nested_cfg / "provider_profiles.yaml").write_text("version: 2\n", encoding="utf-8")

    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --timeout=180\n", encoding="utf-8")
    (tmp_path / "resume_graph_engine" / "pytest.ini").write_text(
        "[pytest]\naddopts = --timeout=60\n",
        encoding="utf-8",
    )

    findings = scan_shadow_config_drift(tmp_path)
    categories = {f["category"] for f in findings}
    assert "SHADOW_CONFIG_DRIFT" in categories
    assert "SHADOW_PYTEST_DRIFT" in categories


def test_intra_file_contradiction_catches_conflicting_summary_word_caps_and_inverted_bounds(
    tmp_path: Path,
) -> None:
    rg_dir = tmp_path / "resume_graph_engine" / "src" / "apps_rg"
    rg_dir.mkdir(parents=True)
    schema = {
        "properties": {
            "sections": {
                "properties": {
                    "summary": {
                        "properties": {
                            "word_count": {"minimum": 10, "maximum": 150},
                        }
                    }
                }
            }
        },
        "definitions": {
            "section_constraints": {
                "properties": {
                    "summary": {"min_words": 80, "max_words": 60},
                }
            }
        },
    }
    (rg_dir / "rg_output_schema.json").write_text(json.dumps(schema), encoding="utf-8")

    findings = scan_intra_file_contradictions(tmp_path)
    categories = {f["category"] for f in findings}
    assert "INTRA_FILE_CONTRADICTION" in categories
    assert "INVERTED_BOUNDS" in categories


def test_twin_profile_sprawl_catches_coexisting_base_and_v1_profiles(tmp_path: Path) -> None:
    dc_dir = tmp_path / "apps_research" / "config" / "domain_contract"
    dc_dir.mkdir(parents=True)
    (dc_dir / "cache_profiles.yaml").write_text("ttl: 300\n", encoding="utf-8")
    (dc_dir / "cache_profile.company_brief.v1.yaml").write_text("ttl: 600\n", encoding="utf-8")

    findings = scan_twin_profile_sprawl(tmp_path)
    assert len(findings) == 1
    assert findings[0]["category"] == "TWIN_PROFILE_SPRAWL"


def test_cross_format_bound_drift_catches_60_vs_150_word_caps(tmp_path: Path) -> None:
    _seed_centralization_registry(tmp_path)
    rg_dir = tmp_path / "resume_graph_engine" / "src" / "apps_rg"
    rg_dir.mkdir(parents=True)
    (rg_dir / "rg_style_profile.yaml").write_text(
        "section_style:\n  summary:\n    max_words: 60\n",
        encoding="utf-8",
    )
    t_dir = rg_dir / "prompt_assembly" / "templates"
    t_dir.mkdir(parents=True)
    (t_dir / "strategic_tailor_v1.yaml").write_text(
        "sections:\n  summary:\n    max_lines: 4\n    max_words: 60\n",
        encoding="utf-8",
    )

    findings = scan_cross_format_bound_drift(tmp_path)
    assert len(findings) == 2
    assert all(f["observed"] == 60 and f["canonical"] == 150 for f in findings)


def test_clean_sandbox_passes_sprawl_scan_and_preserves_analyze_drift_contract(tmp_path: Path) -> None:
    _seed_centralization_registry(tmp_path)
    rg_dir = tmp_path / "resume_graph_engine" / "src" / "apps_rg"
    rg_dir.mkdir(parents=True)
    (rg_dir / "rg_style_profile.yaml").write_text(
        "section_style:\n  summary:\n    max_words: 150\n",
        encoding="utf-8",
    )
    rep = run_sprawl_scan(tmp_path)
    assert rep["is_clean"] is True
    assert rep["status"] == "PASS"

    drift_rep = analyze_drift(tmp_path, include_sprawl=True)
    assert "unallowlisted_differing" in drift_rep
    assert drift_rep["sprawl_scan"]["is_clean"] is True
