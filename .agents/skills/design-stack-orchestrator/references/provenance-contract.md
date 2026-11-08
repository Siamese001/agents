# Provenance contract

For dynamic factual objects, prefer these fields:

- `id`
- `title`
- `status`
- `owner`
- `source`
- `source_timestamp`
- `effective_date`
- `last_verified`
- `next_review`
- `confidence`
- `hitl`

A current factual assertion should normally include `owner`, `source`, and `last_verified`.

Mark `hitl=true` when the source is missing, conflicting, only proposed/conditional, or requires a human approval decision.
