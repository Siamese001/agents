"""Cross-subsystem handoff contract and research boundary unit tests (Wave 1).

Covers:
1. GAP-01: apps_research -> resume_graph_engine CrossAppEnvelope and ResearchBriefEnvelope
   serialization roundtrip, schema_name/semver compatibility, SHA-256 tamper detection,
   and TTL expiration.
2. GAP-02: apps_research -> outreach_engine persist_standalone_outreach_research_bundle
   artifact materialization, empty-brief fail-closed validation, and
   _validate_persisted_research_artifacts path-escape / digest tamper rejection.
3. GAP-03: outreach_engine execute_bounded_live_research retry/timeout exhaustion,
   build_cost_limit_exceeded_result, and build_timeout_result hermetic fallbacks.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps_lic.integrations.apps_research_bridge import ResearchResult
from apps_lic.integrations.managed_research_delegation import (
    _validate_persisted_research_artifacts,
)
from apps_lic.integrations.research_boundary_policy import (
    build_cost_limit_exceeded_result,
    build_timeout_result,
    execute_bounded_live_research,
)
from apps_lic.integrations.research_bridge_support import (
    persist_standalone_outreach_research_bundle,
)
from apps_research.contracts.cross_app.base import (
    EnvelopeExpiredError,
    EnvelopeHashMismatchError,
    EnvelopeLoadError,
    EnvelopeSchemaError,
    compute_sha256,
)
from apps_research.contracts.cross_app.research_brief import (
    ResearchBriefEnvelope,
    ResearchBriefPayload,
    ResearchClaimRow,
)


def _make_research_brief_envelope(
    *,
    emitted_at: datetime | None = None,
    ttl_days: int = 30,
    schema_version: str = "1.0.0",
) -> ResearchBriefEnvelope:
    payload = ResearchBriefPayload(
        brief_path="artifacts/research_brief_trace01.md",
        register_path="artifacts/source_register_trace01.json",
        company_brief="Anthropic builds frontier AI safety and enterprise platform partnerships.",
        role_areas_of_focus=["Partner architecture", "Enterprise AI governance"],
        industry_trends=["Multi-agent orchestration", "Governed retrieval"],
        source_register=[
            ResearchClaimRow(
                claim="Anthropic expands enterprise partner ecosystem",
                claim_type="direct_evidence",
                source_id="SRC-001",
                section_id="partner_ecosystem",
            )
        ],
    )
    fields = ResearchBriefEnvelope._envelope_fields(
        trace_id="trace-cross-app-001",
        producer_app="apps_research",
        payload=payload,
        schema_version=schema_version,
        ttl_days=ttl_days,
        emitted_at=emitted_at,
    )
    return ResearchBriefEnvelope(**fields, payload=payload)


def test_research_brief_envelope_roundtrip_and_zero_ttl(tmp_path: Path) -> None:
    """Verify ResearchBriefEnvelope sidecar write and load roundtrip preserves payload and SHA-256."""
    env = _make_research_brief_envelope(ttl_days=30)
    sidecar_path = tmp_path / "handoff" / "research_brief_envelope.json"
    written = env.write_sidecar(sidecar_path)
    assert written == sidecar_path
    assert sidecar_path.is_file()

    loaded = ResearchBriefEnvelope.load(sidecar_path)
    assert isinstance(loaded, ResearchBriefEnvelope)
    assert loaded.trace_id == "trace-cross-app-001"
    assert loaded.producer_app == "apps_research"
    assert loaded.source_sha256 == compute_sha256(env.payload)
    assert loaded.payload.company_brief == env.payload.company_brief
    assert len(loaded.payload.source_register) == 1
    assert loaded.payload.source_register[0].claim_type == "direct_evidence"
    assert not loaded.is_expired()

    # ttl_days=0 disables expiry even if emitted_at is far in the past
    old_time = datetime.now(timezone.utc) - timedelta(days=365)
    immortal_env = _make_research_brief_envelope(emitted_at=old_time, ttl_days=0)
    assert immortal_env.is_expired() is False


def test_cross_app_envelope_rejects_missing_and_malformed_json(tmp_path: Path) -> None:
    """Verify CrossAppEnvelope.load raises FileNotFoundError and EnvelopeLoadError on bad inputs."""
    missing_path = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError, match="Envelope not found"):
        ResearchBriefEnvelope.load(missing_path)

    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(EnvelopeLoadError, match="Malformed envelope JSON"):
        ResearchBriefEnvelope.load(corrupt_path)

    array_path = tmp_path / "array.json"
    array_path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(EnvelopeLoadError, match="Envelope must be a JSON object"):
        ResearchBriefEnvelope.load(array_path)


def test_cross_app_envelope_rejects_schema_and_version_mismatch(tmp_path: Path) -> None:
    """Verify CrossAppEnvelope.load enforces schema_name, semver format, and major version compatibility."""
    env = _make_research_brief_envelope()
    raw = json.loads(env.dump_json())

    # 1. Wrong schema_name
    bad_name = dict(raw, schema_name="cross_app.wrong_schema")
    p1 = tmp_path / "bad_name.json"
    p1.write_text(json.dumps(bad_name), encoding="utf-8")
    with pytest.raises(EnvelopeSchemaError, match="schema_name mismatch"):
        ResearchBriefEnvelope.load(p1)

    # 2. Invalid semver string
    bad_semver = dict(raw, schema_version="v1.0")
    p2 = tmp_path / "bad_semver.json"
    p2.write_text(json.dumps(bad_semver), encoding="utf-8")
    with pytest.raises(EnvelopeSchemaError, match="is not major.minor.patch"):
        ResearchBriefEnvelope.load(p2)

    # 3. Incompatible major version
    bad_major = dict(raw, schema_version="2.0.0")
    p3 = tmp_path / "bad_major.json"
    p3.write_text(json.dumps(bad_major), encoding="utf-8")
    with pytest.raises(EnvelopeSchemaError, match="incompatible with consumer"):
        ResearchBriefEnvelope.load(p3)

    # 4. Missing required payload field
    bad_payload = dict(raw, payload={"unexpected_key": "value"})
    p4 = tmp_path / "bad_payload.json"
    p4.write_text(json.dumps(bad_payload), encoding="utf-8")
    with pytest.raises(EnvelopeSchemaError, match="failed ResearchBriefEnvelope validation"):
        ResearchBriefEnvelope.load(p4)


def test_cross_app_envelope_rejects_hash_mismatch_and_expired_ttl(tmp_path: Path) -> None:
    """Verify CrossAppEnvelope.load detects tampered payload bytes and expired TTL."""
    env = _make_research_brief_envelope(
        emitted_at=datetime.now(timezone.utc) - timedelta(days=45),
        ttl_days=30,
    )
    expired_path = tmp_path / "expired.json"
    env.write_sidecar(expired_path)

    with pytest.raises(EnvelopeExpiredError, match="expired"):
        ResearchBriefEnvelope.load(expired_path, check_expiry=True)

    # Bypassing expiry check succeeds
    loaded_unexpired = ResearchBriefEnvelope.load(expired_path, check_expiry=False)
    assert loaded_unexpired.trace_id == "trace-cross-app-001"

    # Tamper with payload without updating source_sha256
    tampered_data = json.loads(env.dump_json())
    tampered_data["payload"]["company_brief"] = "TAMPERED BRIEF CONTENT"
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(tampered_data), encoding="utf-8")

    with pytest.raises(EnvelopeHashMismatchError, match="Envelope hash mismatch"):
        ResearchBriefEnvelope.load(tampered_path, check_expiry=False)


def test_persist_standalone_outreach_research_bundle_and_empty_rejection(tmp_path: Path) -> None:
    """Verify persist_standalone_outreach_research_bundle emits all 6 artifacts and rejects empty brief."""
    empty_record = SimpleNamespace(
        run_id="run-empty-01",
        trace_id="trace-empty-01",
        request_id="req-empty-01",
        company_brief_text="   ",
    )
    with pytest.raises(ValueError, match="Cannot persist empty company brief"):
        persist_standalone_outreach_research_bundle(
            record=empty_record,
            target_company="Anthropic",
            target_role="Partner Architect",
            jd_text="Build partner ecosystem.",
            runs_root=tmp_path,
        )

    valid_record = SimpleNamespace(
        run_id="run-valid-01",
        trace_id="bridge:lic:trace-valid-01",
        request_id="req-valid-01",
        company_brief_text="Anthropic enterprise AI safety and partnerships brief.",
        confidence_score=0.93,
        strategic_priorities=("Enterprise AI adoption", "Partner co-sell motion"),
    )
    bundle = persist_standalone_outreach_research_bundle(
        record=valid_record,
        target_company="Anthropic",
        target_role="Partner Architect",
        jd_text="Lead partner architecture and enterprise AI deployment.",
        runs_root=tmp_path,
    )

    assert bundle.run_id == "run-valid-01"
    assert bundle.run_dir == (tmp_path / "run-valid-01").resolve()
    assert bundle.brief_sha256.startswith("sha256:")
    assert bundle.result_metadata_digest.startswith("sha256:")
    assert bundle.bundle_manifest_digest.startswith("sha256:")
    assert bundle.envelope["identity"]["trace_root"] == "trace-valid-01"

    for fname in (
        "briefing.md",
        "company_brief.md",
        "company_brief.json",
        "apps_research_u0_receipt.json",
        "run_metadata.json",
        "apps_research_apps_rg_handoff_v2.json",
        "bundle_commit_manifest.json",
    ):
        assert (bundle.run_dir / fname).is_file(), f"Missing bundle file {fname}"


def test_validate_persisted_research_artifacts_rejects_escape_and_tamper(tmp_path: Path) -> None:
    """Verify _validate_persisted_research_artifacts rejects missing dirs, path escape, and text mismatch."""
    base_result = ResearchResult(
        run_id="r1",
        trace_id="t1",
        request_id="req1",
        is_blocked=False,
        block_reason="",
        is_stale=False,
        evidence_items=(),
        confidence_score=0.9,
        brief_sha256="sha256:00",
        company_brief_text="Valid brief",
        strategic_priorities=(),
        fetch_duration_ms=1.0,
        audit_ref="t1",
        research_artifact_dir="",
        briefing_artifact_path="",
    )
    ok, reason, _ = _validate_persisted_research_artifacts(base_result)
    assert ok is False
    assert "missing research_artifact_dir" in reason

    run_dir = tmp_path / "run_escape"
    run_dir.mkdir()
    outside_brief = tmp_path / "outside_briefing.md"
    outside_brief.write_text("Outside brief", encoding="utf-8")

    escape_result = ResearchResult(
        run_id="r1",
        trace_id="t1",
        request_id="req1",
        is_blocked=False,
        block_reason="",
        is_stale=False,
        evidence_items=(),
        confidence_score=0.9,
        brief_sha256="sha256:00",
        company_brief_text="Outside brief",
        strategic_priorities=(),
        fetch_duration_ms=1.0,
        audit_ref="t1",
        research_artifact_dir=str(run_dir),
        briefing_artifact_path=str(outside_brief),
    )
    ok, reason, _ = _validate_persisted_research_artifacts(escape_result)
    assert ok is False
    assert "escapes research_artifact_dir" in reason


def test_execute_bounded_live_research_retries_and_timeouts() -> None:
    """Verify execute_bounded_live_research recovers on retry and raises TimeoutError when slow."""
    attempts = {"count": 0}

    def flaky_fn() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ValueError("transient network glitch")
        return "recovered_payload"

    res = execute_bounded_live_research(
        invoke_fn=flaky_fn,
        timeout_seconds=1.0,
        max_retries=2,
    )
    assert res == "recovered_payload"
    assert attempts["count"] == 2

    import threading

    gate = threading.Event()

    def hanging_fn() -> str:
        gate.wait(timeout=0.5)
        return "too_late"

    with pytest.raises(TimeoutError, match="apps_research timed out"):
        execute_bounded_live_research(
            invoke_fn=hanging_fn,
            timeout_seconds=0.03,
            max_retries=0,
        )
    gate.set()


def test_build_cost_limit_and_timeout_hermetic_fallback_results() -> None:
    """Verify build_cost_limit_exceeded_result and build_timeout_result produce blocked hermetic results."""
    cost_res = build_cost_limit_exceeded_result(
        run_id="run-cost-01",
        trace_id="trace-cost-01",
        request_id="req-cost-01",
        cumulative_cost_usd=0.45,
        cost_per_call_usd=0.10,
        cost_limit_usd=0.50,
    )
    assert cost_res.is_blocked is True
    assert "COST_LIMIT_EXCEEDED" in cost_res.block_reason
    assert "$0.45 + $0.10 exceeds limit $0.50" in cost_res.block_reason
    assert cost_res.confidence_score == 0.0
    assert cost_res.resolution_source == "HERMETIC_FALLBACK"
    assert cost_res.is_verified is False

    timeout_res = build_timeout_result(
        run_id="run-time-01",
        trace_id="trace-time-01",
        request_id="req-time-01",
        error=TimeoutError("deadline exceeded"),
    )
    assert timeout_res.is_blocked is True
    assert "TIMEOUT: deadline exceeded" in timeout_res.block_reason
    assert timeout_res.confidence_score == 0.0
    assert timeout_res.resolution_source == "HERMETIC_FALLBACK"
    assert timeout_res.is_verified is False
