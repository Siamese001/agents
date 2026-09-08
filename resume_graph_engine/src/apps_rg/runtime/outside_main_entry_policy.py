"""SSOT for executable ``apps_rg`` command surfaces.

The complete product and every product-owned inspection action enter only
through [apps_rg/__main__.py](../__main__.py): ``python -m apps_rg``. Nested
modules are import-only libraries. They must not retain ``__main__`` launch
blocks, including evaluation, graph-maintenance, validation, or bootstrap
helpers.
"""
from __future__ import annotations

# No package submodule may be an executable CLI. These exported empty values
# remain only for compatibility with callers that import the policy constants.
ALLOWED_OUTSIDE_MAIN_MODULE_CLI: frozenset[str] = frozenset()
ALLOWED_OUTSIDE_MAIN_MODULE_PREFIXES: tuple[str, ...] = ()

# Shadow ``python -m`` targets — module paths physically removed.
DELETED_RUNTIME_MODULE_CLI: frozenset[str] = frozenset(
    {
        "apps_rg.runtime.orchestrate_full_resume",
        "apps_rg.runtime.package.resume_package_x3",
        "apps_rg.runtime.reports.generated_lane_rollup",
        "apps_rg.runtime.assembly.final_resume_assembler",
        "apps_rg.runtime.render.docx_renderer",
        "apps_rg.runtime.internal.docx_renderer",
        "apps_rg.runtime.internal.docx_manifest_builder",
        "apps_rg.runtime.render.docx_render_x2",
        "apps_rg.runtime.render.docx_manifest_x2",
        "apps_rg.runtime.render.json_resume_docx",
        "apps_rg.runtime.locked_copy.locked_copy_builder",
        "apps_rg.runtime._offline.lane_batch",
        "apps_rg.runtime._offline.resume_package_disposition",
        "apps_rg.runtime._offline.generated_lane_rollup",
        "apps_rg.runtime._offline.final_resume_assembler",
        "apps_rg.runtime._offline.docx_renderer",
        "apps_rg.runtime._offline.docx_manifest_builder",
        "apps_rg.runtime._offline.locked_copy_builder",
        "apps_rg.runtime.dispatch.headline_dispatch",
        "apps_rg.runtime.dispatch.executive_summary_dispatch",
        "apps_rg.runtime.dispatch.competencies_dispatch",
        "apps_rg.runtime.dispatch.unify_bullets_dispatch",
        "apps_rg.runtime.dispatch.unify_narrative_dispatch",
        "apps_rg.runtime.dispatch.ibm_bullets_dispatch",
        "apps_rg.runtime.dispatch.ibm_narrative_dispatch",
        "apps_rg.audit.srfs_receipt_aggregator",
    }
)

# Disallowed command substrings for docs/CI grep gates (runtime execution, not validation).
DISALLOWED_DOC_CI_COMMAND_SUBSTRINGS: tuple[str, ...] = (
    "python -m apps_rg.runtime.orchestrate_full_resume",
    "python -m apps_rg.runtime.package.resume_package_x3",
    "python -m apps_rg.runtime.reports.generated_lane_rollup",
    "python -m apps_rg.runtime.assembly.final_resume_assembler",
    "python -m apps_rg.runtime.locked_copy.locked_copy_builder",
    "python -m apps_rg.runtime._offline.",
    "python -m apps_rg.runtime.internal.",
    "python -m apps_rg.runtime.dispatch.",
    "python -m tests.fixtures.apps_rg.demo_harness_fixture",
    "python ops_scripts/apps_rg/narrative_pass.py",
    "python ops_scripts/apps_rg/generate_resume.py",
    "python ops_scripts/ci/prove_apps_rg_e2e_runtime.py",
)

CANONICAL_PRODUCT_COMMAND = "python -m apps_rg run"


def is_allowed_outside_main_module_cli(module_name: str) -> bool:
    if module_name in ALLOWED_OUTSIDE_MAIN_MODULE_CLI:
        return True
    return any(module_name.startswith(p) for p in ALLOWED_OUTSIDE_MAIN_MODULE_PREFIXES)


def is_deleted_runtime_module_cli(module_name: str) -> bool:
    return module_name in DELETED_RUNTIME_MODULE_CLI


def is_forbidden_runtime_module_cli(module_name: str) -> bool:
    return str(module_name).strip() != "apps_rg.__main__"


__all__ = [
    "ALLOWED_OUTSIDE_MAIN_MODULE_CLI",
    "ALLOWED_OUTSIDE_MAIN_MODULE_PREFIXES",
    "CANONICAL_PRODUCT_COMMAND",
    "DELETED_RUNTIME_MODULE_CLI",
    "DISALLOWED_DOC_CI_COMMAND_SUBSTRINGS",
    "is_allowed_outside_main_module_cli",
    "is_deleted_runtime_module_cli",
    "is_forbidden_runtime_module_cli",
]
