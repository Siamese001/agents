#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

CURRENT_STATES = {"confirmed", "approved", "effective"}
WEAK_STATES = {"proposed", "conditional", "unresolved"}


def load_records(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        records = data
    else:
        records = data.get("records", data.get("items", []))
    out = {}
    for record in records:
        rid = record.get("id")
        if not rid:
            raise ValueError("Every record requires a stable id")
        if rid in out:
            raise ValueError(f"Duplicate id: {rid}")
        out[rid] = record
    return out


def diff(old, new):
    result = {"add": [], "update": [], "retire_candidate": [], "conflicts": []}
    for rid, rec in new.items():
        if rid not in old:
            result["add"].append(rec)
            continue
        prev = old[rid]
        if prev == rec:
            continue
        old_state = str(prev.get("status", "")).lower()
        new_state = str(rec.get("status", "")).lower()
        if old_state in CURRENT_STATES and new_state in WEAK_STATES:
            result["conflicts"].append({
                "id": rid,
                "reason": "state_regression_requires_review",
                "old": prev,
                "new": rec,
            })
            continue
        old_eff = prev.get("effective_date") or ""
        new_eff = rec.get("effective_date") or ""
        if old_eff and new_eff and new_eff < old_eff:
            result["conflicts"].append({
                "id": rid,
                "reason": "older_effective_date_requires_review",
                "old": prev,
                "new": rec,
            })
            continue
        changed = sorted(k for k in set(prev) | set(rec) if prev.get(k) != rec.get(k))
        result["update"].append({"id": rid, "changed_fields": changed, "old": prev, "new": rec})
    for rid, rec in old.items():
        if rid not in new:
            result["retire_candidate"].append({
                "id": rid,
                "record": rec,
                "reason": "missing_from_new_snapshot_not_proof_of_deletion",
            })
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--output")
    args = ap.parse_args()
    result = diff(load_records(args.old), load_records(args.new))
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        print(text)

if __name__ == "__main__":
    main()
