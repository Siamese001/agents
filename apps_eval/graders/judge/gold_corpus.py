"""Stratified 48-item gold-corpus curator, DIE Studio pool bundler, zero-leakage blinding bundler, and offline review-sheet I/O."""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from apps_eval.graders.judge.blind_pool_deduplicator import (
    VALID_NUANCE_PROFILES,
    deduplicate_blind_candidates,
    split_prompt_core_and_lineage,
    validate_nuanced_answer_calibration_difficulty,
    validate_query_input_quality,
)
from apps_eval.graders.judge.external_rubric_store import load_and_verify_external_rubric
from apps_eval.graders.judge.frontier_rubric_contract import (
    extract_sanitized_evidence_excerpts,
    shuffle_pool_items_seeded,
)

RESUME_JUDGE_FAMILIES: tuple[str, ...] = (
    "headline",
    "executive_summary",
    "competencies",
    "employment_bullets",
    "role_narrative",
    "whole_resume_coherence",
)

OUTREACH_JUDGE_SURFACES: tuple[str, ...] = (
    "x1d_quorum",
    "executive_judge_panel",
)

STRATA_TIERS: tuple[str, ...] = ("clean_pass", "borderline", "subtle_defect")

EXTERNAL_RUBRIC_PATHS: dict[str, str] = {
    "resume_engine": "apps_eval/rubrics/external_human_resume_stakeholder_v1.yaml",
    "outreach_engine": "apps_eval/rubrics/external_human_outreach_stakeholder_v1.yaml",
}

FORBIDDEN_BLIND_KEYS: frozenset[str] = frozenset(
    {
        "expected_tier",
        "expected_pass",
        "gold_pass_label",
        "gold_human_score",
        "planted_defect_class",
        "subtle_defect_type",
        "internal_judge_scores",
        "x1d_score",
        "x3_disposition",
        "source_run_id",
        "model_id",
        "is_repeat_anchor",
        "canonical_item_id",
        "nuance_profile",
    }
)


