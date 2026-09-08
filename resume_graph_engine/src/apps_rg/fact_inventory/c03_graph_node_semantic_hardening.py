"""Deterministic W1 semantic hardening for canonical C0.3 graph nodes."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

NODE_SEMANTIC_CONTRACT_VERSION = "apps_rg.c03_graph_node_semantic_contract.v1"
NODE_SEMANTIC_HARDENING_WAVE = "C03_CLUSTER_EMBEDDING_W1"
W1_RECEIPT_SCHEMA_VERSION = "apps_rg.c03_cluster_embedding_w1_receipt.v1"
W1_COMPLETION_MARKER = "C03_CLUSTER_EMBEDDING_W1_NODE_SEMANTICS_HARDENED"

NODE_SEMANTIC_CONTRACT_PATH = Path(
    "src/apps_rg/fact_inventory/c03_graph_node_semantic_contract.v1.json"
)
GRAPH_PATH = Path("src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json")
CANDIDATE_FACT_LEDGER_PATH = Path(
    "artifacts/apps_rg/fact_inventory/"
    "master_candidate_skills_fact_ledger_20260518T1100Z.json"
)
BASE_RESUME_PATH = Path("src/apps_rg/resume/base/amit_ayer_base_resume_v1.json")
W0_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave0_baseline_receipt.json"
)
LEGACY_ARTIFACT_DIR = Path("artifacts/apps_rg/c03/graph_skill_embeddings")

CLAIM_NODE_TYPES = frozenset({"employment", "skill", "skill_row"})
STRUCTURAL_NODE_TYPES = frozenset(
    {
        "capability_domain",
        "career_epoch",
        "career_track",
        "domain_pillar",
        "identity_north_star",
        "metric",
        "metric_bucket",
    }
)
POLICY_NODE_TYPES = frozenset({"policy", "policy_rule"})
SEMANTIC_KIND_BY_NODE_TYPE = {
    **{node_type: "claim_assertion" for node_type in CLAIM_NODE_TYPES},
    **{node_type: "structural_definition" for node_type in STRUCTURAL_NODE_TYPES},
    **{node_type: "policy_predicate" for node_type in POLICY_NODE_TYPES},
}

_SEMANTIC_SENTINELS = frozenset(
    {
        "",
        "[",
        "]",
        "{",
        "}",
        "[]",
        "{}",
        "null",
        "none",
        "n/a",
        "tbd",
        "todo",
        "unknown",
    }
)
_FORBIDDEN_DESCRIPTION_PREFIXES = (
    "capability domain:",
    "career epoch:",
    "career track ",
    "c0.3 graph-skill granularity node for ",
)
_HELD_POLICIES = frozenset({"pending_source_internal_only"})
_HELD_SUPPORT_LEVELS = frozenset({"USER_CONFIRMED_PENDING_SOURCE"})

_INTERNAL_SKILL_DEFINITIONS = {
    "skill:c03:agentic_runtime_orchestration": (
        "Coordinates multi-agent execution, routing, handoffs, and completion controls "
        "across governed runtime stages."
    ),
    "skill:c03:agentic_policy_gate_design": (
        "Defines precondition and exit gates that evaluate policy, evidence, and runtime "
        "state before actions proceed."
    ),
    "skill:c03:agent_trace_observability": (
        "Captures replayable agent decisions, tool activity, gate verdicts, and evidence "
        "lineage for operational inspection."
    ),
    "skill:c03:graph_retrieval_traversal_design": (
        "Selects evidence by traversing registered graph relationships and rehydrating "
        "authoritative nodes and facts."
    ),
    "skill:c03:evidence_binding_provenance": (
        "Binds generated claims to exact graph nodes, facts, source lineage, and content "
        "digests."
    ),
    "skill:c03:retrieval_quality_guardrails": (
        "Constrains retrieval with eligibility, freshness, section, and rejection checks "
        "to prevent irrelevant or unauthorized evidence."
    ),
    "skill:c03:llm_platform_latency_engineering": (
        "Optimizes model-serving and orchestration paths to reduce end-to-end latency "
        "while preserving governed execution."
    ),
    "skill:c03:mlops_release_governance": (
        "Controls model and prompt releases through versioning, validation, approval, "
        "rollback, and audit evidence."
    ),
    "skill:c03:data_platform_lineage_architecture": (
        "Designs traceable data flows that retain source, transformation, ownership, and "
        "downstream-consumer lineage."
    ),
    "skill:c03:model_risk_control_design": (
        "Defines controls for model validation, monitoring, limitations, approvals, and "
        "risk escalation."
    ),
    "skill:c03:actuarial_ai_risk_translation": (
        "Translates actuarial and insurance risk concepts into governed AI requirements, "
        "controls, and decision criteria."
    ),
    "skill:c03:compliance_audit_readiness": (
        "Organizes evidence, controls, lineage, and ownership so regulated AI activity "
        "can be independently audited."
    ),
    "skill:c03:hyperscaler_partner_cosell": (
        "Coordinates joint solution positioning, seller alignment, pipeline ownership, "
        "and delivery responsibilities with hyperscaler partners."
    ),
    "skill:c03:ai_solution_value_story": (
        "Connects an AI solution's mechanism and buyer problem to evidence-backed "
        "commercial or operational outcomes."
    ),
    "skill:c03:enterprise_adoption_enablement": (
        "Coordinates stakeholders, enablement, operating-model changes, and rollout "
        "controls required for enterprise adoption."
    ),
    "skill:c03:delivery_governance_operating_rhythm": (
        "Defines recurring planning, risk review, dependency, metric, and escalation "
        "cadences for governed delivery."
    ),
}

_POLICY_DEFINITIONS = {
    "policy_external_claim_policy": (
        "Allows external claim projection only when the selected skill and claim are "
        "backed by active authorized evidence; otherwise projection is denied."
    ),
    "policy_skill_projection_not_proof": (
        "Treats skill projection as targeting and ranking context only; a skill identifier "
        "cannot independently prove a resume claim."
    ),
}


class GraphNodeSemanticHardeningError(RuntimeError):
    """Raised when W1 cannot deterministically harden or verify node semantics."""


def validate_node_semantic_contract(contract: Mapping[str, Any]) -> None:
    """Validate the frozen W1 target before applying graph mutations."""

    if contract.get("schema_version") != NODE_SEMANTIC_CONTRACT_VERSION:
        raise GraphNodeSemanticHardeningError(
            "W1 node semantic contract schema is invalid"
        )
    if contract.get("status") != "FROZEN":
        raise GraphNodeSemanticHardeningError("W1 node semantic contract is not frozen")
    if contract.get("semantic_kind_by_node_type") != SEMANTIC_KIND_BY_NODE_TYPE:
        raise GraphNodeSemanticHardeningError("W1 semantic kind registry is invalid")
    boundaries = contract.get("mutation_boundaries")
    if not isinstance(boundaries, Mapping):
        raise GraphNodeSemanticHardeningError("W1 mutation boundaries are missing")
    expected_boundaries = {
        "node_id_changes_allowed": False,
        "node_type_changes_allowed": False,
        "graph_edge_changes_allowed": False,
        "skill_row_identity_changes_allowed": False,
        "graph_hop_fact_missing_removal_allowed": True,
        "legacy_embedding_artifact_changes_allowed": False,
        "replacement_embedding_generation_allowed": False,
        "production_promotion_allowed": False,
    }
    for field, expected in expected_boundaries.items():
        if boundaries.get(field) is not expected:
            raise GraphNodeSemanticHardeningError(
                f"W1 mutation boundary is invalid: {field}"
            )


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _walk_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_objects(child)


def _evidence_index(
    candidate_fact_payload: Mapping[str, Any],
    base_resume_payload: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for raw in candidate_fact_payload.get("candidate_facts") or []:
        if not isinstance(raw, dict):
            continue
        fact_id = str(raw.get("candidate_fact_id") or "").strip()
        if fact_id:
            index[fact_id] = raw
    id_keys = {
        "bullet_id",
        "candidate_fact_id",
        "certification_id",
        "evidence_id",
        "fact_id",
    }
    for raw in _walk_objects(base_resume_payload):
        for key in id_keys:
            source_id = str(raw.get(key) or "").strip()
            if source_id and source_id not in index:
                index[source_id] = raw
    return index


def _evidence_summary(raw: Mapping[str, Any]) -> str:
    for key in (
        "proof_text",
        "claim_text",
        "text",
        "bullet",
        "description",
        "name",
        "title",
    ):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return ""


def _semantic_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _is_generic_description(node: Mapping[str, Any], description: str) -> bool:
    normalized = description.strip()
    lowered = normalized.lower()
    if lowered in _SEMANTIC_SENTINELS or len(normalized) < 24:
        return True
    if any(lowered.startswith(prefix) for prefix in _FORBIDDEN_DESCRIPTION_PREFIXES):
        return True
    description_key = _semantic_key(normalized)
    return description_key in {
        _semantic_key(node.get("node_id")),
        _semantic_key(node.get("label")),
    }


def _format_members(values: list[str], *, limit: int = 4) -> str:
    unique = sorted({value.strip() for value in values if value.strip()})
    if not unique:
        return "its registered graph members"
    visible = unique[:limit]
    rendered = ", ".join(visible)
    remaining = len(unique) - len(visible)
    if remaining:
        rendered += f", and {remaining} more"
    return rendered


def _member_labels(
    node_id: str,
    *,
    edges: list[dict[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
    edge_types: set[str],
    outgoing: bool = True,
) -> list[str]:
    labels: list[str] = []
    for edge in edges:
        if str(edge.get("edge_type") or "") not in edge_types:
            continue
        source = str(edge.get("source_node_id") or "")
        target = str(edge.get("target_node_id") or "")
        member_id = target if outgoing and source == node_id else source
        if outgoing and source != node_id:
            continue
        if not outgoing and target != node_id:
            continue
        member = nodes.get(member_id)
        if member:
            labels.append(str(member.get("label") or member_id))
    return labels


def _is_held_skill(row: Mapping[str, Any]) -> bool:
    return bool(
        str(row.get("support_level") or "") in _HELD_SUPPORT_LEVELS
        or str(row.get("external_claim_policy") or "") in _HELD_POLICIES
        or row.get("human_confirmation_required") is True
    )


def _skill_description(
    node: Mapping[str, Any],
    row: Mapping[str, Any],
    evidence: Mapping[str, Mapping[str, Any]],
) -> str:
    node_id = str(node.get("node_id") or "")
    label = str(node.get("label") or row.get("capability") or node_id).strip()
    if _is_held_skill(row):
        epoch = str(row.get("career_epoch") or "the registered career context")
        return (
            f"Held internal capability candidate for {label} in {epoch}; it cannot "
            "support an external claim until its pending-source policy is cleared."
        )
    manual = _INTERNAL_SKILL_DEFINITIONS.get(node_id)
    if manual:
        return manual
    current = str(node.get("description") or "").strip()
    if not _is_generic_description(node, current):
        return current
    for snippet in row.get("source_snippets") or []:
        value = str(snippet or "").strip()
        if value and value.lower() not in _SEMANTIC_SENTINELS:
            if not value.lower().startswith("c0.3 graph-skill granularity"):
                return value
    for fact_id in row.get("fact_id_links") or []:
        raw = evidence.get(str(fact_id))
        if raw:
            summary = _evidence_summary(raw)
            if summary:
                return summary
    raise GraphNodeSemanticHardeningError(
        f"{node_id}: no concrete evidence-backed skill description is available"
    )


def _structural_description(
    node: Mapping[str, Any],
    *,
    edges: list[dict[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
) -> str:
    node_id = str(node.get("node_id") or "")
    node_type = str(node.get("node_type") or "")
    label = str(node.get("label") or node_id).strip()
    current = str(node.get("description") or "").strip().rstrip(".")
    if node_type == "capability_domain":
        members = _member_labels(
            node_id,
            edges=edges,
            nodes=nodes,
            edge_types={"capability_domain_contains_skill"},
        )
        return (
            f"Defines the {label} capability boundary for {_format_members(members)}; "
            "membership is limited to registered capability-domain edges."
        )
    if node_type == "career_epoch":
        pillars = _member_labels(
            node_id,
            edges=edges,
            nodes=nodes,
            edge_types={"epoch_contains_pillar"},
        )
        return (
            f"Organizes the {label} career phase around {_format_members(pillars)}; "
            "the epoch scopes chronology and does not independently prove a claim."
        )
    if node_type == "career_track":
        epochs = _member_labels(
            node_id,
            edges=edges,
            nodes=nodes,
            edge_types={"career_track_contains_epoch"},
        )
        start = str(node.get("start_year") or "unspecified start")
        end = str(node.get("end_year") or "present")
        return (
            f"Defines the operator-confirmed {start}-{end} career sequence spanning "
            f"{_format_members(epochs)}; ordering is chronological and non-causal."
        )
    if node_type == "metric":
        bucket = str(node.get("bucket") or "registered")
        unit = str(node.get("unit") or "its registered unit")
        return (
            f"Defines {label} as an internal {bucket} outcome option measured in {unit}; "
            "it can surface only through an authorized metric edge and linked fact."
        )
    if node_type == "metric_bucket":
        metrics = _member_labels(
            node_id,
            edges=edges,
            nodes=nodes,
            edge_types={"metric_bucket_contains_metric"},
        )
        return (
            f"Groups internal {label} outcome options including {_format_members(metrics)}; "
            "membership is limited to registered metric-bucket edges."
        )
    if node_type == "domain_pillar":
        base = current if not _is_generic_description(node, current) else label
        return (
            f"{base}. This pillar is a taxonomy boundary; external claims still require "
            "linked evidence authority."
        )
    if node_type == "identity_north_star":
        base = current if not _is_generic_description(node, current) else label
        return (
            f"{base}. This identity anchor organizes graph selection and is not independent "
            "claim proof."
        )
    raise GraphNodeSemanticHardeningError(
        f"{node_id}: unsupported structural node type {node_type}"
    )


def _employment_description(node: Mapping[str, Any]) -> str:
    current = str(node.get("description") or "").strip()
    if not _is_generic_description(node, current):
        return current
    title = str(node.get("title") or node.get("label") or "role")
    employer = str(node.get("employer") or "the registered employer")
    start = str(node.get("start_date") or node.get("start_year") or "registered start")
    end = str(node.get("end_date") or node.get("end_year") or "present")
    return (
        f"Served as {title} at {employer} from {start} to {end}, within the scope "
        "recorded by the linked experience evidence."
    )


def _policy_description(node: Mapping[str, Any]) -> str:
    node_id = str(node.get("node_id") or "")
    manual = _POLICY_DEFINITIONS.get(node_id)
    if manual:
        return manual
    current = str(node.get("description") or "").strip()
    if _is_generic_description(node, current):
        raise GraphNodeSemanticHardeningError(
            f"{node_id}: policy predicate is not concrete"
        )
    return current


def _claim_authority_refs(
    node: Mapping[str, Any],
    row: Mapping[str, Any] | None,
) -> list[str]:
    refs: set[str] = set()
    node_id = str(node.get("node_id") or "")
    source_fact_id = str(node.get("source_fact_id") or "").strip()
    if source_fact_id:
        refs.add(source_fact_id)
    if row:
        refs.update(_strings(row.get("fact_id_links")))
        for field in ("source_resume_files", "repo_evidence_files"):
            refs.update(
                ref
                for ref in _strings(row.get(field))
                if _is_concrete_source_locator(ref)
            )
        refs.discard(str(row.get("skill_id") or ""))
    if refs:
        return sorted(refs)
    if row:
        return [f"ledger:skill_rows/{node_id}"]
    return [f"ledger:graph_nodes/{node_id}"]


def _is_concrete_source_locator(value: str) -> bool:
    normalized = value.strip().lower()
    return bool(
        "/" in normalized
        or "\\" in normalized
        or normalized.endswith(
            (".doc", ".docx", ".json", ".md", ".pdf", ".py", ".txt", ".yaml", ".yml")
        )
    )


def _authority_refs(
    node: Mapping[str, Any],
    row: Mapping[str, Any] | None,
) -> list[str]:
    node_type = str(node.get("node_type") or "")
    node_id = str(node.get("node_id") or "")
    if node_type in CLAIM_NODE_TYPES:
        return _claim_authority_refs(node, row)
    refs = set(_strings(node.get("source_refs")))
    refs.add(f"ledger:graph_nodes/{node_id}")
    return sorted(refs)


def _description_for_node(
    node: Mapping[str, Any],
    *,
    row: Mapping[str, Any] | None,
    evidence: Mapping[str, Mapping[str, Any]],
    edges: list[dict[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
) -> str:
    node_type = str(node.get("node_type") or "")
    if node_type in {"skill", "skill_row"}:
        if row is None:
            raise GraphNodeSemanticHardeningError(
                f"{node.get('node_id')}: claim node has no canonical skill row"
            )
        return _skill_description(node, row, evidence)
    if node_type == "employment":
        return _employment_description(node)
    if node_type in STRUCTURAL_NODE_TYPES:
        return _structural_description(node, edges=edges, nodes=nodes)
    if node_type in POLICY_NODE_TYPES:
        return _policy_description(node)
    raise GraphNodeSemanticHardeningError(
        f"{node.get('node_id')}: unregistered semantic node type {node_type}"
    )


def harden_graph_node_semantics(
    graph_payload: Mapping[str, Any],
    *,
    candidate_fact_payload: Mapping[str, Any],
    base_resume_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deterministic W1 graph with node semantics hardened."""

    output = copy.deepcopy(dict(graph_payload))
    graph_metadata = output.get("graph_metadata")
    if not isinstance(graph_metadata, dict):
        raise GraphNodeSemanticHardeningError("graph_metadata must be an object")
    existing_marker = graph_metadata.get("node_semantic_hardening")
    if (
        isinstance(existing_marker, dict)
        and existing_marker.get("contract_version") == NODE_SEMANTIC_CONTRACT_VERSION
    ):
        issues = collect_graph_node_semantic_issues(output)
        if issues:
            raise GraphNodeSemanticHardeningError(
                f"existing W1 hardening marker is invalid: {issues[:5]}"
            )
        return output

    raw_nodes = output.get("graph_nodes")
    raw_edges = output.get("graph_edges")
    raw_rows = output.get("skill_rows")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise GraphNodeSemanticHardeningError("graph nodes and edges must be lists")
    if not isinstance(raw_rows, list):
        raise GraphNodeSemanticHardeningError("skill_rows must be a list")
    nodes = [dict(node) for node in raw_nodes if isinstance(node, dict)]
    edges = [dict(edge) for edge in raw_edges if isinstance(edge, dict)]
    rows = [dict(row) for row in raw_rows if isinstance(row, dict)]
    if len(nodes) != len(raw_nodes) or len(edges) != len(raw_edges):
        raise GraphNodeSemanticHardeningError(
            "graph contains non-object nodes or edges"
        )
    if len(rows) != len(raw_rows):
        raise GraphNodeSemanticHardeningError("skill_rows contains non-object rows")

    node_by_id = {str(node.get("node_id") or ""): node for node in nodes}
    row_by_id = {str(row.get("skill_id") or ""): row for row in rows}
    evidence = _evidence_index(candidate_fact_payload, base_resume_payload)
    edge_sha256_before = canonical_sha256(edges)
    description_change_count = 0
    held_count = 0

    for node in nodes:
        node_id = str(node.get("node_id") or "")
        node_type = str(node.get("node_type") or "")
        row = row_by_id.get(node_id)
        description = _description_for_node(
            node,
            row=row,
            evidence=evidence,
            edges=edges,
            nodes=node_by_id,
        ).strip()
        if description != str(node.get("description") or "").strip():
            description_change_count += 1
        held = bool(node_type in {"skill", "skill_row"} and row and _is_held_skill(row))
        if held:
            held_count += 1
        node["description"] = description
        node["semantic_contract_version"] = NODE_SEMANTIC_CONTRACT_VERSION
        node["semantic_kind"] = SEMANTIC_KIND_BY_NODE_TYPE[node_type]
        node["canonical_assertion_text"] = description
        node["authority_refs"] = _authority_refs(node, row)
        node["semantic_hardening_status"] = "HELD_INTERNAL_ONLY" if held else "HARDENED"
        node["hardening_wave"] = NODE_SEMANTIC_HARDENING_WAVE

    fact_missing_removed_count = 0
    for row in rows:
        path = row.get("graph_hop_path")
        if not isinstance(path, list):
            continue
        cleaned = [
            value for value in path if str(value or "").strip() != "fact_missing"
        ]
        fact_missing_removed_count += len(path) - len(cleaned)
        row["graph_hop_path"] = cleaned

    output["graph_nodes"] = nodes
    output["skill_rows"] = rows
    edge_sha256_after = canonical_sha256(output["graph_edges"])
    if edge_sha256_after != edge_sha256_before:
        raise GraphNodeSemanticHardeningError("W1 changed canonical graph edges")
    graph_metadata["node_semantic_contract_version"] = NODE_SEMANTIC_CONTRACT_VERSION
    graph_metadata["legacy_skill_embedding_status"] = (
        "STALE_FAIL_CLOSED_AFTER_W1_NODE_SEMANTIC_HARDENING"
    )
    graph_metadata["node_semantic_hardening"] = {
        "contract_version": NODE_SEMANTIC_CONTRACT_VERSION,
        "wave_id": NODE_SEMANTIC_HARDENING_WAVE,
        "node_count": len(nodes),
        "hardened_node_count": len(nodes) - held_count,
        "held_internal_only_node_count": held_count,
        "description_change_count": description_change_count,
        "fact_missing_removed_count": fact_missing_removed_count,
        "edge_count": len(edges),
        "graph_edges_sha256_before": edge_sha256_before,
        "graph_edges_sha256_after": edge_sha256_after,
        "skill_row_count": len(rows),
        "production_promotion_authorized": False,
    }
    issues = collect_graph_node_semantic_issues(output)
    if issues:
        raise GraphNodeSemanticHardeningError(
            f"W1 node semantic hardening failed: {issues[:12]}"
        )
    return output


