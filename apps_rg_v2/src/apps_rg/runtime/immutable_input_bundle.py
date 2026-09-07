"""Capture product inputs once and bind downstream execution to their digests.

Product entry accepts text supplied by its authenticated caller.  It deliberately
does not dereference caller-controlled local paths or URLs: those are an upload/
egress concern and must be converted to text before product authorization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final


INPUT_BUNDLE_DIRNAME: Final[str] = "validated_inputs"
INPUT_BUNDLE_MANIFEST: Final[str] = "validated_input_bundle.v1.json"


class ProductInputBundleError(ValueError):
    """A product run supplied a reference instead of immutable request bytes."""


@dataclass(frozen=True, slots=True)
class ProductInputBundle:
    """Immutable product-run material and the durable receipt that binds it."""

    source_resume_text: str
    job_description_text: str
    manual_brief_ref: str
    manifest_path: Path
    digest: str


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _names_existing_file(value: str) -> bool:
    try:
        return Path(value).is_file()
    except OSError:
        return False


def _reject_reference(*, field: str, value: str) -> None:
    ref = str(value or "").strip()
    if ref:
        kind = "remote URL" if _is_url(ref) else "file/artifact reference"
        raise ProductInputBundleError(
            f"{field} must be submitted as immutable text, not a {kind}"
        )


def freeze_product_inputs(
    *,
    artifact_dir: Path,
    source_resume_text: str = "",
    source_resume_ref: str = "",
    jd: str = "",
    job_description_text: str = "",
    job_description_ref: str = "",
    manual_brief: str = "",
) -> ProductInputBundle:
    """Persist caller text once and return only content-addressed product inputs.

    ``manual_brief`` may be inline text.  A value that names an existing local
    file or begins with an HTTP(S) scheme is rejected rather than read.  This
    closes the pre-U0 local-file and SSRF paths while retaining a durable local
    artifact for components that require a briefing reference.
    """

    _reject_reference(field="source_resume_ref", value=source_resume_ref)
    _reject_reference(field="job_description_ref", value=job_description_ref)

    resume = str(source_resume_text or "").strip()
    jd_text = str(job_description_text or jd or "").strip()
    brief = str(manual_brief or "").strip()
    if _is_url(brief) or _names_existing_file(brief):
        _reject_reference(field="manual_brief", value=brief)

    root = artifact_dir / INPUT_BUNDLE_DIRNAME
    root.mkdir(parents=True, exist_ok=False)
    material = {
        "source_resume_text": resume,
        "job_description_text": jd_text,
        "manual_brief_text": brief,
    }
    digests = {name: _digest(value) for name, value in material.items()}
    refs: dict[str, str] = {}
    for name, value in material.items():
        if not value:
            continue
        filename = f"{name}.{digests[name]}.txt"
        path = root / filename
        path.write_text(value + "\n", encoding="utf-8", newline="\n")
        refs[name] = str(path)

    manifest = {
        "schema_version": "apps_rg.validated_input_bundle.v1",
        "source_kind": "inline_immutable_text",
        "inputs": {
            name: {"sha256": digests[name], "artifact_ref": refs.get(name, "")}
            for name in material
        },
    }
    manifest_blob = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    bundle_digest = hashlib.sha256(manifest_blob.encode("utf-8")).hexdigest()
    manifest["bundle_digest"] = bundle_digest
    manifest_path = artifact_dir / INPUT_BUNDLE_MANIFEST
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ProductInputBundle(
        source_resume_text=resume,
        job_description_text=jd_text,
        manual_brief_ref=refs.get("manual_brief_text", ""),
        manifest_path=manifest_path,
        digest=bundle_digest,
    )


__all__ = [
    "INPUT_BUNDLE_MANIFEST",
    "ProductInputBundle",
    "ProductInputBundleError",
    "freeze_product_inputs",
]