def canonical_sha256(obj: Any) -> str:
    """Return deterministic SHA-256 hex digest of any JSON-serializable object."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def load_external_stakeholder_rubric(engine: str, repo_root: Path | str | None = None) -> tuple[dict[str, Any], str]:
    """Load external stakeholder rubric YAML for `resume_engine` or `outreach_engine` and return `(doc, sha256)`."""
    if engine not in EXTERNAL_RUBRIC_PATHS:
        raise ValueError(f"Unknown engine {engine!r}; expected one of {sorted(EXTERNAL_RUBRIC_PATHS)}")
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    rubric_path = root / EXTERNAL_RUBRIC_PATHS[engine]
    raw_text = rubric_path.read_text(encoding="utf-8")
    doc = yaml.safe_load(raw_text) or {}
    if not isinstance(doc, dict) or not doc.get("rubric_id"):
        raise ValueError(f"Malformed external stakeholder rubric at {rubric_path}")
    return doc, hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GoldCandidateRecord:
    """Canonical gold candidate item stored in `data/judge_calibration/*_gold_candidates.v1.jsonl`."""

    item_id: str
    engine: str
    judge_family: str
    expected_tier: str
    expected_pass: bool
    target_context: str
    candidate_text: str
    allowed_facts: tuple[str, ...]
    subtle_defect_type: str | None = None
    source_provenance: str = ""
    channel: str = "resume_section"
    recipient_class: str = "hiring_manager"
    topic_family: str = ""
    nuance_profile: str = "CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION"
    target_company: str = ""
    target_role: str = ""
    target_mandate: str = ""
    section_label: str = ""

    def target_job_card(self) -> dict[str, str]:
        """Return structured Target Job Mandate card fields for Card 1 in the Calibration Studio."""
        family_labels = {
            "headline": "Resume Headline",
            "executive_summary": "Executive Summary",
            "competencies": "Core Competencies",
            "employment_bullets": "Employment Bullets",
            "role_narrative": "Role Narrative",
            "whole_resume_coherence": "Whole-Resume Multi-Section Excerpt",
            "x1d_quorum": "Outreach Message Sequence",
            "executive_judge_panel": "Executive Outreach Email / InMail",
        }
        sec = self.section_label or family_labels.get(self.judge_family, self.judge_family)
        comp = self.target_company
        role = self.target_role
        mandate = self.target_mandate
        if not (comp and role and mandate):
            m = re.search(
                r"\bfor\s+([A-Za-z0-9&\s.-]+?)\s*\(([^,)]+),\s*(?:requiring|bridging|reviewing|spanning)\s+([^)]+)\)",
                self.target_context,
            )
            if m:
                comp = comp or m.group(1).strip()
                role = role or m.group(2).strip()
                mandate = mandate or m.group(3).strip()
            else:
                comp = comp or ("Target Executive Account" if self.engine == "outreach_engine" else "Enterprise Target Employer")
                role = role or self.recipient_class.replace("_", " ").title()
                mandate = mandate or self.target_context.rstrip("?. ")
        return {
            "target_company": comp,
            "target_role": role,
            "target_mandate": mandate[0].upper() + mandate[1:] if mandate else "",
            "section_label": sec,
        }

    def item_digest(self) -> str:
        return canonical_sha256(
            {
                "item_id": self.item_id,
                "engine": self.engine,
                "judge_family": self.judge_family,
                "target_context": self.target_context,
                "candidate_text": self.candidate_text,
                "allowed_facts": list(self.allowed_facts),
            }
        )

    def source_evidence_excerpts(self) -> list[dict[str, str]]:
        excerpts: list[dict[str, str]] = []
        for idx, raw_fact in enumerate(self.allowed_facts, start=1):
            fact_str = str(raw_fact).strip()
            if ":" in fact_str:
                src_prefix, body = fact_str.split(":", 1)
                source_label = f"{self.engine}:{src_prefix.strip()}"
                excerpt_body = body.strip()
            else:
                source_label = f"{self.engine}:fact_{idx:02d}"
                excerpt_body = fact_str
            excerpts.append(
                {
                    "evidence_id": f"EV-{idx:02d}",
                    "source": source_label[:120],
                    "excerpt": excerpt_body[:360],
                }
            )
        return excerpts

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "engine": self.engine,
            "judge_family": self.judge_family,
            "expected_tier": self.expected_tier,
            "expected_pass": self.expected_pass,
            "target_context": self.target_context,
            "target_job_card": self.target_job_card(),
            "candidate_text": self.candidate_text,
            "allowed_facts": list(self.allowed_facts),
            "subtle_defect_type": self.subtle_defect_type,
            "source_provenance": self.source_provenance,
            "channel": self.channel,
            "recipient_class": self.recipient_class,
            "topic_family": self.topic_family or f"{self.engine}_{self.item_id}",
            "nuance_profile": self.nuance_profile,
            "item_digest": self.item_digest(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GoldCandidateRecord:
        tcard = data.get("target_job_card") if isinstance(data.get("target_job_card"), Mapping) else {}
        return cls(
            item_id=str(data["item_id"]),
            engine=str(data["engine"]),
            judge_family=str(data["judge_family"]),
            expected_tier=str(data["expected_tier"]),
            expected_pass=bool(data["expected_pass"]),
            target_context=str(data["target_context"]),
            candidate_text=str(data["candidate_text"]),
            allowed_facts=tuple(str(f) for f in (data.get("allowed_facts") or ())),
            subtle_defect_type=str(data["subtle_defect_type"]) if data.get("subtle_defect_type") else None,
            source_provenance=str(data.get("source_provenance") or ""),
            channel=str(data.get("channel") or "resume_section"),
            recipient_class=str(data.get("recipient_class") or "hiring_manager"),
            topic_family=str(data.get("topic_family") or ""),
            nuance_profile=str(
                data.get("nuance_profile") or "CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION"
            ),
            target_company=str(data.get("target_company") or tcard.get("target_company") or ""),
            target_role=str(data.get("target_role") or tcard.get("target_role") or ""),
            target_mandate=str(data.get("target_mandate") or tcard.get("target_mandate") or ""),
            section_label=str(data.get("section_label") or tcard.get("section_label") or ""),
        )


@dataclass(frozen=True)
class BlindReviewPrompt:
    """Zero-leakage blinded prompt presented to a human rater (in chat or offline review sheet)."""

    blind_id: str
    engine: str
    judge_family: str
    channel: str
    recipient_class: str
    target_context: str
    candidate_text: str
    allowed_facts: tuple[str, ...]
    rubric_id: str
    rubric_sha256: str
    prompt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "blind_id": self.blind_id,
            "engine": self.engine,
            "judge_family": self.judge_family,
            "channel": self.channel,
            "recipient_class": self.recipient_class,
            "target_context": self.target_context,
            "candidate_text": self.candidate_text,
            "allowed_facts": list(self.allowed_facts),
            "rubric_id": self.rubric_id,
            "rubric_sha256": self.rubric_sha256,
            "prompt_sha256": self.prompt_sha256,
        }


@dataclass(frozen=True)
class BlindGradingPacket:
    """Blinded shuffled prompts + separately sealed mapping for unblinding after grading."""

    engine: str
    rubric_id: str
    rubric_sha256: str
    prompts: tuple[BlindReviewPrompt, ...] = ()
    sealed_mapping: dict[str, dict[str, Any]] = field(default_factory=dict)

    def assert_zero_leakage(self) -> None:
        for p in self.prompts:
            payload = p.to_dict()
            leaked = set(payload.keys()) & FORBIDDEN_BLIND_KEYS
            if leaked:
                raise ValueError(f"Blinded prompt {p.blind_id} leaked forbidden keys: {sorted(leaked)}")


def load_gold_candidates_jsonl(path: Path | str) -> list[GoldCandidateRecord]:
    """Load canonical gold candidate JSONL records."""
    fp = Path(path)
    records: list[GoldCandidateRecord] = []
    for line in fp.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        records.append(GoldCandidateRecord.from_dict(json.loads(raw)))
    return records


def write_gold_candidates_jsonl(records: Sequence[GoldCandidateRecord], path: Path | str) -> Path:
    """Write canonical gold candidate records to deterministic JSONL."""
    fp = Path(path)
    fp.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r.to_dict(), sort_keys=True, ensure_ascii=False) for r in records]
    fp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fp


def validate_stratification(records: Sequence[GoldCandidateRecord], *, engine: str) -> list[str]:
    """Validate 24-item balance (`8/8/8` tiers), query quality, nuanced differentiation, and 5-layer deduplication."""
    errors: list[str] = []
    if len(records) != 24:
        errors.append(f"{engine}: expected 24 gold candidates, found {len(records)}")
    tier_counts = {t: 0 for t in STRATA_TIERS}
    family_counts: dict[str, int] = {}
    seen_ids: set[str] = set()
    dedup_inputs: list[dict[str, Any]] = []
    for r in records:
        if r.item_id in seen_ids:
            errors.append(f"{engine}: duplicate item_id {r.item_id!r}")
        seen_ids.add(r.item_id)
        if r.engine != engine:
            errors.append(f"{engine}: item {r.item_id} has mismatched engine {r.engine!r}")
        if r.expected_tier not in tier_counts:
            errors.append(f"{engine}: item {r.item_id} has unknown tier {r.expected_tier!r}")
        else:
            tier_counts[r.expected_tier] += 1
        family_counts[r.judge_family] = family_counts.get(r.judge_family, 0) + 1
        if not r.candidate_text.strip():
            errors.append(f"{engine}: item {r.item_id} has empty candidate_text")
        if not r.allowed_facts:
            errors.append(f"{engine}: item {r.item_id} has empty allowed_facts")
        if r.nuance_profile not in VALID_NUANCE_PROFILES:
            errors.append(f"{engine}: item {r.item_id} has invalid nuance_profile {r.nuance_profile!r}")

        excerpts = r.source_evidence_excerpts()
        q_ok, q_reasons = validate_query_input_quality(r.target_context, excerpts)
        if not q_ok:
            errors.append(f"{engine}: item {r.item_id} failed query quality gate: {'; '.join(q_reasons)}")

        a_ok, a_reasons = validate_nuanced_answer_calibration_difficulty(
            r.candidate_text,
            excerpts,
            judge_surface=r.judge_family,
            nuance_profile=r.nuance_profile,
        )
        if not a_ok:
            errors.append(f"{engine}: item {r.item_id} failed nuanced answer gate: {'; '.join(a_reasons)}")

        dedup_inputs.append(
            {
                "case_id": r.item_id,
                "artifact_sha256": r.item_digest(),
                "topic_family": r.topic_family or f"{r.engine}_{r.item_id}",
                "prompt_text": r.target_context,
                "core_answer_text": r.candidate_text,
            }
        )

    for tier, cnt in tier_counts.items():
        if cnt != 8:
            errors.append(f"{engine}: tier {tier!r} has {cnt} items (expected 8)")
    if engine == "resume_engine":
        for fam in RESUME_JUDGE_FAMILIES:
            if family_counts.get(fam, 0) != 4:
                errors.append(f"resume_engine: judge family {fam!r} has {family_counts.get(fam, 0)} items (expected 4)")
    elif engine == "outreach_engine":
        for surf in OUTREACH_JUDGE_SURFACES:
            if family_counts.get(surf, 0) < 8:
                errors.append(f"outreach_engine: judge surface {surf!r} has {family_counts.get(surf, 0)} items (expected >= 8)")

    kept, stats = deduplicate_blind_candidates(
        dedup_inputs,
        max_prompt_jaccard=0.40,
        max_body_jaccard=0.35,
    )
    if len(kept) != len(records):
        errors.append(
            f"{engine}: 5-layer deduplicator kept {len(kept)}/{len(records)} items (stats={stats})"
        )
    return errors


def _hmac_key(secret_seed: str, label: str) -> str:
    return hmac.new(secret_seed.encode("utf-8"), label.encode("utf-8"), hashlib.sha256).hexdigest()


def build_studio_blind_pool_dict(
    records: Sequence[GoldCandidateRecord],
    *,
    engine: str,
    partition: str = "dev",
    presentation_seed: int = 20260417,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Build DIE-compatible Studio pool JSON payload (`ide-judge-blind-sample-pool:1.2.0`) with zero leakage."""
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    rubric_path = root / "config" / "governance" / "external_judge_rubric_v2.json"
    rubric_payload = load_and_verify_external_rubric(rubric_path)
    rubric_sha = str(rubric_payload["rubric_sha256"])
    raw_items: list[dict[str, Any]] = []
    for r in records:
        prompt_text, core_body, lineage_footer = split_prompt_core_and_lineage(
            r.candidate_text,
            explicit_prompt=r.target_context,
        )
        excerpts, ev_sha = extract_sanitized_evidence_excerpts(r.source_evidence_excerpts())
        lineage_text = lineage_footer or (
            f"### Evidence & Graph Lineage\n"
            f"- Engine: `{r.engine}` | Surface: `{r.judge_family}` | Channel: `{r.channel}` | Recipient: `{r.recipient_class}`\n"
            f"- Evidence Context Digest: `{ev_sha[:16]}` ({len(excerpts)} governed facts)"
        )
        raw_items.append(
            {
                "case_id": r.item_id,
                "judge_surface": f"{r.engine}:{r.judge_family}",
                "partition": partition,
                "topic_family": r.topic_family or f"{r.engine}_{r.item_id}",
                "prompt_text": prompt_text,
                "target_job_card": r.target_job_card(),
                "core_answer_text": core_body,
                "lineage_footer_text": lineage_text,
                "source_evidence_excerpts": excerpts,
                "evidence_context_sha256": ev_sha,
                "artifact_sha256": r.item_digest(),
                "blinded_text": core_body,
            }
        )
    deduped, dedup_stats = deduplicate_blind_candidates(
        raw_items,
        max_prompt_jaccard=0.40,
        max_body_jaccard=0.35,
    )
    shuffled = shuffle_pool_items_seeded(deduped, seed=presentation_seed)
    for item in shuffled:
        leaked = set(item.keys()) & FORBIDDEN_BLIND_KEYS
        if leaked:
            raise ValueError(f"Studio pool item {item.get('case_id')} leaked forbidden keys: {sorted(leaked)}")
    return {
        "schema_version": "ide-judge-blind-sample-pool:1.2.0",
        "external_rubric_id": str(rubric_payload["rubric_id"]),
        "external_rubric_sha256": rubric_sha,
        "judge_surface": engine,
        "partition": partition,
        "presentation_seed": presentation_seed,
        "deduplication_stats": dedup_stats,
        "sample_count": len(shuffled),
        "items": shuffled,
    }


