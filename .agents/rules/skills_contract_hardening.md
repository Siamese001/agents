# Codex Skill-Contract Hardening

Date: 2026-07-13 (Updated: 2026-11-08)

## Decision

Repository-owned skills under `.agents/skills/` are procedural, on-demand adapters. Always-on policy remains in `AGENTS.md`, `.agents/rules/`, native lifecycle hooks, and deterministic commit gates. A skill explains how to execute or verify work, but invoking a skill is not itself proof that governance was satisfied.

## Active Catalog

- Retain strictly the 7 consolidated root skills under `.agents/skills/`:
  1. `agents-domain-assurance`
  2. `agents-governance-hygiene`
  3. `operational-gates`
  4. `receipt-auditor`
  5. `scope-containment`
  6. `security-hardening`
  7. `testing-framework`
- Keep skills self-contained; eliminate fragmented companion checklists and unverified sub-documents.
- Keep external/IDE skills segregated from repository skills.

## Contract Gates

The skill control plane validates:
1. Valid YAML frontmatter with exact `name` matching parent directory.
2. Concise, intent-focused single-line description within token budget (`INV-SKILLS-BUDGET-MAX-TOKENS`).
3. Complete link and path integrity: all internal links and tool paths referenced in `SKILL.md` must exist on disk.
4. No duplicate descriptions across skills.
5. `agents/openai.yaml` and `evals/` schema integrity for governed skills.

Canonical entrypoints:
```bash
.venv/bin/python tools/audit_skills_budget.py --json
.venv/bin/python tools/validate_turn_gates.py --mode pre-turn
```

## Authoring

New skills must include only reusable procedural knowledge, adhere to the context token budget, and provide `agents/openai.yaml` plus `evals/` when user-facing or state-changing.
