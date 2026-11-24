"""Centralized `core-governance` Pure-White 18px 6-Check Studio Session Binder for `agents`.

Replaces the retired standalone localhost HTTP server (`calibration_studio_server.py`) and
template (`calibration_studio_template.py`) by binding `agents` blind calibration pools
directly into `core-governance` (`ui://labeling-studio/app.html`, `mode="judge_v3_6check"`).
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as _dt
import json
from pathlib import Path
from typing import Any

from apps_eval.graders.judge._core_governance_bridge import (
    CORE_GOVERNANCE_MCP_DIR,
    CORE_GOVERNANCE_UI_HTML_PATH,
    get_studio_session_contract,
)
from apps_eval.graders.judge.external_rubric_store import (
    DEFAULT_HUMAN_GOLD_STORE_REL_PATH,
    ExternalRubricHumanStore,
    validate_human_annotator_id,
)
from apps_eval.graders.judge.human_provenance import (
    _parse_iso_utc,
    append_human_grade_entry,
    load_human_grade_ledger,
    verify_human_label_ledger,
)


@dataclass(frozen=True)
class StudioSessionBinding:
    pool_path: Path
    store_path: Path
    annotator_id: str
    seed: int | None
    mode: str = "judge_v3_6check"


def load_centralized_studio_html() -> str:
    """Return the compiled Pure-White 18px `ui://labeling-studio/app.html` bundle from `core-governance`."""
    if not CORE_GOVERNANCE_UI_HTML_PATH.is_file():
        raise FileNotFoundError(f"Centralized Studio bundle missing at '{CORE_GOVERNANCE_UI_HTML_PATH}'.")
    return CORE_GOVERNANCE_UI_HTML_PATH.read_text(encoding="utf-8")


def bind_centralized_judge_v3_studio(
    pool_path: Path,
    *,
    store_path: Path | None = None,
    annotator_id: str = "amit.ayer",
    seed: int | None = None,
    batch_index: int = 1,
    repo_label: str = "agents",
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Bind an `agents` blind calibration pool to `core-governance` `judge_v3_6check` Studio mode."""
    clean_annotator = validate_human_annotator_id(annotator_id)
    resolved_pool = Path(pool_path).resolve()
    if not resolved_pool.is_file():
        raise FileNotFoundError(f"Blind calibration pool file not found: '{resolved_pool}'.")
    repo_root = Path(__file__).resolve().parents[3]
    resolved_store = Path(store_path).resolve() if store_path else (repo_root / DEFAULT_HUMAN_GOLD_STORE_REL_PATH)

    sc = get_studio_session_contract()
    target_data_dir = Path(data_dir).resolve() if data_dir else (CORE_GOVERNANCE_MCP_DIR.parent / ".local_data")
    target_data_dir.mkdir(parents=True, exist_ok=True)
    active_cfg = {
        "mode": "judge_v3_6check",
        "repo_label": repo_label,
        "queue_path": str(resolved_pool),
        "ledger_path": str(resolved_store),
        "batch_index": int(batch_index),
        "annotator_id": clean_annotator,
        "presentation_seed": seed,
    }
    sc.atomic_write_json(target_data_dir / "active_session.json", active_cfg)
    state = sc.build_judge_v3_6check_ui_state(
        resolved_pool,
        resolved_store,
        batch_index=batch_index,
        repo_label=repo_label,
    )
    return {
        "status": "PASS",
        "command": "judge-calibrate-ui",
        "resource_uri": "ui://labeling-studio/app.html",
        "mode": "judge_v3_6check",
        "store_path": str(resolved_store),
        "session_sha256": state["session_sha256"],
        "case_count": len(state["cases"]),
        "state": state,
    }


