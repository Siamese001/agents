"""CLI entrypoint for outreach_engine / apps_lic.

Commands:
    run, patch-run, eval, validate, show, preflight, models, cache, doctor
"""

from __future__ import annotations

import sys
from typing import Sequence

from apps_lic.cli_subcommands.eval_show_validate import (
    _handle_eval,
    _handle_show,
    _handle_validate,
    _reconstruct_eval_context,
    _reconstruct_eval_draft,
)
from apps_lic.cli_subcommands.parity_commands import (
    DoctorCheck,
    _handle_cache,
    _handle_doctor,
    _handle_models,
    _handle_patch_run,
    _handle_preflight,
    run_doctor,
)
from apps_lic.cli_subcommands.parser_and_run import (
    _build_parser,
    _emit_error,
    _handle_run,
    _normalize_argv,
)

cmd_run = _handle_run
cmd_patch_run = _handle_patch_run
cmd_eval = _handle_eval
cmd_show = _handle_show
cmd_validate = _handle_validate
cmd_preflight = _handle_preflight
cmd_models = _handle_models
cmd_cache = _handle_cache
cmd_doctor = _handle_doctor


def main(argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    normalized = _normalize_argv(argv)
    if prog is None:
        prog = "python -m apps_lic" if (len(sys.argv) > 0 and "apps_lic" in sys.argv[0]) else "python -m outreach_engine"
    parser = _build_parser(prog=prog)
    args = parser.parse_args(normalized)
    handlers = {
        "run": lambda: _handle_run(args, prog=prog),
        "patch-run": lambda: _handle_patch_run(args),
        "eval": lambda: _handle_eval(args),
        "show": lambda: _handle_show(args),
        "validate": lambda: _handle_validate(args),
        "preflight": lambda: _handle_preflight(args, prog=prog),
        "models": lambda: _handle_models(args),
        "cache": lambda: _handle_cache(args),
        "doctor": lambda: _handle_doctor(args),
    }
    handler = handlers.get(args.action)
    return handler() if handler else (parser.print_help() or 1)


__all__ = [
    "DoctorCheck",
    "_build_parser",
    "_emit_error",
    "_handle_cache",
    "_handle_doctor",
    "_handle_eval",
    "_handle_models",
    "_handle_patch_run",
    "_handle_preflight",
    "_handle_run",
    "_handle_show",
    "_handle_validate",
    "_normalize_argv",
    "_reconstruct_eval_context",
    "_reconstruct_eval_draft",
    "cmd_cache",
    "cmd_doctor",
    "cmd_eval",
    "cmd_models",
    "cmd_patch_run",
    "cmd_preflight",
    "cmd_run",
    "cmd_show",
    "cmd_validate",
    "main",
    "run_doctor",
]


if __name__ == "__main__":
    sys.exit(main())
