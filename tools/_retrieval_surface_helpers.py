"""Helper routines for Behavioral 7-Pillar Research & Hybrid Retrieval Surface Auditor."""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Any

RETRIEVAL_PACKAGES = (
    "agents", "apps_eval", "apps_model_telemetry", "apps_research",
    "infrastructure", "ops_scripts", "outreach_engine",
    "resume_engine", "resume_graph_engine", "scripts", "tools",
)


def _ensure_paths(repo_root: Path) -> None:
    for p in (repo_root / "outreach_engine" / "src", repo_root / "resume_graph_engine" / "src", repo_root):
        if p.exists() and str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _static_str_seq(node: ast.AST | None) -> set[str] | None:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)) and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
        return {e.value for e in node.elts}  # type: ignore[misc]
    return None


def _scan_module_ast(py: Path, root: Path, search_bases: tuple[Path, ...]) -> dict[str, Any]:
    from tools.cost_token_budget_probes import resolve_import_from_files

    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    all_set: set[str] | None = None
    ann: set[str] = set()
    sym_typed: dict[str, bool] = {}
    callables: list[tuple[str, int, bool]] = []
    for s in tree.body:
        if isinstance(s, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in s.targets):
            all_set = _static_str_seq(s.value)
        elif isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name):
            if s.target.id == "__all__" and s.value is not None:
                all_set = _static_str_seq(s.value)
            elif s.target.id != "__all__":
                ann.add(s.target.id)
        elif isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sym_typed[s.name] = s.returns is not None
            if not s.name.startswith("_"):
                callables.append((s.name, s.lineno, s.returns is not None))
        elif isinstance(s, ast.ClassDef) and not s.name.startswith("_"):
            sub = [m for m in s.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_")]
            callables.extend((m.name, m.lineno, m.returns is not None) for m in sub)
            sym_typed[s.name] = all(m.returns is not None for m in sub)
    imports = [
        (tgt, a.name, a.asname or a.name)
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for tgt in resolve_import_from_files(py, node, search_bases)
        for a in node.names
    ]
    return {"rel": py.relative_to(root).as_posix(), "all": all_set, "ann": ann, "sym_typed": sym_typed, "callables": callables, "imports": imports}


def _exported_symbol_typed(info: dict[str, Any], sym: str, imp_map: dict[str, tuple[Path, str]], meta: dict[Path, dict[str, Any]]) -> bool:
    if sym in info["ann"]:
        return True
    if sym in info["sym_typed"]:
        return bool(info["sym_typed"][sym])
    tgt, orig = imp_map.get(sym, (None, None))
    t_info = meta.get(tgt) if tgt else None
    return True if t_info is None or orig not in t_info["sym_typed"] else bool(t_info["sym_typed"][orig])


def _facade_exemptions(meta: dict[Path, dict[str, Any]]) -> tuple[set[tuple[Path, str]], dict[Path, set[str]]]:
    exempt_pairs: set[tuple[Path, str]] = set()
    facade_hidden: dict[Path, set[str]] = {}
    for f_py, info in meta.items():
        imp_map: dict[str, tuple[Path, str]] = {}
        for tgt, orig, bound in info["imports"]:
            if orig == "*":
                for n in meta.get(tgt, {}).get("sym_typed", ()):
                    imp_map.setdefault(n, (tgt, n))
            else:
                imp_map[bound] = (tgt, orig)
                if bound.startswith("_") or bound in info["ann"] or info["sym_typed"].get(bound):
                    exempt_pairs.add((tgt, orig))
        exports = info["all"]
        scope_dir = f_py.parent if f_py.name == "__init__.py" else f_py.with_suffix("")
        if not exports or not scope_dir.is_dir() or not all(_exported_symbol_typed(info, s, imp_map, meta) for s in exports):
            continue
        q, seen = [f_py], {f_py}
        while q:
            cur = q.pop(0)
            for tgt, _, _ in meta.get(cur, {}).get("imports", ()):
                if tgt not in seen and tgt != f_py and tgt.is_relative_to(scope_dir):
                    seen.add(tgt)
                    q.append(tgt)
                    facade_hidden.setdefault(tgt, set()).update(exports)
    return exempt_pairs, facade_hidden


def scan_untyped_public_retrieval_callables(repo_root: Path) -> list[dict[str, Any]]:
    """Fail-closed AST scan rejecting public callables without return annotations (facade-aware)."""
    search_bases = tuple(b for b in (repo_root, repo_root / "outreach_engine" / "src", repo_root / "resume_graph_engine" / "src") if b.exists())
    files = [
        py.resolve() for pkg in RETRIEVAL_PACKAGES if (repo_root / pkg).exists()
        for py in sorted((repo_root / pkg).rglob("*.py"))
        if not ("/tests/" in f"/{py.relative_to(repo_root).as_posix()}" or "/artifacts/" in f"/{py.relative_to(repo_root).as_posix()}" or py.name.startswith("test_") or py.name == "conftest.py")
    ]
    meta = {py: _scan_module_ast(py, repo_root, search_bases) for py in files}
    exempt_pairs, facade_hidden = _facade_exemptions(meta)
    missing: list[dict[str, Any]] = []
    for py, info in meta.items():
        allowed = facade_hidden.get(py)
        for name, lineno, is_typed in info["callables"]:
            if not (is_typed or (py, name) in exempt_pairs or name in info["ann"] or (allowed is not None and name not in allowed)):
                missing.append({"file": info["rel"], "line": lineno, "callable": name})
    return missing


def _resolve_pkg_attr(mod: Any, repo_root: Path, rel_path: str, sub_files: list[Path], name: str) -> Any:
    from tools.cost_token_budget_probes import load_repo_module

    prev = sys.modules.get(mod.__name__)
    sys.modules[mod.__name__] = mod
    try:
        for sub_py in sub_files:
            sub_mod, err = load_repo_module(repo_root, sub_py.relative_to(repo_root).as_posix())
            if err is None and sub_mod is not None and name in vars(sub_mod):
                return getattr(sub_mod, name)
    finally:
        if prev is None:
            sys.modules.pop(mod.__name__, None)
        else:
            sys.modules[mod.__name__] = prev
    raise AttributeError(f"module {getattr(mod, '__name__', rel_path)!r} has no attribute {name!r}")


def _require_module(repo_root: Path, rel_path: str) -> Any:
    from tools.cost_token_budget_probes import load_repo_module

    mod, err = load_repo_module(repo_root, rel_path)
    if mod is None or err is not None:
        raise RuntimeError(err or f"Unable to load {rel_path}")
    pkg_dir = (repo_root / rel_path).with_suffix("")
    if (hasattr(mod, "__path__") or pkg_dir.is_dir()) and "__getattr__" not in mod.__dict__:
        sub_files = sorted(p for p in pkg_dir.rglob("*.py") if p.name != "__init__.py" and "__pycache__" not in p.parts)
        mod.__dict__["__getattr__"] = lambda name: _resolve_pkg_attr(mod, repo_root, rel_path, sub_files, name)
    return mod


def _probe_query_decomposition_and_intent_routing(repo_root: Path) -> dict[str, Any]:
    intent_mod = _require_module(repo_root, "apps_research/types/jd_intent_coverage.py")
    sr_mod = _require_module(repo_root, "apps_research/integrations/search_retrieval.py")

    ai_partner_jd = (
        "Lead strategic partnerships and co-sell alliances for enterprise AI agentic platform "
        "architecture with strict security compliance and risk governance."
    )
    inferred = intent_mod.infer_evidence_intents_from_text(ai_partner_jd)
    ids = set(intent_mod.intent_ids(inferred))
    families = set(intent_mod.required_families_for_intents(inferred))
    terms = set(intent_mod.signal_terms_for_intents(inferred))

    ambiguous_only = "Work closely with an internal design partner on UI typography."
    ambiguous_ids = set(intent_mod.intent_ids(intent_mod.infer_evidence_intents_from_text(ambiguous_only)))
    snap = sr_mod.retrieval_config_snapshot(query_families=sorted(families))

    gaps: list[str] = []
    expected_ids = {"partnerships", "platform_engineering", "security_trust", "applied_ai"}
    if not expected_ids.issubset(ids):
        gaps.append(f"Missing expected evidence intents: {expected_ids - ids}")
    if "partner_ecosystem" not in families or "tech_stack_and_tools" not in families:
        gaps.append(f"Required source families incomplete: {sorted(families)}")
    if not terms:
        gaps.append("Signal terms empty for inferred JD intents")
    if "partnerships" in ambiguous_ids:
        gaps.append("Ambiguous isolated word 'partner' falsely triggered partnerships intent")
    if snap.get("query_families") != sorted(families):
        gaps.append("retrieval_config_snapshot failed to preserve routed query families")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "inferred_intents": sorted(ids),
        "required_family_count": len(families),
    }


