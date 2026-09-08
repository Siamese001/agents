"""Read-only Apps RG adapter over an already-closed product run."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from apps_eval.contracts import AppOutputSnapshot

_LANE_ARTIFACT_ROLE_BY_NAME = {
    "l2_output.json": "lane_l2_output",
    "runtime_payload.json": "lane_runtime_payload",
    "x2_gate_outputs.json": "lane_x2_gate_outputs",
    "x1d_llm_judge_outputs.json": "lane_x1d_llm_judge_outputs",
    "x3_disposition.json": "lane_x3_disposition",
    "l6_shadow_eval_package.json": "lane_l6_shadow_eval_package",
}
_EVAL_OWNED_TOP_LEVEL = frozenset({"apps_eval"})
_SOURCE_ID_KEYS = frozenset({"source_id", "source_ref", "evidence_ref"})
_SOURCE_IDS_KEYS = frozenset({"source_ids", "source_refs", "evidence_refs"})
_SOURCE_DIGEST_KEYS = (
    "source_digest",
    "source_sha256",
    "evidence_digest",
    "evidence_sha256",
)
_IDENTITY_KEYS = (
    "parent_run_id",
    "child_run_id",
    "section_attempt_id",
    "runtime_exhaust_bundle_id",
)
_IDENTITY_ARTIFACTS = (
    "apps_research_apps_rg_handoff_v2.json",
    "e2e_preflight_continuation_receipt.json",
    "e2e_preflight_product_entry_receipt.json",
    "apps_rg_product_authorization_receipt.json",
    "r4_run_manifest.json",
    "integrated_runtime_artifact_manifest.json",
    "apps_rg_spine_proof.json",
    "runtime_exhaust_bundle.json",
)
_CANONICAL_IDENTITY_KEYS = (
    "producer_app_id",
    "consumer_app_id",
    "parent_run_id",
    "child_run_id",
    "request_id",
    "trace_root",
    "tenant_id",
    "target_company",
    "target_role",
    "jd_sha256",
    "brief_sha256",
    "policy_hash",
    "blueprint_hash",
    "schema_version",
)
_PRODUCT_AUTHORIZATION_RECEIPT = "apps_rg_product_authorization_receipt.json"
_PREFLIGHT_PRODUCT_ENTRY_RECEIPT = "e2e_preflight_product_entry_receipt.json"
_PREFLIGHT_CONTINUATION_RECEIPT = "e2e_preflight_continuation_receipt.json"
_PREFLIGHT_CONSUMPTION_RECEIPT = (
    "e2e_preflight_continuation_consumption_receipt.json"
)
_ROUTE_HMAC_VERIFIER_KEYRING_ENV = "APPS_RG_ROUTE_HMAC_VERIFIER_KEYRING"
_ROUTE_HMAC_VERIFIER_KEYRING_SCHEMA = "apps_rg.route_hmac_verifier_keyring.v1"


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _bootstrap_apps_rg_env_for_live_replay() -> None:
    """Load the shared Apps RG dotenv before reopening signed run evidence.

    Apps Eval normally imports this adapter directly, so importing ``apps_rg``
    is not guaranteed to have run its package-level dotenv bootstrap.  That
    made a valid replay depend on an operator manually exporting the route
    HMAC material even when the shared Apps RG dotenv already contained it.
    This is credential loading only; the adapter remains read-only and does
    not dispatch a provider.  Pytest intentionally retains fully isolated
    process environments.
    """

    if "pytest" in sys.modules or os.environ.get("APPS_RG_TEST_HARNESS"):
        return
    try:
        from apps_rg.runtime.env_bootstrap import bootstrap_apps_rg_env

        bootstrap_apps_rg_env()
    except Exception:  # noqa: BLE001 - evidence verification fails closed below.
        return


def _json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _payload_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _hmac_signature(secret: str | bytes, body: Mapping[str, Any]) -> str:
    key = secret if isinstance(secret, bytes) else secret.encode("utf-8")
    return "hmac-sha256:" + hmac.new(
        key,
        _canonical_json_bytes(dict(body)),
        hashlib.sha256,
    ).hexdigest()


def _resolve_hmac_verifier_key(
    key_id: str,
) -> tuple[bytes, dict[str, Any], list[str]]:
    """Resolve replay-verification material without embedding it in run artifacts.

    A stable, operator-owned keyring is preferred.  The legacy environment
    secret remains a compatibility path for in-process current-run evaluation,
    but the zero-provider replay guard removes it so historical replay cannot
    silently depend on ephemeral key material.
    """

    normalized_key_id = _as_text(key_id)
    keyring_ref = _as_text(os.environ.get(_ROUTE_HMAC_VERIFIER_KEYRING_ENV))
    metadata: dict[str, Any] = {
        "algorithm": "HMAC-SHA256",
        "key_id": normalized_key_id,
        "key_source": "",
        "verifier_material_ref": keyring_ref,
        "verifier_material_sha256": "",
    }
    if keyring_ref:
        path = Path(keyring_ref).expanduser()
        try:
            raw = path.read_bytes()
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError, TypeError):
            return b"", metadata, ["preflight_verifier_keyring_unreadable"]
        metadata["verifier_material_ref"] = path.resolve().as_posix()
        metadata["verifier_material_sha256"] = _bytes_digest(raw)
        if not isinstance(payload, Mapping):
            return b"", metadata, ["preflight_verifier_keyring_invalid"]
        if payload.get("schema_version") != _ROUTE_HMAC_VERIFIER_KEYRING_SCHEMA:
            return b"", metadata, ["preflight_verifier_keyring_schema_mismatch"]
        keys = payload.get("keys")
        keys = dict(keys) if isinstance(keys, Mapping) else {}
        entry = keys.get(normalized_key_id)
        entry = dict(entry) if isinstance(entry, Mapping) else {}
        if not normalized_key_id or not entry:
            return b"", metadata, ["preflight_verifier_key_id_not_found"]
        if entry.get("algorithm") != "HMAC-SHA256":
            return b"", metadata, ["preflight_verifier_algorithm_mismatch"]
        if entry.get("status", "ACTIVE") != "ACTIVE":
            return b"", metadata, ["preflight_verifier_key_not_active"]
        try:
            key = base64.b64decode(_as_text(entry.get("key_b64")), validate=True)
        except (ValueError, binascii.Error):
            return b"", metadata, ["preflight_verifier_key_encoding_invalid"]
        if len(key) < 32:
            return b"", metadata, ["preflight_verifier_key_too_short"]
        metadata["key_source"] = "STABLE_VERIFIER_KEYRING"
        return key, metadata, []

    legacy_secret = _as_text(os.environ.get("APPS_RG_ROUTE_HMAC_SECRET"))
    if legacy_secret:
        metadata["key_source"] = "LEGACY_EPHEMERAL_ENV"
        return legacy_secret.encode("utf-8"), metadata, []
    return b"", metadata, ["preflight_verifier_key_material_missing"]


def _preflight_verification_status(errors: list[str]) -> str:
    if any(
        error
        in {
            "preflight_verifier_key_material_missing",
            "preflight_verifier_key_id_not_found",
            "preflight_verifier_keyring_unreadable",
        }
        for error in errors
    ):
        return "UNVERIFIABLE_KEY_MATERIAL"
    return "INVALID" if errors else "VERIFIED"


def _parse_utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(_as_text(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _is_prefixed_sha256(value: Any) -> bool:
    text = _as_text(value)
    return (
        len(text) == 71
        and text.startswith("sha256:")
        and text[7:] == text[7:].lower()
        and all(char in "0123456789abcdef" for char in text[7:])
    )


def _contained_source_path(ref: str | Path, artifact_dir: Path) -> Path | None:
    root = artifact_dir.resolve()
    raw = Path(ref)
    candidate = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def build_source_artifact_manifest(artifact_dir: Path) -> list[dict[str, Any]]:
    """Return a byte-bound manifest without following evidence outside the run.

    ``apps_eval`` is an Eval-owned child used by the current-run caller.  It is
    deliberately excluded so emitting Eval artifacts cannot change the sealed
    product-source digest.
    """

    root = artifact_dir.resolve()
    if not root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in _EVAL_OWNED_TOP_LEVEL:
            continue
        resolved = _contained_source_path(path, root)
        if resolved is None:
            continue
        try:
            raw = resolved.read_bytes()
        except OSError:
            continue
        entries.append(
            {
                "artifact_ref": rel.as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "byte_length": len(raw),
            }
        )
    return entries


def source_artifact_manifest_digest(manifest: list[dict[str, Any]]) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_receipt_x3(artifact_dir: Path) -> str:
    path = _contained_source_path("x3_disposition_receipt.json", artifact_dir)
    if path is None or not path.is_file():
        return ""
    receipt = _json_object(path)
    payload = receipt.get("payload") if isinstance(receipt.get("payload"), dict) else receipt
    return _as_text(
        payload.get("disposition")
        or payload.get("x3_code")
        or payload.get("x3_disposition")
    )


def _canonical_x3(raw: str) -> str:
    return _as_text(raw)


def _result_x3(result: dict[str, Any], artifact_dir: Path) -> str:
    del result  # caller summaries are not authoritative Exit evidence
    raw = _read_receipt_x3(artifact_dir) or "UNKNOWN"
    return _canonical_x3(raw)


def _generated_resume_path(artifact_dir: Path) -> Path | None:
    final_output = _json_object(artifact_dir / "FINAL_RESUME_OUTPUT.json")
    final_binding = final_output.get("final_resume_json")
    if isinstance(final_binding, Mapping):
        bound = _contained_source_path(
            str(final_binding.get("relpath") or ""), artifact_dir
        )
        if bound is not None and bound.is_file():
            return bound
    candidates = [
        artifact_dir / "outputs" / "generated_resume.json",
        artifact_dir / "final_resume.json",
        artifact_dir / "modular_r4" / "final_resume_assembly" / "final_resume.json",
        artifact_dir / "modular_r4" / "outputs" / "generated_resume.json",
        artifact_dir / "modular_r4" / "outputs" / "final_resume.json",
    ]
    for path in candidates:
        contained = _contained_source_path(path, artifact_dir)
        if contained is not None and contained.is_file():
            return contained
    return None


def _stringify_section(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"].strip()
        return " ".join(_stringify_section(v) for v in value.values()).strip()
    if isinstance(value, list):
        return " ".join(_stringify_section(v) for v in value).strip()
    return _as_text(value)


def _normalize_sections(generated_resume: dict[str, Any]) -> dict[str, str]:
    raw_sections = generated_resume.get("sections")
    sections = raw_sections if isinstance(raw_sections, dict) else {}
    if isinstance(raw_sections, list):
        section_rows = [row for row in raw_sections if isinstance(row, Mapping)]
        by_id = {
            str(row.get("section_id") or ""): dict(row)
            for row in section_rows
            if str(row.get("section_id") or "")
        }

        def rendered_lane(section_id: str) -> str:
            row = by_id.get(section_id, {})
            snapshot = row.get("l2_output_snapshot")
            snapshot = snapshot if isinstance(snapshot, Mapping) else {}
            return _stringify_section(snapshot)

        experience_parts = [
            rendered_lane(section_id)
            for section_id in (
                "unify_narrative",
                "unify_bullets",
                "ibm_narrative",
                "ibm_bullets",
                "insurtech_narrative",
                "insurtech_bullets",
                "ey_narrative",
                "ey_bullets",
            )
            if rendered_lane(section_id)
        ]
        normalized = {
            "executive_summary": rendered_lane("executive_summary"),
            "experience": " ".join(experience_parts).strip(),
            "skills": rendered_lane("competencies"),
        }
        return {key: value for key, value in normalized.items() if value}
    executive_summary = _stringify_section(
        sections.get("executive_summary")
        or sections.get("summary")
        or generated_resume.get("executive_summary")
        or generated_resume.get("summary")
    )
    experience = _stringify_section(sections.get("experience") or generated_resume.get("experience"))
    skills = _stringify_section(sections.get("skills") or generated_resume.get("skills"))
    normalized = {
        "executive_summary": executive_summary,
        "experience": experience,
        "skills": skills,
    }
    return {key: value for key, value in normalized.items() if value}


def _collect_source_claims(value: Any) -> list[tuple[str, str]]:
    claims: list[tuple[str, str]] = []
    if isinstance(value, Mapping):
        refs: list[str] = []
        for key in _SOURCE_ID_KEYS:
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                refs.append(raw.strip())
        for key in _SOURCE_IDS_KEYS:
            raw = value.get(key)
            if isinstance(raw, list):
                refs.extend(str(item).strip() for item in raw if str(item).strip())
        expected_digest = next(
            (_as_text(value.get(key)) for key in _SOURCE_DIGEST_KEYS if _as_text(value.get(key))),
            "",
        )
        claims.extend((ref, expected_digest) for ref in refs)
        skipped = _SOURCE_ID_KEYS | _SOURCE_IDS_KEYS | frozenset(_SOURCE_DIGEST_KEYS)
        for key, child in value.items():
            if key not in skipped:
                claims.extend(_collect_source_claims(child))
    elif isinstance(value, list):
        for child in value:
            claims.extend(_collect_source_claims(child))
    return claims


def _claims_from_resume(
    generated_resume: dict[str, Any],
    *,
    artifact_dir: Path,
    source_manifest: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_lane_claims = _claims_from_current_lane_ledgers(
        generated_resume,
        artifact_dir=artifact_dir,
        source_manifest=source_manifest,
    )
    if current_lane_claims is not None:
        return current_lane_claims
    manifest_by_ref = {str(row.get("artifact_ref") or ""): row for row in source_manifest}
    expected_by_ref: dict[str, set[str]] = {}
    for ref, expected_digest in _collect_source_claims(generated_resume):
        expected_by_ref.setdefault(ref, set()).add(expected_digest)

    claims: list[dict[str, Any]] = []
    for idx, (ref, declared_digests) in enumerate(sorted(expected_by_ref.items())):
        path = _contained_source_path(ref, artifact_dir)
        rel = ""
        if path is not None:
            try:
                rel = path.relative_to(artifact_dir.resolve()).as_posix()
            except ValueError:
                rel = ""
        manifest_row = manifest_by_ref.get(rel, {})
        observed_digest = _as_text(manifest_row.get("sha256"))
        normalized_declared = {
            digest.removeprefix("sha256:") for digest in declared_digests if digest
        }
        normalized_expected = (
            next(iter(normalized_declared)) if len(normalized_declared) == 1 else ""
        )
        expected_valid = bool(
            len(normalized_expected) == 64
            and normalized_expected == normalized_expected.lower()
            and all(char in "0123456789abcdef" for char in normalized_expected)
        )
        digest_matches = bool(
            expected_valid
            and observed_digest
            and normalized_expected == observed_digest
        )
        supported = bool(rel and manifest_row and digest_matches)
        if not rel or not manifest_row:
            resolution_status = "UNRESOLVED_OR_OUTSIDE_SOURCE_ROOT"
        elif not normalized_declared:
            resolution_status = "EXPECTED_DIGEST_MISSING"
        elif len(normalized_declared) != 1:
            resolution_status = "EXPECTED_DIGEST_CONFLICT"
        elif not expected_valid:
            resolution_status = "EXPECTED_DIGEST_INVALID"
        elif not digest_matches:
            resolution_status = "DIGEST_MISMATCH"
        else:
            resolution_status = "RESOLVED_BYTE_BOUND"
        claims.append(
            {
                "id": f"apps_rg_live_claim_{idx + 1}",
                "source_ids": [ref],
                "supported": supported,
                "text": ref,
                "source_resolution_status": resolution_status,
                "evidence_ref": rel,
                "evidence_digest": observed_digest,
                "expected_evidence_digest": normalized_expected,
                "containment_verified": bool(rel and manifest_row),
                "digest_verified": supported,
            }
        )
    return claims


def _claims_from_current_lane_ledgers(
    generated_resume: dict[str, Any],
    *,
    artifact_dir: Path,
    source_manifest: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Byte-bind assembled resume bullets to their sealed lane claim ledgers.

    The public resume intentionally carries graph fact IDs such as
    ``bul_unify_001`` rather than filesystem paths.  Treating those IDs as
    paths makes every real assembled bullet appear ungrounded.  In a current
    Apps RG run, the lane's sealed claim ledger is the authoritative bridge
    from that ID to the permitted evidence.  This function verifies that
    bridge without modifying the product run.
    """

    lanes_root = artifact_dir / "lanes"
    if not lanes_root.is_dir():
        return None

    manifest_by_ref = {
        str(row.get("artifact_ref") or ""): row
        for row in source_manifest
        if row.get("artifact_ref")
    }
    source_to_ledger: dict[str, tuple[str, str, str, list[str]]] = {}
    for lane_dir in sorted(path for path in lanes_root.iterdir() if path.is_dir()):
        ledger_path = lane_dir / "claim_ledger.json"
        ledger_rel = ledger_path.relative_to(artifact_dir).as_posix()
        ledger_row = manifest_by_ref.get(ledger_rel)
        if not isinstance(ledger_row, Mapping):
            continue
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        rows = ledger.get("claims") if isinstance(ledger, Mapping) else ledger
        if not isinstance(rows, list):
            continue
        digest = _as_text(ledger_row.get("sha256"))
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            claim_text = _as_text(row.get("claim_text") or row.get("text"))
            source_fact_ids = [
                _as_text(value)
                for value in row.get("source_fact_ids", [])
                if _as_text(value)
            ]
            for source_id in source_fact_ids:
                # Source IDs are globally unique in the sealed resume graph.
                # Do not overwrite an earlier binding if malformed evidence
                # reuses one: the first byte-bound ledger remains the only
                # candidate and text containment below still fails closed.
                source_to_ledger.setdefault(
                    source_id,
                    (ledger_rel, digest, claim_text, source_fact_ids),
                )

    # Locked sections never pass through a generated lane.  Their provenance
    # is the byte-for-byte locked-copy manifest, which is equally sealed and
    # must be considered before declaring a preserved bullet unsupported.
    locked_path = artifact_dir / "modular_r4" / "locked_copy" / "locked_copy_manifest.json"
    locked_rel = locked_path.relative_to(artifact_dir).as_posix()
    locked_row = manifest_by_ref.get(locked_rel)
    if isinstance(locked_row, Mapping):
        locked = _json_object(locked_path)
        sections = locked.get("sections") if isinstance(locked.get("sections"), list) else []
        locked_digest = _as_text(locked_row.get("sha256"))
        for section in sections:
            if not isinstance(section, Mapping):
                continue
            try:
                copied = json.loads(_as_text(section.get("copied_text")))
            except json.JSONDecodeError:
                continue
            bullets = copied.get("bullets") if isinstance(copied, Mapping) else []
            if not isinstance(bullets, list):
                continue
            source_fact_ids = [
                _as_text(value)
                for value in section.get("source_fact_ids", [])
                if _as_text(value)
            ]
            for bullet in bullets:
                if not isinstance(bullet, Mapping):
                    continue
                source_id = _as_text(bullet.get("bullet_id"))
                claim_text = _as_text(bullet.get("text"))
                if source_id:
                    source_to_ledger.setdefault(
                        source_id,
                        (locked_rel, locked_digest, claim_text, source_fact_ids),
                    )

    raw_sections = generated_resume.get("sections")
    sections = raw_sections if isinstance(raw_sections, Mapping) else {}
    experience = sections.get("experience") or generated_resume.get("experience")
    experience_rows = experience if isinstance(experience, list) else []
    resume_bullets: dict[str, str] = {}
    for role in experience_rows:
        if not isinstance(role, Mapping):
            continue
        bullets = role.get("bullets")
        if not isinstance(bullets, list):
            continue
        for bullet in bullets:
            if not isinstance(bullet, Mapping):
                continue
            source_id = _as_text(bullet.get("source_id"))
            text = _as_text(bullet.get("text") or bullet.get("bullet"))
            if source_id:
                resume_bullets.setdefault(source_id, text)

    if not resume_bullets:
        return []
    claims: list[dict[str, Any]] = []
    for idx, (source_id, text) in enumerate(sorted(resume_bullets.items()), start=1):
        binding = source_to_ledger.get(source_id)
        if binding is None:
            claims.append(
                {
                    "id": f"apps_rg_live_claim_{idx}",
                    "source_ids": [source_id],
                    "source_fact_ids": [source_id],
                    "supported": False,
                    "text": text or source_id,
                    "source_resolution_status": "SEALED_LANE_LEDGER_BINDING_MISSING",
                    "evidence_ref": "",
                    "evidence_digest": "",
                    "expected_evidence_digest": "",
                    "containment_verified": False,
                    "digest_verified": False,
                }
            )
            continue
        ledger_ref, digest, claim_text, source_fact_ids = binding
        text_matches = " ".join(text.split()) == " ".join(claim_text.split())
        digest_valid = len(digest) == 64 and digest == digest.lower()
        supported = bool(text_matches and digest_valid)
        claims.append(
            {
                "id": f"apps_rg_live_claim_{idx}",
                "source_ids": [ledger_ref],
                "source_fact_ids": source_fact_ids,
                "supported": supported,
                "text": text or source_id,
                "source_resolution_status": (
                    "RESOLVED_BYTE_BOUND"
                    if supported
                    else "SEALED_LANE_LEDGER_TEXT_OR_DIGEST_MISMATCH"
                ),
                "evidence_ref": ledger_ref,
                "evidence_digest": digest,
                "expected_evidence_digest": digest,
                "containment_verified": text_matches,
                "digest_verified": digest_valid,
            }
        )
    return claims


