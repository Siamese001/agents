#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ALLOWED={"task-state","conversation","working","user-memory","episodic","knowledge","evidence","guidance"}
def main():
    if len(sys.argv)!=2: print("Usage: validate_state_memory.py state-memory-design.json"); return 2
    try: d=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e: print("ERROR: invalid JSON: "+str(e)); return 1
    errors=[]
    for k in ["system","stores","write_policies","read_policies","provenance","isolation","retention","concurrency"]:
        if k not in d: errors.append("missing required field: "+k)
    ids=set()
    for s in d.get("stores",[]) if isinstance(d.get("stores"),list) else []:
        if not s.get("id"): errors.append("store missing id")
        else: ids.add(s["id"])
        if s.get("role") not in ALLOWED: errors.append("store has invalid semantic role")
        if not s.get("owner"): errors.append("store missing owner")
    if errors:
        for e in errors: print("ERROR: "+e)
        return 1
    print("PASS: state/memory contract is structurally valid"); return 0
if __name__=="__main__": raise SystemExit(main())
