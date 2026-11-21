"""Fail-closed content-hash-bound blind LLM judge protocol with zero deterministic priming.

Enforces:
1. Zero deterministic priming (anti-anchoring): strips deterministic gate summaries/metrics
   before building the blind judge bundle and fails closed if any forbidden priming key leaks.
2. Strict cross-family orthogonality resolved from config/provider_profiles.yaml (zero self-grading).
3. Rejection of NON_LLM_EVALUATOR_KINDS and SYNTHETIC_MODEL_TOKENS on LLM judge receipts.
4. Exact SHA-256 content-hash binding against live disk artifacts.
5. Borderline score escalation detection (8.5 <= overall < 9.4 or dimension near floor).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from apps_eval.contracts.digests import canonical_sha256, sha256_file
from apps_eval.contracts.schemas import utc_now_iso

FORBIDDEN_DETERMINISTIC_PRIMING_KEYS: frozenset[str] = frozenset(
    {
        "deterministic_gate_summary",
        "deterministic_violation_count",
        "deterministic_visual_ui_metrics",
        "visual_ui_metrics_summary",
        "tier1_gate_receipt",
        "x2_gate_outputs",
        "min_light_contrast_ratio",
        "min_dark_contrast_ratio",
    }
)

NON_LLM_EVALUATOR_KINDS: frozenset[str] = frozenset(
    {
        "deterministic_gate",
        "heuristic",
        "structural_heuristic",
        "mock_judge",
        "rule_based",
        "static_stub",
    }
)

SYNTHETIC_MODEL_TOKENS: tuple[str, ...] = (
    "model_family_a",
    "model_family_b",
    "fake_model",
    "mock_model",
    "stub_model",
    "placeholder",
    "dummy_judge",
)


def is_synthetic_model_id(model_id: str) -> bool:
    """Return True if model_id matches a known synthetic/stub test token."""
    norm = str(model_id or "").strip().lower()
    if not norm:
        return True
    return any(tok in norm for tok in SYNTHETIC_MODEL_TOKENS)


def infer_provider_family(model_id: str) -> str:
    """Infer canonical provider family from a model identifier."""
    norm = str(model_id or "").strip().lower()
    if any(tok in norm for tok in ("claude", "anthropic")):
        return "anthropic"
    if any(tok in norm for tok in ("gpt", "openai", "o1", "o3", "o4")):
        return "openai"
    if any(tok in norm for tok in ("gemini", "google", "argon", "neon", "carbon")):
        return "google"
    if any(tok in norm for tok in ("local", "open_weights")):
        return "local_open_weights"
    return norm or "unknown"


def load_approved_judge_families(repo_root: Path) -> dict[str, list[str]]:
    """Resolve approved judge model families dynamically from config/provider_profiles.yaml."""
    cfg_path = Path(repo_root).resolve() / "config" / "provider_profiles.yaml"
    if not cfg_path.is_file():
        return {}
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    families: dict[str, list[str]] = {}
    judge_models = raw.get("judge_models") or {}

    def _collect(node: Any) -> None:
        if isinstance(node, str) and node.strip():
            fam = infer_provider_family(node)
            if fam not in {"unknown"} and not is_synthetic_model_id(node):
                families.setdefault(fam, [])
                if node not in families[fam]:
                    families[fam].append(node)
        elif isinstance(node, Mapping):
            for v in node.values():
                _collect(v)
        elif isinstance(node, list):
            for item in node:
                _collect(item)

    _collect(judge_models)
    return families


def resolve_orthogonal_judge_family(
    author_model_family: str,
    *,
    repo_root: Path | None = None,
    available_families: Sequence[str] | None = None,
) -> str:
    """Return an approved orthogonal provider family distinct from author_model_family."""
    author_fam = infer_provider_family(author_model_family)
    if available_families is not None:
        candidates = [infer_provider_family(f) for f in available_families]
    elif repo_root is not None:
        candidates = sorted(load_approved_judge_families(repo_root).keys())
    else:
        candidates = ["anthropic", "google", "openai"]

    for fam in candidates:
        if fam and fam != author_fam and fam != "unknown":
            return fam
    raise ValueError(
        f"No orthogonal judge family available distinct from author_model_family={author_fam!r}"
    )


@dataclass(frozen=True)
class BlindJudgeBundle:
    """Cold-reader evaluation bundle stripped of all deterministic priming signals."""

    schema_version: str
    artifact_id: str
    artifact_sha256: str
    author_model_family: str
    required_judge_family: str
    rubric_id: str
    cold_context_isolated: bool
    deterministic_priming_stripped: bool
    stripped_priming_keys: list[str]
    judge_input_keys: list[str]
    payload: dict[str, Any]
    bundle_digest: str = ""
    created_at_utc: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.bundle_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("bundle_digest",))
            object.__setattr__(self, "bundle_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_sealed_blind_judge_bundle(
    *,
    artifact_id: str,
    raw_input: Mapping[str, Any],
    author_model_family: str,
    rubric_id: str,
    artifact_path: Path | None = None,
    repo_root: Path | None = None,
    available_families: Sequence[str] | None = None,
) -> BlindJudgeBundle:
    """Strip all forbidden deterministic priming keys and seal a SHA-256 blind judge bundle."""
    stripped_keys: list[str] = []
    clean_payload: dict[str, Any] = {}
    for key, value in raw_input.items():
        if key in FORBIDDEN_DETERMINISTIC_PRIMING_KEYS:
            stripped_keys.append(key)
            continue
        clean_payload[key] = value

    artifact_sha = (
        sha256_file(artifact_path)
        if artifact_path is not None and artifact_path.is_file()
        else canonical_sha256(clean_payload)
    )
    author_fam = infer_provider_family(author_model_family)
    judge_fam = resolve_orthogonal_judge_family(
        author_fam,
        repo_root=repo_root,
        available_families=available_families,
    )
    return BlindJudgeBundle(
        schema_version="agents.blind-judge-bundle.v2",
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha,
        author_model_family=author_fam,
        required_judge_family=judge_fam,
        rubric_id=rubric_id,
        cold_context_isolated=True,
        deterministic_priming_stripped=True,
        stripped_priming_keys=sorted(stripped_keys),
        judge_input_keys=sorted(clean_payload.keys()),
        payload=clean_payload,
    )


def build_fail_closed_missing_verdict_receipt(bundle: BlindJudgeBundle) -> dict[str, Any]:
    """Fail-closed receipt returned whenever a required blind LLM judge verdict is absent."""
    return {
        "status": "BLOCKED",
        "gate_passed": False,
        "reason_code": "BLIND_JUDGE_VERDICT_MISSING",
        "bundle_digest": bundle.bundle_digest,
        "artifact_sha256": bundle.artifact_sha256,
        "evaluated_at_utc": utc_now_iso(),
    }


def is_borderline_judge_result(
    overall_score: float,
    dimension_scores: Mapping[str, float],
    *,
    lower_bound: float = 8.5,
    upper_bound: float = 9.4,
    dimension_floor: float = 8.0,
    dimension_margin: float = 0.6,
) -> bool:
    """Identify borderline judge scores that require orthogonal second-family escalation."""
    if lower_bound <= overall_score < upper_bound:
        return True
    for score in dimension_scores.values():
        if dimension_floor <= float(score) < (dimension_floor + dimension_margin):
            return True
    return False


def validate_blind_judge_verdict_provenance(
    verdict: Mapping[str, Any],
    *,
    expected_bundle_digest: str | None = None,
    expected_artifact_sha256: str | None = None,
    artifact_disk_path: Path | None = None,
    require_no_deterministic_priming: bool = True,
    allow_external_http: bool = False,
    min_distinct_families: int = 1,
) -> tuple[bool, list[str]]:
    """Fail-closed provenance verification for blind LLM judge verdicts."""
    reasons: list[str] = []

    evaluator_kind = str(verdict.get("evaluator_kind") or "").strip().lower()
    if not evaluator_kind or evaluator_kind in NON_LLM_EVALUATOR_KINDS:
        reasons.append(f"NON_LLM_EVALUATOR_KIND:{evaluator_kind or 'missing'}")

    model_id = str(verdict.get("judge_model_id") or "")
    if is_synthetic_model_id(model_id):
        reasons.append(f"SYNTHETIC_MODEL_ID_REJECTED:{model_id or 'empty'}")

    author_fam = infer_provider_family(str(verdict.get("author_model_family") or ""))
    judge_fam = infer_provider_family(str(verdict.get("judge_model_family") or model_id))
    if not author_fam or author_fam == "unknown":
        reasons.append("MISSING_AUTHOR_MODEL_FAMILY")
    if not judge_fam or judge_fam == "unknown":
        reasons.append("MISSING_JUDGE_MODEL_FAMILY")
    if author_fam and judge_fam and author_fam == judge_fam:
        reasons.append(f"SELF_GRADING_FORBIDDEN:{author_fam}=={judge_fam}")

    families_list = verdict.get("judge_model_families")
    if isinstance(families_list, list) and families_list:
        distinct = {infer_provider_family(str(f)) for f in families_list if str(f).strip()}
        if author_fam in distinct:
            reasons.append(f"SELF_GRADING_IN_PANEL:{author_fam}")
        if len(distinct) < min_distinct_families:
            reasons.append(f"INSUFFICIENT_DISTINCT_FAMILIES:{len(distinct)}<{min_distinct_families}")
    elif min_distinct_families > 1:
        reasons.append(f"INSUFFICIENT_DISTINCT_FAMILIES:1<{min_distinct_families}")

    if not allow_external_http and int(verdict.get("external_http_call_count", 0)) > 0:
        reasons.append("EXTERNAL_HTTP_JUDGE_FORBIDDEN")

    if expected_bundle_digest is not None:
        got_digest = str(verdict.get("bundle_digest") or "")
        if got_digest != expected_bundle_digest:
            reasons.append("BUNDLE_DIGEST_MISMATCH")

    recorded_sha = str(verdict.get("artifact_sha256") or "")
    if expected_artifact_sha256 is not None and recorded_sha != expected_artifact_sha256:
        reasons.append("ARTIFACT_SHA256_MISMATCH")
    if artifact_disk_path is not None:
        if not artifact_disk_path.is_file():
            reasons.append("ARTIFACT_DISK_FILE_MISSING")
        else:
            live_sha = sha256_file(artifact_disk_path)
            if recorded_sha != live_sha:
                reasons.append("STALE_ARTIFACT_RECEIPT_SHA256")

    if require_no_deterministic_priming:
        if verdict.get("deterministic_priming_stripped") is not True:
            reasons.append("DETERMINISTIC_PRIMING_NOT_STRIPPED")
        input_keys = set(verdict.get("judge_input_keys") or [])
        leaked = sorted(input_keys & FORBIDDEN_DETERMINISTIC_PRIMING_KEYS)
        if leaked:
            reasons.append(f"DETERMINISTIC_PRIMING_LEAKED:{','.join(leaked)}")

    return (len(reasons) == 0), reasons
