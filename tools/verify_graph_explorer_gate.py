#!/usr/bin/env python3
"""Agents Graph Explorer quality, WCAG contrast, and cross-repo firewall gate adapter."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.interactive_graph_export_core.dataset_builder import (
    build_agents_explorer_dataset,
    render_explorer_html,
    render_portal_shell_html,
    resolve_default_graph_db_path,
    resolve_primary_repo_root,
)

_PLUGIN_FILE = (
    Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp" / "graph_explorer_quality_gate.py"
)


def load_graph_gate_backend(*, force_standalone: bool | None = None) -> ModuleType:
    """Resolve core-governance graph_explorer_quality_gate unless standalone fallback is active."""
    use_standalone = (
        force_standalone
        if force_standalone is not None
        else (os.environ.get("CORE_GOVERNANCE_FORCE_STANDALONE") == "1")
    )
    if not use_standalone and _PLUGIN_FILE.is_file():
        mod_name = "_core_governance_graph_explorer_quality_gate"
        spec = importlib.util.spec_from_file_location(mod_name, _PLUGIN_FILE)
        if spec is not None and spec.loader is not None:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            return mod
    from tools import _standalone_graph_quality_gate

    return _standalone_graph_quality_gate


def run_agents_graph_quality_gate(
    html_text: str,
    *,
    portal_html_text: str = "",
    extra_payload_texts: Sequence[str] = (),
    run_vm: bool = True,
    force_standalone: bool | None = None,
) -> dict[str, Any]:
    """Run centralized port_8081 behavioral, contrast, and cross-repo firewall verification."""
    backend = load_graph_gate_backend(force_standalone=force_standalone)
    res: dict[str, Any] = backend.run_graph_explorer_quality_gate(
        html_text,
        profile="port_8081",
        portal_html_text=portal_html_text,
        extra_payload_texts=extra_payload_texts,
        run_vm=run_vm,
    )
    res["backend_source"] = getattr(backend, "__file__", "unknown")
    return res


def verify_agents_explorer_artifacts(
    html_path: Path | None = None,
    *,
    force_standalone: bool | None = None,
) -> dict[str, Any]:
    """Validate standalone HTML, live portal shell HTML, and bootstrap dataset JSON."""
    data = build_agents_explorer_dataset(resolve_default_graph_db_path(ROOT))
    default_html = resolve_primary_repo_root(ROOT) / "artifacts" / "explorer" / "interactive_knowledge_graph.html"
    target_html = Path(html_path).resolve() if html_path is not None else default_html
    html_text = (
        target_html.read_text(encoding="utf-8")
        if target_html.is_file()
        else render_explorer_html(data, default_mode="graph")
    )
    portal_html = render_portal_shell_html(data, default_mode="graph")
    bootstrap_json = json.dumps(data, ensure_ascii=False)
    return run_agents_graph_quality_gate(
        html_text,
        portal_html_text=portal_html,
        extra_payload_texts=(bootstrap_json,),
        run_vm=True,
        force_standalone=force_standalone,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Agents port 8081 Graph Explorer quality and firewall gate.")
    parser.add_argument("--html", type=Path, default=None, help="Optional explicit explorer HTML bundle path.")
    parser.add_argument("--standalone", action="store_true", help="Force standalone CI fallback module.")
    args = parser.parse_args(argv)
    result = verify_agents_explorer_artifacts(
        args.html,
        force_standalone=True if args.standalone else None,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
