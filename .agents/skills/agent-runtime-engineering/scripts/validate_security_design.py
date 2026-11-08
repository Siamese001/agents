#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv)!=2: print("Usage: validate_security_design.py security-governance.json"); return 2
    try: d=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e: print("ERROR: invalid JSON: "+str(e)); return 1
    errors=[]
    for k in ["system","environment","assets","actors","identity","authorization","trust_boundaries","controls","approvals","data_policy","secrets","threats","incident_response","residual_risks"]:
        if k not in d: errors.append("missing required field: "+k)
    if d.get("environment")=="production" and not d.get("controls"): errors.append("production design requires explicit controls")
    for c in d.get("controls",[]) if isinstance(d.get("controls"),list) else []:
        for k in ["id","objective","enforcement_point","owner","evidence","test"]:
            if not c.get(k): errors.append("control missing "+k)
    if errors:
        for e in errors: print("ERROR: "+e)
        return 1
    print("PASS: security governance contract is structurally valid"); return 0
if __name__=="__main__": raise SystemExit(main())
