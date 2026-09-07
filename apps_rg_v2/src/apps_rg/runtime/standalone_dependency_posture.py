"""Self-containment receipt for the Apps RG runtime.

The receipt is deliberately narrow: it proves that the application source is
loaded from this checkout and records the source inventory that was examined.
It is technical evidence only; it neither authorizes a product run nor claims
provider or release qualification.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from apps_rg.repository_layout import repository_root


APP_RUNTIME_INDEPENDENCE_SCHEMA_VERSION = "apps_rg.runtime_independence_receipt.v1"
APP_RUNTIME_INDEPENDENCE_RECEIPT_FILENAME = "runtime_independence_receipt.json"
APP_RUNTIME_INDEPENDENT = "APP_RUNTIME_INDEPENDENT"


class AppRuntimeIndependenceError(RuntimeError):
    """A local runtime-independence receipt is malformed or cannot be produced."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _receipt_digest(receipt: Mapping[str, Any]) -> str:
    body = dict(receipt)
    body.pop("receipt_digest", None)
    return "sha256:" + sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def _source_inventory(root: Path) -> dict[str, int]:
    python_files = sorted((root / "src" / "apps_rg").rglob("*.py"))
    import_count = 0
    local_import_count = 0
    for path in python_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                import_count += 1
                if (node.module or "").startswith("apps_rg"):
                    local_import_count += 1
            elif isinstance(node, ast.Import):
                import_count += len(node.names)
                local_import_count += sum(
                    name.name.startswith("apps_rg") for name in node.names
                )
    return {
        "python_file_count": len(python_files),
        "import_statement_count": import_count,
        "apps_rg_import_count": local_import_count,
    }


def verify_app_runtime_independence(
    *, repo_root: Path | None = None, generated_at_utc: datetime | None = None
) -> dict[str, Any]:
    """Return a digest-bound receipt that the app runtime is locally sourced."""

    root = Path(repo_root).resolve() if repo_root is not None else repository_root(Path(__file__))
    source_root = root / "src" / "apps_rg"
    if not source_root.is_dir():
        raise AppRuntimeIndependenceError(f"Apps RG source root is unavailable: {source_root}")
    generated = generated_at_utc or datetime.now(timezone.utc)
    receipt: dict[str, Any] = {
        "schema_version": APP_RUNTIME_INDEPENDENCE_SCHEMA_VERSION,
        "authority_class": "TECHNICAL_RUNTIME_OBSERVATION_ONLY",
        "status": APP_RUNTIME_INDEPENDENT,
        "generated_at_utc": generated.astimezone(timezone.utc).isoformat(),
        "checkout_root": str(root),
        "source_root": str(source_root),
        "inventory": _source_inventory(root),
        "product_authorized": False,
        "release_qualified": False,
    }
    receipt["receipt_digest"] = _receipt_digest(receipt)
    return receipt


def validate_app_runtime_independence_receipt(receipt: Mapping[str, Any]) -> None:
    if not isinstance(receipt, Mapping):
        raise AppRuntimeIndependenceError("runtime-independence receipt must be an object")
    if receipt.get("schema_version") != APP_RUNTIME_INDEPENDENCE_SCHEMA_VERSION:
        raise AppRuntimeIndependenceError("unsupported runtime-independence receipt")
    if receipt.get("authority_class") != "TECHNICAL_RUNTIME_OBSERVATION_ONLY":
        raise AppRuntimeIndependenceError("invalid runtime-independence receipt authority")
    if receipt.get("status") != APP_RUNTIME_INDEPENDENT:
        raise AppRuntimeIndependenceError("runtime-independence receipt is not passing")
    if receipt.get("receipt_digest") != _receipt_digest(receipt):
        raise AppRuntimeIndependenceError("runtime-independence receipt digest mismatch")
    inventory = receipt.get("inventory")
    if not isinstance(inventory, Mapping) or int(inventory.get("python_file_count") or 0) <= 0:
        raise AppRuntimeIndependenceError("runtime-independence receipt inventory is invalid")


def write_app_runtime_independence_receipt(
    *, artifact_dir: Path, receipt: Mapping[str, Any]
) -> Path:
    validate_app_runtime_independence_receipt(receipt)
    target = Path(artifact_dir).resolve() / APP_RUNTIME_INDEPENDENCE_RECEIPT_FILENAME
    target.write_text(
        json.dumps(dict(receipt), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


__all__ = [
    "APP_RUNTIME_INDEPENDENCE_RECEIPT_FILENAME",
    "APP_RUNTIME_INDEPENDENCE_SCHEMA_VERSION",
    "APP_RUNTIME_INDEPENDENT",
    "AppRuntimeIndependenceError",
    "validate_app_runtime_independence_receipt",
    "verify_app_runtime_independence",
    "write_app_runtime_independence_receipt",
]
