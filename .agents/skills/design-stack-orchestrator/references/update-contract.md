# Update contract

Produce these artifacts when practical:

- `content_snapshot.json`: normalized current records with stable IDs and provenance.
- `content_patch.json`: adds, updates, retirement candidates, and conflicts.
- `hitl_register.json`: unresolved decisions with evidence, recommendation, and affected objects.
- `refresh_report.md`: concise summary of what changed and what remains blocked.

## Record shape

Recommended fields:

- `id`
- `type`
- `title`
- `fields`
- `status`
- `source`
- `source_timestamp`
- `effective_date`
- `owner`
- `last_verified`
- `next_review`
- `confidence`
- `hitl`

Do not require every field for static decorative content.
