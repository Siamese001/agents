"""CLI subcommand modules for apps_lic."""

from __future__ import annotations

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
    register_parity_subparsers,
    run_doctor,
)
from apps_lic.cli_subcommands.parser_and_run import (
    _build_parser,
    _emit_error,
    _handle_run,
    _normalize_argv,
)

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
    "register_parity_subparsers",
    "run_doctor",
]