def _probe_chunking_and_context_window(repo_root: Path) -> dict[str, Any]:
    sr_mod = _require_module(repo_root, "apps_research/integrations/search_retrieval.py")
    prov_mod = _require_module(repo_root, "agents/context/provenance.py")
    budget_mod = _require_module(repo_root, "agents/context/budgeting.py")

    prefixed = sr_mod.apply_contextual_prefix(
        "Deployed hybrid retrieval with 42% lower p95 latency.",
        doc_title="Architecture Case Study", surrounding_text="Section 3: Retrieval Performance",
    )
    item_hi = prov_mod.ContextItem(
        source_id="src_case_study_1", source_type=prov_mod.ContextSourceType.RETRIEVED_EVIDENCE,
        content=prefixed, authority="verified", relevance_score=0.95,
    )
    item_lo = prov_mod.ContextItem(
        source_id="src_low_rel_2", source_type=prov_mod.ContextSourceType.EPHEMERAL_SCRATCH,
        content="Unrelated filler text " * 120, authority="advisory", relevance_score=0.15,
    )
    snap_a = prov_mod.ContextSnapshot(snapshot_id="snap_probe", items=(item_hi, item_lo), max_token_budget=4000)
    snap_b = prov_mod.ContextSnapshot(snapshot_id="snap_probe", items=(item_hi, item_lo), max_token_budget=4000)
    fitted = budget_mod.TokenBudget(max_total_tokens=160, reserved_output_tokens=40).fit_items_to_budget([item_lo, item_hi]).items

    rre_mod = _require_module(repo_root, "apps_research/engines/research_retrieval_engine.py")
    prior_harness = os.environ.get("APPS_RG_TEST_HARNESS")
    os.environ["APPS_RG_TEST_HARNESS"] = "1"
    try:
        rre_engine = rre_mod.create_retrieval_engine(chromadb_path=None)
        rre_id_1 = rre_engine.index_research(
            content="Enterprise AI agentic platform architecture and partner ecosystem governance.",
            topic="AI Platform Strategy", artifact_mode="brief", quality_score=0.92, source_count=3,
            claim_types={"architecture": 4, "partnerships": 2}, sources=["sec_10k", "gartner_mq", "partner_portal"],
        )
        rre_id_2 = rre_engine.index_research(
            content="Cloud data warehouse migration and governance roadmap.",
            topic="AI Platform Strategy", artifact_mode="brief", quality_score=0.86, source_count=2,
            claim_types={"architecture": 2, "security": 3}, sources=["sec_10k", "cloud_blog"],
        )
        similar_res = rre_engine.find_similar_research("AI Platform Strategy", artifact_mode="brief", n_results=5)
        recs = rre_engine.recommend_sources("AI Platform Strategy", current_sources=["cloud_blog"])
        benchmark = rre_engine.get_quality_benchmark("brief")
    finally:
        if prior_harness is None:
            os.environ.pop("APPS_RG_TEST_HARNESS", None)
        else:
            os.environ["APPS_RG_TEST_HARNESS"] = prior_harness

    gaps: list[str] = []
    if "<document>Architecture Case Study</document>" not in prefixed:
        gaps.append("apply_contextual_prefix dropped document title envelope")
    if snap_a.provenance_digest != snap_b.provenance_digest:
        gaps.append("ContextSnapshot provenance_digest is non-deterministic")
    if len(fitted) != 1 or fitted[0].source_id != "src_case_study_1":
        gaps.append("TokenBudget.fit_items_to_budget failed to retain high-relevance evidence within cap")
    if not rre_id_1 or not rre_id_2 or len(similar_res) != 2:
        gaps.append("ResearchRetrievalEngine failed to index and retrieve multi-document artifacts")
    for rid, vec in rre_engine.store._embeddings.items():
        v_norm = sum(x * x for x in vec) ** 0.5
        if len(vec) != 1024 or abs(v_norm - 1.0) > 1e-4:
            gaps.append(
                f"InMemoryResearchStore vector {rid} violated 1024-d L2-normalized contract: "
                f"len={len(vec)}, norm={v_norm:.6f}"
            )
    if not recs or recs[0].get("source") != "sec_10k":
        gaps.append(f"ResearchRetrievalEngine.recommend_sources failed deterministic ranking: {recs}")
    if benchmark.get("sample_size") != 2:
        gaps.append(f"ResearchRetrievalEngine.get_quality_benchmark failed: {benchmark}")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "provenance_digest": snap_a.provenance_digest[:16],
        "fitted_count": len(fitted),
        "research_similar_count": len(similar_res),
        "top_recommended_source": recs[0].get("source") if recs else "",
    }