def _artifact_names(artifact_dir: Path) -> list[str]:
    names: set[str] = set()
    if any(
        path is not None and path.is_file()
        for path in (
            _contained_source_path("outputs/resume.md", artifact_dir),
            _contained_source_path("resume.md", artifact_dir),
        )
    ):
        names.add("resume.md")
    if _generated_resume_path(artifact_dir) is not None:
        names.add("generated_resume.json")
        names.add("final_resume.json")
    final_json = _contained_source_path("FINAL_RESUME_OUTPUT.json", artifact_dir)
    if final_json is not None and final_json.is_file():
        names.add("FINAL_RESUME_OUTPUT.json")
    final_text = _contained_source_path("FINAL_RESUME_OUTPUT.txt", artifact_dir)
    if final_text is not None and final_text.is_file():
        names.add("FINAL_RESUME_OUTPUT.txt")
    docx = _contained_source_path("outputs/resume.docx", artifact_dir)
    if docx is not None and docx.is_file():
        names.add("resume.docx")
    return sorted(names)


def _artifact_index_entry(
    ref: str,
    artifact_dir: Path,
    manifest_by_ref: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    path = _contained_source_path(ref, artifact_dir)
    if path is None or not path.is_file():
        return {}
    rel = path.relative_to(artifact_dir.resolve()).as_posix()
    manifest_row = manifest_by_ref.get(rel) or manifest_by_ref.get(rel.replace("/", "\\"))
    if not isinstance(manifest_row, Mapping):
        return {}
    observed_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed_digest != _as_text(manifest_row.get("sha256")):
        return {}
    payload = _json_object(path) if path.suffix.lower() == ".json" else {}
    return {
        "artifact_ref": path.as_posix(),
        "evidence_ref": rel,
        "evidence_digest": observed_digest,
        "byte_length": int(manifest_row.get("byte_length") or 0),
        "payload": payload,
    }


def _lane_artifact_index(
    artifact_dir: Path,
    source_manifest: list[dict[str, Any]],
    source_identity: Mapping[str, str],
    candidate_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    # ``lanes`` is the public whole-resume layout.  ``modular_r4`` remains a
    # compatibility reader for historical proof bundles only.
    sections_root = artifact_dir / "lanes"
    if not sections_root.is_dir():
        sections_root = artifact_dir / "modular_r4" / "sections"
    if not sections_root.is_dir():
        return {}
    manifest_by_ref = {
        str(row.get("artifact_ref") or "").replace("\\", "/"): row
        for row in source_manifest
        if row.get("artifact_ref")
    }
    candidate_bindings = (
        candidate_manifest.get("artifact_bindings")
        if isinstance(candidate_manifest, Mapping)
        else []
    )
    # A historical run may have no v2 frozen-input manifest.  The current
    # run path validates a candidate manifest before indexing it; compatibility
    # readers simply have no candidate bindings in that case.
    candidate_bindings = (
        candidate_bindings if isinstance(candidate_bindings, list) else []
    )
    candidate_by_key: dict[tuple[str, str], Mapping[str, Any]] = {
        (str(row.get("lane_id") or ""), str(row.get("role") or "")): row
        for row in candidate_bindings
        if isinstance(row, Mapping)
        and str(row.get("lane_id") or "")
        and str(row.get("role") or "")
        and row.get("missing") is not True
    }
    index: dict[str, Any] = {}
    for lane_dir in sorted(path for path in sections_root.iterdir() if path.is_dir()):
        lane_identity = next(
            (
                {
                    key: _as_text(row["identity"].get(key))
                    for key in _IDENTITY_KEYS
                }
                for (lane_id, _role), row in candidate_by_key.items()
                if lane_id == lane_dir.name
                and isinstance(row.get("identity"), Mapping)
                and all(_as_text(row["identity"].get(key)) for key in _IDENTITY_KEYS)
            ),
            {},
        )
        package_entry = _artifact_index_entry(
            (lane_dir / "l6_v40_shadow_eval_package.json").as_posix(),
            artifact_dir,
            manifest_by_ref,
        )
        closure_entry = _artifact_index_entry(
            (lane_dir / "l6_observability_closure_receipt.json").as_posix(),
            artifact_dir,
            manifest_by_ref,
        )
        package_payload = package_entry.get("payload")
        package_payload = (
            dict(package_payload) if isinstance(package_payload, Mapping) else {}
        )
        closure_payload = closure_entry.get("payload")
        closure_payload = (
            dict(closure_payload) if isinstance(closure_payload, Mapping) else {}
        )
        package_identity = {
            key: _as_text(package_payload.get(key)) for key in _IDENTITY_KEYS
        }
        lane_identity_valid = bool(
            package_payload.get("section_id") == lane_dir.name
            and all(package_identity.values())
            and package_identity["parent_run_id"]
            == _as_text(source_identity.get("parent_run_id"))
            and closure_payload.get("observability_closure_status") == "PASS"
            and all(
                _as_text(closure_payload.get(key)) == value
                for key, value in package_identity.items()
            )
        )
        if lane_identity_valid and not lane_identity:
            lane_identity = package_identity
        if not lane_identity:
            for candidate_name in (
                "apps_rg_section_runtime_exhaust_bundle.json",
                "l6_shadow_eval_package.json",
            ):
                exhaust_entry = _artifact_index_entry(
                    (lane_dir / candidate_name).as_posix(),
                    artifact_dir,
                    manifest_by_ref,
                )
                exhaust_payload = exhaust_entry.get("payload")
                exhaust_payload = (
                    dict(exhaust_payload) if isinstance(exhaust_payload, Mapping) else {}
                )
                exhaust_identity = {
                    key: _as_text(exhaust_payload.get(key)) for key in _IDENTITY_KEYS
                }
                if (
                    exhaust_payload.get("section_id") == lane_dir.name
                    and all(exhaust_identity.values())
                    and (
                        not source_identity.get("parent_run_id")
                        or exhaust_identity["parent_run_id"]
                        == _as_text(source_identity.get("parent_run_id"))
                    )
                ):
                    lane_identity = exhaust_identity
                    break
        pointer = next(
            (
                contained
                for candidate in (
                    lane_dir / "latest_successful_real_run.json",
                    lane_dir / "latest_real_run.json",
                )
                if (contained := _contained_source_path(candidate, artifact_dir)) is not None
                and contained.is_file()
            ),
            None,
        )
        pointer_payload = _json_object(pointer) if pointer is not None else {}
        pointer_child_run_id = _find_identity_value(pointer_payload, "child_run_id")
        source_child_run_id = _as_text(source_identity.get("child_run_id"))
        pointer_identity_matches = bool(
            source_child_run_id and pointer_child_run_id == source_child_run_id
        )
        source_parent_run_id = _as_text(source_identity.get("parent_run_id"))
        if source_parent_run_id:
            pointer_identity_matches = pointer_identity_matches and (
                _find_identity_value(pointer_payload, "parent_run_id")
                == source_parent_run_id
            )
        links: dict[str, Any] = {}
        if pointer_identity_matches:
            for key in ("artifact_links", "artifact_links_compact"):
                raw_links = pointer_payload.get(key)
                if isinstance(raw_links, dict):
                    links.update(raw_links)
        for file_name, role in _LANE_ARTIFACT_ROLE_BY_NAME.items():
            candidate_binding = candidate_by_key.get((lane_dir.name, role), {})
            refs = [
                _as_text(candidate_binding.get("artifact_ref")),
                lane_dir / file_name,
                _as_text(links.get(file_name)),
            ]
            for ref in refs:
                if not _as_text(ref):
                    continue
                entry = _artifact_index_entry(_as_text(ref), artifact_dir, manifest_by_ref)
                if not entry and candidate_binding:
                    c_ref = _as_text(candidate_binding.get("artifact_ref"))
                    c_path = _contained_source_path(c_ref, artifact_dir)
                    if c_path and c_path.is_file():
                        c_digest = hashlib.sha256(c_path.read_bytes()).hexdigest()
                        if c_digest == _as_text(candidate_binding.get("sha256")):
                            entry = {
                                "artifact_ref": c_path.as_posix(),
                                "evidence_ref": c_path.relative_to(artifact_dir.resolve()).as_posix(),
                                "evidence_digest": c_digest,
                                "byte_length": int(candidate_binding.get("byte_length") or 0),
                                "payload": _json_object(c_path) if c_path.suffix.lower() == ".json" else {},
                            }
                if entry:
                    if lane_identity:
                        payload = entry.get("payload")
                        payload = dict(payload) if isinstance(payload, Mapping) else {}
                        payload["source_identity"] = dict(lane_identity)
                        entry["payload"] = payload
                    index[f"{lane_dir.name}:{role}"] = entry
                    break
    return index


def _preflight_status(payload: Mapping[str, Any]) -> str:
    inner = payload.get("payload") if isinstance(payload.get("payload"), Mapping) else payload
    return _as_text(inner.get("status") or inner.get("preflight_status")).lower()


def _verify_bound_artifact(
    root: Path,
    binding: Any,
    *,
    expected_ref: str = "",
) -> tuple[Path | None, bytes, list[str]]:
    errors: list[str] = []
    if not isinstance(binding, Mapping):
        return None, b"", ["binding_not_object"]
    ref = _as_text(binding.get("artifact_ref"))
    if not ref:
        errors.append("binding_ref_missing")
    if expected_ref and ref != expected_ref:
        errors.append("binding_ref_not_canonical")
    path = _contained_source_path(ref, root) if ref else None
    raw = b""
    if path is None:
        errors.append("binding_ref_outside_source_root")
    elif not path.is_file():
        errors.append("binding_artifact_missing")
    else:
        try:
            raw = path.read_bytes()
        except OSError:
            errors.append("binding_artifact_unreadable")
    declared_digest = _as_text(binding.get("sha256"))
    if not _is_prefixed_sha256(declared_digest):
        errors.append("binding_digest_invalid")
    elif raw and not hmac.compare_digest(declared_digest, _bytes_digest(raw)):
        errors.append("binding_digest_mismatch")
    try:
        declared_length = int(binding.get("byte_length"))
    except (TypeError, ValueError):
        declared_length = -1
    if raw and declared_length != len(raw):
        errors.append("binding_byte_length_mismatch")
    return path, raw, errors


def _canonical_product_identity_valid(identity: Mapping[str, Any]) -> bool:
    if any(not _as_text(identity.get(key)) for key in _CANONICAL_IDENTITY_KEYS):
        return False
    if identity.get("schema_version") != "apps_research_rg_run_identity.v1":
        return False
    if identity.get("consumer_app_id") != "apps_rg":
        return False
    return all(
        _is_prefixed_sha256(identity.get(key))
        for key in ("jd_sha256", "brief_sha256", "policy_hash", "blueprint_hash")
    )


def _verified_product_authorization(
    artifact_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], str, str, list[str]]:
    root = artifact_dir.resolve()
    path = _contained_source_path(_PRODUCT_AUTHORIZATION_RECEIPT, root)
    errors: list[str] = []
    if path is None or not path.is_file():
        return {}, {}, "", "", ["product_authorization_receipt_missing"]
    raw = path.read_bytes()
    payload = _json_object(path)
    if not payload:
        return {}, {}, path.name, _bytes_digest(raw), ["product_authorization_receipt_invalid"]
    if payload.get("schema_version") != "apps_rg.product_authorization_receipt.v1":
        errors.append("product_authorization_schema_mismatch")
    if payload.get("authority_contract_id") != "apps_research_rg_e2e_authority":
        errors.append("product_authorization_authority_mismatch")
    if not (
        payload.get("authorized") is True
        and payload.get("status") == "AUTHORIZED"
        and payload.get("boundary") == "UWG_COMMIT_CLOSED"
        and payload.get("immutable") is True
    ):
        errors.append("product_authorization_not_closed")
    identity = payload.get("identity")
    identity = dict(identity) if isinstance(identity, Mapping) else {}
    if not _canonical_product_identity_valid(identity):
        errors.append("product_authorization_identity_invalid")
    if payload.get("identity_sha256") != _payload_digest(identity):
        errors.append("product_authorization_identity_digest_mismatch")
    for label, binding in (
        ("decision", payload.get("decision_receipt")),
        ("output", payload.get("output_artifact")),
    ):
        _path, _raw, binding_errors = _verify_bound_artifact(root, binding)
        errors.extend(f"product_authorization_{label}_{error}" for error in binding_errors)
    return payload, identity, path.name, _bytes_digest(raw), errors


def _verified_preflight(
    artifact_dir: Path,
    supplied: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], str, str, list[str]]:
    """Verify the signed continuation, consume-once receipt, and product binding.

    A caller-supplied mapping may identify the canonical receipt but can never
    supply authority payload bytes.  All evidence is reopened beneath the
    completed product run root.
    """

    root = artifact_dir.resolve()
    errors: list[str] = []
    supplied_ref = _as_text((supplied or {}).get("preflight_ref"))
    if supplied_ref:
        supplied_path = _contained_source_path(supplied_ref, root)
        if supplied_path is None or supplied_path.name != _PREFLIGHT_PRODUCT_ENTRY_RECEIPT:
            errors.append("caller_preflight_ref_not_authoritative")
    entry_path = _contained_source_path(_PREFLIGHT_PRODUCT_ENTRY_RECEIPT, root)
    if entry_path is None or not entry_path.is_file():
        return {}, "", "", [*errors, "preflight_product_entry_receipt_missing"]
    entry_raw = entry_path.read_bytes()
    entry = _json_object(entry_path)
    if not entry:
        return {}, entry_path.name, _bytes_digest(entry_raw), [*errors, "preflight_product_entry_receipt_invalid"]
    if entry.get("schema_version") != "apps_rg.e2e_preflight_product_entry.v1":
        errors.append("preflight_product_entry_schema_mismatch")
    if entry.get("authority_contract_id") != "apps_research_rg_e2e_authority":
        errors.append("preflight_product_entry_authority_mismatch")
    if entry.get("status") != "PASS":
        errors.append("preflight_product_entry_not_passed")
    identity = entry.get("identity")
    identity = dict(identity) if isinstance(identity, Mapping) else {}
    if not _canonical_product_identity_valid(identity):
        errors.append("preflight_product_identity_invalid")
    if entry.get("identity_sha256") != _payload_digest(identity):
        errors.append("preflight_product_identity_digest_mismatch")

    continuation_path, continuation_raw, continuation_binding_errors = (
        _verify_bound_artifact(
            root,
            entry.get("signed_continuation"),
            expected_ref=_PREFLIGHT_CONTINUATION_RECEIPT,
        )
    )
    errors.extend(f"preflight_continuation_{error}" for error in continuation_binding_errors)
    consumption_path, consumption_raw, consumption_binding_errors = (
        _verify_bound_artifact(
            root,
            entry.get("consume_once_receipt"),
            expected_ref=_PREFLIGHT_CONSUMPTION_RECEIPT,
        )
    )
    errors.extend(f"preflight_consumption_{error}" for error in consumption_binding_errors)
    continuation = _json_object(continuation_path) if continuation_path is not None else {}
    consumption = _json_object(consumption_path) if consumption_path is not None else {}

    expected_key_id = _as_text(os.environ.get("APPS_RG_ROUTE_HMAC_KEY_ID"))
    continuation_key_id = _as_text(continuation.get("route_signing_key_id"))
    verifier_key, verifier_metadata, verifier_errors = _resolve_hmac_verifier_key(
        continuation_key_id
    )
    errors.extend(verifier_errors)
    continuation_body = {
        key: value
        for key, value in continuation.items()
        if key not in {"continuation_payload_digest", "continuation_signature"}
    }
    if continuation.get("schema_version") != "apps_rg.e2e_preflight.v1":
        errors.append("preflight_continuation_schema_mismatch")
    continuation_identity = continuation.get("identity")
    continuation_identity = (
        dict(continuation_identity)
        if isinstance(continuation_identity, Mapping)
        else {}
    )
    identity_profile = _as_text(continuation.get("identity_profile"))
    if not (
        continuation.get("status") == "PASS"
        and continuation.get("continuation_scope") == "APPS_RG_PRODUCT_ENTRY_ONCE"
        and continuation.get("signature_algorithm") == "HMAC-SHA256"
    ):
        errors.append("preflight_continuation_not_passed")
    if identity_profile == "apps_research_rg_run_identity.v1":
        if continuation.get("product_entry_eligible") is not True:
            errors.append("preflight_continuation_not_product_eligible")
        if continuation_identity != identity:
            errors.append("preflight_continuation_identity_mismatch")
    elif identity_profile == "legacy_e2e_run_only.v1":
        # Fresh preflight necessarily precedes delegated research, so the
        # producer child identity does not exist yet.  The immutable signed
        # continuation is therefore run-root scoped; the later product-entry
        # receipt supplies the canonical identity while byte-binding this
        # continuation and its consume-once receipt.
        expected_legacy_identity = {"e2e_run_id": root.name}
        if continuation.get("product_entry_eligible") is not False:
            errors.append("preflight_legacy_continuation_eligibility_invalid")
        if continuation_identity != expected_legacy_identity:
            errors.append("preflight_legacy_continuation_identity_mismatch")
        if _as_text(continuation.get("e2e_run_id")) != root.name:
            errors.append("preflight_legacy_continuation_run_id_mismatch")
    else:
        errors.append("preflight_continuation_identity_profile_invalid")
    if continuation.get("identity_sha256") != _payload_digest(continuation_identity):
        errors.append("preflight_continuation_identity_digest_mismatch")
    if continuation.get("artifact_dir") != str(root):
        errors.append("preflight_continuation_artifact_dir_mismatch")
    if continuation.get("artifact_dir_sha256") != _payload_digest(str(root)):
        errors.append("preflight_continuation_artifact_dir_digest_mismatch")
    if continuation.get("continuation_payload_digest") != _payload_digest(continuation_body):
        errors.append("preflight_continuation_payload_digest_mismatch")
    if verifier_key and not hmac.compare_digest(
        _as_text(continuation.get("continuation_signature")),
        _hmac_signature(verifier_key, continuation_body),
    ):
        errors.append("preflight_continuation_signature_invalid")
    if expected_key_id and continuation.get("route_signing_key_id") != expected_key_id:
        errors.append("preflight_continuation_key_id_mismatch")

    continuation_binding = entry.get("signed_continuation")
    continuation_binding = continuation_binding if isinstance(continuation_binding, Mapping) else {}
    if continuation_binding.get("payload_digest") != continuation.get("continuation_payload_digest"):
        errors.append("preflight_product_entry_payload_digest_mismatch")
    if continuation_binding.get("route_signing_key_id") != continuation.get("route_signing_key_id"):
        errors.append("preflight_product_entry_key_id_mismatch")

    consumption_body = {
        key: value for key, value in consumption.items() if key != "consumption_signature"
    }
    consumption_binding = entry.get("consume_once_receipt")
    consumption_binding = consumption_binding if isinstance(consumption_binding, Mapping) else {}
    if consumption.get("schema_version") != "apps_rg.e2e_preflight_consumption.v1":
        errors.append("preflight_consumption_schema_mismatch")
    if consumption.get("e2e_run_id") != continuation.get("e2e_run_id"):
        errors.append("preflight_consumption_run_id_mismatch")
    if consumption.get("continuation_ref") != _PREFLIGHT_CONTINUATION_RECEIPT:
        errors.append("preflight_consumption_continuation_ref_mismatch")
    if continuation_raw and consumption.get("continuation_sha256") != _bytes_digest(continuation_raw):
        errors.append("preflight_consumption_continuation_digest_mismatch")
    if consumption.get("continuation_payload_digest") != continuation.get("continuation_payload_digest"):
        errors.append("preflight_consumption_payload_digest_mismatch")
    if consumption.get("consumer_id") != consumption_binding.get("consumer_id"):
        errors.append("preflight_consumption_consumer_mismatch")
    if verifier_key and not hmac.compare_digest(
        _as_text(consumption.get("consumption_signature")),
        _hmac_signature(verifier_key, consumption_body),
    ):
        errors.append("preflight_consumption_signature_invalid")
    try:
        issued = _parse_utc(continuation.get("issued_at_utc"))
        expires = _parse_utc(continuation.get("expires_at_utc"))
        consumed = _parse_utc(consumption.get("consumed_at_utc"))
        if not issued <= consumed < expires:
            errors.append("preflight_consumption_outside_validity_window")
    except (TypeError, ValueError):
        errors.append("preflight_timestamp_invalid")

    verified_entry = dict(entry)
    verified_entry["_apps_eval_verification"] = {
        **verifier_metadata,
        "status": _preflight_verification_status(errors),
    }
    return verified_entry, entry_path.name, _bytes_digest(entry_raw), errors


