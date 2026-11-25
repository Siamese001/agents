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
from apps_eval.graders.judge._core_governance_bridge import (
    get_judge_blind_protocol_v3,
    get_judge_ide_router_v3,
)

_ide_rtr = get_judge_ide_router_v3()
_blind_v3 = get_judge_blind_protocol_v3()

FORBIDDEN_DETERMINISTIC_PRIMING_KEYS: frozenset[str] = frozenset(
    _blind_v3.FORBIDDEN_DETERMINISTIC_PRIMING_KEYS
)

NON_LLM_EVALUATOR_KINDS: frozenset[str] = frozenset(
    _blind_v3.NON_LLM_EVALUATOR_KINDS
)

SYNTHETIC_MODEL_TOKENS: tuple[str, ...] = tuple(_ide_rtr.SYNTHETIC_MODEL_TOKENS)


def is_synthetic_model_id(model_id: str) -> bool:
    """Delegate synthetic/stub judge model token detection to centralized IDE router v3."""
    return bool(_ide_rtr.is_synthetic_judge_model(model_id))


def infer_provider_family(model_id: str) -> str:
    """Infer canonical Antigravity IDE family (`neon`, `carbon`, `argon`) or provider family."""
    norm = str(model_id or "").strip().lower()
    if not norm:
        return "unknown"
    try:
        return str(_ide_rtr.normalize_judge_model_family(norm))
    except Exception:  # guardian: allow-broad-exception -- fall back cleanly for catalog provider pins outside IDE family names
        pass
    if any(tok in norm for tok in ("claude", "anthropic")):
        return "anthropic"
    if any(tok in norm for tok in ("gpt", "openai", "o1", "o3", "o4")):
        return "openai"
    if any(tok in norm for tok in ("gemini", "google")):
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
    """Return an approved orthogonal IDE (`neon`/`carbon`/`argon`) or provider family distinct from author."""
    author_fam = infer_provider_family(author_model_family)
    if author_fam in {"neon", "carbon", "argon"} and available_families is None:
        rtr = get_judge_ide_router_v3()
        return str(rtr.resolve_orthogonal_ide_judge_family(author_fam))
    if available_families is not None:
        candidates = [infer_provider_family(f) for f in available_families]
    elif repo_root is not None:
        loaded = sorted(load_approved_judge_families(repo_root).keys())
        candidates = loaded or ["neon", "carbon", "argon"]
    else:
        candidates = ["neon", "carbon", "argon"]

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
    rubric_sha256: str = ""
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
    rubric_sha256: str = "",
    artifact_path: Path | None = None,
    repo_root: Path | None = None,
    available_families: Sequence[str] | None = None,
    fail_on_priming: bool = False,
) -> BlindJudgeBundle:
    """Strip all forbidden deterministic priming keys via centralized blind protocol v3 and seal SHA-256."""
    cleaned_map, stripped_tuple = _blind_v3.strip_or_reject_deterministic_priming(
        raw_input,
        fail_on_priming=fail_on_priming,
    )
    clean_payload = dict(cleaned_map) if isinstance(cleaned_map, Mapping) else {}
    stripped_keys = list(stripped_tuple)

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
        schema_version="agents.blind-judge-bundle.v3",
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha,
        author_model_family=author_fam,
        required_judge_family=judge_fam,
        rubric_id=rubric_id,
        rubric_sha256=str(rubric_sha256 or ""),
        cold_context_isolated=True,
        deterministic_priming_stripped=True,
        stripped_priming_keys=sorted(stripped_keys),
        judge_input_keys=sorted(clean_payload.keys()),
        payload=clean_payload,
    )


build_sealed_v3_blind_bundle = _blind_v3.build_sealed_v3_blind_bundle
verify_sealed_v3_bundle_and_verdict = _blind_v3.verify_sealed_v3_bundle_and_verdict
select_ide_judge_route = _ide_rtr.select_ide_judge_route


def build_fail_closed_missing_verdict_receipt(bundle: BlindJudgeBundle) -> dict[str, Any]:
    """Fail-closed receipt returned whenever a required blind LLM judge verdict is absent."""
    return {
        "status": "BLOCKED",
        "gate_passed": False,
        "llm_judge_executed": False,
        "normalized_unit_score": None,
        "reason_code": "BLIND_JUDGE_VERDICT_MISSING",
        "bundle_digest": bundle.bundle_digest,
        "artifact_sha256": bundle.artifact_sha256,
        "evaluated_at_utc": utc_now_iso(),
    }


def is_borderline_judge_result(
    overall_score: float,
    dimension_scores: Mapping[str, float] | None = None,
    *,
    pass_threshold: float = 0.80,
    unit_margin: float = 0.08,
    borderline_band: Sequence[float] | None = None,
    profile: Any | None = None,
    lower_bound: float = 8.5,
    upper_bound: float = 9.4,
    dimension_floor: float = 8.0,
    dimension_margin: float = 0.6,
) -> bool:
    """Identify near-threshold unit scores (`[0.0, 1.0]`) requiring second-family escalation."""
    dims = dimension_scores or {}
    if profile is not None:
        prof_thresh = getattr(profile, "pass_threshold", None)
        if prof_thresh is not None:
            pass_threshold = float(prof_thresh)
        prof_band = getattr(profile, "borderline_band", None)
        if borderline_band is None and isinstance(prof_band, (list, tuple)) and len(prof_band) == 2:
            borderline_band = prof_band
    if overall_score <= 1.0 and all(float(v) <= 1.0 for v in dims.values()):
        if borderline_band is not None and len(borderline_band) == 2:
            lo_b, hi_b = float(borderline_band[0]), float(borderline_band[1])
            if lo_b <= overall_score <= hi_b:
                return True
            return any(lo_b <= float(s) < pass_threshold for s in dims.values())
        if (pass_threshold - unit_margin) <= overall_score < (pass_threshold + unit_margin):
            return True
        return any(
            (pass_threshold - unit_margin) <= float(s) < pass_threshold
            for s in dims.values()
        )
    if lower_bound <= overall_score < upper_bound:
        return True
    for score in dims.values():
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
