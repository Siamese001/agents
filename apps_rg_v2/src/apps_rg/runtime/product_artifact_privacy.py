"""Redact product diagnostic payloads before review packaging and terminal sealing.

Evidence and final output remain available to the governed product pipeline.
Verbose prompts and raw provider transport bodies are debugging material, not
product authority, and must not survive in a product artifact bundle.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REDACTION_RECEIPT = "product_diagnostic_redaction_receipt.json"
_TEXT_DIAGNOSTICS = frozenset(
    {"compiled_prompt.txt", "command_output.txt", "raw_model_output.txt", "raw_model_output_original.txt"}
)
_JSON_DIAGNOSTIC_PREFIXES = ("provider_request", "provider_response")
_SENSITIVE_JSON_KEYS = frozenset(
    {
        "content",
        "messages",
        "prompt",
        "raw_model_output",
        "raw_response",
        "request_body",
        "response_body",
    }
)


class ProductArtifactPrivacyError(RuntimeError):
    """Raised when a product diagnostic cannot be redacted safely."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _redaction_marker(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        raw = value.encode("utf-8")
        shape = "text"
    else:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        shape = "structured"
    return {"redacted": True, "content_type": shape, "byte_length": len(raw), "sha256": _sha256(raw)}


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _redaction_marker(item)
            if str(key).lower() in _SENSITIVE_JSON_KEYS
            else _redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    return value


def _is_json_diagnostic(path: Path) -> bool:
    return path.suffix.lower() == ".json" and path.name.startswith(_JSON_DIAGNOSTIC_PREFIXES)


def _is_text_diagnostic(path: Path) -> bool:
    return path.name in _TEXT_DIAGNOSTICS


def redact_product_diagnostics(artifact_dir: Path | str) -> Path:
    """Replace raw prompt/provider diagnostics with digest-bound redaction markers.

    This runs after all runtime consumers have completed but before any review
    bundle or terminal manifest is written, so sealed artifacts describe the
    redacted bytes rather than a post-seal mutation.
    """

    root = Path(artifact_dir).resolve()
    if not root.is_dir():
        raise ProductArtifactPrivacyError(f"product artifact directory is absent: {root}")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            path.relative_to(root)
        except ValueError as exc:  # pragma: no cover - resolve/rglob containment guard
            raise ProductArtifactPrivacyError(f"diagnostic escapes product root: {path}") from exc
        before = path.read_bytes()
        if _is_text_diagnostic(path):
            replacement = (
                "REDACTED_PRODUCT_DIAGNOSTIC\n"
                f"sha256={_sha256(before)}\nbyte_length={len(before)}\n"
            ).encode("utf-8")
            kind = "raw_text_diagnostic"
        elif _is_json_diagnostic(path):
            try:
                parsed = json.loads(before)
            except json.JSONDecodeError as exc:
                raise ProductArtifactPrivacyError(
                    f"provider diagnostic is invalid JSON: {path.relative_to(root)}"
                ) from exc
            replacement = (json.dumps(_redact_json(parsed), indent=2, sort_keys=True) + "\n").encode("utf-8")
            kind = "provider_transport_diagnostic"
        else:
            continue
        if replacement == before:
            continue
        path.write_bytes(replacement)
        rows.append(
            {
                "artifact_ref": path.relative_to(root).as_posix(),
                "kind": kind,
                "original_sha256": _sha256(before),
                "redacted_sha256": _sha256(replacement),
                "original_byte_length": len(before),
            }
        )
    receipt = {
        "schema_version": "apps_rg.product_diagnostic_redaction.v1",
        "mode": "redact_before_review_bundle_and_terminal_seal",
        "redacted_count": len(rows),
        "redactions": rows,
    }
    receipt_path = root / REDACTION_RECEIPT
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt_path


__all__ = [
    "ProductArtifactPrivacyError",
    "REDACTION_RECEIPT",
    "redact_product_diagnostics",
]