def _find_identity_values(value: Any, key: str) -> set[str]:
    if not isinstance(value, Mapping):
        return set()
    values: set[str] = set()
    direct = _as_text(value.get(key))
    if direct:
        values.add(direct)
    for wrapper in (
        "identity",
        "run_identity",
        "canonical_run_identity",
        "payload",
        "result",
        "runtime",
    ):
        nested = value.get(wrapper)
        values.update(_find_identity_values(nested, key))
    return values


def _find_identity_value(value: Any, key: str) -> str:
    values = _find_identity_values(value, key)
    return next(iter(values)) if len(values) == 1 else ""


def _source_identity(
    result: Mapping[str, Any],
    artifact_dir: Path,
    *,
    authoritative_identity: Mapping[str, Any],
) -> dict[str, str]:
    sources: list[tuple[str, Mapping[str, Any]]] = [("result", result)]
    for rel in _IDENTITY_ARTIFACTS:
        path = _contained_source_path(rel, artifact_dir)
        if path is not None and path.is_file():
            payload = _json_object(path)
            if payload:
                sources.append((rel, payload))
    identity: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    for key in _IDENTITY_KEYS:
        values = {
            candidate
            for _label, source in sources
            for candidate in _find_identity_values(source, key)
            if candidate
        }
        authority_value = _as_text(authoritative_identity.get(key))
        if authority_value:
            values.add(authority_value)
        if len(values) > 1:
            conflicts[key] = sorted(values)
        identity[key] = next(iter(values)) if len(values) == 1 else ""
    if conflicts:
        detail = ";".join(
            f"{key}={','.join(values)}" for key, values in sorted(conflicts.items())
        )
        raise ValueError(f"apps_rg_source_identity_conflict:{detail}")
    return identity


