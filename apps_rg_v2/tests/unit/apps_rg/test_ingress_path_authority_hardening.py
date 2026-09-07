"""Unit tests verifying Wave 2 ingress, preflight, and path authority hardening."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from apps_rg.runtime.bindings.u0_binding import (
    AppsRgU0RejectedError,
    u0_validate_apps_rg,
)
from apps_rg.runtime.bindings.u0_rejection import AppsRgIngressReasonCode
from apps_rg.runtime.briefing_resolution import BriefingResolutionError
from apps_rg.runtime.embedding_settings import (
    _resolve_bootstrap_repo_root,
    bootstrap_apps_rg_embedding_env,
    resolve_apps_rg_embedding_settings,
)
from apps_rg.runtime.fact_vectors_bootstrap import prepare_fact_vector_hydration_env
from apps_rg.runtime.orchestration.canonical_dispatch import _read_optional_file
from apps_rg.runtime.runtime_proof_layout import find_repo_root
from apps_rg.runtime.spine_contracts import AppsRgIngressPayload, RequestEnvelope


def _build_u0_envelope(
    *,
    target_company: str = "Acme Corp",
    target_role: str = "Lead Architect",
) -> RequestEnvelope:
    payload = AppsRgIngressPayload(
        app_id="apps_rg",
        task_class="resume_generation",
        target_company=target_company,
        target_role=target_role,
        target_level="IC-6",
        source_resume_text="Experienced software architect and systems engineer.",
        job_description_text="Looking for a seasoned architect with AI systems experience.",
        briefing_artifact_ref="Acme Corp is expanding its core infrastructure.",
    )
    return RequestEnvelope(payload=payload)


def test_u0_whitespace_company_rejected() -> None:
    """U0 ingress must reject empty or whitespace-only target_company."""
    envelope = _build_u0_envelope(target_company="   \t\n  ")

    with pytest.raises(AppsRgU0RejectedError) as exc_info:
        u0_validate_apps_rg(envelope)

    assert exc_info.value.notice.rejection_reason == AppsRgIngressReasonCode.FIELD_TYPE_MISMATCH
    assert "target_company cannot be empty or whitespace" in str(exc_info.value)


def test_u0_whitespace_role_rejected() -> None:
    """U0 ingress must reject empty or whitespace-only target_role."""
    envelope = _build_u0_envelope(target_role="      ")

    with pytest.raises(AppsRgU0RejectedError) as exc_info:
        u0_validate_apps_rg(envelope)

    assert exc_info.value.notice.rejection_reason == AppsRgIngressReasonCode.FIELD_TYPE_MISMATCH
    assert "target_role cannot be empty or whitespace" in str(exc_info.value)


def test_u0_valid_targeting_succeeds() -> None:
    """Valid target_company and target_role pass U0 validation successfully."""
    envelope = _build_u0_envelope(target_company="Stripe", target_role="Staff Infrastructure Engineer")
    result = u0_validate_apps_rg(envelope)
    assert result.app_payload["target_company"] == "Stripe"
    assert result.app_payload["target_role"] == "Staff Infrastructure Engineer"


def test_read_optional_file_branches(tmp_path: Path) -> None:
    """_read_optional_file correctly handles empty string, inline text, and files."""
    assert _read_optional_file("") == ""
    assert _read_optional_file("   ") == ""
    assert _read_optional_file("inline text briefing") == "inline text briefing"

    valid_file = tmp_path / "brief.txt"
    valid_file.write_text("Hello from file", encoding="utf-8")
    assert _read_optional_file(str(valid_file)) == "Hello from file"


def test_read_optional_file_unreadable_fails_closed(tmp_path: Path) -> None:
    """When a briefing file exists but raises OSError on read, fail closed with BriefingResolutionError."""
    test_file = tmp_path / "locked_brief.txt"
    test_file.write_text("Secret briefing", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=OSError("simulated permission denied")):
        with pytest.raises(BriefingResolutionError) as exc_info:
            _read_optional_file(str(test_file))

    assert "Failed to read file at" in str(exc_info.value)


def test_resolve_bootstrap_repo_root_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_bootstrap_repo_root respects explicit arg, APPS_RG_REPO_ROOT, and legacy fallback."""
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    assert _resolve_bootstrap_repo_root(explicit) == explicit.resolve()

    apps_env = tmp_path / "apps_env"
    apps_env.mkdir()
    monkeypatch.setenv("APPS_RG_REPO_ROOT", str(apps_env))
    monkeypatch.delenv("AGENTIC_REPO_ROOT", raising=False)
    assert _resolve_bootstrap_repo_root(None) == apps_env.resolve()

    agentic_env = tmp_path / "agentic_env"
    agentic_env.mkdir()
    monkeypatch.delenv("APPS_RG_REPO_ROOT", raising=False)
    monkeypatch.setenv("AGENTIC_REPO_ROOT", str(agentic_env))
    assert _resolve_bootstrap_repo_root(None) == agentic_env.resolve()

    monkeypatch.delenv("AGENTIC_REPO_ROOT", raising=False)
    assert _resolve_bootstrap_repo_root(None) == find_repo_root()


def test_agentic_repo_root_completely_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neither embedding bootstrap nor fact vector hydration should set AGENTIC_REPO_ROOT."""
    monkeypatch.setenv("APPS_RG_RUNTIME_BOUNDARY_ENFORCED", "0")
    monkeypatch.delenv("AGENTIC_REPO_ROOT", raising=False)
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)
    monkeypatch.delenv("APPS_RG_EMBEDDING_MODEL_PATH", raising=False)

    applied_embed = bootstrap_apps_rg_embedding_env(repo_root=tmp_path)
    assert "AGENTIC_REPO_ROOT" not in applied_embed

    applied_fv = prepare_fact_vector_hydration_env(repo_root=tmp_path)
    assert "AGENTIC_REPO_ROOT" not in applied_fv

    # Model resolution with explicit repo_root
    pre = tmp_path / "artifacts" / "models" / "BAAI" / "bge-m3"
    pre.mkdir(parents=True)
    (pre / "weights.bin").write_bytes(b"x")

    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_MODEL_ID", "bge-m3-v1")
    s = resolve_apps_rg_embedding_settings(repo_root=tmp_path)
    assert s.embedding_model_name == "BAAI/bge-m3"
    assert s.embedding_model_resolved is True


def test_bootstrap_embedding_env_under_boundary_enforcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When APPS_RG_RUNTIME_BOUNDARY_ENFORCED=1, bootstrap sets AGENTIC_REPO_ROOT and validates boundary."""
    repo = find_repo_root()
    monkeypatch.setenv("APPS_RG_RUNTIME_BOUNDARY_ENFORCED", "1")
    monkeypatch.setenv("EMBEDDING_ENABLED", "0")

    applied = bootstrap_apps_rg_embedding_env(repo_root=repo)
    assert Path(os.environ.get("AGENTIC_REPO_ROOT", "")).resolve() == repo.resolve()


def test_prepare_fact_vector_hydration_env_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prepare_fact_vector_hydration_env resolves APPS_RG_REPO_ROOT when repo_root is None."""
    apps_env = tmp_path / "apps_rg_custom_root"
    apps_env.mkdir()
    monkeypatch.setenv("APPS_RG_REPO_ROOT", str(apps_env))
    monkeypatch.delenv("AGENTIC_REPO_ROOT", raising=False)
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)

    applied = prepare_fact_vector_hydration_env(repo_root=None)
    assert Path(applied["chroma_path"]).resolve() == (
        apps_env / "data" / "cache" / "chromadb"
    ).resolve()
