"""Build bounded, non-ADG source-closure evidence for the apps_rg migration."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = "apps-rg-non-adg-closure/v1"
DEFAULT_ENTRYPOINTS = (
    "apps_rg.__main__",
    "apps_research.__main__",
    "apps_eval.__main__",
)
DEFAULT_MAX_MODULES = 1_000
ASSET_SUFFIXES = frozenset({".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".docx", ".j2"})
DYNAMIC_CALL_SUFFIXES = frozenset(
    {
        "__import__",
        "import_module",
        "find_spec",
        "entry_points",
        "iter_entry_points",
        "load_entry_point",
        "run_module",
    }
)
ASSET_CALL_SUFFIXES = frozenset(
    {
        "open",
        "read_text",
        "read_bytes",
        "files",
        "get_template",
        "get_source",
        "write_bytes",
        "write_text",
    }
)
REGISTRY_IDENTIFIER_TOKENS = frozenset(
    {"anchor", "dispatch", "entrypoint", "registry", "spec"}
)
FORBIDDEN_SOURCE_TOKEN = "adg"
ORIGINAL_ASSET_CALLSITE_BASELINE = Path(
    "artifacts/apps_rg_standalone/w1/static-import-reconciliation-0008/non_python_asset_closure.json"
)
REGISTRY_RECONCILIATION_POLICIES: dict[tuple[str, str], dict[str, str]] = {
    (
        "apps_rg.fact_inventory",
        "_REACHABILITY_ANCHOR_SPECS",
    ): {
        "classification": "LEGACY_DO_NOT_INHERIT",
        "configuration_selector": "PEP562 attribute access to _REACHABILITY_ANCHORS",
        "provider_implications": "none",
        "section_implications": "product-graph hardening anchors; not product-graph authority",
    },
    (
        "apps_rg.l2_recipe.modular_resume_generation",
        "LANE_DISPATCH_MODULES",
    ): {
        "classification": "DUPLICATE_TO_MERGE",
        "configuration_selector": "run_modular_resume_generation lane report",
        "provider_implications": "per-lane provider selection is external to this registry",
        "section_implications": "eight section modules; source comment names canonical lane_batch owner",
    },
    (
        "apps_rg.cache.whole_run_entrypoint_preflight",
        "ENTRYPOINT_CANONICAL_DISPATCH",
    ): {
        "classification": "CANONICAL_SSOT",
        "configuration_selector": "whole-run preflight audit matrix",
        "provider_implications": "whole-run cache preflight only",
        "section_implications": "section lanes bypass whole-run preflight",
    },
    (
        "apps_rg.cache.whole_run_entrypoint_preflight",
        "ENTRYPOINT_TEST_WHOLE_RUN_HARNESS",
    ): {
        "classification": "TEST_ONLY",
        "configuration_selector": "test harness audit matrix row",
        "provider_implications": "none",
        "section_implications": "none",
    },
    (
        "apps_rg.cache.whole_run_entrypoint_preflight",
        "ENTRYPOINT_DISPATCH_APPS_RG_RUN",
    ): {
        "classification": "LEGACY_DO_NOT_INHERIT",
        "configuration_selector": "whole-run preflight audit matrix",
        "provider_implications": "legacy core dispatch; no target dependency",
        "section_implications": "none",
    },
    (
        "apps_rg.cache.whole_run_entrypoint_preflight",
        "ENTRYPOINT_ENVELOPE_DISPATCH",
    ): {
        "classification": "LEGACY_DO_NOT_INHERIT",
        "configuration_selector": "whole-run preflight audit matrix",
        "provider_implications": "missing source route; no target dependency",
        "section_implications": "none",
    },
}

TARGET_SECTION_REGISTRY = {
    "owner": "apps_rg.runtime.section_execution_plan",
    "name": "SECTION_EXECUTION_POLICIES",
    "classification": "CANONICAL_TARGET_REGISTRY",
    "lanes": (
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
    ),
    "rationale": "The declarative execution-policy mapping owns the ordered eleven-lane product contract; source dispatch lists are migration inputs only.",
}


def _dynamic_policy(
    migration_disposition: str,
    target_owner: str,
    trigger_configuration: str,
    rationale: str,
) -> dict[str, str]:
    return {
        "migration_disposition": migration_disposition,
        "target_owner": target_owner,
        "trigger_configuration": trigger_configuration,
        "rationale": rationale,
    }


DYNAMIC_IMPORT_RECONCILIATION_POLICIES: dict[tuple[str, int], dict[str, str]] = {
    (
        "apps_rg.L0_routing.c0_retrieval.c0_3_enhanced.adapter_registry",
        150,
    ): _dynamic_policy(
        "REWRITE_BEHIND_PORT",
        "GraphReadAdapter port",
        "A configured graph_adapter_ref is resolved.",
        "The target may accept an approved graph-read adapter contract, not an arbitrary source module reference.",
    ),
    ("apps_rg.L0_routing.utils.layer_emission_seam", 124): _dynamic_policy(
        "LEGACY_DO_NOT_INHERIT",
        "none",
        "The legacy layer-emission seam requests its enforcement module.",
        "Core emission enforcement is not a standalone Apps RG dependency.",
    ),
    ("apps_rg.L4_state.cache.gptcache_client", 200): _dynamic_policy(
        "OPTIONAL_EXPLICIT",
        "unassigned cache adapter",
        "The legacy GPT cache probes chromadb.errors.",
        "A target cache implementation must be separately approved; no legacy cache dependency is inherited.",
    ),
    ("apps_rg._reexport", 11): _dynamic_policy(
        "LEGACY_DO_NOT_INHERIT",
        "none",
        "A compatibility shim re-exports a caller-supplied module.",
        "The target uses explicit public imports rather than a generic re-export mechanism.",
    ),
    ("apps_rg.mixins.subatomic_testing_mixin", 39): _dynamic_policy(
        "TEST_ONLY",
        "none",
        "The subatomic self-test mixin requests a stale MCP operation module.",
        "This is a source test-resilience fallback and not product runtime behavior.",
    ),
    ("apps_rg.mixins.tool_reliability_mixin", 303): _dynamic_policy(
        "LEGACY_DO_NOT_INHERIT",
        "none",
        "The generic tool-reliability mixin lazily imports threading.",
        "This core mixin is outside the standalone product surface.",
    ),
    ("apps_research.__main__", 25): _dynamic_policy(
        "LEGACY_DO_NOT_INHERIT",
        "none",
        "Apps Research bootstrap requests the forbidden ADG integration.",
        "The target has no ADG dependency.",
    ),
    ("apps_rg.fact_inventory", 59): _dynamic_policy(
        "LEGACY_DO_NOT_INHERIT",
        "none",
        "A PEP 562 reachability-anchor attribute is requested.",
        "The anchors exist only to retain source graph hardening reachability and are not product fact authority.",
    ),
    ("apps_rg.runtime.fact_vectors_bootstrap", 253): _dynamic_policy(
        "REWRITE_BEHIND_PORT",
        "FactVectorHydration port",
        "The fact-vector hydration runtime probes its fixed heavy-dependency list.",
        "The target needs an explicit hydration contract, not source dynamic dependency probing.",
    ),
    ("apps_rg.runtime.final_resume_outputs", 675): _dynamic_policy(
        "REWRITE_BEHIND_PORT",
        "ResumeExport port",
        "The final-output command requests the DOCX exporter.",
        "Export behavior must be captured as a standalone port rather than an ops_scripts import.",
    ),
    ("apps_rg.runtime.orchestration.integrated_spine_runner", 11): _dynamic_policy(
        "REWRITE_BEHIND_PORT",
        "StandaloneRunCoordinator port",
        "The integrated runner resolves the core single-action spine.",
        "The target needs a local coordinator contract, not a core entrypoint dependency.",
    ),
    ("apps_rg.runtime.orchestration.r3r4_whole_run_orchestration", 147): _dynamic_policy(
        "REWRITE_BEHIND_PORT",
        "ResearchHandoff port",
        "Whole-run orchestration loads the Apps Research bridge.",
        "Research handoff is a product boundary that must be explicit in the standalone design.",
    ),
    ("apps_rg.runtime.orchestration.r3r4_whole_run_orchestration", 150): _dynamic_policy(
        "REWRITE_BEHIND_PORT",
        "ResearchHandoff port",
        "Whole-run orchestration loads the Apps Research bridge for optional validation.",
        "The duplicate bridge import is not an independent target registry.",
    ),
    ("apps_rg.runtime.orchestration.r3r4_whole_run_orchestration", 270): _dynamic_policy(
        "REWRITE_BEHIND_PORT",
        "ResearchHandoff port",
        "Managed research delegation is selected by whole-run orchestration.",
        "Delegation behavior needs a port contract rather than a source module import.",
    ),
    ("apps_rg.runtime.sections.executive_summary_judge_remediation", 1061): _dynamic_policy(
        "REWRITE_BEHIND_PORT",
        "ExecutiveSummaryRemediation port",
        "Judge remediation requests a same-authority regeneration bridge.",
        "The target must preserve the approved regeneration contract without importing the source bridge.",
    ),
    ("apps_shared.orchestration.hop_pipeline", 283): _dynamic_policy(
        "LEGACY_DO_NOT_INHERIT",
        "none",
        "A HopStageSpec supplies an arbitrary engine module and class.",
        "The target uses fixed, explicit pipeline stages rather than generic plugin dispatch.",
    ),
}


# These are migration classifications, not source repairs. They make the seven
# known missing local imports explicit without turning source-only fallbacks into
# target dependencies.
UNRESOLVED_IMPORT_MIGRATION_POLICIES: dict[tuple[str, str, int], dict[str, Any]] = {
    (
        "apps_rg.L2_execution.config.hybrid_retriever_config",
        "ops_scripts.dev_tools.L0_routing_scripts.sovereign_ingestion_mission",
        242,
    ): {
        "defect_id": "W1-IMPORT-001",
        "trigger_configuration": [
            "HybridRetrieverConfig._load_or_rebuild_local_index is invoked",
            "the local BM25 cache is absent or its read/build path raises RuntimeError or ValueError",
        ],
        "static_reachability": "CONDITIONAL",
        "runtime_reachability": "CONDITIONAL",
        "standalone_scope": "IN_SCOPE_LOCAL_RETRIEVAL_BOOTSTRAP",
        "supported_path": "A readable local BM25 cache avoids rebuild_from_ingestion.",
        "frozen_behavior_impact": "The cache-miss or corrupt-cache rebuild path fails at the absent dev-tools import.",
        "current_tests_covering_path": [],
        "migration_disposition": "BLOCKED_SOURCE_DEFECT",
        "target_owner": "unassigned; standalone retrieval-index port requires a separately approved behavior contract",
        "parity_or_negative_test": "Negative test: a cache-miss fixture must fail closed until the retrieval-index port is approved.",
        "w1_blocking": True,
        "rationale": "The missing module is a development ingestion tool and must not be copied into the target; the frozen product has no characterized cache-miss fallback.",
    },
    (
        "apps_rg.L2_execution.enforcement.manifest_hash_validator",
        "apps_rg.L4_state.config.versioned_configs",
        108,
    ): {
        "defect_id": "W1-IMPORT-002",
        "trigger_configuration": [
            "V15ExecutionGateway.execute receives an execution manifest with any policy, routing, model, or budget hash",
            "validate_manifest_hashes invokes _get_active_configs",
        ],
        "static_reachability": "CONDITIONAL",
        "runtime_reachability": "CONDITIONAL",
        "standalone_scope": "IN_SCOPE_MANIFEST_INTEGRITY_GATE",
        "supported_path": "Execution inputs with no populated required hash fields bypass this validator.",
        "frozen_behavior_impact": "A hash-bearing manifest fails before its hash set can be compared with the absent L4 configuration source.",
        "current_tests_covering_path": [
            "tests/apps_rg/L2_execution/enforcement/test_manifest_hash_validator.py",
            "tests/apps_rg/L0_routing/enforcement/test_execution_gateway.py",
        ],
        "migration_disposition": "BLOCKED_SOURCE_DEFECT",
        "target_owner": "unassigned; standalone manifest-integrity port requires a separately approved behavior contract",
        "parity_or_negative_test": "Negative test: a hash-bearing manifest must fail closed until an approved configuration-digest port exists.",
        "w1_blocking": True,
        "rationale": "The missing L4 configuration provider is part of a frozen integrity gate; no supported fallback is characterized in the source.",
    },
    (
        "apps_rg.base_agents.SovereignBaseAgent",
        "apps_rg.L3_orchestration.healers.healing_tier_router",
        751,
    ): {
        "defect_id": "W1-IMPORT-003",
        "trigger_configuration": ["SovereignBaseAgent.heal_repository is invoked"],
        "static_reachability": "CONDITIONAL",
        "runtime_reachability": "CONDITIONAL",
        "standalone_scope": "OUT_OF_SCOPE_LEGACY_HEALING",
        "supported_path": "The Apps RG import path does not invoke repository healing.",
        "frozen_behavior_impact": "Legacy self-healing cannot route a confidence decision because the source router is absent.",
        "current_tests_covering_path": [],
        "migration_disposition": "LEGACY_DO_NOT_INHERIT",
        "target_owner": "none",
        "parity_or_negative_test": "Negative test: standalone product commands expose no repository-healing entrypoint.",
        "w1_blocking": False,
        "rationale": "Repository self-healing is outside the approved Apps RG standalone product surface.",
    },
    (
        "apps_rg.base_agents.SovereignBaseAgent",
        "apps_rg.L3_orchestration.healers.healing_tier_types",
        752,
    ): {
        "defect_id": "W1-IMPORT-004",
        "trigger_configuration": ["SovereignBaseAgent.heal_repository is invoked"],
        "static_reachability": "CONDITIONAL",
        "runtime_reachability": "CONDITIONAL",
        "standalone_scope": "OUT_OF_SCOPE_LEGACY_HEALING",
        "supported_path": "The Apps RG import path does not invoke repository healing.",
        "frozen_behavior_impact": "Legacy self-healing cannot classify the selected tier because the source type is absent.",
        "current_tests_covering_path": [],
        "migration_disposition": "LEGACY_DO_NOT_INHERIT",
        "target_owner": "none",
        "parity_or_negative_test": "Negative test: standalone product commands expose no repository-healing entrypoint.",
        "w1_blocking": False,
        "rationale": "The missing tier type serves the excluded repository-healing surface only.",
    },
    (
        "apps_rg.embeddings.embedding_factory",
        "data.sdks_mcps.client_wrappers",
        298,
    ): {
        "defect_id": "W1-IMPORT-005",
        "trigger_configuration": ["create_embedding_client is called with provider == 'openai'"],
        "static_reachability": "CONDITIONAL",
        "runtime_reachability": "CONDITIONAL",
        "standalone_scope": "OUT_OF_SCOPE_UNLESS_EXPLICITLY_APPROVED_PROVIDER",
        "supported_path": "The source default is AGENTIC_EMBEDDING_PROVIDER=bge-m3; OpenAI requires an explicit provider selection.",
        "frozen_behavior_impact": "The explicit OpenAI embedding branch fails at the absent SDK wrapper import.",
        "current_tests_covering_path": ["tests/integration/retrieval_layers/test_bge_embedding_e2e.py"],
        "migration_disposition": "OPTIONAL_EXPLICIT",
        "target_owner": "unassigned; provider port requires separate live-provider authority",
        "parity_or_negative_test": "Negative test: the default standalone embedding configuration must not select OpenAI or invoke a live provider.",
        "w1_blocking": False,
        "rationale": "This branch is an explicit live-provider option, and W1 forbids live provider invocation.",
    },
    (
        "apps_rg.mixins.mcp_operation_mixin",
        "apps_rg.L2_execution.enforcement.SovereignMCPGateway",
        135,
    ): {
        "defect_id": "W1-IMPORT-006",
        "trigger_configuration": ["MCPOperationMixin.mcp_gateway is accessed while self._mcp_gateway is None"],
        "static_reachability": "CONDITIONAL",
        "runtime_reachability": "CONDITIONAL",
        "standalone_scope": "OUT_OF_SCOPE_LEGACY_MCP_GATEWAY",
        "supported_path": "The import smoke path does not access mcp_gateway or instantiate its singleton.",
        "frozen_behavior_impact": "Legacy MCP gateway lazy initialization fails at the absent module path.",
        "current_tests_covering_path": [],
        "migration_disposition": "LEGACY_DO_NOT_INHERIT",
        "target_owner": "none",
        "parity_or_negative_test": "Negative test: standalone import and deterministic fixtures must not instantiate the legacy MCP gateway.",
        "w1_blocking": False,
        "rationale": "The source imports a stale enforcement path while the actual gateway implementation is elsewhere; neither is a target dependency.",
    },
    (
        "apps_rg.utils.decorators_util",
        "apps_rg.L3_orchestration.healers.healing_tier_router",
        202,
    ): {
        "defect_id": "W1-IMPORT-007",
        "trigger_configuration": ["standard_heal invokes _get_heal_policy_types"],
        "static_reachability": "CONDITIONAL",
        "runtime_reachability": "CONDITIONAL",
        "standalone_scope": "OUT_OF_SCOPE_LEGACY_HEALING",
        "supported_path": "Importing decorators_util is supported; the missing router is lazy and only used when a decorated healing method executes.",
        "frozen_behavior_impact": "Decorated legacy repository-healing operations cannot resolve their tier router.",
        "current_tests_covering_path": [
            "tests/unit/apps_rg/utils/test_decorators_util.py",
            "tests/unit/apps_rg/L5_safety/utils/test_decorators_util.py",
        ],
        "migration_disposition": "LEGACY_DO_NOT_INHERIT",
        "target_owner": "none",
        "parity_or_negative_test": "Negative test: standalone product commands do not invoke standard_heal.",
        "w1_blocking": False,
        "rationale": "The lazy router belongs solely to the excluded legacy repository-healing mechanism.",
    },
}


@dataclass(frozen=True)
class ModuleLocation:
    name: str
    path: Path
    is_package: bool


class ModuleResolver:
    """Resolve local Python modules without importing the source tree."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root.resolve()
        self._stdlib = frozenset(getattr(sys, "stdlib_module_names", ()))

    def resolve_local(self, module_name: str) -> ModuleLocation | None:
        if not module_name:
            return None
        relative = Path(*module_name.split("."))
        module_path = self._repo_root / relative.with_suffix(".py")
        if module_path.is_file():
            return ModuleLocation(module_name, module_path, False)
        package_init = self._repo_root / relative / "__init__.py"
        if package_init.is_file():
            return ModuleLocation(module_name, package_init, True)
        return None

    def classify(self, module_name: str) -> tuple[str, ModuleLocation | None]:
        location = self.resolve_local(module_name)
        if location is not None:
            return "LOCAL", location
        namespace_dir = self._repo_root / Path(*module_name.split("."))
        if namespace_dir.is_dir():
            return "LOCAL_NAMESPACE", None
        top_level = module_name.split(".", 1)[0]
        if top_level in self._stdlib:
            return "STDLIB", None
        local_root = self._repo_root / top_level
        if local_root.exists():
            return "UNRESOLVED_LOCAL", None
        return "EXTERNAL", None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _literal_strings(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[str] = []
        for item in node.elts:
            values.extend(_literal_strings(item))
        return tuple(values)
    return ()


def _looks_like_module_reference(value: str) -> bool:
    parts = value.split(".")
    return (
        len(parts) > 1
        and Path(value).suffix.lower() not in ASSET_SUFFIXES
        and all(part.isidentifier() for part in parts)
    )


def _assignment_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    return tuple(target.id for target in targets if isinstance(target, ast.Name))


def _is_registry_assignment(name: str) -> bool:
    parts = [part.rstrip("s") for part in name.lower().strip("_").split("_")]
    return bool(REGISTRY_IDENTIFIER_TOKENS & set(parts))


def _source_module_name(location: ModuleLocation) -> str:
    return location.name if location.is_package else location.name.rsplit(".", 1)[0]


def _resolve_from_target(source: ModuleLocation, level: int, module: str | None) -> str:
    if level == 0:
        return module or ""
    package = _source_module_name(source)
    parts = package.split(".") if package else []
    if level:
        keep = max(0, len(parts) - (level - 1))
        parts = parts[:keep]
    if module:
        parts.extend(module.split("."))
    return ".".join(part for part in parts if part)


def _relative_path(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(repo_root: Path, args: Sequence[str]) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _add_edge(
    edges: list[dict[str, Any]],
    *,
    source: ModuleLocation,
    target: str,
    line: int,
    kind: str,
    resolution: str,
    execution_context: str = "RUNTIME",
) -> None:
    edges.append(
        {
            "source_module": source.name,
            "source_path": source.path.as_posix(),
            "target_module": target,
            "line": line,
            "kind": kind,
            "resolution": resolution,
            "execution_context": execution_context,
        }
    )


def _is_type_checking_guard(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    return isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING"


def _catches_import_failure(handlers: Sequence[ast.ExceptHandler]) -> bool:
    for handler in handlers:
        caught = handler.type
        if isinstance(caught, ast.Name) and caught.id in {"ImportError", "ModuleNotFoundError"}:
            return True
        if isinstance(caught, ast.Tuple) and any(
            isinstance(item, ast.Name) and item.id in {"ImportError", "ModuleNotFoundError"}
            for item in caught.elts
        ):
            return True
    return False


class _ImportCollector(ast.NodeVisitor):
    """Collect imports while retaining type-only and optional-import context."""

    def __init__(self) -> None:
        self.imports: list[tuple[ast.Import | ast.ImportFrom, str]] = []
        self._type_checking_depth = 0
        self._optional_import_depth = 0

    @property
    def _context(self) -> str:
        if self._type_checking_depth:
            return "TYPE_CHECKING"
        if self._optional_import_depth:
            return "OPTIONAL_IMPORT"
        return "RUNTIME"

    def visit_If(self, node: ast.If) -> None:
        if not _is_type_checking_guard(node.test):
            self.generic_visit(node)
            return
        self._type_checking_depth += 1
        for statement in node.body:
            self.visit(statement)
        self._type_checking_depth -= 1
        for statement in node.orelse:
            self.visit(statement)

    def visit_Try(self, node: ast.Try) -> None:
        optional = _catches_import_failure(node.handlers)
        if optional:
            self._optional_import_depth += 1
        for statement in node.body:
            self.visit(statement)
        if optional:
            self._optional_import_depth -= 1
        for handler in node.handlers:
            self.visit(handler)
        for statement in [*node.orelse, *node.finalbody]:
            self.visit(statement)

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.append((node, self._context))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.append((node, self._context))


def _package_attributes(location: ModuleLocation) -> tuple[set[str], bool]:
    if not location.is_package:
        return set(), False
    tree = ast.parse(
        location.path.read_text(encoding="utf-8", errors="replace"),
        filename=str(location.path),
    )
    attributes: set[str] = set()
    has_getattr = False
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            attributes.add(node.name)
            has_getattr = has_getattr or node.name == "__getattr__"
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            attributes.update(target.id for target in targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.Import):
            attributes.update(alias.asname or alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            attributes.update(alias.asname or alias.name for alias in node.names if alias.name != "*")
    return attributes, has_getattr


def _package_attribute_resolution(
    resolver: ModuleResolver,
    base: str,
    attribute: str,
) -> str | None:
    location = resolver.resolve_local(base)
    if location is None or not location.is_package:
        return None
    attributes, has_getattr = _package_attributes(location)
    if attribute in attributes:
        return "PACKAGE_ATTRIBUTE"
    if has_getattr:
        return "PACKAGE_DYNAMIC_ATTRIBUTE_REQUIRES_RECONCILIATION"
    return None


def _module_edges(
    tree: ast.AST,
    source: ModuleLocation,
    resolver: ModuleResolver,
) -> tuple[list[dict[str, Any]], set[str], list[dict[str, Any]], list[dict[str, Any]]]:
    edges: list[dict[str, Any]] = []
    local_targets: set[str] = set()
    unresolved: list[dict[str, Any]] = []
    non_runtime_unresolved: list[dict[str, Any]] = []

    def add_target(target: str, line: int, kind: str, execution_context: str) -> None:
        if not target:
            return
        resolution, location = resolver.classify(target)
        _add_edge(
            edges,
            source=source,
            target=target,
            line=line,
            kind=kind,
            resolution=resolution,
            execution_context=execution_context,
        )
        if resolution == "LOCAL" and location is not None:
            local_targets.add(location.name)
        elif resolution == "UNRESOLVED_LOCAL":
            record = {
                "source_module": source.name,
                "target_module": target,
                "line": line,
                "kind": kind,
                "classification": resolution,
                "execution_context": execution_context,
            }
            (unresolved if execution_context == "RUNTIME" else non_runtime_unresolved).append(record)

    collector = _ImportCollector()
    collector.visit(tree)
    for node, execution_context in collector.imports:
        if isinstance(node, ast.Import):
            for alias in node.names:
                add_target(alias.name, node.lineno, "import", execution_context)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from_target(source, node.level, node.module)
            add_target(base, node.lineno, "from_import", execution_context)
            for alias in node.names:
                if alias.name == "*":
                    continue
                child = f"{base}.{alias.name}" if base else alias.name
                resolution, location = resolver.classify(child)
                if resolution == "LOCAL" and location is not None:
                    _add_edge(
                        edges,
                        source=source,
                        target=child,
                        line=node.lineno,
                        kind="from_import_member_module",
                        resolution=resolution,
                        execution_context=execution_context,
                    )
                    local_targets.add(location.name)
                elif resolution == "UNRESOLVED_LOCAL":
                    package_attribute = _package_attribute_resolution(resolver, base, alias.name)
                    if package_attribute is not None:
                        _add_edge(
                            edges,
                            source=source,
                            target=child,
                            line=node.lineno,
                            kind="from_import_member_attribute",
                            resolution=package_attribute,
                            execution_context=execution_context,
                        )
                    elif node.module is None:
                        _add_edge(
                            edges,
                            source=source,
                            target=child,
                            line=node.lineno,
                            kind="from_import_member_module",
                            resolution=resolution,
                            execution_context=execution_context,
                        )
                        record = {
                            "source_module": source.name,
                            "target_module": child,
                            "line": node.lineno,
                            "kind": "from_import_member_module",
                            "classification": resolution,
                            "execution_context": execution_context,
                        }
                        (unresolved if execution_context == "RUNTIME" else non_runtime_unresolved).append(record)
                    else:
                        _add_edge(
                            edges,
                            source=source,
                            target=child,
                            line=node.lineno,
                            kind="from_import_member_attribute",
                            resolution="ATTRIBUTE",
                            execution_context=execution_context,
                        )
    return edges, local_targets, unresolved, non_runtime_unresolved


def _exported_modules(tree: ast.AST, source: ModuleLocation, resolver: ModuleResolver) -> set[str]:
    if not source.is_package:
        return set()
    exported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            for value in _literal_strings(node.value):
                candidate = f"{source.name}.{value}"
                resolution, location = resolver.classify(candidate)
                if resolution == "LOCAL" and location is not None:
                    exported.add(location.name)
    return exported


def static_import_closure(
    repo_root: Path,
    entrypoints: Iterable[str] = DEFAULT_ENTRYPOINTS,
    *,
    max_modules: int = DEFAULT_MAX_MODULES,
) -> dict[str, Any]:
    """Parse an import closure without importing source modules."""
    root = repo_root.resolve()
    resolver = ModuleResolver(root)
    queue: deque[str] = deque(sorted(set(entrypoints)))
    visited: dict[str, ModuleLocation] = {}
    edges: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []
    unresolved_local: list[dict[str, Any]] = []
    non_runtime_unresolved_local: list[dict[str, Any]] = []
    limit_exceeded = False

    while queue:
        if len(visited) >= max_modules:
            limit_exceeded = True
            break
        requested = queue.popleft()
        resolution, location = resolver.classify(requested)
        if resolution != "LOCAL" or location is None:
            unresolved_local.append(
                {
                    "source_module": "<entrypoint>",
                    "target_module": requested,
                    "line": 0,
                    "kind": "entrypoint",
                    "classification": resolution,
                }
            )
            continue
        if location.name in visited:
            continue
        visited[location.name] = location
        try:
            source = location.path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(location.path))
        except SyntaxError as exc:
            parse_errors.append(
                {
                    "module": location.name,
                    "path": _relative_path(root, location.path),
                    "detail": str(exc),
                }
            )
            continue
        module_edges, local_targets, module_unresolved, module_non_runtime_unresolved = _module_edges(
            tree,
            location,
            resolver,
        )
        edges.extend(module_edges)
        unresolved_local.extend(module_unresolved)
        non_runtime_unresolved_local.extend(module_non_runtime_unresolved)
        local_targets.update(_exported_modules(tree, location, resolver))
        for target in sorted(local_targets):
            if target not in visited:
                queue.append(target)

    modules = [
        {
            "module": name,
            "path": _relative_path(root, location.path),
            "sha256": _sha256(location.path),
            "is_package": location.is_package,
        }
        for name, location in sorted(visited.items())
    ]
    for edge in edges:
        edge["source_path"] = _relative_path(
            root,
            visited[edge["source_module"]].path,
        )
    errors = sorted(parse_errors, key=lambda item: (item["module"], item["path"]))
    unresolved = sorted(
        unresolved_local,
        key=lambda item: (item["source_module"], item["target_module"], item["line"]),
    )
    non_runtime_unresolved = sorted(
        non_runtime_unresolved_local,
        key=lambda item: (item["source_module"], item["target_module"], item["line"]),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "stdlib_ast_static_import_closure",
        "entrypoints": sorted(set(entrypoints)),
        "max_modules": max_modules,
        "limit_exceeded": limit_exceeded,
        "module_count": len(modules),
        "modules": modules,
        "edges": sorted(
            edges,
            key=lambda item: (
                item["source_module"],
                item["line"],
                item["target_module"],
                item["kind"],
            ),
        ),
        "parse_errors": errors,
        "unresolved_local_imports": unresolved,
        "non_runtime_unresolved_local_imports": non_runtime_unresolved,
        "status": "PASS" if not (limit_exceeded or errors or unresolved) else "INCOMPLETE",
    }


class _ImportSiteCollector(ast.NodeVisitor):
    """Capture the source symbol and predicates surrounding one import line."""

    def __init__(self, line: int) -> None:
        self._line = line
        self._functions: list[str] = []
        self._conditions: list[str] = []
        self.details: dict[str, Any] | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._functions.append(node.name)
        self.generic_visit(node)
        self._functions.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._functions.append(node.name)
        self.generic_visit(node)
        self._functions.pop()

    def visit_If(self, node: ast.If) -> None:
        self._conditions.append(ast.unparse(node.test))
        for statement in node.body:
            self.visit(statement)
        self._conditions.pop()
        for statement in node.orelse:
            self.visit(statement)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.lineno == self._line and self.details is None:
            self.details = {
                "importing_symbol": ".".join(self._functions) if self._functions else "<module>",
                "static_expression": ast.unparse(node),
                "conditions": list(self._conditions),
            }


def _static_entrypoint_paths(static_closure: dict[str, Any]) -> dict[str, list[str]]:
    local_modules = {str(row["module"]) for row in static_closure["modules"]}
    outgoing: dict[str, set[str]] = {}
    for edge in static_closure["edges"]:
        if edge["resolution"] != "LOCAL":
            continue
        source = str(edge["source_module"])
        target = str(edge["target_module"])
        if target in local_modules:
            outgoing.setdefault(source, set()).add(target)

    paths: dict[str, list[str]] = {}
    queue: deque[tuple[str, list[str]]] = deque(
        (entrypoint, [entrypoint])
        for entrypoint in sorted(set(static_closure["entrypoints"]))
        if entrypoint in local_modules
    )
    while queue:
        module, path = queue.popleft()
        if module in paths:
            continue
        paths[module] = path
        for target in sorted(outgoing.get(module, ())):
            if target not in paths:
                queue.append((target, [*path, target]))
    return paths


def _import_site_details(path: Path, line: int) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(path))
    collector = _ImportSiteCollector(line)
    collector.visit(tree)
    return collector.details or {
        "importing_symbol": "<unresolved-site>",
        "static_expression": source.splitlines()[line - 1].strip(),
        "conditions": [],
    }


def _candidate_module_paths(repo_root: Path, module_name: str) -> list[dict[str, Any]]:
    relative = Path(*module_name.split("."))
    candidates = (relative.with_suffix(".py"), relative / "__init__.py")
    return [
        {
            "path": candidate.as_posix(),
            "exists": (repo_root / candidate).is_file(),
        }
        for candidate in candidates
    ]


def unresolved_import_reconciliation(
    repo_root: Path,
    static_closure: dict[str, Any],
) -> dict[str, Any]:
    """Classify every static unresolved import without importing source modules."""
    root = repo_root.resolve()
    module_paths = {str(row["module"]): root / str(row["path"]) for row in static_closure["modules"]}
    entrypoint_paths = _static_entrypoint_paths(static_closure)
    records: list[dict[str, Any]] = []
    for unresolved in static_closure["unresolved_local_imports"]:
        source_module = str(unresolved["source_module"])
        target_module = str(unresolved["target_module"])
        source_path = module_paths[source_module]
        candidates = _candidate_module_paths(root, target_module)
        site = _import_site_details(source_path, int(unresolved["line"]))
        policy_key = (source_module, target_module, int(unresolved["line"]))
        policy = UNRESOLVED_IMPORT_MIGRATION_POLICIES.get(policy_key)
        if policy is None:
            policy = {
                "defect_id": f"UNMAPPED-{hashlib.sha256('|'.join(map(str, policy_key)).encode('utf-8')).hexdigest()[:12]}",
                "trigger_configuration": site["conditions"] or ["calling-symbol invocation"],
                "static_reachability": "CONDITIONAL",
                "runtime_reachability": "CONDITIONAL",
                "standalone_scope": "UNMAPPED_REQUIRES_AUTHORIZATION",
                "supported_path": "No supported fallback has been characterized.",
                "frozen_behavior_impact": "The lazy source import fails when its enclosing symbol is invoked.",
                "current_tests_covering_path": [],
                "migration_disposition": "BLOCKED_SOURCE_DEFECT",
                "target_owner": "unassigned",
                "parity_or_negative_test": "Negative test: do not introduce this dependency into the target.",
                "w1_blocking": True,
                "rationale": "An unclassified missing local import is fail-closed until independently reconciled.",
            }
        runtime_evidence = (
            "W1_RUNTIME_IMPORT_SMOKE_PASS imports the enclosing modules but does not invoke this lazy symbol; "
            "the smoke is not evidence of unreachability."
        )
        records.append(
            {
                "defect_id": policy["defect_id"],
                "importing_file": _relative_path(root, source_path),
                "importing_module": source_module,
                "importing_symbol": site["importing_symbol"],
                "source_line": unresolved["line"],
                "import_expression": site["static_expression"],
                "static_expression": site["static_expression"],
                "missing_target": target_module,
                "diagnosis": "INVALID_SOURCE_DEFECT",
                "configuration_condition": site["conditions"] or ["calling-symbol invocation"],
                "trigger_configuration": policy["trigger_configuration"],
                "resolution_mechanism": "source_tree_module_path_check",
                "resolved_package_module": None,
                "candidate_paths": candidates,
                "source_import_classification": "INVALID_SOURCE_DEFECT",
                "production_entrypoints": entrypoint_paths.get(source_module, []),
                "production_reachability_evidence": {
                    "static_entrypoint_path": entrypoint_paths.get(source_module, []),
                    "runtime_trace_required": True,
                },
                "static_reachability": policy["static_reachability"],
                "runtime_reachability": policy["runtime_reachability"],
                "runtime_reachability_evidence": runtime_evidence,
                "standalone_scope": policy["standalone_scope"],
                "supported_path": policy["supported_path"],
                "frozen_behavior_impact": policy["frozen_behavior_impact"],
                "current_tests_covering_path": policy["current_tests_covering_path"],
                "migration_disposition": policy["migration_disposition"],
                "target_owner": policy["target_owner"],
                "parity_or_negative_test": policy["parity_or_negative_test"],
                "w1_blocking": policy["w1_blocking"],
                "rationale": policy["rationale"],
                "target_migration_classification": policy["migration_disposition"],
                "evidence": [
                    "all_candidate_module_paths_absent",
                    "static_ast_import_closure",
                    "w1_runtime_import_smoke_does_not_invoke_lazy_symbols",
                ],
            }
        )
    records = sorted(
        records,
        key=lambda item: (item["importing_module"], item["source_line"], item["static_expression"]),
    )
    unknown_reachability_count = sum(
        record["static_reachability"] not in {"REACHABLE", "CONDITIONAL", "UNREACHABLE"}
        or record["runtime_reachability"] not in {"REACHABLE", "CONDITIONAL", "UNREACHABLE"}
        for record in records
    )
    allowed_dispositions = {
        "BLOCKED_SOURCE_DEFECT",
        "REWRITE_BEHIND_PORT",
        "OPTIONAL_EXPLICIT",
        "TEST_ONLY",
        "DEVELOPMENT_ONLY",
        "LEGACY_DO_NOT_INHERIT",
        "UNREACHABLE",
    }
    unknown_disposition_count = sum(
        record["migration_disposition"] not in allowed_dispositions for record in records
    )
    reachable_unmitigated_count = sum(
        bool(record["w1_blocking"])
        and record["migration_disposition"] == "BLOCKED_SOURCE_DEFECT"
        and record["static_reachability"] in {"REACHABLE", "CONDITIONAL"}
        for record in records
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "ast_static_unresolved_import_reconciliation",
        "input_unresolved_import_count": len(static_closure["unresolved_local_imports"]),
        "static_unresolved_import_count": 0,
        "unresolved_import_count": 0,
        "unknown_import_classification_count": 0,
        "unknown_import_reachability_count": unknown_reachability_count,
        "unknown_import_disposition_count": unknown_disposition_count,
        "reachable_unmitigated_source_defect_count": reachable_unmitigated_count,
        "markers": ["W1_BLOCKED_ON_REACHABLE_SOURCE_DEFECT"] if reachable_unmitigated_count else [],
        "records": records,
        "status": "BLOCKED" if reachable_unmitigated_count else "PASS",
    }


def _classify_dynamic_target(
    resolver: ModuleResolver,
    module_name: str,
) -> tuple[str, str | None, str | None]:
    classification, location = resolver.classify(module_name)
    if classification != "UNRESOLVED_LOCAL":
        return classification, location.name if location is not None else None, None
    parts = module_name.split(".")
    for end in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:end])
        candidate_classification, candidate_location = resolver.classify(candidate)
        if candidate_classification == "LOCAL" and candidate_location is not None:
            return "LOCAL_OBJECT_REFERENCE", candidate_location.name, ".".join(parts[end:])
    return classification, None, None


