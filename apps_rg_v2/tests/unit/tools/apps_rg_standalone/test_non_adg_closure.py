from __future__ import annotations

import json
from pathlib import Path

from tools.apps_rg_standalone.non_adg_closure import (
    DYNAMIC_IMPORT_RECONCILIATION_POLICIES,
    TARGET_SECTION_REGISTRY,
    asset_access_callsites,
    dynamic_import_inventory,
    emit_manifest_bundle,
    legacy_surface_inventory,
    normalized_asset_inventory,
    non_python_asset_closure,
    original_asset_callsite_baseline,
    registry_reconciliation,
    static_import_closure,
    unresolved_import_reconciliation,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_static_closure_resolves_relative_stdlib_external_and_missing_local(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "__all__ = ['child']\nVALUE = 1\n")
    _write(
        tmp_path / "demo" / "__main__.py",
        "from __future__ import annotations\nfrom . import child\nfrom demo import VALUE\nimport json\nimport requests\n",
    )
    _write(tmp_path / "demo" / "child.py", "from . import missing\n")

    result = static_import_closure(tmp_path, ("demo.__main__",))

    modules = {row["module"] for row in result["modules"]}
    assert modules == {"demo", "demo.__main__", "demo.child"}
    assert result["status"] == "INCOMPLETE"
    assert result["unresolved_local_imports"] == [
        {
            "source_module": "demo.child",
            "target_module": "demo.missing",
            "line": 1,
            "kind": "from_import_member_module",
            "classification": "UNRESOLVED_LOCAL",
            "execution_context": "RUNTIME",
        }
    ]
    resolutions = {edge["target_module"]: edge["resolution"] for edge in result["edges"]}
    assert resolutions["__future__"] == "STDLIB"
    assert resolutions["demo.VALUE"] == "PACKAGE_ATTRIBUTE"
    assert resolutions["json"] == "STDLIB"
    assert resolutions["requests"] == "EXTERNAL"


def test_static_closure_separates_type_only_optional_and_package_facade_imports(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "class PackageError(Exception):\n    pass\n")
    _write(
        tmp_path / "demo" / "__main__.py",
        "from typing import TYPE_CHECKING\n"
        "from . import PackageError\n"
        "if TYPE_CHECKING:\n"
        "    from . import type_only_missing\n"
        "try:\n"
        "    from . import optional_missing\n"
        "except ImportError:\n"
        "    optional_missing = None\n",
    )

    result = static_import_closure(tmp_path, ("demo.__main__",))

    assert result["status"] == "PASS"
    assert not result["unresolved_local_imports"]
    assert {row["execution_context"] for row in result["non_runtime_unresolved_local_imports"]} == {
        "OPTIONAL_IMPORT",
        "TYPE_CHECKING",
    }
    resolutions = {edge["target_module"]: edge["resolution"] for edge in result["edges"]}
    assert resolutions["demo.PackageError"] == "PACKAGE_ATTRIBUTE"


def test_unresolved_import_reconciliation_records_site_condition_and_absent_paths(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "")
    _write(
        tmp_path / "demo" / "__main__.py",
        "def load(provider: str) -> None:\n"
        "    if provider == 'openai':\n"
        "        from .missing import Client\n",
    )

    static = static_import_closure(tmp_path, ("demo.__main__",))
    reconciliation = unresolved_import_reconciliation(tmp_path, static)

    assert reconciliation["status"] == "BLOCKED"
    assert reconciliation["unresolved_import_count"] == 0
    assert reconciliation["static_unresolved_import_count"] == 0
    assert reconciliation["unknown_import_reachability_count"] == 0
    assert reconciliation["unknown_import_disposition_count"] == 0
    assert reconciliation["reachable_unmitigated_source_defect_count"] == 1
    assert reconciliation["markers"] == ["W1_BLOCKED_ON_REACHABLE_SOURCE_DEFECT"]
    record = reconciliation["records"][0]
    assert record["importing_symbol"] == "load"
    assert record["configuration_condition"] == ["provider == 'openai'"]
    assert record["source_import_classification"] == "INVALID_SOURCE_DEFECT"
    assert record["diagnosis"] == "INVALID_SOURCE_DEFECT"
    assert record["missing_target"] == "demo.missing"
    assert record["static_reachability"] == "CONDITIONAL"
    assert record["runtime_reachability"] == "CONDITIONAL"
    assert record["migration_disposition"] == "BLOCKED_SOURCE_DEFECT"
    assert record["w1_blocking"] is True
    assert not any(candidate["exists"] for candidate in record["candidate_paths"])


def test_dynamic_and_asset_inventory_require_reconciliation_for_expressions(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "")
    _write(
        tmp_path / "demo" / "__main__.py",
        "import importlib\n"
        "from pathlib import Path\n"
        "importlib.import_module('demo.plugin')\n"
        "importlib.import_module(module_name)\n"
        "Path('data/fixture.json').read_text()\n"
        "Path(asset_path).read_text()\n",
    )
    _write(tmp_path / "demo" / "plugin.py", "")
    _write(tmp_path / "data" / "fixture.json", "{}\n")

    static = static_import_closure(tmp_path, ("demo.__main__",))
    dynamic = dynamic_import_inventory(tmp_path, static)
    assets = non_python_asset_closure(tmp_path, static)

    assert dynamic["status"] == "INCOMPLETE"
    assert {record["classification"] for record in dynamic["records"]} == {
        "LOCAL",
        "DYNAMIC_EXPRESSION_REQUIRES_RECONCILIATION",
    }
    assert assets["status"] == "INCOMPLETE"
    assert {record["classification"] for record in assets["records"]} == {
        "STATIC_ASSET",
        "DYNAMIC_ASSET_EXPRESSION_REQUIRES_RECONCILIATION",
    }


def test_normalized_asset_inventory_groups_dynamic_templates_and_preserves_write_intent(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "")
    _write(
        tmp_path / "demo" / "__main__.py",
        "from pathlib import Path\n"
        "Path(output_path).write_text('result')\n"
        "Path(output_path).write_text('result')\n",
    )

    static = static_import_closure(tmp_path, ("demo.__main__",))
    assets = non_python_asset_closure(tmp_path, static)
    normalized = normalized_asset_inventory(asset_access_callsites(assets))

    assert normalized["raw_callsite_count"] == 2
    assert normalized["normalized_expression_count"] == 1
    assert normalized["records"][0]["intent"] == "WRITE"
    assert normalized["records"][0]["access_kind"] == "WRITE"
    assert normalized["records"][0]["asset_role"] == "GENERATED_OUTPUT"
    assert normalized["canonical_migration_asset_count"] == 0
    assert normalized["records"][0]["runtime_binding_required"] is True


def test_original_asset_baseline_is_preserved_without_becoming_a_target_input(tmp_path: Path) -> None:
    baseline_path = tmp_path / "artifacts/apps_rg_standalone/w1/static-import-reconciliation-0008"
    _write(
        baseline_path / "non_python_asset_closure.json",
        json.dumps(
            {
                "records": [
                    {
                        "source_path": "demo/__main__.py",
                        "line": 1,
                        "call": "open",
                        "path_literal": None,
                    }
                ]
            }
        ),
    )

    baseline = original_asset_callsite_baseline(tmp_path)

    assert baseline["status"] == "PRESERVED"
    assert baseline["callsite_count"] == 1
    assert baseline["callsites"][0]["source_path"] == "demo/__main__.py"


def test_dynamic_inventory_extracts_literal_module_references_from_named_registries(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "")
    _write(
        tmp_path / "demo" / "__main__.py",
        "_PLUGIN_SPECS = {'demo': ('demo.plugin', 'Plugin')}\n"
        "_ENTRYPOINT_REGISTRY = {'factory': 'demo.plugin.Factory'}\n"
        "_OPTIONAL_PROVIDER: dict[str, str]\n"
        "_ASSET_REGISTRY = {'fixture': 'data/fixture.json'}\n"
        "class AnchorNames:\n"
        "    ANCHOR_EXAMPLE = 'demo.not_a_module'\n",
    )
    _write(tmp_path / "demo" / "plugin.py", "")

    static = static_import_closure(tmp_path, ("demo.__main__",))
    dynamic = dynamic_import_inventory(tmp_path, static)

    records = dynamic["registry_references"]
    assert records[0] == {
        "source_module": "demo.__main__",
        "source_path": "demo/__main__.py",
        "line": 1,
        "registry_name": "_PLUGIN_SPECS",
        "registry_key": "demo",
        "module_name": "demo.plugin",
        "classification": "LOCAL",
        "resolved_module": "demo.plugin",
        "attribute_path": None,
    }
    assert records[1]["classification"] == "LOCAL_OBJECT_REFERENCE"
    assert records[1]["resolved_module"] == "demo.plugin"
    assert records[1]["attribute_path"] == "Factory"


def test_legacy_inventory_marks_frozen_dynamic_reference_for_non_inheritance(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "")
    _write(
        tmp_path / "demo" / "__main__.py",
        "import importlib\nimportlib.import_module('demo.adg_legacy')\n",
    )
    _write(tmp_path / "demo" / "adg_legacy.py", "")

    static = static_import_closure(tmp_path, ("demo.__main__",))
    legacy = legacy_surface_inventory(dynamic_import_inventory(tmp_path, static))

    assert legacy["status"] == "PASS"
    assert legacy["entries"] == [
        {
            "source_module": "demo.__main__",
            "source_path": "demo/__main__.py",
            "line": 2,
            "reference_kind": "dynamic_import",
            "frozen_reference": "demo.adg_legacy",
            "classification": "LOCAL",
            "target_disposition": "DO_NOT_INHERIT",
        }
    ]


def test_registry_reconciliation_classifies_known_owner_and_keeps_pending_imports_incomplete() -> None:
    dynamic = {
        "registry_references": [
            {
                "source_module": "apps_rg.fact_inventory",
                "registry_name": "_REACHABILITY_ANCHOR_SPECS",
                "registry_key": "anchor",
                "source_path": "apps_rg/fact_inventory/__init__.py",
                "line": 12,
            }
        ],
        "requires_reconciliation": [
            {
                "source_module": "apps_rg.fact_inventory",
                "call": "import_module",
                "classification": "DYNAMIC_EXPRESSION_REQUIRES_RECONCILIATION",
            }
        ],
    }

    reconciliation = registry_reconciliation(dynamic)

    assert reconciliation["status"] == "INCOMPLETE"
    assert reconciliation["unknown_registry_entry_count"] == 0
    assert reconciliation["unresolved_dynamic_import_count"] == 1
    assert reconciliation["registries"][0]["classification"] == "LEGACY_DO_NOT_INHERIT"
    assert reconciliation["canonical_target_registry"]["name"] == "SECTION_EXECUTION_POLICIES"
    assert reconciliation["canonical_target_registry"]["lane_count"] == 11


def test_dynamic_import_policy_table_covers_the_current_static_inventory_sites() -> None:
    assert len(DYNAMIC_IMPORT_RECONCILIATION_POLICIES) == 16
    assert TARGET_SECTION_REGISTRY["lanes"] == (
        "competencies",
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
        "ey_bullets",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
        "ey_narrative",
        "executive_summary",
        "headline",
    )


def test_static_closure_classifies_namespace_packages_without_marking_them_missing(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "")
    _write(tmp_path / "demo" / "__main__.py", "from demo.namespace import VALUE\n")
    _write(tmp_path / "demo" / "namespace" / "leaf.py", "VALUE = 1\n")

    result = static_import_closure(tmp_path, ("demo.__main__",))

    assert result["status"] == "PASS"
    assert not result["unresolved_local_imports"]
    resolutions = {edge["target_module"]: edge["resolution"] for edge in result["edges"]}
    assert resolutions["demo.namespace"] == "LOCAL_NAMESPACE"


def test_emitted_bundle_is_deterministic_and_declares_runtime_trace_not_run(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "")
    _write(tmp_path / "demo" / "__main__.py", "import json\n")
    output = tmp_path / "out"

    first = emit_manifest_bundle(tmp_path, output, ("demo.__main__",))
    before = (output / "static_import_closure.json").read_text(encoding="utf-8")
    second = emit_manifest_bundle(tmp_path, output, ("demo.__main__",))
    after = (output / "static_import_closure.json").read_text(encoding="utf-8")

    assert first == second
    assert before == after
    assert json.loads((output / "runtime_module_trace.json").read_text(encoding="utf-8"))["status"] == "NOT_RUN"
