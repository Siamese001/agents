#!/usr/bin/env python3
"""Lints commit message against conventional commit format via core-governance with standalone fallback."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_PLUGIN_FILE = Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp" / "security_purity_linters.py"
_CACHED_PLUGIN_MOD: ModuleType | None = None


def _load_backend() -> ModuleType:
    """Resolve core-governance security_purity_linters unless standalone mode is forced or plugin is absent."""
    global _CACHED_PLUGIN_MOD
    if os.environ.get("CORE_GOVERNANCE_FORCE_STANDALONE") != "1" and _PLUGIN_FILE.is_file():
        if _CACHED_PLUGIN_MOD is None:
            mod_name = "_core_governance_security_purity_linters"
            spec = importlib.util.spec_from_file_location(mod_name, _PLUGIN_FILE)
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                _CACHED_PLUGIN_MOD = mod
        if _CACHED_PLUGIN_MOD is not None:
            return _CACHED_PLUGIN_MOD
    from tools import _standalone_security_purity

    return _standalone_security_purity


def lint_commit_msg(msg: str) -> bool:
    ok, _reason = _load_backend().validate_commit_message(msg, check_model_neutral=False)
    return bool(ok)


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint commit message.")
    parser.add_argument("-f", "--file", required=True, help="Path to commit message file")
    args = parser.parse_args()

    msg_file = Path(args.file)
    if not msg_file.is_file():
        print(f"Error: Commit message file '{args.file}' not found.", file=sys.stderr)
        return 1

    content = msg_file.read_text(encoding="utf-8", errors="replace")
    ok, reason = _load_backend().validate_commit_message(content, check_model_neutral=False)
    if not ok:
        first_line = content.strip().splitlines()[0] if content.strip() else ""
        print(f"COMMIT MESSAGE REJECTED: '{first_line}' ({reason})", file=sys.stderr)
        print(
            "   Allowed formats: feat(...): ..., fix(...): ..., chore(...): ..., docs(...): ..., refactor(...): ..., test(...): ..., ci(...): ...",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
