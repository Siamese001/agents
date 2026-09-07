# apps_lic_v2 (Lifecycle Intelligence & Communication Engine)

`apps_lic_v2` is a standalone, decoupled executive outreach and candidate lifecycle communication system. It generates grounded, high-converting outreach communications (LinkedIn InMail, connection notes, executive emails, follow-up sequences) with strict anti-hallucination guardrails and automated spam/compliance validation.

## Key Architectural Principles
- **Zero Core Dependency**: 100% decoupled from `agentic_core`. No Redis, no heavyweight UWG, no complex mixin hierarchies.
- **Strict Grounding**: Outbound drafts must only reference verified candidate achievements and facts. Fabricating relationships, metrics, or company details is strictly rejected.
- **Multi-Gate Validation**:
  1. *Spam Trigger Gate*: Detects false urgency, aggressive CTAs, and generic openers.
  2. *Channel Ceiling Gate*: Hard limits for LinkedIn InMail (2000 chars), connection requests (300 chars), and emails (1500 chars).
  3. *Question-Ending Gate*: Ensures messages conclude with low-friction, conversational calls to action.
  4. *Factual Grounding Gate*: Blocks unverified claims.
- **Cadence & Sequence Engine**: Plans cohesive multi-touch arcs (Day 1 Hook -> Day 4 Value Add -> Day 10 Low-friction Closing).
- **Rubric-Based Evaluation**: Automated 4-stage judge evaluation (Classification, Grounding, Alignment, Narrative).

## Quickstart CLI
```bash
# Run standalone outreach generation from fixture
python -m apps_lic --brief data/fixtures/truist_pascal_brief.json --channel inmail
```
