# Outreach Engine (outreach_engine)

> Autonomous Lifecycle Intelligence & Grounded Executive Outreach Engine v2.
> Decoupled, contract-governed outreach synthesis with zero monolithic framework dependencies.

## Key Capabilities

1. **Grounded Outreach Authoring**: Generates channel-tailored outreach communications (email, LinkedIn InMail, follow-ups) strictly anchored to verified facts in target company profiles and executive candidate briefs.
2. **Dynamic YAML Prompt Compiler**: Resolves prompt templates (`exec_positioning.yaml`, `compact_recruiter_arc.yaml`, `outreach_draft_v2.yaml`) dynamically with strict context validation.
3. **Forbidden Claims Guardrails**: Hard assertion gate rejecting ungrounded compensation, unverifiable tenure claims, and policy-forbidden phrasing before output dispatch.
4. **Mission Fixture Ingestion**: Ingests realistic JSON mission fixtures (e.g. `charles_truist_mission.json`) to drive reproducible candidate-to-executive narratives.
5. **Deterministic Multi-Touch Cadence Engine**: Generates spaced, channel-diverse follow-up sequences across days 1 through 14.
6. **Automated Rubric Evaluation**: Pluggable judge panel evaluating grounding adherence, narrative flow, and channel length constraints.

## Quickstart

```bash
cd outreach_engine

# Run the end-to-end demo
python -m outreach_engine --demo

# Run with a target mission fixture
python -m outreach_engine --mission data/fixtures/charles_truist_mission.json

# Run unit and integration tests
pytest tests/
```