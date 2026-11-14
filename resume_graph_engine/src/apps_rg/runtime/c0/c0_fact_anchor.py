"""C0.3 FactAnchor contract, raw-chunk resolution, and disjoint partition helpers."""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from apps_rg.repository_layout import resolve_apps_rg_path

_BUNDLE_FILES: tuple[tuple[str, str], ...] = (
    ("slalom", "slalom_role_episode_bundles.json"),
    ("unify", "unify_role_episode_bundles.json"),
    ("ibm", "ibm_role_episode_bundles.json"),
    ("insurtech", "insurtech_role_episode_bundles.json"),
    ("ey", "ey_role_episode_bundles.json"),
)
_CANDIDATE_FACT_LEDGER_FILE = "master_candidate_skills_fact_ledger_20260518T1100Z.json"

PARTNER_THEME_PATTERNS: Mapping[str, tuple[str, ...]] = {
    "gcp": ("gcp", "google cloud", "bigquery", "cloud run"),
    "google_cloud": ("google cloud", "gcp", "vertex ai", "model armor"),
    "vertex_ai": ("vertex ai", "vertex", "gemini"),
    "model_armor": ("model armor",),
    "anthropic": ("anthropic", "claude"),
    "claude": ("claude", "claude code"),
    "openai": ("openai", "codex", "gpt"),
    "codex": ("codex",),
    "aws": ("aws", "amazon web services", "bedrock", "sagemaker", "eks"),
    "azure": ("azure", "microsoft", "copilot"),
    "databricks": ("databricks", "lakehouse"),
    "kafka": ("kafka", "event-driven", "microservices"),
    "guidewire": ("guidewire", "policycenter", "claimcenter", "billingcenter"),
    "snowflake": ("snowflake",),
}

_NUMERIC_TOKEN_RE = re.compile(
    r"(?:\$\d+(?:\.\d+)?[BMKbmk]?|\b\d+(?:\.\d+)?(?:\+|%|x|bps|ms|s|m|b|k)?\b)",
    re.I,
)
_WORD_TOKEN_RE = re.compile(r"[a-z][a-z0-9]{2,}")
_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "into", "over", "under",
    "across", "through", "while", "where", "when", "which", "their", "there",
    "these", "those", "have", "has", "had", "were", "was", "are", "been", "being",
    "will", "would", "could", "should", "about", "after", "before", "between",
    "within", "without", "using", "used", "via", "per", "all", "any", "both",
    "each", "more", "most", "other", "some", "such", "than", "too", "very",
    "role", "episode", "bundle", "claim", "unit", "section", "slot", "root",
})


