"""Helper routines for tools/validate_eval_rubrics.py."""
from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path
from typing import Any

import yaml  # type: ignore
from jsonschema import Draft202012Validator  # type: ignore
from jsonschema.exceptions import SchemaError  # type: ignore
from tools.cost_token_budget_probes import load_repo_module

CONFIG_ROOTS: tuple[str, ...] = (
    "config",
    "outreach_engine/config",
    "apps_eval",
    "apps_research/config",
    "resume_graph_engine/config",
)
DATA_ROOTS: tuple[str, ...] = ("data", "outreach_engine/data", "resume_graph_engine/data")
_DEF_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.ImportFrom,
    ast.Import,
    ast.Assign,
    ast.AnnAssign,
)


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


def _probe_app_graders(
    contracts_mod: Any, graders_mod: Any, app_id: str, clean_body: str, bad_body: str
) -> list[str]:
    errs: list[str] = []
    all_grader_ids = (
        "schema",
        "artifact_presence",
        "x3_disposition",
        "forbidden_content",
        "grounded_claim",
        "provenance",
        "section_structure",
        "length_bounds",
        "side_effect",
        "escalation",
        "determinism",
    )
    scenario = contracts_mod.EvalScenario(
        scenario_id=f"scn_live_probe_{app_id}",
        suite_id="suite_probe",
        app_id=app_id,
        description=f"Live deterministic grader probe for {app_id}",
        fixture_path="probe.json",
        graders=all_grader_ids,
        rubric_id=f"rub_probe_{app_id}",
    )
    provenance = contracts_mod.FixtureProvenance(
        scenario_id=f"scn_live_probe_{app_id}", fixture_path="probe.json"
    )
    fixture = contracts_mod.EvalFixture(
        scenario=scenario,
        input_dir=".",
        expected_dir=".",
        snapshot_path="probe.json",
        artifacts_dir=".",
        expected={
            "required_output_keys": ["draft", "sections"],
            "required_artifacts": ["final_artifact.json"],
            "expected_x3": "APPROVE",
            "forbidden_terms": ["guaranteed_offer"],
            "grounded_claims_required": True,
            "required_provenance": ["ev_ref_1"],
            "required_sections": ["summary"],
            "length_bounds": {"min_words": 5, "max_words": 60},
            "allow_side_effects": False,
            "escalation_required": False,
        },
        provenance=provenance,
    )
    clean_kwargs: dict[str, Any] = {
        "app_id": app_id,
        "scenario_id": scenario.scenario_id,
        "x3_disposition": "APPROVE",
        "output": {"draft": clean_body, "sections": {"summary": clean_body}},
        "claims": [{"id": "c1", "supported": True, "source_ids": ["src_1"]}],
        "artifacts": ["final_artifact.json"],
        "provenance": {"evidence_refs": ["ev_ref_1"]},
        "side_effects": {"writes": [], "product_state_mutated": False},
    }
    clean_hash = graders_mod._canonical_hash(contracts_mod.AppOutputSnapshot(**clean_kwargs))
    clean_snap = contracts_mod.AppOutputSnapshot(**clean_kwargs, deterministic_hash=clean_hash)
    tainted_snap = contracts_mod.AppOutputSnapshot(
        app_id=app_id,
        scenario_id=scenario.scenario_id,
        x3_disposition="X3B_ESCALATE_HITL",
        output={"other_key": bad_body + (" filler" * 80)},
        claims=[{"id": "c1", "supported": False, "source_ids": []}],
        artifacts=[],
        provenance={"evidence_refs": []},
        side_effects={"writes": ["unauthorized_write.json"], "product_state_mutated": True},
        deterministic_hash="tampered_hash_000",
    )
    for grader in graders_mod.build_default_graders():
        pos, neg = grader.grade(fixture, clean_snap), grader.grade(fixture, tainted_snap)
        if not pos.passed or neg.passed:
            errs.append(
                f"{grader.grader_id} failed behavioral pass/fail probe for {app_id} (pos={pos.passed}, neg={neg.passed})"
            )
    return errs


