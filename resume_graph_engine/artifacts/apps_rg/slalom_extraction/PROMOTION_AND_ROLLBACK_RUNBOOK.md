# Promotion and Rollback Runbook: Slalom Agentic Graph Augmentation

## 1. Executive Summary & Governance Preconditions

This runbook outlines the operational procedure for promoting the staged Slalom agentic capability delta (`slalom_graph_delta_proposal.json`) to the live production database (`augmented_skills_graph.sqlite`) and fact ledger (`master_candidate_skills_fact_ledger_*.json`).

> [!CAUTION]
> **GOVERNANCE PROHIBITION:**
> Under the current plan (`plans/resume-slalom-agentic-outcomes-a7b3e1.md`), live graph promotion is **strictly firewalled**. No promotion actions may be performed without:
> 1. An explicitly approved follow-on promotion plan (`plans/resume-slalom-promotion-<hex>.md`).
> 2. Operator review and approval of `slalom_augmentation_diff.md` and `anonymization_scan_report.json`.
> 3. Verified test execution of the E2E and adversarial test suites.

---

## 2. Pre-Promotion Verification Checklist

Before applying any changes to the production graph, execute the following pre-flight checks:

1. **Verify Bundle Integrity**:
   Validate that all artifacts match their cryptographic SHA-256 hashes recorded in `bundle_manifest.json`:
   ```bash
   python3 -c "
   import hashlib, json
   from pathlib import Path
   staging = Path('resume_graph_engine/artifacts/apps_rg/slalom_extraction')
   manifest = json.loads((staging / 'bundle_manifest.json').read_text())
   for art in manifest['artifacts']:
       p = staging / art['filename']
       actual = hashlib.sha256(p.read_bytes()).hexdigest()
       assert actual == art['sha256'], f'Hash mismatch on {art[\"filename\"]}'
   print('ALL ARTIFACTS VERIFIED OK')
   "
   ```

2. **Execute Staged Safety Suites**:
   ```bash
   .venv/bin/python -m pytest \
     .worktrees/slalom-agentic-outcomes/resume_graph_engine/tests/unit/test_slalom_augmentation_e2e.py \
     .worktrees/slalom-agentic-outcomes/resume_graph_engine/tests/unit/test_slalom_augmentation_adversarial.py \
     -v --timeout=60
   ```

3. **Backup Live Production Database**:
   Create a timestamped backup before touching the production database:
   ```bash
   LIVE_DB="resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
   BACKUP_DB="resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite.backup_$(date +%Y%m%d_%H%M%S)"
   cp -p "$LIVE_DB" "$BACKUP_DB"
   shasum -a 256 "$BACKUP_DB" > "${BACKUP_DB}.sha256"
   ```

---

## 3. Promotion Execution Procedure

1. **Transaction-Wrapped Database Application**:
   Execute the migration script in a single atomic SQLite transaction:
   ```python
   import json
   import sqlite3
   from pathlib import Path

   DB_PATH = Path("resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite")
   PROPOSAL_PATH = Path("resume_graph_engine/artifacts/apps_rg/slalom_extraction/slalom_graph_delta_proposal.json")

   proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
   conn = sqlite3.connect(DB_PATH)
   cur = conn.cursor()

   try:
       cur.execute("BEGIN TRANSACTION;")
       
       # Enrich existing facts
       for n in proposal["nodes"]:
           if n["staged_status"] == "ENRICH_EXISTING":
               cur.execute(
                   """
                   UPDATE graph_nodes 
                   SET label = ?, description = ?, activation_status = ?, support_level = ?, confidence = ?, source_authority = ?, updated_at = datetime('now')
                   WHERE node_id = ?
                   """,
                   (n["label"], n["description"], n["activation_status"], n["support_level"], n["confidence"], n["source_authority"], n["node_id"]),
               )
           else:
               cur.execute(
                   """
                   INSERT INTO graph_nodes (node_id, node_type, label, description, activation_status, support_level, confidence, external_eligible, career_epoch, phase_ordinal, source_authority, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                   """,
                   (n["node_id"], n["node_type"], n["label"], n["description"], n["activation_status"], n["support_level"], n["confidence"], n["external_eligible"], n["career_epoch"], n["phase_ordinal"], n["source_authority"]),
               )

       # Insert staged edges
       for e in proposal["edges"]:
           cur.execute(
               """
               INSERT INTO graph_edges (edge_id, source_node_id, target_node_id, edge_family, edge_type, weight, confidence, directional, evidence_status, source_authority, business_story, technical_story)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               """,
               (e["edge_id"], e["source_node_id"], e["target_node_id"], e["edge_family"], e["edge_type"], e["weight"], e["confidence"], e["directional"], e["evidence_status"], e["source_authority"], e["business_story"], e["technical_story"]),
           )

       cur.execute("PRAGMA integrity_check;")
       assert cur.fetchall() == [("ok",)], "Integrity check failed"

       cur.execute("PRAGMA foreign_key_check;")
       assert len(cur.fetchall()) == 0, "Foreign key check failed"

       conn.commit()
       print("PROMOTION COMMITTED SUCCESSFULLY")
   except Exception as err:
       conn.rollback()
       print(f"PROMOTION ABORTED AND ROLLED BACK: {err}")
       raise
   finally:
       conn.close()
   ```

2. **Fact Ledger Synchronization**:
   Append new facts `fact_slalom_005` and `fact_slalom_006` into `master_candidate_skills_fact_ledger_*.json` under an approved schema-validated transformation.

3. **Re-Run Full Résumé Engine Validation Suite**:
   ```bash
   .venv/bin/python -m pytest resume_graph_engine/tests/ -v --timeout=180
   ```

---

## 4. Rollback Procedure

If any anomaly, query degradation, or contract violation occurs post-promotion:

1. **Restore SQLite from Pre-Flight Backup**:
   ```bash
   cp -p "$BACKUP_DB" "$LIVE_DB"
   shasum -a 256 "$LIVE_DB" # Verify hash matches pre-promotion baseline
   ```

2. **Revert Fact Ledger**:
   ```bash
   git checkout -- resume_graph_engine/artifacts/apps_rg/fact_inventory/master_candidate_skills_fact_ledger_*.json
   ```

3. **Verify Restoration**:
   Run database integrity check and verify query consistency:
   ```bash
   python3 -c "
   import sqlite3
   conn = sqlite3.connect('$LIVE_DB')
   assert conn.execute('PRAGMA integrity_check;').fetchall() == [('ok',)]
   print('ROLLBACK COMPLETE - INTEGRITY VERIFIED')
   "
   ```
