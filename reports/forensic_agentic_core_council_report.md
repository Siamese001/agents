# Forensic Investigation: The Zombie Persistence of `agentic_core` Across the Monorepo

**Council Convened**: 10-Agent Autonomous Forensic Council  
**Date**: October 11, 2026  
**Worktree Branch**: `feat/agentic-core-forensics`  
**Base Commit**: `f8b0ba50cb` (branched from `feat/outreach-research-audit`)  
**Decommission Commit Under Audit**: `0289fb1af7a4bab9b588b2f1d9f831859e691b15` (Tue Sep 8 04:36:32 2026)  
**Primary Invariant Question**: *Why are `agentic_core` references, phantom imports, and zombie boundary invariants still permeating agent prompts, governance rules, workflows, configs, and subsystem documentation when the physical core was decommissioned?*

---

## Executive Summary & Forensic Verdict

On September 8, 2026, commit [`0289fb1af7`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics) executed a massive decommissioning titled `chore(decommission): retire agentic_core, apps_shared, legacy apps, and orphaned tests`. In that single transaction, **3,711 files** in `agentic_core/`, **284 files** in `apps_shared/`, and **3,447 test files** were physically deleted from git.

However, the Council's multi-layered audit reveals an acute architectural failure mode: **Incomplete Surgical Decommissioning (Phantom Core Syndrome)**.

The physical deletion of the Python modules was executed, but **zero cleanup was performed on the secondary and tertiary cognitive planes**:
1. **Active Python Runtime Traps**: `infrastructure/__init__.py`, `infrastructure/reasoning/cross_layer_coherence.py`, and `infrastructure/sdks_mcps/gemini_client.py` still contain active `from agentic_core...` import statements hidden behind `try...except ImportError` guards.
2. **Global Agent Prompt Contamination**: The Antigravity IDE global skills directory (`~/.gemini/config/skills/security-hardening`) is a live symlink to `.agents/skills/security-hardening/SKILL.md`. This file explicitly instructs the AI on every single session prompt: *"Invoke when changing production code (agentic_core/, apps_*/, system_learning/)"*.
3. **Negative Invariant Poisoning**: Subsystem documentation, specifically `outreach_engine/AGENTS.md` line 8, encoded the negative rule: `apps_lic_v2 is an independent, self-contained subsystem with ZERO imports of agentic_core or apps_shared`. When agents read this file, the negative mention acts as a prompt anchor, causing agents to repeatedly report and hallucinate `agentic_core` isolation checks in PR summaries.
4. **Configuration Zombie Graph**: Over **26 YAML and JSON files** in `config/` (`expected_wiring.yaml`, `routing_thresholds.yaml`, `rubrics.yaml`, `ast_signals.yaml`) still explicitly map runtime dependencies, proof tests, and schema identifiers to non-existent `agentic_core` paths.
5. **CI/CD Latent Landmines**: 9 GitHub Actions workflow definitions (`.github/ci-lanes.yaml`, `hitl-integrity-gate.yml`, `runtime-smokes.yml`) still define path triggers on `agentic_core/**` or attempt direct Python imports of `agentic_core.L3_orchestration` and `agentic_core.L5_safety`.
6. **Tooling & Build Scaffolding**: `pyproject.toml` declares `source = ["agentic_core"]`, `pytest.ini` defines custom markers for `agentic_core/L0-L6`, and `.pre-commit-config.yaml` points pre-commit hooks to dead entrypoint scripts like `agentic_core/L0_routing/scripts/run_guardian_c0_sovereignty.py`.

---

## The 10-Agent Council Forensic Testimonies

