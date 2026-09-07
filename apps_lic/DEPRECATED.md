# DEPRECATION NOTICE: `apps_lic`

> [!WARNING]
> **`apps_lic` is formally DEPRECATED as of September 2026.**
> 
> The active, modern production subsystem has moved to [`apps_lic_v2/`](../apps_lic_v2/).

### Why was `apps_lic` superseded?
1. **Zero Core Coupling**: Legacy `apps_lic` relied on 256 references across obsolete `agentic_core` layers (L0-L6, Redis coordination fabric, UWG storage writers, and complex mixins). `apps_lic_v2` is 100% self-contained with zero external framework dependencies.
2. **Simplified, Hardened Pipeline**: The 14-hop sequential pipeline has been streamlined into a direct, bounded 4-stage execution architecture (Context Assembly -> Draft Generation -> Multi-Gate Validation -> Cadence Planning).
3. **Automated Rubric Judges**: `apps_lic_v2` features local rubric evaluators implementing Classification, Grounding, Alignment, and Narrative quality gates.

### Migration Guide
- For CLI usage, run:
  ```bash
  python -m apps_lic_v2
  ```
- For Python imports, replace:
  ```python
  from apps_lic...
  ```
  with:
  ```python
  from apps_lic_v2...
  ```
