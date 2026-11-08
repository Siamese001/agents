#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Usage: validate_mcp_design.py mcp-design.json")
        return 2
    try:
        d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e:
        print("ERROR: invalid JSON: " + str(e)); return 1
    errors=[]
    for k in ["protocol","target_version","environment","host","server","transport","capabilities","security","resilience","observability","compatibility"]:
        if k not in d: errors.append("missing required field: "+k)
    if d.get("protocol") != "mcp": errors.append("protocol must be 'mcp'")
    caps=d.get("capabilities",{}) if isinstance(d.get("capabilities"),dict) else {}
    if not any(caps.get(k) for k in ["tools","resources","prompts","extensions"]): errors.append("declare at least one MCP capability")
    sec=d.get("security",{}) if isinstance(d.get("security"),dict) else {}
    srv=d.get("server",{}) if isinstance(d.get("server"),dict) else {}
    if d.get("environment")=="production" and srv.get("remote") and not sec.get("authorization"):
        errors.append("remote production server requires explicit authorization design")
    if errors:
        for e in errors: print("ERROR: "+e)
        return 1
    print("PASS: MCP design contract is structurally valid")
    return 0
if __name__ == "__main__": raise SystemExit(main())
