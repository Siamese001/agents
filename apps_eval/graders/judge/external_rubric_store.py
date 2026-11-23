"""External Rubric Contract and Tamper-Evident Human Gold Store for IDE LLM-as-a-Judges (DIE Parity).

Provides:
1. Canonical SHA-256 verification of the frozen vendor-neutral external rubric
   (`config/governance/external_judge_rubric_v1.json`).
2. `ExternalHumanLabelRecord`: typed, content-hash-bound human evaluation grade
   across 4 external 1-to-5 behavioral pillars (`F`, `C`, `R`, `A`) plus binary
   `PASS` / `FAIL`, 6 atomic binary checks, and 6 failure-taxonomy tags.
3. `ExternalRubricHumanStore`: atomic JSON store enforcing topic-disjoint `dev`,
   `calibration`, and `final_holdout` partitions and rejecting synthetic/mock
   annotators fail-closed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.graders.judge.frontier_rubric_contract import (
    QuarantineDisposition,
    enforce_pass_rule_and_critique,
    validate_atomic_checks,
    validate_failure_tags,
)

DEFAULT_EXTERNAL_RUBRIC_REL_PATH = Path("config/governance/external_judge_rubric_v1.json")
DEFAULT_HUMAN_GOLD_STORE_REL_PATH = Path("data/judge_calibration/ide_judge_external_human_labels_v1.json")

EXTERNAL_RUBRIC_DIMENSIONS: tuple[str, ...] = (
    "factual_faithfulness",
    "completeness_and_relevance",
    "cold_reader_clarity",
    "actionability_and_proportion",
)

VALID_PARTITIONS: frozenset[str] = frozenset({"dev", "calibration", "final_holdout"})
VALID_HUMAN_VERDICTS: frozenset[str] = frozenset({"PASS", "FAIL"})
VALID_JUDGE_SURFACES: frozenset[str] = frozenset(
    {
        # Engine-level & prefixed surfaces
        "resume_engine",
        "outreach_engine",
        "combined_resume_and_outreach",
        "resume_engine:headline",
        "resume_engine:executive_summary",
        "resume_engine:competencies",
        "resume_engine:employment_bullets",
        "resume_engine:role_narrative",
        "resume_engine:whole_resume_coherence",
        "outreach_engine:x1d_quorum",
        "outreach_engine:executive_judge_panel",
        # Resume Engine judge surfaces
        "resume_headline",
        "resume_executive_summary",
        "resume_competencies",
        "resume_employment_bullets",
        "resume_role_narrative",
        "resume_whole_coherence",
        "headline",
        "executive_summary",
        "competencies",
        "employment_bullets",
        "role_narrative",
        "whole_resume_coherence",
        # Outreach Engine judge surfaces
        "outreach_x1d_quorum",
        "outreach_executive_panel",
        "x1d_quorum",
        "executive_judge_panel",
        # DIE cross-workspace surfaces
        "query_synthesis",
        "stage_01_forensic",
        "stage_02_recap",
        "stage_03_graph",
        "live_copilot",
        "answer_ledger_batch",
        "explorer_visual_ui",
        "portfolio_dossier",
    }
)

FORBIDDEN_ANNOTATOR_TOKENS: tuple[str, ...] = (
    "mock",
    "synthetic",
    "auto",
    "bot",
    "stub",
    "fake",
    "dummy",
    "llm",
    "subagent",
    "argon",
    "neon",
    "carbon",
    "gpt",
    "claude",
    "gemini",
    "placeholder",
    "system",
    "unknown",
    "anonymous",
)

FORBIDDEN_INTERNAL_RULE_LEAK_TOKENS: tuple[str, ...] = (
    "BLIND_JUDGE_DIM_BELOW_FLOOR",
    "UNNATURAL_DATE_OR_OVERENGINEERING_VOICE",
    "LINEAGE_FOOTER_SOURCE_MISATTRIBUTION",
    "JudgeRubricRegistry",
    "RAW_TRANSCRIPT_SYNTHESIS_PROMPT",
    "x2_executive_summary_structural_count",
    "x2_first_person_zero",
)


def compute_payload_sha256(text_or_bytes: str | bytes) -> str:
    """Compute canonical UTF-8 SHA-256 hex digest over candidate text or bytes."""
    raw = text_or_bytes.encode("utf-8") if isinstance(text_or_bytes, str) else bytes(text_or_bytes)
    return hashlib.sha256(raw).hexdigest()


def compute_external_rubric_sha256(rubric_payload: Mapping[str, Any]) -> str:
    """Compute canonical SHA-256 over external rubric JSON excluding `rubric_sha256`."""
    clean = {k: v for k, v in rubric_payload.items() if k != "rubric_sha256"}
    encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_dimension_anchors(dim_key: str, spec: Any) -> None:
    if not isinstance(spec, Mapping):
        raise ValueError(f"External rubric dimension '{dim_key}' must be an object.")
    anchors = spec.get("anchors")
    if not isinstance(anchors, Mapping):
        raise ValueError(f"External rubric dimension '{dim_key}' missing 'anchors' map.")
    for score_str in ("1", "2", "3", "4", "5"):
        desc = str(anchors.get(score_str) or "").strip()
        if len(desc) < 15:
            raise ValueError(f"External rubric dimension '{dim_key}' anchor '{score_str}' must be >= 15 chars.")


def load_and_verify_external_rubric(rubric_path: Path | None = None) -> dict[str, Any]:
    """Load and verify `external_judge_rubric_v1.json` integrity and independence fail-closed."""
    repo_root = Path(__file__).resolve().parents[3]
    target = Path(rubric_path) if rubric_path is not None else (repo_root / DEFAULT_EXTERNAL_RUBRIC_REL_PATH)
    if not target.is_file():
        raise FileNotFoundError(f"External judge rubric missing at '{target}'.")
    raw_text = target.read_text(encoding="utf-8")
    for leak_tok in FORBIDDEN_INTERNAL_RULE_LEAK_TOKENS:
        if leak_tok in raw_text:
            raise ValueError(f"External rubric contaminated with internal repo rule token '{leak_tok}'.")
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("External judge rubric must decode to a JSON object.")
    if str(payload.get("rubric_id") or "") != "external_judge_rubric_v1":
        raise ValueError(f"Unexpected external rubric_id: {payload.get('rubric_id')!r}.")
    dims = payload.get("dimensions")
    if not isinstance(dims, Mapping) or tuple(dims.keys()) != EXTERNAL_RUBRIC_DIMENSIONS:
        raise ValueError(f"External rubric dimensions must match {EXTERNAL_RUBRIC_DIMENSIONS}.")
    for dim_key in EXTERNAL_RUBRIC_DIMENSIONS:
        _validate_dimension_anchors(dim_key, dims[dim_key])
    expected_sha = compute_external_rubric_sha256(payload)
    observed_sha = str(payload.get("rubric_sha256") or "").strip()
    if not observed_sha or observed_sha != expected_sha:
        raise ValueError(
            f"External rubric SHA-256 mismatch: expected {expected_sha}, observed {observed_sha or 'EMPTY'}."
        )
    return payload


def validate_human_annotator_id(annotator_id: str) -> str:
    """Ensure annotator_id represents an authenticated human rater rather than a mock or LLM."""
    clean = str(annotator_id or "").strip()
    if len(clean) < 3 or len(clean) > 80:
        raise ValueError("Human annotator_id must be between 3 and 80 characters.")
    lowered = clean.lower()
    for bad in FORBIDDEN_ANNOTATOR_TOKENS:
        if bad in lowered:
            raise ValueError(f"Synthetic or automated annotator token '{bad}' is forbidden in human gold labels.")
    if not any(ch.isalpha() for ch in clean):
        raise ValueError("Human annotator_id must contain alphabetic characters.")
    return clean


def _validate_dimension_grades(grades: Mapping[str, Any]) -> dict[str, int]:
    if not isinstance(grades, Mapping):
        raise ValueError("dimension_grades must be a mapping of the 4 external pillars.")
    if set(grades.keys()) != set(EXTERNAL_RUBRIC_DIMENSIONS):
        raise ValueError(f"dimension_grades keys must exactly equal {EXTERNAL_RUBRIC_DIMENSIONS}.")
    out: dict[str, int] = {}
    for key in EXTERNAL_RUBRIC_DIMENSIONS:
        val = grades[key]
        if isinstance(val, bool) or not isinstance(val, int) or val < 1 or val > 5:
            raise ValueError(f"Dimension '{key}' grade must be an integer in 1..5, got {val!r}.")
        out[key] = val
    return out


def _validate_sha256_hex(digest_str: str, field_name: str) -> str:
    clean = str(digest_str or "").strip().lower()
    if len(clean) != 64 or any(ch not in "0123456789abcdef" for ch in clean):
        raise ValueError(f"Field '{field_name}' must be a 64-char lowercase hex SHA-256 digest.")
    return clean


def _require_non_empty_field(raw: Mapping[str, Any], key: str, min_len: int = 1) -> str:
    val = str(raw.get(key) or "").strip()
    if len(val) < min_len:
        raise ValueError(f"{key} must be at least {min_len} character(s).")
    return val


def _validate_membership(val: str, allowed: frozenset[str], label: str) -> str:
    if val not in allowed:
        raise ValueError(f"Invalid {label} {val!r}; expected one of {sorted(allowed)}.")
    return val


def _validate_record_digests(
    raw: Mapping[str, Any],
    case_id: str,
    expected_rubric_sha256: str | None,
    candidate_text: str | bytes | None,
) -> tuple[str, str, str]:
    art_sha = _validate_sha256_hex(str(raw.get("artifact_sha256") or ""), "artifact_sha256")
    if candidate_text is not None and compute_payload_sha256(candidate_text) != art_sha:
        raise ValueError(f"Candidate payload SHA-256 mismatch for case '{case_id}'.")
    rub_id = str(raw.get("external_rubric_id") or "").strip()
    if rub_id != "external_judge_rubric_v1":
        raise ValueError(f"Unsupported external_rubric_id {rub_id!r}.")
    rub_sha = _validate_sha256_hex(str(raw.get("external_rubric_sha256") or ""), "external_rubric_sha256")
    if expected_rubric_sha256 and rub_sha != expected_rubric_sha256:
        raise ValueError(
            f"Record '{case_id}' external_rubric_sha256 {rub_sha} != active rubric {expected_rubric_sha256}."
        )
    return art_sha, rub_id, rub_sha


@dataclass(frozen=True)
class ExternalHumanLabelRecord:
    """Immutable human-graded label bound to an artifact digest and external rubric digest."""

    case_id: str
    judge_surface: str
    topic_family: str
    partition: str
    artifact_sha256: str
    external_rubric_id: str
    external_rubric_sha256: str
    dimension_grades: dict[str, int]
    human_verdict: str
    annotator_id: str
    graded_at_utc: str
    notes: str = ""
    atomic_checks: dict[str, bool] = field(default_factory=dict)
    failure_tags: tuple[str, ...] = ()
    critique_rationale: str = ""
    evidence_context_sha256: str = ""

    def normalized_human_score(self) -> float:
        """Map weighted 1..5 ordinal grade onto [0.0, 1.0] (weights: F=0.35, C=0.25, R=0.20, A=0.20)."""
        weights = {
            "factual_faithfulness": 0.35,
            "completeness_and_relevance": 0.25,
            "cold_reader_clarity": 0.20,
            "actionability_and_proportion": 0.20,
        }
        weighted_likert = sum(self.dimension_grades[k] * weights[k] for k in EXTERNAL_RUBRIC_DIMENSIONS)
        return round((weighted_likert - 1.0) / 4.0, 4)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["failure_tags"] = list(self.failure_tags)
        return out

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
        *,
        expected_rubric_sha256: str | None = None,
        candidate_text: str | bytes | None = None,
        require_fail_critique: bool = False,
    ) -> ExternalHumanLabelRecord:
        if not isinstance(raw, Mapping):
            raise ValueError("Human label record must be a mapping.")
        case_id = _require_non_empty_field(raw, "case_id", 1)
        surface = _validate_membership(str(raw.get("judge_surface") or "").strip(), VALID_JUDGE_SURFACES, "judge_surface")
        topic = _require_non_empty_field(raw, "topic_family", 2).lower()
        partition = _validate_membership(str(raw.get("partition") or "").strip(), VALID_PARTITIONS, "partition")
        art_sha, rub_id, rub_sha = _validate_record_digests(raw, case_id, expected_rubric_sha256, candidate_text)
        grades = _validate_dimension_grades(raw.get("dimension_grades") or {})
        verdict = _validate_membership(str(raw.get("human_verdict") or "").strip().upper(), VALID_HUMAN_VERDICTS, "human_verdict")
        annotator = validate_human_annotator_id(str(raw.get("annotator_id") or ""))
        graded_at = _require_non_empty_field(raw, "graded_at_utc", 10)
        atomic = validate_atomic_checks(raw.get("atomic_checks"))
        f_tags = validate_failure_tags(raw.get("failure_tags"))
        notes = str(raw.get("notes") or "").strip()
        rationale = str(raw.get("critique_rationale") or notes).strip()
        ev_sha = str(raw.get("evidence_context_sha256") or "").strip().lower()
        if ev_sha:
            ev_sha = _validate_sha256_hex(ev_sha, "evidence_context_sha256")
        enforce_pass_rule_and_critique(
            grades,
            verdict,
            atomic_checks=atomic,
            failure_tags=f_tags,
            critique_rationale=rationale,
            require_fail_critique=require_fail_critique,
        )
        return cls(
            case_id=case_id,
            judge_surface=surface,
            topic_family=topic,
            partition=partition,
            artifact_sha256=art_sha,
            external_rubric_id=rub_id,
            external_rubric_sha256=rub_sha,
            dimension_grades=grades,
            human_verdict=verdict,
            annotator_id=annotator,
            graded_at_utc=graded_at,
            notes=notes,
            atomic_checks=atomic,
            failure_tags=f_tags,
            critique_rationale=rationale,
            evidence_context_sha256=ev_sha,
        )


def verify_partition_isolation(records: Sequence[ExternalHumanLabelRecord]) -> None:
    """Enforce zero topic_family or artifact_sha256 overlap across dev/calibration/final_holdout."""
    topic_to_partition: dict[str, str] = {}
    sha_to_partition: dict[str, str] = {}
    seen_case_ids: set[str] = set()
    for rec in records:
        if rec.case_id in seen_case_ids:
            raise ValueError(f"Duplicate case_id '{rec.case_id}' in human gold store.")
        seen_case_ids.add(rec.case_id)
        prior_part = topic_to_partition.get(rec.topic_family)
        if prior_part is not None and prior_part != rec.partition:
            raise ValueError(
                f"Partition topic leakage detected: topic_family '{rec.topic_family}' spans "
                f"'{prior_part}' and '{rec.partition}'."
            )
        topic_to_partition[rec.topic_family] = rec.partition
        prior_sha_part = sha_to_partition.get(rec.artifact_sha256)
        if prior_sha_part is not None and prior_sha_part != rec.partition:
            raise ValueError(
                f"Partition artifact leakage detected: artifact_sha256 '{rec.artifact_sha256[:12]}' spans "
                f"'{prior_sha_part}' and '{rec.partition}'."
            )
        sha_to_partition[rec.artifact_sha256] = rec.partition


class ExternalRubricHumanStore:
    """Tamper-evident store for human external-rubric calibration and holdout labels."""

    def __init__(self, store_path: Path | None = None, rubric_path: Path | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        self.store_path = Path(store_path) if store_path is not None else (repo_root / DEFAULT_HUMAN_GOLD_STORE_REL_PATH)
        self.rubric_path = Path(rubric_path) if rubric_path is not None else (repo_root / DEFAULT_EXTERNAL_RUBRIC_REL_PATH)
        self.rubric = load_and_verify_external_rubric(self.rubric_path)
        self.rubric_sha256 = str(self.rubric["rubric_sha256"])

    def _read_verified_payload(self) -> Mapping[str, Any] | None:
        if not self.store_path.is_file():
            return None
        payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
            raise ValueError(f"Malformed human gold store schema at '{self.store_path}'.")
        expected_digest = str(payload.get("store_digest") or "").strip()
        body_no_digest = {k: v for k, v in payload.items() if k != "store_digest"}
        computed = compute_payload_sha256(
            json.dumps(body_no_digest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        )
        if not expected_digest or expected_digest != computed:
            raise ValueError(
                f"Human gold store digest mismatch at '{self.store_path}': expected {computed}, observed {expected_digest or 'EMPTY'}."
            )
        return payload

    def load_records(
        self,
        *,
        partition: str | None = None,
        judge_surface: str | None = None,
    ) -> list[ExternalHumanLabelRecord]:
        """Load and validate all stored human records, optionally filtered by partition or surface."""
        payload = self._read_verified_payload()
        if payload is None:
            return []
        records = [
            ExternalHumanLabelRecord.from_mapping(item, expected_rubric_sha256=self.rubric_sha256)
            for item in payload["records"]
        ]
        verify_partition_isolation(records)
        return [
            r
            for r in records
            if (partition is None or r.partition == partition)
            and (judge_surface is None or r.judge_surface == judge_surface)
        ]

    def load_quarantined(self) -> list[QuarantineDisposition]:
        """Load verified quarantined/abstained items kept isolated from gold drift cohorts."""
        payload = self._read_verified_payload()
        if payload is None:
            return []
        return [QuarantineDisposition.from_mapping(item) for item in payload.get("quarantined_records", [])]

    def save_records(
        self,
        records: Sequence[ExternalHumanLabelRecord],
        *,
        quarantined: Sequence[QuarantineDisposition] | None = None,
    ) -> dict[str, Any]:
        """Validate partition isolation and atomically persist records and quarantines with a store digest."""
        validated = [
            ExternalHumanLabelRecord.from_mapping(r.to_dict(), expected_rubric_sha256=self.rubric_sha256)
            for r in records
        ]
        verify_partition_isolation(validated)
        q_list = list(quarantined) if quarantined is not None else self.load_quarantined()
        body: dict[str, Any] = {
            "schema_version": "ide-judge-external-human-labels:1.1.0",
            "external_rubric_id": "external_judge_rubric_v1",
            "external_rubric_sha256": self.rubric_sha256,
            "record_count": len(validated),
            "records": [r.to_dict() for r in validated],
            "quarantined_count": len(q_list),
            "quarantined_records": [q.to_dict() for q in q_list],
        }
        store_digest = compute_payload_sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        )
        full_payload = {**body, "store_digest": store_digest}
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.store_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(full_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(self.store_path)
        return full_payload

    def append_label(
        self,
        record: ExternalHumanLabelRecord | Mapping[str, Any],
        *,
        candidate_text: str | bytes | None = None,
        require_fail_critique: bool = False,
    ) -> ExternalHumanLabelRecord:
        """Validate and append or update a single human label record with partition checks."""
        raw_map = record.to_dict() if isinstance(record, ExternalHumanLabelRecord) else record
        validated_new = ExternalHumanLabelRecord.from_mapping(
            raw_map,
            expected_rubric_sha256=self.rubric_sha256,
            candidate_text=candidate_text,
            require_fail_critique=require_fail_critique,
        )
        existing = self.load_records()
        updated = [r for r in existing if r.case_id != validated_new.case_id]
        updated.append(validated_new)
        self.save_records(updated)
        return validated_new

    def append_quarantine(self, record: QuarantineDisposition | Mapping[str, Any]) -> QuarantineDisposition:
        """Record an abstained or defective item in quarantined_records without contaminating gold labels."""
        raw_map = record.to_dict() if isinstance(record, QuarantineDisposition) else record
        validated_q = QuarantineDisposition.from_mapping(raw_map)
        existing_gold = [r for r in self.load_records() if r.case_id != validated_q.case_id]
        existing_q = [q for q in self.load_quarantined() if q.case_id != validated_q.case_id]
        existing_q.append(validated_q)
        self.save_records(existing_gold, quarantined=existing_q)
        return validated_q


__all__ = [
    "DEFAULT_EXTERNAL_RUBRIC_REL_PATH",
    "DEFAULT_HUMAN_GOLD_STORE_REL_PATH",
    "EXTERNAL_RUBRIC_DIMENSIONS",
    "ExternalHumanLabelRecord",
    "ExternalRubricHumanStore",
    "FORBIDDEN_ANNOTATOR_TOKENS",
    "FORBIDDEN_INTERNAL_RULE_LEAK_TOKENS",
    "VALID_HUMAN_VERDICTS",
    "VALID_JUDGE_SURFACES",
    "VALID_PARTITIONS",
    "compute_external_rubric_sha256",
    "compute_payload_sha256",
    "load_and_verify_external_rubric",
    "validate_human_annotator_id",
    "verify_partition_isolation",
]
