# Truist Financial Corporation  -  11-Lane Pre-Stub Keyed vs. Real IDE CLI Comparison

- **Target Role**: Head of Forward Deployed Engineering  -  Truist Financial Corporation
- **Pre-Stub Keyed Baseline Run**: `full_resume_0acb8e1555de` (`2026-11-17T22:38:26Z`, prior to synthetic stub introduction)
- **Real IDE CLI Run**: `truist_ide_cli_20261119` (`all_lanes_authorized: True`)
- **Audit Status**: `PASS  -  0 synthetic judge or canned generator violations across all 11 lanes`

## Executive Summary Table

| Lane | Keyed Writer | Keyed Words | Keyed Proof Judges | Real IDE / Hybrid Writer | IDE Words | Real IDE CLI Proof Judges (Slot 1 + Slot 2) |
|---|---|---:|---|---|---:|---|
| `headline` | `claude-sonnet-5` | 11 | `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `gpt-5.6-luna`: **4.5** (0_to_5, PASS) | `gemini-4-neon-high` (via `gemini-4-neon-high`, 44835 tok, conv `ed36bfb2`) | 11 | `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 24594 tok, conv `23d1abcf`); `gemini-3.8-flash-high`: **5.0** (0_to_5, PASS, 49835 tok, conv `4be02621`) |
| `executive_summary` | `claude-sonnet-5` | 141 | `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `gpt-5.6-luna`: **4.2** (0_to_5, PASS) | `gemini-4-neon-high` (via `gemini-4-neon-high`, 50447 tok, conv `e28a6398`) | 117 | `gemini-4-argon-high`: **4.8** (0_to_5, PASS, 37578 tok, conv `5f155c71`); `gemini-3.8-flash-high`: **4.8** (0_to_5, PASS, 118683 tok, conv `4dae525f`) |
| `competencies` | `claude-sonnet-5` | 200 | `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `gpt-5.6-luna`: **4.25** (0_to_5, PASS) | `gemini-4-neon-medium` (via `gemini-4-neon-medium`, 20821 tok, conv `bf36f800`) | 202 | `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 28663 tok, conv `c15419bf`); `gemini-3.8-flash-high`: **4.8** (0_to_5, PASS, 45616 tok, conv `42791ef5`) |
| `slalom_narrative` | `gpt-5.6-luna` | 33 | `gemini-3.8-flash`: **4.8** (0_to_5, PASS) | `gpt-5.6-luna` (external_openai) | 30 | `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 22572 tok, conv `1feb94e7`); `gemini-4-neon-high`: **4.6** (0_to_5, PASS, 26545 tok, conv `ed0a1dbb`) |
| `slalom_bullets` | `claude-sonnet-5` | 126 | `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `claude-haiku-5-5`: **0.9** (0_to_1, PASS) | `gemini-4-neon-medium` (via `gemini-4-neon-medium`, 20692 tok, conv `dd8cb94c`) | 106 | `gemini-4-argon-medium`: **4.85** (0_to_5, PASS, 28782 tok, conv `7362d8ea`); `gemini-3.8-flash-high`: **4.8** (0_to_5, PASS, 55392 tok, conv `33091f18`); `claude-sonnet-5-5-medium`: **0.95** (0_to_1, PASS, 20692 tok, conv `dd8cb94c`) |
| `unify_narrative` | `gpt-5.6-luna` | 40 | `gemini-3.8-flash`: **4.8** (0_to_5, PASS) | `gpt-5.6-luna` (external_openai) | 33 | `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 18771 tok, conv `f2efccd5`); `gemini-4-neon-high`: **4.4** (0_to_5, PASS, 23430 tok, conv `048bca90`) |
| `unify_bullets` | `claude-sonnet-5` | 170 | `gemini-3.8-flash`: **4.85** (0_to_5, PASS); `claude-haiku-5-5`: **0.9** (0_to_1, PASS); `gemini-3.8-flash`: **4.8** (0_to_5, PASS) | `gemini-4-neon-medium` (via `gemini-4-neon-medium`, 22191 tok, conv `1a314df5`) | 165 | `gemini-4-argon-medium`: **4.7** (0_to_5, PASS, 27612 tok, conv `d81d62f4`); `gemini-3.8-flash-high`: **4.9** (0_to_5, PASS, 61320 tok, conv `f35a0ac1`); `claude-sonnet-5-5-medium`: **0.94** (0_to_1, PASS, 22191 tok, conv `1a314df5`) |
| `ibm_narrative` | `gpt-5.6-luna` | 40 | `gemini-3.8-flash`: **4.8** (0_to_5, PASS) | `gpt-5.6-luna` (external_openai) | 21 | `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 17926 tok, conv `0fae383f`); `gemini-4-neon-high`: **4.6** (0_to_5, PASS, 22490 tok, conv `06518e4d`) |
| `ibm_bullets` | `claude-sonnet-5` | 136 | `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `claude-haiku-5-5`: **0.89** (0_to_1, PASS) | `gemini-4-neon-medium` (via `gemini-4-neon-medium`, 19881 tok, conv `2b3a023e`) | 124 | `gemini-4-argon-medium`: **4.3** (0_to_5, PASS, 33721 tok, conv `c48b0948`); `gemini-3.8-flash-high`: **4.6** (0_to_5, PASS, 86161 tok, conv `73cf3204`); `claude-sonnet-5-5-medium`: **0.88** (0_to_1, PASS, 19881 tok, conv `2b3a023e`) |
| `insurtech_narrative` | `gpt-5.6-luna` | 32 | `gemini-3.8-flash`: **4.8** (0_to_5, PASS) | `gpt-5.6-luna` (external_openai) | 28 | `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 41938 tok, conv `139975f0`); `gemini-4-neon-high`: **4.6** (0_to_5, PASS, 49573 tok, conv `f2efcb8f`) |
| `insurtech_bullets` | `claude-sonnet-5` | 52 | `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `claude-haiku-5-5`: **0.9** (0_to_1, PASS) | `gemini-4-neon-medium` (via `gemini-4-neon-medium`, 19493 tok, conv `f67ca27d`) | 42 | `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 27524 tok, conv `5a703046`); `gemini-3.8-flash-high`: **4.8** (0_to_5, PASS, 48564 tok, conv `4b28cf34`); `claude-sonnet-5-5-medium`: **0.94** (0_to_1, PASS, 19493 tok, conv `f67ca27d`) |

## Lane-by-Lane Side-by-Side Outputs & Judge Verdicts

### `headline`

- **Pre-Stub Keyed Output** (`claude-sonnet-5`, 11 words):
```text
SVP Engineering | Regulated Financial Governance | SDLC Automation Platforms | Runtime Telemetry Controls
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `gpt-5.6-luna`: **4.5** (0_to_5, PASS)