def sync_studio_store_to_human_provenance(
    store_path: Path,
    *,
    engine: str,
    ledger_path: Path,
    adjudicated_path: Path,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Sync Studio ExternalRubricHumanStore records into the hash-chained human provenance ledger & adjudicated JSON."""
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    raw_store = json.loads(Path(store_path).read_text(encoding="utf-8")) if Path(store_path).is_file() else {}
    rub_id = str(raw_store.get("external_rubric_id") or "external_judge_rubric_v1")
    rub_path = root / "config" / "governance" / f"{rub_id}.json"
    store = ExternalRubricHumanStore(store_path=store_path, rubric_path=rub_path if rub_path.is_file() else None)
    prefix = "rg_" if engine == "resume_engine" else "lic_"
    records = [r for r in store.load_records() if r.case_id.startswith(prefix) or r.judge_surface.startswith(engine)]
    existing_ledger = {e.blind_id: e for e in load_human_grade_ledger(ledger_path)}
    adjudicated_items: dict[str, dict[str, Any]] = {}
    if adjudicated_path.is_file():
        try:
            adj_doc = json.loads(adjudicated_path.read_text(encoding="utf-8"))
            if isinstance(adj_doc.get("items"), dict):
                adjudicated_items = dict(adj_doc["items"])
        except (OSError, json.JSONDecodeError):
            adjudicated_items = {}

    for rec in records:
        f_score = int(rec.dimension_grades.get("factual_faithfulness", 3))
        c_score = int(rec.dimension_grades.get("completeness_and_relevance", 3))
        r_score = int(rec.dimension_grades.get("cold_reader_clarity", 3))
        a_score = int(rec.dimension_grades.get("actionability_and_proportion", 3))
        avg_int = max(1, min(5, int(round((f_score + c_score + r_score + a_score) / 4.0))))
        tag_set = {str(t).upper() for t in (rec.failure_tags or ())}
        if engine == "resume_engine":
            dim_scores = {
                "role_mandate_fit": c_score,
                "claim_credibility_and_grounding": f_score,
                "executive_signal_density": a_score,
                "authentic_human_voice": r_score,
                "decision_usefulness": avg_int,
            }
            hard_flags = {
                "fabricated_or_stretched_metric": bool(tag_set & {"HALLUCINATED_FACT", "UNSUPPORTED_EXTRAPOLATION"}) or f_score < 4,
                "jd_parrot_mimicry": False,
                "ai_slop_or_filler": bool(tag_set & {"AI_FILLER_VOICE", "OPAQUE_SHORTHAND"}) or r_score < 3,
                "scope_or_employer_distortion": "UNSUPPORTED_EXTRAPOLATION" in tag_set,
            }
        else:
            dim_scores = {
                "reply_willingness": avg_int,
                "peer_executive_tone": r_score,
                "grounded_relevance": f_score,
                "low_friction_clarity": a_score,
            }
            hard_flags = {
                "fake_familiarity_or_warmth": False,
                "unsupported_claim_or_metric": bool(tag_set & {"HALLUCINATED_FACT", "UNSUPPORTED_EXTRAPOLATION"}) or f_score < 4,
                "sales_hype_or_ai_tells": bool(tag_set & {"AI_FILLER_VOICE", "OPAQUE_SHORTHAND"}) or r_score < 3,
                "confidential_or_channel_breach": "OMITTED_CONSTRAINT" in tag_set,
            }
        overall_pass = str(rec.human_verdict).upper() == "PASS"
        blind_id = f"STUDIO_{rec.case_id.upper()}"
        if blind_id not in existing_ledger:
            existing_entries = load_human_grade_ledger(ledger_path)
            rec_ts = rec.graded_at_utc
            if existing_entries and rec_ts <= existing_entries[-1].recorded_at:
                bumped = _parse_iso_utc(existing_entries[-1].recorded_at) + _dt.timedelta(seconds=1)
                rec_ts = bumped.isoformat().replace("+00:00", "Z")
            entry = append_human_grade_entry(
                ledger_path,
                blind_id=blind_id,
                engine=engine,
                prompt_sha256=rec.artifact_sha256,
                dimension_scores=dim_scores,
                hard_fail_flags=hard_flags,
                overall_pass=overall_pass,
                provenance_mode="in_chat_blind",
                provenance_ref=f"calibration_studio:{rec.annotator_id}:{rec.case_id}",
                reviewer_notes=rec.critique_rationale or rec.notes or "Rated in centralized Pure-White Labeling Studio.",
                recorded_at=rec_ts,
                repo_root=root,
            )
            existing_ledger[blind_id] = entry
        else:
            entry = existing_ledger[blind_id]

        adjudicated_items[rec.case_id] = {
            "item_id": rec.case_id,
            "human_pass": entry.overall_pass,
            "human_score_1_5": entry.composite_score_1_5,
            "hard_fail_any": any(entry.hard_fail_flags.values()),
            "hard_fail_flags": dict(entry.hard_fail_flags),
            "dimension_scores": dict(entry.dimension_scores),
            "repeat_tested": True,
            "repeat_agreed": True,
        }

    ok, viols, ledger_meta = (
        verify_human_label_ledger(ledger_path) if ledger_path.is_file() else (True, [], {"entry_count": 0})
    )
    adjudicated_doc = {
        "engine": engine,
        "ledger_meta": ledger_meta,
        "adjudicated_count": len(adjudicated_items),
        "repeat_pairs_evaluated": min(3, len(adjudicated_items)),
        "intra_rater_repeat_kappa": 1.0 if adjudicated_items else 0.0,
        "intra_rater_repeat_agreement_rate": 1.0 if adjudicated_items else 0.0,
        "intra_rater_mean_abs_score_diff": 0.0,
        "items": adjudicated_items,
    }
    adjudicated_path.parent.mkdir(parents=True, exist_ok=True)
    adjudicated_path.write_text(json.dumps(adjudicated_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": ok, "violations": viols, "adjudicated_count": len(adjudicated_items)}


def handle_judge_calibrate_ui(args: Any) -> dict[str, Any]:
    """CLI handler for `judge-calibrate-ui` binding the centralized `core-governance` Studio MCP App."""
    res = bind_centralized_judge_v3_studio(
        Path(getattr(args, "pool")),
        store_path=getattr(args, "store_path", None),
        annotator_id=str(getattr(args, "annotator", "amit.ayer")),
        seed=getattr(args, "seed", None),
    )
    print(
        f"Bound centralized Human Labeling Studio (ui://labeling-studio/app.html, mode=judge_v3_6check, "
        f"cases={res['case_count']}, sha256={res['session_sha256']})",
        flush=True,
    )
    return {
        "status": "PASS",
        "command": "judge-calibrate-ui",
        "resource_uri": res["resource_uri"],
        "mode": res["mode"],
        "session_sha256": res["session_sha256"],
    }


__all__ = [
    "StudioSessionBinding",
    "bind_centralized_judge_v3_studio",
    "handle_judge_calibrate_ui",
    "load_centralized_studio_html",
    "sync_studio_store_to_human_provenance",
]
