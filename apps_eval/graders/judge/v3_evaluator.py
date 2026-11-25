"""Clean-Slate Judge v3 Stage B Atomic Binary Evaluator (`<= 280L`).

Enforces:
1. Cold-read takeaway generated FIRST before any check verdict.
2. Atomic `YES` / `NO` decision per profile criterion (`4-6` checks).
3. Mandatory non-empty verbatim `evidence_span` on every `NO` verdict (fail-closed).
4. Mechanical `passed` (`all(critical == YES) and sum(passed_weights) >= pass_threshold`)
   and `normalized_unit_score` in `[0.0, 1.0]` with zero post-hoc regex score caps.
5. Honest `llm_judge_executed: false, normalized_unit_score: null` when skipped or Stage-A blocked.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.graders.judge._core_governance_bridge import get_judge_v3_rigor_engine
from apps_eval.graders.judge.blind_protocol import (
    BlindJudgeBundle,
    build_sealed_blind_judge_bundle,
    infer_provider_family,
    validate_blind_judge_verdict_provenance,
)
from apps_eval.graders.judge.frontier_rubric_contract import validate_failure_tags
from apps_eval.graders.judge.preflight_lint import PreflightLintReceipt
from apps_eval.graders.judge.v3_registry import (
    JudgeProfileV3,
    JudgeRubricRegistryV3,
    render_v3_rubric_prompt,
)

_rigor = get_judge_v3_rigor_engine()

JUDGE_V3_SCORECARD_SCHEMA_VERSION = "agents.judge_v3_scorecard.v3"
JudgeV3SchemaError = _rigor.JudgeV3SchemaError
JudgeV3ProvenanceError = _rigor.JudgeV3ProvenanceError
verify_verbatim_failure_span = _rigor.verify_verbatim_failure_span
score_v3_atomic_checks = _rigor.score_v3_atomic_checks


@dataclass(frozen=True)
class JudgeV3Scorecard:
    """Immutable, hash-bound Stage B atomic binary scorecard."""

    schema_version: str
    profile_id: str
    cluster: str
    rubric_sha256: str
    artifact_id: str
    artifact_sha256: str
    bundle_digest: str
    author_model_family: str
    judge_model_id: str
    judge_model_family: str
    evaluator_kind: str
    llm_judge_executed: bool
    status: str
    passed: bool
    normalized_unit_score: float | None
    pass_threshold: float
    critical_veto_triggered: bool
    cold_read_takeaway: str
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    failed_check_ids: tuple[str, ...] = ()
    failure_tags: tuple[str, ...] = ()
    preflight_failed_gates: tuple[str, ...] = ()
    deterministic_priming_stripped: bool = True
    judge_input_keys: tuple[str, ...] = ()
    external_http_call_count: int = 0
    conversation_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["verdict"] = self.verdict
        out["overall_score"] = self.normalized_unit_score
        out["failed_check_ids"] = list(self.failed_check_ids)
        out["failure_tags"] = list(self.failure_tags)
        out["preflight_failed_gates"] = list(self.preflight_failed_gates)
        out["judge_input_keys"] = list(self.judge_input_keys)
        return out


def build_v3_response_schema(profile: JudgeProfileV3) -> dict[str, Any]:
    """Delegate strict Stage B JSON schema generation to centralized `core-governance`."""
    return dict(_rigor.build_v3_response_json_schema(profile))


def build_v3_evaluation_bundle(
    *,
    profile_token: str,
    artifact_id: str,
    raw_input: Mapping[str, Any],
    author_model_family: str,
    registry: JudgeRubricRegistryV3 | None = None,
    artifact_path: Path | None = None,
    repo_root: Path | None = None,
    available_families: Sequence[str] | None = None,
) -> tuple[BlindJudgeBundle, JudgeProfileV3, str]:
    """Seal Layer 0 `BlindJudgeBundle` and compile the concise Stage B v3 prompt."""
    reg = registry if registry is not None else JudgeRubricRegistryV3.load()
    profile = reg.get_profile(profile_token)
    bundle = build_sealed_blind_judge_bundle(
        artifact_id=artifact_id,
        raw_input=raw_input,
        author_model_family=author_model_family,
        rubric_id=profile.profile_id,
        rubric_sha256=reg.rubric_sha256,
        artifact_path=artifact_path,
        repo_root=repo_root,
        available_families=available_families,
    )
    rubric_block = render_v3_rubric_prompt(profile)
    payload_json = json.dumps(bundle.payload, ensure_ascii=False, sort_keys=True)
    prompt = f"{rubric_block}\n\nBLIND_EVALUATION_PACKET:\n{payload_json}\n"
    return bundle, profile, prompt


def build_skipped_v3_scorecard(
    *,
    bundle: BlindJudgeBundle,
    profile: JudgeProfileV3,
    rubric_sha256: str,
    preflight_receipt: PreflightLintReceipt | None = None,
    reason: str = "SKIPPED_NO_LLM",
) -> JudgeV3Scorecard:
    """Emit honest `normalized_unit_score: None` scorecard when Stage A blocks or LLM is offline."""
    stage_a_blocked = preflight_receipt is not None and not preflight_receipt.passed
    return JudgeV3Scorecard(
        schema_version=JUDGE_V3_SCORECARD_SCHEMA_VERSION,
        profile_id=profile.profile_id,
        cluster=profile.cluster,
        rubric_sha256=rubric_sha256,
        artifact_id=bundle.artifact_id,
        artifact_sha256=bundle.artifact_sha256,
        bundle_digest=bundle.bundle_digest,
        author_model_family=bundle.author_model_family,
        judge_model_id="",
        judge_model_family="",
        evaluator_kind="deterministic_gate" if stage_a_blocked else "skipped",
        llm_judge_executed=False,
        status="STAGE_A_BLOCKED" if stage_a_blocked else reason,
        passed=False,
        normalized_unit_score=None,
        pass_threshold=profile.pass_threshold,
        critical_veto_triggered=False,
        cold_read_takeaway="",
        preflight_failed_gates=tuple(preflight_receipt.failed_gates) if preflight_receipt else (),
        deterministic_priming_stripped=bundle.deterministic_priming_stripped,
        judge_input_keys=tuple(bundle.judge_input_keys),
    )


def parse_and_seal_v3_verdict(
    raw_response: Mapping[str, Any] | str,
    *,
    bundle: BlindJudgeBundle,
    profile: JudgeProfileV3,
    rubric_sha256: str,
    judge_model_id: str,
    judge_model_family: str | None = None,
    artifact_disk_path: Path | None = None,
    verify_verbatim_in: str | None = None,
    primary_source_text: str = "",
    allow_external_http: bool = False,
    external_http_call_count: int = 0,
    conversation_id: str | None = None,
    usage: Mapping[str, Any] | None = None,
) -> JudgeV3Scorecard:
    """Parse Stage B atomic binary JSON via centralized `score_v3_atomic_checks` and seal Layer 0 provenance."""
    if isinstance(raw_response, str):
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").lstrip("json").strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise JudgeV3SchemaError(f"Invalid Judge v3 JSON: {exc}") from exc
    elif isinstance(raw_response, Mapping):
        parsed = dict(raw_response)
    else:
        raise JudgeV3SchemaError("Judge v3 response must be a JSON object.")

    if not isinstance(parsed, Mapping):
        raise JudgeV3SchemaError("Judge v3 response must be a JSON object.")

    resolved_judge_fam = infer_provider_family(judge_model_family or judge_model_id)
    prov_probe = {
        "evaluator_kind": "llm_judge",
        "judge_model_id": judge_model_id,
        "author_model_family": bundle.author_model_family,
        "judge_model_family": resolved_judge_fam,
        "bundle_digest": bundle.bundle_digest,
        "artifact_sha256": bundle.artifact_sha256,
        "deterministic_priming_stripped": bundle.deterministic_priming_stripped,
        "judge_input_keys": list(bundle.judge_input_keys),
        "external_http_call_count": external_http_call_count,
    }
    prov_ok, prov_errs = validate_blind_judge_verdict_provenance(
        prov_probe,
        expected_bundle_digest=bundle.bundle_digest,
        expected_artifact_sha256=bundle.artifact_sha256,
        artifact_disk_path=artifact_disk_path,
        allow_external_http=allow_external_http,
    )
    if not prov_ok:
        raise JudgeV3ProvenanceError(f"BlindJudgeProvenanceError: {prov_errs}")

    try:
        raw_tags = validate_failure_tags(parsed.get("failure_tags") or ())
    except ValueError as exc:
        raise JudgeV3SchemaError(str(exc)) from exc

    raw_checks_obj = parsed.get("checks")
    if isinstance(raw_checks_obj, Mapping):
        for spec in profile.checks:
            c_raw = raw_checks_obj.get(spec.id)
            if isinstance(c_raw, Mapping) and str(c_raw.get("verdict") or "").strip().upper() == "NO":
                span_raw = str(c_raw.get("evidence_span") or "").strip()
                if len(span_raw) < 3:
                    raise JudgeV3SchemaError(f"Check '{spec.id}' answered NO without a verbatim evidence_span.")

    try:
        takeaway, check_verdicts, central_tags, unit_score, critical_veto, passed = _rigor.score_v3_atomic_checks(
            parsed,
            profile,
            verify_verbatim_in=verify_verbatim_in,
            primary_source_text=primary_source_text,
        )
    except JudgeV3SchemaError as exc:
        msg = str(exc)
        if "without a required verbatim 'evidence_span'" in msg:
            raise JudgeV3SchemaError(msg.replace("without a required verbatim 'evidence_span'", "without a verbatim evidence_span")) from exc
        if "not found verbatim in candidate text" in msg:
            raise JudgeV3SchemaError(f"{msg} (not a verbatim substring of the evaluated packet)") from exc
        raise

    sealed_checks: dict[str, dict[str, Any]] = {}
    failed_ids: list[str] = []
    auto_tags: list[str] = []
    for spec in profile.checks:
        cv = check_verdicts[spec.id]
        if not cv.passed:
            failed_ids.append(spec.id)
            auto_tags.append(spec.failure_tag)
        sealed_checks[spec.id] = {
            "verdict": cv.verdict,
            "critical": cv.critical,
            "weight": cv.weight,
            "failure_tag": cv.failure_tag,
            "evidence_span": cv.evidence_span,
        }

    merged_tags = tuple(dict.fromkeys([*auto_tags, *raw_tags, *central_tags])) if not passed else ()

    return JudgeV3Scorecard(
        schema_version=JUDGE_V3_SCORECARD_SCHEMA_VERSION,
        profile_id=profile.profile_id,
        cluster=profile.cluster,
        rubric_sha256=rubric_sha256,
        artifact_id=bundle.artifact_id,
        artifact_sha256=bundle.artifact_sha256,
        bundle_digest=bundle.bundle_digest,
        author_model_family=bundle.author_model_family,
        judge_model_id=judge_model_id,
        judge_model_family=resolved_judge_fam,
        evaluator_kind="llm_judge",
        llm_judge_executed=True,
        status="PASSED" if passed else "FAILED",
        passed=passed,
        normalized_unit_score=unit_score,
        pass_threshold=profile.pass_threshold,
        critical_veto_triggered=critical_veto,
        cold_read_takeaway=takeaway,
        checks=sealed_checks,
        failed_check_ids=tuple(failed_ids),
        failure_tags=merged_tags,
        deterministic_priming_stripped=bundle.deterministic_priming_stripped,
        judge_input_keys=tuple(bundle.judge_input_keys),
        external_http_call_count=external_http_call_count,
        conversation_id=conversation_id,
        usage=dict(usage or {}),
    )
