# Policy-Gated External Communications Engine (`outreach_engine` · `apps_lic`)

> **Reference Enterprise Workload: Governed External Messaging & Multi-Touch State Machine**  
> Demonstrates how the platform control plane enforces inbound prompt-injection airlocks, deterministic forbidden-claims linting, and multi-judge rubric gates on external communications.

---

## Architectural Role in the Platform

External communication is one of the highest-risk surfaces for enterprise AI deployment: an ungoverned agent can ingest adversarial third-party context, fabricate commercial or factual commitments, or violate communication compliance policies.

This reference workload exercises five core control-plane primitives:

1. **Inbound & Outbound Prompt-Injection Airlock**: Sanitizes untrusted external research briefs (`ResearchBriefEnvelope`) and blocks instruction-override payloads before prompt assembly.
2. **Forbidden-Claims & Compliance Linter**: Deterministic assertion gate that rejects uncorroborated metrics, unauthorized commitments, and spam-trigger phrasing prior to output emission.
3. **Contract-Bound Prompt Compilation**: Resolves declarative YAML templates with strict schema validation and instruction/data slot separation.
4. **Deterministic Multi-Touch State Machine**: Orchestrates state transitions across multi-step communication sequences with full replayability.
5. **Multi-Judge Rubric Evaluation**: Evaluates grounding fidelity, policy compliance, and channel constraints before clearing Exit Evaluation.

---

## Verification & Execution

```bash
# Run the reference workload in demo mode
python -m outreach_engine --demo

# Execute the subsystem unit and airlock regression suite
pytest outreach_engine/tests/ -v --timeout=60
```