- **Real IDE CLI Run Output** (`gemini-4-neon-high`, 11 words):
```text
SVP Engineering | Sandboxed AI Systems | SDLC Automation Platform | Regulated AI Governance
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 24594 tok, conv `23d1abcf`); `gemini-3.8-flash-high`: **5.0** (0_to_5, PASS, 49835 tok, conv `4be02621`)
  - `gemini-3.8-flash-high` findings: Candidate headline meets all rubric criteria with verified factual support, approved executive prefix, and proper segment structure.

### `executive_summary`

- **Pre-Stub Keyed Output** (`claude-sonnet-5`, 141 words):
```text
Engineering executive directing governed runtime architecture and platform delivery, enforcing deterministic proof lineage and a safety validation mesh with one hundred percent gate conformance for safety-critical agent decisions across regulated enterprises. That platform discipline scales through offering accelerator management, standardizing repeatable cloud and AI blueprints across regulated financial-services and insurance institutions. Against that foundation, AWS shared-responsibility operating-model framing and insurer-owned control design anchor regulated cloud adoption guardrails for highly regulated deployment environments. In parallel, regulated financial-services AI governance, compliance automation, and model-risk discipline reduced banking regulatory findings while accelerating compliance submission cycles. That operating foundation built demoable accelerator packages and client-facing modernization playbooks that deepened fluency across regulated financial institutions and drove reuse of packaged offerings. This governed platform foundation, forward-deployed delivery discipline, and regulatory-grade evidence control will scale AI capability activation across business lines with measurable adoption and compliance confidence.
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `gpt-5.6-luna`: **4.2** (0_to_5, PASS)

