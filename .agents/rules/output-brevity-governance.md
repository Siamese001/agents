# Output Brevity & Word Budget Invariant

> On-demand rule. Applies to all agent responses and outputs within this repository.

## Invariant Specification

- **Target Word Count**: Approximately 120 words per response.
- **Hard Word Ceiling**: 300 words maximum strictly enforced under all conditions.
- **Information Density**: Deliver direct facts, verifiable code actions, and actionable results. Eliminate conversational preamble, pleasantries, fluff, and unnecessary repetition.

## Direct Inquiry Grounding & Anti-Evasion Invariant (`INV-DIRECT-INQUIRY-GROUNDING`)

1. **Itemized Dimension Coverage**: Whenever a user prompt specifies concrete architectural components, criteria, or subsystems (e.g. nodes, assertions, confidence, evidence, lineage), the agent's visible response must address each named dimension directly.
2. **Prohibition of Generic Analogies on Technical Inquiries**: Do NOT use conversational analogies (e.g. courtroom reporters, hospital charts, library catalogs) when answering architectural comparisons, trade-off evaluations, or technical defenses. Reserve the Rule 6 four-part analogy structure strictly for questions asking "what is feature X" or "how do I use feature X".
3. **Anti-Deflection Standard**: Never deflect the entire substantive answer into an external artifact while outputting abstract process boilerplate (propose, verify, build, record) in chat. The chat response must contain the direct facts, specific architectural decisions, and empirical defense within the word ceiling.

