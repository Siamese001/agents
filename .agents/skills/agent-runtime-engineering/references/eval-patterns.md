# Eval patterns

Use deterministic checks for schemas, permissions, exact outputs, tool selection constraints, and invariant violations.

Use reference-based scoring when a known-good answer or artifact exists.

Use rubric-based model judging for nuanced quality only with a clear rubric, judge/version tracking, calibration, and periodic human review.

Use pairwise comparison for relative quality when absolute scores are unstable.

Use trajectory evaluation when the path matters: unnecessary tools, bad delegation, policy violations, loops, or missed recovery.

Use production outcome metrics when the business consequence is measurable. Do not substitute proxy scores for business outcomes without stating the limitation.