def build_blind_grading_packet(
    records: Sequence[GoldCandidateRecord],
    *,
    engine: str,
    blinding_seed: str,
    repeat_count: int = 3,
    repo_root: Path | str | None = None,
) -> BlindGradingPacket:
    """Create a shuffled zero-leakage blinded packet with `repeat_count` intra-rater duplicate anchors."""
    rubric_doc, rubric_sha = load_external_stakeholder_rubric(engine, repo_root=repo_root)
    rubric_id = str(rubric_doc["rubric_id"])

    entries: list[tuple[str, GoldCandidateRecord, bool]] = []
    by_tier: dict[str, list[GoldCandidateRecord]] = {t: [] for t in STRATA_TIERS}
    for r in records:
        entries.append((f"orig::{r.item_id}", r, False))
        if r.expected_tier in by_tier:
            by_tier[r.expected_tier].append(r)

    repeats_added = 0
    for tier in STRATA_TIERS:
        if repeats_added >= repeat_count:
            break
        bucket = by_tier.get(tier) or []
        if bucket:
            chosen = sorted(bucket, key=lambda rec: _hmac_key(blinding_seed, f"rep_pick::{rec.item_id}"))[0]
            entries.append((f"rep::{chosen.item_id}", chosen, True))
            repeats_added += 1

    ordered = sorted(entries, key=lambda tup: _hmac_key(blinding_seed, tup[0]))
    prefix = "RG" if engine == "resume_engine" else "LIC"
    prompts: list[BlindReviewPrompt] = []
    sealed: dict[str, dict[str, Any]] = {}

    for idx, (slot_key, rec, is_repeat) in enumerate(ordered, start=1):
        blind_id = f"{prefix}_BLIND_{idx:03d}"
        prompt_core = {
            "blind_id": blind_id,
            "engine": rec.engine,
            "judge_family": rec.judge_family,
            "channel": rec.channel,
            "recipient_class": rec.recipient_class,
            "target_context": rec.target_context,
            "candidate_text": rec.candidate_text,
            "allowed_facts": list(rec.allowed_facts),
            "rubric_id": rubric_id,
            "rubric_sha256": rubric_sha,
        }
        prompt_sha = canonical_sha256(prompt_core)
        prompts.append(
            BlindReviewPrompt(
                blind_id=blind_id,
                engine=rec.engine,
                judge_family=rec.judge_family,
                channel=rec.channel,
                recipient_class=rec.recipient_class,
                target_context=rec.target_context,
                candidate_text=rec.candidate_text,
                allowed_facts=rec.allowed_facts,
                rubric_id=rubric_id,
                rubric_sha256=rubric_sha,
                prompt_sha256=prompt_sha,
            )
        )
        sealed[blind_id] = {
            "canonical_item_id": rec.item_id,
            "item_digest": rec.item_digest(),
            "expected_tier": rec.expected_tier,
            "expected_pass": rec.expected_pass,
            "subtle_defect_type": rec.subtle_defect_type,
            "is_repeat_anchor": is_repeat,
            "slot_key": slot_key,
            "prompt_sha256": prompt_sha,
        }

    packet = BlindGradingPacket(
        engine=engine,
        rubric_id=rubric_id,
        rubric_sha256=rubric_sha,
        prompts=tuple(prompts),
        sealed_mapping=sealed,
    )
    packet.assert_zero_leakage()
    return packet