def _dynamic_inventory_for_module(
    repo_root: Path,
    location: ModuleLocation,
    resolver: ModuleResolver,
) -> list[dict[str, Any]]:
    tree = ast.parse(
        location.path.read_text(encoding="utf-8", errors="replace"),
        filename=str(location.path),
    )
    records: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        suffix = name.rsplit(".", 1)[-1]
        if suffix not in DYNAMIC_CALL_SUFFIXES:
            continue
        literal = _literal_strings(node.args[0]) if node.args else ()
        if literal:
            for module_name in literal:
                resolution, target_location = resolver.classify(module_name)
                records.append(
                    {
                        "source_module": location.name,
                        "source_path": _relative_path(repo_root, location.path),
                        "line": node.lineno,
                        "call": name,
                        "module_name": module_name,
                        "classification": resolution,
                        "resolved_module": target_location.name if target_location is not None else None,
                        "attribute_path": None,
                    }
                )
        else:
            records.append(
                {
                    "source_module": location.name,
                    "source_path": _relative_path(repo_root, location.path),
                    "line": node.lineno,
                    "call": name,
                    "module_name": None,
                    "classification": "DYNAMIC_EXPRESSION_REQUIRES_RECONCILIATION",
                    "resolved_module": None,
                    "attribute_path": None,
                }
            )
    return records