def _allowed_authority_refs(
    node: Mapping[str, Any],
    row: Mapping[str, Any] | None,
) -> set[str]:
    node_id = str(node.get("node_id") or "")
    allowed = set(_strings(node.get("source_refs")))
    source_fact_id = str(node.get("source_fact_id") or "").strip()
    if source_fact_id:
        allowed.add(source_fact_id)
    allowed.add(f"ledger:graph_nodes/{node_id}")
    if row:
        for field in (
            "fact_id_links",
            "source_resume_files",
            "repo_evidence_files",
        ):
            allowed.update(_strings(row.get(field)))
        allowed.add(f"ledger:skill_rows/{node_id}")
    return allowed


def _add_issue(issues: list[str], code: str, offenders: Iterable[Any]) -> None:
    values = sorted({str(value) for value in offenders if str(value).strip()})
    if values:
        issues.append(f"{code}: count={len(values)} offenders={values[:12]}")


def collect_graph_node_semantic_issues(graph_payload: Mapping[str, Any]) -> list[str]:
    """Return deterministic W1 semantic issues for every canonical graph node."""

    issues: list[str] = []
    nodes = list(graph_payload.get("graph_nodes") or [])
    rows = list(graph_payload.get("skill_rows") or [])
    graph_metadata = graph_payload.get("graph_metadata")
    marker = (
        graph_metadata.get("node_semantic_hardening")
        if isinstance(graph_metadata, Mapping)
        else None
    )
    if not isinstance(marker, Mapping):
        return ["GRAPH_NODE_SEMANTIC_HARDENING_MARKER_MISSING"]
    row_by_id = {
        str(row.get("skill_id") or ""): row for row in rows if isinstance(row, dict)
    }

    missing_fields: list[str] = []
    kind_mismatch: list[str] = []
    generic_descriptions: list[str] = []
    text_mismatch: list[str] = []
    invalid_refs: list[str] = []
    unresolved_refs: list[str] = []
    invalid_status: list[str] = []
    claim_without_evidence: list[str] = []
    invalid_hold: list[str] = []
    held_count = 0
    required_fields = (
        "semantic_contract_version",
        "semantic_kind",
        "canonical_assertion_text",
        "authority_refs",
        "semantic_hardening_status",
        "hardening_wave",
    )
    for index, raw_node in enumerate(nodes):
        if not isinstance(raw_node, dict):
            continue
        node = raw_node
        node_id = str(node.get("node_id") or f"graph_nodes[{index}]")
        node_type = str(node.get("node_type") or "")
        row = row_by_id.get(node_id)
        for field in required_fields:
            value = node.get(field)
            if value is None or value == "" or value == []:
                missing_fields.append(f"{node_id}.{field}")
        if node.get("semantic_contract_version") != NODE_SEMANTIC_CONTRACT_VERSION:
            missing_fields.append(f"{node_id}.semantic_contract_version")
        if node.get("hardening_wave") != NODE_SEMANTIC_HARDENING_WAVE:
            missing_fields.append(f"{node_id}.hardening_wave")
        if node.get("semantic_kind") != SEMANTIC_KIND_BY_NODE_TYPE.get(node_type):
            kind_mismatch.append(node_id)
        description = str(node.get("description") or "").strip()
        assertion_text = str(node.get("canonical_assertion_text") or "").strip()
        if _is_generic_description(node, description):
            generic_descriptions.append(node_id)
        if description != assertion_text:
            text_mismatch.append(node_id)
        refs = node.get("authority_refs")
        if not isinstance(refs, list) or refs != sorted(set(_strings(refs))):
            invalid_refs.append(node_id)
            normalized_refs: list[str] = []
        else:
            normalized_refs = _strings(refs)
        allowed_refs = _allowed_authority_refs(node, row)
        unresolved_refs.extend(
            f"{node_id}={ref}" for ref in normalized_refs if ref not in allowed_refs
        )
        status = str(node.get("semantic_hardening_status") or "")
        if status not in {"HARDENED", "HELD_INTERNAL_ONLY"}:
            invalid_status.append(node_id)
        if node_type in CLAIM_NODE_TYPES:
            non_ledger_refs = [
                ref for ref in normalized_refs if not ref.startswith("ledger:")
            ]
            if status == "HARDENED" and not non_ledger_refs:
                claim_without_evidence.append(node_id)
            if status == "HELD_INTERNAL_ONLY":
                held_count += 1
                retrieval_eligible = (
                    row.get("retrieval_eligible")
                    if row
                    else node.get("retrieval_eligible")
                )
                if retrieval_eligible is not False:
                    invalid_hold.append(node_id)

    _add_issue(issues, "GRAPH_NODE_SEMANTIC_FIELD_MISSING", missing_fields)
    _add_issue(issues, "GRAPH_NODE_SEMANTIC_KIND_MISMATCH", kind_mismatch)
    _add_issue(issues, "GRAPH_NODE_DESCRIPTION_NOT_CONCRETE", generic_descriptions)
    _add_issue(issues, "GRAPH_NODE_ASSERTION_TEXT_MISMATCH", text_mismatch)
    _add_issue(issues, "GRAPH_NODE_AUTHORITY_REFS_INVALID", invalid_refs)
    _add_issue(issues, "GRAPH_NODE_AUTHORITY_REF_UNRESOLVED", unresolved_refs)
    _add_issue(issues, "GRAPH_NODE_SEMANTIC_STATUS_INVALID", invalid_status)
    _add_issue(issues, "GRAPH_NODE_CLAIM_WITHOUT_EVIDENCE", claim_without_evidence)
    _add_issue(issues, "GRAPH_NODE_HELD_STATUS_INVALID", invalid_hold)

    fact_missing_rows = [
        str(row.get("skill_id") or "")
        for row in rows
        if isinstance(row, dict)
        and "fact_missing" in [str(value) for value in row.get("graph_hop_path") or []]
    ]
    _add_issue(issues, "GRAPH_HOP_PATH_AUTHORITY_SENTINEL", fact_missing_rows)

    reconciliation_marker = (
        graph_metadata.get("authority_reconciliation")
        if isinstance(graph_metadata, Mapping)
        else None
    )
    expected_edge_count = (
        reconciliation_marker.get("source_edge_count")
        if isinstance(reconciliation_marker, Mapping)
        else len(graph_payload.get("graph_edges") or [])
    )
    expected_counts = {
        "node_count": len(nodes),
        "hardened_node_count": len(nodes) - held_count,
        "held_internal_only_node_count": held_count,
        "edge_count": expected_edge_count,
        "skill_row_count": len(rows),
    }
    marker_mismatches = [
        f"{field}={marker.get(field)}!=expected:{expected}"
        for field, expected in expected_counts.items()
        if marker.get(field) != expected
    ]
    if marker.get("contract_version") != NODE_SEMANTIC_CONTRACT_VERSION:
        marker_mismatches.append("contract_version")
    if marker.get("wave_id") != NODE_SEMANTIC_HARDENING_WAVE:
        marker_mismatches.append("wave_id")
    if isinstance(reconciliation_marker, Mapping) and reconciliation_marker.get(
        "source_w1_marker_sha256"
    ) != canonical_sha256(marker):
        marker_mismatches.append("source_w1_marker_sha256")
    edge_digest = canonical_sha256(graph_payload.get("graph_edges") or [])
    edge_marker = (
        graph_metadata.get("edge_semantic_hardening")
        if isinstance(graph_metadata, Mapping)
        else None
    )
    expected_w1_edge_digest = (
        str(edge_marker.get("source_graph_edges_sha256") or "")
        if isinstance(edge_marker, Mapping)
        else edge_digest
    )
    if marker.get("graph_edges_sha256_before") != expected_w1_edge_digest:
        marker_mismatches.append("graph_edges_sha256_before")
    if marker.get("graph_edges_sha256_after") != expected_w1_edge_digest:
        marker_mismatches.append("graph_edges_sha256_after")
    if marker.get("production_promotion_authorized") is not False:
        marker_mismatches.append("production_promotion_authorized")
    _add_issue(issues, "GRAPH_NODE_SEMANTIC_MARKER_MISMATCH", marker_mismatches)
    return issues


