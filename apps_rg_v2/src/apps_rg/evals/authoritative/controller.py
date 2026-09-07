"""Create controller-observed execution receipts by actually launching Apps RG commands."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.evals.repeatability.evaluation import (
    RUN_SCHEMA,
    RUN_SET_SCHEMA,
    scenario_registry_digest,
    seal_run_set,
)
from apps_rg.evals.resume_graph.reporting import canonical_digest

from .artifacts import path_has_symlink_component, seal_record
from .repeatability import (
    CONTROLLER_MANIFEST_SCHEMA,
    CONTROLLER_RECEIPT_SCHEMA,
)

PLAN_SCHEMA = "apps_rg.execution_controller_plan.v1"
_SEMANTIC_FIELDS = (
    "retrieved_candidate_ids",
    "selected_evidence_ids",
    "selected_graph_path_ids",
    "material_claim_ids",
    "bindings",
    "section_decisions",
    "grounding_dispositions",
    "final_disposition",
    "output_quality_scores",
    "output_text_by_section",
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class ControllerExecutionError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_create_once(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)


def _command_tokens(command: Sequence[str], *, input_path: Path, output_path: Path) -> list[str]:
    return [
        str(token).replace("{input}", str(input_path)).replace("{output}", str(output_path))
        for token in command
    ]


def _git_value(workdir: Path, *arguments: str) -> str:
    """Return one Git value from the exact checkout that will run the command."""

    try:
        completed = subprocess.run(
            ["git", "-C", str(workdir), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControllerExecutionError(
            f"unable to inspect controller workdir Git identity: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        raise ControllerExecutionError("controller workdir is not a readable Git checkout")
    return completed.stdout.strip()


def _verified_workdir_identity(workdir: Path, *, source_commit: str) -> dict[str, str]:
    """Prove that the process will execute the plan's exact clean source tree."""

    head_commit = _git_value(workdir, "rev-parse", "HEAD")
    if head_commit != source_commit:
        raise ControllerExecutionError(
            "controller workdir HEAD does not match declared source_commit"
        )
    expected_tree = _git_value(workdir, "rev-parse", f"{source_commit}^{{tree}}")
    head_tree = _git_value(workdir, "rev-parse", "HEAD^{tree}")
    tracked_changes = _git_value(workdir, "status", "--porcelain", "--untracked-files=no")
    if head_tree != expected_tree:
        raise ControllerExecutionError(
            "controller workdir tree does not match declared source_commit"
        )
    if tracked_changes:
        raise ControllerExecutionError("controller workdir has tracked source changes")
    return {
        "source_commit": head_commit,
        "source_tree": head_tree,
        "workdir": str(workdir),
    }


