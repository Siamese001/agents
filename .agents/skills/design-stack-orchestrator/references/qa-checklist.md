# Cross-format QA checklist

## 1. Intent and audience

- Artifact answers the user's actual decision, onboarding, explanation, or collaboration need.
- Medium fits the use case; no unnecessary canvas/tool complexity.
- Primary path is understandable without a live facilitator when self-service is intended.

## 2. Factual trust

- Current assertions have source, owner, and verification date when applicable.
- Proposed/conditional/unresolved content is visibly labeled.
- Conflicts are surfaced as HITL rather than silently resolved.
- Links point to governed or authoritative sources where volatile detail changes frequently.

## 3. Security and privacy

- No secrets or credentials.
- No unnecessary personal data.
- No sensitive asset identifiers or internal commercial terms unless explicitly authorized.
- No signed URLs or query strings that expose credentials.

## 4. Accessibility

- Normal text contrast target: 4.5:1 or greater.
- Large text contrast target: 3:1 or greater.
- Status is conveyed with text/icon/shape, not color alone.
- Images have alt text where the medium supports it.
- Navigation order is coherent.

## 5. Visual quality

- Strong hierarchy and whitespace.
- Consistent component dimensions and spacing.
- No overlap, clipping, accidental off-canvas placement, or unreadably small text.
- Decorative imagery does not reduce legibility.
- Executive frames are presentation-ready when applicable.

## 6. Maintainability

- Stable IDs exist for structured dynamic objects.
- Editable source is retained.
- Owner and refresh cadence exist for volatile content.
- Deployment-owned items can be distinguished from unrelated content.
- Rollback or archive strategy exists for direct-write deployments.

## 7. Integrity

- Every promised artifact exists.
- Every linked local output path is valid before handoff.
- Direct-write claims are backed by API/plugin confirmation.
- Visual verification claims are backed by an actual render or live view.
