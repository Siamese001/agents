"""apps-test-model: APP CONTRACT.

Fresh E2E preflight and mandatory operational-RCA contract tests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _write_passing_baseline(repo_root: Path) -> Path:
    baseline_run = repo_root / "artifacts" / "apps_rg" / "runs" / "baseline-pass"
    baseline_run.mkdir(parents=True)
    mandatory = baseline_run / "APPS_RG_MANDATORY_RUN_OUTPUT.json"
    mandatory.write_text(
        json.dumps(
            {
                "result_summary": {
                    "exit_status": "success",
                    "outcome_authorized": True,
                    "x3_disposition": "X3D",
                },
                "sections": [
                    {
                        "section": "executive_summary",
                        "x2_pass": True,
                        "x3_code": "X3_ALLOW",
                        "judges": [
                            {
                                "provider_key": "gemini_pro",
                                "score": 4.5,
                                "threshold": 4.0,
                                "pass": True,
                            },
                            {
                                "provider_key": "openai_chatgpt",
                                "score": 4.4,
                                "threshold": 4.0,
                                "pass": True,
                            },
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (baseline_run / "route_contract.json").write_text(
        json.dumps({"route_evidence_signature": "sha256:baseline-signature"}) + "\n",
        encoding="utf-8",
    )
    contract = repo_root / "baseline.json"
    contract.write_text(
        json.dumps(
            {
                "schema_version": "apps_rg.e2e_baseline.v1",
                "baseline_id": "baseline-pass",
                "baseline_run_dir": str(baseline_run.relative_to(repo_root)),
                "mandatory_output_sha256": hashlib.sha256(mandatory.read_bytes()).hexdigest(),
                "git_commit": "a" * 40,
                "expected_exit_status": "success",
                "expected_outcome_authorized": True,
                "expected_x3_disposition": "X3D",
                "target_company": "Anthropic",
                "target_role": "Manager of Applied AI Architecture, Partnerships",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return contract


def _run_identity(run_id: str) -> dict[str, str]:
    return {
        "producer_app_id": "apps_research",
        "consumer_app_id": "apps_rg",
        "parent_run_id": run_id,
        "child_run_id": "research-child-001",
        "request_id": "request-001",
        "trace_root": "trace-001",
        "tenant_id": "tenant-001",
        "target_company": "Anthropic",
        "target_role": "Applied AI Manager",
        "jd_sha256": "sha256:" + "1" * 64,
        "brief_sha256": "sha256:" + "2" * 64,
        "policy_hash": "sha256:" + "3" * 64,
        "blueprint_hash": "sha256:" + "4" * 64,
        "schema_version": "apps_research_rg_run_identity.v1",
    }


def test_pinned_baseline_accepts_only_checkout_line_ending_translation(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_baseline import validate_pinned_baseline

    contract = _write_passing_baseline(tmp_path)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    mandatory = tmp_path / payload["baseline_run_dir"] / "APPS_RG_MANDATORY_RUN_OUTPUT.json"
    raw = mandatory.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    mandatory.write_bytes(lf)
    payload["mandatory_output_sha256"] = hashlib.sha256(crlf).hexdigest()
    contract.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_pinned_baseline(tmp_path, contract)

    assert result["mandatory_output_digest_match_mode"] == "line_ending_compatible"
    mandatory.write_bytes(lf.replace(b'"success"', b'"failure"'))
    try:
        validate_pinned_baseline(tmp_path, contract)
    except RuntimeError as exc:
        assert "PINNED_BASELINE_DIGEST_MISMATCH" in str(exc)
    else:
        raise AssertionError("content alteration must not be accepted as an EOL translation")


def test_missing_signing_config_emits_canonical_rca_without_running_dependencies(
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.e2e_preflight import run_fresh_e2e_preflight

    run_dir = tmp_path / "runs" / "current-failure"
    run_dir.mkdir(parents=True)
    baseline_ref = _write_passing_baseline(tmp_path)
    calls: list[str] = []

    outcome = run_fresh_e2e_preflight(
        artifact_dir=run_dir,
        e2e_run_id=run_dir.name,
        repo_root=tmp_path,
        baseline_ref=baseline_ref,
        environ={},
        runtime_check=lambda: calls.append("runtime"),
        bootstrap=lambda: calls.append("bootstrap"),
    )

    assert outcome.passed is False
    assert outcome.exit_code == 2
    assert calls == []
    for filename in (
        "e2e_preflight_receipt.json",
        "e2e_stage_ledger.json",
        "01_BCG_executive_output.md",
        "02_output_bisect.md",
        "02_section_lane_summary_table.md",
        "03_L7_audit_ability_output.md",
        "APPS_RG_MANDATORY_RUN_OUTPUT.json",
    ):
        assert (run_dir / filename).is_file(), filename

    receipt_text = (run_dir / "e2e_preflight_receipt.json").read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["missing_environment_variables"] == [
        "APPS_RG_ROUTE_HMAC_SECRET",
        "APPS_RG_ROUTE_HMAC_KEY_ID",
    ]
    assert receipt["research_attempt_count"] == 0
    assert receipt["judge_attempt_count"] == 0
    assert "secret-value" not in receipt_text

    ledger = json.loads((run_dir / "e2e_stage_ledger.json").read_text(encoding="utf-8"))
    assert [(row["stage_id"], row["status"]) for row in ledger["entries"]] == [
        ("PREFLIGHT", "BLOCKED"),
        ("CLOSEOUT", "PASS"),
    ]

    mandatory = json.loads((run_dir / "APPS_RG_MANDATORY_RUN_OUTPUT.json").read_text(encoding="utf-8"))
    operational = mandatory["operational_failure_forensics"]
    assert operational["comparison_complete"] is True
    assert len(operational["layperson_explanation"]) == 3
    assert operational["retry_analysis"]["current_retry_count"] == 0
    assert operational["retry_analysis"]["prior_retry_count"] == 0
    assert operational["retry_analysis"]["why_retries_did_not_run"]
    assert operational["first_causally_relevant_divergence"]["stage"] == "PREFLIGHT"
    assert operational["judge_matrix"][0]["current"] == "JUDGES_NOT_REACHED"
    assert 3 <= len(operational["implementation_plan"]) <= 5
    assert mandatory["mandatory_output_hard_stop"]["pass"] is True
    assert mandatory["result_summary"]["apps_eval_record_ref"] == "NOT_REACHED:PREFLIGHT"
    assert mandatory["result_summary"]["l6_shadow_bridge_ref"] == "NOT_REACHED:PREFLIGHT"
    bcg = (run_dir / "01_BCG_executive_output.md").read_text(encoding="utf-8")
    assert "Restore the missing external preflight configuration" in bcg
    assert bcg.index("Restore the missing external preflight configuration") < bcg.index(
        "Keep the canonical preflight RCA"
    )


def test_valid_preflight_runs_runtime_and_bootstrap_without_secret_leakage(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_preflight import run_fresh_e2e_preflight

    run_dir = tmp_path / "runs" / "current-pass"
    run_dir.mkdir(parents=True)
    baseline_ref = _write_passing_baseline(tmp_path)
    calls: list[str] = []

    outcome = run_fresh_e2e_preflight(
        artifact_dir=run_dir,
        e2e_run_id=run_dir.name,
        repo_root=tmp_path,
        baseline_ref=baseline_ref,
        environ={
            "APPS_RG_ROUTE_HMAC_SECRET": "secret-value",
            "APPS_RG_ROUTE_HMAC_KEY_ID": "local-key",
        },
        runtime_check=lambda: calls.append("runtime"),
        bootstrap=lambda: calls.append("bootstrap") or {"status": "PASS", "exit_code": 0},
    )

    assert outcome.passed is True
    assert calls == ["runtime", "bootstrap"]
    receipt_text = (run_dir / "e2e_preflight_receipt.json").read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["status"] == "PASS"
    assert receipt["route_signing_secret_present"] is True
    assert receipt["route_signing_key_id"] == "local-key"
    assert "secret-value" not in receipt_text
    ledger = json.loads((run_dir / "e2e_stage_ledger.json").read_text(encoding="utf-8"))
    assert [(row["stage_id"], row["status"]) for row in ledger["entries"]] == [("PREFLIGHT", "PASS")]
    assert not (run_dir / "APPS_RG_MANDATORY_RUN_OUTPUT.json").exists()


def test_runtime_preflight_failure_is_non_retriable_and_skips_bootstrap(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_preflight import run_fresh_e2e_preflight

    run_dir = tmp_path / "runs" / "runtime-failure"
    run_dir.mkdir(parents=True)
    baseline_ref = _write_passing_baseline(tmp_path)
    calls: list[str] = []

    def fail_runtime() -> None:
        calls.append("runtime")
        raise RuntimeError("PROVIDER_CREDENTIAL_REQUIRED")

    outcome = run_fresh_e2e_preflight(
        artifact_dir=run_dir,
        e2e_run_id=run_dir.name,
        repo_root=tmp_path,
        baseline_ref=baseline_ref,
        environ={
            "APPS_RG_ROUTE_HMAC_SECRET": "secret-value",
            "APPS_RG_ROUTE_HMAC_KEY_ID": "local-key",
        },
        runtime_check=fail_runtime,
        bootstrap=lambda: calls.append("bootstrap"),
    )

    assert outcome.passed is False
    assert calls == ["runtime"]
    receipt = json.loads((run_dir / "e2e_preflight_receipt.json").read_text(encoding="utf-8"))
    assert receipt["failure_code"] == "PRODUCTION_RUNTIME_PREFLIGHT_FAILED"
    assert receipt["retry_policy"] == "NON_RETRIABLE_CONFIGURATION"


def test_initial_otel_failure_emits_standard_terminal_evidence_before_dependencies(
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.e2e_preflight import run_fresh_e2e_preflight

    run_dir = tmp_path / "runs" / "otel-marker-failure"
    run_dir.mkdir(parents=True)
    calls: list[str] = []
    outcome = run_fresh_e2e_preflight(
        artifact_dir=run_dir,
        e2e_run_id=run_dir.name,
        repo_root=tmp_path,
        baseline_ref=_write_passing_baseline(tmp_path),
        environ={
            "APPS_RG_ROUTE_HMAC_SECRET": "secret-value",
            "APPS_RG_ROUTE_HMAC_KEY_ID": "local-key",
        },
        dependency_check=lambda: calls.append("dependency"),
        runtime_check=lambda: calls.append("runtime"),
        bootstrap=lambda: calls.append("bootstrap"),
        initial_failure_code="COLLECTOR_MARKER_NOT_CAPTURED",
        initial_failure_detail="The configured collector did not capture the per-run preflight marker.",
    )

    assert outcome.passed is False
    assert outcome.exit_code == 2
    assert calls == []
    receipt = json.loads((run_dir / "e2e_preflight_receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "BLOCKED"
    assert receipt["failure_code"] == "COLLECTOR_MARKER_NOT_CAPTURED"
    assert receipt["research_attempt_count"] == 0
    ledger = json.loads((run_dir / "e2e_stage_ledger.json").read_text(encoding="utf-8"))
    assert [(row["stage_id"], row["status"]) for row in ledger["entries"]] == [
        ("PREFLIGHT", "BLOCKED"),
        ("CLOSEOUT", "PASS"),
    ]
    mandatory = json.loads(
        (run_dir / "APPS_RG_MANDATORY_RUN_OUTPUT.json").read_text(encoding="utf-8")
    )
    assert mandatory["result_summary"]["completion_fault"] == "COLLECTOR_MARKER_NOT_CAPTURED"
    assert mandatory["result_summary"]["research_artifact_dir"] == "NOT_REACHED:PREFLIGHT"


def test_external_runtime_dependency_failure_is_receipted_and_skips_runtime_and_bootstrap(
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.e2e_preflight import run_fresh_e2e_preflight
    from apps_rg.runtime import standalone_dependency_posture as posture

    run_dir = tmp_path / "runs" / "dependency-failure"
    run_dir.mkdir(parents=True)
    calls: list[str] = []

    def _failing_check():
        calls.append("dependency")
        raise posture.AppRuntimeIndependenceError("simulated runtime dependency failure")

    outcome = run_fresh_e2e_preflight(
        artifact_dir=run_dir,
        e2e_run_id=run_dir.name,
        repo_root=tmp_path,
        baseline_ref=_write_passing_baseline(tmp_path),
        environ={
            "APPS_RG_ROUTE_HMAC_SECRET": "secret-value",
            "APPS_RG_ROUTE_HMAC_KEY_ID": "local-key",
        },
        dependency_check=_failing_check,
        runtime_check=lambda: calls.append("runtime"),
        bootstrap=lambda: calls.append("bootstrap"),
    )

    assert outcome.passed is False
    assert calls == ["dependency"]
    receipt = json.loads((run_dir / "e2e_preflight_receipt.json").read_text(encoding="utf-8"))
    assert receipt["failure_code"] == "APP_RUNTIME_INDEPENDENCE_PREFLIGHT_FAILED"


def test_missing_key_id_alone_is_reported_without_running_dependencies(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_preflight import run_fresh_e2e_preflight

    run_dir = tmp_path / "runs" / "missing-key-id"
    run_dir.mkdir(parents=True)
    calls: list[str] = []
    outcome = run_fresh_e2e_preflight(
        artifact_dir=run_dir,
        e2e_run_id=run_dir.name,
        repo_root=tmp_path,
        baseline_ref=_write_passing_baseline(tmp_path),
        environ={"APPS_RG_ROUTE_HMAC_SECRET": "secret-value"},
        runtime_check=lambda: calls.append("runtime"),
        bootstrap=lambda: calls.append("bootstrap"),
    )

    assert outcome.passed is False
    assert calls == []
    receipt_text = (run_dir / "e2e_preflight_receipt.json").read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["missing_environment_variables"] == ["APPS_RG_ROUTE_HMAC_KEY_ID"]
    assert receipt["route_signing_secret_present"] is True
    assert receipt["route_signing_key_id_present"] is False
    assert "secret-value" not in receipt_text


def test_failed_fact_vector_bootstrap_closes_out_before_research(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_preflight import run_fresh_e2e_preflight

    run_dir = tmp_path / "runs" / "bootstrap-failure"
    run_dir.mkdir(parents=True)
    calls: list[str] = []
    outcome = run_fresh_e2e_preflight(
        artifact_dir=run_dir,
        e2e_run_id=run_dir.name,
        repo_root=tmp_path,
        baseline_ref=_write_passing_baseline(tmp_path),
        environ={
            "APPS_RG_ROUTE_HMAC_SECRET": "secret-value",
            "APPS_RG_ROUTE_HMAC_KEY_ID": "local-key",
        },
        runtime_check=lambda: calls.append("runtime"),
        bootstrap=lambda: calls.append("bootstrap") or {"status": "FAIL", "exit_code": 1},
    )

    assert outcome.passed is False
    assert calls == ["runtime", "bootstrap"]
    receipt = json.loads((run_dir / "e2e_preflight_receipt.json").read_text(encoding="utf-8"))
    assert receipt["failure_code"] == "FACT_VECTOR_BOOTSTRAP_PREFLIGHT_FAILED"
    assert receipt["research_attempt_count"] == 0
    mandatory = json.loads((run_dir / "APPS_RG_MANDATORY_RUN_OUTPUT.json").read_text(encoding="utf-8"))
    assert mandatory["operational_failure_forensics"]["judge_matrix"][0]["current"] == ("JUDGES_NOT_REACHED")


def test_product_continuation_is_signed_digest_bound_and_consumed_once(
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.e2e_preflight import (
        E2E_PREFLIGHT_CONTINUATION_CONSUMPTION_FILENAME,
        E2E_PREFLIGHT_CONTINUATION_RECEIPT_FILENAME,
        run_fresh_e2e_preflight,
        validate_preflight_continuation,
    )

    run_dir = tmp_path / "runs" / "signed-continuation"
    run_dir.mkdir(parents=True)
    issued = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    identity = _run_identity(run_dir.name)
    outcome = run_fresh_e2e_preflight(
        artifact_dir=run_dir,
        e2e_run_id=run_dir.name,
        repo_root=tmp_path,
        baseline_ref=_write_passing_baseline(tmp_path),
        environ={
            "APPS_RG_ROUTE_HMAC_SECRET": "continuation-secret",
            "APPS_RG_ROUTE_HMAC_KEY_ID": "key-001",
        },
        run_identity=identity,
        clock=lambda: issued,
        nonce_factory=lambda: "nonce-001",
    )

    assert outcome.passed is True
    canonical_path = run_dir / E2E_PREFLIGHT_CONTINUATION_RECEIPT_FILENAME
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    assert canonical["product_entry_eligible"] is True
    assert canonical["identity"] == identity
    assert canonical["continuation_signature"].startswith("hmac-sha256:")
    legacy = json.loads((run_dir / "e2e_preflight_receipt.json").read_text(encoding="utf-8"))
    assert legacy["compatibility_projection"]["classification"] == "NON_PRODUCT_ONLY"

    first = validate_preflight_continuation(
        receipt_path=canonical_path,
        secret="continuation-secret",
        expected_e2e_run_id=run_dir.name,
        expected_key_id="key-001",
        expected_identity=identity,
        consumer_id="whole-run-entrypoint",
        consume=True,
        now_utc=issued + timedelta(seconds=1),
    )
    second = validate_preflight_continuation(
        receipt_path=canonical_path,
        secret="continuation-secret",
        expected_e2e_run_id=run_dir.name,
        expected_identity=identity,
        now_utc=issued + timedelta(seconds=2),
    )

    assert first.valid is True
    assert (run_dir / E2E_PREFLIGHT_CONTINUATION_CONSUMPTION_FILENAME).is_file()
    assert second.valid is False
    assert "continuation_already_consumed" in second.errors


def test_apps_eval_accepts_two_stage_legacy_preflight_product_identity_binding(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from apps_eval.adapters.apps_rg import _verified_preflight
    from apps_rg.runtime.e2e_preflight import (
        E2E_PREFLIGHT_CONTINUATION_RECEIPT_FILENAME,
        bind_preflight_to_product_identity,
        run_fresh_e2e_preflight,
        validate_preflight_continuation,
    )

    secret = "two-stage-product-binding-secret"
    key_id = "two-stage-key"
    run_dir = tmp_path / "runs" / "two-stage-product-entry"
    run_dir.mkdir(parents=True)
    outcome = run_fresh_e2e_preflight(
        artifact_dir=run_dir,
        e2e_run_id=run_dir.name,
        repo_root=tmp_path,
        baseline_ref=_write_passing_baseline(tmp_path),
        environ={
            "APPS_RG_ROUTE_HMAC_SECRET": secret,
            "APPS_RG_ROUTE_HMAC_KEY_ID": key_id,
        },
    )
    assert outcome.passed is True
    continuation_path = run_dir / E2E_PREFLIGHT_CONTINUATION_RECEIPT_FILENAME
    validation = validate_preflight_continuation(
        receipt_path=continuation_path,
        secret=secret,
        expected_e2e_run_id=run_dir.name,
        expected_key_id=key_id,
        consumer_id="apps_rg.whole_run.primary",
        consume=True,
        require_product_identity=False,
    )
    assert validation.valid is True
    bind_preflight_to_product_identity(
        validation=validation,
        receipt_path=continuation_path,
        secret=secret,
        identity=_run_identity(run_dir.name),
        consumer_id="apps_rg.whole_run.primary",
    )
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", secret)
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_KEY_ID", key_id)

    _entry, _ref, _digest, errors = _verified_preflight(run_dir, {})

    assert errors == []


def test_product_continuation_rejects_tamper_and_expiry(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_preflight import (
        E2E_PREFLIGHT_CONTINUATION_RECEIPT_FILENAME,
        run_fresh_e2e_preflight,
        validate_preflight_continuation,
    )

    issued = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    run_dir = tmp_path / "runs" / "tampered-continuation"
    run_dir.mkdir(parents=True)
    identity = _run_identity(run_dir.name)
    run_fresh_e2e_preflight(
        artifact_dir=run_dir,
        e2e_run_id=run_dir.name,
        repo_root=tmp_path,
        baseline_ref=_write_passing_baseline(tmp_path),
        environ={
            "APPS_RG_ROUTE_HMAC_SECRET": "continuation-secret",
            "APPS_RG_ROUTE_HMAC_KEY_ID": "key-001",
        },
        run_identity=identity,
        continuation_ttl_seconds=2,
        clock=lambda: issued,
        nonce_factory=lambda: "nonce-002",
    )
    canonical_path = run_dir / E2E_PREFLIGHT_CONTINUATION_RECEIPT_FILENAME
    expired = validate_preflight_continuation(
        receipt_path=canonical_path,
        secret="continuation-secret",
        expected_e2e_run_id=run_dir.name,
        expected_identity=identity,
        now_utc=issued + timedelta(seconds=2),
    )
    assert expired.valid is False
    assert "continuation_expired" in expired.errors

    payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    payload["identity"]["tenant_id"] = "other-tenant"
    canonical_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tampered = validate_preflight_continuation(
        receipt_path=canonical_path,
        secret="continuation-secret",
        expected_e2e_run_id=run_dir.name,
        expected_identity=identity,
        now_utc=issued + timedelta(seconds=1),
    )
    assert tampered.valid is False
    assert "continuation_payload_digest_mismatch" in tampered.errors
    assert "continuation_signature_invalid" in tampered.errors
    assert "continuation_identity_mismatch" in tampered.errors