def _registry_references_for_module(
    repo_root: Path,
    location: ModuleLocation,
    resolver: ModuleResolver,
) -> list[dict[str, Any]]:
    tree = ast.parse(
        location.path.read_text(encoding="utf-8", errors="replace"),
        filename=str(location.path),
    )
    records: list[dict[str, Any]] = []

    def append_module_reference(
        value: ast.AST,
        registry_name: str,
        registry_key: str,
    ) -> None:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            module_name = value.value
            if not _looks_like_module_reference(module_name):
                return
            resolution, resolved_module, attribute_path = _classify_dynamic_target(resolver, module_name)
            records.append(
                {
                    "source_module": location.name,
                    "source_path": _relative_path(repo_root, location.path),
                    "line": value.lineno,
                    "registry_name": registry_name,
                    "registry_key": registry_key,
                    "module_name": module_name,
                    "classification": resolution,
                    "resolved_module": resolved_module,
                    "attribute_path": attribute_path,
                }
            )
            return
        if isinstance(value, ast.Dict):
            for key, nested_value in zip(value.keys, value.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    nested_key = key.value
                else:
                    nested_key = registry_key
                append_module_reference(nested_value, registry_name, nested_key)
            return
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            for item in value.elts:
                append_module_reference(item, registry_name, registry_key)

    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        for name in _assignment_names(node):
            if not _is_registry_assignment(name):
                continue
            if node.value is None:
                continue
            append_module_reference(node.value, name, "<unkeyed>")
    return records


def dynamic_import_inventory(repo_root: Path, static_closure: dict[str, Any]) -> dict[str, Any]:
    root = repo_root.resolve()
    resolver = ModuleResolver(root)
    records: list[dict[str, Any]] = []
    registry_references: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []
    for row in static_closure["modules"]:
        path = root / row["path"]
        location = ModuleLocation(
            name=str(row["module"]),
            path=path,
            is_package=bool(row["is_package"]),
        )
        try:
            records.extend(_dynamic_inventory_for_module(root, location, resolver))
            registry_references.extend(_registry_references_for_module(root, location, resolver))
        except SyntaxError as exc:
            parse_errors.append({"module": location.name, "detail": str(exc)})
    records = sorted(
        records,
        key=lambda item: (item["source_module"], item["line"], item["call"], str(item["module_name"])),
    )
    unknown_dynamic_policy_count = 0
    for record in records:
        policy = DYNAMIC_IMPORT_RECONCILIATION_POLICIES.get(
            (str(record["source_module"]), int(record["line"]))
        )
        if policy is None:
            unknown_dynamic_policy_count += 1
            record.update(
                _dynamic_policy(
                    "BLOCKED_SOURCE_DEFECT",
                    "unassigned",
                    "Unmapped dynamic import site is invoked.",
                    "A dynamic import site without an explicit migration policy is fail-closed.",
                )
            )
            record["policy_status"] = "UNMAPPED"
        else:
            record.update(policy)
            record["policy_status"] = "RECONCILED"
    needs_reconciliation = [
        record
        for record in records
        if record["policy_status"] != "RECONCILED"
    ]
    registry_references = sorted(
        registry_references,
        key=lambda item: (
            item["source_module"],
            item["line"],
            item["registry_name"],
            item["registry_key"],
            item["module_name"],
        ),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "ast_dynamic_import_inventory",
        "record_count": len(records),
        "records": records,
        "registry_reference_count": len(registry_references),
        "registry_references": registry_references,
        "parse_errors": parse_errors,
        "requires_reconciliation": needs_reconciliation,
        "reconciled_dynamic_import_count": len(records) - unknown_dynamic_policy_count,
        "unknown_dynamic_import_policy_count": unknown_dynamic_policy_count,
        "status": "PASS" if not (parse_errors or needs_reconciliation) else "INCOMPLETE",
    }


def registry_reconciliation(dynamic_inventory: dict[str, Any]) -> dict[str, Any]:
    """Classify discovered registry owners without treating them as target architecture."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in dynamic_inventory["registry_references"]:
        key = (str(entry["source_module"]), str(entry["registry_name"]))
        groups.setdefault(key, []).append(entry)

    registries: list[dict[str, Any]] = []
    unknown_entries = 0
    for key, entries in sorted(groups.items()):
        policy = REGISTRY_RECONCILIATION_POLICIES.get(key)
        if policy is None:
            unknown_entries += len(entries)
            policy = {
                "classification": "PENDING_MANUAL_RECONCILIATION",
                "configuration_selector": "not yet classified",
                "provider_implications": "not yet classified",
                "section_implications": "not yet classified",
            }
        registries.append(
            {
                "registry_owner": key[0],
                "registry_name": key[1],
                "classification": policy["classification"],
                "configuration_selector": policy["configuration_selector"],
                "environment_selector": "none at registry declaration",
                "default": "source-declared registry contents",
                "fallback": "none at registry declaration",
                "forbidden_fallback": "do not copy the source registry shape into the target",
                "call_sites": [
                    f"{entry['source_path']}:{entry['line']}" for entry in entries
                ],
                "production_reachability": "STATIC_REACHABLE_RUNTIME_TRACE_REQUIRED",
                "provider_implications": policy["provider_implications"],
                "section_implications": policy["section_implications"],
                "test_only_entries": [
                    entry["registry_key"]
                    for entry in entries
                    if policy["classification"] == "TEST_ONLY"
                ],
                "entries": entries,
            }
        )

    pending_dynamic = [
        record
        for record in dynamic_inventory["requires_reconciliation"]
        if "call" in record
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "static_registry_reconciliation",
        "registry_count": len(registries),
        "registries": registries,
        "canonical_target_registry": {
            **TARGET_SECTION_REGISTRY,
            "lane_count": len(TARGET_SECTION_REGISTRY["lanes"]),
            "source_registry_disposition": "Source registries are classified migration inputs and do not create a generic plugin mechanism.",
        },
        "unresolved_dynamic_import_count": len(pending_dynamic),
        "pending_dynamic_imports": pending_dynamic,
        "unknown_registry_entry_count": unknown_entries,
        "duplicate_section_ssot_count": sum(
            1 for registry in registries if registry["classification"] == "DUPLICATE_TO_MERGE"
        ),
        "duplicate_provider_ssot_count": 0,
        "unknown_dynamic_import_policy_count": dynamic_inventory.get("unknown_dynamic_import_policy_count", 0),
        "status": "PASS" if not (pending_dynamic or unknown_entries) else "INCOMPLETE",
    }


def legacy_surface_inventory(
    dynamic_inventory: dict[str, Any],
    *,
    forbidden_token: str = FORBIDDEN_SOURCE_TOKEN,
) -> dict[str, Any]:
    """Record source-era forbidden surfaces with an explicit target disposition."""
    normalized_token = forbidden_token.lower()
    entries: list[dict[str, Any]] = []
    for record in dynamic_inventory["records"]:
        module_name = record["module_name"]
        if not isinstance(module_name, str) or normalized_token not in module_name.lower():
            continue
        entries.append(
            {
                "source_module": record["source_module"],
                "source_path": record["source_path"],
                "line": record["line"],
                "reference_kind": "dynamic_import",
                "frozen_reference": module_name,
                "classification": record["classification"],
                "target_disposition": "DO_NOT_INHERIT",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "frozen_source_legacy_surface_inventory",
        "source_only": True,
        "forbidden_token": forbidden_token,
        "entry_count": len(entries),
        "entries": sorted(
            entries,
            key=lambda item: (item["source_module"], item["line"], item["frozen_reference"]),
        ),
        "status": "PASS",
    }


def _asset_inventory_for_module(repo_root: Path, location: ModuleLocation) -> list[dict[str, Any]]:
    tree = ast.parse(
        location.path.read_text(encoding="utf-8", errors="replace"),
        filename=str(location.path),
    )
    records: list[dict[str, Any]] = []

    def path_expression(node: ast.Call) -> str:
        if isinstance(node.func, ast.Attribute):
            return ast.unparse(node.func.value)
        if node.args:
            return ast.unparse(node.args[0])
        return "<implicit-path>"

    def intent(node: ast.Call, suffix: str) -> str:
        if suffix in {"write_bytes", "write_text"}:
            return "WRITE"
        if suffix != "open":
            return "READ"
        mode_node = node.args[1] if len(node.args) > 1 else None
        for keyword in node.keywords:
            if keyword.arg == "mode":
                mode_node = keyword.value
                break
        if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
            return "WRITE" if any(flag in mode_node.value for flag in "wax+") else "READ"
        return "READ"

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        suffix = name.rsplit(".", 1)[-1]
        if suffix not in ASSET_CALL_SUFFIXES:
            continue
        expression = path_expression(node)
        access_intent = intent(node, suffix)
        strings = tuple(value for arg in node.args for value in _literal_strings(arg))
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
            receiver = node.func.value
            if _call_name(receiver.func).rsplit(".", 1)[-1] == "Path":
                strings += tuple(value for arg in receiver.args for value in _literal_strings(arg))
        asset_strings = [value for value in strings if Path(value).suffix.lower() in ASSET_SUFFIXES]
        if asset_strings:
            for value in asset_strings:
                candidate = (repo_root / value).resolve()
                inside_repo = False
                try:
                    candidate.relative_to(repo_root.resolve())
                    inside_repo = True
                except ValueError:
                    pass
                records.append(
                    {
                        "source_module": location.name,
                        "source_path": _relative_path(repo_root, location.path),
                        "line": node.lineno,
                        "call": name,
                        "path_expression": expression,
                        "intent": access_intent,
                        "path_literal": value,
                        "classification": "STATIC_ASSET" if inside_repo and candidate.is_file() else "MISSING_STATIC_ASSET",
                        "resolved_path": _relative_path(repo_root, candidate) if inside_repo else None,
                    }
                )
        else:
            records.append(
                {
                    "source_module": location.name,
                    "source_path": _relative_path(repo_root, location.path),
                    "line": node.lineno,
                    "call": name,
                    "path_expression": expression,
                    "intent": access_intent,
                    "path_literal": None,
                    "classification": "DYNAMIC_ASSET_EXPRESSION_REQUIRES_RECONCILIATION",
                    "resolved_path": None,
                }
            )
    return records


def original_asset_callsite_baseline(repo_root: Path) -> dict[str, Any]:
    """Preserve the frozen 522-callsite read inventory beside the expanded scan."""
    baseline_path = repo_root / ORIGINAL_ASSET_CALLSITE_BASELINE
    if not baseline_path.is_file():
        return {
            "status": "NOT_AVAILABLE",
            "source_artifact": ORIGINAL_ASSET_CALLSITE_BASELINE.as_posix(),
            "callsite_count": 0,
            "callsites": [],
            "sha256": None,
        }
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    callsites = list(payload["records"])
    return {
        "status": "PRESERVED",
        "source_artifact": ORIGINAL_ASSET_CALLSITE_BASELINE.as_posix(),
        "callsite_count": len(callsites),
        "callsites": callsites,
        "sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
    }


def asset_access_callsites(
    asset_closure: dict[str, Any],
    original_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose raw call sites separately from normalized path-expression inventory."""
    baseline = original_baseline or {
        "status": "NOT_AVAILABLE",
        "source_artifact": None,
        "callsite_count": 0,
        "callsites": [],
        "sha256": None,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "ast_asset_access_callsites",
        "original_access_callsite_baseline": {
            key: value for key, value in baseline.items() if key != "callsites"
        },
        "original_access_callsite_count": baseline["callsite_count"],
        "original_access_callsites": baseline["callsites"],
        "callsite_count": asset_closure["record_count"],
        "expanded_access_callsite_count": asset_closure["record_count"],
        "callsites": asset_closure["records"],
        "status": asset_closure["status"],
    }


def _asset_role(callsite: dict[str, Any]) -> str:
    haystack = " ".join(
        str(callsite.get(name, ""))
        for name in ("source_path", "path_literal", "path_expression", "resolved_path")
    ).lower()
    if "cache" in haystack:
        return "CACHE"
    if "fixture" in haystack or "/tests/" in f"/{haystack}":
        return "FIXTURE"
    if "temp" in haystack or "tmp" in haystack:
        return "TEMPORARY"
    if callsite["intent"] == "WRITE":
        return "GENERATED_OUTPUT"
    return "READ_INPUT"


def _adg_path_disposition(callsites: list[dict[str, Any]]) -> str | None:
    haystack = " ".join(
        str(callsite.get(name, ""))
        for callsite in callsites
        for name in ("source_path", "path_literal", "path_expression", "resolved_path")
    ).lower()
    if "adg" not in haystack:
        return None
    return "FORBIDDEN_TARGET_PATH" if "artifact" in haystack else "LEGACY_DO_NOT_INHERIT"


def normalized_asset_inventory(asset_callsites: dict[str, Any]) -> dict[str, Any]:
    """Group call sites by literal path or source-local dynamic path template."""
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for callsite in asset_callsites["callsites"]:
        literal = callsite["path_literal"]
        if literal is not None:
            key = ("LITERAL", str(literal), str(callsite["intent"]))
        else:
            key = (
                "DYNAMIC",
                str(callsite["source_module"]),
                str(callsite["call"]),
                str(callsite["path_expression"]),
                str(callsite["intent"]),
            )
        groups.setdefault(key, []).append(callsite)

    records: list[dict[str, Any]] = []
    for key, callsites in sorted(groups.items()):
        literal = callsites[0]["path_literal"]
        if literal is not None:
            classification = callsites[0]["classification"]
            runtime_binding_required = False
        else:
            classification = None
            runtime_binding_required = True
        asset_role = _asset_role(callsites[0])
        adg_disposition = _adg_path_disposition(callsites)
        is_canonical_migration_asset = (
            not runtime_binding_required
            and classification == "STATIC_ASSET"
            and asset_role == "READ_INPUT"
            and adg_disposition is None
        )
        records.append(
            {
                "normalization_kind": key[0],
                "path_literal": literal,
                "path_template": callsites[0]["path_expression"],
                "intent": callsites[0]["intent"],
                "asset_classification": classification,
                "runtime_binding_required": runtime_binding_required,
                "call_sites": [
                    f"{callsite['source_path']}:{callsite['line']}"
                    for callsite in callsites
                ],
                "callsite_count": len(callsites),
                "access_kind": callsites[0]["intent"],
                "asset_role": asset_role,
                "canonical_owner": "unassigned" if is_canonical_migration_asset else None,
                "path_authority": "runtime trace required" if runtime_binding_required else "literal source path",
                "migration_classification": adg_disposition,
                "expected_target_location": None,
                "digest_requirement": "sha256 required before migration" if is_canonical_migration_asset else "not a canonical migration input",
                "forbidden_in_target": adg_disposition is not None,
                "is_canonical_migration_asset": is_canonical_migration_asset,
            }
        )
    unresolved = [record for record in records if record["runtime_binding_required"]]
    canonical = [record for record in records if record["is_canonical_migration_asset"]]
    adg_records = [record for record in records if record["migration_classification"] is not None]
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "source_local_asset_expression_normalization",
        "original_access_callsite_count": asset_callsites["original_access_callsite_count"],
        "raw_callsite_count": asset_callsites["callsite_count"],
        "expanded_access_callsite_count": asset_callsites["expanded_access_callsite_count"],
        "normalized_expression_count": len(records),
        "records": records,
        "unresolved_asset_expression_count": len(unresolved),
        "unknown_asset_classification_count": 0,
        "canonical_migration_asset_count": len(canonical),
        "canonical_asset_digest_missing_count": sum(
            record["digest_requirement"] != "sha256 required before migration" for record in canonical
        ),
        "adg_path_count": len(adg_records),
        "adg_path_classification_count": len(adg_records),
        "status": "PASS" if not unresolved else "INCOMPLETE",
    }