- **Real IDE CLI Run Output** (`gemini-4-neon-high`, 117 words):
```text
Engineering executive aligning governed AI platforms, enterprise deployment blueprints, and financial-services compliance controls to scale production AI adoption reliably. Architects governed runtime platforms combining deterministic proof lineage and resilience controls so production agent workflows remain traceable under enterprise oversight. Within that ecosystem model, offering accelerator management scaled reusable AI solution packages and client-facing modernization playbooks alongside regulated cloud shared-responsibility guardrails. In parallel, banking AI governance, evidence-contract design, and model-risk automation cut regulatory findings while accelerating compliance submissions. Across critical agent decisions, a safety validation mesh enforced 100% gate conformance, sustaining verifiable reliability across high-stakes financial workflows. That platform and governance foundation enables disciplined prototype-to-production activation and sustained business-unit alignment, preserving control rigor as enterprise AI portfolios expand.
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-high`: **4.8** (0_to_5, PASS, 37578 tok, conv `5f155c71`); `gemini-3.8-flash-high`: **4.8** (0_to_5, PASS, 118683 tok, conv `4dae525f`)
  - `gemini-4-argon-high` findings: All six sentences are grounded in the authorized graph fact bundles and skill references.; Executive thesis and body sentences align with the Head of Forward Deployed Engineering mandate at Truist without using JD or briefing text as proof.; Quantitative gate-conformance outcome (100%) and regulated banking governance controls are woven cohesively without inventory stacking.
  - `gemini-3.8-flash-high` findings: Strong executive alignment with the Head of Forward Deployed Engineering mandate at Truist.; All claims are strictly grounded in allocated graph facts and role episode bundles.; Effectively integrates platform governance, reusable accelerator playbooks, and 100% validation gate conformance.

### `competencies`

