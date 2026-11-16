# Apps_research — App Customization Rules

> `apps_research` owns domain customization for Company Research Brief generation. All app-specific behavior lives here; `apps_rg` provides generic enforcement engines.

## App Ownership

`apps_research` **owns**:
- Ingress contract (`config/domain_contract/`)
- JSON schemas (`schemas/`)
- Field maps (`config/domain_contract/`)
- runtime_customization_package refs
- Route/retrieval/prompt profiles
- Cache policy profiles
- Runtime gate profiles
- Exit profiles
- Judge/eval/rubric profiles
- Threshold profiles
- Forbidden action/send policy
- Consent/compliance policy
- Write policy
- Learning/meta-feedback profiles
- Tests (`tests/unit/apps_research/`, `tests/_apps_contract/`)
- Migration receipts for core bindings

## Core Boundaries

`apps_research` **must NOT**:

1. **Implement separate Exit** — only `apps_rg` Exit emits X3
2. **Emit X3 directly** — use Exit profile (data), not Exit implementation
3. **Write L4 directly** — all durable writes go through Exit X3C → CommitRequest → UWG → L4
4. **Send directly or perform forbidden side effects** — must route through governed spine and clear Exit
5. **Add app-specific code to `apps_rg`** — use U0 package refs instead

## U0 Runtime Customization Package

`apps_research` behavior enters `apps_rg` **only** through:

```
apps_research/
  config/domain_contract/
    ingress_contract.yaml          → U0 validates
    schema/*.json                  → U0 validates
    field_map.yaml                 → U0 preserves
    runtime_customization_package/
      route_profile.yaml           → L0 consumes
      retrieval_profile.yaml       → C0 consumes
      prompt_profile.yaml          → PA consumes
      cache_policy.yaml            → Cache layer consumes
      exit_profile.yaml            → Exit consumes
      judge_rubric.yaml            → Eval consumes
      threshold_profile.yaml       → Exit gates consume
      meta_feedback_profile.yaml   → L6 consumes
```

### Package Structure

```yaml
# runtime_customization_package.yaml
package_version: "1.0"
package_digest: "sha256:..."

refs:
  ingress_contract: "apps_research/config/domain_contract/ingress_contract.yaml"
  schema: "apps_research/schemas/ingress_payload.json"
  field_map: "apps_research/config/domain_contract/field_map.yaml"
  
  route_profile: "apps_research/config/domain_contract/l0_route_profile.yaml"
  retrieval_profile: "apps_research/config/domain_contract/c0_retrieval_profile.yaml"
  prompt_profile: "apps_research/config/domain_contract/prompt_profile.yaml"
  cache_policy: "apps_research/config/domain_contract/cache_policy.yaml"
  
  exit_profile: "apps_research/config/domain_contract/exit_profile.yaml"
  judge_rubric: "apps_research/config/domain_contract/judge_rubric.yaml"
  threshold_profile: "apps_research/config/domain_contract/threshold_profile.yaml"
  
  meta_feedback_profile: "apps_research/config/domain_contract/meta_feedback_profile.yaml"
```

## Customization & Root-Cause Bug Resolution

Root-cause bug fixes and cohesive cross-spine refactors across `apps_research/` and its connected upstream/downstream contracts execute freely with zero file-count, file-size, line-count, or blast-radius caps (`INV-REFACTOR-EXTENT-UNBOUNDED`) while preserving directional inter-subsystem import boundaries and the Core Boundaries above:

- [ ] Profile defined in `config/domain_contract/` when adding new U0 customization surfaces
- [ ] Schema and field map aligned if ingress changes
- [ ] Impacted unit/contract tests (`tests/unit/apps_research/`, `tests/_apps_contract/`, `apps_research/tests/`) pass with `--timeout=60`
- [ ] Boundary audit (`tools/ssot_boundary_auditor.py`) passes

## Related

- Root `AGENTS.md` — Architecture law
- `resume_graph_engine/src/apps_rg/AGENTS.md` — Core boundary rules
- `.agents/rules/apps-customization.md` — App customization guidance
- `tools/ssot_boundary_auditor.py` — Boundary audit runner