def export_blind_review_sheet_csv(
    packet: BlindGradingPacket,
    output_path: Path | str,
    *,
    repo_root: Path | str | None = None,
) -> Path:
    """Export a zero-leakage blinded CSV sheet for offline human scoring."""
    rubric_doc, _ = load_external_stakeholder_rubric(packet.engine, repo_root=repo_root)
    dim_ids = [str(d["id"]) for d in rubric_doc.get("dimensions", [])]
    flag_ids = [str(f["id"]) for f in rubric_doc.get("hard_fail_flags", [])]
    fieldnames = [
        "blind_id",
        "prompt_sha256",
        "judge_family",
        "channel",
        "recipient_class",
        "target_context",
        "candidate_text",
        "allowed_facts_json",
        *dim_ids,
        *flag_ids,
        "overall_pass",
        "reviewer_notes",
        "graded_at_utc",
    ]
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for p in packet.prompts:
            row: dict[str, Any] = {
                "blind_id": p.blind_id,
                "prompt_sha256": p.prompt_sha256,
                "judge_family": p.judge_family,
                "channel": p.channel,
                "recipient_class": p.recipient_class,
                "target_context": p.target_context,
                "candidate_text": p.candidate_text,
                "allowed_facts_json": json.dumps(list(p.allowed_facts), ensure_ascii=False),
                "overall_pass": "",
                "reviewer_notes": "",
                "graded_at_utc": "",
            }
            for did in dim_ids:
                row[did] = ""
            for fid in flag_ids:
                row[fid] = "false"
            writer.writerow(row)
    return out