def _normalize_live_snapshot(
    *,
    scenario_id: str,
    result: dict[str, Any],
    artifact_dir: Path,
    preflight: dict[str, Any],
) -> AppOutputSnapshot:
    _bootstrap_apps_rg_env_for_live_replay()
    source_manifest_before = build_source_artifact_manifest(artifact_dir)
    source_digest_before = source_artifact_manifest_digest(source_manifest_before)
    candidate_manifest: dict[str, Any] = {}
    candidate_manifest_errors: list[str] = []
    candidate_manifest_ref = ""
    candidate_manifest_path = artifact_dir / "candidate_evaluation_manifest.v2.json"
    if candidate_manifest_path.is_file():
        from apps_rg.runtime.evaluation_manifest import (
            validate_candidate_evaluation_manifest,
        )

        candidate_manifest, candidate_manifest_errors = (
            validate_candidate_evaluation_manifest(artifact_dir)
        )
        candidate_manifest_ref = candidate_manifest_path.name
        if candidate_manifest_errors:
            raise ValueError(
                "apps_rg_candidate_evaluation_manifest_invalid:"
                + ",".join(candidate_manifest_errors)
            )
    (
        product_authorization,
        authoritative_identity,
        product_authorization_ref,
        product_authorization_digest,
        product_authorization_errors,
    ) = _verified_product_authorization(artifact_dir)
    verified_preflight, preflight_ref, preflight_digest, preflight_errors = (
        _verified_preflight(
            artifact_dir,
            preflight,
        )
    )
    preflight_verification = verified_preflight.get("_apps_eval_verification")
    preflight_verification = (
        dict(preflight_verification)
        if isinstance(preflight_verification, Mapping)
        else {}
    )
    preflight_identity = verified_preflight.get("identity")
    preflight_identity = (
        dict(preflight_identity) if isinstance(preflight_identity, Mapping) else {}
    )
    if authoritative_identity and preflight_identity != authoritative_identity:
        preflight_errors.append("preflight_product_authorization_identity_mismatch")
    preflight_verification_status = _preflight_verification_status(
        preflight_errors
    )
    resume_path = _generated_resume_path(artifact_dir)
    generated_resume = _json_object(resume_path) if resume_path is not None else {}
    sections = _normalize_sections(generated_resume) if generated_resume else {}
    claims = _claims_from_resume(
        generated_resume,
        artifact_dir=artifact_dir,
        source_manifest=source_manifest_before,
    )
    evidence_refs = sorted({ref for claim in claims for ref in claim.get("source_ids", [])})
    identity = _source_identity(
        result,
        artifact_dir,
        authoritative_identity=authoritative_identity,
    )
    if candidate_manifest:
        candidate_identity = candidate_manifest.get("product_identity")
        candidate_identity = (
            dict(candidate_identity)
            if isinstance(candidate_identity, Mapping)
            else {}
        )
        identity["parent_run_id"] = _as_text(candidate_identity.get("parent_run_id"))
        identity["child_run_id"] = _as_text(candidate_identity.get("child_run_id"))
        identity["section_attempt_id"] = (
            f"whole_resume:{identity['child_run_id']}" if identity["child_run_id"] else ""
        )
        identity["runtime_exhaust_bundle_id"] = _as_text(
            candidate_identity.get("runtime_exhaust_bundle_id")
        )
    artifact_index = _lane_artifact_index(
        artifact_dir,
        source_manifest_before,
        identity,
        candidate_manifest,
    )
    # Use the frozen manifest for whole-run roles too.  Without this index the
    # resolver follows compatibility-order paths (for example an old generated
    # resume rather than the final assembly), so L6 cannot reproduce the
    # scorecard's declared source bytes.
    candidate_bindings = candidate_manifest.get("artifact_bindings", [])
    candidate_bindings = (
        candidate_bindings if isinstance(candidate_bindings, list) else []
    )
    manifest_by_ref = {
        str(row.get("artifact_ref") or ""): row
        for row in source_manifest_before
        if row.get("artifact_ref")
    }
    for binding in candidate_bindings:
        if not isinstance(binding, Mapping) or binding.get("missing") is True:
            continue
        if str(binding.get("lane_id") or ""):
            continue
        role = str(binding.get("role") or "")
        entry = _artifact_index_entry(
            str(binding.get("artifact_ref") or ""),
            artifact_dir,
            manifest_by_ref,
        )
        if not role or not entry:
            continue
        payload = entry.get("payload")
        payload = dict(payload) if isinstance(payload, Mapping) else {}
        binding_identity = binding.get("identity")
        if isinstance(binding_identity, Mapping):
            payload["source_identity"] = {
                key: _as_text(binding_identity.get(key))
                for key in _IDENTITY_KEYS
            }
        entry["payload"] = payload
        artifact_index[role] = entry
    output: dict[str, Any] = {
        "runtime": {
            "exit_status": _as_text(result.get("exit_status")),
            "execution_status": _as_text(result.get("execution_status")),
            "outcome_authorized": bool(result.get("outcome_authorized", False)),
            "fault": _as_text(result.get("fault")),
        }
    }
    if sections:
        output["sections"] = sections
    source_manifest_after = build_source_artifact_manifest(artifact_dir)
    source_digest_after = source_artifact_manifest_digest(source_manifest_after)
    if source_digest_after != source_digest_before:
        raise RuntimeError("source_run_mutated_during_apps_eval_normalization")
    return AppOutputSnapshot(
        app_id="apps_rg",
        scenario_id=scenario_id,
        x3_disposition=_result_x3(result, artifact_dir),
        output=output,
        claims=claims,
        artifacts=_artifact_names(artifact_dir),
        provenance={
            "entrypoint": "apps_rg.runtime.entry.apps_rg_dispatch:dispatch_apps_rg_run",
            "preflight": _preflight_status(verified_preflight) or "unknown",
            "preflight_verified": preflight_verification_status == "VERIFIED"
            and not preflight_errors,
            "preflight_verification_status": preflight_verification_status,
            "preflight_verification_errors": sorted(set(preflight_errors)),
            "preflight_verifier_key_id": _as_text(
                preflight_verification.get("key_id")
            ),
            "preflight_verifier_key_source": _as_text(
                preflight_verification.get("key_source")
            ),
            "preflight_verifier_material_ref": _as_text(
                preflight_verification.get("verifier_material_ref")
            ),
            "preflight_verifier_material_sha256": _as_text(
                preflight_verification.get("verifier_material_sha256")
            ),
            "preflight_ref": preflight_ref,
            "preflight_digest": preflight_digest,
            "source_seal_verified": not product_authorization_errors,
            "source_seal_verification_errors": sorted(
                set(product_authorization_errors)
            ),
            "product_authorization_ref": product_authorization_ref,
            "product_authorization_digest": product_authorization_digest,
            "product_authorized": product_authorization.get("authorized") is True,
            "generated_resume_ref": (
                resume_path.relative_to(artifact_dir.resolve()).as_posix()
                if resume_path
                else ""
            ),
            "evidence_refs": evidence_refs,
            "supported_evidence_refs": sorted(
                ref
                for claim in claims
                if claim.get("supported") is True
                for ref in claim.get("source_ids", [])
            ),
            "unresolved_evidence_refs": sorted(
                ref
                for claim in claims
                if claim.get("supported") is not True
                for ref in claim.get("source_ids", [])
            ),
            "lane_artifact_index_count": len(artifact_index),
            "candidate_evaluation_manifest_ref": candidate_manifest_ref,
            "candidate_evaluation_manifest_sha256": _as_text(
                candidate_manifest.get("manifest_sha256")
            ),
            "resolved_inputs": verified_preflight.get("resolved_inputs", {}),
            "source_digest_before": source_digest_before,
            "source_digest_after": source_digest_after,
            "source_unchanged": True,
        },
        side_effects={"product_state_mutated": False, "writes": []},
        run_root=str(artifact_dir),
        artifact_index=artifact_index,
        raw_artifact_refs=[str(row["artifact_ref"]) for row in source_manifest_before],
        parent_run_id=identity["parent_run_id"],
        child_run_id=identity["child_run_id"],
        section_attempt_id=identity["section_attempt_id"],
        runtime_exhaust_bundle_id=identity["runtime_exhaust_bundle_id"],
        snapshot_digest=source_digest_before,
        source_artifact_manifest=source_manifest_before,
    )