- **Pre-Stub Keyed Output** (`claude-sonnet-5`, 200 words):
```text
- Governed Agentic AI Platform Architecture: governed multi-agent orchestration control planes, agentic workflow routing across enterprise systems, reusable accelerator assets for autonomous platforms
- Model Risk Governance & AI Runtime Control Gates: fail-closed policy authorization gates for runtime execution, policy enforcement across agent execution paths, governed write-boundary controls for runtime execution
- Retrieval & Context Engineering: relationship-grounded context retrieval for enterprise workflows, dense-sparse retrieval with relationship-aware ranking, authority-ordered prompt context assembly delivery
- LLMOps, Evaluation & Reliability: audit-ready agent reliability evidence for enterprise systems, model behavior evaluation and schema validation pipelines, deterministic multi-step quality loop design for pipelines
- Distributed Systems & Cloud Data Engineering: regulated cloud-native data architecture reference patterns, event-driven microservices architecture for distributed ecosystems, enterprise lakehouse platform modernization for decision intelligence
- Engineering Leadership & Operating Model: enterprise operating model for governed agentic delivery, executive investment decision governance for portfolio scale, runtime proof-bundle lineage for platforms
- Platform Productization & Commercialization: demoable AI platform prototypes for executive buyers, agentic platform productization for asset intelligence pipelines, enterprise pursuit execution across portfolio expansion motions
- Applied AI Reference Architecture & Enablement: enterprise applied AI reference architectures, reusable AI solution accelerators for business lines, production AI deployment enablement and assurance patterns, cloud portfolio architecture for reusable AI offerings
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `gpt-5.6-luna`: **4.25** (0_to_5, PASS)

- **Real IDE CLI Run Output** (`gemini-4-neon-medium`, 202 words):
```text
- Governed Agentic AI Platform Architecture: governed multi-agent orchestration control planes, agentic workflow routing across enterprise systems, dependency graph intelligence and join control architecture
- Model Risk Governance & AI Runtime Control Gates: fail-closed policy authorization gates for runtime execution, policy enforcement across agent execution paths, sandboxed decision workflows with audit trails
- Retrieval & Context Engineering: relationship-grounded context retrieval for enterprise workflows, dense-sparse retrieval with relationship-aware ranking, authority-ordered prompt context assembly delivery
- LLMOps, Evaluation & Reliability: audit-ready agent reliability evidence for enterprise systems, model behavior evaluation and schema validation pipelines, deterministic multi-step quality loop design for pipelines
- Distributed Systems & Cloud Data Engineering: regulated cloud-native data blueprint reference patterns, event-driven microservices architecture for distributed ecosystems, side-effect bounded action controls for runtime execution
- Engineering Leadership & Operating Model: enterprise operating model for governed agentic delivery, executive investment decision governance for portfolio scale, enterprise deal support and solution execution
- Platform Productization & Commercialization: demoable AI platform prototypes for executive buyers, agentic platform productization for asset intelligence pipelines, enterprise pursuit execution across portfolio expansion motions
- Applied AI Reference Architecture & Enablement: enterprise applied AI reference architectures, reusable AI solution accelerators for business lines, production AI deployment enablement and assurance patterns, cloud portfolio architecture for reusable AI offerings
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 28663 tok, conv `c15419bf`); `gemini-3.8-flash-high`: **4.8** (0_to_5, PASS, 45616 tok, conv `42791ef5`)
  - `gemini-4-argon-medium` findings: All seven competency categories are well-differentiated, graph-backed, and directly aligned with the Head of Forward Deployed Engineering role at Truist.; Terms combine concrete SVP-level agentic platform and runtime governance mechanisms with source-bound enterprise deployment and commercialization proof.; Partner and reference architecture terms bind cleanly to valid IBM and Unify roots without chronology leakage or off-domain clutter.
  - `gemini-3.8-flash-high` findings: All eight competency categories are strictly grounded in claim ledger facts with zero unsupported claims.; Category structure directly addresses forward deployed AI engineering needs for enterprise deployment and governance.; Deep agentic mechanisms are demonstrated across multi-agent orchestration, runtime policy gates, and context retrieval.

### `slalom_narrative`

- **Pre-Stub Keyed Output** (`gpt-5.6-luna`, 33 words):
```text
Operationalized enterprise AI delivery by pairing governed agentic orchestration with auditable knowledge foundations and calibrated human oversight, translating complex client environments into repeatable production activation through executive relationship ownership and disciplined delivery governance.
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.8** (0_to_5, PASS)

- **Real IDE CLI Run Output** (`gpt-5.6-luna`, 30 words):
```text
Operationalized enterprise AI delivery by converting governed retrieval, model-risk controls, and repeatable solution architecture into an executive operating rhythm that connected complex stakeholder needs to deployable, auditable outcomes at scale.
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 22572 tok, conv `1feb94e7`); `gemini-4-neon-high`: **4.6** (0_to_5, PASS, 26545 tok, conv `ed0a1dbb`)
  - `gemini-4-argon-medium` findings: Single-sentence narrative is grounded in four allowed reb_slalom_* role episode bundles and passes all deterministic X2 gates.; Executive framing cleanly complements companion bullets without metric collision, opener repetition, or internal micro-plumbing specs.

### `slalom_bullets`