def import_blind_review_sheet_csv(
    csv_path: Path | str,
    *,
    engine: str,
    repo_root: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Parse and validate a completed blinded CSV human review sheet into normalized grade dicts."""
    rubric_doc, rubric_sha = load_external_stakeholder_rubric(engine, repo_root=repo_root)
    dim_ids = [str(d["id"]) for d in rubric_doc.get("dimensions", [])]
    flag_ids = [str(f["id"]) for f in rubric_doc.get("hard_fail_flags", [])]
    fp = Path(csv_path)
    file_sha = hashlib.sha256(fp.read_bytes()).hexdigest()
    parsed: list[dict[str, Any]] = []
    with fp.open("r", encoding="utf-8", newline="") as fh:
        for row_num, row in enumerate(csv.DictReader(fh), start=2):
            blind_id = str(row.get("blind_id") or "").strip()
            if not blind_id:
                raise ValueError(f"Row {row_num}: missing blind_id")
            scores: dict[str, int] = {}
            for did in dim_ids:
                raw_val = str(row.get(did) or "").strip()
                if not raw_val:
                    raise ValueError(f"Row {row_num} ({blind_id}): missing dimension score {did!r}")
                val = int(raw_val)
                if val < 1 or val > 5:
                    raise ValueError(f"Row {row_num} ({blind_id}): score {did}={val} outside [1, 5]")
                scores[did] = val
            flags: dict[str, bool] = {}
            for fid in flag_ids:
                raw_f = str(row.get(fid) or "false").strip().lower()
                if raw_f not in {"true", "false", "1", "0", "yes", "no"}:
                    raise ValueError(f"Row {row_num} ({blind_id}): invalid boolean flag {fid}={raw_f!r}")
                flags[fid] = raw_f in {"true", "1", "yes"}
            raw_pass = str(row.get("overall_pass") or "").strip().lower()
            if raw_pass not in {"true", "false", "1", "0", "yes", "no", "pass", "fail"}:
                raise ValueError(f"Row {row_num} ({blind_id}): invalid overall_pass={raw_pass!r}")
            overall_pass = raw_pass in {"true", "1", "yes", "pass"}
            graded_at = str(row.get("graded_at_utc") or "").strip()
            if not graded_at:
                raise ValueError(f"Row {row_num} ({blind_id}): missing graded_at_utc")
            parsed.append(
                {
                    "blind_id": blind_id,
                    "prompt_sha256": str(row.get("prompt_sha256") or "").strip(),
                    "engine": engine,
                    "rubric_id": str(rubric_doc["rubric_id"]),
                    "rubric_sha256": rubric_sha,
                    "dimension_scores": scores,
                    "hard_fail_flags": flags,
                    "overall_pass": overall_pass,
                    "reviewer_notes": str(row.get("reviewer_notes") or "").strip(),
                    "recorded_at": graded_at,
                    "source_sheet_sha256": file_sha,
                }
            )
    return parsed


__all__ = [
    "BlindGradingPacket",
    "BlindReviewPrompt",
    "EXTERNAL_RUBRIC_PATHS",
    "FORBIDDEN_BLIND_KEYS",
    "GoldCandidateRecord",
    "OUTREACH_JUDGE_SURFACES",
    "RESUME_JUDGE_FAMILIES",
    "STRATA_TIERS",
    "build_blind_grading_packet",
    "build_studio_blind_pool_dict",
    "canonical_sha256",
    "export_blind_review_sheet_csv",
    "import_blind_review_sheet_csv",
    "load_external_stakeholder_rubric",
    "load_gold_candidates_jsonl",
    "validate_stratification",
    "write_gold_candidates_jsonl",
]
