# Adversarial Red Team Report: L1 Reasoning Step & Optimization Plan

## Status & Scope
- **Branch**: `antigravity/redteam-l1-reasoning` (branched off local `main` at `fcacf1f36`)
- **Objective**: Adversarial Agent Red Team assessment of the L1 reasoning step in `apps_rg_v2`, validating user hypothesis regarding "glorified planning", and formulating concrete optimization paths.
- **Mode**: Plan-only analysis and architectural design.

---

## 1. Executive Verdict & Validation of Hypothesis

> **User Assertion**: *"I do not feel L1 is doing anything but glorified planning."*

**Verdict: Confirmed.**
The L1 pipeline step is not performing semantic reasoning, trade-off optimization, candidate fit analysis, or strategic planning. It is a **deterministic, zero-model, zero-evidence regex parser wrapped in over 7,000 lines of cryptographic hashing, immutable dictionary wrappers, and synthetic schema verification.**

---

## 2. Detailed Technical Red-Team Findings

### 2.1 The "Cognitive Theater" Architecture
The codebase employs an extensive vocabulary suggesting high-order cognitive processes:
- `atomic_requirement_graph`
- `feasibility_graph`
- `alternative_plan_ledger`
- `critique_ledger`
- `cognition_plan`
- `self_consistency_intent` & `reflexion_intent`

However, inspection of the actual implementation reveals complete detachment from real reasoning:

1. **Zero-Authority & Zero-Evidence Mandate**:
   ```python
   # apps_rg/runtime/bindings/l1_binding.py:4-5
   "Deterministic only. No C0, PA, L2, tool, provider, or write calls."
   non_authority_assertion = {
       "no_evidence_retrieval": True,
       "no_pa_assembly": True,
       "no_model_call": True,
       "no_c0_import": True,
   }
   ```
   L1 is architecturally firewalled from candidate evidence. It does not know who the candidate is, what projects they have worked on, what skills they possess, or what trade-offs exist between their experience and the target job description (JD).

2. **The "Feasibility Graph" is Purely Synthetic**:
   In `apps_rg/runtime/bindings/l1_cognitive_planner_v3.py:1423-1517`, `_feasibility_graph()` iterates over regex-extracted requirements and blindly generates two static options for every single requirement:
   - **Option 1 (`TARGET_WORK_UNIT`)**: Hardcoded string `assumption_code="C0_CAN_VERIFY_REQUIREMENT_SUPPORT"`, `rationale_code="TYPE_AND_QUALIFIER_COMPATIBLE_TARGET"`.
   - **Option 2 (`ESCALATE`)**: Hardcoded string `assumption_code="NAMED_RESOLVER_CAN_RESOLVE_UNSUPPORTED_SCOPE"`, `rationale_code="ALTERNATIVE_SAFE_PATH"`.
   There is no feasibility evaluation whatsoever; it is merely an unconditional pair of dummy records.

3. **The "Alternative Plan Ledger" is a Trivial Fallback**:
   In `apps_rg/runtime/bindings/l1_cognitive_planner_v3.py:1607-1671`, `_alternative_plan_ledger()` chooses Option 1 if a target unit ID was regex-mapped, or Option 2 if unmapped. No alternative space is searched.

4. **The "Critique Ledger" is String Checking**:
   In `_critique_ledger()`, the "critique" consists solely of checking whether the JD text or target role strings are empty, or whether hardcoded conflict patterns fired.

5. **The "Cognition Plan" Does Not Execute**:
   In `apps_rg/runtime/bindings/l1_planning_capsule.py:1122-1145`, `_cognition_plan()` records:
   - `controls_applied: False`
   - `execution_provability: "ADVISORY_ONLY_UNTIL_L2_RECEIPT"`
   - `authority_class: "L2_OR_L3_MUST_PROVE_EXECUTION"`
   L1 itself runs no self-consistency sampling or reflexion loops.

---

### 2.2 Massive Schema Inflation & Boilerplate Tax
Over **7,000 lines of Python code** implement the L1 boundary across 5 modules:
- `src/apps_rg/runtime/bindings/l1_cognitive_planner_v3.py` (3,111 lines)
- `src/apps_rg/runtime/bindings/l1_planning_capsule.py` (1,271 lines)
- `src/apps_rg/runtime/bindings/l1_planning_capsule_v2.py` (1,220 lines)
- `src/apps_rg/runtime/bindings/l1_cognitive_consumption.py` (1,231 lines)
- `src/apps_rg/runtime/contracts/l1_cognitive_output_disposition.py` (1,234 lines)

The system simultaneously generates and cross-validates **three parallel capsule generations** (`v1`, `v2`, and `v3`) for every run. Every dummy atom is recursively converted to `FrozenDict`, serialized with canonical JSON separators, hashed with SHA-256, stamped with prefixed IDs (`l1opt-...`, `l1decide-...`, `l1crit-...`), and verified against strict schemas.

---

