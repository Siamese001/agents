---
trigger: always_on
---

# Output Brevity & Word Budget Invariant

> On-demand rule. Applies to all agent responses and outputs within this repository.

## Invariant Specification

- **Target Word Count**: Approximately 150 to 250 words per response.
- **Hard Word Ceiling**: 450 words (5,000 characters) maximum strictly enforced on visible prose (`### Evidence & Graph Lineage` footers, HTML comments, Markdown link URLs, and table divider tokens are excluded from prose word/character counts).
- **Post-Turn Circuit Breaker**: `PostInvocation` brevity and prose rewrites fire at most once per gate (`< 1` retry) and at most twice across all post-turn intercepts per user turn, halting immediately if consecutive replies are identical so the chat UI never loops.
- **Information Density**: Deliver direct facts, verifiable code actions, and actionable results. Eliminate conversational preamble, pleasantries, fluff, and unnecessary repetition.

## Direct Inquiry Grounding & Anti-Evasion Invariant (`INV-DIRECT-INQUIRY-GROUNDING`)

1. **Itemized Dimension Coverage**: Whenever a user prompt specifies concrete architectural components, criteria, or subsystems (e.g. nodes, assertions, confidence, evidence, lineage), the agent's visible response must address each named dimension directly.
2. **Prohibition of Generic Analogies on Technical Inquiries**: Do NOT use conversational analogies (e.g. courtroom reporters, hospital charts, library catalogs) when answering architectural comparisons, trade-off evaluations, or technical defenses. Reserve the Rule 6 four-part analogy structure strictly for questions asking "what is feature X" or "how do I use feature X".
3. **Anti-Deflection Standard**: Never deflect the entire substantive answer into an external artifact while outputting abstract process boilerplate (propose, verify, build, record) in chat. The chat response must contain the direct facts, specific architectural decisions, and empirical defense within the word ceiling.

