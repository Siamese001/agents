"""Append-only SHA-256 hash-chained Human QRELS & Quarantine Store (DIE Parity).

Maintains human-only relevance grades (0..3), atomic consistency checks,
structured rejection tags, correction chains, and non-contaminating quarantine
dispositions with deterministic `store_digest` tamper detection.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from apps_eval.qrels.qrels_rubric_contract import (
    ALLOWED_QRELS_GRADES,
    EXTERNAL_QRELS_RUBRIC_ID,
    QrelsQuarantineDisposition,
    canonical_json_sha256,
    enforce_qrels_grade_consistency,
    load_and_verify_qrels_rubric,
    validate_qrels_atomic_checks,
    validate_qrels_rejection_tags,
)

DEFAULT_QRELS_HUMAN_STORE_REL_PATH = Path("artifacts/eval_harness/qrels_human_gold_store.v1.json")
_FORBIDDEN_ANNOTATOR_TOKENS = (
    "bot",
    "llm",
    "agent",
    "model",
    "judge",
    "synthetic",
    "auto",
    "gpt",
    "claude",
    "gemini",
)


def validate_human_qrels_annotator_id(annotator_id: str) -> str:
    """Validate non-empty human annotator identity and block synthetic/bot labels."""
    clean = str(annotator_id or "").strip()
    if len(clean) < 3:
        raise ValueError("annotator_id must be at least 3 characters.")
    tokens = [t for t in re.split(r"[^a-z0-9]+", clean.lower()) if t]
    for tok in tokens:
        if tok in _FORBIDDEN_ANNOTATOR_TOKENS:
            raise ValueError(
                f"Synthetic or automated annotator identity rejected fail-closed: {clean!r}."
            )
    return clean


@dataclass(frozen=True)
class ExternalQrelsHumanRecord:
    """Single immutable human QRELS judgment sealed with rubric and artifact hashes."""

    event_id: str
    pair_id: str
    query_id: str
    record_id: str
    surface: str
    topic_family: str
    partition: str
    artifact_sha256: str
    external_rubric_id: str
    external_rubric_sha256: str
    relevance_grade: int
    atomic_checks: dict[str, bool]
    rejection_tags: list[str]
    critique_rationale: str
    annotator_id: str
    graded_at_utc: str
    prior_event_id: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExternalQrelsHumanStore:
    """SHA-256 sealed JSON store for human QRELS grades and quarantined items."""

    def __init__(
        self,
        store_path: Path | str,
        *,
        rubric_path: Path | None = None,
    ) -> None:
        self.store_path = Path(store_path)
        self.rubric = load_and_verify_qrels_rubric(rubric_path)
        self.rubric_sha256 = str(self.rubric["rubric_sha256"])

    def _empty_payload(self) -> dict[str, Any]:
        unsigned = {
            "schema_version": "1.0.0",
            "rubric_id": EXTERNAL_QRELS_RUBRIC_ID,
            "rubric_sha256": self.rubric_sha256,
            "records": [],
            "quarantined_records": [],
        }
        return {**unsigned, "store_digest": canonical_json_sha256(unsigned)}

    def _load_raw(self) -> dict[str, Any]:
        if not self.store_path.is_file():
            return self._empty_payload()
        raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"QRELS human store must be a JSON object: {self.store_path}")
        supplied = str(raw.get("store_digest") or "")
        unsigned = {k: v for k, v in raw.items() if k != "store_digest"}
        expected = canonical_json_sha256(unsigned)
        if supplied != expected:
            raise ValueError(
                f"QRELS human store tamper detected: expected '{expected}', observed '{supplied}'."
            )
        return raw

    def _save_raw(self, unsigned: dict[str, Any]) -> dict[str, Any]:
        sealed = {**unsigned, "store_digest": canonical_json_sha256(unsigned)}
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        staging = self.store_path.with_name(f".{self.store_path.name}.tmp-{os.getpid()}")
        try:
            staging.write_text(json.dumps(sealed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(staging, self.store_path)
        except BaseException:
            staging.unlink(missing_ok=True)
            raise
        return sealed

    def verify_integrity(self) -> bool:
        """Return True if the store exists or initializes cleanly with matching store_digest."""
        self._load_raw()
        return True

    def load_records(self) -> list[ExternalQrelsHumanRecord]:
        """Return active (latest per pair_id) human QRELS records, excluding quarantined items."""
        raw = self._load_raw()
        active: dict[str, ExternalQrelsHumanRecord] = {}
        for item in raw.get("records") or []:
            rec = ExternalQrelsHumanRecord(
                event_id=str(item["event_id"]),
                pair_id=str(item["pair_id"]),
                query_id=str(item["query_id"]),
                record_id=str(item["record_id"]),
                surface=str(item.get("surface") or "candidate_graph"),
                topic_family=str(item.get("topic_family") or ""),
                partition=str(item.get("partition") or "dev"),
                artifact_sha256=str(item["artifact_sha256"]),
                external_rubric_id=str(item["external_rubric_id"]),
                external_rubric_sha256=str(item["external_rubric_sha256"]),
                relevance_grade=int(item["relevance_grade"]),
                atomic_checks=dict(item.get("atomic_checks") or {}),
                rejection_tags=list(item.get("rejection_tags") or []),
                critique_rationale=str(item.get("critique_rationale") or ""),
                annotator_id=str(item["annotator_id"]),
                graded_at_utc=str(item["graded_at_utc"]),
                prior_event_id=item.get("prior_event_id"),
                notes=str(item.get("notes") or ""),
            )
            active[rec.pair_id] = rec
        return list(active.values())

    def load_quarantined(self) -> list[QrelsQuarantineDisposition]:
        """Return active quarantined dispositions isolated from scored records."""
        raw = self._load_raw()
        by_pair: dict[str, QrelsQuarantineDisposition] = {}
        for item in raw.get("quarantined_records") or []:
            q = QrelsQuarantineDisposition(
                pair_id=str(item["pair_id"]),
                query_id=str(item["query_id"]),
                record_id=str(item["record_id"]),
                surface=str(item.get("surface") or "candidate_graph"),
                topic_family=str(item.get("topic_family") or ""),
                partition=str(item.get("partition") or "dev"),
                artifact_sha256=str(item["artifact_sha256"]),
                reason=str(item["reason"]),
                annotator_id=str(item["annotator_id"]),
                recorded_at_utc=str(item["recorded_at_utc"]),
                notes=str(item.get("notes") or ""),
            )
            by_pair[q.pair_id] = q
        return list(by_pair.values())

    def append_grade(
        self,
        payload: Mapping[str, Any],
        *,
        require_grade0_rationale: bool = True,
    ) -> ExternalQrelsHumanRecord:
        """Validate, chain, and atomically persist a human QRELS grade."""
        annotator = validate_human_qrels_annotator_id(str(payload.get("annotator_id") or ""))
        grade = payload.get("relevance_grade")
        if not isinstance(grade, int) or isinstance(grade, bool) or grade not in ALLOWED_QRELS_GRADES:
            raise ValueError(f"relevance_grade must be integer 0..3, got {grade!r}.")
        checks = validate_qrels_atomic_checks(payload.get("atomic_checks"))
        tags = list(validate_qrels_rejection_tags(payload.get("rejection_tags")))
        critique = str(payload.get("critique_rationale") or payload.get("notes") or "").strip()
        enforce_qrels_grade_consistency(
            grade,
            atomic_checks=checks,
            rejection_tags=tags,
            critique_rationale=critique,
            require_grade0_rationale=require_grade0_rationale,
        )

        raw = self._load_raw()
        pair_id = str(payload["pair_id"]).strip()
        prior_event_id: str | None = None
        for existing in raw.get("records") or []:
            if str(existing.get("pair_id")) == pair_id:
                prior_event_id = str(existing["event_id"])

        rec = ExternalQrelsHumanRecord(
            event_id=str(payload.get("event_id") or f"qrel-{uuid.uuid4()}"),
            pair_id=pair_id,
            query_id=str(payload["query_id"]).strip(),
            record_id=str(payload["record_id"]).strip(),
            surface=str(payload.get("surface") or "candidate_graph").strip(),
            topic_family=str(payload.get("topic_family") or "").strip(),
            partition=str(payload.get("partition") or "dev").strip(),
            artifact_sha256=str(payload["artifact_sha256"]).strip(),
            external_rubric_id=EXTERNAL_QRELS_RUBRIC_ID,
            external_rubric_sha256=self.rubric_sha256,
            relevance_grade=grade,
            atomic_checks=checks,
            rejection_tags=tags,
            critique_rationale=critique,
            annotator_id=annotator,
            graded_at_utc=str(payload["graded_at_utc"]).strip(),
            prior_event_id=prior_event_id,
            notes=str(payload.get("notes") or "").strip(),
        )
        unsigned = {k: v for k, v in raw.items() if k != "store_digest"}
        unsigned["records"] = list(unsigned.get("records") or []) + [rec.to_dict()]
        # Remove from quarantined if explicitly re-graded
        unsigned["quarantined_records"] = [
            q for q in (unsigned.get("quarantined_records") or []) if str(q.get("pair_id")) != pair_id
        ]
        self._save_raw(unsigned)
        return rec

    def append_quarantine(self, payload: Mapping[str, Any]) -> QrelsQuarantineDisposition:
        """Persist a non-contaminating quarantine disposition for an ungradable QRELS item."""
        annotator = validate_human_qrels_annotator_id(str(payload.get("annotator_id") or ""))
        q = QrelsQuarantineDisposition(
            pair_id=str(payload["pair_id"]).strip(),
            query_id=str(payload["query_id"]).strip(),
            record_id=str(payload["record_id"]).strip(),
            surface=str(payload.get("surface") or "candidate_graph").strip(),
            topic_family=str(payload.get("topic_family") or "").strip(),
            partition=str(payload.get("partition") or "dev").strip(),
            artifact_sha256=str(payload["artifact_sha256"]).strip(),
            reason=str(payload["reason"]).strip().upper(),
            annotator_id=annotator,
            recorded_at_utc=str(payload["recorded_at_utc"]).strip(),
            notes=str(payload.get("notes") or "").strip(),
        )
        raw = self._load_raw()
        unsigned = {k: v for k, v in raw.items() if k != "store_digest"}
        unsigned["quarantined_records"] = list(unsigned.get("quarantined_records") or []) + [q.to_dict()]
        self._save_raw(unsigned)
        return q


__all__ = [
    "DEFAULT_QRELS_HUMAN_STORE_REL_PATH",
    "ExternalQrelsHumanRecord",
    "ExternalQrelsHumanStore",
    "validate_human_qrels_annotator_id",
]
