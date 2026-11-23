"""Tamper-evident SHA-256 hash-chained human label ledger, synthetic batch detector, and intra-rater repeat scorer."""
from __future__ import annotations

import csv
import datetime
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.graders.judge.calibration import compute_cohens_kappa
from apps_eval.graders.judge.gold_corpus import canonical_sha256, load_external_stakeholder_rubric

GENESIS_CHAIN_HASH = "0" * 64
VALID_PROVENANCE_MODES = frozenset({"in_chat_blind", "offline_sheet_import"})
SYNTHETIC_COMMENT_MARKERS = (
    "planted defect detected:",
    "clean grounded multi-touch sequence.",
)
SYNTHETIC_BATCH_IDS = frozenset({"lic_wave5_batch_a", "lic_wave5_batch_b"})


def _parse_iso_utc(raw: str) -> datetime.datetime:
    txt = str(raw or "").strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    dt = datetime.datetime.fromisoformat(txt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def compute_weighted_stakeholder_score(
    dimension_scores: Mapping[str, int | float],
    rubric_doc: Mapping[str, Any],
) -> float:
    """Compute weighted 1.0-5.0 score from rubric dimensions."""
    total = 0.0
    wsum = 0.0
    for dim in rubric_doc.get("dimensions") or []:
        did = str(dim["id"])
        w = float(dim.get("weight", 0.0))
        if did in dimension_scores and w > 0.0:
            total += float(dimension_scores[did]) * w
            wsum += w
    return round(total / wsum, 4) if wsum > 0.0 else 0.0


@dataclass(frozen=True)
class HumanGradeEntry:
    """Single hash-chained human label record bound to blind prompt, rubric hash, and timestamp."""

    blind_id: str
    engine: str
    rubric_id: str
    rubric_sha256: str
    prompt_sha256: str
    dimension_scores: dict[str, int]
    hard_fail_flags: dict[str, bool]
    composite_score_1_5: float
    overall_pass: bool
    reviewer_notes: str
    provenance_mode: str
    provenance_ref: str
    recorded_at: str
    prev_entry_sha256: str
    entry_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "blind_id": self.blind_id,
            "engine": self.engine,
            "rubric_id": self.rubric_id,
            "rubric_sha256": self.rubric_sha256,
            "prompt_sha256": self.prompt_sha256,
            "dimension_scores": dict(self.dimension_scores),
            "hard_fail_flags": dict(self.hard_fail_flags),
            "composite_score_1_5": round(float(self.composite_score_1_5), 4),
            "overall_pass": self.overall_pass,
            "reviewer_notes": self.reviewer_notes,
            "provenance_mode": self.provenance_mode,
            "provenance_ref": self.provenance_ref,
            "recorded_at": self.recorded_at,
            "prev_entry_sha256": self.prev_entry_sha256,
            "entry_sha256": self.entry_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HumanGradeEntry:
        return cls(
            blind_id=str(data["blind_id"]),
            engine=str(data["engine"]),
            rubric_id=str(data["rubric_id"]),
            rubric_sha256=str(data["rubric_sha256"]),
            prompt_sha256=str(data["prompt_sha256"]),
            dimension_scores={str(k): int(v) for k, v in (data.get("dimension_scores") or {}).items()},
            hard_fail_flags={str(k): bool(v) for k, v in (data.get("hard_fail_flags") or {}).items()},
            composite_score_1_5=float(data["composite_score_1_5"]),
            overall_pass=bool(data["overall_pass"]),
            reviewer_notes=str(data.get("reviewer_notes") or ""),
            provenance_mode=str(data["provenance_mode"]),
            provenance_ref=str(data["provenance_ref"]),
            recorded_at=str(data["recorded_at"]),
            prev_entry_sha256=str(data["prev_entry_sha256"]),
            entry_sha256=str(data["entry_sha256"]),
        )


def _compute_entry_hash(payload_without_entry_sha: Mapping[str, Any]) -> str:
    clean = {k: v for k, v in payload_without_entry_sha.items() if k != "entry_sha256"}
    return canonical_sha256(clean)


def load_human_grade_ledger(ledger_path: Path | str) -> list[HumanGradeEntry]:
    fp = Path(ledger_path)
    if not fp.is_file():
        return []
    out: list[HumanGradeEntry] = []
    for line in fp.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if raw:
            out.append(HumanGradeEntry.from_dict(json.loads(raw)))
    return out


def append_human_grade_entry(
    ledger_path: Path | str,
    *,
    blind_id: str,
    engine: str,
    prompt_sha256: str,
    dimension_scores: Mapping[str, int],
    hard_fail_flags: Mapping[str, bool],
    overall_pass: bool,
    provenance_mode: str,
    provenance_ref: str,
    reviewer_notes: str = "",
    recorded_at: str | None = None,
    repo_root: Path | str | None = None,
) -> HumanGradeEntry:
    """Validate and atomically append a hash-chained human grade entry to `ledger_path`."""
    if provenance_mode not in VALID_PROVENANCE_MODES:
        raise ValueError(f"Invalid provenance_mode {provenance_mode!r}; expected {sorted(VALID_PROVENANCE_MODES)}")
    if not str(provenance_ref or "").strip():
        raise ValueError("provenance_ref (conversation_id or signed sheet SHA-256) is required.")
    if not str(prompt_sha256 or "").strip():
        raise ValueError("prompt_sha256 is required.")

    rubric_doc, rubric_sha = load_external_stakeholder_rubric(engine, repo_root=repo_root)
    req_dims = [str(d["id"]) for d in rubric_doc.get("dimensions", [])]
    norm_scores: dict[str, int] = {}
    for did in req_dims:
        if did not in dimension_scores:
            raise ValueError(f"Missing required rubric dimension {did!r}")
        val = int(dimension_scores[did])
        if val < 1 or val > 5:
            raise ValueError(f"Dimension {did!r} score {val} outside [1, 5]")
        norm_scores[did] = val

    req_flags = [str(f["id"]) for f in rubric_doc.get("hard_fail_flags", [])]
    norm_flags = {fid: bool(hard_fail_flags.get(fid, False)) for fid in req_flags}
    any_hard_fail = any(norm_flags.values())
    eff_pass = False if any_hard_fail else bool(overall_pass)

    existing = load_human_grade_ledger(ledger_path)
    if any(e.blind_id == blind_id for e in existing):
        raise ValueError(f"Duplicate blind_id {blind_id!r} already recorded in ledger.")

    ts_str = recorded_at or datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    cur_dt = _parse_iso_utc(ts_str)
    prev_hash = GENESIS_CHAIN_HASH
    if existing:
        prev_entry = existing[-1]
        prev_dt = _parse_iso_utc(prev_entry.recorded_at)
        if cur_dt <= prev_dt:
            raise ValueError(
                f"Non-monotonic timestamp {ts_str!r} <= previous entry {prev_entry.recorded_at!r}; "
                "batch-stamped synthetic rows are prohibited."
            )
        prev_hash = prev_entry.entry_sha256

    comp_score = compute_weighted_stakeholder_score(norm_scores, rubric_doc)
    core = {
        "blind_id": str(blind_id).strip(),
        "engine": engine,
        "rubric_id": str(rubric_doc["rubric_id"]),
        "rubric_sha256": rubric_sha,
        "prompt_sha256": str(prompt_sha256).strip(),
        "dimension_scores": norm_scores,
        "hard_fail_flags": norm_flags,
        "composite_score_1_5": comp_score,
        "overall_pass": eff_pass,
        "reviewer_notes": str(reviewer_notes or "").strip(),
        "provenance_mode": provenance_mode,
        "provenance_ref": str(provenance_ref).strip(),
        "recorded_at": ts_str,
        "prev_entry_sha256": prev_hash,
    }
    entry_sha = _compute_entry_hash(core)
    entry = HumanGradeEntry(entry_sha256=entry_sha, **core)

    fp = Path(ledger_path)
    fp.parent.mkdir(parents=True, exist_ok=True)
    with fp.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")
    return entry


def verify_human_label_ledger(ledger_path: Path | str) -> tuple[bool, list[str], dict[str, Any]]:
    """Verify hash-chain integrity, monotonic per-item human timestamps, and anti-synthetic provenance."""
    fp = Path(ledger_path)
    violations: list[str] = []
    if not fp.is_file():
        return False, [f"Human label ledger not found: {fp}"], {"entry_count": 0}

    try:
        entries = load_human_grade_ledger(fp)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return False, [f"Malformed human label ledger {fp.name}: {exc}"], {"entry_count": 0}

    if not entries:
        return True, [], {"entry_count": 0, "chain_head_sha256": GENESIS_CHAIN_HASH}

    prev_hash = GENESIS_CHAIN_HASH
    prev_dt: datetime.datetime | None = None
    seen_ids: set[str] = set()
    ts_counts: Counter[str] = Counter()

    for idx, entry in enumerate(entries, start=1):
        if entry.blind_id in seen_ids:
            violations.append(f"Row {idx}: duplicate blind_id {entry.blind_id!r}")
        seen_ids.add(entry.blind_id)
        if entry.provenance_mode not in VALID_PROVENANCE_MODES:
            violations.append(f"Row {idx}: invalid provenance_mode {entry.provenance_mode!r}")
        if not entry.provenance_ref.strip():
            violations.append(f"Row {idx}: missing provenance_ref")
        if entry.prev_entry_sha256 != prev_hash:
            violations.append(f"Row {idx} ({entry.blind_id}): broken prev_entry_sha256 hash chain")
        expected_sha = _compute_entry_hash(entry.to_dict())
        if entry.entry_sha256 != expected_sha:
            violations.append(f"Row {idx} ({entry.blind_id}): entry_sha256 tamper mismatch")
        prev_hash = entry.entry_sha256

        try:
            dt = _parse_iso_utc(entry.recorded_at)
        except ValueError:
            violations.append(f"Row {idx} ({entry.blind_id}): invalid recorded_at {entry.recorded_at!r}")
            dt = None
        if dt is not None:
            if prev_dt is not None and dt <= prev_dt:
                violations.append(
                    f"Row {idx} ({entry.blind_id}): non-monotonic timestamp {entry.recorded_at!r} <= {prev_dt.isoformat()}"
                )
            prev_dt = dt
        ts_counts[entry.recorded_at] += 1

        note_l = entry.reviewer_notes.lower()
        if any(m in note_l for m in SYNTHETIC_COMMENT_MARKERS):
            violations.append(f"Row {idx} ({entry.blind_id}): synthetic templated comment marker detected")

    if ts_counts and ts_counts.most_common(1)[0][1] >= 3:
        ts_val, cnt = ts_counts.most_common(1)[0]
        violations.append(f"SYNTHETIC_BATCH_HUMAN_LABELS: {cnt} entries share identical timestamp {ts_val!r}")

    summary = {
        "entry_count": len(entries),
        "chain_head_sha256": prev_hash,
        "distinct_timestamps": len(ts_counts),
        "rubric_ids": sorted({e.rubric_id for e in entries}),
        "rubric_sha256s": sorted({e.rubric_sha256 for e in entries}),
    }
    return len(violations) == 0, violations, summary


def detect_synthetic_human_label_csv(csv_path: Path | str) -> list[str]:
    """Fail-closed scanner catching batch-stamped synthetic rows in human-label CSV files."""
    fp = Path(csv_path)
    if not fp.is_file():
        return []
    violations: list[str] = []
    with fp.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return []
    ts_counts: Counter[str] = Counter()
    synth_comments = 0
    for row in rows:
        ts = str(row.get("labeled_at") or row.get("graded_at_utc") or "").strip()
        if ts:
            ts_counts[ts] += 1
        batch = str(row.get("label_batch_id") or "").strip()
        if batch in SYNTHETIC_BATCH_IDS:
            violations.append(f"{fp.name}: synthetic batch_id {batch!r} found in human label CSV")
            break
        comment = str(row.get("comments") or row.get("reviewer_notes") or "").lower()
        if any(m in comment for m in SYNTHETIC_COMMENT_MARKERS):
            synth_comments += 1
    if len(rows) >= 4 and ts_counts:
        top_ts, top_cnt = ts_counts.most_common(1)[0]
        if top_cnt >= max(3, int(len(rows) * 0.5)):
            violations.append(
                f"SYNTHETIC_BATCH_HUMAN_LABELS: {fp.name} has {top_cnt}/{len(rows)} rows with identical timestamp {top_ts!r}"
            )
    if synth_comments >= 3:
        violations.append(
            f"SYNTHETIC_BATCH_HUMAN_LABELS: {fp.name} has {synth_comments} templated synthetic comments"
        )
    return violations


def unseal_and_adjudicate_human_gold(
    ledger_path: Path | str,
    sealed_mapping: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Unseal a verified human grade ledger, compute intra-rater repeat Kappa, and return per-item human truth."""
    ok, viols, ledger_meta = verify_human_label_ledger(ledger_path)
    if not ok:
        raise ValueError(f"Cannot unseal invalid human label ledger: {'; '.join(viols)}")
    entries = load_human_grade_ledger(ledger_path)

    primary_by_item: dict[str, HumanGradeEntry] = {}
    repeat_by_item: dict[str, HumanGradeEntry] = {}

    for entry in entries:
        meta = sealed_mapping.get(entry.blind_id)
        if meta is None:
            raise ValueError(f"blind_id {entry.blind_id!r} missing from sealed_mapping")
        if entry.prompt_sha256 != str(meta.get("prompt_sha256") or ""):
            raise ValueError(f"prompt_sha256 mismatch for {entry.blind_id!r}")
        cid = str(meta["canonical_item_id"])
        if bool(meta.get("is_repeat_anchor", False)):
            repeat_by_item[cid] = entry
        else:
            primary_by_item[cid] = entry

    rep_a: list[int] = []
    rep_b: list[int] = []
    rep_score_diffs: list[float] = []
    for cid, rep_entry in sorted(repeat_by_item.items()):
        if cid in primary_by_item:
            p_entry = primary_by_item[cid]
            rep_a.append(1 if p_entry.overall_pass else 0)
            rep_b.append(1 if rep_entry.overall_pass else 0)
            rep_score_diffs.append(abs(p_entry.composite_score_1_5 - rep_entry.composite_score_1_5))

    repeat_kappa = round(compute_cohens_kappa(rep_a, rep_b), 4) if rep_a else 0.0
    repeat_exact_rate = (
        round(sum(1 for a, b in zip(rep_a, rep_b) if a == b) / float(len(rep_a)), 4) if rep_a else 0.0
    )

    adjudicated: dict[str, dict[str, Any]] = {}
    for cid, entry in sorted(primary_by_item.items()):
        rep = repeat_by_item.get(cid)
        avg_score = (
            round((entry.composite_score_1_5 + rep.composite_score_1_5) / 2.0, 4)
            if rep is not None
            else entry.composite_score_1_5
        )
        hard_fail_any = any(entry.hard_fail_flags.values()) or (any(rep.hard_fail_flags.values()) if rep else False)
        final_pass = False if hard_fail_any else (entry.overall_pass and (rep.overall_pass if rep else True))
        adjudicated[cid] = {
            "item_id": cid,
            "human_pass": final_pass,
            "human_score_1_5": avg_score,
            "hard_fail_any": hard_fail_any,
            "hard_fail_flags": dict(entry.hard_fail_flags),
            "dimension_scores": dict(entry.dimension_scores),
            "repeat_tested": rep is not None,
            "repeat_agreed": (entry.overall_pass == rep.overall_pass) if rep is not None else None,
        }

    return {
        "ledger_meta": ledger_meta,
        "adjudicated_count": len(adjudicated),
        "repeat_pairs_evaluated": len(rep_a),
        "intra_rater_repeat_kappa": repeat_kappa,
        "intra_rater_repeat_agreement_rate": repeat_exact_rate,
        "intra_rater_mean_abs_score_diff": round(sum(rep_score_diffs) / float(len(rep_score_diffs)), 4)
        if rep_score_diffs
        else 0.0,
        "items": adjudicated,
    }


__all__ = [
    "GENESIS_CHAIN_HASH",
    "HumanGradeEntry",
    "SYNTHETIC_BATCH_IDS",
    "SYNTHETIC_COMMENT_MARKERS",
    "VALID_PROVENANCE_MODES",
    "append_human_grade_entry",
    "compute_weighted_stakeholder_score",
    "detect_synthetic_human_label_csv",
    "load_human_grade_ledger",
    "unseal_and_adjudicate_human_gold",
    "verify_human_label_ledger",
]