### 2.3 Downstream Token Bloat & Generation Degradation
In `section_prompt_adapter.py` and `governed_pa_compose.py`, the L1 cognitive advisory is injected into the LLM prompt:
```text
<L1_COGNITIVE_ADVISORY>
L1 cognitive goal constraints: preserve every closed-vocabulary directive below...
L1 cognitive atomic coverage: make one distinct source-grounded content decision for every listed atom...
L1 cognitive atom: id=req-001; type=TECH_SKILL; modality=MUST; criticality=CRITICAL; qualifiers=...; qualifier_scope=SHARED_PARENT; decomposition=ATOMIC; relations=...; planned_decision=REQUIRE; feasibility=FEASIBLE; preconditions=...; alternative=none; risk=LOW; covered_audit_tag=L1_COGNITIVE_ATOM:req-001:COVERED.
...
L1 cognitive audit action: add one non-display change_log string per listed atom: L1_COGNITIVE_ATOM:<id>:COVERED only when a distinct allowed-source output element covers it, otherwise L1_COGNITIVE_ATOM:<id>:GAP.
</L1_COGNITIVE_ADVISORY>
```

#### Negative Impacts:
1. **Token Cost**: Adds 800–1,500 tokens of dense metadata to **every section lane prompt** (headline, executive summary, unify bullets, ibm bullets, narrative, competencies). For a full resume generation run, this wastes 10,000–15,000 prompt tokens.
2. **Attention Degradation**: Frontier models suffer from attention dispersion when flooded with dense, repetitive pseudo-code tokens instead of clean stylistic guidance and candidate facts.
3. **Output Contamination**: Forcing models to generate `L1_COGNITIVE_ATOM:<id>:COVERED` inside change logs turns the generation model into a compliance bookkeeper rather than crafting high-impact executive prose.

---

### 2.4 Brittle Failure Modes & Attack Vectors
1. **Formatting Fragility**: Slicing JDs via regexes (`\b(?:must|required|minimum|\d+\+?\s+years?)\b` and header markers) causes non-traditional JDs (narrative postings, markdown tables) to yield 0 requirements or misclassify core requirements.
2. **Combinatorial Atom Splitting**: Splitting sentences via `_COMPOUND_RE` (`and`, `or`, `;`) explodes complex requirements into dozens of micro-atoms, overwhelming the prompt.
3. **Brittle Finalization Blocks (`X3_BLOCK_L1_COGNITIVE_OUTPUT`)**: In `l1_cognitive_output_disposition.py`, unmapped critical requirements trigger hard terminal blocks without any replanning or adaptive pivot capability.

---

## 3. Architectural Optimization Roadmap

### Option A: Lean Deterministic Normalizer (Pragmatic De-bloat) — RECOMMENDED
Acknowledge that L1 is an ingress parsing and structuring step, not a reasoning step:
1. **De-bloat the Prompt**:
   - Replace `<L1_COGNITIVE_ADVISORY>` with a concise `<TARGET_REQUIREMENTS>` block (under 150 tokens) listing the primary role objectives, seniority level, and key competencies.
   - Eliminate mandatory non-display `L1_COGNITIVE_ATOM:<id>:COVERED` audit tags from the generation prompt.
2. **Consolidate Capsules**:
   - Retire the redundant parallel construction of `v1`, `v2`, and `v3` capsules in `l1_binding.py`.
   - Remove the synthetic `_feasibility_graph()`, `_alternative_plan_ledger()`, and `_critique_ledger()` string builders.
3. **Soften X3 Veto Gates**:
   - Convert hard finalization blocks (`X3_BLOCK_L1_COGNITIVE_OUTPUT`) into diagnostic warnings and advisory score penalties, preventing minor keyword mismatches from aborting viable runs.

### Option B: Post-C0 Strategic Reasoning (True Reasoning Architecture)
If true reasoning is desired in Apps RG, it must be placed **after C0 graph retrieval**:
1. **Positioning**: Introduce a new reasoning step between C0 and PA:
   ```text
   U0 (Ingress) -> L1 (Target Normalization) -> L0 (Routing) -> C0 (Evidence Graph) -> [L1.5 Strategic Fit Reasoner] -> PA -> L2
   ```
2. **Responsibilities of L1.5**:
   - **Career Thesis Synthesis**: Synthesize the candidate's overarching value proposition relative to the target role.
   - **Evidence Gap Mitigation**: Identify requirements not directly supported by candidate facts and formulate intentional narrative pivots.
   - **Cross-Section Thematic Allocation**: Decide which achievements and proof points belong in the Executive Summary vs. Bullet Lanes.

---

## 4. Verification and Governance Protocol
All future implementation on this branch must conform to `RULE[AGENTS.md]`:
1. Use `codex-defender run --policy .codex/runtime-boundary.json --command ...` for explicit test verification.
2. Verify token reductions across compiled section prompts (`compile_section_prompt`).
3. Validate that resume generation utility and fact grounding remain preserved while eliminating prompt bloat.
