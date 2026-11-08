---
name: figma-visual-studio
description: Author, audit, and quality-gate 3840x2160 Figma-native executive presentations and diagrams. Covers canvas layout and reviewer release gates.
---

# Figma Visual Studio Skill

Unified authoring, structuring, and release governance for consulting-grade 3840×2160 executive slides and technical diagrams in Figma. Upholds the strict separation of **Builder** and **Reviewer** roles within a single cohesive studio workflow.

## When to use

- Authoring or modifying 3840×2160 Figma frames, consulting slides, and system architectures
- Extracting layer properties and generating scene manifests
- Running visual quality audits and inspecting typography floors
- Authorizing machine release via `runtime.govern`

---

## Role 1: Builder Workflow (Authoring & Layout)

1. **Lock Source Truth & Slide Class**:
   - Extract facts, figures, and dates; select class (`EXECUTIVE`, `TECHNICAL_ARCHITECTURE`, `VOICE_OF_CUSTOMER`).
2. **Select Governed Archetype**:
   - Select one canonical slide archetype per [Executive Archetypes](./references/archetypes.md) §Reference Archetypes & Repair Order.
3. **Establish 4K Frame & Layout Zones**:
   - Canvas: Exact 3840×2160 frame (`aspect_ratio: "16:9"`).
   - Safe margins: Left/Right 64–96 px, Top 48–64 px.
   - Title Row: Exclusive band ($y \in [48, 310]$ px), width $\ge 3648$ px. No badges or logos sharing this row.
4. **Apply Inter Typography System**:
   - **Font**: Inter only. Fallback strictly forbidden.
   - **Title**: 92–104 px (88 px floor), Bold/ExtraBold, $\le 2$ lines.
   - **Dominant Heading**: 46–56 px SemiBold/Bold.
   - **Essential Body**: $\ge 42$ px Regular/Medium.
   - **Secondary Body**: $\ge 38$ px Regular/Medium.
5. **Construct Dominant Exhibit**:
   - Dominant exhibit must occupy $\ge 45\%$ of usable canvas. Structure: `CONCLUSION → EVIDENCE → IMPLICATION`.
6. **Export Candidate & Properties**:
   - Export 3840×2160 PNG at 1× scale.
   - Extract layer tree into `figma_evidence.json` via helper:
     ```bash
     python .agents/skills/figma-visual-studio/scripts/export_scene_manifest.py
     ```

---

## Role 2: Reviewer Workflow (Governance & Machine Release)

1. **Verify Candidate & Non-Self-Attestation**:
   - Candidate must be 3840×2160 PNG with luminance variance $\ge 8.0$.
   - `builder.run_id` must be distinct from `producer.run_id`. Zero self-attestation blocks.
2. **Validate Layer Properties**:
   - Inter only, title width $\ge 3648$ px, typography floors respected. Zero shrink-to-fit or clipping.
3. **100% Source Truth Mapping**:
   - Every substantive claim in `source_manifest.json` mapped to verified evidence.
4. **Rendered, Storyline & Cognitive QA (18 Blockers + President-View Gates P1-P5)**:
   - 16 rendered QA tests pass. All 18 [Cognitive & Storyline Blockers](./references/cognitive-blockers.md) must be `false`.
   - Dominant exhibit ratio $\ge 0.45$, visual regions $\le 5$, direct quotes $\le 1$.
   - For multi-slide executive decks and PDFs, run `python .agents/skills/figma-visual-studio/scripts/run_release_gate.py --diagnostic` and certify via an isolated blind multimodal subagent (`TypeName: "research"`, `Model: "pro"`) enforcing Hard-Veto Gates `P1-P5` (`>= 9.0 / 10` overall, `>= 8.5 / 10` per gate): (P1) Answer-First Slide 1 with ranked recommendations and executive decisions, (P2) zero cryptic `#NN` charter IDs, insider slang, or rubric meta-text, (P3) upfront `$/hr` sticker-rate candor + incumbent revenue ring-fence (`$0` cannibalization) + bench payback math, (P4) descending largest-to-smallest competitor ordering, and (P5) zero bounding-box overlaps or out-of-bounds strings.
5. **Authorize Machine Release**:
   - Execute release command:
     ```bash
     python .agents/skills/figma-visual-studio/scripts/run_release_gate.py --receipt <path_to_RELEASE.json>
     ```
   - Only terminal status `DELIVERY_READY` authorizes distribution.

---

## Resources

- [Cognitive Blockers](./references/cognitive-blockers.md): The 18 cognitive, storyline, and commercial failure patterns.
- [Regression Dimensions](./references/regression-dimensions.md): The 26 comparison dimensions.
- [Executive Archetypes](./references/archetypes.md): The 6 consulting archetypes.
- [Executive Prompt Contract](./references/prompt-template.md): Zero-loss slide prompt contract.
- [Figma Evidence Extraction](./references/figma-evidence.md): Layer extraction schema.
