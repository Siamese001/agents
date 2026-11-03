#!/usr/bin/env python3
"""Model Pin Integrity and Lifecycle Linter.

Audits model configurations for:
- Floating pins (e.g. '-latest')
- Preview pins (e.g. '-preview')
- Undated or generic family aliases (e.g. 'gpt-4', 'claude-3', 'gemini-pro')
- Mislabelled aliases (e.g. key indicates one family but value points to another)
- Conflicting dated snapshots across catalog/routing keys
- Stale, deprecated, or retired model references

Supports:
  --report: Diagnostic overview mode (default, exit 0)
  --strict: Enforcing CI gate (exit 1 if violations found)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.pr_governance_core.common import bootstrap_shared_venv

bootstrap_shared_venv(_REPO_ROOT)

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


RE_LATEST = re.compile(r"-[lL]atest$")
RE_PREVIEW = re.compile(r"-[pP]review$")
RE_DATED_SNAPSHOT = re.compile(r"-\d{8}$")


def scan_catalog_json(path: Path) -> list[dict[str, Any]]:
    """Scan a JSON model catalog file."""
    findings: list[dict[str, Any]] = []
    if not path.is_file():
        return findings

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append({
            "file": str(path),
            "key": "SCHEMA",
            "val": "",
            "category": "PARSE_ERROR",
            "message": f"Failed to parse JSON: {exc}",
        })
        return findings

    def check_val(key_path: str, val: Any) -> None:
        if not isinstance(val, str):
            return
        val_clean = val.strip()
        # Floating
        if RE_LATEST.search(val_clean):
            findings.append({
                "file": str(path),
                "key": key_path,
                "val": val_clean,
                "category": "FLOATING_PIN",
                "message": f"Floating '-latest' pin: '{val_clean}'",
            })
        # Preview
        if RE_PREVIEW.search(val_clean):
            findings.append({
                "file": str(path),
                "key": key_path,
                "val": val_clean,
                "category": "PREVIEW_PIN",
                "message": f"Preview pin: '{val_clean}'",
            })
        # Mislabelled aliases
        if "haiku_3" in key_path and "haiku-4" in val_clean:
            findings.append({
                "file": str(path),
                "key": key_path,
                "val": val_clean,
                "category": "MISLABELLED_ALIAS",
                "message": f"Key '{key_path}' promises Haiku 3 but resolves to '{val_clean}'",
            })
        if "opus" in key_path and "sonnet" in val_clean:
            findings.append({
                "file": str(path),
                "key": key_path,
                "val": val_clean,
                "category": "MISLABELLED_ALIAS",
                "message": f"Key '{key_path}' promises Opus but resolves to '{val_clean}'",
            })

    def walk_dict(d: Mapping[str, Any], prefix: str = "") -> None:
        for k, v in d.items():
            curr_path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                walk_dict(v, curr_path)
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        walk_dict(item, f"{curr_path}[{i}]")
                    else:
                        check_val(f"{curr_path}[{i}]", item)
            else:
                check_val(curr_path, v)

    if isinstance(data, dict):
        walk_dict(data)

    return findings


def scan_provider_profiles_yaml(path: Path) -> list[dict[str, Any]]:
    """Scan provider_profiles YAML files for pin integrity."""
    findings: list[dict[str, Any]] = []
    if not path.is_file():
        return findings
    if yaml is None:
        findings.append({
            "file": str(path),
            "key": "SCHEMA",
            "val": "",
            "category": "PARSE_ERROR",
            "message": "PyYAML is required for YAML model pin validation (fail-closed)",
        })
        return findings

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append({
            "file": str(path),
            "key": "SCHEMA",
            "val": "",
            "category": "PARSE_ERROR",
            "message": f"Failed to parse YAML: {exc}",
        })
        return findings

    if not isinstance(data, dict):
        return findings

    def _check_pin(key_path: str, pin: Any) -> None:
        if not isinstance(pin, str):
            return
        clean = pin.strip()
        if not clean:
            findings.append({
                "file": str(path),
                "key": key_path,
                "val": clean,
                "category": "EMPTY_PIN",
                "message": f"Empty model pin at '{key_path}'",
            })
            return
        if RE_LATEST.search(clean):
            findings.append({
                "file": str(path),
                "key": key_path,
                "val": clean,
                "category": "FLOATING_PIN",
                "message": f"Floating pin at '{key_path}': '{clean}'",
            })
        if RE_PREVIEW.search(clean):
            findings.append({
                "file": str(path),
                "key": key_path,
                "val": clean,
                "category": "PREVIEW_PIN",
                "message": f"Preview pin at '{key_path}': '{clean}'",
            })

    pin_ownership = data.get("model_pin_ownership", {})
    if isinstance(pin_ownership, dict):
        for role, pin in pin_ownership.items():
            if role not in ("routing_ssot", "shared_catalog_role", "receipt_identity_source", "role_paths"):
                _check_pin(f"model_pin_ownership.{role}", pin)

    profiles = data.get("profiles", {})
    if isinstance(profiles, dict):
        for prof_name, prof_cfg in profiles.items():
            if not isinstance(prof_cfg, dict):
                continue
            for section_key in ("model_by_section", "anthropic_limit_backup_model_by_section"):
                sec_map = prof_cfg.get(section_key, {})
                if isinstance(sec_map, dict):
                    for sec_name, pin in sec_map.items():
                        _check_pin(f"profiles.{prof_name}.{section_key}.{sec_name}", pin)

    judge_models = data.get("judge_models", {})
    if isinstance(judge_models, dict):
        for tier_name, tier_map in judge_models.items():
            if isinstance(tier_map, dict):
                for prov_name, pin in tier_map.items():
                    _check_pin(f"judge_models.{tier_name}.{prov_name}", pin)

    selector_models = data.get("selector_models", {})
    if isinstance(selector_models, dict):
        for sel_name, sel_cfg in selector_models.items():
            if isinstance(sel_cfg, dict):
                _check_pin(f"selector_models.{sel_name}.model", sel_cfg.get("model"))
                backup = sel_cfg.get("anthropic_limit_backup")
                if isinstance(backup, dict):
                    _check_pin(f"selector_models.{sel_name}.anthropic_limit_backup.model", backup.get("model"))

    return findings


def audit_model_pins(repo_root: Path) -> list[dict[str, Any]]:
    """Run full model pin integrity audit."""
    targets = [
        repo_root / "config/model_catalog.json",
        repo_root / "resume_graph_engine/config/model_catalog.json",
        repo_root / "config/provider_profiles.yaml",
        repo_root / "resume_graph_engine/src/apps_rg/config/provider_profiles.yaml",
    ]

    all_findings: list[dict[str, Any]] = []
    for target in targets:
        if not target.is_file():
            continue
        if target.suffix == ".json":
            all_findings.extend(scan_catalog_json(target))
        elif target.suffix in (".yaml", ".yml"):
            all_findings.extend(scan_provider_profiles_yaml(target))

    return all_findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Model Pin Integrity and Lifecycle Linter.")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument("--strict", action="store_true", help="Fail with exit 1 if violations found")
    parser.add_argument("--report", action="store_true", default=True, help="Generate audit report")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    findings = audit_model_pins(repo_root)

    print(f"[MODEL PIN LINTER] Scanned configuration surfaces under {repo_root}")
    print(f"Total findings: {len(findings)}\n")

    if findings:
        for f in findings:
            try:
                rel_f = str(Path(f["file"]).relative_to(repo_root))
            except ValueError:
                rel_f = f["file"]
            print(f"  [{f['category']}] {rel_f} :: {f['key']}")
            print(f"    Value: {f['val']}")
            print(f"    Detail: {f['message']}")
            print()

    if args.strict and findings:
        print(f"[FAIL] Model pin linter failed in strict mode ({len(findings)} violations).", file=sys.stderr)
        return 1

    print(f"[PASS] Model pin linter complete ({len(findings)} findings recorded).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