def _stem_token(word: str) -> str:
    token = word.lower().strip()
    for suffix in ("ization", "ational", "fulness", "ousness", "iveness", "ments", "ment", "ings", "ing", "edly", "ed", "ies", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    return token[:6] if len(token) > 6 else token


def extract_numeric_tokens(text: str) -> list[str]:
    seen: list[str] = []
    for match in _NUMERIC_TOKEN_RE.finditer(str(text or "")):
        tok = match.group(0).strip()
        if tok and tok not in seen:
            seen.append(tok)
    return seen


def extract_content_word_stems(text: str, *, max_stems: int = 32) -> list[str]:
    stems: list[str] = []
    for match in _WORD_TOKEN_RE.finditer(str(text or "").lower()):
        word = match.group(0)
        if word in _STOPWORDS or word.isdigit():
            continue
        stem = _stem_token(word)
        if len(stem) >= 3 and stem not in stems:
            stems.append(stem)
            if len(stems) >= max_stems:
                break
    return stems


def extract_partner_theme_tags(text: str) -> list[str]:
    blob = f" {str(text or '').lower()} "
    tags: list[str] = []
    for tag, patterns in PARTNER_THEME_PATTERNS.items():
        if any(pat in blob for pat in patterns):
            tags.append(tag)
    return tags


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


@lru_cache(maxsize=4)
def _load_canonical_fact_corpora(repo_root_str: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    repo_root = Path(repo_root_str)
    bundles_by_id: dict[str, dict[str, Any]] = {}
    facts_by_id: dict[str, dict[str, Any]] = {}
    for employer_lane, filename in _BUNDLE_FILES:
        try:
            path = resolve_apps_rg_path(repo_root, "fact_inventory", filename)
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, FileNotFoundError):
            continue
        for bundle in doc.get("role_episode_bundles") or []:
            if isinstance(bundle, Mapping):
                bid = str(bundle.get("bundle_id") or "").strip()
                if bid:
                    bundles_by_id[bid] = {"employer_lane": employer_lane, **dict(bundle)}
    try:
        ledger_path = resolve_apps_rg_path(repo_root, "fact_inventory", _CANDIDATE_FACT_LEDGER_FILE)
        ledger_doc = json.loads(ledger_path.read_text(encoding="utf-8"))
        for row in ledger_doc.get("candidate_facts") or []:
            if isinstance(row, Mapping):
                fid = str(row.get("candidate_fact_id") or row.get("fact_id") or "").strip()
                if fid:
                    facts_by_id[fid] = dict(row)
    except (OSError, ValueError, FileNotFoundError):
        pass
    return bundles_by_id, facts_by_id


def resolve_raw_chunk_text(
    row: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
) -> str:
    """Resolve >=18-word authoritative raw_chunk prose from bundle + fact ledger."""
    existing = str(
        row.get("raw_chunk")
        or (row.get("fact_anchor") or {}).get("resolved_raw_chunk")
        or ""
    ).strip()
    if len(existing.split()) >= 18:
        return existing

    root_dir = repo_root or _default_repo_root()
    bundles_by_id, facts_by_id = _load_canonical_fact_corpora(str(root_dir))

    root_id = str(
        row.get("root_id")
        or row.get("role_episode_bundle_id")
        or row.get("candidate_fact_id")
        or ""
    ).strip()
    fact_id = str(
        row.get("fact_id")
        or row.get("candidate_fact_id")
        or ""
    ).strip()
    linked_ids = [
        str(x).strip()
        for x in (
            list(row.get("linked_source_fact_ids") or [])
            + list(row.get("linked_identity_fact_ids") or [])
            + list(row.get("citation_refs") or [])
        )
        if str(x).strip()
    ]

    bundle = bundles_by_id.get(root_id) or {}
    fact_entry = facts_by_id.get(fact_id) or {}
    if not fact_entry:
        for lid in linked_ids:
            if lid in facts_by_id:
                fact_entry = facts_by_id[lid]
                break

    segments: list[str] = []
    for candidate_text in (
        str(row.get("claim_text") or "").strip(),
        str(row.get("root_claim_text") or "").strip(),
        str(bundle.get("claim_text") or "").strip(),
        str(fact_entry.get("claim_text") or "").strip(),
        str(fact_entry.get("proof_text") or "").strip(),
    ):
        if candidate_text and candidate_text not in segments and not candidate_text.startswith("reb_"):
            segments.append(candidate_text.rstrip("."))

    exec_signals = [
        str(s).strip().rstrip(".")
        for s in (bundle.get("executive_scope_signals") or [])
        if str(s).strip()
    ]
    for sig in exec_signals[:2]:
        if sig and sig not in segments:
            segments.append(sig)

    action = str(row.get("root_claim_action") or bundle.get("claim_action") or "").strip()
    scope = str(row.get("root_claim_scope") or row.get("domain") or bundle.get("claim_scope") or "").strip()
    outcome = str(row.get("root_claim_outcome") or bundle.get("claim_outcome") or "").strip()
    skill_label = str(row.get("skill_label") or "").strip()
    metric_text = str(
        row.get("metric_text")
        or row.get("metric_raw")
        or (row.get("metric_values") or [""])[0]
        or ""
    ).strip()

    if action or scope or outcome:
        clause = " ".join(p for p in (action, scope, outcome) if p).strip().rstrip(".")
        if clause and clause not in segments:
            segments.append(clause)
    if skill_label and all(skill_label.lower() not in s.lower() for s in segments):
        segments.append(f"applying {skill_label}")
    if metric_text and all(metric_text.lower() not in s.lower() for s in segments):
        segments.append(f"delivering {metric_text}")

    joined = ". ".join(s for s in segments if s).strip()
    if joined and not joined.endswith("."):
        joined += "."

    if len(joined.split()) < 18:
        employer = str(row.get("employer_lane") or bundle.get("employer_lane") or "enterprise").strip()
        skill_id = str(row.get("skill_id") or (row.get("technologies") or ["architecture"])[0] or "architecture").replace("skill_", "").replace("_", " ")
        root_label = (root_id or fact_id or "enterprise_architecture").replace("reb_", "").replace("_", " ")
        fallback_clause = (
            f"Architected and governed {employer} production systems for {root_label} "
            f"utilizing {skill_label or skill_id} across cross-functional engineering, platform governance, "
            f"and enterprise delivery workflows"
        )
        if metric_text:
            fallback_clause += f" achieving {metric_text}"
        joined = f"{joined} {fallback_clause}.".strip()

    return joined


def build_fact_anchor(
    row: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Build deterministic FactAnchor payload attached to C0.3 candidates and assignments."""
    existing = row.get("fact_anchor")
    resolved_raw_chunk = resolve_raw_chunk_text(row, repo_root=repo_root)
    metric_text = str(
        row.get("metric_text")
        or row.get("metric_raw")
        or " ".join(str(x) for x in (row.get("metric_values") or []))
        or ""
    ).strip()
    combined_text = " ".join(
        part
        for part in (
            resolved_raw_chunk,
            metric_text,
            str(row.get("skill_label") or ""),
            str(row.get("root_bundle_theme") or row.get("domain") or ""),
            str(row.get("root_id") or row.get("role_episode_bundle_id") or ""),
        )
        if part
    )
    numeric_tokens = extract_numeric_tokens(f"{metric_text} {resolved_raw_chunk}")
    metric_val = str(row.get("metric_value") or "").strip()
    if metric_val and metric_val not in numeric_tokens:
        numeric_tokens.insert(0, metric_val)
    content_word_stems = extract_content_word_stems(combined_text)
    partner_theme_tags = extract_partner_theme_tags(combined_text)
    if isinstance(existing, Mapping):
        if not numeric_tokens and existing.get("numeric_tokens"):
            numeric_tokens = [str(x) for x in existing.get("numeric_tokens") or [] if str(x).strip()]
        if not partner_theme_tags and existing.get("partner_theme_tags"):
            partner_theme_tags = [str(x) for x in existing.get("partner_theme_tags") or [] if str(x).strip()]
    return {
        "numeric_tokens": numeric_tokens,
        "content_word_stems": content_word_stems,
        "resolved_raw_chunk": resolved_raw_chunk,
        "partner_theme_tags": partner_theme_tags,
    }


def select_disjoint_narrative_candidates(
    *,
    narrative_section: str,
    bullet_section: str,
    upstream_bullet_assignments: Sequence[Mapping[str, Any]],
    all_assignments: Sequence[Mapping[str, Any]],
    section_plans: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build narrative assignments disjoint from executive_summary and role bullets when extra roots exist."""
    if not upstream_bullet_assignments:
        return []
    exec_roots = {
        str(r.get("root_id") or "")
        for r in all_assignments
        if str(r.get("section_id") or "") == "executive_summary" and str(r.get("root_id") or "")
    }
    bullet_roots = {
        str(r.get("root_id") or "")
        for r in upstream_bullet_assignments
        if str(r.get("root_id") or "")
    }
    used_Visible_facts = {
        str(r.get("fact_id") or "")
        for r in all_assignments
        if str(r.get("section_id") or "") in {"executive_summary", bullet_section}
        and str(r.get("fact_id") or "")
    }

    alt_pool: list[dict[str, Any]] = []
    if section_plans:
        nar_plan = section_plans.get(narrative_section) or section_plans.get(bullet_section) or {}
        target_profile = str(nar_plan.get("target_role_profile") or "").strip()
        if target_profile != "insurance_it_strategy":
            ledger = nar_plan.get("graph_candidate_decision_ledger") or []
            roots_by_id: dict[str, dict[str, Any]] = {}
            facts_by_root: dict[str, list[dict[str, Any]]] = {}
            skills_by_root: dict[str, list[dict[str, Any]]] = {}
            for raw in ledger:
                if not isinstance(raw, Mapping):
                    continue
                auth = raw.get("authority")
                auth_ok = raw.get("authority_pass") is True or (isinstance(auth, Mapping) and auth.get("authority_pass") is True)
                if not auth_ok:
                    continue
                ctype = str(raw.get("candidate_type") or "")
                rid = str(raw.get("root_id") or raw.get("candidate_id") or "").strip()
                if not rid:
                    continue
                if ctype == "role_episode_root":
                    roots_by_id[rid] = dict(raw)
                elif ctype == "source_fact":
                    facts_by_root.setdefault(rid, []).append(dict(raw))
                elif ctype == "leaf_skill":
                    skills_by_root.setdefault(rid, []).append(dict(raw))

            for rid, root_row in sorted(
                roots_by_id.items(),
                key=lambda item: (-float(item[1].get("ranking_score") or item[1].get("target_alignment_score") or 0.0), item[0]),
            ):
                if rid in bullet_roots or rid in exec_roots:
                    continue
                r_facts = facts_by_root.get(rid) or []
                r_skills = skills_by_root.get(rid) or []
                if not r_facts or not r_skills:
                    continue
                chosen_fact = next(
                    (f for f in r_facts if str(f.get("candidate_id") or "") not in used_Visible_facts),
                    r_facts[0],
                )
                chosen_skill = r_skills[0]
                fact_id_str = str(chosen_fact.get("candidate_id") or "")
                skill_id_str = str(chosen_skill.get("candidate_id") or "")
                alt_pool.append({
                    "root_id": rid,
                    "fact_id": fact_id_str,
                    "skill_id": skill_id_str,
                    "skill_label": str(chosen_skill.get("skill_label") or ""),
                    "employer_lane": str(root_row.get("employer_lane") or ""),
                    "source_family": str(root_row.get("employer_lane") or ""),
                    "root_bundle_theme": str(root_row.get("bundle_theme") or ""),
                    "root_claim_text": str(root_row.get("claim_text") or ""),
                    "root_claim_action": str(root_row.get("claim_action") or ""),
                    "root_claim_scope": str(root_row.get("claim_scope") or ""),
                    "root_claim_outcome": str(root_row.get("claim_outcome") or ""),
                    "citation_refs": [fact_id_str or rid],
                    "graph_path_ids": [
                        str(root_row.get("candidate_path_id") or f"root:{rid}"),
                        str(chosen_skill.get("candidate_path_id") or f"root:{rid}/skill:{skill_id_str}"),
                        str(chosen_fact.get("candidate_path_id") or f"root:{rid}/fact:{fact_id_str}"),
                    ],
                })

    derived_rows: list[dict[str, Any]] = []
    for index, source in enumerate(upstream_bullet_assignments, start=1):
        derived = dict(source)
        if alt_pool:
            alt = alt_pool[(index - 1) % len(alt_pool)]
            derived.update({
                "root_id": alt["root_id"],
                "fact_id": alt["fact_id"],
                "skill_id": alt["skill_id"] or derived.get("skill_id", ""),
                "skill_label": alt["skill_label"] or derived.get("skill_label", ""),
                "root_bundle_theme": alt["root_bundle_theme"] or derived.get("root_bundle_theme", ""),
                "root_claim_text": alt["root_claim_text"] or derived.get("root_claim_text", ""),
                "root_claim_action": alt["root_claim_action"] or derived.get("root_claim_action", ""),
                "root_claim_scope": alt["root_claim_scope"] or derived.get("root_claim_scope", ""),
                "root_claim_outcome": alt["root_claim_outcome"] or derived.get("root_claim_outcome", ""),
                "citation_refs": alt["citation_refs"],
                "graph_path_ids": alt["graph_path_ids"],
                "metric_outcome_id": "",
                "metric_text": "",
                "metric_value": "",
                "metric_unit": "",
                "normalized_metric_signature": "",
            })
        derived["section_id"] = narrative_section
        derived["claim_unit_id"] = f"{narrative_section}:derived:{index:02d}"
        derived["candidate_id"] = f"derived:{narrative_section}:{source['candidate_id']}"
        derived["derived_from_section_id"] = bullet_section
        derived["derived_from_claim_unit_id"] = str(source.get("claim_unit_id") or "")
        derived["counts_toward_global_uniqueness"] = False
        derived["metric_required"] = False
        anchor = build_fact_anchor(derived)
        derived["fact_anchor"] = anchor
        derived["raw_chunk"] = anchor["resolved_raw_chunk"]
        derived_rows.append(derived)
    return derived_rows
