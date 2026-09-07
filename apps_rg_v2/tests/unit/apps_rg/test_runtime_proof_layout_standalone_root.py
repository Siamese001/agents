"""Standalone-path protection for run-scoped modular section artifacts."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.runtime_proof_layout import (
    MODULAR_R4_SECTIONS_ROOT_ENV,
    allocate_section_spine_artifact_dir,
    modular_sections_root_from_env,
    prepare_runtime_proof_run_dir,
    rel_posix,
)
from apps_rg.runtime.sections_root_manifest import SECTIONS_ROOT_MANIFEST_FILENAME


def test_standalone_src_root_uses_checkout_scoped_modular_artifacts(
    monkeypatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    source_root = checkout / "src"
    package_init = source_root / "apps_rg" / "__init__.py"
    package_init.parent.mkdir(parents=True)
    package_init.write_text("", encoding="utf-8")
    sections_root = checkout / ".runtime" / "e2e" / "modular_r4" / "sections"
    sections_root.mkdir(parents=True)
    (sections_root / SECTIONS_ROOT_MANIFEST_FILENAME).write_text(
        "{}", encoding="utf-8"
    )
    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(sections_root))

    assert modular_sections_root_from_env(source_root) == sections_root.resolve()

    run_dir = prepare_runtime_proof_run_dir(
        source_root,
        "competencies",
        "external_openai",
        "run-123",
    )

    assert run_dir == (sections_root / "competencies" / "real" / "run-123").resolve()
    assert rel_posix(run_dir, source_root) == (
        ".runtime/e2e/modular_r4/sections/competencies/real/run-123"
    )


def test_whole_resume_section_spine_uses_the_flat_run_scoped_lane_directory(
    monkeypatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    source_root = checkout / "src"
    package_init = source_root / "apps_rg" / "__init__.py"
    package_init.parent.mkdir(parents=True)
    package_init.write_text("", encoding="utf-8")
    sections_root = (
        checkout
        / "artifacts"
        / "apps_rg"
        / "runtime_proofs"
        / "full_resume_run123"
        / "lanes"
    )
    sections_root.mkdir(parents=True)
    (sections_root / SECTIONS_ROOT_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(sections_root))
    monkeypatch.setenv("APPS_RG_WHOLE_RUN_ENVELOPE", "1")

    artifact_dir = allocate_section_spine_artifact_dir(source_root, "competencies")

    assert artifact_dir == (sections_root / "competencies").resolve()


def test_explicit_e2e_section_spine_uses_the_run_scoped_lane_directory(
    monkeypatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    source_root = checkout / "src"
    package_init = source_root / "apps_rg" / "__init__.py"
    package_init.parent.mkdir(parents=True)
    package_init.write_text("", encoding="utf-8")
    run_root = checkout / ".runtime" / "owner_solo_final_output" / "brown_brown" / "e2e_run123"
    sections_root = run_root / "modular_r4" / "sections"
    sections_root.mkdir(parents=True)
    (run_root / "spine_run_manifest.json").write_text("{}", encoding="utf-8")
    (sections_root / SECTIONS_ROOT_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(sections_root))
    monkeypatch.setenv("APPS_RG_WHOLE_RUN_ENVELOPE", "1")

    artifact_dir = allocate_section_spine_artifact_dir(source_root, "competencies")

    assert artifact_dir == (sections_root / "competencies").resolve()
