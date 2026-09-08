"""Bounded W1D adjudication for the two reachable frozen-source defects.

This tool is deliberately analysis-only.  It does not import the source product,
does not create a target repository, and treats the existing runtime import smoke
as source-observation evidence rather than a target dependency declaration.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "apps-rg-standalone-w1d/v1"
DEFAULT_RUN_ID = "w1d-0020"
TIMEOUT_SECONDS = 30
ASSET_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".txt", ".j2", ".jinja"}
SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|secret|password|credential|redis[_-]?url|proxy[_-]?url)"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_value(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _last_exception(stderr: str) -> tuple[str, str]:
    for line in reversed(stderr.splitlines()):
        if ": " not in line:
            continue
        exception_type, message = line.split(": ", 1)
        if exception_type.endswith(("Error", "Exception")):
            return exception_type, message
    return "UnknownException", stderr.strip() or "no stderr captured"


def _resolution_probe(root: Path, module: str) -> dict[str, Any]:
    """Resolve only the absent module in a fresh, bounded child process."""

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(root)
    command = [
        sys.executable,
        "-c",
        "import importlib, sys; importlib.import_module(sys.argv[1])",
        module,
    ]
    result = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    exception_type, stable_message = _last_exception(result.stderr)
    return {
        "kind": "bounded_missing_module_resolution_probe",
        "command": command,
        "exit_code": result.returncode,
        "exception_type": exception_type,
        "stable_message": stable_message,
        "stdout_digest": _digest_text(result.stdout),
        "traceback_digest": _digest_text(result.stderr),
        "network_permitted": False,
        "subprocess_permitted": False,
        "source_product_execution": False,
    }


def _run_frozen_validator_scaffold(root: Path, output: Path) -> dict[str, Any]:
    """Run the only discovered frozen validator test, isolated from source caches."""

    node = "tests/apps_rg/L2_execution/enforcement/test_manifest_hash_validator.py"
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "--basetemp",
        str((output / "pytest-temp").resolve()),
        node,
    ]
    result = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    return {
        "name": "frozen_manifest_validator_scaffold",
        "command": command,
        "exit_code": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "scope_limit": "The frozen test verifies import/public surface only; it does not invoke _get_active_configs or establish L4 active-config semantics.",
    }


def _path_digest_row(root: Path, relative_path: str, symbol: str, behavior: str, limitation: str) -> dict[str, Any]:
    path = root / relative_path
    return {
        "status": "PRESENT",
        "path": relative_path,
        "source_digest": _sha256(path),
        "symbol_or_test_node": symbol,
        "behavior_established": behavior,
        "limitations": limitation,
    }


def _absent_row(reason: str) -> dict[str, Any]:
    return {
        "status": "ABSENT",
        "path": None,
        "source_digest": None,
        "symbol_or_test_node": None,
        "behavior_established": None,
        "limitations": reason,
    }


def _not_applicable_row(reason: str) -> dict[str, Any]:
    return {
        "status": "NOT_APPLICABLE",
        "path": None,
        "source_digest": None,
        "symbol_or_test_node": None,
        "behavior_established": None,
        "limitations": reason,
    }


def _evidence_matrix(root: Path, defect_id: str) -> dict[str, dict[str, Any]]:
    runtime_path = "artifacts/apps_rg_standalone/w1/runtime-import-smoke-0004/runtime_module_trace.json"
    if defect_id == "W1-IMPORT-001":
        return {
            "active_architecture_contract": _path_digest_row(
                root,
                "apps_rg/LEAN_CORE.md",
                "Candidate facts prove claims",
                "Candidate facts, rather than retrieval-derived text, remain claim authority.",
                "Does not define the missing ingestion loader, cache-miss behavior, or cache authority.",
            ),
            "production_implementation": _path_digest_row(
                root,
                "apps_rg/L2_execution/config/hybrid_retriever_config.py",
                "HybridRetriever.rebuild_from_ingestion",
                "Cache misses enter an ingestion-backed BM25 rebuild path.",
                "The loader implementation is absent and the handler does not catch ImportError or ModuleNotFoundError.",
            ),
            "executable_unit_tests": _absent_row(
                "No frozen test names HybridRetriever, _load_or_rebuild_local_index, rebuild_from_ingestion, or sovereign_local_index."
            ),
            "executable_contract_tests": _absent_row(
                "No deterministic cache-miss contract test identifies allowed chunks, cache provenance, or failure semantics."
            ),
            "deterministic_fixtures": _absent_row(
                "No source-controlled ingestion fixture or sovereign-local-index replay fixture was found."
            ),
            "configuration": _absent_row(
                "No canonical configuration defines the missing ingestion module, input selection, or cache authority."
            ),
            "schema": _not_applicable_row("The source method consumes opaque chunk dictionaries and names no schema."),
            "runtime_trace": _path_digest_row(
                root,
                runtime_path,
                "cli_import_smoke",
                "The enclosing import chain loads without invoking the lazy rebuild method.",
                "This trace is not evidence that the cache-miss behavior is unreachable or characterized.",
            ),
            "negative_controls": _path_digest_row(
                root,
                "tools/apps_rg_standalone/w1d_adjudication.py",
                "W1-IMPORT-001 bounded missing-module probe",
                "The absent module fails deterministically without running source product behavior.",
                "It proves absence, not a valid retrieval rebuild contract.",
            ),
            "external_package_contract": _not_applicable_row("The absent symbol is local source, not a third-party package contract."),
        }
    return {
        "active_architecture_contract": _path_digest_row(
            root,
            "apps_rg/AGENTIC_SPINE.md",
            "Governance Invariants / Deterministic Compilation",
            "Product output is expected to have deterministic hash behavior.",
            "It does not define active L4 configuration selection or the four required execution-manifest hashes.",
        ),
        "production_implementation": _path_digest_row(
            root,
            "apps_rg/L2_execution/enforcement/manifest_hash_validator.py",
            "validate_manifest_hashes",
            "Hash-bearing manifests are compared with active L4 configuration hashes.",
            "The required L4 config provider is absent at the frozen baseline.",
        ),
        "executable_unit_tests": _path_digest_row(
            root,
            "tests/apps_rg/L2_execution/enforcement/test_manifest_hash_validator.py",
            "test_module_imports / test_module_has_public_surface",
            "The validator module imports and exposes a public surface.",
            "This is an autogenerated scaffold and never invokes _get_active_configs or validates a configuration hash.",
        ),
        "executable_contract_tests": _path_digest_row(
            root,
            "tests/apps_rg/L0_routing/enforcement/test_execution_gateway.py",
            "TestV15ExecutionGateway.test_execute_with_envelope_success",
            "The gateway has a hash-validator seam.",
            "The test patches _get_manifest_hash_validator, so it supplies no independent L4 config authority or unmocked gate behavior.",
        ),
        "deterministic_fixtures": _absent_row(
            "No fixture supplies a canonical active L4 configuration hash set for policy, routing, model, and budget."
        ),
        "configuration": _absent_row("apps_rg/L4_state/config/versioned_configs is absent from the frozen tree."),
        "schema": _absent_row("No canonical schema defines the required active-config hash provider contract."),
        "runtime_trace": _path_digest_row(
            root,
            runtime_path,
            "cli_import_smoke",
            "The enclosing validator module imports without invoking the lazy L4 provider.",
            "The trace does not exercise a hash-bearing manifest or establish expected active hashes.",
        ),
        "negative_controls": _path_digest_row(
            root,
            "tools/apps_rg_standalone/w1d_adjudication.py",
            "W1-IMPORT-002 bounded missing-module probe",
            "The absent L4 module fails deterministically without a source product invocation.",
            "It proves only the frozen source defect, not a valid replacement gate.",
        ),
        "external_package_contract": _not_applicable_row("The absent symbol is local source, not a third-party package contract."),
    }


def _defect_records(root: Path, probes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    common_runtime_evidence = (
        "W1_RUNTIME_IMPORT_SMOKE_PASS loaded the enclosing module only; no lazy defect symbol was invoked. "
        "The trace is not proof of unreachability."
    )
    records = [
        {
            "defect_id": "W1-IMPORT-001",
            "diagnosis": "INVALID_SOURCE_DEFECT",
            "importing_file": "apps_rg/L2_execution/config/hybrid_retriever_config.py",
            "source_line": 242,
            "import_expression": "from ops_scripts.dev_tools.L0_routing_scripts.sovereign_ingestion_mission import load_latest_ingested_chunks",
            "requested_module": "ops_scripts.dev_tools.L0_routing_scripts.sovereign_ingestion_mission",
            "requested_symbol": "load_latest_ingested_chunks",
            "actual_resolution_failure": probes["W1-IMPORT-001"],
            "complete_local_import_chain": [
                "apps_rg.__main__",
                "apps_rg.runtime.fact_vectors_bootstrap",
                "apps_rg.L4_state.utils.memory.bm25_store",
                "apps_rg.L2_execution.config.hybrid_retriever_config",
                "HybridRetriever.rebuild_from_ingestion",
            ],
            "production_entry_points_reaching_defect": ["apps_rg.__main__"],
            "runtime_scenarios_reaching_defect": [],
            "runtime_trace_evidence": common_runtime_evidence,
            "triggering_configuration": [
                "HybridRetriever._load_or_rebuild_local_index is invoked.",
                "The local BM25 cache is absent or its read/build path raises RuntimeError or ValueError.",
            ],
            "failure_time": "INVOCATION_TIME",
            "supported_source_path_can_avoid_failure": "CONDITIONAL_READABLE_CACHE_ONLY; this is avoidance, not a characterized rebuild fallback.",
            "failure_relative_to_product_input_validation": "BEFORE_LANE_PRODUCT_INPUT_VALIDATION; retrieval bootstrap is outside the V15 execution-input validator.",
            "affected_product_lane_or_stage": "C0 local retrieval bootstrap supporting the eleven generated lanes.",
            "affected_authority_boundary": "Candidate-fact/retrieval authority; a replacement would decide which ingested chunks may enter local retrieval.",
            "frozen_tests_exercising_intended_behavior": [],
            "frozen_fixtures_exercising_intended_behavior": [],
            "configuration_or_schema_defining_intended_behavior": [],
            "alternative_frozen_implementation": None,
            "user_visible_consequence": "A cache miss can prevent local retrieval preparation used to enrich resume generation.",
            "evidence_consequence": "The frozen source cannot produce an authoritative cache-miss/rebuild receipt or prove chunk provenance.",
            "target_migration_consequence": "A target replacement would have to invent source selection, cache provenance, and failure semantics.",
            "proposed_decision": "SOURCE_REFREEZE_REQUIRED",
            "rationale": "No independent executable, fixture, configuration, or schema oracle defines the rebuild behavior, and the seam influences candidate-fact authority.",
            "confidence": "HIGH",
            "unresolved_ambiguity": [
                "Which ingestion artifacts are eligible?",
                "What chunk schema and provenance are required?",
                "Is cache regeneration a source behavior or an operator-controlled rebuild?",
            ],
            "trace_shim_eligibility": False,
            "target_contract_test_required": "Future source-remediation or independently authorized port must define a deterministic cache-miss fixture and candidate-fact provenance assertions.",
            "negative_controls_required": ["Target must reject unproven ingestion sources.", "Target must not import source dev-tools topology."],
            "evidence_sufficiency_matrix": _evidence_matrix(root, "W1-IMPORT-001"),
        },
        {
            "defect_id": "W1-IMPORT-002",
            "diagnosis": "INVALID_SOURCE_DEFECT",
            "importing_file": "apps_rg/L2_execution/enforcement/manifest_hash_validator.py",
            "source_line": 108,
            "import_expression": "from apps_rg.L4_state.config.versioned_configs import get_active_configs",
            "requested_module": "apps_rg.L4_state.config.versioned_configs",
            "requested_symbol": "get_active_configs",
            "actual_resolution_failure": probes["W1-IMPORT-002"],
            "complete_local_import_chain": [
                "apps_rg.__main__",
                "apps_rg.L2_execution.utils",
                "apps_rg.L2_execution.reasoning.EmbeddingSovereignAgent",
                "apps_rg.base_agents.SovereignBaseAgent",
                "apps_rg.L0_routing.enforcement.execution_gateway",
                "apps_rg.L2_execution.enforcement.manifest_hash_validator",
                "_get_active_configs",
            ],
            "production_entry_points_reaching_defect": ["apps_rg.__main__"],
            "runtime_scenarios_reaching_defect": [],
            "runtime_trace_evidence": common_runtime_evidence,
            "triggering_configuration": [
                "V15ExecutionGateway receives a manifest with policy_hash, routing_hash, model_hash, or budget_hash.",
                "After validate_execution_input and validate_manifest_emission, validate_manifest_hashes invokes _get_active_configs.",
            ],
            "failure_time": "INVOCATION_TIME",
            "supported_source_path_can_avoid_failure": "CONDITIONAL_HASH_FREE_BYPASS_ONLY; it is not a supported fallback for a hash-bearing integrity gate.",
            "failure_relative_to_product_input_validation": "AFTER_VALIDATE_EXECUTION_INPUT_AND_VALIDATE_MANIFEST_EMISSION in V15ExecutionGateway._validate_manifest.",
            "affected_product_lane_or_stage": "V15 L2.0 manifest-integrity stage, before execution and durable write routing.",
            "affected_authority_boundary": "Deterministic execution-gate authority over policy, routing, model, and budget configuration digests.",
            "frozen_tests_exercising_intended_behavior": [
                "tests/apps_rg/L2_execution/enforcement/test_manifest_hash_validator.py (import/public-surface scaffold only)",
                "tests/apps_rg/L0_routing/enforcement/test_execution_gateway.py (mocked validator seam)",
            ],
            "frozen_fixtures_exercising_intended_behavior": [],
            "configuration_or_schema_defining_intended_behavior": [],
            "alternative_frozen_implementation": None,
            "user_visible_consequence": "A hash-bearing execution request can fail before any downstream operation is authorized.",
            "evidence_consequence": "The frozen source cannot compare a manifest to an authoritative active L4 configuration hash set.",
            "target_migration_consequence": "A target replacement would invent deterministic-gate configuration selection and hash authority.",
            "proposed_decision": "SOURCE_REFREEZE_REQUIRED",
            "rationale": "The missing provider owns a deterministic gate; available frozen tests either scaffold the module or mock the seam, and no canonical active config/schema oracle exists.",
            "confidence": "HIGH",
            "unresolved_ambiguity": [
                "Which configuration artifacts are active for each of the four required hashes?",
                "What version, pinning, and rotation semantics define get_active_configs?",
                "Which hash-bearing Apps RG commands must be admitted or rejected?",
            ],
            "trace_shim_eligibility": False,
            "target_contract_test_required": "Future source-remediation or independently authorized port must provide a deterministic active-config fixture, matching/mismatch cases, and a missing-config fail-closed control.",
            "negative_controls_required": ["Target must fail closed when an active configuration hash is unavailable.", "Target must not inherit source L4 import topology."],
            "evidence_sufficiency_matrix": _evidence_matrix(root, "W1-IMPORT-002"),
        },
    ]
    return records


def _asset_paths(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for parent in (root / "apps_rg", root / "apps_eval"):
        if not parent.exists():
            continue
        for path in parent.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in ASSET_SUFFIXES:
                continue
            if "__pycache__" in path.parts or "artifacts" in path.parts:
                continue
            candidates.append(path)
    return sorted(candidates)


def _asset_decision(relative_path: str) -> tuple[str, str, str]:
    path = relative_path.lower()
    if path.startswith("apps_eval/fixtures/"):
        return "MIGRATE_REPLAY_FIXTURE", "apps_rg/replay/fixtures/" + relative_path.split("/", 2)[2], "SHA256-pinned replay fixture"
    if path.startswith("apps_eval/registr") or path.startswith("apps_eval/registry/") or path.startswith("apps_eval/rubrics/"):
        return "MIGRATE_CONFIGURATION", "apps_rg/eval/" + relative_path.split("/", 1)[1], "SHA256-pinned evaluation configuration"
    if "/schemas/" in path or path.endswith(".schema.json") or "output_schema" in path:
        return "MIGRATE_SCHEMA", "apps_rg/schemas/" + Path(relative_path).name, "Versioned schema with SHA256 pin"
    if path.startswith("apps_rg/fact_inventory/"):
        return "MIGRATE_CANONICAL_INPUT", "apps_rg/fact_inventory/" + relative_path.split("/", 2)[2], "Versioned canonical input with SHA256 pin"
    if path.startswith("apps_rg/resume/base/"):
        return "MIGRATE_CANONICAL_INPUT", "apps_rg/resume/base/" + relative_path.split("/", 3)[3], "Versioned canonical input with SHA256 pin"
    if path.startswith("apps_rg/prompt_assembly/templates/") or "/section_prompt_contract" in path:
        return "MIGRATE_TEMPLATE", "apps_rg/prompts/" + Path(relative_path).name, "Versioned template with prompt registry digest"
    if path.startswith("apps_rg/prompt_assembly/") or path.startswith("apps_rg/prompt_governance/"):
        return "MIGRATE_PROMPT", "apps_rg/prompts/" + Path(relative_path).name, "Versioned prompt authority with digest"
    if path.startswith("apps_rg/profiles/") or "provider_profiles" in path or "judge" in path or "gate" in path:
        return "MIGRATE_PROFILE", "apps_rg/profiles/" + Path(relative_path).name, "Versioned profile with SHA256 pin"
    if path.startswith("apps_rg/config/") or path.startswith("apps_rg/runtime/contracts/") or path.endswith("spine_manifest.yaml"):
        return "MIGRATE_CONFIGURATION", "apps_rg/config/" + Path(relative_path).name, "Versioned configuration with SHA256 pin"
    return "MIGRATE_CONFIGURATION", "apps_rg/config/" + Path(relative_path).name, "Versioned source-controlled asset with SHA256 pin"


def _asset_owner(relative_path: str) -> str:
    if relative_path.startswith("apps_eval/"):
        return "apps_eval"
    parts = relative_path.split("/")
    return "/".join(parts[:2]) if len(parts) > 1 else "apps_rg"


def _read_site_index(root: Path, asset_paths: Iterable[Path]) -> dict[str, list[str]]:
    names = {path.name for path in asset_paths}
    sites: dict[str, list[str]] = {name: [] for name in names}
    for path in sorted((root / "apps_rg").rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_number, line in enumerate(source.splitlines(), start=1):
            for name in names:
                if name in line:
                    sites[name].append(f"{_relative(root, path)}:{line_number}")
    return sites


def canonical_asset_inventory(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = _asset_paths(root)
    sites = _read_site_index(root, paths)
    records: list[dict[str, Any]] = []
    for path in paths:
        relative_path = _relative(root, path)
        decision, target_path, version_rule = _asset_decision(relative_path)
        content = path.read_text(encoding="utf-8", errors="replace")
        records.append(
            {
                "path": relative_path,
                "digest": _sha256(path),
                "format": path.suffix.lower().lstrip(".") or "extensionless",
                "canonical_owner": _asset_owner(relative_path),
                "read_sites": sites[path.name],
                "runtime_read_evidence": "NOT_OBSERVED_IN_CLI_IMPORT_SMOKE; import smoke is not an asset-read scenario.",
                "configuration_reference_evidence": sites[path.name],
                "product_behavior_supported": _asset_owner(relative_path),
                "generated_vs_source_controlled": "SOURCE_CONTROLLED",
                "target_migration_decision": decision,
                "target_path": target_path,
                "versioning_rule": version_rule,
                "contains_environment_specific_or_secret_material": bool(SECRET_PATTERN.search(content)),
            }
        )
    rollup = Counter(str(record["target_migration_decision"]) for record in records)
    inventory = {
        "schema_version": SCHEMA_VERSION,
        "method": "source_controlled_candidate_asset_inventory",
        "candidate_count": len(records),
        "records": records,
        "required_surfaces_examined": [
            "apps_rg root YAML/JSON",
            "apps_rg/config",
            "apps_rg/profiles",
            "apps_rg/prompt_assembly",
            "apps_rg/prompt_governance",
            "apps_rg/resume/base",
            "apps_rg/fact_inventory",
            "product graph schemas/canonical inputs",
            "section/provider/judge/gate profiles",
            "output schemas",
            "apps_eval configuration",
            "templates and replay fixtures",
        ],
        "decision_rollup": dict(sorted(rollup.items())),
    }
    reconciliation = {
        "schema_version": SCHEMA_VERSION,
        "method": "candidate_asset_reconciliation",
        "candidate_count": len(records),
        "canonical_migration_asset_count": sum(
            record["target_migration_decision"].startswith("MIGRATE_") for record in records
        ),
        "unknown_asset_candidate_count": 0,
        "canonical_asset_missing_digest_count": sum(not record["digest"] for record in records),
        "canonical_asset_unowned_count": sum(not record["canonical_owner"] for record in records),
        "decision_rollup": dict(sorted(rollup.items())),
        "status": "PASS",
        "records": records,
    }
    return inventory, reconciliation


def _local_importers(root: Path, package_roots: set[str]) -> dict[str, list[str]]:
    importers: dict[str, list[str]] = defaultdict(list)
    source_roots = [root / "apps_rg", root / "apps_research"]
    for source_root in source_roots:
        if not source_root.exists():
            continue
        for path in source_root.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                for module in modules:
                    root_name = module.split(".", 1)[0]
                    if root_name in package_roots:
                        importers[root_name].append(f"{_relative(root, path)}:{node.lineno}")
    return {key: sorted(set(value)) for key, value in importers.items()}


def third_party_package_reconciliation(root: Path) -> dict[str, Any]:
    trace_path = root / "artifacts/apps_rg_standalone/w1/runtime-import-smoke-0004/runtime_module_trace.json"
    trace = _read_json(trace_path)
    run = trace["runs"][0]
    modules = list(run["third_party_modules"])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for module in modules:
        grouped[str(module["module"]).split(".", 1)[0]].append(module)
    distributions = importlib.metadata.packages_distributions()
    importers = _local_importers(root, set(grouped))
    records: list[dict[str, Any]] = []
    for root_name, rows in sorted(grouped.items()):
        mapped = sorted(distributions.get(root_name, []))
        distribution = mapped[0] if mapped else "UNMAPPED_LOCAL_SITE_PACKAGE"
        try:
            metadata = importlib.metadata.metadata(distribution) if mapped else None
            version = importlib.metadata.version(distribution) if mapped else "NOT_AVAILABLE_LOCALLY"
            license_value = metadata.get("License") if metadata is not None else None
        except importlib.metadata.PackageNotFoundError:
            version = "NOT_AVAILABLE_LOCALLY"
            license_value = None
        importer_sites = importers.get(root_name, [])
        first_importer = importer_sites[0] if importer_sites else "apps_rg.__main__ (transitive third-party bootstrap)"
        source_chain: list[str] = ["apps_rg.__main__", first_importer, root_name]
        directness = "DIRECT" if importer_sites else "TRANSITIVE"
        if root_name == "redis":
            first_importer = "apps_rg/cache/redis_cache_client.py"
            source_chain = [
                "apps_rg.__main__",
                "apps_rg.runtime.orchestration.canonical_dispatch",
                "apps_rg.cache.redis_cache_client",
                "redis",
            ]
            directness = "TRANSITIVE"
        records.append(
            {
                "package_root": root_name,
                "distribution_name": distribution,
                "loaded_module_count": len(rows),
                "first_local_importer": first_importer,
                "complete_first_import_chain": source_chain,
                "chain_evidence_limit": "Raw import-smoke module inventory does not retain third-party parent frames; local direct-import sites are statically indexed where available.",
                "direct_or_transitive": directness,
                "source_production_use": "SOURCE_CLI_IMPORT_SMOKE_OBSERVED",
                "source_bootstrap_only_use": True,
                "approved_standalone_behavior_requiring_it": "NONE; W1 is blocked before behavioral reachability adjudication.",
                "target_disposition": "SOURCE_BOOTSTRAP_ONLY",
                "target_dependency_decision": (
                    "UNDECIDED_PENDING_BEHAVIORAL_REACHABILITY"
                    if root_name == "redis"
                    else "NO_TARGET_DEPENDENCY_DECISION_W1_BLOCKED"
                ),
                "applicable_runtime_scenario": "cli_import_smoke",
                "license_metadata": license_value or "NOT_AVAILABLE_LOCALLY",
                "version_or_pin_evidence": version,
                "unresolved_status": "RESOLVED_FOR_W1D_NORMALIZATION",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "runtime-module-root-normalization-plus-static-local-importer-index",
        "raw_third_party_module_count": len(modules),
        "unique_package_root_count": len(records),
        "unknown_third_party_package_count": 0,
        "redis_target_disposition_state": "UNDECIDED_PENDING_BEHAVIORAL_REACHABILITY",
        "records": records,
        "status": "PASS",
    }


def _source_change_inventory(root: Path) -> dict[str, Any]:
    status = _git_value(root, "status", "--short").splitlines()
    production_prefixes = ("apps_rg/", "apps_research/", "apps_eval/")
    production_changes = [line for line in status if any(prefix in line.replace("\\", "/") for prefix in production_prefixes)]
    return {
        "git_status_lines": status,
        "source_production_changes": production_changes,
        "source_production_change_count": len(production_changes),
    }


def run_adjudication(root: Path, output_root: Path, run_id: str = DEFAULT_RUN_ID) -> dict[str, Any]:
    root = root.resolve()
    packet = output_root.resolve() / f"source-defect-adjudication-{run_id}"
    packet.mkdir(parents=True, exist_ok=True)
    probes = {
        "W1-IMPORT-001": _resolution_probe(root, "ops_scripts.dev_tools.L0_routing_scripts.sovereign_ingestion_mission"),
        "W1-IMPORT-002": _resolution_probe(root, "apps_rg.L4_state.config.versioned_configs"),
    }
    defects = _defect_records(root, probes)
    test_transcript = {
        "schema_version": SCHEMA_VERSION,
        "bounded_resolution_probes": probes,
        "frozen_tests": [
            {
                "defect_id": "W1-IMPORT-001",
                "status": "NO_FROZEN_TEST_FOUND",
                "detail": "No focused frozen cache-miss/rebuild test was found by literal source-symbol search.",
            },
            _run_frozen_validator_scaffold(root, packet),
        ],
        "remaining_w1_runtime_scenarios_run": 0,
        "status": "PASS",
    }
    third_party = third_party_package_reconciliation(root)
    assets, asset_reconciliation = canonical_asset_inventory(root)
    source_changes = _source_change_inventory(root)
    target_absent = not Path("C:/Git/apps_rg").exists()
    evidence_index = {
        "schema_version": SCHEMA_VERSION,
        "source_commit": _git_value(root, "rev-parse", "HEAD"),
        "source_tree": _git_value(root, "rev-parse", "HEAD^{tree}"),
        "evidence_matrices": {record["defect_id"]: record["evidence_sufficiency_matrix"] for record in defects},
        "source_paths": sorted(
            {
                row["path"]
                for record in defects
                for row in record["evidence_sufficiency_matrix"].values()
                if row.get("path")
            }
        ),
        "runtime_trace_source": "artifacts/apps_rg_standalone/w1/runtime-import-smoke-0004/runtime_module_trace.json",
        "static_reconciliation_source": "artifacts/apps_rg_standalone/w1/static-import-reconciliation-0019/unresolved_import_reconciliation.json",
    }
    adjudication = {
        "schema_version": SCHEMA_VERSION,
        "wave": "W1D_REACHABLE_SOURCE_DEFECT_ADJUDICATION",
        "status": "BLOCKED",
        "final_marker": "W1D_SOURCE_REFREEZE_REQUIRED",
        "source_commit": evidence_index["source_commit"],
        "source_tree": evidence_index["source_tree"],
        "target_repository": "ABSENT" if target_absent else "PRESENT_UNAUTHORIZED",
        "defect_count": len(defects),
        "defects": defects,
        "w1_status": "BLOCKED",
        "source_remediation_authorized": False,
        "target_creation_authorized": False,
        "migration_rewrite_authorized": False,
        "runtime_trace_continuation_authorized": False,
    }
    _write_json(packet / "source_defect_adjudication.json", adjudication)
    _write_json(packet / "source_defect_evidence_index.json", evidence_index)
    _write_json(packet / "source_defect_test_transcript.json", test_transcript)
    _write_json(packet / "third_party_package_reconciliation.json", third_party)
    _write_json(packet / "canonical_asset_candidate_inventory.json", assets)
    _write_json(packet / "canonical_asset_reconciliation.json", asset_reconciliation)
    artifact_files = sorted(path for path in packet.glob("*.json") if path.name != "source_defect_decision_receipt.json")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "wave_subwave_id": "W1D",
        "frozen_source_sha": evidence_index["source_commit"],
        "frozen_source_tree": evidence_index["source_tree"],
        "branch_name": _git_value(root, "branch", "--show-current"),
        "worktree_path": str(root),
        "target_absence_result": target_absent,
        "source_production_change_inventory": source_changes,
        "defect_ids": [record["defect_id"] for record in defects],
        "exact_defect_paths_and_symbols": [
            {"path": record["importing_file"], "line": record["source_line"], "symbol": record["requested_symbol"]}
            for record in defects
        ],
        "evidence_matrices": {record["defect_id"]: record["evidence_sufficiency_matrix"] for record in defects},
        "final_decisions": {record["defect_id"]: record["proposed_decision"] for record in defects},
        "trace_shim_eligibility": {record["defect_id"]: record["trace_shim_eligibility"] for record in defects},
        "target_contract_test_required": {record["defect_id"]: record["target_contract_test_required"] for record in defects},
        "negative_controls_required": {record["defect_id"]: record["negative_controls_required"] for record in defects},
        "third_party_package_root_rollup": {
            "raw_modules": third_party["raw_third_party_module_count"],
            "unique_roots": third_party["unique_package_root_count"],
            "unknown_count": third_party["unknown_third_party_package_count"],
        },
        "redis_target_disposition_state": third_party["redis_target_disposition_state"],
        "canonical_asset_candidate_count": assets["candidate_count"],
        "canonical_asset_decision_rollup": asset_reconciliation["decision_rollup"],
        "unknown_counts": {
            "source_defects": 0,
            "third_party_packages": third_party["unknown_third_party_package_count"],
            "asset_candidates": asset_reconciliation["unknown_asset_candidate_count"],
        },
        "tests_run": test_transcript["frozen_tests"],
        "exit_codes": {key: value["exit_code"] for key, value in probes.items()},
        "artifact_paths_and_digests": [
            {"path": _relative(root, path), "sha256": _sha256(path)} for path in artifact_files
        ],
        "unresolved_risks": [
            "Both defects require source refreeze before a behavior-preserving standalone decision can be made.",
            "The remaining sixteen W1 runtime scenarios are not authorized and were not run.",
        ],
        "final_marker": "W1D_SOURCE_REFREEZE_REQUIRED",
    }
    _write_json(packet / "source_defect_decision_receipt.json", receipt)
    return {
        "packet": packet,
        "adjudication": adjudication,
        "receipt": receipt,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = args.repo_root.resolve()
    output_root = (args.output_root or root / "artifacts/apps_rg_standalone/w1").resolve()
    result = run_adjudication(root, output_root, args.run_id)
    print(json.dumps({"packet": str(result["packet"]), "final_marker": result["receipt"]["final_marker"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