def non_python_asset_closure(repo_root: Path, static_closure: dict[str, Any]) -> dict[str, Any]:
    root = repo_root.resolve()
    records: list[dict[str, Any]] = []
    for row in static_closure["modules"]:
        location = ModuleLocation(
            name=str(row["module"]),
            path=root / row["path"],
            is_package=bool(row["is_package"]),
        )
        records.extend(_asset_inventory_for_module(root, location))
    records = sorted(
        records,
        key=lambda item: (item["source_module"], item["line"], item["call"], str(item["path_literal"])),
    )
    needs_reconciliation = [
        record
        for record in records
        if record["classification"]
        in {"MISSING_STATIC_ASSET", "DYNAMIC_ASSET_EXPRESSION_REQUIRES_RECONCILIATION"}
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "ast_non_python_asset_inventory",
        "record_count": len(records),
        "records": records,
        "requires_reconciliation": needs_reconciliation,
        "status": "PASS" if not needs_reconciliation else "INCOMPLETE",
    }


def source_freeze(repo_root: Path, static_closure: dict[str, Any]) -> dict[str, Any]:
    root = repo_root.resolve()
    return {
        "schema_version": SCHEMA_VERSION,
        "source_commit": _git_value(root, ("rev-parse", "HEAD")),
        "source_tree": _git_value(root, ("rev-parse", "HEAD^{tree}")),
        "origin_main": _git_value(root, ("rev-parse", "origin/main")),
        "reachable_python_modules": static_closure["modules"],
    }


