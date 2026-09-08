from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.runtime.orchestration.canonical_identity_context import (
    canonical_identity_for_recipe_context,
    canonical_run_identity_scope,
    current_canonical_run_identity,
    validate_canonical_run_identity,
)


def _identity(*, parent: str = "research-run") -> dict[str, str]:
    digest = "sha256:" + ("a" * 64)
    return {
        "producer_app_id": "apps_research",
        "consumer_app_id": "apps_rg",
        "parent_run_id": parent,
        "child_run_id": "apps-rg-run",
        "request_id": "request-1",
        "trace_root": "trace-1",
        "tenant_id": "tenant-1",
        "target_company": "Anthropic",
        "target_role": "Partnerships",
        "jd_sha256": digest,
        "brief_sha256": digest,
        "policy_hash": digest,
        "blueprint_hash": digest,
        "schema_version": "apps_research_rg_run_identity.v1",
    }


def test_scope_propagates_identity_then_resets_and_isolates_copies() -> None:
    source = _identity()

    with canonical_run_identity_scope(source):
        observed = current_canonical_run_identity()
        observed["parent_run_id"] = "mutated"
        assert current_canonical_run_identity()["parent_run_id"] == "research-run"

    assert current_canonical_run_identity() == {}


def test_recipe_context_explicit_identity_precedes_dynamic_scope() -> None:
    explicit = _identity(parent="explicit")
    with canonical_run_identity_scope(_identity(parent="dynamic")):
        assert canonical_identity_for_recipe_context(
            {"canonical_run_identity": explicit}
        )["parent_run_id"] == "explicit"


@pytest.mark.parametrize(
    "mutation",
    [
        {"parent_run_id": ""},
        {"producer_app_id": "apps_rg"},
        {"consumer_app_id": "apps_research"},
        {"policy_hash": "not-a-digest"},
    ],
)
def test_validation_rejects_incomplete_or_wrong_authority(mutation: dict[str, str]) -> None:
    candidate = _identity()
    candidate.update(mutation)

    with pytest.raises(ValueError, match="canonical run identity"):
        validate_canonical_run_identity(candidate)


def test_patch_run_rehydrates_only_digest_bound_product_identity(tmp_path: Path) -> None:
    from apps_rg.runtime.orchestration.patch_run import _patch_canonical_run_identity

    identity = _identity()
    digest = "sha256:" + hashlib.sha256(
        json.dumps(
            identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    (tmp_path / "e2e_preflight_product_entry_receipt.json").write_text(
        json.dumps({"status": "PASS", "identity": identity, "identity_sha256": digest}),
        encoding="utf-8",
    )

    assert _patch_canonical_run_identity(tmp_path) == identity

    tampered = json.loads(
        (tmp_path / "e2e_preflight_product_entry_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    tampered["identity"]["parent_run_id"] = "tampered"
    (tmp_path / "e2e_preflight_product_entry_receipt.json").write_text(
        json.dumps(tampered), encoding="utf-8"
    )
    with pytest.raises(Exception, match="identity digest mismatch"):
        _patch_canonical_run_identity(tmp_path)