def semantic_profile(graph_payload: Mapping[str, Any]) -> dict[str, Any]:
    nodes = [
        node
        for node in graph_payload.get("graph_nodes") or []
        if isinstance(node, dict)
    ]
    rows = [
        row for row in graph_payload.get("skill_rows") or [] if isinstance(row, dict)
    ]
    generic = [
        str(node.get("node_id") or "")
        for node in nodes
        if _is_generic_description(node, str(node.get("description") or ""))
    ]
    sentinel = [
        str(node.get("node_id") or "")
        for node in nodes
        if str(node.get("description") or "").strip().lower() in _SEMANTIC_SENTINELS
    ]
    held = [
        str(node.get("node_id") or "")
        for node in nodes
        if node.get("semantic_hardening_status") == "HELD_INTERNAL_ONLY"
    ]
    fact_missing = [
        str(row.get("skill_id") or "")
        for row in rows
        if "fact_missing" in [str(value) for value in row.get("graph_hop_path") or []]
    ]
    return {
        "node_count": len(nodes),
        "edge_count": len(graph_payload.get("graph_edges") or []),
        "skill_row_count": len(rows),
        "node_type_counts": dict(
            sorted(Counter(str(node.get("node_type") or "") for node in nodes).items())
        ),
        "sentinel_description_count": len(sentinel),
        "generic_description_count": len(generic),
        "held_internal_only_node_count": len(held),
        "fact_missing_graph_hop_count": len(fact_missing),
        "semantic_issue_count": (
            len(collect_graph_node_semantic_issues(graph_payload))
            if isinstance(
                (graph_payload.get("graph_metadata") or {}).get(
                    "node_semantic_hardening"
                ),
                Mapping,
            )
            else None
        ),
        "graph_edges_sha256": canonical_sha256(graph_payload.get("graph_edges") or []),
    }


