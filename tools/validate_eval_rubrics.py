#!/usr/bin/env python3
"""Deterministic evaluator, judge rubric, schema, and holdout dataset validator across all 5 config roots and 314 data files."""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.pr_governance_core.common import bootstrap_shared_venv

bootstrap_shared_venv(REPO_ROOT)

import yaml  # type: ignore  # noqa: E402
from jsonschema import Draft202012Validator  # type: ignore  # noqa: E402
from jsonschema.exceptions import SchemaError  # type: ignore  # noqa: E402
from tools.cost_token_budget_probes import load_repo_module  # noqa: E402
from tools.hitl_governance import load_approved_provider_models  # noqa: E402
from tools.lint_production_purity import PRODUCTION_DIRECTORIES, check_file_production_purity  # noqa: E402

CONFIG_ROOTS: tuple[str, ...] = ("config", "outreach_engine/config", "apps_eval", "apps_research/config", "resume_graph_engine/config")
DATA_ROOTS: tuple[str, ...] = ("data", "outreach_engine/data", "resume_graph_engine/data")
_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ImportFrom, ast.Import, ast.Assign, ast.AnnAssign)


def _validate_eval_modules_ast_and_schemas(repo_root: Path) -> tuple[int, int, list[str]]:
    """Verify AST syntax + definitions on eval/judge/grader/rubric modules and JSON Schema validity."""
    violations: list[str] = []
    seen_py: set[Path] = set()
    py_files: list[Path] = []

    apps_eval_dir = repo_root / "apps_eval"
    if apps_eval_dir.is_dir():
        for p in sorted(apps_eval_dir.rglob("*.py")):
            if "__pycache__" not in p.parts and "/tests/" not in p.as_posix():
                seen_py.add(p)
                py_files.append(p)

    for sub in ("outreach_engine/src", "resume_graph_engine/src", "apps_research", "tools"):
        base = repo_root / sub
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts or p in seen_py:
                continue
            posix = p.as_posix()
            if any(tok in p.name or tok in posix for tok in ("eval", "judge", "grader", "rubric")):
                seen_py.add(p)
                py_files.append(p)

    for p in py_files:
        rel = str(p.relative_to(repo_root))
        try:
            src = p.read_text(encoding="utf-8")
        except OSError as exc:
            violations.append(f"{rel}: unreadable evaluation module ({exc})")
            continue
        if p.name == "__init__.py" and not src.strip():
            continue
        if not src.strip():
            violations.append(f"Empty evaluation module detected: {rel}")
            continue
        try:
            tree = ast.parse(src, filename=str(p))
        except SyntaxError as exc:
            violations.append(f"{rel}:{exc.lineno or 1}: SyntaxError in evaluation module ({exc.msg})")
            continue
        if not any(isinstance(n, _DEF_NODES) for n in tree.body) and p.name != "__init__.py":
            violations.append(f"{rel}: evaluation module contains zero AST definitions or exports")

    schema_count = 0
    seen_schemas: set[Path] = set()
    for croot in CONFIG_ROOTS:
        cbase = repo_root / croot
        if not cbase.is_dir():
            continue
        for sf in sorted(cbase.rglob("*.json")):
            if sf in seen_schemas:
                continue
            if not (sf.name.endswith(".schema.json") or sf.parent.name == "schemas" or "schema" in sf.name):
                continue
            seen_schemas.add(sf)
            rel_s = str(sf.relative_to(repo_root))
            try:
                schema_obj = json.loads(sf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                violations.append(f"{rel_s}: invalid JSON Schema JSON ({exc})")
                continue
            if isinstance(schema_obj, dict) and (
                "$schema" in schema_obj or "properties" in schema_obj or "definitions" in schema_obj
            ):
                schema_count += 1
                try:
                    Draft202012Validator.check_schema(schema_obj)
                except SchemaError as exc:
                    violations.append(f"{rel_s}: invalid JSON Schema ({exc.message})")

    return len(py_files), schema_count, violations


def _probe_app_graders(contracts_mod: Any, graders_mod: Any, app_id: str, clean_body: str, bad_body: str) -> list[str]:
    errs: list[str] = []
    all_grader_ids = (
        "schema", "artifact_presence", "x3_disposition", "forbidden_content",
        "grounded_claim", "provenance", "section_structure", "length_bounds",
        "side_effect", "escalation", "determinism",
    )
    scenario = contracts_mod.EvalScenario(
        scenario_id=f"scn_live_probe_{app_id}", suite_id="suite_probe", app_id=app_id,
        description=f"Live deterministic grader probe for {app_id}", fixture_path="probe.json",
        graders=all_grader_ids, rubric_id=f"rub_probe_{app_id}",
    )
    provenance = contracts_mod.FixtureProvenance(scenario_id=f"scn_live_probe_{app_id}", fixture_path="probe.json")
    fixture = contracts_mod.EvalFixture(
        scenario=scenario, input_dir=".", expected_dir=".", snapshot_path="probe.json", artifacts_dir=".",
        expected={
            "required_output_keys": ["draft", "sections"], "required_artifacts": ["final_artifact.json"],
            "expected_x3": "APPROVE", "forbidden_terms": ["guaranteed_offer"], "grounded_claims_required": True,
            "required_provenance": ["ev_ref_1"], "required_sections": ["summary"],
            "length_bounds": {"min_words": 5, "max_words": 60}, "allow_side_effects": False, "escalation_required": False,
        },
        provenance=provenance,
    )
    clean_kwargs: dict[str, Any] = {
        "app_id": app_id, "scenario_id": scenario.scenario_id, "x3_disposition": "APPROVE",
        "output": {"draft": clean_body, "sections": {"summary": clean_body}},
        "claims": [{"id": "c1", "supported": True, "source_ids": ["src_1"]}],
        "artifacts": ["final_artifact.json"], "provenance": {"evidence_refs": ["ev_ref_1"]},
        "side_effects": {"writes": [], "product_state_mutated": False},
    }
    clean_hash = graders_mod._canonical_hash(contracts_mod.AppOutputSnapshot(**clean_kwargs))
    clean_snap = contracts_mod.AppOutputSnapshot(**clean_kwargs, deterministic_hash=clean_hash)
    tainted_snap = contracts_mod.AppOutputSnapshot(
        app_id=app_id, scenario_id=scenario.scenario_id, x3_disposition="X3B_ESCALATE_HITL",
        output={"other_key": bad_body + (" filler" * 80)},
        claims=[{"id": "c1", "supported": False, "source_ids": []}],
        artifacts=[], provenance={"evidence_refs": []},
        side_effects={"writes": ["unauthorized_write.json"], "product_state_mutated": True},
        deterministic_hash="tampered_hash_000",
    )
    for grader in graders_mod.build_default_graders():
        pos, neg = grader.grade(fixture, clean_snap), grader.grade(fixture, tainted_snap)
        if not pos.passed or neg.passed:
            errs.append(f"{grader.grader_id} failed behavioral pass/fail probe for {app_id} (pos={pos.passed}, neg={neg.passed})")
    return errs


def _run_live_apps_eval_probes(repo_root: Path) -> list[str]:
    """Execute live behavioral probes against apps_eval graders, adapters, registries, and L6 claim ladder."""
    import tempfile

    violations: list[str] = []
    if not (repo_root / "apps_eval" / "graders" / "deterministic" / "core.py").is_file():
        return violations

    mod_paths = {
        "contracts": "apps_eval/contracts/models.py",
        "graders": "apps_eval/graders/deterministic/core.py",
        "ladder": "apps_eval/l6_eval_ladder.py",
        "loader": "apps_eval/registry/loader.py",
        "lic_adapter": "apps_eval/adapters/outreach_engine.py",
        "rg_adapter": "apps_eval/adapters/resume_graph_engine.py",
        "bridge": "apps_eval/l6_shadow_bridge.py",
        "render": "apps_eval/outputs/render.py",
        "trends": "apps_eval/trends.py",
        "scenarios": "apps_eval/scenarios.py",
    }
    loaded: dict[str, Any] = {}
    for key, rel_p in mod_paths.items():
        mod, err = load_repo_module(repo_root, rel_p)
        if err or mod is None:
            violations.append(f"{rel_p}: failed loading live evaluator module ({err})")
            return violations
        loaded[key] = mod
    contracts_mod, graders_mod = loaded["contracts"], loaded["graders"]
    ladder_mod, loader_mod = loaded["ladder"], loaded["loader"]
    lic_adapter, rg_adapter = loaded["lic_adapter"], loaded["rg_adapter"]
    bridge_mod, render_mod, trends_mod, scenarios_mod = loaded["bridge"], loaded["render"], loaded["trends"], loaded["scenarios"]

    try:
        default_graders = graders_mod.build_default_graders()
        if len(default_graders) != 11:
            violations.append(f"build_default_graders() returned {len(default_graders)} graders (expected 11)")

        violations.extend(_probe_app_graders(
            contracts_mod, graders_mod, "apps_lic",
            "Grounded executive outreach note referencing verified transformation scope.",
            "This outreach message promises a guaranteed_offer immediately.",
        ))
        violations.extend(_probe_app_graders(
            contracts_mod, graders_mod, "apps_rg",
            "Led enterprise platform transformation delivering measurable latency gains across 18 services.",
            "Resume headline promising a guaranteed_offer upon submission.",
        ))

        if not callable(getattr(lic_adapter, "run_apps_lic_live", None)):
            violations.append("apps_eval/adapters/outreach_engine.py missing callable run_apps_lic_live")
        if not callable(getattr(rg_adapter, "run_apps_rg_live", None)) or not callable(
            getattr(rg_adapter, "build_source_artifact_manifest", None)
        ):
            violations.append("apps_eval/adapters/resume_graph_engine.py missing callable run_apps_rg_live")

        fake_lane_claim = ladder_mod.build_l6_eval_execution_receipt(
            eval_level="LANE", deterministic_only=True, writer_live=False, graders_live=False
        )
        if fake_lane_claim.execution_claim_status != "FAIL":
            violations.append("build_l6_eval_execution_receipt failed to block deterministic LANE claim")

        apps_reg, graders_reg = loader_mod.load_apps_registry(), loader_mod.load_graders_registry()
        if set(apps_reg) != {"apps_rg", "apps_lic"} or len(graders_reg) < 11:
            violations.append("apps_eval registry loader returned incomplete apps or graders registry")

        with tempfile.TemporaryDirectory(prefix="eval_probe_l6_") as td:
            td_path = Path(td)
            drv_payload = bridge_mod.emit_driver_l6_shadow_bridge(
                td_path, eval_id="eval_probe_1",
                app_scorecards=[{"suite_id": "apps_rg.dev.smoke", "score": 1.0}],
                output_refs={"eval_record": "eval_record.json"},
            )
            bridge_file = Path(drv_payload["l6_shadow_bridge"])
            if not bridge_file.is_file():
                violations.append("emit_driver_l6_shadow_bridge failed to write l6_shadow_bridge.json")
            else:
                bdoc = json.loads(bridge_file.read_text(encoding="utf-8"))
                if bdoc.get("current_run_mutated") is not False or bdoc.get("future_run_only") is not True:
                    violations.append("l6_shadow_bridge violated non-mutation / future_run_only invariant")

            sample_sc = contracts_mod.Scorecard(
                suite_id="apps_rg.dev.smoke", app_id="apps_rg", scenario_count=1, finding_count=11,
                passed_findings=11, failed_findings=0, block_failures=0, score=1.0,
                verdict="pass", dimension_scores={"grounding": 1.0},
            )
            sample_reg = contracts_mod.RegressionSummary(
                compared=True, current_score=1.0, baseline_score=0.98, delta=0.02, verdict="improved"
            )
            rec_base: dict[str, Any] = {
                "suite_id": "apps_rg.dev.smoke", "app_id": "apps_rg", "mode": "snapshot",
                "deterministic_only": True, "scenario_results": [{"scenario_id": "scn_1", "passed": True, "failed_findings": 0}],
                "scorecard": sample_sc, "regression": sample_reg, "artifact_paths": {}, "rubric_ids": ["rub_1"],
            }
            sample_rec = contracts_mod.CompletedEvalRecord(record_id="rec_probe_1", created_at="2026-11-03T00:00:00Z", **rec_base)
            rendered_md = render_mod.render_report(sample_rec, [])
            if "# apps_eval report: apps_rg.dev.smoke" not in rendered_md or "Verdict: `pass`" not in rendered_md:
                violations.append("apps_eval/outputs/render.py failed to render CompletedEvalRecord report")

            for r_id, ts in (("run1", "2026-11-03T00:00:00Z"), ("run2", "2026-11-03T01:00:00Z")):
                rdir = td_path / "records" / r_id
                rdir.mkdir(parents=True, exist_ok=True)
                rec_obj = contracts_mod.CompletedEvalRecord(record_id=f"rec_{r_id}", created_at=ts, **rec_base)
                (rdir / "eval_record.json").write_text(json.dumps(rec_obj.to_dict()), encoding="utf-8")
            gate_dec = trends_mod.emit_release_gate(
                records_root=td_path / "records", app_id="apps_rg", out_dir=td_path / "trends_out", emit_l6_shadow=True
            )
            if gate_dec.status != "pass" or gate_dec.sample_count != 2:
                violations.append(f"apps_eval/trends.py emit_release_gate failed clean 2-sample approval: {gate_dec.status}")

        cent_file = repo_root / "config" / "governance" / "centralization_registry.yaml"
        if cent_file.is_file():
            cent_doc = yaml.safe_load(cent_file.read_text(encoding="utf-8")) or {}
            owners = cent_doc.get("domain_threshold_owners") or {}
            exec_max = int(((owners.get("resume_executive_summary_shape") or {}).get("canonical_symbols") or {}).get("EXEC_SUMMARY_MAX_WORDS", 150))
            rg_exp = scenarios_mod._apps_rg_expectations()
            if int((rg_exp.get("length_bounds") or {}).get("max_words", 0)) < exec_max:
                violations.append("apps_eval/scenarios.py _apps_rg_expectations length_bounds.max_words below EXEC_SUMMARY_MAX_WORDS")

        qrel_mod, qrel_err = load_repo_module(repo_root, "resume_graph_engine/src/apps_rg/evals/owner_solo/c03_rendered_unit_qrel.py")
        if qrel_err or qrel_mod is None:
            violations.append(f"c03_rendered_unit_qrel.py failed to load: {qrel_err}")
        else:
            q_contract = qrel_mod.load_contract(repo_root)
            if q_contract.get("status") != "FROZEN":
                violations.append("c03_rendered_unit_qrel contract status is not FROZEN")

        seal_py = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "evals" / "c03_human_eval" / "seal_records.py"
        if seal_py.is_file() and 'if __name__ == "__main__":' not in seal_py.read_text(encoding="utf-8"):
            violations.append("c03_human_eval/seal_records.py missing __main__ CLI entrypoint")
    except Exception as exc:  # guardian: allow-broad-exception -- fail-closed live evaluator probe harness
        violations.append(f"Live apps_eval behavioral probe raised error: {exc}")

    return violations


def _validate_exit_and_domain_rubrics(repo_root: Path) -> tuple[int, list[str]]:
    """Validate exit-eval rubrics and domain rubrics across all 5 configuration roots."""
    violations: list[str] = []
    count = 0

    for rub_rel in ("config/exit_eval_rubrics", "resume_graph_engine/config/exit_eval_rubrics"):
        rubrics_dir = repo_root / rub_rel
        if not rubrics_dir.is_dir():
            continue
        for yf in sorted(rubrics_dir.glob("*.yaml")):
            if yf.name.startswith("_"):
                continue
            count += 1
            rel = str(yf.relative_to(repo_root))
            try:
                doc = yaml.safe_load(yf.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
                violations.append(f"{rel}: YAML parse error: {exc}")
                continue
            if not isinstance(doc, dict):
                violations.append(f"{rel}: rubric root must be a mapping")
                continue

            if "aggregate_threshold" in doc:
                agg = float(doc["aggregate_threshold"])
                if not (0.0 <= agg <= 1.0):
                    violations.append(f"{rel}: aggregate_threshold {agg} outside [0.0, 1.0]")

            dims = doc.get("dimensions")
            if not isinstance(dims, list) or not dims:
                violations.append(f"{rel}: missing non-empty dimensions list")
                continue

            weight_sum = 0.0
            has_weights = False
            for dim in dims:
                if not isinstance(dim, dict):
                    continue
                dname = str(dim.get("name", "<unnamed>"))
                scale = dim.get("scale")
                if isinstance(scale, list) and len(scale) == 2:
                    lo, hi = float(scale[0]), float(scale[1])
                    if lo < 0.0 or hi > 1.0 or lo >= hi:
                        violations.append(f"{rel}::{dname}: invalid normalized scale {scale} (expected [0.0, 1.0])")
                if "threshold" in dim:
                    thr = float(dim["threshold"])
                    if not (0.0 <= thr <= 1.0):
                        violations.append(f"{rel}::{dname}: threshold {thr} outside [0.0, 1.0]")
                if "weight" in dim:
                    has_weights = True
                    w = float(dim["weight"])
                    if not (0.0 <= w <= 1.0):
                        violations.append(f"{rel}::{dname}: weight {w} outside [0.0, 1.0]")
                    weight_sum += w

            if doc.get("composition") == "weighted" and has_weights and abs(weight_sum - 1.0) > 1e-6:
                violations.append(f"{rel}: weighted dimensions sum to {weight_sum:.4f} != 1.0")

    # Validate outreach_engine/config/rubrics/*.yaml
    outreach_rub_dir = repo_root / "outreach_engine" / "config" / "rubrics"
    if outreach_rub_dir.is_dir():
        for yf in sorted(outreach_rub_dir.glob("*.yaml")):
            count += 1
            rel = str(yf.relative_to(repo_root))
            try:
                doc = yaml.safe_load(yf.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
                violations.append(f"{rel}: YAML parse error: {exc}")
                continue
            if not isinstance(doc, dict) or not doc.get("rubric_id"):
                violations.append(f"{rel}: missing rubric_id")
                continue
            prev_min = -1.0
            for band in doc.get("score_bands") or []:
                if isinstance(band, dict) and "min_score" in band:
                    ms = float(band["min_score"])
                    if not (0.0 <= ms <= 1.0) or ms < prev_min:
                        violations.append(f"{rel}: invalid or non-monotonic score_bands min_score {ms}")
                    prev_min = ms
            lenses = doc.get("lenses")
            if isinstance(lenses, dict) and lenses:
                wsum = 0.0
                for lname, lcfg in lenses.items():
                    if not isinstance(lcfg, dict):
                        continue
                    w, thr = float(lcfg.get("weight", 0.0)), float(lcfg.get("threshold", 0.0))
                    if not (0.0 <= w <= 1.0) or not (0.0 <= thr <= 1.0):
                        violations.append(f"{rel}::{lname}: lens weight/threshold outside [0.0, 1.0]")
                    wsum += w
                if abs(wsum - 1.0) > 1e-6:
                    violations.append(f"{rel}: outreach lenses weights sum to {wsum:.4f} != 1.0")

    apps_eval_rub_dir = repo_root / "apps_eval" / "rubrics"
    if apps_eval_rub_dir.is_dir():
        for yf in sorted(apps_eval_rub_dir.glob("*.yaml")):
            count += 1
            rel = str(yf.relative_to(repo_root))
            try:
                doc = yaml.safe_load(yf.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
                violations.append(f"{rel}: YAML parse error: {exc}")
                continue
            if not isinstance(doc, dict) or not isinstance(doc.get("dimensions"), list):
                violations.append(f"{rel}: missing dimensions list")
                continue
            wsum = 0.0
            for dim in doc["dimensions"]:
                if not isinstance(dim, dict):
                    continue
                did, w = str(dim.get("id", "<unnamed>")), float(dim.get("weight", 0.0))
                if not (0.0 <= w <= 1.0):
                    violations.append(f"{rel}::{did}: weight {w} outside [0.0, 1.0]")
                if dim.get("informational_only") is True and w > 0.0:
                    violations.append(f"{rel}::{did}: informational_only dimension must have weight 0.0, got {w}")
                wsum += w
            if abs(wsum - 1.0) > 1e-6:
                violations.append(f"{rel}: rubric dimensions sum to {wsum:.4f} != 1.0")

    res_rub = repo_root / "apps_research" / "config" / "domain_contract" / "eval_rubrics.yaml"
    if res_rub.is_file():
        count += 1
        rel = str(res_rub.relative_to(repo_root))
        try:
            items = yaml.safe_load(res_rub.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            violations.append(f"{rel}: YAML parse error: {exc}")
            items = None
        if not isinstance(items, list) or not items:
            violations.append(f"{rel}: expected non-empty list of eval rubrics")
        else:
            for item in (it for it in items if isinstance(it, dict)):
                rid, wsum = str(item.get("eval_rubric_id", "<unnamed>")), 0.0
                for sdim in (sd for sd in (item.get("score_dimensions") or []) if isinstance(sd, dict)):
                    w, mrs = float(sdim.get("weight", 0.0)), float(sdim.get("min_required_score", 0.0))
                    if not (0.0 <= w <= 1.0) or not (0.0 <= mrs <= 1.0):
                        violations.append(f"{rel}::{rid}: score_dimension weight/min_required_score outside [0.0, 1.0]")
                    wsum += w
                if abs(wsum - 1.0) > 1e-6:
                    violations.append(f"{rel}::{rid}: score_dimensions weights sum to {wsum:.4f} != 1.0")

    return count, violations


def _validate_judge_rubrics_and_profiles(repo_root: Path) -> list[str]:
    """Validate judge rubric banks and approved model pins across all 5 config roots."""
    violations: list[str] = []
    for j_rel in ("config/judges/rubrics.yaml", "resume_graph_engine/config/judges/rubrics.yaml"):
        j_rubric = repo_root / j_rel
        if not j_rubric.is_file():
            continue
        try:
            doc = yaml.safe_load(j_rubric.read_text(encoding="utf-8")) or {}
            for dname, cfg in (doc.get("dimensions") or {}).items():
                if not isinstance(cfg, dict):
                    continue
                smin, smax = float(cfg.get("scale_min", 1)), float(cfg.get("scale_max", 5))
                warn_t, pass_t = float(cfg.get("warn_threshold", smin)), float(cfg.get("pass_threshold", smax))
                ubudget = float(cfg.get("unknown_budget", 0.0))
                if not (smin <= warn_t <= pass_t <= smax):
                    violations.append(f"{j_rel}::{dname}: invalid threshold ordering ({smin} <= {warn_t} <= {pass_t} <= {smax})")
                if not (0.0 <= ubudget <= 1.0):
                    violations.append(f"{j_rel}::{dname}: unknown_budget {ubudget} outside [0.0, 1.0]")
        except (OSError, yaml.YAMLError, ValueError, TypeError) as exc:
            violations.append(f"{j_rel}: failed parsing judge rubrics: {exc}")

    approved = load_approved_provider_models(repo_root)
    if not approved:
        return violations

    prof_path = repo_root / "config" / "provider_profiles.yaml"
    if prof_path.is_file():
        doc = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
        for tier, pmap in (doc.get("judge_models") or {}).items():
            if isinstance(pmap, dict):
                for prov, mid in pmap.items():
                    if str(mid).lower() not in approved:
                        violations.append(f"config/provider_profiles.yaml::judge_models.{tier}.{prov}: unapproved '{mid}'")

    for rel_p, top_key in (
        ("outreach_engine/config/provider_profiles.yaml", "profiles"),
        ("apps_research/config/domain_contract/provider_profile.company_brief.v1.yaml", "approved_model_lanes"),
    ):
        fp = repo_root / rel_p
        if fp.is_file():
            doc = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
            for kname, kcfg in (doc.get(top_key) or {}).items() if isinstance(doc.get(top_key), dict) else ():
                if isinstance(kcfg, dict) and kcfg.get("model") and str(kcfg["model"]).lower() not in approved:
                    violations.append(f"{rel_p}::{kname}: unapproved '{kcfg['model']}'")

    apps_eval_rub_dir = repo_root / "apps_eval" / "rubrics"
    if apps_eval_rub_dir.is_dir():
        for yf in sorted(apps_eval_rub_dir.glob("*.yaml")):
            doc = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
            pin = (doc.get("judge_model_pin") or {}) if isinstance(doc, dict) else {}
            if isinstance(pin, dict) and pin.get("model") and str(pin["model"]).lower() not in approved:
                violations.append(f"{yf.relative_to(repo_root)}::judge_model_pin: unapproved '{pin['model']}'")

    res_jprof = repo_root / "apps_research" / "config" / "domain_contract" / "judge_profile.company_brief.v1.yaml"
    if res_jprof.is_file():
        doc = yaml.safe_load(res_jprof.read_text(encoding="utf-8")) or {}
        hj = (doc.get("apps_rg_handoff_judge") or {}) if isinstance(doc, dict) else {}
        if isinstance(hj, dict) and hj.get("model") and str(hj["model"]).lower() not in approved:
            violations.append(f"{res_jprof.relative_to(repo_root)}::apps_rg_handoff_judge: unapproved '{hj['model']}'")

    return violations


_RUNTIME_CACHE_DIR_PARTS: frozenset[str] = frozenset({"cache", "__pycache__", ".pytest_cache", ".ruff_cache"})
_RUNTIME_BINARY_SIDE_SUFFIXES: tuple[str, ...] = ("-wal", "-shm", "-journal", ".sqlite", ".sqlite3", ".db", ".bin", ".lock")


def _validate_data_holdout_surface(repo_root: Path) -> tuple[int, dict[str, int], list[str]]:
    """Validate structural integrity across all 3 data roots (`data`, `outreach_engine/data`, `resume_graph_engine/data`)."""
    violations: list[str] = []
    file_count = 0
    counts_by_root: dict[str, int] = {}

    for d_rel in DATA_ROOTS:
        data_dir = repo_root / d_rel
        if not data_dir.is_dir():
            continue
        root_count = 0
        for fp in sorted(data_dir.rglob("*")):
            if not fp.is_file() or fp.is_symlink():
                continue
            rel_parts = fp.relative_to(data_dir).parts
            if any(part in _RUNTIME_CACHE_DIR_PARTS for part in rel_parts[:-1]) or fp.name.endswith(
                _RUNTIME_BINARY_SIDE_SUFFIXES
            ):
                continue
            file_count += 1
            root_count += 1
            if fp.name == ".gitkeep":
                continue
            rel = str(fp.relative_to(repo_root))
            if fp.stat().st_size == 0:
                violations.append(f"{rel}: empty benchmark/holdout data file")
                continue
            try:
                if fp.suffix == ".json":
                    json.loads(fp.read_text(encoding="utf-8"))
                elif fp.suffix == ".jsonl":
                    for line in fp.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            json.loads(line)
                elif fp.suffix in (".yaml", ".yml"):
                    yaml.safe_load(fp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
                violations.append(f"{rel}: malformed dataset payload ({exc})")
        counts_by_root[d_rel] = root_count

    return file_count, counts_by_root, violations


def validate_eval_rubrics(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Audits evaluation modules, schemas, live graders, rubrics, judge profiles, holdouts, and purity."""
    root = repo_root.resolve()
    violations: list[str] = []

    if not (root / "tests").is_dir():
        violations.append("Missing mandatory tests/ directory for evaluation verification.")

    eval_mod_count, schema_count, mod_errs = _validate_eval_modules_ast_and_schemas(root)
    violations.extend(mod_errs)
    violations.extend(_run_live_apps_eval_probes(root))

    exit_rubric_count, rubric_errs = _validate_exit_and_domain_rubrics(root)
    violations.extend(rubric_errs)
    violations.extend(_validate_judge_rubrics_and_profiles(root))

    data_file_count, data_counts_by_root, data_errs = _validate_data_holdout_surface(root)
    violations.extend(data_errs)

    purity_errs: list[str] = []
    for prod_dir in PRODUCTION_DIRECTORIES:
        d = root / prod_dir
        if d.exists():
            for py in sorted(d.rglob("*.py")):
                for lineno, cat, msg in check_file_production_purity(py, root):
                    purity_errs.append(f"{py.relative_to(root)}:{lineno}: [{cat}] {msg}")
    violations.extend(purity_errs)

    is_clean = len(violations) == 0
    return {
        "status": "PASS" if is_clean else "FAIL", "is_clean": is_clean,
        "config_roots_audited": [r for r in CONFIG_ROOTS if (root / r).is_dir()],
        "eval_module_count": eval_mod_count, "validated_schema_count": schema_count,
        "exit_rubric_count": exit_rubric_count, "data_file_count": data_file_count,
        "data_counts_by_root": data_counts_by_root, "purity_violation_count": len(purity_errs),
        "violations": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agents evaluation rubrics, judge bounds, and holdout data.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    rep = validate_eval_rubrics(args.repo_root.resolve())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(f"[{rep['status']}] Validated {rep['eval_module_count']} eval modules, {rep['validated_schema_count']} schemas, {rep['exit_rubric_count']} rubrics, and {rep['data_file_count']} data files ({len(rep['violations'])} violations).")
    return 0 if rep["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
