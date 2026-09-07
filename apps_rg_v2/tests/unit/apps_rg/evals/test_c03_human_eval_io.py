from __future__ import annotations

import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from apps_rg.evals import resume_graph_evaluation
from apps_rg.evals.c03_human_eval.cli import _read_blinding_nonce_file
from apps_rg.evals.c03_human_eval import _io
from apps_rg.evals.c03_human_eval import seal_records
from apps_rg.evals.c03_proxy_eval.evaluation import _canonical_profile
from apps_rg.evals.resume_graph.models import EvaluationDataError


def test_module_roots_resolve_standalone_src_layout() -> None:
    repository = Path(__file__).resolve().parents[4]

    assert _io.repo_root_from_module() == repository
    assert _io.package_root_from_module() == repository / "src" / "apps_rg"


def test_logical_apps_rg_resource_resolves_below_standalone_package() -> None:
    repository = _io.repo_root_from_module()

    assert _io.resolve_repository_resource(
        repository,
        "apps_rg/config/targeting/openai_partner_ade_jd.txt",
    ) == (
        repository
        / "src"
        / "apps_rg"
        / "config"
        / "targeting"
        / "openai_partner_ade_jd.txt"
    )


def test_all_canonical_target_sources_match_frozen_byte_digests() -> None:
    repository = _io.repo_root_from_module()
    manifest = _io.read_yaml(
        _io.package_root_from_module()
        / "evals"
        / "c03_human_eval"
        / "target_cases.v1.yaml"
    )
    observed: list[tuple[str, str]] = []

    for case in manifest["cases"]:
        for kind in ("jd", "brief"):
            source = _io.resolve_repository_resource(
                repository,
                case[f"{kind}_path"],
            )
            observed.append((case["case_id"], kind))
            assert source.is_file()
            assert _io.file_digest(source) == case[f"{kind}_sha256"]

    assert len(observed) == 12


def test_repository_resource_rejects_absolute_and_escaping_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        _io.resolve_repository_resource(tmp_path, tmp_path / "source.txt")
    with pytest.raises(ValueError, match="escapes repo_root"):
        _io.resolve_repository_resource(tmp_path, "../source.txt")


def test_repository_resource_rejects_symlink_alias(tmp_path: Path) -> None:
    package = tmp_path / "src" / "apps_rg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    target = package / "source.txt"
    target.write_text("authoritative source\n", encoding="utf-8")
    alias = package / "source-alias.txt"
    try:
        alias.symlink_to(target)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege is unavailable")
        raise

    with pytest.raises(ValueError, match="must not use a symlink alias"):
        _io.resolve_repository_resource(tmp_path, "apps_rg/source-alias.txt")


def test_alias_detector_recognizes_windows_reparse_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o700,
        st_file_attributes=0x400,
    )
    monkeypatch.setattr(_io.os, "lstat", lambda _path: metadata)

    assert _io._path_component_is_alias(tmp_path) is True
    assert seal_records._path_component_is_alias(tmp_path) is True


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX symlink contract")
def test_sensitive_paths_reject_symlinked_ancestors(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    controlled.mkdir(mode=0o700)
    nonce = controlled / "nonce.hex"
    nonce.write_text("ab" * 32, encoding="utf-8")
    nonce.chmod(0o600)
    alias = tmp_path / "controlled-alias"
    try:
        alias.symlink_to(controlled, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")
    aliased_nonce = alias / nonce.name

    assert _io.path_has_symlink_component(aliased_nonce) is True
    assert _io.private_path_error(aliased_nonce, directory=False) == (
        "must not be a symlink alias or reparse point"
    )
    with pytest.raises(ValueError, match="symlink alias or reparse point"):
        _read_blinding_nonce_file(aliased_nonce)
    with pytest.raises(EvaluationDataError, match="symlink alias or reparse point"):
        resume_graph_evaluation._secure_private_file_bytes(aliased_nonce)
    with pytest.raises(ValueError, match="symlink alias or reparse point"):
        _io.ensure_private_directory(alias / "new-private-directory")
    with pytest.raises(ValueError, match="symlink alias or reparse point"):
        seal_records._private_directory(alias / "returned-labels")


def test_proxy_profile_reference_is_repository_relative_in_src_layout() -> None:
    repository = _io.repo_root_from_module()
    relative = Path(
        "src/apps_rg/config/domain_contract/resume_graph_evaluation_profile.yaml"
    )

    assert _canonical_profile(repository / relative)["ref"] == relative.as_posix()


def test_private_path_fails_closed_when_owner_security_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controlled = tmp_path / "controlled.json"
    controlled.write_text("{}\n", encoding="utf-8")
    monkeypatch.delattr(_io.os, "getuid", raising=False)

    assert _io.private_path_error(controlled, directory=False) == (
        _io.PLATFORM_SECURITY_UNSUPPORTED
    )


def test_private_directory_is_not_created_without_owner_security(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controlled = tmp_path / "controlled"
    monkeypatch.delattr(_io.os, "getuid", raising=False)

    with pytest.raises(ValueError, match="PLATFORM_SECURITY_UNSUPPORTED"):
        _io.ensure_private_directory(controlled)

    assert not controlled.exists()


def test_descriptor_nonce_and_return_paths_fail_closed_without_owner_security(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controlled = tmp_path / "controlled.json"
    controlled.write_text("ab" * 32, encoding="utf-8")
    monkeypatch.delattr(_io.os, "getuid", raising=False)

    with pytest.raises(EvaluationDataError, match="PLATFORM_SECURITY_UNSUPPORTED"):
        resume_graph_evaluation._secure_private_file_bytes(controlled)
    with pytest.raises(ValueError, match="PLATFORM_SECURITY_UNSUPPORTED"):
        _read_blinding_nonce_file(controlled)

    return_dir = tmp_path / "return"
    with pytest.raises(ValueError, match="PLATFORM_SECURITY_UNSUPPORTED"):
        seal_records._private_directory(return_dir)
    assert not return_dir.exists()


def test_private_metadata_keeps_posix_owner_and_mode_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_io.os, "getuid", lambda: 1000, raising=False)
    private = SimpleNamespace(st_uid=1000, st_mode=stat.S_IFREG | 0o600)
    wrong_owner = SimpleNamespace(st_uid=1001, st_mode=stat.S_IFREG | 0o600)
    public = SimpleNamespace(st_uid=1000, st_mode=stat.S_IFREG | 0o644)

    assert _io.private_metadata_error(private, directory=False) is None
    assert _io.private_metadata_error(wrong_owner, directory=False) == (
        "must be owned by the current user"
    )
    assert _io.private_metadata_error(public, directory=False) == (
        "must be owner-only (0600)"
    )