- **Pre-Stub Keyed Output** (`claude-sonnet-5`, 126 words):
```text
- bul_slalom_001: Architected production agentic AI delivery programs and A2A multi-agent orchestration for Fortune 500 enterprise transformations by establishing the architecture standards that governed how autonomous systems were integrated and activated within client environments.
- bul_slalom_002: Led a 105-person engineering and data organization across a leading energy and utility enterprise by owning executive client relationships, multi-workstream delivery governance, and commercial pipeline growth to sustain advanced technology activation at scale.
- bul_slalom_003: Built regulated data governance and model-risk evaluation frameworks with confidence-calibrated human-in-the-loop escalation controls that delivered 99% policy-gate auditability across HITL escalation workflows, ensuring regulated AI deployments remained compliant and operationally sound.
- bul_slalom_004: Designed enterprise bitemporal GraphRAG knowledge-graph retrieval platforms with governed data lineage controls to make regulated client AI analytics auditable and enterprise-grade before activation into production workflows.
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `claude-haiku-5-5`: **0.9** (0_to_1, PASS)

- **Real IDE CLI Run Output** (`gemini-4-neon-medium`, 106 words):
```text
- bul_slalom_001: Architected enterprise bitemporal GraphRAG knowledge-graph retrieval platforms with governed data lineage controls, which equipped regulated client analytics and AI transformation programs with audit-ready retrieval fidelity.
- bul_slalom_002: Directed 105 software engineers and data leaders across a leading energy and utility enterprise to align executive client relationships, multi-workstream delivery governance, and commercial pipeline growth across active client programs.
- bul_slalom_003: Established regulated data governance frameworks, multi-model evaluation panels, and multi-stage quality reviews that delivered 99% policy-gate auditability across confidence-calibrated human-in-the-loop (HITL) escalation workflows.
- bul_slalom_004: Commercialized frontier model research and next-generation AI practice architecture into repeatable client offerings by establishing capability roadmaps and practice delivery standards for enterprise deployment.
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-medium`: **4.85** (0_to_5, PASS, 28782 tok, conv `7362d8ea`); `gemini-3.8-flash-high`: **4.8** (0_to_5, PASS, 55392 tok, conv `33091f18`); `claude-sonnet-5-5-medium`: **0.95** (0_to_1, PASS, 20692 tok, conv `dd8cb94c`)
  - `gemini-4-argon-medium` findings: All 4 Slalom bullets map cleanly to authorized bul_slalom_001 through bul_slalom_004 proof facts and graph-bound claim ledger entries.; Executive action verbs, concrete mechanisms, and audit-ready or commercial outcomes satisfy role episode rubric requirements without micro-plumbing clutter.
  - `claude-sonnet-5-5-medium` findings: Employment pool selector: 4 slots, min_score=0.94, threshold=0.86, gate_ok=True

### `unify_narrative`

- **Pre-Stub Keyed Output** (`gpt-5.6-luna`, 40 words):
```text
Owned Unify Consulting’s mandate to turn governed agentic architecture into an industrialized platform capability, pairing GraphRAG control-plane design with runtime resilience and audit-grade observability to support repeatable enterprise delivery and a credible path from bespoke engagements to scalable IP-led services.
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.8** (0_to_5, PASS)

