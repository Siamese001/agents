#!/usr/bin/env python3
"""Model Pin Integrity and Lifecycle Linter.

Audits model configurations for:
- Floating pins (e.g. '-latest')
- Preview pins (e.g. '-preview')
- Undated or generic bare family aliases
- Mislabelled family aliases (e.g. key promises one family/tier while value resolves to another)
- Unapproved pins in provider_profiles.yaml missing from the canonical model catalog
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

from tools.hitl_governance import load_approved_provider_models  # noqa: E402

RE_LATEST = re.compile(r"-[lL]atest$")
RE_PREVIEW = re.compile(r"-[pP]review$")
BARE_FAMILY_ALIASES: frozenset[str] = frozenset(
    {"gpt", "gpt-3.5", "gpt-4", "claude", "claude-2", "claude-3", "gemini", "gemini-pro"}
)
CLAUDE_TIERS: tuple[str, ...] = ("haiku", "sonnet", "opus")


def _detect_alias_mismatch(key_path: str, val_clean: str) -> str | None:
    """Detect family/tier mismatches between alias keys and resolved model values."""
    leaf_key = key_path.rsplit(".", 1)[-1].lower()
    val_low = val_clean.lower()
    if "haiku_3" in leaf_key and "haiku-4" in val_low:
        return f"Key '{key_path}' promises Haiku 3 but resolves to '{val_clean}'"
    for expected_tier in CLAUDE_TIERS:
        if re.search(rf"(?:^|_){expected_tier}(?:_|$|\d)", leaf_key):
            for other_tier in CLAUDE_TIERS:
                if other_tier != expected_tier and other_tier in val_low and expected_tier not in val_low:
                    return f"Key '{key_path}' promises '{expected_tier}' tier but resolves to '{val_clean}'"
    if leaf_key.startswith("openai_") and any(p in val_low for p in ("claude-", "gemini-")):
        return f"Key '{key_path}' declares OpenAI family but resolves to '{val_clean}'"
    if leaf_key.startswith("anthropic_") and any(p in val_low for p in ("gpt-", "gemini-")):
        return f"Key '{key_path}' declares Anthropic family but resolves to '{val_clean}'"
    if leaf_key.startswith("gemini_") and any(p in val_low for p in ("gpt-", "claude-")):
        return f"Key '{key_path}' declares Gemini family but resolves to '{val_clean}'"
    return None


def scan_catalog_json(path: Path) -> list[dict[str, Any]]:
    """Scan a JSON model catalog file."""
    findings: list[dict[str, Any]] = []
    if not path.is_file():
        return findings

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(
            {
                "file": str(path),
                "key": "SCHEMA",
                "val": "",
                "category": "PARSE_ERROR",
                "message": f"Failed to parse JSON: {exc}",
            }
        )
        return findings

    def check_val(key_path: str, val: Any) -> None:
        if not isinstance(val, str):
            return
        val_clean = val.strip()
        if RE_LATEST.search(val_clean):
            findings.append(
                {
                    "file": str(path),
                    "key": key_path,
                    "val": val_clean,
                    "category": "FLOATING_PIN",
                    "message": f"Floating '-latest' pin: '{val_clean}'",
                }
            )
        if RE_PREVIEW.search(val_clean):
            findings.append(
                {
                    "file": str(path),
                    "key": key_path,
                    "val": val_clean,
                    "category": "PREVIEW_PIN",
                    "message": f"Preview pin: '{val_clean}'",
                }
            )
        if val_clean.lower() in BARE_FAMILY_ALIASES and ".legacy." not in key_path and ".generic." not in key_path:
            findings.append(
                {
                    "file": str(path),
                    "key": key_path,
                    "val": val_clean,
                    "category": "BARE_FAMILY_ALIAS",
                    "message": f"Generic unpinned family alias '{val_clean}' at '{key_path}'",
                }
            )
        mismatch = _detect_alias_mismatch(key_path, val_clean)
        if mismatch:
            findings.append(
                {
                    "file": str(path),
                    "key": key_path,
                    "val": val_clean,
                    "category": "MISLABELLED_ALIAS",
                    "message": mismatch,
                }
            )

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


def scan_provider_profiles_yaml(
    path: Path,
    approved_models: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Scan provider_profiles YAML files for pin integrity and catalog conformance."""
    findings: list[dict[str, Any]] = []
    if not path.is_file():
        return findings
    if yaml is None:
        findings.append(
            {
                "file": str(path),
                "key": "SCHEMA",
                "val": "",
                "category": "PARSE_ERROR",
                "message": "PyYAML is required for YAML model pin validation (fail-closed)",
            }
        )
        return findings

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        findings.append(
            {
                "file": str(path),
                "key": "SCHEMA",
                "val": "",
                "category": "PARSE_ERROR",
                "message": f"Failed to parse YAML: {exc}",
            }
        )
        return findings

    if not isinstance(data, dict):
        return findings

    def _check_pin(key_path: str, pin: Any) -> None:
        if not isinstance(pin, str):
            return
        clean = pin.strip()
        if not clean:
            findings.append(
                {
                    "file": str(path),
                    "key": key_path,
                    "val": clean,
                    "category": "EMPTY_PIN",
                    "message": f"Empty model pin at '{key_path}'",
                }
            )
            return
        if RE_LATEST.search(clean):
            findings.append(
                {
                    "file": str(path),
                    "key": key_path,
                    "val": clean,
                    "category": "FLOATING_PIN",
                    "message": f"Floating pin at '{key_path}': '{clean}'",
                }
            )
        if RE_PREVIEW.search(clean):
            findings.append(
                {
                    "file": str(path),
                    "key": key_path,
                    "val": clean,
                    "category": "PREVIEW_PIN",
                    "message": f"Preview pin at '{key_path}': '{clean}'",
                }
            )
        if clean.lower() in BARE_FAMILY_ALIASES:
            findings.append(
                {
                    "file": str(path),
                    "key": key_path,
                    "val": clean,
                    "category": "BARE_FAMILY_ALIAS",
                    "message": f"Generic unpinned family alias at '{key_path}': '{clean}'",
                }
            )
        if approved_models and clean.lower() not in approved_models:
            findings.append(
                {
                    "file": str(path),
                    "key": key_path,
                    "val": clean,
                    "category": "UNAPPROVED_PIN",
                    "message": f"Model pin '{clean}' at '{key_path}' is missing from approved model catalog",
                }
            )

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
    """Run full model pin integrity audit across JSON catalogs and YAML routing profiles."""
    approved = load_approved_provider_models(repo_root)
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
            all_findings.extend(scan_provider_profiles_yaml(target, approved_models=approved or None))

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
