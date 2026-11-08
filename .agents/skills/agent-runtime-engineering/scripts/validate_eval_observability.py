#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv)!=2: print("Usage: validate_eval_observability.py eval-observability.json"); return 2
    try: d=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e: print("ERROR: invalid JSON: "+str(e)); return 1
    errors=[]
    for k in ["system","critical_journeys","correlation","events","metrics","offline_evals","online_slos","release_gates","alerts","privacy","human_calibration"]:
        if k not in d: errors.append("missing required field: "+k)
    corr=d.get("correlation",{}) if isinstance(d.get("correlation"),dict) else {}
    if not corr.get("root_id") or not corr.get("propagation"): errors.append("end-to-end correlation model is required")
    if not d.get("metrics"): errors.append("at least one metric is required")
    if errors:
        for e in errors: print("ERROR: "+e)
        return 1
    print("PASS: evaluation/observability contract is structurally valid"); return 0
if __name__=="__main__": raise SystemExit(main())