- **Real IDE CLI Run Output** (`gpt-5.6-luna`, 33 words):
```text
Anchored Unify Consulting’s agentic platform mandate, connecting control-plane architecture and GraphRAG grounding to a productized commercial engine that converted governed delivery into modular infrastructure for compliance-bound-enterprise adoption at scale across complex financial environments.
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 18771 tok, conv `f2efccd5`); `gemini-4-neon-high`: **4.4** (0_to_5, PASS, 23430 tok, conv `048bca90`)
  - `gemini-4-argon-medium` findings: Strong role-level executive thesis anchoring the Unify Consulting agentic platform mandate, control-plane architecture, GraphRAG grounding, and commercial engine.; Fully grounded in allowed_fact_packet (reb_unify_dependency_graph_accelerator) and companion_bullets_context (bul_unify_001 through bul_unify_006) without repeating bullet metrics.; Single sentence at 37 words and 297 characters, well within the 58-word and 360-character executive brevity ceiling.
  - `gemini-4-neon-high` findings: Minor hyphenation defect in 'compliance-bound-enterprise adoption' (extra hyphen before 'enterprise').; Opening verb 'Anchored' is slightly softer than direct SVP ownership language and the closing phrase is mildly dense.

### `unify_bullets`

- **Pre-Stub Keyed Output** (`claude-sonnet-5`, 170 words):
```text
- bul_unify_001: Directed governed agentic systems architecture for a multi-agent production platform, binding agent outputs to a runtime proof-bundle lineage surface that ties every output to graph evidence for claim-safe decisioning.
- bul_unify_002: Standardized the AI systems lifecycle with managed workflow orchestration and replayable runtime design, compressing lab-to-production cycle time from six months to three weeks while preserving deterministic auditability.
- bul_unify_003: Architected distributed cloud and data execution infrastructure spanning Databricks Lakehouse, vector services, and API gateways, establishing cloud data and runtime integration patterns that kept agentic workloads highly available.
- bul_unify_004: Directed a dependency graph accelerator that mapped architecture visibility across legacy systems, applying static governance drift detection to deliver semantic-edge governance controls for refactor safety ahead of agentic modernization.
- bul_unify_005: Converted bespoke client delivery into reusable platform IP through agentic platform productization and an operating model for agentic AI, expanding gross margin by 20% while scaling the engineering organization.
- bul_unify_006: Drove enterprise AI adoption by aligning generative-AI workflows to CFO priorities, which unlocked $5M in annual contract value from CFO-aligned enterprise adoption.
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.85** (0_to_5, PASS); `claude-haiku-5-5`: **0.9** (0_to_1, PASS); `gemini-3.8-flash`: **4.8** (0_to_5, PASS)

- **Real IDE CLI Run Output** (`gemini-4-neon-medium`, 165 words):
```text
- bul_unify_001: Established runtime proof-bundle lineage tying agent outputs to graph evidence for regulated financial institutions by architecting a governed multi-agent control plane with GraphRAG grounding and human override escalation paths.
- bul_unify_002: Delivered audit-grade runtime observability coverage for regulated AI workflows through runtime reliability governance and AI CI/CD standards that enforce evaluation gates, telemetry instrumentation, and rollback controls.
- bul_unify_003: Accelerated lab-to-production AI systems lifecycle from six months to three weeks with standardized managed workflow orchestration from intake through monitoring to embed deterministic auditability and exit disposition governance.
- bul_unify_004: Operationalized cloud data/runtime integration patterns across Databricks, vector services, and API gateways on AWS and Databricks Lakehouse pipelines that sustained parallel decision workflows under egress governance.
- bul_unify_005: Drove 20% gross margin expansion across enterprise lines of business by converting bespoke client delivery into reusable platform services under a commercial operating model for agentic AI.
- bul_unify_006: Generated $5M ACV from CFO-aligned enterprise AI workflow adoption through consumption-based licensing and executive deal support that shortened commercial cycles and sustained renewals.
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-medium`: **4.7** (0_to_5, PASS, 27612 tok, conv `d81d62f4`); `gemini-3.8-flash-high`: **4.9** (0_to_5, PASS, 61320 tok, conv `f35a0ac1`); `claude-sonnet-5-5-medium`: **0.94** (0_to_1, PASS, 22191 tok, conv `1a314df5`)
  - `gemini-4-argon-medium` findings: All six Unify bullets align verbatim with the claim ledger and preserve assigned metrics including the six-months-to-three-weeks cycle reduction, 20% gross margin expansion, and $5M ACV anchor in bul_unify_006.; Bullet 4 repeats 'Databricks' twice ('across Databricks, vector services, and API gateways on AWS and Databricks Lakehouse pipelines'), which is a minor stylistic redundancy.
  - `gemini-3.8-flash-high` findings: All 6 bullets map to verified claim ledger source facts with exact metric alignment.; Crisp single-sentence bullet lines demonstrating clear cross-bullet outcome diversity.; Strong executive signal and platform proof for Unify with zero cross-employer leakage.
  - `claude-sonnet-5-5-medium` findings: Employment pool selector: 6 slots, min_score=0.92, threshold=0.86, gate_ok=True

### `ibm_narrative`