def _run_live_apps_eval_probes(repo_root: Path) -> list[str]:
    """Execute live behavioral probes against apps_eval graders, adapters, registries, and L6 claim ladder."""
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
    bridge_mod, render_mod, trends_mod, scenarios_mod = (
        loaded["bridge"],
        loaded["render"],
        loaded["trends"],
        loaded["scenarios"],
    )

    try:
        default_graders = graders_mod.build_default_graders()
        if len(default_graders) != 11:
            violations.append(f"build_default_graders() returned {len(default_graders)} graders (expected 11)")

        violations.extend(
            _probe_app_graders(
                contracts_mod,
                graders_mod,
                "apps_lic",
                "Grounded executive outreach note referencing verified transformation scope.",
                "This outreach message promises a guaranteed_offer immediately.",
            )
        )
        violations.extend(
            _probe_app_graders(
                contracts_mod,
                graders_mod,
                "apps_rg",
                "Led enterprise platform transformation delivering measurable latency gains across 18 services.",
                "Resume headline promising a guaranteed_offer upon submission.",
            )
        )

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
                td_path,
                eval_id="eval_probe_1",
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

            sample_reg = contracts_mod.RegressionSummary(
                compared=True, current_score=1.0, baseline_score=0.98, delta=0.02, verdict="improved"
            )
            for app_id, suite_id in (("apps_rg", "apps_rg.dev.smoke"), ("apps_lic", "apps_lic.dev.smoke")):
                sc = contracts_mod.Scorecard(
                    suite_id=suite_id,
                    app_id=app_id,
                    scenario_count=1,
                    finding_count=11,
                    passed_findings=11,
                    failed_findings=0,
                    block_failures=0,
                    score=1.0,
                    verdict="pass",
                    dimension_scores={"grounding": 1.0},
                )
                rbase: dict[str, Any] = {
                    "suite_id": suite_id,
                    "app_id": app_id,
                    "mode": "snapshot",
                    "deterministic_only": True,
                    "scenario_results": [
                        {"scenario_id": f"scn_{app_id}_1", "passed": True, "failed_findings": 0}
                    ],
                    "scorecard": sc,
                    "regression": sample_reg,
                    "artifact_paths": {},
                    "rubric_ids": ["rub_1"],
                }
                rec = contracts_mod.CompletedEvalRecord(
                    record_id=f"rec_{app_id}_1", created_at="2026-11-03T00:00:00Z", **rbase
                )
                md = render_mod.render_report(rec, [])
                if f"# apps_eval report: {suite_id}" not in md or "Verdict: `pass`" not in md:
                    violations.append(f"apps_eval/outputs/render.py failed to render {app_id} report")
                for r_id, ts in (("run1", "2026-11-03T00:00:00Z"), ("run2", "2026-11-03T01:00:00Z")):
                    rdir = td_path / f"{app_id}_records" / r_id
                    rdir.mkdir(parents=True, exist_ok=True)
                    robj = contracts_mod.CompletedEvalRecord(
                        record_id=f"rec_{app_id}_{r_id}", created_at=ts, **rbase
                    )
                    (rdir / "eval_record.json").write_text(json.dumps(robj.to_dict()), encoding="utf-8")
                gdec = trends_mod.emit_release_gate(
                    records_root=td_path / f"{app_id}_records",
                    app_id=app_id,
                    out_dir=td_path / f"{app_id}_trends",
                    emit_l6_shadow=True,
                )
                if gdec.status != "pass" or gdec.sample_count != 2:
                    violations.append(f"apps_eval/trends.py emit_release_gate failed for {app_id}: {gdec.status}")

        lic_eval_mod, lic_eval_err = load_repo_module(
            repo_root, "outreach_engine/src/apps_lic/judges/evaluator.py"
        )
        if (
            lic_eval_err
            or lic_eval_mod is None
            or not hasattr(lic_eval_mod, "ExecutiveOutreachJudgePanel")
            or not hasattr(lic_eval_mod, "evaluate_x1d_judge_quorum")
            or not hasattr(lic_eval_mod, "GradeOnlyJudgePacket")
        ):
            violations.append(
                f"outreach_engine/src/apps_lic/judges/evaluator.py missing X1D quorum / judge exports: {lic_eval_err}"
            )

        cent_file = repo_root / "config" / "governance" / "centralization_registry.yaml"
        if cent_file.is_file():
            cent_doc = yaml.safe_load(cent_file.read_text(encoding="utf-8")) or {}
            owners = cent_doc.get("domain_threshold_owners") or {}
            exec_max = int(
                (
                    (owners.get("resume_executive_summary_shape") or {}).get("canonical_symbols") or {}
                ).get("EXEC_SUMMARY_MAX_WORDS", 150)
            )
            rg_exp = scenarios_mod._apps_rg_expectations()
            if int((rg_exp.get("length_bounds") or {}).get("max_words", 0)) < exec_max:
                violations.append(
                    "apps_eval/scenarios.py _apps_rg_expectations length_bounds.max_words below EXEC_SUMMARY_MAX_WORDS"
                )

        qrel_mod, qrel_err = load_repo_module(
            repo_root, "resume_graph_engine/src/apps_rg/evals/owner_solo/c03_rendered_unit_qrel.py"
        )
        if qrel_err or qrel_mod is None:
            violations.append(f"c03_rendered_unit_qrel.py failed to load: {qrel_err}")
        else:
            q_contract = qrel_mod.load_contract(repo_root)
            if q_contract.get("status") != "FROZEN":
                violations.append("c03_rendered_unit_qrel contract status is not FROZEN")

        seal_py = (
            repo_root
            / "resume_graph_engine"
            / "src"
            / "apps_rg"
            / "evals"
            / "c03_human_eval"
            / "seal_records.py"
        )
        if seal_py.is_file() and 'if __name__ == "__main__":' not in seal_py.read_text(encoding="utf-8"):
            violations.append("c03_human_eval/seal_records.py missing __main__ CLI entrypoint")
    except Exception as exc:  # guardian: allow-broad-exception -- fail-closed live evaluator probe harness
        violations.append(f"Live apps_eval behavioral probe raised error: {exc}")

    return violations


__all__ = [
    "CONFIG_ROOTS",
    "DATA_ROOTS",
    "_DEF_NODES",
    "_probe_app_graders",
    "_run_live_apps_eval_probes",
    "_validate_eval_modules_ast_and_schemas",
]
