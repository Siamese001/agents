# Agents Repository — Storage & Worktree Hygiene Automation Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage I (Order 1/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Storage, Worktree, and SQLite Hygiene Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`05:30 ET`, Order `1/7`). This agent prepares a clean foundation before Stages II–IV run by auditing and remediating orphaned git worktrees, merged local feature branches, SQLite/WAL health (`artifacts/adg/*.sqlite`, `artifacts/governance/hitl_decisions.sqlite`, `.codex/state/refactor_decisions/refactor_decision_ledger.sqlite`), and runaway artifact directories.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Git worktree pruning, merged local branch cleanup, SQLite `PRAGMA integrity_check` / `PRAGMA wal_checkpoint(TRUNCATE)`, and `artifacts/sidecar_runs/` retention hygiene.
- **Delegated to peer agents**: Subsystem boundary & SSOT drift (`agents-ssot-boundary-governance`), E2E pipeline execution (`agents-outreach-resume-functionality`), retrieval quality (`agents-research-retrieval-surface`), judge validity (`agents-evals-judge-assurance`), token budgets (`agents-cost-token-budget`), and test coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Strictly bound to `/Users/amitayer/Git/agents`. Zero access to external repositories or external sidecar directories.
- **Unconditional Wave-Based Plan Mandate (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - In **BOTH** `MODE: scheduled` and `MODE: interactive`, this agent MUST author a wave-based remediation plan at `plans/<branch-slug>-<6hex>.md` (and copy it to `<run_dir>/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `python3 tools/validate_implementation_plan.py --file plans/<branch-slug>-<6hex>.md` (`exit code 0`).
  - In `MODE: scheduled`, after validating the wave plan and copying durable artifacts to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_storage_worktree_hygiene/<run_id>/`, prune the ephemeral worktree (`INV-WT-EPHEMERAL-SCHEDULED`) and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED` without mutating repository code.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

Before executing any inspection or writing any file, provision an isolated worktree off local `main`:

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-storage-hygiene-${RUN_TS}"
export BRANCH_NAME="automation/${BRANCH_SLUG}"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${BRANCH_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_storage_worktree_hygiene/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
python3 "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 6-Pillar Read-Only Audit & Executable Forensic Scanners

### Phase 1: 6-Pillar Hygiene Audit
1. **Pillar 1 — Worktree & Branch Drift**: Detect stale worktrees in `git worktree list --porcelain` and local branches already merged into `main` (`git branch --merged main`).
2. **Pillar 2 — SQLite Integrity & Journal Mode**: Verify `PRAGMA integrity_check` and `PRAGMA journal_mode=WAL` across `artifacts/adg/*.sqlite`, `artifacts/governance/hitl_decisions.sqlite`, and `.codex/state/refactor_decisions/refactor_decision_ledger.sqlite`.
3. **Pillar 3 — WAL / SHM Bloat Detection**: Flag `-wal` or `-shm` sidecar files exceeding `32 MB` that require `PRAGMA wal_checkpoint(TRUNCATE)`.
4. **Pillar 4 — Ephemeral Artifact Sprawl**: Measure disk footprint across `artifacts/sidecar_runs/`, `artifacts/mcp/playwright/`, and `.pytest_cache/` (> `500 MB` threshold).
5. **Pillar 5 — Stale Lock & Temp File Sweep**: Identify orphaned `.lock`, `.tmp`, or unreferenced scratch files older than 24 hours.
6. **Pillar 6 — Cross-Repository Isolation Verification**: Run `python3 tools/validate_sidecar_separation.py --json` to confirm zero namespace, cron, or path drift.

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the bounded 6-pillar scanner CLI `python3 tools/storage_worktree_hygiene.py --json` (or the inline script below) in `${WORKTREE_DIR}` (`timeout <= 60s`):

```bash
python3 - <<'PY'
import json, sqlite3, subprocess
from pathlib import Path

root = Path("/Users/amitayer/Git/agents")
wt_out = subprocess.run(["git", "-C", str(root), "worktree", "list", "--porcelain"], capture_output=True, text=True, timeout=30).stdout
merged_out = subprocess.run(["git", "-C", str(root), "branch", "--merged", "main"], capture_output=True, text=True, timeout=30).stdout

sqlite_dbs = list(root.glob("artifacts/**/*.sqlite")) + list(root.glob(".codex/**/*.sqlite"))
db_report = []
for db in sqlite_dbs:
    wal = Path(str(db) + "-wal")
    wal_mb = round(wal.stat().st_size / (1024 * 1024), 3) if wal.exists() else 0.0
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
        integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        jmode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        conn.close()
    except Exception as exc:
        integrity, jmode = f"ERROR: {exc}", "unknown"
    db_report.append({"db": str(db.relative_to(root)), "integrity": integrity, "journal_mode": jmode, "wal_mb": wal_mb})

print(json.dumps({"db_count": len(db_report), "dbs": db_report, "merged_branches": [b.strip() for b in merged_out.splitlines() if b.strip() and not b.strip().startswith("*") and b.strip() != "main"]}, indent=2))
PY
```

Write the structured findings to `${RUN_DIR}/audit_report.json`.

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/storage-hygiene-${HEX6}.md` (500–800 words, max 1,000 words) structured as sequential waves:
- `## Wave 1: Worktree, Merged Branch & Lock Hygiene`
- `## Wave 2: SQLite WAL Checkpoint & Artifact Retention`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`), followed by `## Wave Implementation & Completion Status Table`.
Validate immediately:
```bash
python3 tools/validate_implementation_plan.py --file "plans/storage-hygiene-${HEX6}.md"
cp "plans/storage-hygiene-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) covering all 6 pillars.
Compute multi-factor calibrated confidence using `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_storage_worktree_hygiene/${RUN_TS}`, prune `${WORKTREE_DIR}` and `${BRANCH_NAME}`, and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED`.
- In `MODE: interactive`: If $\Delta \le 0.20$, invoke `ask_question` with one atomic decision (`Candidate ID`, calibrated confidence scores, `(Recommended)` option). If $\Delta > 0.20$, record the autonomous decision receipt in `HITLDecisionStore` and proceed to Phase 3.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`) in `MODE: interactive`:
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` metrics (worktree count, merged branch count, WAL byte size).
   - Execute bounded remediation commands (`git worktree prune`, `PRAGMA wal_checkpoint(TRUNCATE)`).
   - Run `POST_MUTATION_RUN` verification and scoped pytest:
     `/Users/amitayer/Git/agents/.venv/bin/pytest tests/unit/test_sidecar_separation_governance.py -v --timeout=60`
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore` (`artifacts/governance/hitl_decisions.sqlite`).
3. **Turn & Commit Gates (`C09`, `C10`)**:
   ```bash
   python3 tools/validate_sidecar_separation.py --json
   python3 tools/validate_turn_gates.py --mode all
   python3 tools/verify_commit.py
   ```
   Commit on `${BRANCH_NAME}`, rebase onto `main`, merge `--no-ff` into `/Users/amitayer/Git/agents` (`main`), and remove `${WORKTREE_DIR}` and `${BRANCH_NAME}`.
