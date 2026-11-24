"""Fail-closed Clean-Slate Judge v3 Declarative Rubric Registry (`<= 160L`, Centralized `core-governance` Adapter).

Delegates profile catalog loading, 3-tier passing criteria, and non-degenerate weight
enforcement to `~/.gemini/config/plugins/core-governance/mcp/judge_v3_rigor_engine.py`.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from apps_eval.graders.judge._core_governance_bridge import get_judge_v3_rigor_engine

_eng = get_judge_v3_rigor_engine()
AtomicCheckSpec = _eng.AtomicCheckSpec
JudgeProfileV3 = _eng.JudgeProfileV3
UnknownJudgeProfileError = _eng.UnknownJudgeProfileError
VALID_PILLARS = _eng.VALID_PILLARS
MAX_CHECK_WORDS = _eng.MAX_CHECK_WORDS
MAX_COLD_READ_WORDS = _eng.MAX_COLD_READ_WORDS
MAX_RENDERED_RUBRIC_WORDS = _eng.MAX_RENDERED_RUBRIC_WORDS
MAX_RENDERED_RUBRIC_CHARS = _eng.MAX_RENDERED_RUBRIC_CHARS
render_v3_rubric_prompt = _eng.render_v3_rubric_prompt

DEFAULT_JUDGE_RUBRICS_V3_REL_PATH = Path("config/governance/judge_rubrics_v3.json")
REQUIRED_CLUSTERS: tuple[str, ...] = (
    "resume_sections",
    "resume_whole_coherence",
    "outreach_sequence",
    "company_research_brief",
    "agent_trace_and_calibration",
)


def compute_rubric_doc_sha256(payload: Mapping[str, Any]) -> str:
    clean = {k: v for k, v in payload.items() if k != "rubric_sha256"}
    encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class JudgeRubricRegistryV3:
    """Immutable, fail-closed Judge v3 profile registry backed by centralized `core-governance`."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.rubric_id: str = "judge_rubrics_v3"
        self.rubric_sha256: str = str(inner.rubric_sha256)

    @classmethod
    def load(cls, rubric_path: Path | None = None) -> JudgeRubricRegistryV3:
        repo_root = Path(__file__).resolve().parents[3]
        target = Path(rubric_path).resolve() if rubric_path is not None else (repo_root / DEFAULT_JUDGE_RUBRICS_V3_REL_PATH)
        if not target.is_file():
            raise FileNotFoundError(f"Judge v3 rubric SSOT missing at '{target}'.")
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping) or str(raw.get("rubric_id") or "") not in {"judge_rubrics_v3", "judge_archetypes_v3"}:
            raise ValueError("Invalid Judge v3 rubric_id; expected 'judge_rubrics_v3'.")
        expected_sha = compute_rubric_doc_sha256(raw)
        observed_sha = str(raw.get("rubric_sha256") or "").strip()
        if not observed_sha or observed_sha != expected_sha:
            raise ValueError(f"Judge v3 rubric SHA-256 mismatch: expected {expected_sha}, got {observed_sha!r}.")
        try:
            inner = _eng.JudgeRubricRegistryV3.load(target)
        except Exception as exc:
            msg = str(exc)
            if "exceeds 25 words" in msg:
                msg = f"{msg} (violates <=25-word rule)"
            raise ValueError(msg) from exc

        seen_clusters = {p.cluster for p in inner.list_profiles()}
        missing_clusters = sorted(set(REQUIRED_CLUSTERS) - seen_clusters)
        if missing_clusters:
            raise ValueError(f"Judge v3 registry missing required clusters: {missing_clusters}.")
        return cls(inner)

    def get_profile(self, token: str) -> Any:
        return self._inner.get_profile(token)

    def list_profiles(self) -> tuple[Any, ...]:
        return self._inner.list_profiles()

    def to_document_dict(self) -> dict[str, Any]:
        """Materialize canonical standalone document dict for adversarial tamper testing."""
        profs_out: dict[str, Any] = {}
        for p in self.list_profiles():
            profs_out[p.profile_id] = {
                "archetype": p.archetype,
                "assurance_tier": p.assurance_tier,
                "reasoning_effort": p.reasoning_effort,
                "cluster": p.cluster,
                "title": p.title,
                "cold_read_question": p.cold_read_question,
                "pass_threshold": p.pass_threshold,
                "checks": [asdict(c) for c in p.checks],
            }
        doc: dict[str, Any] = {
            "schema_version": "3.1.0",
            "rubric_id": "judge_rubrics_v3",
            "profiles": profs_out,
        }
        doc["rubric_sha256"] = compute_rubric_doc_sha256(doc)
        return doc


__all__ = [
    "AtomicCheckSpec",
    "DEFAULT_JUDGE_RUBRICS_V3_REL_PATH",
    "JudgeProfileV3",
    "JudgeRubricRegistryV3",
    "MAX_CHECK_WORDS",
    "MAX_COLD_READ_WORDS",
    "MAX_RENDERED_RUBRIC_CHARS",
    "MAX_RENDERED_RUBRIC_WORDS",
    "REQUIRED_CLUSTERS",
    "UnknownJudgeProfileError",
    "VALID_PILLARS",
    "compute_rubric_doc_sha256",
    "render_v3_rubric_prompt",
]