def execute_controller_plan(
    plan: Any,
    *,
    output_root: Path,
    expected_plan_digest: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute every governed scenario and create a run set plus controller manifest."""

    if not isinstance(plan, Mapping) or plan.get("schema_version") != PLAN_SCHEMA:
        raise ControllerExecutionError("controller plan schema mismatch")
    if plan.get("record_digest") != expected_plan_digest:
        raise ControllerExecutionError("controller plan differs from expected digest")
    payload = dict(plan)
    payload.pop("record_digest", None)
    if canonical_digest(payload) != expected_plan_digest:
        raise ControllerExecutionError("controller plan digest mismatch")
    scenarios = plan.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ControllerExecutionError("controller plan scenarios are empty")
    controller_id = str(plan.get("controller_id") or "")
    source_commit = str(plan.get("source_commit") or "")
    evaluation_id = str(plan.get("evaluation_id") or "")
    timeout_seconds = plan.get("timeout_seconds")
    if (
        not controller_id
        or not evaluation_id
        or not _COMMIT.fullmatch(source_commit)
        or not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not 1 <= timeout_seconds <= 3600
    ):
        raise ControllerExecutionError("controller identity, source commit, or timeout is invalid")
    if path_has_symlink_component(output_root.parent):
        raise ControllerExecutionError("controller output root must not use a symlink alias")
    validated_scenarios: list[tuple[Mapping[str, Any], Path, Path, dict[str, str]]] = []
    observed_scenario_ids: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            raise ControllerExecutionError("controller scenario must be an object")
        scenario_id = str(scenario.get("scenario_id") or "")
        raw_input_path = Path(str(scenario.get("input_path") or ""))
        input_path = raw_input_path.resolve()
        command = scenario.get("command")
        execution_count = scenario.get("execution_count")
        raw_workdir = Path(str(scenario.get("workdir") or ""))
        workdir = raw_workdir.resolve()
        if (
            not scenario_id
            or scenario_id in observed_scenario_ids
            or not input_path.is_file()
            or path_has_symlink_component(raw_input_path)
            or not workdir.is_dir()
            or path_has_symlink_component(raw_workdir)
            or not isinstance(command, list)
            or not command
            or any(not isinstance(token, str) or not token for token in command)
            or not isinstance(execution_count, int)
            or isinstance(execution_count, bool)
            or execution_count < 3
        ):
            raise ControllerExecutionError(f"invalid controller scenario: {scenario_id}")
        observed_scenario_ids.add(scenario_id)
        validated_scenarios.append(
            (scenario, input_path, workdir, _verified_workdir_identity(workdir, source_commit=source_commit))
        )

    source_trees = {identity["source_tree"] for _, _, _, identity in validated_scenarios}
    if len(source_trees) != 1:
        raise ControllerExecutionError("controller scenarios resolve to different source trees")
    source_tree = next(iter(source_trees))
    output_root.mkdir(parents=True, exist_ok=False)
    scenario_rows: list[dict[str, Any]] = []
    execution_receipts: list[dict[str, Any]] = []
    for scenario, input_path, workdir, identity in validated_scenarios:
        scenario_id = str(scenario.get("scenario_id") or "")
        command = scenario.get("command")
        execution_count = scenario.get("execution_count")
        assert isinstance(command, list)
        assert isinstance(execution_count, int)
        input_digest = _file_sha256(input_path)
        runs: list[dict[str, Any]] = []
        for index in range(execution_count):
            nonce = secrets.token_hex(32)
            execution_id = f"{scenario_id}-{index + 1}-{nonce[:12]}"
            run_dir = output_root / execution_id
            run_dir.mkdir(exist_ok=False)
            result_path = run_dir / "semantic-result.json"
            tokens = _command_tokens(command, input_path=input_path, output_path=result_path)
            environment = dict(os.environ)
            environment.update(
                {
                    "APPS_RG_EVAL_CONTROLLER_ID": controller_id,
                    "APPS_RG_EVAL_EXECUTION_ID": execution_id,
                    "APPS_RG_EVAL_NONCE": nonce,
                    "APPS_RG_EVAL_INPUT": str(input_path),
                    "APPS_RG_EVAL_OUTPUT": str(result_path),
                    "APPS_RG_EVAL_SOURCE_COMMIT": source_commit,
                }
            )
            started_at = _now()
            try:
                completed = subprocess.run(
                    tokens,
                    cwd=str(workdir),
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=False,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise ControllerExecutionError(
                    f"runtime command timed out for {execution_id}"
                ) from exc
            ended_at = _now()
            if completed.returncode != 0:
                raise ControllerExecutionError(
                    f"runtime command failed for {execution_id}: exit {completed.returncode}"
                )
            try:
                raw_result = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ControllerExecutionError(
                    f"runtime result invalid for {execution_id}: {exc}"
                ) from exc
            if result_path.is_symlink() or not isinstance(raw_result, Mapping) or set(
                raw_result
            ) != set(_SEMANTIC_FIELDS):
                raise ControllerExecutionError(
                    f"runtime result fields differ from semantic contract for {execution_id}"
                )
            if _file_sha256(input_path) != input_digest:
                raise ControllerExecutionError(
                    f"runtime input changed during execution for {execution_id}"
                )
            semantic = {field: raw_result[field] for field in _SEMANTIC_FIELDS}
            semantic_digest = canonical_digest(semantic)
            receipt = seal_record(
                {
                    "schema_version": CONTROLLER_RECEIPT_SCHEMA,
                    "controller_id": controller_id,
                    "controller_nonce": nonce,
                    "execution_id": execution_id,
                    "scenario_id": scenario_id,
                    "source_commit": source_commit,
                    "source_tree": identity["source_tree"],
                    "workdir": identity["workdir"],
                    "input_file_sha256": input_digest,
                    "command_digest": canonical_digest(tokens),
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "runtime_invoked": True,
                    "exit_code": completed.returncode,
                    "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
                    "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
                    "semantic_output_digest": semantic_digest,
                }
            )
            run = {
                "schema_version": RUN_SCHEMA,
                "execution_id": execution_id,
                "execution_receipt_digest": receipt["record_digest"],
                "independent_execution_attested": True,
                **semantic,
                "record_digest": "",
            }
            runs.append(run)
            execution_receipts.append(receipt)
            _write_create_once(run_dir / "execution-receipt.json", receipt)
        scenario_rows.append({"scenario_id": scenario_id, "runs": runs})

    run_set = seal_run_set(
        {
            "schema_version": RUN_SET_SCHEMA,
            "evaluation_id": evaluation_id,
            "scenario_registry_digest": scenario_registry_digest(),
            "scenarios": scenario_rows,
            "bundle_digest": "",
        }
    )
    manifest = seal_record(
        {
            "schema_version": CONTROLLER_MANIFEST_SCHEMA,
            "evaluation_id": evaluation_id,
            "controller_id": controller_id,
            "source_commit": source_commit,
            "source_tree": source_tree,
            "controller_plan_digest": expected_plan_digest,
            "runtime_invoked": True,
            "execution_receipts": execution_receipts,
        }
    )
    _write_create_once(output_root / "repeatability-run-set.json", run_set)
    _write_create_once(output_root / "controller-manifest.json", manifest)
    return run_set, manifest


__all__ = ["ControllerExecutionError", "PLAN_SCHEMA", "execute_controller_plan"]
