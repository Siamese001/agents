"""Live behavioral probes for the 8-pillar Cost, Cache, and Token Budget Auditor.

Executes real cache, quarantine, briefing, prompt-trimming, zero-model replay,
and token-budget modules against deterministic fixtures rather than scanning
source files for substring markers.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import socket
import sys
import tempfile
import time
import types
from pathlib import Path
from typing import Any

import yaml


def load_yaml_strict(path: Path) -> tuple[dict[str, Any], str | None]:
    """Strictly parse a YAML mapping via PyYAML; fail closed on missing or invalid YAML."""
    if not path.is_file():
        return {}, f"Missing YAML file: {path.name}"
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw)
    except Exception as exc:  # guardian: allow-broad-exception -- report exact YAML parse failure
        return {}, f"Malformed YAML in {path.name}: {type(exc).__name__}: {exc}"
    if not isinstance(parsed, dict):
        return {}, f"YAML root in {path.name} must be a mapping, got {type(parsed).__name__}"
    return parsed, None


def load_repo_module(repo_root: Path, rel_path: str) -> tuple[types.ModuleType | None, str | None]:
    """Load and execute a Python module from repo_root/rel_path with isolated sys.path."""
    target = (repo_root / rel_path).resolve()
    if not target.is_file():
        return None, f"Missing module {rel_path}"

    search_entries = [
        str(repo_root.resolve()),
        str((repo_root / "resume_graph_engine" / "src").resolve()),
        str((repo_root / "outreach_engine" / "src").resolve()),
        str((repo_root / "resume_engine" / "src").resolve()),
    ]
    primary_root = Path(__file__).resolve().parents[1]
    if primary_root != repo_root.resolve():
        search_entries.extend(
            [
                str(primary_root),
                str(primary_root / "resume_graph_engine" / "src"),
                str(primary_root / "outreach_engine" / "src"),
                str(primary_root / "resume_engine" / "src"),
            ]
        )

    digest = hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:10]
    parent_pkg = ""
    rel_norm = rel_path.replace("\\", "/")
    for prefix in ("resume_graph_engine/src/", "outreach_engine/src/", "resume_engine/src/", ""):
        if not prefix or rel_norm.startswith(prefix):
            sub = rel_norm[len(prefix) :]
            parts = [p for p in sub.split("/")[:-1] if p]
            if parts:
                parent_pkg = ".".join(parts)
            break

    mod_name = f"{parent_pkg}.{target.stem}" if parent_pkg else f"_cost_audit_probe_{digest}_{target.stem}"
    prior_mod = sys.modules.get(mod_name)
    added: list[str] = []
    for entry in reversed(search_entries):
        if entry not in sys.path:
            sys.path.insert(0, entry)
            added.append(entry)
    try:
        if parent_pkg:
            importlib.import_module(parent_pkg)
        spec = importlib.util.spec_from_file_location(mod_name, target)
        if spec is None or spec.loader is None:
            return None, f"Cannot build module spec for {rel_path}"
        module = importlib.util.module_from_spec(spec)
        if parent_pkg:
            module.__package__ = parent_pkg
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module, None
    except Exception as exc:  # guardian: allow-broad-exception -- surface import/exec failure as audit gap
        return None, f"Failed loading {rel_path}: {type(exc).__name__}: {exc}"
    finally:
        if prior_mod is not None:
            sys.modules[mod_name] = prior_mod
        else:
            sys.modules.pop(mod_name, None)
        for entry in added:
            if entry in sys.path:
                sys.path.remove(entry)


def verify_ast_compact_json_surface(path: Path) -> list[str]:
    """Verify via AST that json.dumps calls in compact-cache surfaces specify compact separators."""
    if not path.is_file():
        return [f"Missing compact serialization surface: {path.name}"]
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"Syntax error in {path.name}: {exc}"]

    found_compact_dumps = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_json_dumps = (
            isinstance(func, ast.Attribute)
            and func.attr == "dumps"
            and isinstance(func.value, ast.Name)
            and func.value.id == "json"
        )
        if not is_json_dumps:
            continue
        for kw in node.keywords:
            if kw.arg == "separators" and isinstance(kw.value, (ast.Tuple, ast.List)) and len(kw.value.elts) == 2:
                vals = [
                    elt.value
                    for elt in kw.value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                ]
                if vals == [",", ":"]:
                    found_compact_dumps = True
    if not found_compact_dumps:
        return [f"{path.name} lacks AST-verified json.dumps(..., separators=(',', ':'))"]
    return []


def run_pillar_2_live_probes(repo_root: Path, claude_model: str, openai_model: str) -> tuple[list[str], dict[str, Any]]:
    """Execute live Anthropic 3-breakpoint payload, receipt multiplier, and OpenAI prefix probes."""
    gaps: list[str] = []
    metrics: dict[str, Any] = {}

    apc, err = load_repo_module(
        repo_root,
        "resume_graph_engine/src/apps_rg/runtime/providers/anthropic_prompt_cache.py",
    )
    if err or apc is None:
        gaps.append(err or "Missing anthropic_prompt_cache.py")
    ascp, err = load_repo_module(
        repo_root,
        "resume_graph_engine/src/apps_rg/runtime/providers/anthropic_section_cache_payload.py",
    )
    if err or ascp is None:
        gaps.append(err or "Missing anthropic_section_cache_payload.py")
    spc, err = load_repo_module(repo_root, "agents/observability/prompt_cache.py")
    if err or spc is None:
        gaps.append(err or "Missing agents/observability/prompt_cache.py")

    if gaps:
        return gaps, metrics

    try:
        s0_body = "SYSTEM AUTHORITY LAW: STRICT EVIDENCE GROUNDING.\n" * 220
        i0_body = "<authority_boundary>SOVEREIGN</authority_boundary>\n<evidence_law>NO FABRICATION</evidence_law>\n" * 140
        c0_body = "FACT_ATOM_1: Delivered $42M cloud migration across 14 business units.\n" * 120
        r0_body = '{"type":"object","required":["resume_display_text","claim_ledger"]}'

        slots = [
            types.SimpleNamespace(slot_id="S0", content=s0_body),
            types.SimpleNamespace(slot_id="I0", content=i0_body),
            types.SimpleNamespace(slot_id="C0", content=c0_body),
            types.SimpleNamespace(slot_id="R0", content=r0_body),
        ]
        compiled_system = "\n\n".join(f"<!-- SLOT: {s.slot_id} -->\n{s.content}" for s in slots)
        art_a = types.SimpleNamespace(
            slot_payloads=slots,
            messages=[
                {"role": "system", "content": compiled_system},
                {"role": "user", "content": "Repair attempt A: tighten word count to 112 words."},
            ],
        )
        art_b = types.SimpleNamespace(
            slot_payloads=slots,
            messages=[
                {"role": "system", "content": compiled_system},
                {"role": "user", "content": "Repair attempt B: tighten word count to 108 words."},
            ],
        )

        p_a = ascp.build_anthropic_section_cache_payload(
            section_id="executive_summary",
            model=claude_model,
            compiled_prompt_artifact=art_a,
            workload_kind="REPAIR",
            run_id="probe_run_a",
        )
        p_b = ascp.build_anthropic_section_cache_payload(
            section_id="executive_summary",
            model=claude_model,
            compiled_prompt_artifact=art_b,
            workload_kind="REPAIR",
            run_id="probe_run_b",
        )
        max_markers = int(getattr(ascp, "MAX_ANTHROPIC_CACHE_MARKERS", 0))
        if max_markers != 3:
            gaps.append(f"MAX_ANTHROPIC_CACHE_MARKERS expected 3, got {max_markers}")
        if p_a.cache_strategy != "pa_slot_prefix_tiers_v2":
            gaps.append(f"Expected cache_strategy 'pa_slot_prefix_tiers_v2', got '{p_a.cache_strategy}'")
        if not (1 <= p_a.cache_marker_count <= 3):
            gaps.append(f"Expected 1..3 active cache markers, got {p_a.cache_marker_count}")
        if not p_a.stable_prefix_hash or p_a.stable_prefix_hash != p_b.stable_prefix_hash:
            gaps.append("Stable Tier-1 prefix hash drifted across identical system slots")
        if not p_a.c0_prefix_hash or p_a.c0_prefix_hash != p_b.c0_prefix_hash:
            gaps.append("Tier-2 C0 prefix hash drifted across identical C0 slots")
        if p_a.volatile_tail_hash == p_b.volatile_tail_hash:
            gaps.append("Volatile tail hash failed to isolate distinct repair user tails")

        ttls = p_a.cache_receipt_seed.get("active_cache_ttls") or []
        if "1h" not in ttls or "5m" not in ttls:
            gaps.append(f"Expected active Tier-1 '1h' and Tier-2 '5m' TTLs, got {ttls}")

        prewarm = ascp.build_prefix_prewarm_plan([p_a, p_b])
        if not prewarm.get("prewarm_enabled") or prewarm.get("expected_cold_writes") != 1 or prewarm.get("expected_warm_reads") != 1:
            gaps.append(f"build_prefix_prewarm_plan failed single-section pre-warming contract: {prewarm}")

        # Mismatched compiled system must fail closed to uncached strategy
        art_mismatch = types.SimpleNamespace(
            slot_payloads=slots,
            messages=[{"role": "system", "content": "TAMPERED SYSTEM TEXT"}, {"role": "user", "content": "go"}],
        )
        p_mis = ascp.build_anthropic_section_cache_payload(
            section_id="executive_summary",
            model=claude_model,
            compiled_prompt_artifact=art_mismatch,
            workload_kind="REPAIR",
        )
        if p_mis.cache_marker_count != 0:
            gaps.append("Tampered compiled system prompt must fail closed with 0 cache markers")

        # Receipt math check
        read_mult = float(getattr(apc, "CACHE_READ_INPUT_MULTIPLIER", -1.0))
        w5_mult = float(getattr(apc, "CACHE_WRITE_5M_INPUT_MULTIPLIER", -1.0))
        w1h_mult = float(getattr(apc, "CACHE_WRITE_1H_INPUT_MULTIPLIER", -1.0))
        if (read_mult, w5_mult, w1h_mult) != (0.10, 1.25, 2.00):
            gaps.append(f"Anthropic cache multipliers drifted: read={read_mult}, 5m={w5_mult}, 1h={w1h_mult}")

        receipt = apc.build_cache_receipt_from_usage(
            seed={"cache_enabled": True, "cache_strategy": p_a.cache_strategy, "active_cache_ttls": ["1h"], "input_usd_per_million": 3.0},
            provider="external_claude",
            model=claude_model,
            section_id="executive_summary",
            usage={"input_tokens": 500, "output_tokens": 180, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 4000},
        )
        if receipt.get("cache_hit_ratio") != 1.0 or receipt.get("estimated_cached_input_tokens") != 900:
            gaps.append(f"build_cache_receipt_from_usage produced wrong read math: {receipt}")

        # Shared OpenAI prefix cache checks
        norm = spc.normalize_static_template("Alpha\r\nBeta\n\n")
        if norm != "Alpha\nBeta\n":
            gaps.append("normalize_static_template failed CRLF/trailing-newline normalization")
        fp1 = spc.prefix_fingerprint(
            model=openai_model,
            prefix_messages=[{"role": "system", "content": norm}],
            response_format={"b": 2, "a": 1},
        )
        fp2 = spc.prefix_fingerprint(
            model=openai_model,
            prefix_messages=[{"role": "system", "content": norm}],
            response_format={"a": 1, "b": 2},
        )
        fp3 = spc.prefix_fingerprint(
            model=openai_model,
            prefix_messages=[{"role": "system", "content": norm + "MUTATED"}],
            response_format={"a": 1, "b": 2},
        )
        if fp1 != fp2 or fp1 == fp3:
            gaps.append("prefix_fingerprint failed canonical key-order invariance or mutation sensitivity")
        rk = spc.routing_key("outreach", "v1", fp1)
        if rk != f"outreach:v1:{fp1[:24]}":
            gaps.append(f"routing_key malformed: {rk}")
        usage_m = spc.chat_usage_metrics(
            {"usage": {"prompt_tokens": 2000, "completion_tokens": 150, "prompt_tokens_details": {"cached_tokens": 1500}}}
        )
        if usage_m.get("cache_read_ratio") != 0.75 or usage_m.get("uncached_input_tokens") != 500:
            gaps.append(f"chat_usage_metrics miscomputed cached token ratio: {usage_m}")

        metrics = {
            "compiled_prefix_chars": len(s0_body) + len(i0_body) + len(c0_body),
            "volatile_tail_chars": len(r0_body) + 60,
            "cache_marker_count": p_a.cache_marker_count,
            "read_multiplier": read_mult,
            "write_1h_multiplier": w1h_mult,
            "write_5m_multiplier": w5_mult,
        }
    except Exception as exc:  # guardian: allow-broad-exception -- record runtime failure in pillar gaps
        gaps.append(f"Pillar 2 execution failure: {type(exc).__name__}: {exc}")

    return gaps, metrics


def run_pillar_3_live_probes(repo_root: Path) -> list[str]:
    """Execute C02 semantic cache payload cap/round-trip, UWG quarantine block, and judge class checks."""
    gaps: list[str] = []
    c02, err = load_repo_module(
        repo_root,
        "resume_graph_engine/src/apps_rg/runtime/c0/c02_semantic_cache_payload.py",
    )
    if err or c02 is None:
        gaps.append(err or "Missing c02_semantic_cache_payload.py")
    quar, err = load_repo_module(
        repo_root,
        "resume_graph_engine/src/apps_rg/runtime/semantic_cache_persistence_quarantine.py",
    )
    if err or quar is None:
        gaps.append(err or "Missing semantic_cache_persistence_quarantine.py")
    ccj, err = load_repo_module(
        repo_root,
        "apps_research/engines/judges/cache_compatibility_judge.py",
    )
    if err or ccj is None:
        gaps.append(err or "Missing apps_research/engines/judges/cache_compatibility_judge.py")

    if gaps:
        return gaps

    try:
        atoms = [
            {
                "fact_id": f"fact_{i:02d}",
                "claim_text": f"Quantified delivery proof atom {i}",
                "confidence": "HIGH",
                "proof_status": "VERIFIED",
                "retrieval_score": 0.95 - (i * 0.01),
                "source_type": "employment",
            }
            for i in range(30)
        ]
        payload = c02.build_c02_semantic_cache_payload(
            section_id="executive_summary",
            atoms=atoms,
            vector_query_receipt={"dense_search_refs": ["ref_1"], "hybrid_enrichment_item_count": 4},
            target_company="AcmeCloud",
            target_role="SVP Platform",
            jd_digest="jd_sha_123",
            run_id="probe_c02",
        )
        if payload.get("proposal_status") != "PENDING_UWG" or payload.get("durable_write_authority") is not False:
            gaps.append("C02 semantic cache payload violated PENDING_UWG inert proposal authority")
        if len(payload.get("query_output") or []) != 24:
            gaps.append(f"C02 query_output must cap 30 atoms to 24, got {len(payload.get('query_output') or [])}")

        capped_fact_ids = [f"fact_{i:02d}" for i in range(24)]
        if not c02.verify_semantic_fact_digest_cache_hit(
            payload,
            candidate_similarity=0.991,
            candidate_fact_ids=capped_fact_ids,
        ):
            gaps.append("verify_semantic_fact_digest_cache_hit rejected valid >=0.985 fact-matched hit")
        if c02.verify_semantic_fact_digest_cache_hit(
            payload,
            candidate_similarity=0.991,
            candidate_fact_ids=capped_fact_ids[:-1] + ["fact_drifted"],
        ):
            gaps.append("verify_semantic_fact_digest_cache_hit failed to block drifted fact IDs")
        if c02.verify_semantic_fact_digest_cache_hit(
            payload,
            candidate_similarity=0.970,
            candidate_fact_ids=capped_fact_ids,
        ):
            gaps.append("verify_semantic_fact_digest_cache_hit failed to block below-threshold similarity")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            written = c02.write_c02_semantic_cache_payload(tmp_dir, payload)
            loaded = c02.read_c02_semantic_cache_payload(tmp_dir)
            if written is None or loaded.get("intent_digest") != payload.get("intent_digest"):
                gaps.append("C02 semantic cache payload write/read round-trip failed")

            uwg = quar.assess_uwg_durable_write_chain(
                repo_root=repo_root,
                artifact_dir=tmp_dir,
                integrated_dir=None,
            )
            cls = quar.classify_shadow_chroma_write_path(uwg_assessment=uwg)
            assertion = quar.build_no_direct_chroma_write_bypass_assertion(
                repo_root=repo_root,
                artifact_dir=tmp_dir,
                section_id="executive_summary",
                run_id="probe_quarantine",
                uwg_assessment=uwg,
                chroma_classification=cls,
            )
            if uwg.get("durable_vector_persistence_proven") is not False:
                gaps.append("Uncommitted run dir falsely passed durable_vector_persistence_proven")
            if cls != "NON_DURABLE_INDEX_WRITE":
                gaps.append(f"Uncommitted shadow Chroma path must classify as NON_DURABLE_INDEX_WRITE, got {cls}")
            if assertion.get("durable_persistence_claim_allowed") is not False:
                gaps.append("Direct Chroma bypass assertion falsely permitted durable persistence claim")

        judge_cls = getattr(ccj, "CacheCompatibilityJudge", None)
        if judge_cls is None:
            gaps.append("CacheCompatibilityJudge class missing")
        else:
            judge_inst = judge_cls()
            if getattr(judge_inst, "dimension", "") != "cache_compatibility":
                gaps.append("CacheCompatibilityJudge dimension mismatch")
    except Exception as exc:  # guardian: allow-broad-exception -- record runtime failure in pillar gaps
        gaps.append(f"Pillar 3 execution failure: {type(exc).__name__}: {exc}")

    return gaps


def run_pillar_4_live_probes(repo_root: Path, model_pin: str) -> tuple[list[str], int]:
    """Execute CacheIdentity, BriefingCache, GovernedBriefingResolver, Targeting, and ExactReuse probes."""
    gaps: list[str] = []
    briefing_chars = 0

    cid, e1 = load_repo_module(repo_root, "resume_graph_engine/src/apps_rg/cache/cache_identity.py")
    bcache, e2 = load_repo_module(repo_root, "resume_graph_engine/src/apps_rg/cache/briefing_cache.py")
    resolver, e3 = load_repo_module(repo_root, "outreach_engine/src/apps_lic/pipeline/briefing_resolver.py")
    bridge, e4 = load_repo_module(repo_root, "outreach_engine/src/apps_lic/integrations/apps_research_bridge.py")
    tca, e5 = load_repo_module(repo_root, "resume_graph_engine/src/apps_rg/runtime/targeting_context_authority.py")
    err_mod, e6 = load_repo_module(repo_root, "apps_model_telemetry/exact_response_reuse.py")

    for mod, msg in ((cid, e1), (bcache, e2), (resolver, e3), (bridge, e4), (tca, e5), (err_mod, e6)):
        if msg or mod is None:
            gaps.append(msg or "Missing Pillar 4 cache module")
    if gaps:
        return gaps, briefing_chars

    try:
        # 1. CacheIdentity sentinel rejection + mutation sensitivity
        bad_id = cid.CacheIdentity(
            resolved_model_snapshot="unknown",
            registry_digest="reg_123",
            prompt_template_hash="tpl_123",
            generation_params={"temperature": 0.0},
        )
        if bad_id.is_cacheable() or bad_id.compute_key() != "":
            gaps.append("CacheIdentity failed to reject sentinel 'unknown' model snapshot")

        k1 = cid.CacheIdentity(
            resolved_model_snapshot=model_pin,
            registry_digest="reg_123",
            prompt_template_hash="tpl_123",
            generation_params={"b": 2, "a": 1},
            input_digests={"jd": "h1"},
            role="SVP",
        ).compute_key()
        k2 = cid.CacheIdentity(
            resolved_model_snapshot=model_pin,
            registry_digest="reg_123",
            prompt_template_hash="tpl_123",
            generation_params={"a": 1, "b": 2},
            input_digests={"jd": "h1"},
            role="SVP",
        ).compute_key()
        k3 = cid.CacheIdentity(
            resolved_model_snapshot=model_pin,
            registry_digest="reg_123",
            prompt_template_hash="tpl_MUTATED",
            generation_params={"a": 1, "b": 2},
            input_digests={"jd": "h1"},
            role="SVP",
        ).compute_key()
        if len(k1) != 64 or k1 != k2 or k1 == k3:
            gaps.append("CacheIdentity key failed 64-hex canonical stability or template mutation sensitivity")

        # 2. BriefingCache disk persistence + TTL expiry
        sample_brief = (
            "Strategic Priorities:\n"
            "- Consolidate multi-cloud AI platform governance across enterprise business units.\n"
            "- Reduce inference spend through prompt caching and deterministic routing.\n"
        ) * 18
        briefing_chars = len(sample_brief)
        with tempfile.TemporaryDirectory() as tmp:
            cdir = Path(tmp) / "briefings"
            bkey = bcache.compute_briefing_cache_key(
                company_name="Acme Corp",
                jd_hash="jd_hash_001",
                target_role="SVP AI Platform",
                model_pin=model_pin,
            )
            cache_w = bcache.BriefingCache(cache_dir=cdir)
            cache_w.put(
                bkey,
                bcache.CachedBriefing(
                    company_name="Acme Corp",
                    target_role="SVP AI Platform",
                    briefing_text=sample_brief,
                    digest="dig_1",
                    source="PROBE",
                    created_at=time.time(),
                    ttl_seconds=3600.0,
                ),
            )
            cache_r = bcache.BriefingCache(cache_dir=cdir)
            hit = cache_r.get(bkey)
            if hit is None or hit.briefing_text != sample_brief:
                gaps.append("BriefingCache disk reload missed valid non-expired briefing")

            exp_key = bkey + "_exp"
            cache_w.put(
                exp_key,
                bcache.CachedBriefing(
                    company_name="Acme Corp",
                    target_role="SVP AI Platform",
                    briefing_text=sample_brief,
                    digest="dig_exp",
                    source="PROBE",
                    created_at=time.time() - 500.0,
                    ttl_seconds=10.0,
                ),
            )
            if bcache.BriefingCache(cache_dir=cdir).get(exp_key) is not None:
                gaps.append("BriefingCache served expired TTL entry")

            # 3. GovernedBriefingResolver: verify unverified fallback never poisons cache + verified Path B CACHE_HIT
            resolver.GovernedBriefingResolver.clear_cache()
            try:
                unverified = resolver.GovernedBriefingResolver.resolve(
                    company_name="UnknownOfflineCorp",
                    target_role="VP Platform",
                    job_description_text="Offline probe",
                    auto_research=False,
                    force_fresh=False,
                )
                if unverified.resolution_source != "HERMETIC_FALLBACK" or len(resolver.GovernedBriefingResolver._cache) != 0:
                    gaps.append("Unverified HERMETIC_FALLBACK must not poison GovernedBriefingResolver._cache")

                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    shared_disk = Path(tmp) / "shared_briefing_disk"
                    resolver.GovernedBriefingResolver.SHARED_DISK_CACHE_DIR = shared_disk
                    res1 = resolver.GovernedBriefingResolver.resolve(
                        company_name="Citi",
                        target_role="Head of AI Strategy",
                        job_description_text="Lead enterprise AI strategy and governance.",
                        auto_research=True,
                        force_fresh=False,
                    )
                    resolver.GovernedBriefingResolver.clear_cache()
                    res2 = resolver.GovernedBriefingResolver.resolve(
                        company_name="Citi",
                        target_role="Head of AI Strategy",
                        job_description_text="Lead enterprise AI strategy and governance.",
                        auto_research=False,
                        force_fresh=False,
                    )
                if (
                    res2.resolution_source != "CACHE_HIT"
                    or res1.digest != res2.digest
                    or not res2.is_verified
                    or not res2.metadata.get("reused_from_shared_disk")
                ):
                    gaps.append(f"GovernedBriefingResolver second resolve did not hit shared disk cache (got {res2.resolution_source}, meta={res2.metadata})")
            finally:
                resolver.GovernedBriefingResolver.SHARED_DISK_CACHE_DIR = None
                resolver.GovernedBriefingResolver.clear_cache()

            # 4. Targeting binding digest sensitivity
            td1 = tca.build_targeting_binding_digest(
                target_title="SVP AI",
                target_company="Acme",
                jd_text="Lead AI platform",
                briefing_text=sample_brief,
            )
            td2 = tca.build_targeting_binding_digest(
                target_title="SVP AI",
                target_company="Acme",
                jd_text="Lead DIFFERENT role",
                briefing_text=sample_brief,
            )
            if len(td1) != 64 or td1 == td2:
                gaps.append("build_targeting_binding_digest failed JD mutation sensitivity")

            # 5. ExactRequestIdentity unbound rejection + store/lookup round-trip
            unbound = err_mod.build_exact_request_identity(
                run_id="",
                stage="L2",
                section_id="executive_summary",
                provider="external_openai",
                model=model_pin,
                request_digest="req_1",
                prompt_text="prompt",
                native_payload={"a": 1},
                temperature=0.0,
                max_output_tokens=400,
                timeout_seconds=30.0,
            )
            if unbound is not None:
                gaps.append("build_exact_request_identity must return None for unbound empty run_id")

            bound = err_mod.build_exact_request_identity(
                run_id="run_probe_1",
                stage="L2",
                section_id="executive_summary",
                provider="external_openai",
                model=model_pin,
                request_digest="req_1",
                prompt_text="prompt body",
                native_payload={"a": 1},
                temperature=0.0,
                max_output_tokens=400,
                timeout_seconds=30.0,
            )
            reusable_result = {
                "provider_requested": "external_openai",
                "provider_attempted": True,
                "provider_available": True,
                "runtime_generation_status": "REAL_LLM",
                "model": model_pin,
                "stub": False,
                "exact_provider_error": "",
                "raw_model_output": '{"ok":true}',
            }
            ev_dig = err_mod.store_exact_response(artifact_dir=Path(tmp), identity=bound, result=reusable_result)
            looked = err_mod.lookup_exact_response(artifact_dir=Path(tmp), identity=bound)
            if not ev_dig or looked is None or looked[0].get("raw_model_output") != '{"ok":true}':
                gaps.append("Exact response cache store/lookup round-trip failed")

        # Verify bridge exposes callable bundle finder
        if not callable(getattr(bridge, "_find_valid_persisted_artifact_bundle", None)):
            gaps.append("apps_research_bridge._find_valid_persisted_artifact_bundle is not callable")
    except Exception as exc:  # guardian: allow-broad-exception -- record runtime failure in pillar gaps
        gaps.append(f"Pillar 4 execution failure: {type(exc).__name__}: {exc}")

    return gaps, briefing_chars
