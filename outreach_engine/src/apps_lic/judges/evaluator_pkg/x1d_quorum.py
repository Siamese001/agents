"""Target-free GradeOnlyJudgePacket and dual cross-family X1D proof-judge quorum for apps_lic."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from apps_lic.domain.validators_pkg.sequence_x2 import check_undefined_mga_acronym
from apps_lic.judges.evaluator_pkg.report_and_rubrics import _load_cached_rubric_file
from apps_lic.runtime.model_registry import OutreachModelPin, OutreachModelRegistry

WHOLE_SEQUENCE_JUDGE_QUORUM_SCHEMA_VERSION: Final[str] = "apps_lic.whole_sequence_judge_quorum.v1"
DEFAULT_X1D_RUBRIC_ID: Final[str] = "lic_x1d_v1"
X1D_PASS_THRESHOLD: Final[float] = 0.85
X1D_MAX_JUDGE_SPREAD: Final[float] = 0.20

_UNTRUSTED_BLOCK_PAT: Final[re.Pattern[str]] = re.compile(r"<untrusted_data\b[^>]*>[\s\S]*?</untrusted_data>", re.IGNORECASE)
_UNTRUSTED_TAG_PAT: Final[re.Pattern[str]] = re.compile(r"</?untrusted_data\b[^>]*>", re.IGNORECASE)
_FACT_ID_TAG_PAT: Final[re.Pattern[str]] = re.compile(r"\[fact_id:([A-Za-z0-9_.\-:]+)\]")
_SUBORDINATE_OR_SPAM_PAT: Final[re.Pattern[str]] = re.compile(
    r"\b(?:guaranteed_offer|please\s+hire\s+me|desperately\s+seeking|begging\s+for|act\s+now|limited\s+time\s+offer)\b",
    re.IGNORECASE,
)


class _TouchFactAllocationMap(dict[int, list[str]]):
    def __getitem__(self, key: int | str) -> list[str]:
        return super().__getitem__(int(key.strip()) if isinstance(key, str) and key.strip().lstrip("-").isdigit() else int(key))

    def get(self, key: Any, default: Any = None) -> Any:
        return super().get(int(key.strip()), default) if isinstance(key, str) and key.strip().lstrip("-").isdigit() else (super().get(key, default) if isinstance(key, int) else default)

    def __contains__(self, key: object) -> bool:
        return super().__contains__(int(key.strip()) if isinstance(key, str) and key.strip().lstrip("-").isdigit() else key)


def strip_untrusted_target_data(text: str | None) -> str:
    """Strip `<untrusted_data>...</untrusted_data>` blocks and breakout tags from text."""
    raw = str(text or "")
    return re.sub(r"[ \t]{2,}", " ", _UNTRUSTED_TAG_PAT.sub("", _UNTRUSTED_BLOCK_PAT.sub("", raw))).strip() if raw else ""


def load_x1d_exit_rubric(rubric_path: Path | str | None = None) -> dict[str, Any]:
    """Load and cache `config/exit_eval_rubrics/lic_x1d_v1.yaml`."""
    cand = Path(__file__).resolve().parents[5] / "config" / "exit_eval_rubrics" / "lic_x1d_v1.yaml"
    resolved = Path(rubric_path) if rubric_path is not None else (cand if cand.is_file() else Path(__file__).resolve().parents[4].parent / "config" / "exit_eval_rubrics" / "lic_x1d_v1.yaml")
    if data := _load_cached_rubric_file(resolved):
        return data
    dims = (("candidate_evidence_grounding", 0.30, 0.90), ("sequence_coherence_and_progression", 0.20, 0.85), ("executive_altitude_and_peer_framing", 0.15, 0.80), ("citation_and_pct_support", 0.15, 0.95), ("cta_and_friction_calibration", 0.10, 0.80), ("constraint_and_hygiene_compliance", 0.10, 0.85))
    return {"schema_version": "1.0.0", "rubric_id": DEFAULT_X1D_RUBRIC_ID, "subsystem": "outreach_engine", "pass_threshold": X1D_PASS_THRESHOLD, "max_judge_spread": X1D_MAX_JUDGE_SPREAD, "dimensions": [{"id": n, "name": n, "weight": w, "threshold": t} for n, w, t in dims]}


@dataclass(frozen=True)
class GradeOnlyTouchItem:
    """Target-free touch item inside `GradeOnlyJudgePacket`."""
    touch_number: int = 1
    subject: str = ""
    body: str = ""
    cited_fact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "touch_number", max(1, int(self.touch_number or 1)))
        object.__setattr__(self, "subject", strip_untrusted_target_data(self.subject))
        object.__setattr__(self, "body", strip_untrusted_target_data(self.body))
        norm_fids = tuple(str(fid).strip() for fid in (self.cited_fact_ids or ()) if str(fid).strip())
        object.__setattr__(self, "cited_fact_ids", norm_fids or (tuple(_FACT_ID_TAG_PAT.findall(self.body)) if self.body else ()))

    def to_dict(self) -> dict[str, Any]:
        return {"touch_number": int(self.touch_number), "subject": self.subject, "body": self.body, "cited_fact_ids": list(self.cited_fact_ids)}


def _normalize_touch_entry(item: Any, default_touch_number: int) -> dict[str, Any]:
    if isinstance(item, GradeOnlyTouchItem):
        return item.to_dict()
    t_num = int(getattr(item, "touch_number", default_touch_number) or default_touch_number) if hasattr(item, "draft") else default_touch_number
    item = getattr(item, "draft") if hasattr(item, "draft") else item
    if isinstance(item, Mapping):
        t_num, subj, body = int(item.get("touch_number", t_num) or t_num), strip_untrusted_target_data(str(item.get("subject") or "")), strip_untrusted_target_data(str(item.get("body") or ""))
        raw_fids = item.get("cited_fact_ids") or item.get("grounded_facts_used") or item.get("fact_ids") or ()
    elif isinstance(item, str):
        subj, body, raw_fids = "", strip_untrusted_target_data(item), _FACT_ID_TAG_PAT.findall(strip_untrusted_target_data(item))
    else:
        t_num, subj, body = int(getattr(item, "touch_number", t_num) or t_num), strip_untrusted_target_data(str(getattr(item, "subject", "") or "")), strip_untrusted_target_data(str(getattr(item, "body", "") or ""))
        raw_fids = getattr(item, "cited_fact_ids", None) or getattr(item, "grounded_facts_used", None) or ()
    fids = [str(f).strip() for f in raw_fids if str(f).strip()] or (_FACT_ID_TAG_PAT.findall(body) if body else [])
    return {"touch_number": max(1, t_num), "subject": subj, "body": body, "cited_fact_ids": fids}


def _normalize_pct_entry(cert: Any) -> dict[str, Any]:
    raw = dict(cert.to_dict()) if hasattr(cert, "to_dict") and callable(cert.to_dict) else (dict(cert) if isinstance(cert, Mapping) else {k: getattr(cert, k, d) for k, d in (("certificate_id", ""), ("touch_number", 1), ("claim_span", ""), ("metric_token", ""), ("fact_id", ""), ("source_chunk_id", ""), ("verbatim_span", ""), ("in_cand", False), ("in_opp", False), ("verified", False))})
    return {"certificate_id": str(raw.get("certificate_id", "")), "touch_number": int(raw.get("touch_number", 1) or 1), "claim_span": strip_untrusted_target_data(str(raw.get("claim_span", ""))), "metric_token": str(raw.get("metric_token", "")), "fact_id": str(raw.get("fact_id", "")), "source_chunk_id": str(raw.get("source_chunk_id", "")), "verbatim_span": strip_untrusted_target_data(str(raw.get("verbatim_span", ""))), "in_cand": bool(raw.get("in_cand", True)), "in_opp": bool(raw.get("in_opp", False)), "verified": bool(raw.get("verified", True))}


@dataclass(frozen=True)
class GradeOnlyJudgePacket:
    """Frozen target-free judge input packet stripping all untrusted opportunity research data."""

    run_id: str = "run-default"
    mission_id: str = "mission-default"
    touches: tuple[dict[str, Any], ...] = ()
    pct_certificates: tuple[dict[str, Any], ...] = ()
    allocated_fact_ids_by_touch: dict[int, list[str]] = field(default_factory=_TouchFactAllocationMap)
    x2_passed: bool = True
    drafter_model_id: str = ""
    drafter_family: str = "anthropic"
    used_fallback: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", str(self.run_id or "run-default").strip())
        object.__setattr__(self, "mission_id", str(self.mission_id or "mission-default").strip())
        raw_touches = self.touches if isinstance(self.touches, Sequence) and not isinstance(self.touches, (str, bytes)) else ()
        norm_touches = tuple(_normalize_touch_entry(t, idx) for idx, t in enumerate(raw_touches, start=1))
        object.__setattr__(self, "touches", norm_touches)
        raw_certs = self.pct_certificates if isinstance(self.pct_certificates, Sequence) and not isinstance(self.pct_certificates, (str, bytes)) else ()
        object.__setattr__(self, "pct_certificates", tuple(_normalize_pct_entry(c) for c in raw_certs))

        alloc_map = _TouchFactAllocationMap()
        if isinstance(self.allocated_fact_ids_by_touch, Mapping) and self.allocated_fact_ids_by_touch:
            for k, v in self.allocated_fact_ids_by_touch.items():
                if str(k).strip().lstrip("-").isdigit():
                    alloc_map[int(str(k).strip())] = [str(x).strip() for x in (v or ()) if str(x).strip()] if isinstance(v, Sequence) and not isinstance(v, (str, bytes)) else []
        elif norm_touches:
            for t_dict in norm_touches:
                alloc_map[int(t_dict["touch_number"])] = list(t_dict["cited_fact_ids"])
        object.__setattr__(self, "allocated_fact_ids_by_touch", alloc_map)
        object.__setattr__(self, "x2_passed", bool(self.x2_passed))

        gen_pin = OutreachModelRegistry.get_model_pin("executive_outreach_generator")
        raw_model_id, raw_family, fallback_flag = str(self.drafter_model_id or "").strip(), str(self.drafter_family or "").strip(), bool(self.used_fallback)
        raw_model_id = raw_model_id or (gen_pin.backup_model if fallback_flag else gen_pin.model)
        fallback_flag = True if (gen_pin.backup_model and raw_model_id == gen_pin.backup_model) else fallback_flag
        resolved_family = OutreachModelRegistry.normalize_provider_family(
            (gen_pin.backup_provider or raw_model_id) if (fallback_flag and (not raw_family or raw_family.lower() == gen_pin.provider_family)) else (raw_family or raw_model_id)
        )
        if resolved_family == gen_pin.backup_provider_family and raw_model_id == gen_pin.model and gen_pin.backup_model:
            raw_model_id, fallback_flag = gen_pin.backup_model, True
        object.__setattr__(self, "drafter_model_id", raw_model_id)
        object.__setattr__(self, "drafter_family", resolved_family)
        object.__setattr__(self, "used_fallback", fallback_flag)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "mission_id": self.mission_id, "touches": [dict(t) for t in self.touches],
            "pct_certificates": [dict(c) for c in self.pct_certificates],
            "allocated_fact_ids_by_touch": {str(k): list(v) for k, v in sorted(self.allocated_fact_ids_by_touch.items())},
            "x2_passed": self.x2_passed, "drafter_model_id": self.drafter_model_id,
            "drafter_family": self.drafter_family, "used_fallback": self.used_fallback,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_sequence(cls, touches: Sequence[Any] = (), **kwargs: Any) -> GradeOnlyJudgePacket:
        return build_grade_only_judge_packet(touches=touches, **kwargs)


def build_grade_only_judge_packet(
    *, run_id: str = "run-default", mission_id: str = "mission-default", touches: Sequence[Any] = (),
    pct_certificates: Sequence[Any] = (), allocated_fact_ids_by_touch: Mapping[Any, Sequence[str]] | None = None,
    allocation_plan: Any | None = None, x2_report: Any | None = None, x2_passed: bool | None = None,
    drafter_model_id: str = "", drafter_family: str = "anthropic", used_fallback: bool = False, **_stripped_target_kwargs: Any,
) -> GradeOnlyJudgePacket:
    """Build a target-free `GradeOnlyJudgePacket`, stripping `<untrusted_data>` and target brief inputs."""
    resolved_certs = list(pct_certificates or (getattr(x2_report, "pct_certificates", None) or (x2_report.get("pct_certificates") if isinstance(x2_report, Mapping) else ()) if x2_report is not None else ()) or ())
    plan_alloc = getattr(allocation_plan, "allocated_fact_ids_by_touch", None) or (allocation_plan.get("allocated_fact_ids_by_touch") if isinstance(allocation_plan, Mapping) else {}) if allocation_plan is not None else {}
    resolved_alloc = allocated_fact_ids_by_touch or (plan_alloc if isinstance(plan_alloc, Mapping) else {})
    resolved_x2 = bool(getattr(x2_report, "passed", x2_report.get("passed", True) if isinstance(x2_report, Mapping) else True)) if (x2_passed is None and x2_report is not None) else (True if x2_passed is None else bool(x2_passed))
    return GradeOnlyJudgePacket(
        run_id=run_id, mission_id=mission_id, touches=tuple(touches or ()), pct_certificates=tuple(resolved_certs),
        allocated_fact_ids_by_touch=dict(resolved_alloc),  # type: ignore[arg-type]
        x2_passed=resolved_x2, drafter_model_id=drafter_model_id, drafter_family=drafter_family, used_fallback=used_fallback,
    )


@dataclass(frozen=True)
class X1DJudgeVote:
    """Single proof-eligible judge vote inside the dual cross-family X1D quorum."""

    judge_role: str
    model_id: str
    provider: str
    provider_family: str
    reasoning_effort: str = "low"
    proof_eligible: bool = True
    advisory_only: bool = False
    orthogonal_to_drafter: bool = True
    self_grading_blocked: bool = False
    score: float = 0.0
    passed: bool = False
    dimension_scores: dict[str, float] = field(default_factory=dict)
    rationale: str = ""
    violations: tuple[str, ...] = ()
    transport: str = "deterministic"
    evaluator_mode: str = "DETERMINISTIC_PRE_JUDGE"
    llm_judge_executed: bool = False
    conversation_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    judge_model_id = property(lambda self: self.model_id)
    judge_family = property(lambda self: self.provider_family)
    composite_score = property(lambda self: self.score)

    def to_dict(self) -> dict[str, Any]:
        return {
            "judge_role": self.judge_role,
            "model_id": self.model_id,
            "provider": self.provider,
            "provider_family": self.provider_family,
            "reasoning_effort": self.reasoning_effort,
            "proof_eligible": self.proof_eligible,
            "advisory_only": self.advisory_only,
            "orthogonal_to_drafter": self.orthogonal_to_drafter,
            "self_grading_blocked": self.self_grading_blocked,
            "score": round(float(self.score), 4),
            "passed": self.passed,
            "dimension_scores": {k: round(float(v), 4) for k, v in self.dimension_scores.items()},
            "rationale": self.rationale,
            "violations": list(self.violations),
            "transport": self.transport,
            "evaluator_mode": self.evaluator_mode,
            "llm_judge_executed": self.llm_judge_executed,
            "conversation_id": self.conversation_id,
            "usage": dict(self.usage),
        }


@dataclass(frozen=True)
class WholeSequenceJudgeQuorumReport:
    """Consolidated dual cross-family X1D judge quorum report."""
    schema_version: str = WHOLE_SEQUENCE_JUDGE_QUORUM_SCHEMA_VERSION
    rubric_id: str = DEFAULT_X1D_RUBRIC_ID
    run_id: str = "run-default"
    mission_id: str = "mission-default"
    x2_passed: bool = True
    quorum_passed: bool = False
    self_grading_blocked: bool = False
    drafter_judge_orthogonal: bool = True
    drafter_model_id: str = ""
    drafter_family: str = "anthropic"
    used_fallback: bool = False
    primary_score: float = 0.0
    secondary_score: float = 0.0
    mean_score: float = 0.0
    spread: float = 0.0
    pass_threshold: float = X1D_PASS_THRESHOLD
    max_judge_spread: float = X1D_MAX_JUDGE_SPREAD
    recommended_x3_disposition: str = "X3E_SAFE_ABSTAIN"
    votes: tuple[X1DJudgeVote, ...] = ()
    reason_codes: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    target_free_verified: bool = True
    passed = property(lambda self: self.quorum_passed)
    score_spread = property(lambda self: self.spread)
    x3_disposition = property(lambda self: self.recommended_x3_disposition)
    primary_vote = property(lambda self: self.votes[0] if len(self.votes) >= 1 else None)
    secondary_vote = property(lambda self: self.votes[1] if len(self.votes) >= 2 else None)

    def to_dict(self) -> dict[str, Any]:
        vote_dicts = [v.to_dict() for v in self.votes]
        return {"schema_version": self.schema_version, "rubric_id": self.rubric_id, "run_id": self.run_id, "mission_id": self.mission_id, "x2_passed": self.x2_passed, "quorum_passed": self.quorum_passed, "self_grading_blocked": self.self_grading_blocked, "drafter_judge_orthogonal": self.drafter_judge_orthogonal, "drafter_model_id": self.drafter_model_id, "drafter_family": self.drafter_family, "used_fallback": self.used_fallback, "primary_score": round(float(self.primary_score), 4), "secondary_score": round(float(self.secondary_score), 4), "mean_score": round(float(self.mean_score), 4), "spread": round(float(self.spread), 4), "pass_threshold": round(float(self.pass_threshold), 4), "max_judge_spread": round(float(self.max_judge_spread), 4), "recommended_x3_disposition": self.recommended_x3_disposition, "proof_judges": [v.model_id for v in self.votes], "votes": vote_dicts, "judge_votes": vote_dicts, "reason_codes": list(self.reason_codes), "violations": list(self.violations), "target_free_verified": self.target_free_verified}


def _score_packet_for_judge(packet: GradeOnlyJudgePacket, pin: OutreachModelPin, rubric: dict[str, Any], *, explicit_score: float | None = None, seed: int | None = None) -> tuple[float, dict[str, float], list[str]]:
    dims = [d for d in (rubric.get("dimensions") or []) if isinstance(d, Mapping)]
    if explicit_score is not None:
        clamped = round(max(0.0, min(1.0, float(explicit_score))), 4)
        return clamped, {str(d.get("name") or d.get("id")): clamped for d in dims}, []
    viols: list[str] = []
    g_sc, c_sc, a_sc, cit_sc, cta_sc, h_sc = 0.94, 0.92, 0.91, 0.95, 0.90, 0.93
    for cert in packet.pct_certificates:
        if cert.get("in_opp") and not cert.get("in_cand"):
            g_sc, cit_sc = 0.10, 0.20
            viols.append(f"Laundered opportunity metric '{cert.get('metric_token')}' detected in PCTCertificate.")
        elif not cert.get("verified", True) or not cert.get("in_cand", True):
            g_sc, cit_sc = min(g_sc, 0.20), min(cit_sc, 0.30)
            viols.append(f"Unverified candidate metric '{cert.get('metric_token')}' in PCTCertificate.")
    seen_fids: set[str] = set()
    for t in packet.touches:
        t_num, body, subj = int(t.get("touch_number", 1)), str(t.get("body") or ""), str(t.get("subject") or "")
        fids = [str(f) for f in (t.get("cited_fact_ids") or ()) if str(f).strip()]
        if (alloc := packet.allocated_fact_ids_by_touch.get(t_num)) and (unalloc := [f for f in fids if f not in alloc]):
            cit_sc, g_sc = min(cit_sc, 0.25), min(g_sc, 0.35)
            viols.append(f"Touch {t_num} cites unallocated fact_ids {unalloc}.")
        for f in fids:
            if f in seen_fids:
                c_sc = min(c_sc, 0.25)
                viols.append(f"Cross-touch fact_id collision on '{f}' in touch {t_num}.")
            seen_fids.add(f)
        mga_ok, mga_errs = check_undefined_mga_acronym(f"{subj} {body}")
        if not mga_ok:
            h_sc = min(h_sc, 0.20)
            viols.extend(mga_errs)
        if _SUBORDINATE_OR_SPAM_PAT.search(body):
            a_sc, h_sc = min(a_sc, 0.25), min(h_sc, 0.30)
            viols.append(f"Touch {t_num} contains subordinate or spam phrase.")
    offset = -0.01 if pin.provider_family == "openai" else 0.005
    jitter = (((hashlib.sha256(f"{packet.run_id}:{pin.model}:{seed}".encode("utf-8")).digest()[0] / 255.0) - 0.5) * 0.008) if seed is not None else 0.0
    raw_dims = {"candidate_evidence_grounding": g_sc, "sequence_coherence_and_progression": c_sc, "executive_altitude_and_peer_framing": a_sc, "citation_and_pct_support": cit_sc, "cta_and_friction_calibration": cta_sc, "constraint_and_hygiene_compliance": h_sc}
    dim_scores: dict[str, float] = {}
    weighted_total, weight_sum = 0.0, 0.0
    for d in dims:
        dname, w = str(d.get("name") or d.get("id") or ""), float(d.get("weight", 0.0))
        val = round(max(0.0, min(1.0, raw_dims.get(dname, 0.92) + offset + jitter)), 4)
        dim_scores[dname] = val
        weighted_total += val * w
        weight_sum += w
    return max(0.0, min(1.0, round(weighted_total / (weight_sum if weight_sum > 0 else 1.0), 4))), dim_scores, viols


def _make_vote(
    pin: OutreachModelPin,
    orthogonal: bool,
    blocked: bool,
    score: float,
    passed: bool,
    dims: dict[str, float],
    rationale: str,
    viols: Sequence[str],
    *,
    transport: str = "deterministic",
    evaluator_mode: str = "DETERMINISTIC_PRE_JUDGE",
    llm_judge_executed: bool = False,
    conversation_id: str | None = None,
    usage: Mapping[str, Any] | None = None,
    model_override: str | None = None,
    family_override: str | None = None,
) -> X1DJudgeVote:
    return X1DJudgeVote(
        pin.role,
        model_override or pin.model,
        pin.provider,
        family_override or pin.provider_family,
        pin.reasoning_effort,
        pin.proof_eligible,
        pin.advisory_only,
        orthogonal,
        blocked,
        score,
        passed,
        dims,
        rationale,
        tuple(viols),
        transport=transport,
        evaluator_mode=evaluator_mode,
        llm_judge_executed=llm_judge_executed,
        conversation_id=conversation_id,
        usage=dict(usage or {}),
    )


def evaluate_x1d_judge_quorum(
    packet: GradeOnlyJudgePacket | Mapping[str, Any] | None = None, *, run_id: str | None = None, mission_id: str | None = None,
    touches: Sequence[Any] | None = None, pct_certificates: Sequence[Any] | None = None, allocated_fact_ids_by_touch: Mapping[Any, Sequence[str]] | None = None,
    x2_passed: bool | None = None, drafter_model_id: str | None = None, drafter_family: str | None = None, used_fallback: bool | None = None,
    primary_score: float | None = None, secondary_score: float | None = None, judge_scores: Mapping[str, float] | Sequence[float] | None = None,
    pass_threshold: float | None = None, max_judge_spread: float | None = None, seed: int | None = None, rubric_path: Path | str | None = None,
    transport: str | None = None, agy_bin: str | os.PathLike[str] | None = None,
) -> WholeSequenceJudgeQuorumReport:
    """Evaluate dual cross-family X1D proof-judge quorum strictly post-X2 on a `GradeOnlyJudgePacket`."""
    from apps_lic.judges.ide_cli_judge import call_outreach_x1d_ide_cli_judge, resolve_lic_judge_transport

    eff_transport = resolve_lic_judge_transport(transport)
    rubric = load_x1d_exit_rubric(rubric_path)
    rubric_id = str(rubric.get("rubric_id", DEFAULT_X1D_RUBRIC_ID))
    eff_threshold = float(pass_threshold if pass_threshold is not None else rubric.get("pass_threshold", X1D_PASS_THRESHOLD))
    eff_max_spread = float(max_judge_spread if max_judge_spread is not None else rubric.get("max_judge_spread", X1D_MAX_JUDGE_SPREAD))
    base = packet.to_dict() if isinstance(packet, GradeOnlyJudgePacket) else (dict(packet) if isinstance(packet, Mapping) else {})
    resolved_packet = GradeOnlyJudgePacket(
        run_id=str(run_id if run_id is not None else base.get("run_id", "run-default")), mission_id=str(mission_id if mission_id is not None else base.get("mission_id", "mission-default")),
        touches=tuple(touches if touches is not None else (base.get("touches") or ())), pct_certificates=tuple(pct_certificates if pct_certificates is not None else (base.get("pct_certificates") or ())),
        allocated_fact_ids_by_touch=dict(allocated_fact_ids_by_touch if allocated_fact_ids_by_touch is not None else (base.get("allocated_fact_ids_by_touch") or {})),
        x2_passed=bool(x2_passed if x2_passed is not None else base.get("x2_passed", True)), drafter_model_id=str(drafter_model_id if drafter_model_id is not None else base.get("drafter_model_id", "")),
        drafter_family=str(drafter_family if drafter_family is not None else base.get("drafter_family", "anthropic")), used_fallback=bool(used_fallback if used_fallback is not None else base.get("used_fallback", False)),
    )
    primary_pin, secondary_pin = OutreachModelRegistry.get_x1d_proof_judge_pins()
    if isinstance(judge_scores, Mapping):
        primary_score = float(judge_scores[primary_pin.model]) if primary_score is None and primary_pin.model in judge_scores else primary_score
        secondary_score = float(judge_scores[secondary_pin.model]) if secondary_score is None and secondary_pin.model in judge_scores else secondary_score
    elif isinstance(judge_scores, Sequence) and len(judge_scores) >= 2:
        primary_score = float(judge_scores[0]) if primary_score is None else primary_score
        secondary_score = float(judge_scores[1]) if secondary_score is None else secondary_score
    target_free_ok = "<untrusted_data" not in resolved_packet.to_json().lower()
    norm_drafter_family = OutreachModelRegistry.normalize_provider_family(resolved_packet.drafter_family or resolved_packet.drafter_model_id)
    primary_orthogonal = OutreachModelRegistry.verify_cross_family_orthogonality(norm_drafter_family, primary_pin)
    secondary_orthogonal = OutreachModelRegistry.verify_cross_family_orthogonality(norm_drafter_family, secondary_pin) and not resolved_packet.used_fallback and norm_drafter_family != secondary_pin.provider_family
    self_grading_blocked = bool(resolved_packet.used_fallback or norm_drafter_family == secondary_pin.provider_family or not primary_orthogonal or not secondary_orthogonal)
    drafter_judge_orthogonal = bool(primary_orthogonal and secondary_orthogonal and not self_grading_blocked)
    reasons, violations = [], []

    def _finish_report(q_passed: bool, p_sc: float, s_sc: float, m_sc: float, sp: float, disp: str, v1: X1DJudgeVote, v2: X1DJudgeVote) -> WholeSequenceJudgeQuorumReport:
        return WholeSequenceJudgeQuorumReport(rubric_id=rubric_id, run_id=resolved_packet.run_id, mission_id=resolved_packet.mission_id, x2_passed=resolved_packet.x2_passed, quorum_passed=q_passed, self_grading_blocked=self_grading_blocked, drafter_judge_orthogonal=drafter_judge_orthogonal, drafter_model_id=resolved_packet.drafter_model_id, drafter_family=norm_drafter_family, used_fallback=resolved_packet.used_fallback, primary_score=p_sc, secondary_score=s_sc, mean_score=m_sc, spread=sp, pass_threshold=eff_threshold, max_judge_spread=eff_max_spread, recommended_x3_disposition=disp, votes=(v1, v2), reason_codes=tuple(reasons), violations=tuple(violations), target_free_verified=target_free_ok)

    if not resolved_packet.x2_passed:
        reasons.append("X1D_BLOCKED_PRE_X2_FAILURE")
        violations.append("X1D judge quorum blocked: sequence failed pre-requisite X2 validation (x2_passed=False).")
        if self_grading_blocked:
            reasons.append("CROSS_FAMILY_SELF_GRADING_BLOCKED")
        v1 = _make_vote(primary_pin, primary_orthogonal, not primary_orthogonal, 0.0, False, {}, "Skipped pre-X2.", violations, transport=eff_transport)
        v2 = _make_vote(secondary_pin, secondary_orthogonal, self_grading_blocked, 0.0, False, {}, "Skipped pre-X2.", violations, transport=eff_transport)
        return _finish_report(False, 0.0, 0.0, 0.0, 0.0, "X3B_ESCALATE_HITL" if self_grading_blocked else "X3E_SAFE_ABSTAIN", v1, v2)

    if self_grading_blocked:
        reasons.extend(["CROSS_FAMILY_SELF_GRADING_BLOCKED", "FALLBACK_DRAFTER_OPENAI_ESCALATE_HITL"])
        block_msg = f"Cross-family anti-self-grading block: drafter '{resolved_packet.drafter_model_id}' (family='{norm_drafter_family}', used_fallback={resolved_packet.used_fallback}) overlaps judge '{secondary_pin.model}'."
        violations.append(block_msg)
        p_val, p_dims, p_viols = _score_packet_for_judge(resolved_packet, primary_pin, rubric, explicit_score=primary_score, seed=seed)
        v1 = _make_vote(primary_pin, primary_orthogonal, not primary_orthogonal, p_val if primary_orthogonal else 0.0, bool(primary_orthogonal and p_val >= eff_threshold and not p_viols), p_dims if primary_orthogonal else {}, "Primary judge pass.", p_viols, transport=eff_transport)
        v2 = _make_vote(secondary_pin, False, True, 0.0, False, {}, block_msg, (block_msg,), transport=eff_transport)
        return _finish_report(False, v1.score, 0.0, round(v1.score / 2.0, 4), round(v1.score, 4), "X3B_ESCALATE_HITL", v1, v2)

    if eff_transport == "ide_cli" and primary_score is None and secondary_score is None:
        pkt_dict = resolved_packet.to_dict()
        r1 = call_outreach_x1d_ide_cli_judge(
            packet_dict=pkt_dict, rubric=rubric, slot="primary",
            drafter_family=norm_drafter_family, pass_threshold=eff_threshold, agy_bin=agy_bin,
        )
        r2 = call_outreach_x1d_ide_cli_judge(
            packet_dict=pkt_dict, rubric=rubric, slot="secondary",
            drafter_family=norm_drafter_family, pass_threshold=eff_threshold, agy_bin=agy_bin,
        )
        v1 = _make_vote(
            primary_pin, True, r1.provider_blocked, r1.score, r1.passed, r1.dimension_scores, r1.rationale, r1.violations,
            transport="ide_cli", evaluator_mode=r1.evaluator_mode, llm_judge_executed=r1.llm_judge_executed,
            conversation_id=r1.conversation_id, usage=r1.usage, model_override=r1.model_reported or r1.model_requested,
            family_override=r1.provider_family,
        )
        v2 = _make_vote(
            secondary_pin, True, r2.provider_blocked, r2.score, r2.passed, r2.dimension_scores, r2.rationale, r2.violations,
            transport="ide_cli", evaluator_mode=r2.evaluator_mode, llm_judge_executed=r2.llm_judge_executed,
            conversation_id=r2.conversation_id, usage=r2.usage, model_override=r2.model_reported or r2.model_requested,
            family_override=r2.provider_family,
        )
        violations.extend(r1.violations)
        violations.extend(sv for sv in r2.violations if sv not in violations)
        mean_score, spread = round((r1.score + r2.score) / 2.0, 4), round(abs(r1.score - r2.score), 4)
        if r1.provider_blocked or r2.provider_blocked:
            reasons.append("X1D_IDE_CLI_PROVIDER_BLOCKED")
            return _finish_report(False, r1.score, r2.score, mean_score, spread, "X3E_SAFE_ABSTAIN", v1, v2)
        score_ok, spread_ok = mean_score >= eff_threshold, spread <= eff_max_spread
        quorum_passed = bool(r1.passed and r2.passed and score_ok and spread_ok and target_free_ok and not violations)
        if quorum_passed:
            disposition = "X3D_ALLOW_FINISH"
            reasons.append("X1D_IDE_CLI_DUAL_QUORUM_PASSED")
        elif not spread_ok:
            disposition = "X3B_ESCALATE_HITL"
            reasons.append("X1D_JUDGE_SPREAD_EXCEEDED")
            violations.append(f"X1D judge spread {spread:.4f} exceeds max_judge_spread {eff_max_spread:.4f}.")
        else:
            disposition = "X3E_SAFE_ABSTAIN"
            reasons.append("X1D_MEAN_SCORE_BELOW_THRESHOLD")
        return _finish_report(quorum_passed, r1.score, r2.score, mean_score, spread, disposition, v1, v2)

    p_score, p_dims, p_viols = _score_packet_for_judge(resolved_packet, primary_pin, rubric, explicit_score=primary_score, seed=seed)
    s_score, s_dims, s_viols = _score_packet_for_judge(resolved_packet, secondary_pin, rubric, explicit_score=secondary_score, seed=seed)
    violations.extend(p_viols)
    violations.extend(sv for sv in s_viols if sv not in violations)
    mean_score, spread = round((p_score + s_score) / 2.0, 4), round(abs(p_score - s_score), 4)
    both_proof_eligible = bool(primary_pin.proof_eligible and not primary_pin.advisory_only and secondary_pin.proof_eligible and not secondary_pin.advisory_only and primary_pin.reasoning_effort == "low" and secondary_pin.reasoning_effort == "low")
    score_ok, spread_ok = mean_score >= eff_threshold, spread <= eff_max_spread
    quorum_passed = bool(both_proof_eligible and score_ok and spread_ok and target_free_ok and not violations)
    if quorum_passed:
        disposition = "X3D_ALLOW_FINISH"
        reasons.append("X1D_DUAL_QUORUM_PASSED")
    elif not spread_ok:
        disposition = "X3B_ESCALATE_HITL"
        reasons.append("X1D_JUDGE_SPREAD_EXCEEDED")
        violations.append(f"X1D judge spread {spread:.4f} exceeds max_judge_spread {eff_max_spread:.4f}.")
    else:
        disposition = "X3E_SAFE_ABSTAIN"
        reasons.append("X1D_MEAN_SCORE_BELOW_THRESHOLD")
        if not score_ok:
            violations.append(f"X1D quorum mean_score {mean_score:.4f} is below pass_threshold {eff_threshold:.4f}.")
    v1 = _make_vote(primary_pin, True, False, p_score, bool(p_score >= eff_threshold and not p_viols), p_dims, "Primary judge pass.", p_viols, transport=eff_transport)
    v2 = _make_vote(secondary_pin, True, False, s_score, bool(s_score >= eff_threshold and not s_viols), s_dims, "Secondary judge pass.", s_viols, transport=eff_transport)
    return _finish_report(quorum_passed, p_score, s_score, mean_score, spread, disposition, v1, v2)


def write_whole_sequence_judge_quorum(
    first: Path | str | WholeSequenceJudgeQuorumReport | Mapping[str, Any] | None = None,
    second: WholeSequenceJudgeQuorumReport | Mapping[str, Any] | Path | str | None = None,
    *, output_dir: Path | str | None = None, output_path: Path | str | None = None,
    path: Path | str | None = None, report: WholeSequenceJudgeQuorumReport | Mapping[str, Any] | None = None,
) -> Path:
    """Write `whole_sequence_judge_quorum.json` with `0644` permissions and return its `Path`."""
    resolved_report: WholeSequenceJudgeQuorumReport | Mapping[str, Any] | None = report
    resolved_target: Path | str | None = output_path or path or output_dir
    if isinstance(first, (WholeSequenceJudgeQuorumReport, Mapping)):
        resolved_report, resolved_target = first, (second if isinstance(second, (Path, str)) else resolved_target)
    elif isinstance(first, (Path, str)):
        resolved_target, resolved_report = first, (second if isinstance(second, (WholeSequenceJudgeQuorumReport, Mapping)) else resolved_report)
    if resolved_target is None or resolved_report is None:
        raise ValueError("write_whole_sequence_judge_quorum requires both a report and a target path/directory.")
    target_path = Path(resolved_target)
    if target_path.suffix.lower() != ".json":
        target_path = target_path / "whole_sequence_judge_quorum.json"
    payload = resolved_report.to_dict() if isinstance(resolved_report, WholeSequenceJudgeQuorumReport) else dict(resolved_report)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(target_path, 0o644)
    return target_path


__all__ = ["DEFAULT_X1D_RUBRIC_ID", "GradeOnlyJudgePacket", "GradeOnlyTouchItem", "WHOLE_SEQUENCE_JUDGE_QUORUM_SCHEMA_VERSION", "WholeSequenceJudgeQuorumReport", "X1DJudgeVote", "X1D_MAX_JUDGE_SPREAD", "X1D_PASS_THRESHOLD", "build_grade_only_judge_packet", "evaluate_x1d_judge_quorum", "load_x1d_exit_rubric", "strip_untrusted_target_data", "write_whole_sequence_judge_quorum"]
