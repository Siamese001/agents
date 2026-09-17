"""Augment master_skills_arsenal_ledger.json with 15 deep agentic build skills.

Derived from architectural review of /Users/amitayer/Git/decision-intelligence-engine.
Adds skills to epoch_agentic_ai_runtime_architecture (Phase 5, phase_ordinal: 5).
Wires domain containment, epoch containment, section eligibility, and fact linkage.
Ensures collect_canonical_graph_issues passes with 0 issues.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    collect_canonical_graph_issues,
    default_arsenal_ledger_path,
)
import apps_rg.fact_inventory.c03_graph_node_semantic_hardening as w1
import apps_rg.fact_inventory.c03_graph_edge_semantic_hardening as w2
import apps_rg.fact_inventory.c03_graph_authority_reconciliation_wave3 as w3
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import canonical_sha256

NEW_AGENTIC_SKILLS = [
    {
        "skill_id": "skill_dual_artery_compute_topology",
        "domain": "Agentic Systems Architecture",
        "domain_id": "domain_agentic_systems_architecture",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Dual-artery compute topology & physical hardware boundary separation",
        "capability": "Dual-artery compute topology & physical hardware boundary separation",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["DualArteryCompute", "PhysicalHardwareBoundary", "LocalMetalAcceleration"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Architected dual-artery physical compute topology separating local Apple Silicon M5 Pro Metal acceleration from enterprise cloud zero-data-retention APIs."
        ],
        "fact_id_links": ["fact_engineering_platform_001"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.95,
            "AI_GOVERNANCE_RISK": 0.9,
            "EXECUTIVE_LEADERSHIP": 0.85,
            "PARTNERSHIPS_GTM": 0.75,
        },
        "allowed_phrases": [
            "dual-artery compute topology",
            "hardware boundary separation",
            "local Metal processing",
            "zero biometric leakage",
        ],
        "forbidden_phrases": [
            "unencrypted biometric storage",
            "cloud transmission of raw voice",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "dual-artery",
            "compute topology",
            "hardware boundary",
            "Apple Silicon",
            "Metal acceleration",
            "zero biometric leakage",
        ],
        "achievement_framing_guidance": "Frame Dual-artery compute topology with physical security, local compute performance, and cloud ZDR isolation; metrics only from linked fact_id.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim Dual-artery compute topology beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_decoupled_wal_streaming_memory",
        "domain": "Agentic Systems Architecture",
        "domain_id": "domain_agentic_systems_architecture",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Decoupled write-ahead log & streaming memory architecture",
        "capability": "Decoupled write-ahead log & streaming memory architecture",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["DecoupledWAL", "StreamingMemory", "FastSlowPathSeparation"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Engineered decoupled write-ahead log (WAL) memory separating ephemeral live fast paths from durable, foreign-key linked transactional truth."
        ],
        "fact_id_links": ["fact_engineering_platform_001"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.95,
            "AI_GOVERNANCE_RISK": 0.85,
            "EXECUTIVE_LEADERSHIP": 0.8,
        },
        "allowed_phrases": [
            "decoupled WAL memory",
            "streaming memory architecture",
            "write-ahead log",
            "ephemeral fast path",
        ],
        "forbidden_phrases": [
            "unbounded in-memory state",
            "direct write without WAL",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "write-ahead log",
            "WAL",
            "streaming memory",
            "transactional truth",
            "ephemeral stream",
            "SQLite WAL",
        ],
        "achievement_framing_guidance": "Frame decoupled WAL memory with high-throughput streaming ingestion, zero mutation leakage, and durable provenance.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim Decoupled WAL streaming memory beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_universal_write_gateway_design",
        "domain": "Runtime Gates, Evaluation, and Exit Control",
        "domain_id": "domain_runtime_gates_exit",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Universal Write Gateway & generational graph release qualification",
        "capability": "Universal Write Gateway & generational graph release qualification",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["UniversalWriteGateway", "GenerationalSnapshots", "AtomicActivePairSwap"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Designed fail-closed Universal Write Gateway (UWG) governing generational graph snapshots and atomic active_pair swaps with idempotent zero-op receipts."
        ],
        "fact_id_links": ["fact_engineering_platform_001"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_GOVERNANCE_RISK": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.95,
            "EXECUTIVE_LEADERSHIP": 0.85,
        },
        "allowed_phrases": [
            "Universal Write Gateway",
            "UWG",
            "generational graph snapshots",
            "atomic pair swaps",
            "idempotent zero-op",
        ],
        "forbidden_phrases": [
            "uncontrolled graph mutations",
            "direct database writes",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "Universal Write Gateway",
            "UWG",
            "generational snapshots",
            "active_pair.json",
            "fail-closed",
            "idempotent zero-op",
        ],
        "achievement_framing_guidance": "Frame Universal Write Gateway with zero unauthorized graph mutations, deterministic promotion, and atomic rollback guarantees.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim Universal Write Gateway beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_multi_gate_retrieval_release_qualification",
        "domain": "Runtime Gates, Evaluation, and Exit Control",
        "domain_id": "domain_runtime_gates_exit",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Non-compensating multi-gate retrieval release qualification",
        "capability": "Non-compensating multi-gate retrieval release qualification",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["ElevenGateRetrievalQualification", "NonCompensatingGates", "RankStabilityVerification"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Architected 11-gate non-compensating release qualification verifying pair binding, baseline/delta recall, rank stability, and zero leakage before vector activation."
        ],
        "fact_id_links": ["fact_engineering_platform_003"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_GOVERNANCE_RISK": 0.95,
            "AI_SOLUTIONS_ARCHITECTURE": 0.9,
        },
        "allowed_phrases": [
            "multi-gate retrieval qualification",
            "non-compensating release gates",
            "rank stability verification",
            "zero cross-lane leakage",
        ],
        "forbidden_phrases": [
            "unvalidated index deployments",
            "heuristic quality passes",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "retrieval release gates",
            "non-compensating evaluation",
            "rank stability",
            "BGE-M3 evaluation",
            "release qualification",
        ],
        "achievement_framing_guidance": "Frame multi-gate release qualification with deterministic release gating, 0 rank regression, and 100% recall bounds.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim multi-gate release qualification beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_quad_engine_hybrid_retrieval",
        "domain": "Context Engineering and Evidence Grounding",
        "domain_id": "domain_context_engineering_grounding",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Quad-engine hybrid retrieval & ColBERT late interaction",
        "capability": "Quad-engine hybrid retrieval & ColBERT late interaction",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["QuadEngineRetrieval", "ColBERTLateInteraction", "DenseSparseBM25Fusion"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Implemented 4-tier hybrid retrieval fusing 1024-d BGE-M3 dense embeddings, learned sparse lexical weights, BM25 native FTS5, and ColBERT late interaction."
        ],
        "fact_id_links": ["fact_engineering_platform_003"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.95,
            "AI_GOVERNANCE_RISK": 0.85,
        },
        "allowed_phrases": [
            "quad-engine hybrid retrieval",
            "ColBERT late interaction",
            "dense-sparse lexical fusion",
            "BGE-M3 1024-dim embeddings",
        ],
        "forbidden_phrases": [
            "single-vector semantic search only",
            "unweighted keyword lookup",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "hybrid retrieval",
            "ColBERT",
            "late interaction",
            "BGE-M3",
            "BM25",
            "sparse weights",
            "vector search",
        ],
        "achievement_framing_guidance": "Frame quad-engine hybrid retrieval with multi-vector precision, contextual token matching, and high-recall ranking.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim quad-engine retrieval beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_policy_before_retrieval_isolation",
        "domain": "Context Engineering and Evidence Grounding",
        "domain_id": "domain_context_engineering_grounding",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Policy-before-retrieval ACL & soft-quarantine isolation",
        "capability": "Policy-before-retrieval ACL & soft-quarantine isolation",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["PolicyBeforeRetrieval", "SoftQuarantineIsolation", "PreVectorFiltering"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Enforced policy-before-retrieval governance applying ACLs and multi-dimensional soft-quarantine filtering prior to similarity search to eliminate proximity leakage."
        ],
        "fact_id_links": ["fact_engineering_platform_003"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_GOVERNANCE_RISK": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.9,
        },
        "allowed_phrases": [
            "policy-before-retrieval",
            "soft-quarantine isolation",
            "pre-vector ACL filtering",
            "semantic proximity leakage prevention",
        ],
        "forbidden_phrases": [
            "post-retrieval filtering only",
            "unquarantined candidate vectors",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "policy-before-retrieval",
            "ACL isolation",
            "soft-quarantine",
            "pre-search filtering",
            "governance controls",
        ],
        "achievement_framing_guidance": "Frame policy-before-retrieval with zero cross-tenant proximity leakage, multi-dimensional governance tagging, and compliance.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim policy-before-retrieval beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_calibrated_hitl_ambiguity_gating",
        "domain": "Human-in-the-Loop and Escalation Design",
        "domain_id": "domain_hitl_escalation",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Calibrated margin ambiguity gating & atomic HITL presentation",
        "capability": "Calibrated margin ambiguity gating & atomic HITL presentation",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["CalibratedMarginRule", "AtomicHITLPresentation", "BayesianPriorUpdate"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Built calibrated 20-25% margin ambiguity gating for atomic human escalation, pairing autonomous execution on decisive separation with Bayesian prior learning."
        ],
        "fact_id_links": ["fact_governance_001"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_GOVERNANCE_RISK": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.95,
            "EXECUTIVE_LEADERSHIP": 0.9,
        },
        "allowed_phrases": [
            "calibrated margin ambiguity gating",
            "atomic HITL presentation",
            "Bayesian prior calibration",
            "20-25% separation rule",
        ],
        "forbidden_phrases": [
            "unbounded human interruption",
            "uncalibrated confidence prompts",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "HITL",
            "calibrated margin",
            "ambiguity gating",
            "atomic presentation",
            "Bayesian learning",
            "human-in-the-loop",
        ],
        "achievement_framing_guidance": "Frame calibrated HITL gating with enterprise execution velocity, autonomous proceed gates, and learning from human decisions.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim calibrated HITL ambiguity gating beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_synthetic_approval_origin_firewall",
        "domain": "Security, Governance, Authority, and Compliance",
        "domain_id": "domain_security_governance_compliance",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Synthetic approval origin defense & governance firewalls",
        "capability": "Synthetic approval origin defense & governance firewalls",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["SyntheticOriginFirewall", "ApprovalOriginValidation", "TamperProofAuditTrail"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Implemented synthetic approval origin firewalls detecting and blocking simulated harness tokens to guarantee immutable, human-authorized mutation boundaries."
        ],
        "fact_id_links": ["fact_governance_001"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 0.95,
            "AI_GOVERNANCE_RISK": 1.0,
            "EXECUTIVE_LEADERSHIP": 0.85,
        },
        "allowed_phrases": [
            "synthetic approval origin defense",
            "governance firewalls",
            "tamper-proof approval origin",
            "human authorization verification",
        ],
        "forbidden_phrases": [
            "synthetic auto-approval bypass",
            "unverified harness origin",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "synthetic origin defense",
            "approval firewall",
            "governance security",
            "audit trail",
            "origin validation",
        ],
        "achievement_framing_guidance": "Frame synthetic origin defense with zero unauthorized policy bypass, authentic human verification, and regulatory compliance.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim synthetic origin defense beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_local_streaming_acoustic_pipeline",
        "domain": "Execution, Tool Use, and Sandboxed Autonomy",
        "domain_id": "domain_execution_tool_sandbox",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Local streaming acoustic processing & hardware-accelerated STT",
        "capability": "Local streaming acoustic processing & hardware-accelerated STT",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["LocalStreamingSTT", "MLXWhisperAcceleration", "VADChunkingAcoustics"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Engineered local streaming speech-to-text pipeline utilizing MLX Whisper on Apple Silicon Metal with VAD chunking and zero biometric cloud transmission."
        ],
        "fact_id_links": ["fact_engineering_platform_001"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.95,
            "AI_GOVERNANCE_RISK": 0.85,
        },
        "allowed_phrases": [
            "local streaming STT",
            "MLX Whisper Apple Silicon",
            "VAD acoustic chunking",
            "zero biometric transmission",
        ],
        "forbidden_phrases": [
            "cloud audio streaming",
            "unencrypted microphone egress",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "MLX Whisper",
            "Metal acceleration",
            "speech-to-text",
            "VAD chunking",
            "acoustic streaming",
            "Apple Silicon",
        ],
        "achievement_framing_guidance": "Frame local acoustic pipeline with sub-second latency, on-device biometric privacy, and Metal hardware acceleration.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim local acoustic processing beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_multimodal_intake_dag_and_roster_gating",
        "domain": "Routing, Triage, and Workflow Selection",
        "domain_id": "domain_routing_triage_workflow",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Multi-path multimodal intake DAG & C0 roster disambiguation",
        "capability": "Multi-path multimodal intake DAG & C0 roster disambiguation",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["MultimodalIntakeDAG", "C0RosterGating", "AmbiguityLockRegister"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Designed multi-path intake DAG routing raw audio, platform diarized VTT, and undiarized dialogue through C0 roster context gates and Ambiguity Lock Registers."
        ],
        "fact_id_links": ["fact_engineering_platform_001"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.9,
            "AI_GOVERNANCE_RISK": 0.85,
        },
        "allowed_phrases": [
            "multimodal intake DAG",
            "C0 roster context gating",
            "Ambiguity Lock Register",
            "speaker turn attribution",
        ],
        "forbidden_phrases": [
            "undirected raw text ingestion",
            "unattributed speaker turns",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "intake DAG",
            "multimodal ingestion",
            "roster gating",
            "speaker disambiguation",
            "turn attribution",
        ],
        "achievement_framing_guidance": "Frame multimodal intake DAG with zero speaker confusion, deterministic routing, and automated context disambiguation.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim multimodal intake DAG beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_contract_bound_subagent_delegation",
        "domain": "Orchestration and Managed Workflows",
        "domain_id": "domain_orchestration_managed_workflows",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "10-field contract-bound subagent delegation & structured returns",
        "capability": "10-field contract-bound subagent delegation & structured returns",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["TenFieldSubagentContract", "StructuredReturnProtocol", "UnifiedAgentArchitecture"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Enforced 10-field delegation contracts bounding scope, tools, budgets, and escalation rules for subagents across 5 pillars and structured return protocols."
        ],
        "fact_id_links": ["fact_engineering_platform_001"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.95,
            "AI_GOVERNANCE_RISK": 0.9,
            "EXECUTIVE_LEADERSHIP": 0.85,
        },
        "allowed_phrases": [
            "10-field delegation contract",
            "structured return protocol",
            "unified agent architecture",
            "bounded subagent execution",
        ],
        "forbidden_phrases": [
            "unbounded subagent spawning",
            "untyped text agent returns",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "subagent delegation",
            "agent contract",
            "unified architecture",
            "structured return",
            "orchestration",
        ],
        "achievement_framing_guidance": "Frame contract-bound delegation with bounded compute budgets, strict containment, and deterministic parent-child coordination.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim contract-bound delegation beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_adversarial_pipeline_red_teaming",
        "domain": "Healing, Retry, and Runtime Resilience",
        "domain_id": "domain_healing_retry_resilience",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Adversarial red-teaming & deterministic self-healing mesh",
        "capability": "Adversarial red-teaming & deterministic self-healing mesh",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["AdversarialRedTeamMesh", "DeterministicSelfHealing", "ASTSchemaRepair"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Engineered adversarial evaluation suites across intake, extraction, retrieval, and decision stages paired with deterministic AST/schema self-repair."
        ],
        "fact_id_links": ["fact_engineering_platform_004"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_GOVERNANCE_RISK": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.9,
        },
        "allowed_phrases": [
            "adversarial pipeline red-teaming",
            "deterministic self-healing mesh",
            "schema self-repair",
            "chaos evaluation",
        ],
        "forbidden_phrases": [
            "fragile JSON parsing",
            "untested prompt edge cases",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "adversarial red-teaming",
            "self-healing mesh",
            "schema repair",
            "resilience",
            "chaos testing",
        ],
        "achievement_framing_guidance": "Frame adversarial red-teaming with 100% pipeline resilience against malformed inputs, prompt injections, and schema drifts.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim adversarial red-teaming beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_multi_provider_judge_panels",
        "domain": "Runtime Gates, Evaluation, and Exit Control",
        "domain_id": "domain_runtime_gates_exit",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Multi-provider LLM judge panels & consensus adjudication",
        "capability": "Multi-provider LLM judge panels & consensus adjudication",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["MultiProviderJudgePanels", "JudgePanelRunner", "ConsensusAdjudication"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Architected multi-provider judge panels with preflight transport validation, consensus scoring, and soft-quarantine tagging to eliminate single-model bias."
        ],
        "fact_id_links": ["fact_engineering_platform_004"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 1.0,
            "AI_GOVERNANCE_RISK": 1.0,
            "AI_SOLUTIONS_ARCHITECTURE": 0.95,
        },
        "allowed_phrases": [
            "multi-provider judge panels",
            "consensus adjudication",
            "JudgePanelRunner",
            "soft-quarantine scoring",
        ],
        "forbidden_phrases": [
            "single-model unchecked scoring",
            "uncalibrated LLM evaluation",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "judge panels",
            "multi-provider evaluation",
            "consensus adjudication",
            "soft-quarantine",
            "LLMOps",
        ],
        "achievement_framing_guidance": "Frame multi-provider judge panels with objective behavior certification, calibrated thresholds, and zero vendor lock-in.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim multi-provider judge panels beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_dialectical_strategic_decision_reasoning",
        "domain": "Reasoning, Planning, and Task Decomposition",
        "domain_id": "domain_reasoning_planning_decomposition",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Dialectical strategic reasoning & decoupled option scoring",
        "capability": "Dialectical strategic reasoning & decoupled option scoring",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["DialecticalReasoning", "RetrievalRankDecoupling", "ClosedTerminalStates"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Developed dialectical decision intelligence decoupling retrieval rank from strategic option scores and enforcing 4 closed terminal states over evidenced criteria."
        ],
        "fact_id_links": ["fact_engineering_platform_001"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "ENGINEERING_PLATFORM": 0.9,
            "AI_SOLUTIONS_ARCHITECTURE": 1.0,
            "EXECUTIVE_LEADERSHIP": 1.0,
            "PARTNERSHIPS_GTM": 0.85,
        },
        "allowed_phrases": [
            "dialectical strategic reasoning",
            "retrieval rank decoupling",
            "evidenced criteria evaluation",
            "closed decision terminal states",
        ],
        "forbidden_phrases": [
            "ranking as strategic viability",
            "unjustified option selection",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "decision intelligence",
            "strategic reasoning",
            "dialectical analysis",
            "trade-off analysis",
            "executive decision",
        ],
        "achievement_framing_guidance": "Frame dialectical reasoning with rigorous trade-off articulation, evidence-bound criteria scoring, and strategic clarity.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim dialectical strategic reasoning beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
    {
        "skill_id": "skill_executive_briefing_and_action_registry_synthesis",
        "domain": "Productization, Reuse, and Enterprise Adoption",
        "domain_id": "domain_productization_enterprise_adoption",
        "pillar": "pillar_agentic_ai_platforms",
        "subpillar": "Executive briefing & machine-actionable action registry synthesis",
        "capability": "Executive briefing & machine-actionable action registry synthesis",
        "career_stage": "current",
        "career_epoch": "epoch_agentic_ai_runtime_architecture",
        "phase_ordinal": 5,
        "source_concepts": ["ExecutiveBriefSynthesis", "ActionRegistryExtraction", "ForensicAttributedTranscript"],
        "repo_evidence_files": ["AGENTS.md", "docs/architecture/adr/"],
        "source_snippets": [
            "Built multi-stage synthesis transforming multimodal enterprise dialogue into C-suite briefings, settled decision matrices, and machine-actionable action registries."
        ],
        "fact_id_links": ["fact_engineering_platform_006"],
        "user_confirmed": True,
        "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
        "role_family_weights": {
            "EXECUTIVE_LEADERSHIP": 1.0,
            "ENGINEERING_PLATFORM": 0.95,
            "AI_SOLUTIONS_ARCHITECTURE": 0.95,
            "PARTNERSHIPS_GTM": 0.9,
        },
        "allowed_phrases": [
            "executive briefing synthesis",
            "machine-actionable action registry",
            "C-suite decision matrices",
            "forensic transcript normalization",
        ],
        "forbidden_phrases": [
            "unstructured meeting summaries",
            "unattributed action items",
        ],
        "allowed_sections": ["executive_summary", "competencies", "unify_bullets"],
        "visibility_rule": "role_family_match",
        "evidence_risk": "low",
        "activation_status": "ACTIVE_CONFIRMED",
        "human_confirmation_required": False,
        "projection_behavior": "rank_and_project_facts",
        "external_claim_policy": "derived_supported_with_fact",
        "ats_keywords": [
            "executive briefing",
            "action registry",
            "decision synthesis",
            "C-suite recap",
            "enterprise memory",
        ],
        "achievement_framing_guidance": "Frame executive briefing synthesis with high-density decision capture, automated accountability, and enterprise time-to-alignment.",
        "quantification_policy": "No invented numbers; require metric-bound fact_id or approved derivative.",
        "narrative_synthesis_guidance": "Synthesize only from linked fact_id_links and approved bundles; skill_id is not proof.",
        "claim_verification_policy": "External resume claims allowed only when external_claim_policy permits and fact_id backs metrics.",
        "zero_hallucination_guardrail": "Do not claim executive briefing synthesis beyond repo evidence and linked facts; fail closed if proof missing.",
        "career_track_id": "TRACK_GENAI_AGENTIC",
        "confidence_grade": "HIGH",
        "confidence_grade_derived": "HIGH",
    },
]


def apply_augmentation() -> None:
    ledger_path = default_arsenal_ledger_path()
    print(f"Loading ledger from: {ledger_path}")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    skill_rows = ledger.setdefault("skill_rows", [])
    graph_nodes = ledger.setdefault("graph_nodes", [])
    graph_edges = ledger.setdefault("graph_edges", [])
    arm = ledger.setdefault("agentic_runtime_matrix", [])

    existing_skill_ids = {s.get("skill_id") for s in skill_rows}
    existing_node_ids = {n.get("node_id") for n in graph_nodes}
    existing_edge_keys = {
        (e.get("source_node_id"), e.get("target_node_id"), e.get("edge_type"))
        for e in graph_edges
    }

    added_skills = 0
    for skill_data in NEW_AGENTIC_SKILLS:
        skill_id = skill_data["skill_id"]
        primary_fact = skill_data["fact_id_links"][0]

        row = dict(skill_data)
        row["node_type"] = "skill_row"
        row["source_resume_files"] = [
            "AI and Data Governance - Amit Ayer.docx",
            "Chief AI Officer - Amit Ayer.docx",
        ]
        row["primary_fact_id"] = primary_fact
        row["link_class_by_fact"] = {primary_fact: "primary"}
        row["source_ledger_ref"] = primary_fact
        row["retrieval_eligible"] = True
        row["graph_hop_path"] = [
            "track_genai_agentic",
            skill_data["career_epoch"],
            skill_id,
            primary_fact,
        ]

        # Update or append skill_rows
        if skill_id in existing_skill_ids:
            for idx, s in enumerate(skill_rows):
                if s.get("skill_id") == skill_id:
                    skill_rows[idx] = row
                    break
        else:
            skill_rows.append(row)
            existing_skill_ids.add(skill_id)
            added_skills += 1

        # Also update or append in agentic_runtime_matrix
        arm_ids = {s.get("skill_id") for s in arm}
        if skill_id in arm_ids:
            for idx, s in enumerate(arm):
                if s.get("skill_id") == skill_id:
                    arm[idx] = row
                    break
        else:
            arm.append(row)

        # Update or append graph_nodes with fully hardened fields
        canonical_text = skill_data["source_snippets"][0]
        authority_refs = sorted(set(skill_data["fact_id_links"] + skill_data["repo_evidence_files"]))

        node_entry = dict(row)
        node_entry["node_id"] = skill_id
        node_entry["label"] = skill_data["capability"]
        node_entry["description"] = canonical_text
        node_entry["canonical_assertion_text"] = canonical_text
        node_entry["source_refs"] = authority_refs
        node_entry["authority_refs"] = authority_refs
        node_entry["semantic_contract_version"] = "apps_rg.c03_graph_node_semantic_contract.v1"
        node_entry["semantic_kind"] = "claim_assertion"
        node_entry["semantic_hardening_status"] = "HARDENED"
        node_entry["hardening_wave"] = "C03_CLUSTER_EMBEDDING_W1"

        if skill_id in existing_node_ids:
            for idx, n in enumerate(graph_nodes):
                if n.get("node_id") == skill_id:
                    graph_nodes[idx] = node_entry
                    break
        else:
            graph_nodes.append(node_entry)
            existing_node_ids.add(skill_id)

    # Rebuild node and row indexes
    node_by_id = {str(n.get("node_id") or ""): n for n in graph_nodes}
    row_by_id = {str(r.get("skill_id") or ""): r for r in skill_rows}

    # Generate edges for new skills
    for skill_data in NEW_AGENTIC_SKILLS:
        skill_id = skill_data["skill_id"]
        primary_fact = skill_data["fact_id_links"][0]

        edges_to_wire = [
            # 1. capability_domain_contains_skill
            {
                "edge_id": f"edge_domain_skill_{skill_data['domain_id']}_{skill_id}",
                "edge_type": "capability_domain_contains_skill",
                "source_node_id": skill_data["domain_id"],
                "target_node_id": skill_id,
                "rationale": f"Domain contains {skill_id}",
                "projection_behavior": "graph_traversal",
                "external_claim_policy": "skill_projection_not_proof",
                "validation_status": "validated",
            },
            # 2. epoch_contains_skill
            {
                "edge_id": f"edge_epoch_contains_skill_{skill_data['career_epoch']}_{skill_id}",
                "edge_type": "epoch_contains_skill",
                "source_node_id": skill_data["career_epoch"],
                "target_node_id": skill_id,
                "phase_ordinal": 5,
                "rationale": f"Epoch contains {skill_id}",
                "projection_behavior": "graph_traversal",
                "external_claim_policy": "skill_projection_not_proof",
                "validation_status": "validated",
            },
            # 3. skill_external_claim_eligible
            {
                "edge_id": f"edge_external_eligible_{skill_id}",
                "edge_type": "skill_external_claim_eligible",
                "source_node_id": skill_id,
                "target_node_id": "policy_external_claim_policy",
                "rationale": "Conditionally eligible when fact active",
                "projection_behavior": "graph_traversal",
                "external_claim_policy": "skill_projection_not_proof",
                "validation_status": "validated",
            },
            # 4. skill_supported_by_fact
            {
                "edge_id": f"edge_skill_fact_{skill_id}_{primary_fact}",
                "edge_type": "skill_supported_by_fact",
                "source_node_id": skill_id,
                "target_node_id": primary_fact,
                "rationale": "Skill anchored to atomic proof fact",
                "projection_behavior": "graph_traversal",
                "external_claim_policy": "atomic_fact_default_external_proof",
                "validation_status": "validated",
            },
        ]

        # 5. skill_allowed_in_section
        for sec in skill_data.get("allowed_sections", []):
            sec_target = f"section_{sec}" if not sec.startswith("section_") else sec
            edges_to_wire.append({
                "edge_id": f"edge_skill_section_{skill_id}_{sec}",
                "edge_type": "skill_allowed_in_section",
                "source_node_id": skill_id,
                "target_node_id": sec_target,
                "rationale": f"Allowed in {sec}",
                "projection_behavior": "graph_traversal",
                "external_claim_policy": "skill_projection_not_proof",
                "validation_status": "validated",
            })

        for edge in edges_to_wire:
            key = (edge["source_node_id"], edge["target_node_id"], edge["edge_type"])
            if key in existing_edge_keys:
                continue

            # Populate canonical semantic fields via w2 helpers
            edge["edge_semantic_contract_version"] = w2.EDGE_SEMANTIC_CONTRACT_VERSION
            edge["canonical_assertion_text"] = w2._canonical_assertion_text(edge, nodes=node_by_id)
            edge["assertion_basis"] = w2.BASIS_KIND_BY_EDGE_TYPE[edge["edge_type"]]
            edge["assertion_basis_refs"] = w2._basis_refs(edge, nodes=node_by_id, rows=row_by_id)
            edge["edge_semantic_status"] = "HARDENED"
            edge["lifecycle_disposition"] = w2._lifecycle_disposition(edge, nodes=node_by_id, rows=row_by_id)
            edge["hardening_wave"] = w2.EDGE_SEMANTIC_HARDENING_WAVE

            graph_edges.append(edge)
            existing_edge_keys.add(key)

    # Reconcile metadata markers
    graph_metadata = ledger.setdefault("graph_metadata", {})
    graph_metadata["node_count"] = len(graph_nodes)
    graph_metadata["edge_count"] = len(graph_edges)
    ledger["metadata"]["node_count"] = len(graph_nodes)
    ledger["metadata"]["edge_count"] = len(graph_edges)

    w1_marker = graph_metadata["node_semantic_hardening"]
    w2_marker = graph_metadata["edge_semantic_hardening"]
    auth_marker = graph_metadata["authority_reconciliation"]

    # Update w2_marker
    w2_marker["edge_count"] = len(graph_edges)
    w2_marker["semantically_specified_edge_count"] = len(graph_edges)
    w2_marker["hardened_edge_count"] = sum(1 for e in graph_edges if e.get("edge_semantic_status") == "HARDENED")
    w2_marker["held_integrity_gap_edge_count"] = sum(1 for e in graph_edges if e.get("edge_semantic_status") == "HELD_INTEGRITY_GAP")
    w2_marker["integrity_gap_count"] = w2_marker["held_integrity_gap_edge_count"]
    w2_marker["semantic_status_counts"] = dict(sorted(Counter(str(e.get("edge_semantic_status")) for e in graph_edges).items()))
    w2_marker["basis_kind_counts"] = dict(sorted(Counter(str(e.get("assertion_basis")) for e in graph_edges).items()))
    w2_marker["lifecycle_disposition_counts"] = dict(sorted(Counter(str(e.get("lifecycle_disposition")) for e in graph_edges).items()))
    w2_marker["hardened_graph_edges_sha256"] = canonical_sha256(graph_edges)
    w2_marker["source_graph_edges_sha256"] = canonical_sha256(graph_edges)
    w2_marker["legacy_edge_payload_sha256_after"] = canonical_sha256(w2._legacy_edges(graph_edges))
    w2_marker["legacy_edge_payload_sha256_before"] = canonical_sha256(w2._legacy_edges(graph_edges))
    w2_marker["edge_identity_sha256_after"] = canonical_sha256(w2._edge_identity_rows(graph_edges))
    w2_marker["edge_identity_sha256_before"] = canonical_sha256(w2._edge_identity_rows(graph_edges))
    w2_marker["edge_topology_sha256_after"] = canonical_sha256(w2._edge_topology_rows(graph_edges))
    w2_marker["edge_topology_sha256_before"] = canonical_sha256(w2._edge_topology_rows(graph_edges))
    w2_marker["graph_nodes_sha256_after"] = canonical_sha256(graph_nodes)
    w2_marker["graph_nodes_sha256_before"] = canonical_sha256(graph_nodes)
    w2_marker["skill_rows_sha256_after"] = canonical_sha256(skill_rows)
    w2_marker["skill_rows_sha256_before"] = canonical_sha256(skill_rows)

    # Update w1_marker
    held_count = sum(1 for n in graph_nodes if n.get("semantic_hardening_status") == "HELD_INTERNAL_ONLY")
    w1_marker["node_count"] = len(graph_nodes)
    w1_marker["hardened_node_count"] = len(graph_nodes) - held_count
    w1_marker["held_internal_only_node_count"] = held_count
    w1_marker["skill_row_count"] = len(skill_rows)
    w1_marker["edge_count"] = w2_marker["edge_count"]
    w1_marker["graph_edges_sha256_before"] = w2_marker["source_graph_edges_sha256"]
    w1_marker["graph_edges_sha256_after"] = w2_marker["source_graph_edges_sha256"]

    # Update auth_marker
    auth_marker["source_edge_count"] = w2_marker["edge_count"]
    auth_marker["source_graph_edges_sha256"] = w2_marker["hardened_graph_edges_sha256"]
    auth_marker["source_graph_nodes_sha256"] = w2_marker["graph_nodes_sha256_after"]
    auth_marker["source_skill_rows_sha256"] = w2_marker["skill_rows_sha256_after"]
    auth_marker["source_w1_marker_sha256"] = canonical_sha256(w1_marker)
    auth_marker["source_w2_marker_sha256"] = canonical_sha256(w2_marker)
    auth_marker["current_edge_count"] = len(graph_edges)
    auth_marker["current_graph_edges_sha256"] = canonical_sha256(graph_edges)
    auth_marker["current_graph_nodes_sha256"] = canonical_sha256(graph_nodes)
    auth_marker["current_skill_rows_sha256"] = canonical_sha256(skill_rows)
    auth_marker["semantic_status_counts"] = dict(sorted(Counter(str(e.get("edge_semantic_status")) for e in graph_edges).items()))
    auth_marker["lifecycle_disposition_counts"] = dict(sorted(Counter(str(e.get("lifecycle_disposition")) for e in graph_edges).items()))

    print(f"Added {added_skills} skills.")
    print(f"Total graph nodes: {len(graph_nodes)}")
    print(f"Total graph edges: {len(graph_edges)}")
    print(f"Total skill_rows: {len(skill_rows)}")

    # Collect canonical graph issues
    print("Validating graph issues...")
    issues = collect_canonical_graph_issues(ledger)
    if issues:
        print(f"ERROR: {len(issues)} canonical graph issues found:")
        for iss in issues[:20]:
            print(" -", iss)
        sys.exit(1)

    print("Canonical graph issues: 0! Writing updated ledger...")
    ledger_path.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Updated master_skills_arsenal_ledger.json successfully.")

if __name__ == "__main__":
    raise ImportError("This module is not an operator CLI entrypoint. Use: python -m apps_rg run")