- **Pre-Stub Keyed Output** (`gpt-5.6-luna`, 40 words):
```text
Anchored BI-enabled decision support and compliance-bound deployment architecture across banking and carrier portfolios at IBM, establishing repeatable governance and stakeholder operating disciplines that translated complex enterprise requirements into production-ready workflows and clearer executive action for transformation leaders and delivery teams.
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.8** (0_to_5, PASS)

- **Real IDE CLI Run Output** (`gpt-5.6-luna`, 21 words):
```text
Anchored AWS modernization architecture and DevSecOps release discipline at IBM, establishing traceable lineage and compliance foundations across banking and carrier accounts.
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 17926 tok, conv `0fae383f`); `gemini-4-neon-high`: **4.6** (0_to_5, PASS, 22490 tok, conv `06518e4d`)
  - `gemini-4-argon-medium` findings: Narrative sentence accurately synthesizes IBM AWS modernization, DevSecOps release discipline, and compliance lineage from bul_ibm_001, bul_ibm_002, and bul_ibm_005 without Unify-era inflation or mechanical five-bullet recap.
  - `gemini-4-neon-high` findings: Minor terminology note: 'carrier accounts' is slightly less explicit than the source phrasing 'insurance institutions' (bul_ibm_002) and could read ambiguously outside insurance.

### `ibm_bullets`

- **Pre-Stub Keyed Output** (`claude-sonnet-5`, 136 words):
```text
- bul_ibm_001: Architected repeatable DevSecOps pipeline blueprints and release validation gates, establishing governed delivery automation for enterprise cloud modernization initiatives.
- bul_ibm_002: Architected NLP and ML decision-support pipelines across enterprise banking and insurance portfolios, translating unstructured regulatory and risk signals into actionable compliance workflows with embedded data lineage governance.
- bul_ibm_003: Directed decision-support data modeling and executive BI views across regulated financial-services modernization portfolios, converting fragmented delivery and budget data into governed dashboards for executive operating decisions.
- bul_ibm_004: Led technical discovery and solution-mapping engagements across enterprise banking and insurance pursuits, translating buyer pain points into architecture-backed pre-sales narratives and delivery-ready handoff packages.
- bul_ibm_005: Led AWS modernization architecture for regulated banking and insurance workloads moving from on-prem constraints to cloud-native delivery patterns, delivering 9 BCBS 239 and OCC-compliant cloud reference architectures reused across 14 banking pursuits (sustaining 99.9% production uptime).
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `claude-haiku-5-5`: **0.89** (0_to_1, PASS)

- **Real IDE CLI Run Output** (`gemini-4-neon-medium`, 124 words):
```text
- bul_ibm_001: Architected repeatable DevSecOps pipeline blueprints and release validation gates, establishing governed delivery automation for enterprise cloud modernization initiatives.
- bul_ibm_002: Architected NLP and ML decision-support pipelines translating unstructured regulatory and risk signals into governed compliance workflows, establishing data lineage and risk visibility across banking and insurance institutions.
- bul_ibm_003: Architected industry-specific AI, analytics, and cloud modernization reference architectures, establishing governed portfolio views and executive operating cadence for financial-services decision support.
- bul_ibm_004: Led technical discovery and solution mapping for enterprise financial-services pursuits, aligning architecture choices with buyer criteria and delivery-ready solution handoffs.
- bul_ibm_005: Drove enterprise AWS modernization architecture and containerized microservices decomposition for regulated banking and insurance workloads, reusing 9 BCBS 239 and OCC-compliant cloud reference architectures across 14 banking pursuits to sustain 99.9% production uptime.
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-medium`: **4.3** (0_to_5, PASS, 33721 tok, conv `c48b0948`); `gemini-3.8-flash-high`: **4.6** (0_to_5, PASS, 86161 tok, conv `73cf3204`); `claude-sonnet-5-5-medium`: **0.88** (0_to_1, PASS, 19881 tok, conv `2b3a023e`)
  - `gemini-4-argon-medium` findings: Bullets 1, 2, and 3 all open with the same verb ('Architected'), reducing executive action-verb variety across the 5-bullet IBM block.; Bullet 3 substitutes 'AI, analytics, and cloud modernization reference architectures' for the more specific data modeling, delivery-cost analytics, and executive BI dashboard focus in bul_ibm_003.; Approved bundle metrics in the fact packet for bul_ibm_001 through bul_ibm_004 remain unused while only bul_ibm_005 carries a quantified outcome.
  - `gemini-3.8-flash-high` findings: All five bullets strictly ground to allowed IBM facts bul_ibm_001 through bul_ibm_005 with no unapproved metrics.; Bul_ibm_005 incorporates approved BCBS 239 and OCC reference architecture metrics verbatim.; Bullets 1, 2, and 3 repeat the identical opening verb Architected, reducing lead-in variety.
  - `claude-sonnet-5-5-medium` findings: Employment pool selector: 5 slots, min_score=0.86, threshold=0.86, gate_ok=True

### `insurtech_narrative`

- **Pre-Stub Keyed Output** (`gpt-5.6-luna`, 32 words):
```text
Operationalized cloud modernization as a governed bridge from emerging analytics to insurer decision workflows, aligning control ownership and core-system integration so regulated organizations could move from platform strategy to dependable, business-ready execution.
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.8** (0_to_5, PASS)