def build_w1_receipt(
    *,
    before_graph: Mapping[str, Any],
    after_graph: Mapping[str, Any],
    w0_receipt: Mapping[str, Any],
    contract: Mapping[str, Any],
    legacy_artifacts: list[Mapping[str, Any]],
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    """Build the W1 completion receipt from exact before/after authority bytes."""

    validate_node_semantic_contract(contract)
    issues = collect_graph_node_semantic_issues(after_graph)
    if issues:
        raise GraphNodeSemanticHardeningError(
            f"cannot receipt invalid W1 graph: {issues}"
        )
    before_profile = semantic_profile(before_graph)
    after_profile = semantic_profile(after_graph)
    before_nodes = {
        str(node.get("node_id") or ""): node
        for node in before_graph.get("graph_nodes") or []
        if isinstance(node, dict)
    }
    after_nodes = {
        str(node.get("node_id") or ""): node
        for node in after_graph.get("graph_nodes") or []
        if isinstance(node, dict)
    }
    changed_descriptions = sorted(
        node_id
        for node_id, node in after_nodes.items()
        if str(node.get("description") or "")
        != str(before_nodes.get(node_id, {}).get("description") or "")
    )
    receipt: dict[str, Any] = {
        "schema_version": W1_RECEIPT_SCHEMA_VERSION,
        "wave_id": NODE_SEMANTIC_HARDENING_WAVE,
        "status": "PASS",
        "completion_marker": W1_COMPLETION_MARKER,
        "source_baseline": {
            "commit": source_commit,
            "tree": source_tree,
            "wave0_receipt_sha256": str(w0_receipt.get("receipt_sha256") or ""),
        },
        "contract": {
            "path": NODE_SEMANTIC_CONTRACT_PATH.as_posix(),
            "schema_version": contract.get("schema_version"),
            "canonical_sha256": canonical_sha256(contract),
        },
        "scope": {
            "repository": "apps_rg_v2",
            "node_semantics_hardened": True,
            "graph_edges_changed": False,
            "legacy_embedding_artifacts_changed": False,
            "replacement_vectors_generated": False,
            "production_promotion_authorized": False,
        },
        "before": {
            "graph_canonical_sha256": canonical_sha256(before_graph),
            "semantic_profile": before_profile,
        },
        "after": {
            "graph_canonical_sha256": canonical_sha256(after_graph),
            "semantic_profile": after_profile,
            "changed_description_count": len(changed_descriptions),
            "changed_description_samples": changed_descriptions[:20],
        },
        "preservation": {
            "node_id_set_preserved": set(before_nodes) == set(after_nodes),
            "node_count_preserved": len(before_nodes) == len(after_nodes),
            "edge_count_preserved": before_profile["edge_count"]
            == after_profile["edge_count"],
            "edge_digest_preserved": before_profile["graph_edges_sha256"]
            == after_profile["graph_edges_sha256"],
            "skill_row_count_preserved": before_profile["skill_row_count"]
            == after_profile["skill_row_count"],
        },
        "legacy_embedding_artifacts": {
            "status": "STALE_FAIL_CLOSED_UNCHANGED_PENDING_W5_RETIREMENT",
            "artifact_count": len(legacy_artifacts),
            "artifacts": [dict(record) for record in legacy_artifacts],
        },
        "wave_exit_gates": {
            "node_semantic_hardening": "PASS",
            "authority_reference_resolution": "PASS",
            "fact_missing_sentinel_removal": "PASS",
            "edge_digest_preservation": "PASS",
            "edge_assertion_hardening": "OPEN_W2",
            "authority_reconciliation": "OPEN_W3",
            "cluster_registry_materialization": "OPEN_W4",
            "legacy_artifact_retirement": "OPEN_W5",
            "cluster_embedding_generation": "OPEN_W6",
        },
        "next_wave": "C03_CLUSTER_EMBEDDING_W2_EDGE_ASSERTION_HARDENING",
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    validate_w1_receipt(receipt)
    return receipt


def validate_w1_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema_version") != W1_RECEIPT_SCHEMA_VERSION:
        raise GraphNodeSemanticHardeningError("W1 receipt schema is invalid")
    if receipt.get("status") != "PASS" or receipt.get("completion_marker") != (
        W1_COMPLETION_MARKER
    ):
        raise GraphNodeSemanticHardeningError("W1 completion truth is invalid")
    scope = receipt.get("scope")
    if not isinstance(scope, Mapping):
        raise GraphNodeSemanticHardeningError("W1 scope is missing")
    expected_scope = {
        "node_semantics_hardened": True,
        "graph_edges_changed": False,
        "legacy_embedding_artifacts_changed": False,
        "replacement_vectors_generated": False,
        "production_promotion_authorized": False,
    }
    for field, expected in expected_scope.items():
        if scope.get(field) is not expected:
            raise GraphNodeSemanticHardeningError(
                f"W1 scope claim is invalid: {field} must be {expected}"
            )
    preservation = receipt.get("preservation")
    if not isinstance(preservation, Mapping) or not all(
        preservation.get(field) is True
        for field in (
            "node_id_set_preserved",
            "node_count_preserved",
            "edge_count_preserved",
            "edge_digest_preserved",
            "skill_row_count_preserved",
        )
    ):
        raise GraphNodeSemanticHardeningError("W1 preservation contract failed")
    after_profile = (receipt.get("after") or {}).get("semantic_profile")
    if not isinstance(after_profile, Mapping):
        raise GraphNodeSemanticHardeningError("W1 after profile is missing")
    for field in (
        "sentinel_description_count",
        "generic_description_count",
        "fact_missing_graph_hop_count",
        "semantic_issue_count",
    ):
        if after_profile.get(field) != 0:
            raise GraphNodeSemanticHardeningError(
                f"W1 semantic exit gate failed: {field}={after_profile.get(field)}"
            )
    legacy = receipt.get("legacy_embedding_artifacts")
    if not isinstance(legacy, Mapping) or legacy.get("artifact_count") != 13:
        raise GraphNodeSemanticHardeningError(
            "W1 legacy artifact inventory is incomplete"
        )
    unsigned = dict(receipt)
    recorded = str(unsigned.pop("receipt_sha256", "") or "")
    observed = canonical_sha256(unsigned)
    if not recorded or recorded != observed:
        raise GraphNodeSemanticHardeningError(
            f"W1 receipt digest mismatch: expected {observed}, observed {recorded}"
        )


__all__ = [
    "GraphNodeSemanticHardeningError",
    "NODE_SEMANTIC_CONTRACT_VERSION",
    "NODE_SEMANTIC_HARDENING_WAVE",
    "W1_COMPLETION_MARKER",
    "W1_RECEIPT_SCHEMA_VERSION",
    "build_w1_receipt",
    "canonical_sha256",
    "collect_graph_node_semantic_issues",
    "file_sha256",
    "harden_graph_node_semantics",
    "semantic_profile",
    "validate_node_semantic_contract",
    "validate_w1_receipt",
]