def normalize_existing_apps_rg_run_snapshot(
    *,
    scenario_id: str,
    result: dict[str, Any],
    artifact_dir: Path,
    preflight: dict[str, Any] | None = None,
) -> AppOutputSnapshot:
    """Normalize an already-produced apps_rg run for current-run evaluation."""
    return _normalize_live_snapshot(
        scenario_id=scenario_id,
        result=result,
        artifact_dir=artifact_dir,
        preflight=preflight or {},
    )


def run_apps_rg_live(scenario_id: str, payload: dict[str, Any], artifact_dir: Path) -> AppOutputSnapshot:
    """Normalize a sealed existing run without invoking or mutating Apps RG.

    ``artifact_dir`` is the product run root.  The optional ``existing_run_result``
    mapping carries non-authoritative display metadata only; authorization, Exit,
    identity, and preflight evidence are always reopened from bound receipts.
    """

    root = Path(artifact_dir).resolve()
    if not root.is_dir():
        raise ValueError("apps_rg live evaluation requires an existing product run root")
    supplied_result = payload.get("existing_run_result")
    result = dict(supplied_result) if isinstance(supplied_result, Mapping) else {}
    supplied_preflight = {
        "preflight_ref": _as_text(payload.get("preflight_ref"))
    }
    snapshot = _normalize_live_snapshot(
        scenario_id=scenario_id,
        result=result,
        artifact_dir=root,
        preflight=supplied_preflight,
    )
    if snapshot.provenance.get("source_seal_verified") is not True:
        raise ValueError("apps_rg existing run product authorization seal is invalid")
    if snapshot.provenance.get("preflight_verified") is not True:
        raise ValueError("apps_rg existing run signed preflight evidence is invalid")
    return snapshot