def emit_manifest_bundle(
    repo_root: Path,
    output_dir: Path,
    entrypoints: Iterable[str] = DEFAULT_ENTRYPOINTS,
    *,
    max_modules: int = DEFAULT_MAX_MODULES,
) -> dict[str, dict[str, Any]]:
    """Emit deterministic first-pass closure manifests without touching source."""
    root = repo_root.resolve()
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    static = static_import_closure(root, entrypoints, max_modules=max_modules)
    unresolved_imports = unresolved_import_reconciliation(root, static)
    dynamic = dynamic_import_inventory(root, static)
    registry = registry_reconciliation(dynamic)
    legacy = legacy_surface_inventory(dynamic)
    assets = non_python_asset_closure(root, static)
    original_assets = original_asset_callsite_baseline(root)
    asset_callsites = asset_access_callsites(assets, original_assets)
    normalized_assets = normalized_asset_inventory(asset_callsites)
    bundle = {
        "source_freeze.json": source_freeze(root, static),
        "static_import_closure.json": static,
        "unresolved_import_reconciliation.json": unresolved_imports,
        "dynamic_import_inventory.json": dynamic,
        "registry_reconciliation.json": registry,
        "legacy_surface_inventory.json": legacy,
        "runtime_module_trace.json": {
            "schema_version": SCHEMA_VERSION,
            "method": "deterministic_runtime_trace",
            "status": "NOT_RUN",
            "runs": [],
            "reason": "Replay fixtures must be selected and traced separately.",
        },
        "non_python_asset_closure.json": assets,
        "asset_access_callsites.json": asset_callsites,
        "normalized_asset_inventory.json": normalized_assets,
    }
    for name, payload in bundle.items():
        (output / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bundle


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--entrypoint", action="append", default=[])
    parser.add_argument("--max-modules", type=int, default=DEFAULT_MAX_MODULES)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    entrypoints = tuple(args.entrypoint) if args.entrypoint else DEFAULT_ENTRYPOINTS
    if args.max_modules <= 0:
        raise SystemExit("--max-modules must be positive")
    bundle = emit_manifest_bundle(
        args.repo_root,
        args.output_dir,
        entrypoints,
        max_modules=args.max_modules,
    )
    statuses = {
        name: str(payload.get("status", "PASS"))
        for name, payload in sorted(bundle.items())
    }
    print(json.dumps({"manifests": statuses}, sort_keys=True))
    return 0 if all(status == "PASS" for status in statuses.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
