# State and memory taxonomy

## Ephemeral execution state
Current step, local variables, pending tool responses. Usually short-lived and runtime-owned.

## Task state
Durable status, inputs, outputs, checkpoints, approvals, and continuation identifiers for a unit of work.

## Conversation state
Turns and interaction context needed to maintain a dialogue. Not automatically durable memory.

## Working memory
Temporary synthesized context selected for the current reasoning window.

## Durable user memory
Explicitly permitted preferences or long-lived facts about a user. Requires correction/deletion and privacy controls.

## Episodic memory
Records of prior events/interactions used to inform future behavior. Requires relevance and retention rules.

## Semantic knowledge
Organizational/domain knowledge, ideally source-backed and governed separately from model-generated memory.

## Evidence/provenance
Source material bound to claims or decisions. Preserve exact locators and integrity metadata when governance requires it.

## Guidance
Derived recommendations or patterns. Keep distinct from approved factual knowledge.