- **Real IDE CLI Run Output** (`gpt-5.6-luna`, 28 words):
```text
Anchored enterprise technology adoption in executable architecture and control ownership, making advanced decisioning usable across insurer operating environments while balancing integration complexity, governance expectations, and dependable production outcomes.
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 41938 tok, conv `139975f0`); `gemini-4-neon-high`: **4.6** (0_to_5, PASS, 49573 tok, conv `f2efcb8f`)
  - `gemini-4-argon-medium` findings: InsurTech narrative sentence is concise (28 words, 263 chars), well-grounded in reb_insurtech_* bundles, and clearly differentiated from the companion bullets.
  - `gemini-4-neon-high` findings: All 13 deterministic gates pass with proof-bound reb_insurtech_* citations and low overlap against companion bullets.; Phrasing is slightly abstract in places but remains clear, executive-appropriate, and grounded in allowed role episode bundles.

### `insurtech_bullets`

- **Pre-Stub Keyed Output** (`claude-sonnet-5`, 52 words):
```text
- bul_insurtech_001: Implemented SOC 2-aligned AWS control frameworks for regulated insurers adopting analytics and ML capabilities, reducing compliance risk and enabling auditable production deployment of data-driven underwriting tools.
- bul_insurtech_002: Directed AWS modernization efforts to integrate directly with policy administration, Guidewire-adjacent workflows, and core insurance data models, translating platform capabilities into business-line-ready operational systems.
```
- **Pre-Stub Keyed Judges**: `gemini-3.8-flash`: **4.8** (0_to_5, PASS); `claude-haiku-5-5`: **0.9** (0_to_1, PASS)

- **Real IDE CLI Run Output** (`gemini-4-neon-medium`, 42 words):
```text
- bul_insurtech_001: Implemented SOC 2-aligned AWS controls that enabled regulated insurers to adopt analytics and ML capabilities with auditable governance.
- bul_insurtech_002: Unified AWS modernization with core insurance operations by connecting cloud architecture directly to policy administration, Guidewire-adjacent workflows, and core insurance data models.
```
- **Real IDE CLI Dual Proof Judges**: `gemini-4-argon-medium`: **4.8** (0_to_5, PASS, 27524 tok, conv `5a703046`); `gemini-3.8-flash-high`: **4.8** (0_to_5, PASS, 48564 tok, conv `4b28cf34`); `claude-sonnet-5-5-medium`: **0.94** (0_to_1, PASS, 19493 tok, conv `f67ca27d`)
  - `claude-sonnet-5-5-medium` findings: Employment pool selector: 2 slots, min_score=0.93, threshold=0.86, gate_ok=True