```
                                  +---------------------------------------+
                                  |         10-AGENT COUNCIL CHAIR        |
                                  |  Root Cause Collapse & Roadmap (A10)  |
                                  +-------------------+-------------------+
                                                      |
         +--------------------+-----------------------+-----------------------+--------------------+
         |                    |                       |                       |                    |
+--------v-------+   +--------v-------+      +--------v-------+      +--------v-------+   +--------v-------+
|  Agent 1 (Git) |   | Agent 2 (AST)  |      | Agent 3 (Doc)  |      | Agent 4 (Sys)  |   | Agent 5 (Conf) |
| Decommission   |   | Active Python  |      | Negative Rule  |      | Global Prompt  |   | 26 Config YAML |
|  Archaeology   |   | Runtime Traps  |      |   Poisoning    |      | Injections     |   | Zombie Graphs  |
+----------------+   +----------------+      +----------------+      +----------------+   +----------------+
         |                    |                       |                       |                    |
+--------v-------+   +--------v-------+      +--------v-------+      +--------v-------+   +--------v-------+
| Agent 6 (CI)   |   | Agent 7 (Build)|      | Agent 8 (Arch) |      | Agent 9 (Rule) |   | Agent 10 (Syn) |
| GitHub Action  |   | pyproject &    |      | Dead Code &    |      | 19 Governance  |   | Pure Subsystem |
| Latent Crashes |   | pre-commit     |      | Fixture Relics |      | Zombie Rules   |   | Emancipation   |
+----------------+   +----------------+      +----------------+      +----------------+   +----------------+
```

---

### Agent 1: Git Forensic Archaeologist
- **Focus**: The historical decommission transaction and blast radius.
- **Empirical Evidence**:
  - Commit [`0289fb1af7a4bab9b588b2f1d9f831859e691b15`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics) committed by Siamese001 on Tue Sep 8 04:36:32 2026.
  - Diff breakdown:
    - `agentic_core/`: 3,711 files deleted.
    - `apps_shared/`: 284 files deleted.
    - `tests/`: 3,447 files deleted.
    - `apps_lic/`: 348 files deleted / restructured into `outreach_engine/`.
    - `apps_rg/`: 929 files deleted / restructured into `resume_graph_engine/`.
  - Total commit deletion: **8,720 files, 1,000,000+ lines removed**.
- **Forensic Finding**:
  - The commit was a brute-force directory deletion of `agentic_core/`. It failed to perform a cross-repository string and symbol sweep across documentation, workflows, linters, pre-commit configs, or declarative manifests. It decapitated the code while leaving the administrative nervous system intact.

---

