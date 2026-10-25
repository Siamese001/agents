"""Single unified CLI entrypoint for the governed resume pipeline.

Supports canonical subcommands:
  - run: Execute the canonical resume pipeline
  - eval: Re-evaluate an existing run without provider calls
  - show: Print an exact output artifact from a completed run
  - bootstrap: Materialize and index fact vectors
  - patch-run: Re-dispatch only failed lanes of an existing run
  - preflight: Validate provider API credentials and live readiness
  - models: Inspect resolved roles, model pins, and catalog digest
  - cache: Inspect application and semantic cache status
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from resume_engine.cli_inspectors import (
    handle_cache as _handle_cache,
    handle_models as _handle_models,
    terminate_cli_cleanly,
)

DEFAULT_TARGET_COMPANY = "Anthropic"
DEFAULT_TARGET_ROLE = "Manager of Applied AI Architecture, Partnerships"


def _build_parser(prog: str = "python -m resume_engine") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "The single governed resume pipeline. Run the full live product flow, "
            "inspect a completed run, print artifacts, manage models, and verify preflight."
        ),
    )
    parser.add_argument("--version", action="version", version="resume_engine 1.0.0")
    parser.add_argument(
        "--l1-cognitive-treatment-arm",
        default="l1_v2_control",
        help="Apps RG-local experiment arm assignment.",
    )
    subparsers = parser.add_subparsers(dest="action", metavar="ACTION")

    # 1. run
    run_parser = subparsers.add_parser("run", help="run the canonical resume pipeline")
    run_parser.add_argument("--target-company", default=DEFAULT_TARGET_COMPANY)
    run_parser.add_argument("--target-role", default=DEFAULT_TARGET_ROLE)
    run_parser.add_argument(
        "--jd",
        default="",
        help="Optional JD file path or inline text. Defaults to canonical Anthropic JD.",
    )
    run_parser.add_argument(
        "--resume",
        default="",
        help="Optional base-resume JSON, Markdown, or text path. Defaults to canonical base resume.",
    )
    run_parser.add_argument(
        "--artifact-dir",
        default="",
        help="Optional fresh output directory beneath artifacts/apps_rg/runtime_proofs.",
    )
    run_parser.add_argument(
        "--briefing",
        default="",
        help="Optional briefing file path or inline text.",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit structured JSON output containing status, evaluation, and runtime details.",
    )

    # 2. eval
    eval_parser = subparsers.add_parser(
        "eval", help="re-evaluate an existing run without a provider call"
    )
    eval_parser.add_argument(
        "--run-dir", required=True, help="Completed run directory."
    )

    # 3. show
    show_parser = subparsers.add_parser(
        "show", help="print an exact output artifact from a completed run"
    )
    show_parser.add_argument(
        "--run-dir", required=True, help="Completed run directory."
    )
    show_parser.add_argument(
        "--artifact",
        required=True,
        choices=("resume", "email", "research", "summary", "evaluation"),
        help="Artifact to print exactly.",
    )

    # 4. bootstrap
    bootstrap_parser = subparsers.add_parser(
        "bootstrap", help="materialize and index fact vectors"
    )
    bootstrap_parser.add_argument(
        "bootstrap_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to fact_vectors_bootstrap CLI.",
    )

    # 5. patch-run
    patch_parser = subparsers.add_parser(
        "patch-run", help="re-dispatch only failed lanes of an existing run"
    )
    patch_parser.add_argument(
        "--run-dir",
        default="",
        help="Run directory to patch.",
    )
    patch_parser.add_argument(
        "patch_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments forwarded to patch_run.",
    )

    # 6. preflight
    preflight_parser = subparsers.add_parser(
        "preflight", help="validate provider credentials and live execution readiness"
    )
    preflight_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit structured JSON preflight status.",
    )

    # 7. models
    models_parser = subparsers.add_parser(
        "models", help="inspect resolved roles, pins, and catalog digest (read-only)"
    )
    models_parser.add_argument(
        "--role",
        default="",
        help="Optional specific role or section to inspect.",
    )
    models_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit structured JSON output.",
    )

    # 8. cache
    cache_parser = subparsers.add_parser(
        "cache", help="inspect briefing and vector cache status (read-only)"
    )
    cache_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit structured JSON output.",
    )

    # 9. doctor
    doctor_parser = subparsers.add_parser(
        "doctor", help="fresh-checkout preflight diagnostics"
    )
    doctor_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any required prerequisite is missing.",
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a table.",
    )
    doctor_parser.add_argument(
        "doctor_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments forwarded to doctor CLI.",
    )

    return parser


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        return ["run"]
    if values[0] in {"-h", "--help", "-v", "--version"}:
        return values

    if values[0] == "--patch-run" or values[0].startswith("--patch-run="):
        if values[0] == "--patch-run":
            target = values[1] if len(values) > 1 else ""
            remainder = values[2:] if len(values) > 2 else []
            return ["patch-run", "--run-dir", target, *remainder]
        target = values[0].split("=", 1)[1]
        return ["patch-run", "--run-dir", target, *values[1:]]

    known_actions = {
        "run",
        "eval",
        "show",
        "bootstrap",
        "patch-run",
        "preflight",
        "models",
        "cache",
        "doctor",
    }
    if values[0] not in known_actions and values[0].startswith("-"):
        return ["run", *values]
    return values


def _enforce_gate_order(
    prog: str,
    args: argparse.Namespace,
    *,
    requires_preflight: bool = False,
) -> int | None:
    """Enforce mandatory gate order across all subcommands."""
    from apps_rg.runtime.env_bootstrap import (
        apply_route_signing_posture,
        bootstrap_apps_rg_env,
    )
    from apps_rg.runtime.live_judge_only_guard import assert_production_runtime

    bootstrap_apps_rg_env()
    if getattr(args, "action", "") in {"run", "patch-run"} or not getattr(args, "action", ""):
        os.environ.setdefault("APPS_RG_ROUTE_SIGNING_POSTURE", "ephemeral_dev")
    apply_route_signing_posture()

    if requires_preflight:
        assert_production_runtime(context=prog, args=args)
        from apps_rg.__main__ import _run_preflight

        json_out = getattr(args, "json", False)
        pf = _run_preflight(prog, json_out=json_out)
        if pf is not None:
            return pf
    return None


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    """Sole public unified CLI entrypoint for resume_engine."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)

    if prog is None:
        if len(sys.argv) > 0 and "resume_engine" in sys.argv[0]:
            prog = "python -m resume_engine"
        elif len(sys.argv) > 0 and "apps_rg" in sys.argv[0]:
            prog = "python -m apps_rg"
        elif len(sys.argv) > 0 and "resume_graph_engine" in sys.argv[0]:
            prog = "python -m resume_graph_engine"
        else:
            prog = "resume-engine"

    normalized = _normalize_argv(raw_argv)
    parser = _build_parser(prog=prog)
    args = parser.parse_args(normalized)

    action = getattr(args, "action", "") or "run"

    is_provider_action = action in {"run", "bootstrap", "patch-run", "preflight"}
    gate_rc = _enforce_gate_order(prog, args, requires_preflight=is_provider_action)
    if gate_rc is not None:
        return gate_rc

    if action == "run":
        from apps_rg.__main__ import (
            _print_json_result,
            _print_result,
            _run_product_from_cli,
        )

        result = _run_product_from_cli(args)
        if getattr(args, "json", False):
            _print_json_result(result)
        else:
            _print_result(result)
        return 0 if result.get("status") == "SUCCESS" else 1

    if action == "eval":
        from apps_rg.__main__ import _evaluate_product_run, _print_evaluation

        run_path = Path(args.run_dir).expanduser().resolve()
        report = _evaluate_product_run(run_path)
        report["run_dir"] = str(run_path)
        _print_evaluation(report)
        return 0 if report.get("status") == "PASS" else 1

    if action == "show":
        from apps_rg.__main__ import _read_product_artifact

        run_path = Path(args.run_dir).expanduser().resolve()
        content = _read_product_artifact(run_path, args.artifact)
        sys.stdout.write(content)
        return 0

    if action == "bootstrap":
        from apps_rg.runtime.fact_vectors_bootstrap import run_bootstrap_cli

        sub_args = getattr(args, "bootstrap_args", [])
        return int(run_bootstrap_cli(sub_args))

    if action == "patch-run":
        from apps_rg.runtime.orchestration.patch_run import main as patch_main

        run_dir = getattr(args, "run_dir", "")
        extra_args = list(getattr(args, "patch_args", []))
        call_args: list[str] = []
        if run_dir:
            call_args.append(run_dir)
        call_args.extend(extra_args)
        return patch_main(call_args)

    if action == "preflight":
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "message": "Preflight credentials and live readiness validated.",
                    },
                    indent=2,
                )
            )
        else:
            print(f"[{prog}] Preflight check PASSED.")
        return 0

    if action == "models":
        return _handle_models(args)

    if action == "cache":
        return _handle_cache(args)

    if action == "doctor":
        from apps_rg.runtime.doctor import run_doctor_cli

        sub_args: list[str] = []
        if getattr(args, "strict", False):
            sub_args.append("--strict")
        if getattr(args, "json", False):
            sub_args.append("--json")
        extra = getattr(args, "doctor_args", [])
        if extra:
            sub_args.extend(list(extra))
        return int(run_doctor_cli(sub_args))

    parser.error(f"unsupported action: {action!r}")
    return 2


if __name__ == "__main__":
    terminate_cli_cleanly(main())
