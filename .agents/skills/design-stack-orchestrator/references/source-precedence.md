# Source precedence and lifecycle

## Recommended source precedence

Use content-type-specific authority rather than one universal hierarchy.

- Staffing/assignment: approved staffing tracker > roster > accountable owner confirmation > current discussion.
- Asset state: approved asset inventory > fulfillment/return evidence > operations-owner confirmation.
- Org/reporting: current approved org source > leadership/vertical source > accountable leader confirmation > roster.
- Project scope/status: approved charter > current project status artifact > engagement-owner confirmation > staffing evidence > recent discussion.
- Onboarding procedure: current published process > process owner > recent operating evidence > historical deck.
- Business profile: official client/public source > approved internal reference.

## Lifecycle states

Use: `proposed`, `conditional`, `confirmed`, `approved`, `effective`, `superseded`, `cancelled`, `completed`, `historical`, `unresolved`.

Only `confirmed`, `approved`, or `effective` may be rendered as current without an uncertainty marker. `completed` is current only as a completed-state fact, not as active work.

Flag a conflict when:

- a lower-confidence update regresses a confirmed/effective state to proposed/unresolved;
- a new source has an older effective date but attempts to overwrite a later authoritative state;
- two authoritative sources disagree on ownership, reporting, dates, or status;
- a deletion is inferred only because an item disappeared from one source.
