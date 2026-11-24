"""Fail-closed Clean-Slate Judge v3 Declarative Rubric Registry (`<= 200L`).

Loads and SHA-256 verifies `config/governance/judge_rubrics_v3.json` across all 5
`agents` clusters (`resume_sections`, `resume_whole_coherence`, `outreach_sequence`,
`company_research_brief`, `agent_trace_and_calibration`), resolves profiles
fail-closed (`UnknownJudgeProfileError`), and renders `<= 300`-word (`<= 1,800`-char)
atomic binary prompts (`1` cold-read question + `4-6` `YES`/`NO` checks).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

from apps_eval.graders.judge.frontier_rubric_contract import VALID_FAILURE_TAG_IDS

DEFAULT_JUDGE_RUBRICS_V3_REL_PATH = Path("config/governance/judge_rubrics_v3.json")
REQUIRED_CLUSTERS: tuple[str, ...] = (
    "resume_sections",
    "resume_whole_coherence",
    "outreach_sequence",
    "company_research_brief",
    "agent_trace_and_calibration",
)
VALID_PILLARS: frozenset[str] = frozenset(
    {
        "factual_faithfulness",
        "completeness_and_relevance",
        "cold_reader_clarity",
        "actionability_and_proportion",
    }
)
MAX_CHECK_WORDS = 25
MAX_COLD_READ_WORDS = 35
MAX_RENDERED_RUBRIC_WORDS = 300
MAX_RENDERED_RUBRIC_CHARS = 1800


class UnknownJudgeProfileError(KeyError):
    """Raised fail-closed when a caller requests an unmapped or empty Judge v3 profile."""


@dataclass(frozen=True)
class AtomicCheckSpec:
    id: str
    pillar: str
    question: str
    critical: bool
    weight: float
    failure_tag: str


@dataclass(frozen=True)
class JudgeProfileV3:
    profile_id: str
    cluster: str
    title: str
    cold_read_question: str
    pass_threshold: float
    checks: tuple[AtomicCheckSpec, ...]

    @property
    def check_ids(self) -> tuple[str, ...]:
        return tuple(c.id for c in self.checks)


def compute_rubric_doc_sha256(payload: Mapping[str, Any]) -> str:
    """Compute canonical UTF-8 SHA-256 hex digest excluding `rubric_sha256`."""
    clean = {k: v for k, v in payload.items() if k != "rubric_sha256"}
    encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def render_v3_rubric_prompt(profile: JudgeProfileV3) -> str:
    """Render concise (`<= 300` words, `<= 1,800` chars) atomic binary Stage B rubric prompt."""
    lines = [
        f"PROFILE: {profile.profile_id} ({profile.title})",
        f"COLD_READ_QUESTION: {profile.cold_read_question}",
        "ATOMIC_BINARY_CHECKS (answer YES or NO for each; every NO requires verbatim evidence_span):",
    ]
    for chk in profile.checks:
        crit = "CRITICAL" if chk.critical else "WEIGHTED"
        lines.append(f"- {chk.id} [{crit}, w={chk.weight:.2f}, tag={chk.failure_tag}]: {chk.question}")
    lines.append(
        'OUTPUT_JSON: {"cold_read_takeaway":"...","checks":{"<check_id>":{"verdict":"YES|NO","evidence_span":"..."}},"failure_tags":[...]}'
    )
    rendered = "\n".join(lines)
    wc = len(rendered.split())
    if wc > MAX_RENDERED_RUBRIC_WORDS or len(rendered) > MAX_RENDERED_RUBRIC_CHARS:
        raise ValueError(
            f"Rendered rubric '{profile.profile_id}' exceeds anti-bloat cap ({wc}w/{len(rendered)}c)."
        )
    return rendered


class JudgeRubricRegistryV3:
    """Immutable, fail-closed Judge v3 profile registry."""

    def __init__(
        self,
        *,
        rubric_id: str,
        rubric_sha256: str,
        profiles: Mapping[str, JudgeProfileV3],
        aliases: Mapping[str, str],
    ) -> None:
        self.rubric_id = rubric_id
        self.rubric_sha256 = rubric_sha256
        self._profiles = dict(profiles)
        self._aliases = {str(k).strip().lower(): str(v).strip() for k, v in aliases.items()}

    @classmethod
    def load(cls, rubric_path: Path | None = None) -> JudgeRubricRegistryV3:
        repo_root = Path(__file__).resolve().parents[3]
        target = Path(rubric_path) if rubric_path is not None else (repo_root / DEFAULT_JUDGE_RUBRICS_V3_REL_PATH)
        if not target.is_file():
            raise FileNotFoundError(f"Judge v3 rubric SSOT missing at '{target}'.")
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping) or str(raw.get("rubric_id") or "") != "judge_rubrics_v3":
            raise ValueError("Invalid Judge v3 rubric_id; expected 'judge_rubrics_v3'.")
        expected_sha = compute_rubric_doc_sha256(raw)
        observed_sha = str(raw.get("rubric_sha256") or "").strip()
        if not observed_sha or observed_sha != expected_sha:
            raise ValueError(f"Judge v3 rubric SHA-256 mismatch: expected {expected_sha}, got {observed_sha!r}.")

        raw_profiles = raw.get("profiles")
        if not isinstance(raw_profiles, Mapping) or not raw_profiles:
            raise ValueError("Judge v3 registry requires a non-empty 'profiles' object.")

        parsed_profiles: dict[str, JudgeProfileV3] = {}
        seen_clusters: set[str] = set()
        for pid, pdata in raw_profiles.items():
            if not isinstance(pdata, Mapping):
                raise ValueError(f"Profile '{pid}' must be a mapping.")
            cluster = str(pdata.get("cluster") or "").strip()
            if cluster not in REQUIRED_CLUSTERS:
                raise ValueError(f"Profile '{pid}' declares invalid cluster '{cluster}'.")
            seen_clusters.add(cluster)
            cold_q = str(pdata.get("cold_read_question") or "").strip()
            if not cold_q or len(cold_q.split()) > MAX_COLD_READ_WORDS:
                raise ValueError(f"Profile '{pid}' cold_read_question must be 1..{MAX_COLD_READ_WORDS} words.")
            thresh = float(pdata.get("pass_threshold", 0.0))
            if not (0.0 < thresh <= 1.0):
                raise ValueError(f"Profile '{pid}' pass_threshold must be in (0.0, 1.0].")
            raw_checks = pdata.get("checks")
            if not isinstance(raw_checks, list) or not (4 <= len(raw_checks) <= 6):
                raise ValueError(f"Profile '{pid}' must define 4..6 atomic checks.")
            checks: list[AtomicCheckSpec] = []
            seen_cids: set[str] = set()
            for item in raw_checks:
                cid = str(item.get("id") or "").strip()
                pillar = str(item.get("pillar") or "").strip()
                q = str(item.get("question") or "").strip()
                ftag = str(item.get("failure_tag") or "").strip().upper()
                w = float(item.get("weight", 0.0))
                if not cid or cid in seen_cids or pillar not in VALID_PILLARS or ftag not in VALID_FAILURE_TAG_IDS:
                    raise ValueError(f"Profile '{pid}' check '{cid}' has invalid id/pillar/failure_tag.")
                if not q or len(q.split()) > MAX_CHECK_WORDS or w <= 0.0:
                    raise ValueError(f"Profile '{pid}' check '{cid}' violates <=25-word or positive weight rule.")
                seen_cids.add(cid)
                checks.append(AtomicCheckSpec(cid, pillar, q, bool(item.get("critical", False)), w, ftag))
            if not math.isclose(sum(c.weight for c in checks), 1.0, abs_tol=1e-6) or not any(c.critical for c in checks):
                raise ValueError(f"Profile '{pid}' checks must sum to 1.0 and contain >=1 critical check.")
            prof = JudgeProfileV3(str(pid), cluster, str(pdata.get("title") or pid), cold_q, thresh, tuple(checks))
            render_v3_rubric_prompt(prof)
            parsed_profiles[str(pid)] = prof

        missing_clusters = sorted(set(REQUIRED_CLUSTERS) - seen_clusters)
        if missing_clusters:
            raise ValueError(f"Judge v3 registry missing required clusters: {missing_clusters}.")
        raw_aliases = raw.get("profile_aliases") or {}
        for alias_key, target_pid in raw_aliases.items():
            if str(target_pid) not in parsed_profiles:
                raise ValueError(f"Alias '{alias_key}' targets missing profile '{target_pid}'.")
        return cls(rubric_id="judge_rubrics_v3", rubric_sha256=observed_sha, profiles=parsed_profiles, aliases=raw_aliases)

    def list_profiles(self) -> tuple[JudgeProfileV3, ...]:
        return tuple(self._profiles[k] for k in sorted(self._profiles))

    def get_profile(self, token: str | None) -> JudgeProfileV3:
        clean = str(token or "").strip()
        if not clean:
            raise UnknownJudgeProfileError("Judge profile token cannot be empty.")
        if clean in self._profiles:
            return self._profiles[clean]
        mapped = self._aliases.get(clean.lower())
        if mapped and mapped in self._profiles:
            return self._profiles[mapped]
        raise UnknownJudgeProfileError(f"Unknown Judge v3 profile token {token!r}; fail-closed (no default fallback).")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    r_path: Path | None = None
    if "--rubric-path" in args:
        idx = args.index("--rubric-path")
        if idx + 1 < len(args):
            r_path = Path(args[idx + 1])
    reg = JudgeRubricRegistryV3.load(r_path)
    for prof in reg.list_profiles():
        txt = render_v3_rubric_prompt(prof)
        print(f"[PASS] {prof.profile_id:48s} | {len(txt.split()):3d}w | {len(txt):4d}c | checks={len(prof.checks)}")
    print(f"[PASS] judge_rubrics_v3 sha256={reg.rubric_sha256} profiles={len(reg.list_profiles())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
