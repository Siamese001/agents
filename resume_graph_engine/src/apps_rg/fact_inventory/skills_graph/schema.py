"""Database DDL statements and registered graph types / epochs."""
from __future__ import annotations

CANONICAL_NODE_TYPES = frozenset(
    {
        "pillar",
        "skill",
        "fact",
        "role_family",
        "career_track",
        "career_epoch",
        "capability_domain",
        "employment",
        "locked_bullet",
        "certification",
        "section",
        "concept",
        "repo_evidence",
        "policy",
        "policy_rule",
        "graph_ref",
        "metric",
        "metric_bucket",
        # W2.0 (typed-edge-role-facet-guardrails-a6f3d2): first-class metric_outcome
        # nodes materialized from role_episode_bundle metric_outcome_nodes dicts.
        "metric_outcome",
    }
)

RAW_TO_CANONICAL_NODE_TYPE: dict[str, str] = {
    "atomic_proof_fact": "fact",
    "bullet_fact": "locked_bullet",
    "capability_domain": "capability_domain",
    "career_epoch": "career_epoch",
    "career_track": "career_track",
    "certification_evidence": "certification",
    "domain_pillar": "pillar",
    "employment": "employment",
    "experience_evidence": "employment",
    "external_claim_policy": "policy",
    "identity_north_star": "role_family",
    "metric": "metric",
    "metric_bucket": "metric_bucket",
    "policy": "policy",
    "policy_rule": "policy_rule",
    "repository_evidence": "repo_evidence",
    "resume_section_projection": "section",
    "skill": "skill",
    "skill_row": "skill",
    "source_concept": "concept",
    "targeting_input": "graph_ref",
}

CANONICAL_CAREER_EPOCHS: tuple[str, ...] = (
    "epoch_actuarial_financial_engineering",
    "epoch_enterprise_risk_governance",
    "epoch_cloud_data_platform_engineering",
    "epoch_partner_gtm_revenue_leadership",
    "epoch_agentic_ai_runtime_architecture",
    "epoch_ai_platform_commercialization",
)

EPOCH_ORDINAL: dict[str, int] = {
    "epoch_actuarial_financial_engineering": 1,
    "epoch_enterprise_risk_governance": 2,
    "epoch_cloud_data_platform_engineering": 3,
    "epoch_partner_gtm_revenue_leadership": 4,
    "epoch_agentic_ai_runtime_architecture": 5,
    "epoch_ai_platform_commercialization": 6,
}

ORDINAL_TO_EPOCH: dict[int, str] = {v: k for k, v in EPOCH_ORDINAL.items()}

EPOCH_LABELS: dict[str, str] = {
    "epoch_actuarial_financial_engineering": "Actuarial & Financial Engineering",
    "epoch_enterprise_risk_governance": "Enterprise Risk & Governance",
    "epoch_cloud_data_platform_engineering": "Cloud & Data Platform Engineering",
    "epoch_partner_gtm_revenue_leadership": "Partner GTM & Revenue Leadership",
    "epoch_agentic_ai_runtime_architecture": "Agentic AI Runtime Architecture",
    "epoch_ai_platform_commercialization": "AI Platform Commercialization",
}

P6_SKILLS: frozenset[str] = frozenset(
    {
        "skill_agentic_platform_productization",
        "skill_reusable_ai_ip_design",
        "skill_app_specific_runtime_overlay_design",
        "skill_enterprise_workflow_adoption",
        "skill_operating_model_for_agentic_ai",
        "skill_ai_platform_commercialization",
    }
)

LEGACY_SKILL_EPOCHS: dict[str, str] = {
    "skill_meddpicc_sales_qualification": "epoch_partner_gtm_revenue_leadership",
    "skill_cpq_deal_velocity_automation": "epoch_ai_platform_commercialization",
    "skill_soc2_zero_trust_security": "epoch_enterprise_risk_governance",
    "skill_saas_arr_ltv_cac_metrics": "epoch_ai_platform_commercialization",
    "skill_confluent_streaming_platforms": "epoch_cloud_data_platform_engineering",
    "skill_watson_studio_fraud_aml": "epoch_cloud_data_platform_engineering",
    "skill_nps_customer_health_scoring": "epoch_ai_platform_commercialization",
    "skill_credit_adjudication_default_risk": "epoch_enterprise_risk_governance",
}

EMPLOYMENT_PHASES: dict[str, tuple[int, int]] = {
    "employment_exp_early_career_001": (1, 1),
    "employment_exp_ey_001": (2, 2),
    "employment_exp_insurtech_001": (3, 3),
    "employment_exp_ibm_001": (3, 4),
    "employment_exp_unify_001": (5, 6),
}


DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS graph_nodes (
        node_id TEXT PRIMARY KEY CHECK (TRIM(node_id) <> ''),
        node_type TEXT NOT NULL CHECK (TRIM(node_type) <> ''),
        label TEXT NOT NULL CHECK (TRIM(label) <> ''),
        description TEXT NOT NULL DEFAULT '',
        activation_status TEXT NOT NULL DEFAULT '',
        support_level TEXT NOT NULL DEFAULT '',
        confidence TEXT NOT NULL DEFAULT '',
        external_eligible INTEGER NOT NULL DEFAULT 0 CHECK (external_eligible IN (0, 1)),
        career_epoch TEXT NOT NULL DEFAULT '',
        phase_ordinal INTEGER DEFAULT NULL,
        source_authority TEXT NOT NULL DEFAULT 'augmented_skills_graph',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS graph_edges (
        edge_id TEXT PRIMARY KEY CHECK (TRIM(edge_id) <> ''),
        source_node_id TEXT NOT NULL CHECK (TRIM(source_node_id) <> ''),
        target_node_id TEXT NOT NULL CHECK (TRIM(target_node_id) <> ''),
        edge_family TEXT NOT NULL DEFAULT '',
        edge_type TEXT NOT NULL CHECK (TRIM(edge_type) <> ''),
        weight REAL NOT NULL DEFAULT 1.0 CHECK (weight >= 0.0 AND weight <= 1.0),
        confidence TEXT NOT NULL DEFAULT '',
        directional INTEGER NOT NULL DEFAULT 1 CHECK (directional IN (0, 1)),
        evidence_status TEXT NOT NULL DEFAULT '',
        section_fit TEXT NOT NULL DEFAULT '',
        source_authority TEXT NOT NULL DEFAULT 'augmented_skills_graph',
        rationale TEXT NOT NULL DEFAULT '',
        projection_behavior TEXT NOT NULL DEFAULT '',
        external_claim_policy TEXT NOT NULL DEFAULT '',
        validation_status TEXT NOT NULL DEFAULT '',
        edge_note TEXT NOT NULL DEFAULT '',
        operator_note TEXT NOT NULL DEFAULT '',
        business_story TEXT NOT NULL DEFAULT '',
        technical_story TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (source_node_id) REFERENCES graph_nodes(node_id),
        FOREIGN KEY (target_node_id) REFERENCES graph_nodes(node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS skill_fact_links (
        skill_id TEXT NOT NULL,
        fact_id TEXT NOT NULL,
        support_level TEXT NOT NULL DEFAULT '',
        claim_eligibility INTEGER NOT NULL DEFAULT 0 CHECK (claim_eligibility IN (0, 1)),
        source_trace TEXT NOT NULL DEFAULT '',
        archive_trace TEXT NOT NULL DEFAULT '',
        human_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (human_confirmed IN (0, 1)),
        external_eligible INTEGER NOT NULL DEFAULT 0 CHECK (external_eligible IN (0, 1)),
        PRIMARY KEY (skill_id, fact_id),
        FOREIGN KEY (skill_id) REFERENCES graph_nodes(node_id),
        FOREIGN KEY (fact_id) REFERENCES graph_nodes(node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS section_eligibility (
        node_id TEXT NOT NULL,
        section_id TEXT NOT NULL,
        allowed INTEGER NOT NULL DEFAULT 0 CHECK (allowed IN (0, 1)),
        claim_policy TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL DEFAULT '',
        blocked_reason TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (node_id, section_id),
        FOREIGN KEY (node_id) REFERENCES graph_nodes(node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS role_family_projection (
        role_family_id TEXT PRIMARY KEY,
        projection_role_family_key TEXT NOT NULL,
        track_weight_profile TEXT NOT NULL DEFAULT '{}',
        taxonomy_source TEXT NOT NULL DEFAULT '',
        targeting_keywords TEXT NOT NULL DEFAULT '[]',
        proof_policy_note TEXT NOT NULL DEFAULT 'graph_routing_not_claim_proof'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS c03_skill_selection_features (
        skill_id TEXT PRIMARY KEY,
        pillar TEXT NOT NULL DEFAULT '',
        subpillar TEXT NOT NULL DEFAULT '',
        domain_id TEXT NOT NULL DEFAULT '',
        career_track_id TEXT NOT NULL DEFAULT '',
        career_epoch TEXT NOT NULL DEFAULT '',
        phase_ordinal INTEGER DEFAULT NULL,
        skill_family TEXT NOT NULL DEFAULT '',
        metric_bucket TEXT NOT NULL DEFAULT 'general_business_outcome',
        role_family_weights TEXT NOT NULL DEFAULT '{}',
        allowed_sections TEXT NOT NULL DEFAULT '[]',
        source_fact_count INTEGER NOT NULL DEFAULT 0,
        confidence TEXT NOT NULL DEFAULT '',
        activation_status TEXT NOT NULL DEFAULT '',
        support_level TEXT NOT NULL DEFAULT '',
        external_eligible INTEGER NOT NULL DEFAULT 0 CHECK (external_eligible IN (0, 1)),
        source_authority TEXT NOT NULL DEFAULT 'augmented_skills_graph',
        source_trace TEXT NOT NULL DEFAULT '[]',
        updated_at TEXT NOT NULL,
        FOREIGN KEY (skill_id) REFERENCES graph_nodes(node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS c03_role_family_skill_weights (
        skill_id TEXT NOT NULL,
        role_family_key TEXT NOT NULL,
        weight REAL NOT NULL DEFAULT 0.0 CHECK (weight >= 0.0),
        source TEXT NOT NULL DEFAULT 'skill_row.role_family_weights',
        PRIMARY KEY (skill_id, role_family_key),
        FOREIGN KEY (skill_id) REFERENCES graph_nodes(node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS graph_paths (
        path_id TEXT PRIMARY KEY,
        start_node_id TEXT NOT NULL,
        end_node_id TEXT NOT NULL,
        path_depth INTEGER NOT NULL CHECK (path_depth >= 1),
        path_signature TEXT NOT NULL,
        node_path_json TEXT NOT NULL
            CHECK (json_valid(node_path_json) AND json_type(node_path_json) = 'array'),
        edge_path_json TEXT NOT NULL
            CHECK (json_valid(edge_path_json) AND json_type(edge_path_json) = 'array'),
        edge_types_json TEXT NOT NULL
            CHECK (json_valid(edge_types_json) AND json_type(edge_types_json) = 'array'),
        proof_fact_ids_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(proof_fact_ids_json) AND json_type(proof_fact_ids_json) = 'array'),
        metric_ids_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(metric_ids_json) AND json_type(metric_ids_json) = 'array'),
        section_ids_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(section_ids_json) AND json_type(section_ids_json) = 'array'),
        path_score REAL NOT NULL DEFAULT 0.0,
        novelty_score REAL NOT NULL DEFAULT 0.0,
        proof_strength_score REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (start_node_id) REFERENCES graph_nodes(node_id),
        FOREIGN KEY (end_node_id) REFERENCES graph_nodes(node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS graph_neighborhoods (
        center_node_id TEXT NOT NULL,
        neighbor_node_id TEXT NOT NULL,
        distance INTEGER NOT NULL CHECK (distance >= 1),
        connecting_path_json TEXT NOT NULL
            CHECK (json_valid(connecting_path_json) AND json_type(connecting_path_json) = 'array'),
        edge_types_json TEXT NOT NULL
            CHECK (json_valid(edge_types_json) AND json_type(edge_types_json) = 'array'),
        relationship_summary TEXT NOT NULL DEFAULT '',
        neighbor_score REAL NOT NULL DEFAULT 0.0,
        PRIMARY KEY (center_node_id, neighbor_node_id, distance),
        CHECK (center_node_id <> neighbor_node_id),
        FOREIGN KEY (center_node_id) REFERENCES graph_nodes(node_id),
        FOREIGN KEY (neighbor_node_id) REFERENCES graph_nodes(node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS graph_sibling_links (
        node_id TEXT NOT NULL,
        sibling_node_id TEXT NOT NULL,
        sibling_reason TEXT NOT NULL DEFAULT '',
        shared_parent_node_id TEXT NOT NULL DEFAULT '',
        shared_edge_type TEXT NOT NULL DEFAULT '',
        sibling_score REAL NOT NULL DEFAULT 0.0,
        PRIMARY KEY (
            node_id, sibling_node_id, shared_parent_node_id, shared_edge_type
        ),
        CHECK (node_id <> sibling_node_id),
        FOREIGN KEY (node_id) REFERENCES graph_nodes(node_id),
        FOREIGN KEY (sibling_node_id) REFERENCES graph_nodes(node_id),
        FOREIGN KEY (shared_parent_node_id) REFERENCES graph_nodes(node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_metric_usage (
        run_id TEXT NOT NULL CHECK (TRIM(run_id) <> ''),
        resume_section TEXT NOT NULL CHECK (TRIM(resume_section) <> ''),
        metric_id TEXT NOT NULL CHECK (TRIM(metric_id) <> ''),
        metric_value TEXT NOT NULL DEFAULT '',
        fact_id TEXT NOT NULL DEFAULT '',
        skill_id TEXT NOT NULL DEFAULT '',
        role_family_key TEXT NOT NULL DEFAULT '',
        usage_count INTEGER NOT NULL DEFAULT 1 CHECK (usage_count >= 1),
        created_at TEXT NOT NULL,
        PRIMARY KEY (run_id, resume_section, metric_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS section_evidence_budget (
        section_id TEXT NOT NULL CHECK (TRIM(section_id) <> ''),
        role_family_key TEXT NOT NULL CHECK (TRIM(role_family_key) <> ''),
        max_metric_reuse INTEGER NOT NULL DEFAULT 1 CHECK (max_metric_reuse >= 0),
        max_fact_family_reuse INTEGER NOT NULL DEFAULT 2 CHECK (max_fact_family_reuse >= 0),
        required_node_types_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(required_node_types_json) AND json_type(required_node_types_json) = 'array'),
        preferred_edge_types_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(preferred_edge_types_json) AND json_type(preferred_edge_types_json) = 'array'),
        forbidden_metric_ids_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(forbidden_metric_ids_json) AND json_type(forbidden_metric_ids_json) = 'array'),
        preferred_metric_families_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(preferred_metric_families_json) AND json_type(preferred_metric_families_json) = 'array'),
        PRIMARY KEY (section_id, role_family_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS graph_selection_rejections (
        run_id TEXT NOT NULL CHECK (TRIM(run_id) <> ''),
        section_id TEXT NOT NULL CHECK (TRIM(section_id) <> ''),
        candidate_node_id TEXT NOT NULL CHECK (TRIM(candidate_node_id) <> ''),
        candidate_node_type TEXT NOT NULL CHECK (TRIM(candidate_node_type) <> ''),
        rejected_reason TEXT NOT NULL CHECK (TRIM(rejected_reason) <> ''),
        rejected_at_stage TEXT NOT NULL CHECK (TRIM(rejected_at_stage) <> ''),
        competing_selected_node_id TEXT NOT NULL DEFAULT '',
        path_signature TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        PRIMARY KEY (run_id, section_id, candidate_node_id, rejected_at_stage)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS graph_metadata (
        graph_version TEXT PRIMARY KEY,
        materialized_from TEXT NOT NULL,
        materialized_at TEXT NOT NULL,
        ledger_hash TEXT NOT NULL,
        graph_count_summary TEXT NOT NULL DEFAULT '{}',
        authority_status TEXT NOT NULL DEFAULT 'augmented_skills_graph_authoritative'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type)",
    "CREATE INDEX IF NOT EXISTS idx_graph_nodes_phase ON graph_nodes(phase_ordinal)",
    "CREATE INDEX IF NOT EXISTS idx_graph_nodes_epoch ON graph_nodes(career_epoch)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges(edge_type)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_src ON graph_edges(source_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_tgt ON graph_edges(target_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_src_type_tgt ON graph_edges(source_node_id, edge_type, target_node_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_graph_edges_src_tgt_type ON graph_edges(source_node_id, target_node_id, edge_type)",
    "CREATE INDEX IF NOT EXISTS idx_section_eligibility_section ON section_eligibility(section_id)",
    "CREATE INDEX IF NOT EXISTS idx_skill_fact_links_fact ON skill_fact_links(fact_id)",
    "CREATE INDEX IF NOT EXISTS idx_c03_skill_selection_metric ON c03_skill_selection_features(metric_bucket)",
    "CREATE INDEX IF NOT EXISTS idx_c03_skill_selection_pillar ON c03_skill_selection_features(pillar)",
    "CREATE INDEX IF NOT EXISTS idx_c03_skill_selection_family ON c03_skill_selection_features(skill_family)",
    "CREATE INDEX IF NOT EXISTS idx_c03_skill_selection_phase ON c03_skill_selection_features(phase_ordinal)",
    "CREATE INDEX IF NOT EXISTS idx_c03_skill_selection_epoch ON c03_skill_selection_features(career_epoch)",
    "CREATE INDEX IF NOT EXISTS idx_c03_role_family_skill_weights_role ON c03_role_family_skill_weights(role_family_key)",
    "CREATE INDEX IF NOT EXISTS idx_c03_role_family_skill_weights_skill ON c03_role_family_skill_weights(skill_id)",
    "CREATE INDEX IF NOT EXISTS idx_graph_paths_start ON graph_paths(start_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_graph_paths_end ON graph_paths(end_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_graph_paths_depth ON graph_paths(path_depth)",
    "CREATE INDEX IF NOT EXISTS idx_graph_paths_end_depth_score ON graph_paths(end_node_id, path_depth, path_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_neighborhood_center ON graph_neighborhoods(center_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_neighborhood_neighbor ON graph_neighborhoods(neighbor_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_neighborhood_distance ON graph_neighborhoods(distance)",
    "CREATE INDEX IF NOT EXISTS idx_neighborhood_center_distance_score ON graph_neighborhoods(center_node_id, distance, neighbor_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sibling_node ON graph_sibling_links(node_id)",
    "CREATE INDEX IF NOT EXISTS idx_sibling_peer ON graph_sibling_links(sibling_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_sibling_node_score ON graph_sibling_links(node_id, sibling_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sibling_context_lookup ON graph_sibling_links(node_id, sibling_node_id, shared_parent_node_id, shared_edge_type)",
    "CREATE INDEX IF NOT EXISTS idx_metric_usage_metric ON resume_metric_usage(metric_id)",
    "CREATE INDEX IF NOT EXISTS idx_metric_usage_section ON resume_metric_usage(resume_section)",
    "CREATE INDEX IF NOT EXISTS idx_metric_usage_fact ON resume_metric_usage(fact_id)",
    "CREATE INDEX IF NOT EXISTS idx_metric_usage_skill ON resume_metric_usage(skill_id)",
    "CREATE INDEX IF NOT EXISTS idx_metric_usage_role ON resume_metric_usage(role_family_key)",
    "CREATE INDEX IF NOT EXISTS idx_metric_usage_metric_section ON resume_metric_usage(metric_id, resume_section)",
    "CREATE INDEX IF NOT EXISTS idx_rejections_run_section ON graph_selection_rejections(run_id, section_id)",
    "CREATE INDEX IF NOT EXISTS idx_rejections_candidate ON graph_selection_rejections(candidate_node_id)",
    """
    CREATE VIEW IF NOT EXISTS graph_edges_reverse AS
    SELECT
        edge_id,
        target_node_id AS source_node_id,
        source_node_id AS target_node_id,
        edge_type || '_reverse' AS edge_type,
        edge_family,
        weight,
        confidence,
        evidence_status,
        section_fit,
        source_authority,
        rationale,
        projection_behavior,
        external_claim_policy,
        validation_status,
        edge_note,
        operator_note,
        business_story,
        technical_story
    FROM graph_edges
    """,
    """
    CREATE VIEW IF NOT EXISTS v_partner_architecture_competency_candidates AS
    SELECT
        w.skill_id,
        w.role_family_key,
        w.weight,
        f.pillar,
        f.subpillar,
        f.domain_id,
        f.skill_family,
        f.metric_bucket,
        n.label,
        n.confidence,
        n.activation_status,
        n.support_level,
        n.external_eligible,
        l.fact_id,
        l.claim_eligibility,
        l.external_eligible AS fact_external_eligible,
        se.allowed AS competencies_allowed
    FROM c03_role_family_skill_weights w
    JOIN c03_skill_selection_features f
      ON f.skill_id = w.skill_id
    JOIN graph_nodes n
      ON n.node_id = w.skill_id
     AND n.node_type = 'skill'
    JOIN section_eligibility se
      ON se.node_id = w.skill_id
     AND se.section_id = 'competencies'
     AND se.allowed = 1
    LEFT JOIN skill_fact_links l
      ON l.skill_id = w.skill_id
    WHERE w.role_family_key IN ('PARTNER_APPLIED_AI_ARCHITECTURE', 'ANTHROPIC_PARTNERSHIPS_APPLIED_AI')
      AND w.weight >= 0.80
      AND n.activation_status NOT IN ('DRAFT', 'INTERNAL_ONLY', 'DO_NOT_PROMOTE', 'BLOCKED')
      AND n.external_eligible = 1
      AND (
        f.pillar = 'pillar_applied_ai_partner_architecture'
        OR f.skill_family = 'pillar_applied_ai_partner_architecture'
        OR f.subpillar LIKE '%partner%'
        OR f.subpillar LIKE '%reference_architecture%'
        OR f.subpillar LIKE '%solution%'
      )
    """,
)


__all__ = [
    "CANONICAL_NODE_TYPES",
    "RAW_TO_CANONICAL_NODE_TYPE",
    "CANONICAL_CAREER_EPOCHS",
    "EPOCH_ORDINAL",
    "ORDINAL_TO_EPOCH",
    "EPOCH_LABELS",
    "P6_SKILLS",
    "LEGACY_SKILL_EPOCHS",
    "EMPLOYMENT_PHASES",
    "DDL_STATEMENTS",
]
