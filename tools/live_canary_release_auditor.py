#!/usr/bin/env python3
"""Live Keyless Canary, MCP Stdio Server, Graph Portal & Sequential Release-Gate Auditor (Agent 7/7).

Isolates high-latency keyless IDE CLI (`agy`) canary checks, MCP stdio server verification,
Interactive Graph Explorer Portal verification, and sequential `verify_release_gate.py --no-write`
execution so Agents 1/7 through 6/7 remain sub-60s hermetic preflights.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(DEFAULT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_REPO_ROOT))


def _probe_vector_db_mcp_stdio(repo_root: Path) -> dict[str, Any]:
    gaps: list[str] = []
    srv = repo_root / "tools" / "mcp" / "vector_db_server.py"
    if not srv.is_file():
        return {"passed": False, "gaps": ["Missing tools/mcp/vector_db_server.py"]}

    requests_ndjson = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "vector_stats"}})
        + "\n"
    )
    proc = subprocess.run(
        [sys.executable, str(srv)],
        input=requests_ndjson,
        capture_output=True,
        text=True,
        shell=False,
        timeout=30,
        cwd=str(repo_root),
    )
    if proc.returncode != 0:
        gaps.append(f"vector_db_server.py exited {proc.returncode}: {proc.stderr.strip()[:200]}")
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if len(lines) != 3:
        gaps.append(f"vector_db_server.py returned {len(lines)} JSON-RPC responses (expected 3)")
    else:
        try:
            r1, r2, r3 = (json.loads(ln) for ln in lines)
            if (r1.get("result") or {}).get("serverInfo", {}).get("name") != "vector_db":
                gaps.append("vector_db_server initialize missing serverInfo.name == 'vector_db'")
            tool_names = {t.get("name") for t in (r2.get("result") or {}).get("tools", []) if isinstance(t, dict)}
            if not {"vector_stats", "list_collections"}.issubset(tool_names):
                gaps.append(f"vector_db_server tools/list missing required tools: {sorted(tool_names)}")
            if not (r3.get("result") or {}).get("content"):
                gaps.append("vector_db_server tools/call(vector_stats) returned empty content")
        except json.JSONDecodeError as exc:
            gaps.append(f"vector_db_server emitted malformed JSON-RPC: {exc}")

    return {"passed": len(gaps) == 0, "gaps": gaps, "responses_verified": len(lines)}


def _probe_graph_explorer_and_portal(repo_root: Path) -> dict[str, Any]:
    gaps: list[str] = []
    portal_script = repo_root / "scripts" / "serve_agents_graph_portal.py"
    if not portal_script.is_file():
        gaps.append("Missing scripts/serve_agents_graph_portal.py")

    gate_script = repo_root / "tools" / "verify_graph_explorer_gate.py"
    if not gate_script.is_file():
        gaps.append("Missing tools/verify_graph_explorer_gate.py")
        return {"passed": False, "gaps": gaps}

    proc = subprocess.run(
        [sys.executable, str(gate_script), "--standalone"],
        capture_output=True,
        text=True,
        shell=False,
        timeout=60,
        cwd=str(repo_root),
    )
    gate_passed = proc.returncode == 0
    if not gate_passed:
        gaps.append(f"verify_graph_explorer_gate.py --standalone failed (rc={proc.returncode}): {(proc.stderr or proc.stdout)[:240]}")

    return {"passed": len(gaps) == 0, "gaps": gaps, "explorer_gate_passed": gate_passed}


def _resolve_live_canary_candidates(repo_root: Path, agy_bin: str) -> list[str]:
    """Resolve ordered, live-available keyless `agy` canary model pins from SSOT config."""
    from infrastructure.sdks_mcps.agy_cli_transport import AgyTransportError, list_agy_models

    configured: list[str] = []
    cfg_path = repo_root / "config" / "provider_profiles.yaml"
    if cfg_path.is_file():
        try:
            import yaml

            doc = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            ide_gen = doc.get("ide_cli_generation") or {}
            for key in ("quota_backup_models", "ide_models"):
                for item in ide_gen.get(key) or []:
                    slug = str(item or "").strip()
                    if slug and slug not in configured:
                        configured.append(slug)
        except (ImportError, OSError, ValueError):
            pass

    preferred_order = [
        "gemini-3.8-flash-medium",
        "gemini-3.8-flash-low",
        "gemini-4-neon-medium",
        "gemini-4-neon-low",
        *configured,
    ]
    deduped_pref: list[str] = []
    for slug in preferred_order:
        if slug and slug not in deduped_pref:
            deduped_pref.append(slug)

    try:
        available = list_agy_models(agy_bin)
    except AgyTransportError:
        return deduped_pref

    available_set = set(available)
    matched = [slug for slug in deduped_pref if slug in available_set]
    if matched:
        return matched
    fast_live = [slug for slug in available if "flash" in slug or "neon" in slug]
    return fast_live or available


def _probe_keyless_agy_transport_readiness(repo_root: Path, *, live_canary: bool = False) -> dict[str, Any]:
    gaps: list[str] = []
    from infrastructure.sdks_mcps.agy_cli_transport import (
        AgyQuotaExhaustedError,
        clear_agy_quota_cooldowns,
        ide_cli_ready,
        is_agy_model_quota_cooled_down,
        is_agy_quota_error,
        mark_agy_model_quota_exhausted,
        run_agy,
    )

    ready, reason = ide_cli_ready(allow_default_app_bundle=True)
    # Behavioral circuit-breaker check (hermetic, $0.00)
    clear_agy_quota_cooldowns()
    try:
        if not is_agy_quota_error("HTTP 429 RESOURCE_EXHAUSTED: quota exceeded"):
            gaps.append("is_agy_quota_error failed to classify HTTP 429 RESOURCE_EXHAUSTED")
        mark_agy_model_quota_exhausted("canary-probe-model", ttl_s=60.0)
        if not is_agy_model_quota_cooled_down("canary-probe-model"):
            gaps.append("mark_agy_model_quota_exhausted failed to activate cooldown")
    finally:
        clear_agy_quota_cooldowns()

    live_probe_result: dict[str, Any] = {"executed": False}
    if live_canary:
        if not ready:
            gaps.append(f"Live canary requested but keyless agy CLI not ready: {reason}")
        else:
            try:
                from infrastructure.sdks_mcps.agy_cli_transport import discover_agy_bin

                agy_bin = discover_agy_bin(allow_default_app_bundle=True)
                candidates = _resolve_live_canary_candidates(repo_root, agy_bin)
                active_candidates = [m for m in candidates if not is_agy_model_quota_cooled_down(m)]
                if not active_candidates:
                    gaps.append(f"All live canary candidates are in quota cooldown: {candidates}")
                last_quota_err: str | None = None
                for candidate_model in active_candidates:
                    try:
                        res = run_agy(
                            'Return strictly valid JSON: {"canary": "ok"}.',
                            model=candidate_model,
                            json_schema={
                                "type": "object",
                                "required": ["canary"],
                                "properties": {"canary": {"type": "string", "enum": ["ok"]}},
                                "additionalProperties": False,
                            },
                            timeout_s=180,
                            agy_bin=agy_bin,
                        )
                    except AgyQuotaExhaustedError as exc:
                        last_quota_err = f"{candidate_model}: {exc}"
                        continue
                    live_probe_result = {
                        "executed": True,
                        "status": res.status,
                        "model_requested": res.model_requested,
                        "model_reported": res.model_reported,
                        "structured_output": res.structured_output,
                        "conversation_id": res.conversation_id,
                        "marginal_api_cost_usd": 0.0,
                    }
                    if res.status != "SUCCESS":
                        gaps.append(f"Live keyless canary returned non-SUCCESS status: {res.status}")
                    elif res.structured_output != {"canary": "ok"}:
                        gaps.append(
                            f"Live keyless canary returned unexpected structured_output: {res.structured_output!r}"
                        )
                    break
                else:
                    if active_candidates and last_quota_err:
                        gaps.append(f"Live keyless agy canary quota-exhausted across candidates: {last_quota_err}")
            except Exception as exc:  # guardian: allow-broad-exception -- surface live canary failure
                gaps.append(f"Live keyless agy canary failed: {type(exc).__name__}: {exc}")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "ide_cli_ready": ready,
        "ide_cli_reason": reason,
        "live_canary": live_probe_result,
    }


def _probe_sequential_release_gate(repo_root: Path, *, run_release_gate: bool = False) -> dict[str, Any]:
    gate_script = repo_root / "tools" / "verify_release_gate.py"
    if not gate_script.is_file():
        return {"passed": False, "gaps": ["Missing tools/verify_release_gate.py"], "executed": False}
    if not run_release_gate:
        return {"passed": True, "gaps": [], "executed": False, "gate_script_present": True}

    proc = subprocess.run(
        [sys.executable, str(gate_script), "--no-write", "--json"],
        capture_output=True,
        text=True,
        shell=False,
        timeout=300,
        cwd=str(repo_root),
    )
    gaps: list[str] = []
    if proc.returncode != 0:
        gaps.append(f"verify_release_gate.py --no-write failed (rc={proc.returncode}): {(proc.stderr or proc.stdout)[-400:]}")
    return {"passed": len(gaps) == 0, "gaps": gaps, "executed": True, "returncode": proc.returncode}


def run_live_canary_release_audit(
    repo_root: Path | None = None,
    *,
    live_canary: bool = False,
    run_release_gate: bool = False,
) -> dict[str, Any]:
    """Execute Agent 7/7 certification probes across MCP stdio, Graph Portal, keyless transport, and release gate."""
    root = Path(repo_root or DEFAULT_REPO_ROOT).resolve()
    pillars = {
        "pillar_1_vector_db_mcp_stdio": _probe_vector_db_mcp_stdio(root),
        "pillar_2_graph_explorer_and_portal": _probe_graph_explorer_and_portal(root),
        "pillar_3_keyless_agy_transport_and_canary": _probe_keyless_agy_transport_readiness(
            root, live_canary=live_canary
        ),
        "pillar_4_sequential_release_gate": _probe_sequential_release_gate(
            root, run_release_gate=run_release_gate
        ),
    }
    all_gaps = [g for p in pillars.values() for g in p.get("gaps", [])]
    passing = sum(1 for p in pillars.values() if p.get("passed"))
    is_clean = len(all_gaps) == 0
    return {
        "schema_version": "agents.live_canary_release_audit.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "live_canary_requested": live_canary,
        "release_gate_requested": run_release_gate,
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "passing_pillars": passing,
        "total_pillars": len(pillars),
        "total_gaps": len(all_gaps),
        "gaps": all_gaps,
        "pillars": pillars,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live Keyless Canary, MCP Portal & Release Gate Auditor.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--preflight-readiness", action="store_true", help="Verify MCP stdio, Graph Portal, and transport circuit-breaker.")
    parser.add_argument("--live-canary", action="store_true", help="Execute live keyless agy CLI canary ($0.00 API spend).")
    parser.add_argument("--run-release-gate", action="store_true", help="Execute sequential verify_release_gate.py --no-write.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    report = run_live_canary_release_audit(
        args.repo_root,
        live_canary=args.live_canary,
        run_release_gate=args.run_release_gate,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[{report['status']}] Live Canary & Release Certification: "
            f"{report['passing_pillars']}/{report['total_pillars']} pillars passing (gaps={report['total_gaps']})"
        )
        for g in report["gaps"]:
            print(f"  - {g}", file=sys.stderr)
    return 0 if report["is_clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
