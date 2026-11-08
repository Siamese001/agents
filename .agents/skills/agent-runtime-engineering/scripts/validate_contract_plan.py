#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv)!=2: print("Usage: validate_contract_plan.py contract-test-plan.json"); return 2
    try: d=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e: print("ERROR: invalid JSON: "+str(e)); return 1
    errors=[]
    for k in ["system","boundaries","versions","scenarios","fault_injection","mocks","compatibility_matrix","release_blockers","evidence"]:
        if k not in d: errors.append("missing required field: "+k)
    bids={b.get("id") for b in d.get("boundaries",[]) if isinstance(b,dict)}
    for s in d.get("scenarios",[]) if isinstance(d.get("scenarios"),list) else []:
        if s.get("boundary") not in bids: errors.append("scenario references unknown boundary")
        for k in ["id","class","action","expected"]:
            if not s.get(k): errors.append("scenario missing "+k)
    if not d.get("scenarios"): errors.append("at least one scenario is required")
    if errors:
        for e in errors: print("ERROR: "+e)
        return 1
    print("PASS: contract test plan is structurally valid"); return 0
if __name__=="__main__": raise SystemExit(main())
