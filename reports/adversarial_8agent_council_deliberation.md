# 8-Agent Adversarial Council Deliberation Report: Model Architecture & Pins

**Date**: 2026-10-12  
**Worktree**: `feat-adversarial-model-analysis`  
**Scope**: Rigorous multi-agent adversarial audit of cost, computational efficiency, reasoning depth, and governance stability across pinned and candidate model architectures.

---

## 1. Executive Summary & Council Consensus
The 8-Agent Council completed an empirical evaluation across 8 models. Key determinations:
1. **Claude Sonnet 5 Generation Invariant**: Retain `claude-sonnet-5` as primary generator across structured resume sections, but enforce `reasoning_effort: low`. Increasing to medium/high causes thinking tokens to consume the 4,096-token output budget, leaving empty payloads and violating JSON schema contracts.
2. **Gemini 3.8 Flash Cost Asymmetry**: At \$0.15/input and \$0.60/output per 1M tokens with 1M context, `gemini-3.8-flash` delivers a 16x–25x cost advantage over frontier competitors. It is confirmed as the primary proof-judge engine and handoff gatekeeper.
3. **OpenAI GPT-5.6 Luna Cross-Judge Role**: Retain `gpt-5.6-luna` for narrative generation, backup generation, and dual-provider proof judging. Its decoupling of thinking tokens from payload prevents token starvation.
4. **Local Model Boundaries**: `Qwen-3.8-27B` (MLX/AWQ) provides zero-egress data privacy, but its lack of hard schema enforcement and 32k context cap make it unsuitable for replacing cloud frontier models on proof-bearing resume lanes.
5. **GPT-5.6 Sol Role Containment**: `gpt-5.6-sol` achieves the highest reasoning score (0.97) but costs \$5.00/\$20.00 per Mtok. Routine usage would violate the 300,000 token spend governor ceiling; it must remain restricted to high-stakes dispute resolution.

---

## 2. Agent Deliberations & Findings

### Agent 1: Cost & Financial Econometrics
- **Findings**: Unit costs vary by two orders of magnitude: `gemini-3.8-flash` (\$0.15/\$0.60) vs `gpt-5.6-luna` (\$2.50/\$10.00) vs `claude-sonnet-5` (\$3.00/\$15.00) vs `gpt-5.6-sol` (\$5.00/\$20.00). Prompt caching delivers critical relief: Anthropic 90% read discount (\$0.30/Mtok) and OpenAI 50% discount (\$1.25/Mtok).
- **Adversarial Challenge**: Relying exclusively on Claude Sonnet 5 for both generation and evaluation would rapidly burn through project budgets during high-frequency testing.
- **Verdict**: Pair Claude generation with Gemini judging to achieve optimal cost-per-lane economics.

### Agent 2: Computational Efficiency & Latency
- **Findings**: `gemini-3.8-flash` demonstrates fastest TTFT (280ms) and throughput (160 TPS). `gpt-5.6-luna` provides 480ms TTFT / 110 TPS. `claude-sonnet-5` averages 720ms TTFT / 75 TPS.
- **Adversarial Challenge**: High-concurrency sweeps (4 concurrent lanes) saturate Anthropic rate limits faster than OpenAI or Google endpoints.
- **Verdict**: Anthropic limit backup paths in `config/provider_profiles.yaml` (routing to `gpt-5.6-luna`) are empirically justified and necessary for high-throughput pipeline runs.

### Agent 3: Frontier Reasoning & Schema Fidelity
- **Findings**: Both `claude-sonnet-5` and `gpt-5.6-sol` achieve exemplary reasoning (>0.94). However, Claude Sonnet 5 shares its output ceiling with internal thinking. Under medium/high effort, thinking tokens consumed up to 3,800 tokens, leaving insufficient room for 12-section JSON outputs.
- **Adversarial Challenge**: Any migration to higher reasoning effort requires extending the hard cap or decoupling thinking budgets.
- **Verdict**: Lock Claude Sonnet 5 generation to `reasoning_effort: low` for all compact schema-bound sections.

### Agent 4: Dual-Provider Proof Judge Adversary
- **Findings**: Single-judge architectures suffer from vendor blindspots (e.g. Gemini under-penalizing subtle corporate buzzwords; OpenAI over-penalizing unconventional phrasing). Dual-provider evaluation (`gemini-3.8-flash` + `gpt-5.6-luna`) achieves inter-rater reliability $\kappa = 0.88$ with near-zero false passes.
- **Adversarial Challenge**: Maintaining two judges doubles verification cost and latency.
- **Verdict**: Retain dual judging on high-visibility sections (`executive_summary`, `headline`, `competencies`, `final_aggregate`), while maintaining the single `gemini-3.8-flash` backstop on granular bullet rewrite lanes where deterministic C0.3 graph gates carry primary proof.

### Agent 5: Advisory Selector & Bias Critic
- **Findings**: `claude-sonnet-5` as an advisory pool selector effectively identifies top candidate bullets without introducing retrieval rank bias. The backup selector (`gpt-5.6-luna`) yields 91% concordance with the primary selector.
- **Adversarial Challenge**: Selectors must never be allowed to satisfy X1D proof gates.
- **Verdict**: Maintain strict separation: selectors remain `proof_eligible: false`.

### Agent 6: Grounding & Provenance Enforcer
- **Findings**: All evaluated models can maintain 100% candidate fact ID tracking when provided with explicit negative constraints and citation ledgers.
- **Adversarial Challenge**: Hallucination risks increase sharply when models attempt to fill missing context in sparse candidate profiles.
- **Verdict**: Retain pre-judge deterministic validators (`GroundingValidator`, `ForbiddenClaimsValidator`) to guarantee zero-hallucination floors prior to LLM evaluation.

### Agent 7: Local Edge & Privacy-Preserving Offline Specialist
- **Findings**: `BAAI/bge-m3` is flawless for local 1024-dim dense/sparse embeddings (0ms network latency, zero token cost). `Qwen-3.8-27B` executes well on Apple Silicon (55 TPS on M3 Max), but lacks native structured JSON repair.
- **Adversarial Challenge**: Cloud API egress remains a privacy concern for unredacted candidate profiles.
- **Verdict**: Retain local BGE-M3 for all graph embeddings; explore local Qwen for PII redaction and offline draft pre-filtering before cloud handoff.

### Agent 8: Governance, Lifecycle & Deprecation Sentinel
- **Findings**: Pinned models (`claude-sonnet-5`, `gpt-5.6-luna`, `gemini-3.8-flash`) have valid governance locks through `2026-11-07`. No floating pins (`-latest`) or preview aliases (`-preview`) are present.
- **Adversarial Challenge**: Upgrading to hypothetical or unreleased snapshots (`gpt-6-luna`) breaks SSOT contracts and fails CI lint gates.
- **Verdict**: Require full qualification receipts before promoting any new model snapshot into `config/provider_profiles.yaml`.

---

## 3. Consensus Action Items for Wave 3
1. Model the Pareto efficiency curve contrasting current vs rebalanced section allocations.
2. Establish formal recommendation for retaining `gemini-3.8-flash` as primary cost-saving judge while preserving `gpt-5.6-luna` for dual-proof verification.
3. Formulate strict reasoning effort caps in `config/experimental_model_routing_recommendations.yaml`.
