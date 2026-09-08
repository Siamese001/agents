"""Antigravity command gate for the Apps RG runtime boundary.

The application guard remains authoritative. This hook ensures runtime commands
execute cleanly within the workspace environment and prevents invoking deprecated
external Codex Defender wrappers.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any


def _payload() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _command(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str):
        return tool_input["command"]
    if isinstance(payload.get("command"), str):
        return payload["command"]
    tool_info = payload.get("tool_info")
    if isinstance(tool_info, dict) and isinstance(tool_info.get("command_line"), str):
        return tool_info["command_line"]
    return ""


def _block(reason: str) -> int:
    print(json.dumps({"decision": "block", "reason": reason}), flush=True)
    return 2


def main() -> int:
    command = _command(_payload())
    if not command:
        return 0
    if re.search(r"(?i)(?:^|[\\/])codex-defender(?:\.cmd|\.ps1|\.exe)?\b", command):
        return _block(
            "codex-defender has been deprecated and retired. Run Python or pytest commands "
            "directly in the workspace using the local virtualenv (.venv) and "
            ".antigravity/runtime-boundary.json."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
