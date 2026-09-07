"""Codex-only command gate for the Apps RG runtime boundary.

The application guard remains authoritative.  This hook prevents an agent from
accidentally bypassing the global Defender while using Codex shell tools.  It
does not run tests, create environments, or alter Git/worktree commands.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

_RUNTIME_COMMAND = re.compile(
    r"(?i)(?:^|[;&|]\s*)(?:py(?:thon)?(?:\.exe)?|pytest(?:\.exe)?|pip(?:\.exe)?|uv(?:\.exe)?|poetry|tox|nox)\b"
)


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
    if not command or not _RUNTIME_COMMAND.search(command):
        return 0
    if re.search(r"(?i)(?:^|[\\/])codex-defender(?:\.cmd|\.ps1|\.exe)?\b", command):
        return 0
    return _block(
        "Apps RG runtime commands must use the global Defender so paths, venv identity, "
        "timeout, and descendant processes are contained. Use: "
        "C:\\Users\\amita\\.codex\\defender\\bin\\codex-defender.cmd run "
        "--policy .codex\\runtime-boundary.json --command python -m apps_rg ..."
    )


if __name__ == "__main__":
    raise SystemExit(main())
