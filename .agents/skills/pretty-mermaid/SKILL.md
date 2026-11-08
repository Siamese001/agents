---
name: pretty-mermaid
description: Author Mermaid, Draw.io, and SVG diagrams for visual documentation, flowcharts, sequence diagrams, state diagrams, ER diagrams, and system architectures.
---

# Pretty Mermaid

Create concise Mermaid diagram source with deliberate hierarchy and readable labels.

## Workflow

1. Pick the smallest Mermaid diagram type that expresses the relationship correctly.
2. Author the `.mmd` source.
3. Apply the readability rules in `references/mermaid-style.md`.
4. Run `python scripts/check_mermaid.py <file.mmd>` for basic structural checks.
5. If a Mermaid renderer such as `mmdc` is already available locally, render to SVG.
6. If no renderer is available, deliver the `.mmd` source and, when a preview matters, create a companion SVG using an available local visual skill. Do not install packages or require network access unless the user explicitly asks.

## Diagram Choice

- `flowchart`: process, architecture, dependency, branching.
- `sequenceDiagram`: time-ordered interactions.
- `stateDiagram-v2`: state transitions.
- `classDiagram`: type relationships.
- `erDiagram`: data entities and cardinality.
- `timeline`: chronological milestones where supported.

## Readability Rules

- Keep node labels brief and put detail in annotations outside the diagram when possible.
- Limit a single diagram to one dominant story.
- Use subgraphs only for true boundaries such as domains, teams, trust zones, or layers.
- Prefer one flow direction.
- Avoid decorative styling that reduces portability.
- Escape labels that contain punctuation Mermaid could interpret as syntax.

## Output Contract

Deliver the `.mmd` source, validation status, and a rendered artifact only when available or requested.

## Source Lineage

See `references/source.md`.
