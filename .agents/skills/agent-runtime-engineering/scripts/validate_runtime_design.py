#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv)!=2: print("Usage: validate_runtime_design.py runtime-design.json"); return 2
    try: d=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e: print("ERROR: invalid JSON: "+str(e)); return 1
    errors=[]
    for k in ["agent_id","goal","pattern","authority","state","loop","termination","budgets","resilience","human_control","observability"]:
        if k not in d: errors.append("missing required field: "+k)
    term=d.get("termination",{}) if isinstance(d.get("termination"),dict) else {}
    if not term.get("success") or not term.get("failure"): errors.append("termination must define success and failure")
    if not isinstance(term.get("max_steps"), int) or term.get("max_steps",0)<=0: errors.append("termination.max_steps must be a positive integer")
    budgets=d.get("budgets",{}) if isinstance(d.get("budgets"),dict) else {}
    if budgets.get("delegation_depth") is None: errors.append("budgets.delegation_depth is required")
    if errors:
        for e in errors: print("ERROR: "+e)
        return 1
    print("PASS: runtime design contract is structurally valid"); return 0
if __name__=="__main__": raise SystemExit(main())
