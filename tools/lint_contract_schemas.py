#!/usr/bin/env python3
"""Deterministic contract and schema validator.

Validates JSON/YAML syntax and enforces schema compliance on declarative configurations,
manifests, and contracts against repository schemas in config/schemas/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

try:
    import jsonschema
except ImportError:
    jsonschema = None

try:
    import yaml
except ImportError:
    yaml = None


SCHEMA_DIRECTORIES: tuple[str, ...] = (
    "config/schemas",
    "resume_graph_engine/config/schemas",
)

# Explicit mappings of file pattern or filename to schema file
KNOWN_SCHEMA_MAPPINGS: dict[str, str] = {
    "context_assembly_manifest.yaml": "context_assembly_manifest.schema.json",
    "structure_blueprint.yaml": "structure_blueprint.schema.json",
    "canonical_pipeline.yaml": "canonical_pipeline.schema.json",
    "token_budget.yaml": "token_budget.schema.json",
    "layer_overrides.yaml": "layer_overrides.schema.json",
    "escalation_packet.json": "escalation_packet.schema.json",
    "eval_event.json": "eval_event.schema.json",
    "exit_decision.json": "exit_decision.schema.json",
}


def load_file_content(path: Path) -> tuple[Any, str | None]:
    """Parse JSON or YAML content. Returns (parsed_obj, error_message)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        try:
            return json.loads(text), None
        except Exception as e:
            return None, f"JSON syntax error: {e}"
    elif path.suffix.lower() in (".yaml", ".yml"):
        if yaml is None:
            return None, "PyYAML not installed"
        try:
            return yaml.safe_load(text), None
        except Exception as e:
            return None, f"YAML syntax error: {e}"
    return None, "Unsupported file format"


def validate_file_against_schema(
    file_path: Path,
    repo_root: Path,
) -> tuple[bool, str]:
    """Validate a JSON or YAML file for syntax and schema compliance."""
    if not file_path.exists():
        return True, "File does not exist"

    # Skip schema files themselves
    if file_path.name.endswith(".schema.json"):
        # Validate that the schema itself is valid JSON
        try:
            schema_data = json.loads(file_path.read_text(encoding="utf-8"))
            if jsonschema:
                jsonschema.Draft7Validator.check_schema(schema_data)
            return True, "Valid JSON Schema"
        except Exception as e:
            return False, f"Invalid schema structure: {e}"

    # Verify JSON / YAML syntax
    if file_path.suffix.lower() in (".json", ".yaml", ".yml"):
        data, err = load_file_content(file_path)
        if err:
            return False, err

        # Check if mapped schema exists
        schema_file_name = KNOWN_SCHEMA_MAPPINGS.get(file_path.name)
        if schema_file_name and jsonschema and isinstance(data, dict):
            # Locate schema
            for s_dir in SCHEMA_DIRECTORIES:
                candidate = repo_root / s_dir / schema_file_name
                if candidate.is_file():
                    try:
                        schema_obj = json.loads(candidate.read_text(encoding="utf-8"))
                        jsonschema.validate(instance=data, schema=schema_obj)
                        return True, f"Valid against schema {schema_file_name}"
                    except jsonschema.ValidationError as ve:
                        return False, f"Schema validation error against {schema_file_name}: {ve.message}"
                    except Exception as e:
                        return False, f"Error reading schema {schema_file_name}: {e}"

        return True, "Syntax valid"

    return True, "Skipped non-declarative file"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic contract and schema validator.")
    parser.add_argument("--files", nargs="*", help="Specific files to validate")
    parser.add_argument("--all", action="store_true", help="Validate all schemas and declarative configs")
    parser.add_argument("--repo-root", default=".", help="Root of repository")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    failures = []

    if args.files:
        files_to_check = [Path(f) if Path(f).is_absolute() else repo_root / f for f in args.files]
    else:
        # Check all schemas and configs in config/
        files_to_check = []
        for s_dir in SCHEMA_DIRECTORIES:
            d = repo_root / s_dir
            if d.exists():
                files_to_check.extend(d.glob("*.json"))
                files_to_check.extend(d.glob("*.yaml"))
        config_dir = repo_root / "config"
        if config_dir.exists():
            files_to_check.extend(config_dir.glob("*.json"))
            files_to_check.extend(config_dir.glob("*.yaml"))

    for f in files_to_check:
        if f.suffix.lower() in (".json", ".yaml", ".yml"):
            ok, msg = validate_file_against_schema(f, repo_root)
            rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
            if not ok:
                failures.append((rel, msg))

    if failures:
        print(f"[FAIL] Schema/Contract validation failed ({len(failures)} errors):", file=sys.stderr)
        for rel, msg in failures:
            print(f"  - {rel}: {msg}", file=sys.stderr)
        return 1

    print(f"[PASS] Contract / Schema validation clean (checked {len(files_to_check)} declarative artifacts).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