def normalize_anthropic_deterministic_fixture_snapshot(
    *,
    scenario_id: str,
    artifact_dir: Path,
) -> AppOutputSnapshot:
    """Normalize only the explicit test-fixture boundary into an Eval snapshot.

    This path is intentionally separate from ``run_apps_rg_live``: it rejects
    product authority and records that L2 was replaced before any provider work
    could occur.
    """

    from apps_rg.evals.anthropic_deterministic_fixture import (
        FIXTURE_EVAL_PROFILE_ID,
        FIXTURE_EVIDENCE_CLASS,
        FIXTURE_HANDOFF_FILENAME,
        FIXTURE_L2_OUTPUT_FILENAME,
        FIXTURE_RUN_RECEIPT_FILENAME,
        TEST_HARNESS_ENV,
    )

    if str(os.environ.get(TEST_HARNESS_ENV) or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise PermissionError("deterministic fixture normalization requires APPS_RG_TEST_HARNESS")
    root = Path(artifact_dir).resolve()
    if not root.is_dir():
        raise ValueError("deterministic fixture run root is missing")
    manifest = _json_object(root / FIXTURE_HANDOFF_FILENAME)
    l2_output = _json_object(root / FIXTURE_L2_OUTPUT_FILENAME)
    receipt = _json_object(root / FIXTURE_RUN_RECEIPT_FILENAME)
    expected_no_provider = {
        "evidence_class": FIXTURE_EVIDENCE_CLASS,
        "fixture_policy_id": FIXTURE_EVAL_PROFILE_ID,
        "product_eligible": False,
        "provider_call_attempted": False,
        "network_call_attempted": False,
    }
    for label, payload in (
        ("fixture_handoff", manifest),
        ("fixture_l2_output", l2_output),
        ("fixture_run_receipt", receipt),
    ):
        if not payload:
            raise ValueError(f"deterministic fixture {label} is missing or unreadable")
        mismatches = {
            key: payload.get(key)
            for key, expected in expected_no_provider.items()
            if payload.get(key) != expected
        }
        if mismatches:
            raise ValueError(f"deterministic fixture {label} provenance mismatch: {sorted(mismatches)}")
    if receipt.get("l2_external_seam_replaced") is not True:
        raise ValueError("deterministic fixture receipt does not declare the L2 seam replacement")
    source_identity = manifest.get("identity")
    fixture_identity = receipt.get("identity")
    source_identity = dict(source_identity) if isinstance(source_identity, Mapping) else {}
    fixture_identity = dict(fixture_identity) if isinstance(fixture_identity, Mapping) else {}
    for key in ("parent_run_id", "child_run_id"):
        if not str(source_identity.get(key) or "").strip() or source_identity.get(key) != fixture_identity.get(key):
            raise ValueError(f"deterministic fixture identity mismatch: {key}")
    for key in ("section_attempt_id", "runtime_exhaust_bundle_id"):
        if not str(fixture_identity.get(key) or "").strip():
            raise ValueError(f"deterministic fixture identity is missing {key}")

    source_manifest_before = build_source_artifact_manifest(root)
    manifest_by_ref = {
        str(row.get("artifact_ref") or ""): row
        for row in source_manifest_before
        if row.get("artifact_ref")
    }
    artifact_index: dict[str, Any] = {}
    for role, ref in (
        ("fixture_handoff", FIXTURE_HANDOFF_FILENAME),
        ("fixture_u0_receipt", "u0_receipt.json"),
        ("fixture_l1_plan", "l1_plan_contract.json"),
        ("fixture_l0_route", "route_contract.json"),
        ("fixture_l2_output", FIXTURE_L2_OUTPUT_FILENAME),
    ):
        entry = _artifact_index_entry(ref, root, manifest_by_ref)
        if not entry:
            raise ValueError(f"deterministic fixture required artifact is absent or unbound: {role}")
        artifact_index[role] = entry
    generated_resume = _json_object(root / "outputs" / "generated_resume.json")
    sections = _normalize_sections(generated_resume)
    if set(sections) != {"executive_summary", "experience", "skills"}:
        raise ValueError("deterministic fixture generated-resume sections are incomplete")
    source_manifest_after = build_source_artifact_manifest(root)
    source_digest = source_artifact_manifest_digest(source_manifest_before)
    if source_artifact_manifest_digest(source_manifest_after) != source_digest:
        raise RuntimeError("fixture_source_mutated_during_snapshot_normalization")
    return AppOutputSnapshot(
        app_id="apps_rg",
        scenario_id=scenario_id,
        x3_disposition="TEST_FIXTURE_ONLY",
        output={
            "runtime": {
                "fixture_only": True,
                "product_authorized": False,
                "provider_call_attempted": False,
                "network_call_attempted": False,
            },
            "sections": sections,
        },
        claims=[
            {
                "id": "anthropic_fixture_boundary_claim",
                "source_ids": ["fixture:anthropic-partnership"],
                "supported": True,
                "text": "Deterministic fixture boundary only",
            }
        ],
        artifacts=_artifact_names(root),
        provenance={
            **expected_no_provider,
            "fixture_only": True,
            "evidence_refs": ["fixture:anthropic-partnership"],
            "source_unchanged": True,
            "source_digest_before": source_digest,
            "source_digest_after": source_digest,
            "l2_external_seam_replaced": True,
        },
        side_effects={"product_state_mutated": False, "writes": []},
        run_root=str(root),
        artifact_index=artifact_index,
        raw_artifact_refs=[str(row["artifact_ref"]) for row in source_manifest_before],
        parent_run_id=str(fixture_identity["parent_run_id"]),
        child_run_id=str(fixture_identity["child_run_id"]),
        section_attempt_id=str(fixture_identity["section_attempt_id"]),
        runtime_exhaust_bundle_id=str(fixture_identity["runtime_exhaust_bundle_id"]),
        contract_profile_id=FIXTURE_EVAL_PROFILE_ID,
        snapshot_digest=source_digest,
        source_artifact_manifest=source_manifest_before,
    )


__all__ = [
    "build_source_artifact_manifest",
    "normalize_anthropic_deterministic_fixture_snapshot",
    "normalize_existing_apps_rg_run_snapshot",
    "run_apps_rg_live",
    "source_artifact_manifest_digest",
]