### Agent 2: Runtime & AST Codebase Detective
- **Focus**: Active Python files currently attempting to import `agentic_core`.
- **Empirical Evidence**:
  AST parsing and regex analysis discovered active import lines in active repository files:
  1. [`infrastructure/__init__.py`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/infrastructure/__init__.py#L6):
     ```python
     try:
         from agentic_core.runtime.contracts import lifecycle_trace_contract as trace_contract
     except ImportError:
         trace_contract = None
     ```
  2. [`infrastructure/reasoning/cross_layer_coherence.py`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/infrastructure/reasoning/cross_layer_coherence.py#L672):
     ```python
     from agentic_core.L6_system_learning.system_learning_memory_bridge import get_sl_memory_bridge
     ```
  3. [`infrastructure/sdks_mcps/gemini_client.py`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/infrastructure/sdks_mcps/gemini_client.py#L39):
     ```python
     from agentic_core.L2_execution.reasoning.prompt_messages import PromptMessages
     ```
  4. [`docs/reports/agent_inventory/_generate_runtime_assessment.py`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/docs/reports/agent_inventory/_generate_runtime_assessment.py#L15):
     ```python
     from agentic_core.L2_execution.types.agent_taxonomy_registry import AGENT_TAXONOMY_MAP
     from agentic_core.runtime.entrypoints.integrated_single_action_spine_run import run_integrated_single_action_spine
     ```
  5. [`docs/svp/demo_script.py`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/docs/svp/demo_script.py#L12):
     ```python
     from agentic_core.L4_state.reasoning.retrieval_layers import RetrievalOrchestrator, L4AgenticActions
     ```
- **Forensic Finding**:
  - `infrastructure/` was never properly adapted post-decommission. It relies on silent `try...except ImportError` blocks that suppress runtime crashes, hiding the fact that telemetry, memory bridges, and prompt helpers are pointing to ghost modules.

---

### Agent 3: Subsystem Boundary & Manifest Detective
- **Focus**: The origin of the specific phrase that triggered this audit.
- **Empirical Evidence**:
  - In [`outreach_engine/AGENTS.md`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/outreach_engine/AGENTS.md#L8):
    ```markdown
    - `apps_lic_v2` is an independent, self-contained subsystem with ZERO imports of `agentic_core` or `apps_shared`.
    ```
  - In root [`AGENTS.md`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/AGENTS.md#L110):
    ```markdown
    Apps customize inputs; core enforces contracts. No app leakage in `agentic_core` without migration receipt. Multi-provider X1D proof panels: `agentic_core/runtime/judges/panel/` ... Detail: `agentic_core/AGENTS.md`
    ```
- **Forensic Finding**:
  - The author of `outreach_engine/AGENTS.md` attempted to enforce architectural autonomy by writing a negative boundary invariant.
  - In LLM cognitive architectures, **negative constraints ("do not think of a pink elephant") function as prime semantic anchors**. When the agent reads `ZERO imports of agentic_core`, the concept `agentic_core` enters the agent's active working memory. The agent then dutifully checks for it, reports on it, and preserves the dead name in subsequent turn summaries.

---

### Agent 4: Antigravity Agent Runtime & Skills Inspector
- **Focus**: Why the agent itself references `agentic_core` unprompted.
- **Empirical Evidence**:
  - Inspecting the global user skill directory on macOS:
    ```
    /Users/amitayer/.gemini/config/skills/security-hardening -> /Users/amitayer/Git/agents/.agents/skills/security-hardening
    ```
  - Contents of [`.agents/skills/security-hardening/SKILL.md`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.agents/skills/security-hardening/SKILL.md#L3):
    ```markdown
    description: Procedure for passing security validation before commit — no hardcoded secrets, no sensitive data in logs, vetted dependencies, and authorization checks on sensitive operations. Invoke when changing production code (agentic_core/, apps_*/, system_learning/), adding or updating a dependency, modifying logging, touching auth/authorization logic, or before committing any security-sensitive change.
    ```
  - Contents of [`.agents/skills/receipt-auditor/SKILL.md`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.agents/skills/receipt-auditor/SKILL.md#L12):
    ```markdown
    Ensures every `agentic_core` modification is documented with proper classification, tests, and migration path.
    ```
- **Forensic Finding**:
  - Every single Antigravity prompt sent to Gemini or Claude contains `<skills>` extracted from `~/.gemini/config/skills/`.
  - Because `~/.gemini/config/skills/security-hardening` is symlinked to the monorepo's `.agents/skills/security-hardening`, the system prompt injects `agentic_core/` into the model's instructions on **every turn of every conversation**. The model is literally told that `agentic_core` is production code.

---

### Agent 5: Configuration & Declarative Manifest Archaeologist
- **Focus**: Dead references in `config/`.
- **Empirical Evidence**:
  A repository grep reveals **26 declarative configuration files** with hundreds of `agentic_core` references:
  1. [`config/expected_wiring.yaml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/config/expected_wiring.yaml): Contains 15+ sections defining `entry_module: agentic_core/L0_routing/...`, `proof_test: tests/unit/agentic_core/...`.
  2. [`config/routing_thresholds.yaml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/config/routing_thresholds.yaml): Cites `agentic_core/runtime/config/routing_thresholds.py` as primary consumer.
  3. [`config/judges/rubrics.yaml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/config/judges/rubrics.yaml): Sets `schema: agentic_core.evaluation.judges.rubric_schema_v1`.
  4. [`config/retrieval/calibration_manifest.yaml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/config/retrieval/calibration_manifest.yaml): Sets roots to `agentic_core/knowledge/retrieval` and `agentic_core/L4_state/utils/memory`.
  5. [`config/structure_blueprint/structure_policy.yaml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/config/structure_blueprint/structure_policy.yaml): Declares `agentic_core` as a permanent committed root.
- **Forensic Finding**:
  - The configuration subsystem is frozen in a pre-decommission state. Any tool or validator parsing these files expecting to find backing Python code will either fail or require special bypasses.

---

### Agent 6: CI/CD & Pipeline Forensic Inspector
- **Focus**: Workflows and GitHub CI configurations.
- **Empirical Evidence**:
  1. [`.github/ci-lanes.yaml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.github/ci-lanes.yaml#L127-L131): Declares active path filters for `agentic_core/runtime/**`, `agentic_core/L2_execution/**`, `agentic_core/L3_orchestration/**`, `agentic_core/L5_safety/**`, and `agentic_core/L7_auditability/**`.
  2. [`.github/workflows/hitl-integrity-gate.yml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.github/workflows/hitl-integrity-gate.yml#L48-L52):
     ```python
     from agentic_core.L3_orchestration.exit_control.ledger_integrity import AuditChain
     from agentic_core.L3_orchestration.exit_control.runtime_hitl_ledger import RuntimeHitlLedger
     from agentic_core.L5_safety.exit_control.hitl_classes import HitlClass
     ```
  3. [`.github/workflows/adg-hardening-contracts.yml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.github/workflows/adg-hardening-contracts.yml#L13-L21): Path triggers on `agentic_core/adg/**` and `agentic_core/L6_system_learning/**`.
  4. [`.github/workflows/runtime-smokes.yml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.github/workflows/runtime-smokes.yml#L40-L42): Inspects `agentic_core/runtime/manual_dispatch.py`.
- **Forensic Finding**:
  - Several CI workflows are ticking time bombs: if triggered, they will crash on missing modules. Many workflows are completely dead because the paths they trigger on no longer exist.

---

### Agent 7: Tooling, Pre-commit & Build Systems Sleuth
- **Focus**: Build descriptors, linters, and hooks.
- **Empirical Evidence**:
  1. [`pyproject.toml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/pyproject.toml#L135):
     ```toml
     source = ["agentic_core"]
     ```
  2. [`pytest.ini`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/pytest.ini#L6):
     ```ini
     # This makes tools.adg, apps_*, agentic_core importable in every worker
     pythonpath = src tools
     ```
     Along with ADG markers `adg_l0` through `adg_l6` defining `agentic_core/L0_*` through `L6_*`.
  3. [`.pre-commit-config.yaml`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.pre-commit-config.yaml#L669):
     ```yaml
     entry: py agentic_core/L0_routing/scripts/run_guardian_c0_sovereignty.py
     ```
- **Forensic Finding**:
  - The build, testing, and pre-commit harness still considers `agentic_core` a primary source tree.

---

### Agent 8: Dead Code, Provenance & Merkle Artifact Sleuth
- **Focus**: Historical archives and test fixtures.
- **Empirical Evidence**:
  - `artifacts/archives/adg_dead_code/2026-04-23/agentic_core/`: Contains dead code preserved for archival analysis.
  - `resume_graph_engine/tests/fixtures/e2e_failure_20260808T062125Z_c9caf451/`: Contains recorded historical JSON traces (`agentic_core_how_trace.json`, `agentic_core_spine_proof.json`) from when the monorepo still ran the old spine.
  - `resume_graph_engine/tests/unit/apps_rg/test_public_cli_surface.py:83`:
    ```python
    def test_agentic_core_is_physically_absent() -> None:
        assert not (REPO_ROOT / "src" / "agentic_core").exists()
        assert not (REPO_ROOT / "tests" / "unit" / "agentic_core").exists()
        assert not (REPO_ROOT / "agentic_core").exists()
    ```
- **Forensic Finding**:
  - While test fixtures and historical ADRs intentionally preserve `agentic_core` as an archival artifact (annotated with *Archival Provenance Notice*), the failure was treating active configs with the same passivity as archival records.

---

### Agent 9: Rule Engine & Governance Map Auditor
- **Focus**: Active rules in `.agents/rules/`.
- **Empirical Evidence**:
  **19 rule files** still actively regulate `agentic_core`:
  - [`.agents/rules/boundary-audit-required.md`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.agents/rules/boundary-audit-required.md#L3): *"Run /core-boundary-audit when any agentic_core/ or *_binding.py changes"*.
  - [`.agents/rules/git-branch-per-chat.md`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.agents/rules/git-branch-per-chat.md#L3): *"Core / agentic_core / infrastructure / governance work touches no apps_<x> file"*.
  - [`.agents/rules/conformance-map.md`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.agents/rules/conformance-map.md#L80): Maps rules to `agentic_core/AGENTS.md`.
  - [`.agents/rules/l6_apps_eval_microstep_alignment_invariant.md`](file:///Users/amitayer/Git/agents/.worktrees/agentic-core-forensics/.agents/rules/l6_apps_eval_microstep_alignment_invariant.md#L9): References `agentic_core/L6_observability/shadow_eval/microsteps.py`.
- **Forensic Finding**:
  - The governance rule engine is hallucinating boundaries for a non-existent territory. Rules that enforce "no leakage into agentic_core" confuse agents into thinking `agentic_core` is a live subsystem they must protect.

---

### Agent 10: Chief Forensic Investigator & Council Chair (Synthesis)
- **Unified Root Cause Indictment**:
  The presence of `agentic_core` in recent discussions and outputs is **NOT** a sign that code was re-introduced or un-deleted.
  Rather, it is the result of a **tripartite feedback loop of cognitive contamination**:
  1. **Prompt Ingestion**: Antigravity loads `.agents/skills/security-hardening/SKILL.md` (via `~/.gemini/config/skills/`), which explicitly commands the LLM to inspect `agentic_core/`.
  2. **Subsystem Framing**: `outreach_engine/AGENTS.md` and root `AGENTS.md` define architectural purity negatively (*"ZERO imports of agentic_core"*).
  3. **Cognitive Echo**: The agent reads these instructions and dutifully verifies and reports that `agentic_core` was not imported. The human user, knowing that `agentic_core` was supposed to have been killed in September, hears the agent mention `agentic_core` and rightfully asks: *"what the fuck is going on?"*

---

## 5-Wave Total Extinction Roadmap (Purging the Ghost)

To permanently eradicate all zombie references and prevent any agent from ever hallucinating or referencing `agentic_core` again, the Council recommends executing the following structured waves in this worktree:

| Wave | Scope | Action Items |
|---|---|---|
| **Wave 1: Active Code & Infrastructure Purge** | `infrastructure/`, `docs/reports/` | Remove all `from agentic_core...` imports; replace `trace_contract` shims with direct no-op or native telemetry. |
| **Wave 2: Skills & Agent Prompt Sanitization** | `.agents/skills/`, `~/.gemini/config/skills/` | Update `security-hardening/SKILL.md`, `receipt-auditor/SKILL.md`, and `testing-framework` to remove `agentic_core/` triggers. |
| **Wave 3: Subsystem AGENTS.md & Negative Invariant Reframe** | `outreach_engine/AGENTS.md`, `AGENTS.md` | Reframe negative rules to positive self-containment (*"Self-contained subsystem with standard library & local package dependencies only"*). |
| **Wave 4: Configuration & Declarative Schema Cleanout** | `config/*.yaml`, `pyproject.toml`, `pytest.ini` | Purge dead `agentic_core` references from `expected_wiring.yaml`, `routing_thresholds.yaml`, `pyproject.toml`, and `pytest.ini`. |
| **Wave 5: CI/CD & GitHub Workflow Decommissioning** | `.github/workflows/`, `.github/ci-lanes.yaml` | Remove dead workflows (`hitl-integrity-gate.yml`, etc.) and dead path triggers. |
