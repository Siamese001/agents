"""W7.1 — patch-run mode: re-dispatch ONLY failed lanes of an existing integrated run.

Convergence problem this solves: a full 11-lane re-roll is a casino — independent
per-roll variance means previously-green lanes can fail on the next attempt. Patch-run
makes convergence monotone: lanes that already hold an accepted REAL_LLM + X3-allow
bundle stay banked; only non-authorized lanes are re-dispatched into the SAME run dir
(new timestamped lane dir, exactly like the integrated full run), then the same
app-side aggregation chain re-runs (rollup → locked copy → final assembly → rg_output
merge → artifact gate → recipe policy → integrated lane evidence refresh).

Honest boundary (spine law): apps_rg never emits root X3. The original run's root
``x3_disposition_receipt.json`` / ``r4_run_manifest.json`` / ``terminal_ret_packet.json``
remain the historical Exit record of the failed integrated dispatch. Post-patch product
authorization is expressed through per-lane X3 dispositions, the refreshed
``integrated_lane_evidence_status.json``, and the full-success eligibility evaluation
recorded in ``patch_run_receipt.json``.

CLI:
    python -m apps_rg --patch-run <existing_run_dir> [--sections <csv>]
                      [--force-lanes <csv>] [--dry-run]

Targeting inputs are re-derived from the run dir's persisted artifacts
(``ingress_raw.json`` + per-lane ``run_manifest.json`` command + per-lane
``validated_request.json`` app_payload). Never re-asks interactively; refuses with a
clear error (exit 2) when inputs cannot be derived.
"""
from __future__ import annotations

import concurrent.futures
import json
import hashlib
import os
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from apps_rg.repository_layout import resolve_repository_path
from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
from apps_rg.runtime.runtime_proof_layout import (
    MODULAR_R4_SECTIONS_ROOT_ENV,
    find_repo_root,
)

PATCH_RUN_RECEIPT_ARTIFACT = "patch_run_receipt.json"
PATCH_RUN_PREFLIGHT_ARTIFACT = "patch_run_preflight_receipt.json"
_WHOLE_RUN_ENVELOPE_ENV = "APPS_RG_WHOLE_RUN_ENVELOPE"
_CORRELATED_CLI_RUN_ENV = "APPS_RG_CORRELATED_CLI_RUN"

DEFAULT_PATCH_LANE_TIMEOUT_SECONDS = 360.0
DEFAULT_PATCH_RUN_TIMEOUT_SECONDS = 1200.0


def resolve_patch_lane_timeout_s(override: float | None = None) -> float:
    if override is not None and override > 0:
        return float(override)
    raw = os.environ.get("APPS_RG_PATCH_LANE_TIMEOUT_SECONDS", "").strip()
    if raw:
        try:
            val = float(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return DEFAULT_PATCH_LANE_TIMEOUT_SECONDS


def resolve_patch_run_timeout_s(override: float | None = None) -> float:
    if override is not None and override > 0:
        return float(override)
    raw = os.environ.get("APPS_RG_PATCH_RUN_TIMEOUT_SECONDS", "").strip()
    if raw:
        try:
            val = float(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return DEFAULT_PATCH_RUN_TIMEOUT_SECONDS


def _resolve_sections_root(run_dir: Path | str) -> Path:
    rd = Path(str(run_dir)).resolve()
    modular_root = rd / "modular_r4" / "sections"
    lanes_root = rd / "lanes"
    if (lanes_root / "sections_root_manifest.json").is_file() and not (
        modular_root / "sections_root_manifest.json"
    ).is_file():
        return lanes_root
    if lanes_root.is_dir() and any(lanes_root.glob("*/latest_*.json")) and not any(modular_root.glob("*/latest_*.json")):
        return lanes_root
    if modular_root.is_dir():
        return modular_root
    return lanes_root if lanes_root.is_dir() else modular_root


def _whole_resume_graph_env_for_patch(run_dir: Path) -> dict[str, str]:
    """Restore the immutable whole-run graph allocation for patch lanes.

    The integrated runner freezes section source plans before dispatch and
    exposes them through process-local environment variables. A later
    ``--patch-run`` is a new process, so those variables no longer exist even
    though their governed artifacts remain in the run bundle. Falling back to
    fresh section selection can choose different roots and makes the patched
    lane disagree with the original allocation. Rebind the persisted bundle;
    if a bundle exists only partially, fail closed instead of mixing frozen and
    reselected authority.
    """

    from apps_rg.runtime.c0.graph_skill_embedding_allocation import (
        GRAPH_SKILL_EMBEDDING_ALLOWLISTS_ENV,
    )
    from apps_rg.runtime.c0.resume_graph_allocation import (
        ALLOCATION_PLAN_ENV,
        ALLOCATION_USAGE_LEDGER_ENV,
        SECTION_EVIDENCE_CONTRACTS_ENV,
        SECTION_SOURCE_PLANS_ENV,
        load_resume_graph_allocation_plan,
    )

    allocation_dir = run_dir / "modular_r4" / "resume_graph_allocation"
    required = {
        ALLOCATION_PLAN_ENV: allocation_dir / "resume_graph_allocation_plan.json",
        ALLOCATION_USAGE_LEDGER_ENV: allocation_dir / "resume_graph_usage_ledger.json",
        SECTION_EVIDENCE_CONTRACTS_ENV: (
            allocation_dir / "section_final_graph_evidence_contracts.json"
        ),
        SECTION_SOURCE_PLANS_ENV: allocation_dir / "c03_section_graph_plans.json",
    }
    present = {name: path for name, path in required.items() if path.is_file()}
    if not present:
        return {}
    missing = sorted(name for name in required if name not in present)
    if missing:
        raise PatchRunInputError(
            "patch-run whole-resume graph allocation bundle is incomplete; missing "
            + ", ".join(missing)
        )

    # Validate the digest-bound allocation and the JSON shape of every paired
    # authority artifact before any lane is dispatched.
    load_resume_graph_allocation_plan(required[ALLOCATION_PLAN_ENV])
    malformed = [
        path.name
        for name, path in required.items()
        if name != ALLOCATION_PLAN_ENV and _load_json(path) is None
    ]
    if malformed:
        raise PatchRunInputError(
            "patch-run whole-resume graph allocation artifacts are malformed: "
            + ", ".join(sorted(malformed))
        )

    bindings = {name: str(path.resolve()) for name, path in required.items()}
    embedding_allowlists = (
        run_dir
        / "modular_r4"
        / "graph_skill_embedding_allocation"
        / "lane_graph_skill_embedding_allowlists.json"
    )
    if embedding_allowlists.is_file():
        if _load_json(embedding_allowlists) is None:
            raise PatchRunInputError(
                "patch-run graph skill embedding allowlists artifact is malformed"
            )
        bindings[GRAPH_SKILL_EMBEDDING_ALLOWLISTS_ENV] = str(
            embedding_allowlists.resolve()
        )
    return bindings


def _whole_resume_graph_rollup_authority(
    *,
    repo: Path,
    run_dir: Path,
) -> dict[str, Any]:
    """Rehydrate persisted whole-run graph identity at the aggregation boundary.

    Restoring process environment is sufficient for re-dispatched lanes, but the
    final W7 reconciliation reads the generated rollup. A patch aggregation must
    therefore carry the same frozen plan digest and artifact references that the
    original full-run aggregator emits. This restores graph identity only; it
    does not create delivery authorization.
    """
    from apps_rg.runtime.c0.resume_graph_allocation import (
        ALLOCATION_PLAN_ENV,
        ALLOCATION_USAGE_LEDGER_ENV,
        SECTION_EVIDENCE_CONTRACTS_ENV,
        SECTION_SOURCE_PLANS_ENV,
    )

    bindings = _whole_resume_graph_env_for_patch(run_dir)
    if not bindings:
        return {}
    plan = _load_json(Path(bindings[ALLOCATION_PLAN_ENV]))
    if not isinstance(plan, dict):
        raise PatchRunInputError("patch-run allocation plan became unreadable")
    digest = str(plan.get("allocation_plan_digest") or "").strip()
    if not digest:
        raise PatchRunInputError("patch-run allocation plan digest is missing")

    def _ref(env_name: str) -> str:
        path = Path(bindings[env_name]).resolve()
        try:
            return path.relative_to(repo.resolve()).as_posix()
        except ValueError:
            return str(path)

    authority: dict[str, Any] = {
        "resume_graph_allocation_plan_digest": digest,
        "resume_graph_allocation_refs": {
            "allocation_plan": _ref(ALLOCATION_PLAN_ENV),
            "usage_ledger": _ref(ALLOCATION_USAGE_LEDGER_ENV),
            "section_final_evidence_contracts": _ref(
                SECTION_EVIDENCE_CONTRACTS_ENV
            ),
            "section_plans": _ref(SECTION_SOURCE_PLANS_ENV),
        },
    }

    inventory = _load_json(run_dir / "modular_r4" / "phase1_lane_inventory.json") or {}
    for key in (
        "graph_skill_embeddings_required",
        "graph_skill_embedding_allowlists_digest",
        "graph_skill_embedding_runtime_refs",
    ):
        if key in inventory:
            authority[key] = inventory[key]

    return authority

# CLI flags whose values we re-derive from a persisted lane ``run_manifest.json`` command.
_COMMAND_FLAGS_OF_INTEREST = (
    "--jd",
    "--target-level",
    "--target-company",
    "--target-role",
    "--manual-brief",
)

DispatchFn = Callable[..., dict[str, Any]]


def _resolve_patch_lane_provider_for_section(
    configured_provider: str | None,
    lane: str,
) -> tuple[str, str]:
    """Resolve patch-run provider for one lane.

    Empty ``configured_provider`` means use the section CLI default matrix; a non-empty
    value is an explicit whole-run override.
    """
    from apps_rg.runtime.section_cli_defaults import resolve_cli_lane_provider_with_source

    configured = str(configured_provider or "").strip()
    return resolve_cli_lane_provider_with_source(configured or None, section_id=lane)


class PatchRunInputError(Exception):
    """Input/argument error — maps to process exit 2 (same family as CLI config errors)."""

    exit_code = 2


def _run_patch_runtime_preflight(
    run_dir: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Fail before lane dispatch when route-signing configuration is absent."""

    env = environ if environ is not None else os.environ
    test_mode = str(env.get("APPS_RG_TEST_HARNESS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    } or bool(str(env.get("PYTEST_CURRENT_TEST") or "").strip())
    unsigned_test = str(env.get("APPS_RG_ROUTE_SIGNING_POSTURE") or "").strip().lower() == (
        "unsigned_test"
    )
    secret_present = bool(str(env.get("APPS_RG_ROUTE_HMAC_SECRET") or "").strip())
    required = not test_mode and not unsigned_test
    missing = ["APPS_RG_ROUTE_HMAC_SECRET"] if required and not secret_present else []
    receipt = {
        "schema_version": "apps_rg_patch_run_preflight_v1",
        "generated_at_utc": _utc_now(),
        "status": "BLOCKED" if missing else "PASS",
        "dispatch_eligible": not missing,
        "route_signing_required": required,
        "route_signing_secret_present": secret_present,
        "route_signing_key_id_present": bool(
            str(env.get("APPS_RG_ROUTE_HMAC_KEY_ID") or "").strip()
        ),
        "missing_environment_variables": missing,
        "secret_material_recorded": False,
    }
    _write_json(Path(run_dir) / PATCH_RUN_PREFLIGHT_ARTIFACT, receipt)
    if missing:
        raise PatchRunInputError(
            "patch-run preflight blocked before lane dispatch: missing "
            + ", ".join(missing)
        )
    return receipt

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _patch_canonical_run_identity(run_dir: Path) -> dict[str, Any]:
    """Revalidate the persisted fresh-E2E identity for a new patch process."""

    path = Path(run_dir) / "e2e_preflight_product_entry_receipt.json"
    if not path.is_file():
        return {}
    receipt = _load_json(path)
    if not isinstance(receipt, dict) or receipt.get("status") != "PASS":
        raise PatchRunInputError("patch-run canonical product-entry receipt is invalid")
    identity = receipt.get("identity")
    if not isinstance(identity, dict):
        raise PatchRunInputError("patch-run canonical product identity is missing")
    from apps_rg.runtime.orchestration.canonical_identity_context import (
        validate_canonical_run_identity,
    )

    try:
        normalized = validate_canonical_run_identity(identity)
    except ValueError as exc:
        raise PatchRunInputError(str(exc)) from exc
    computed = "sha256:" + hashlib.sha256(
        json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    if str(receipt.get("identity_sha256") or "") != computed:
        raise PatchRunInputError("patch-run canonical product identity digest mismatch")
    return normalized


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------- targeting


@dataclass(frozen=True)
class PatchTargeting:
    """Targeting inputs re-derived from the run dir's persisted artifacts."""

    target_company: str = ""
    target_role: str = ""
    target_level: str = ""
    job_description_ref: str = ""
    job_description_text: str = ""
    manual_brief: str = ""
    generation_mode: str = "strategic_tailor"
    sources: dict[str, str] = field(default_factory=dict)


def parse_cli_command_flags(command: str) -> dict[str, str]:
    """Parse ``--flag value...`` pairs from a persisted run_manifest ``command`` string.

    The command string is ``" ".join(sys.argv)`` from the original invocation; values
    may contain spaces but never a token starting with ``--``, so splitting on flag
    tokens is deterministic.
    """
    tokens = str(command or "").split()
    out: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--"):
            vals: list[str] = []
            j = i + 1
            while j < len(tokens) and not tokens[j].startswith("--"):
                vals.append(tokens[j])
                j += 1
            out[tok] = " ".join(vals)
            i = j
        else:
            i += 1
    return out


def latest_lane_run_dir_any(sections_root: Path, lane: str) -> Path | None:
    """Deterministic latest lane run dir: lexicographically greatest ``real/<run_id>``.

    Lane run ids are ``<lane>_<YYYYMMDD>_<HHMMSS>`` so lexicographic order equals
    chronological order, independent of filesystem mtimes (deterministic across
    copies / checkouts).
    """
    real_root = Path(sections_root) / lane / "real"
    if not real_root.is_dir():
        return None
    candidates = sorted(
        (p for p in real_root.iterdir() if p.is_dir()),
        key=lambda p: p.name,
    )
    return candidates[-1] if candidates else None


def _lane_app_payload(run_dir: Path) -> dict[str, Any]:
    doc = _load_json(run_dir / "validated_request.json") or {}
    payload = doc.get("payload") or {}
    ap = payload.get("app_payload") if isinstance(payload, dict) else None
    return ap if isinstance(ap, dict) else {}


def _root_app_payload(run_dir: Path) -> tuple[dict[str, Any], str]:
    """Load the original whole-run U0 payload when lane artifacts are incomplete.

    A failed managed run can have a valid, source-bound U0 request while having no
    lane ``validated_request.json`` files (or only lane manifests without a JD
    flag).  That U0 contract is the canonical fallback for a patch continuation;
    it is more faithful than asking an operator to reconstruct targeting inputs.
    """
    for filename in ("apps_rg_u0_validated_request.json", "validated_request.json"):
        doc = _load_json(Path(run_dir) / filename) or {}
        payload = doc.get("payload") if isinstance(doc, dict) else None
        app_payload = payload.get("app_payload") if isinstance(payload, dict) else None
        if isinstance(app_payload, dict) and app_payload:
            return app_payload, f"root:{filename}:app_payload"
    return {}, ""


def _path_from_briefing_value(repo: Path, value: str) -> str:
    """Return a resolved briefing path only when the persisted value is a file."""
    text = str(value or "").strip()
    if not text:
        return ""
    candidate = resolve_repository_path(repo, text)
    return str(candidate.resolve()) if candidate.is_file() else ""


def _is_authorized_handoff_reference(
    *,
    brief_ref: str,
    jd_ref: str,
    target_company: str,
    target_role: str,
) -> bool:
    """Whether a persisted briefing path retains canonical apps_research authority.

    A patch continuation may retain this exact source-bound reference.  It may not
    replace it with the same briefing text, because inline text loses the adjacent
    producer envelope and therefore cannot satisfy the U0 provenance gate.
    """
    if not str(brief_ref or "").strip():
        return False
    from apps_rg.prerequisites.briefing_validator import validate_apps_research_handoff

    validation = validate_apps_research_handoff(
        brief_ref=str(brief_ref),
        jd_ref=str(jd_ref or ""),
        require_observed=True,
        require_x1_x3_authorization=True,
        require_canonical_exit=True,
        expected_target_company=str(target_company or ""),
        expected_target_role=str(target_role or ""),
    )
    return bool(validation.valid)


def _pointer_run_dir(repo: Path, pointer_doc: Mapping[str, Any]) -> Path | None:
    rel = str(pointer_doc.get("run_dir") or "").strip()
    if not rel:
        return None
    rd = Path(rel)
    if not rd.is_absolute():
        rd = repo / rel
    return rd.resolve()


def _iter_lane_targeting_sources(
    repo: Path,
    sections_root: Path,
    lane: str,
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Return targeting metadata sources for one lane in precedence order.

    Current runs keep the canonical metadata in ``real/<run_id>`` lane dirs. Some
    copied or compacted historical runs only keep lane pointer files with the
    original command, so patch-run must be able to recover from those pointers too.
    """
    out: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    lrd = latest_lane_run_dir_any(sections_root, lane)
    if lrd is not None:
        out.append(
            (
                f"lane:{lane}:real",
                _load_json(lrd / "run_manifest.json") or {},
                _lane_app_payload(lrd),
            )
        )

    lane_root = Path(sections_root) / lane
    for pointer_name in ("latest_successful_real_run.json", "latest_real_run.json"):
        pointer = _load_json(lane_root / pointer_name) or {}
        if not pointer:
            continue
        if str(pointer.get("command") or "").strip():
            out.append((f"lane:{lane}:{pointer_name}", pointer, {}))
        rd = _pointer_run_dir(repo, pointer)
        if rd is not None and rd.is_dir():
            out.append(
                (
                    f"lane:{lane}:{pointer_name}:run_dir",
                    _load_json(rd / "run_manifest.json") or {},
                    _lane_app_payload(rd),
                )
            )
    return out


def _iter_existing_lane_run_dirs(repo: Path, sections_root: Path, lane: str) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    lrd = latest_lane_run_dir_any(sections_root, lane)
    if lrd is not None and lrd.is_dir():
        resolved = lrd.resolve()
        out.append(resolved)
        seen.add(resolved)

    lane_root = Path(sections_root) / lane
    for pointer_name in ("latest_successful_real_run.json", "latest_real_run.json"):
        pointer = _load_json(lane_root / pointer_name) or {}
        rd = _pointer_run_dir(repo, pointer)
        if rd is not None and rd.is_dir() and rd not in seen:
            out.append(rd)
            seen.add(rd)
    return out


def _existing_majority_briefing(repo: Path, sections_root: Path) -> tuple[str, str] | None:
    """Return the majority briefing text already used by banked lane inputs.

    Patch-run must preserve whole-run input coherence. Root ingress can be stale
    after copied or compacted runs, while the lane ledgers/runtime payloads show
    the actual briefing text used by accepted evidence.
    """
    counts: Counter[str] = Counter()
    text_by_hash: dict[str, str] = {}
    for lane in GENERATED_LANES:
        for rd in _iter_existing_lane_run_dirs(repo, sections_root, lane):
            ledger = _load_json(rd / "section_input_usage_ledger.json") or {}
            refs = ledger.get("input_refs") if isinstance(ledger, dict) else {}
            briefing_hash = str(
                refs.get("briefing_hash") if isinstance(refs, dict) else ""
            ).strip()
            payload = _load_json(rd / "runtime_payload.json") or {}
            briefing_text = str(payload.get("briefing") or "").strip()
            if not briefing_hash or not briefing_text:
                continue
            counts[briefing_hash] += 1
            text_by_hash.setdefault(briefing_hash, briefing_text)

    if not counts:
        return None
    top_count = counts.most_common(1)[0][1]
    top_hashes = [h for h, count in counts.items() if count == top_count]
    if len(top_hashes) != 1:
        return None
    top_hash = top_hashes[0]
    return text_by_hash[top_hash], f"lane:runtime_payload.majority_briefing_hash:{top_hash}"


def derive_patch_targeting(repo: Path, run_dir: Path) -> PatchTargeting:
    """Re-derive targeting inputs from the run dir's persisted artifacts.

    Sources, in precedence order:
      1. root ``ingress_raw.json`` — target_company / target_role / manual_brief /
         generation_mode (written by the whole-run orchestration).
      2. any executed lane's ``run_manifest.json`` ``command`` — ``--jd`` path /
         ``--target-level`` (and company/role fallback).
      3. any executed lane's ``validated_request.json`` app_payload —
         ``job_description_text`` inline fallback when the JD file path is gone.

    Raises ``PatchRunInputError`` when company, role, or a JD source cannot be derived.
    """
    repo = Path(repo).resolve()
    run_dir = Path(run_dir).resolve()
    sources: dict[str, str] = {}

    ingress = _load_json(run_dir / "ingress_raw.json") or {}
    target_company = str(ingress.get("target_company") or "").strip()
    target_role = str(ingress.get("target_role") or "").strip()
    manual_brief = str(ingress.get("manual_brief") or "").strip()
    generation_mode = str(ingress.get("generation_mode") or "strategic_tailor").strip()
    root_payload, root_payload_source = _root_app_payload(run_dir)
    if target_company:
        sources["target_company"] = "ingress_raw.json"
    if target_role:
        sources["target_role"] = "ingress_raw.json"
    if manual_brief:
        sources["manual_brief"] = "ingress_raw.json"

    sections_root = _resolve_sections_root(run_dir)
    existing_briefing = _existing_majority_briefing(repo, sections_root)

    command_flags: dict[str, str] = {}
    app_payload: dict[str, Any] = {}
    command_source = ""
    payload_source = ""
    for lane in GENERATED_LANES:
        for source, manifest, ap in _iter_lane_targeting_sources(repo, sections_root, lane):
            flags = parse_cli_command_flags(str(manifest.get("command") or ""))
            if flags and not command_flags:
                command_flags = flags
                command_source = source
            if ap and not app_payload:
                app_payload = ap
                payload_source = source
            if command_flags and app_payload:
                break
        if command_flags and app_payload:
            break

    payload_candidates: list[tuple[dict[str, Any], str]] = []
    if app_payload:
        payload_candidates.append((app_payload, payload_source))
    if root_payload:
        payload_candidates.append((root_payload, root_payload_source))

    if not target_company:
        target_company = str(command_flags.get("--target-company") or "").strip()
        target_source = command_source
        if not target_company:
            for candidate_payload, candidate_source in payload_candidates:
                target_company = str(candidate_payload.get("target_company") or "").strip()
                if target_company:
                    target_source = candidate_source
                    break
        if target_company:
            sources["target_company"] = target_source
    if not target_role:
        target_role = str(command_flags.get("--target-role") or "").strip()
        role_source = command_source
        if not target_role:
            for candidate_payload, candidate_source in payload_candidates:
                target_role = str(candidate_payload.get("target_role") or "").strip()
                if target_role:
                    role_source = candidate_source
                    break
        if target_role:
            sources["target_role"] = role_source

    target_level = str(command_flags.get("--target-level") or "").strip()
    level_source = command_source
    if not target_level:
        for candidate_payload, candidate_source in payload_candidates:
            target_level = str(candidate_payload.get("target_level") or "").strip()
            if target_level:
                level_source = candidate_source
                break
    if target_level:
        sources["target_level"] = level_source

    jd_ref = ""
    jd_text = ""
    jd_flag = str(command_flags.get("--jd") or "").strip()
    if jd_flag:
        cand = resolve_repository_path(repo, jd_flag)
        if cand.is_file():
            jd_ref = str(cand.resolve())
            sources["job_description_ref"] = f"{command_source}:command:--jd"
    if not jd_ref:
        for candidate_payload, candidate_source in payload_candidates:
            candidate_ref = str(candidate_payload.get("job_description_ref") or "").strip()
            if not candidate_ref:
                continue
            candidate = resolve_repository_path(repo, candidate_ref)
            if candidate.is_file():
                jd_ref = str(candidate.resolve())
                sources["job_description_ref"] = candidate_source
                break
    if not jd_ref:
        for candidate_payload, candidate_source in payload_candidates:
            jd_text = str(candidate_payload.get("job_description_text") or "").strip()
            if jd_text:
                sources["job_description_text"] = (
                    "lane:validated_request.app_payload"
                    if candidate_source.startswith("lane:")
                    else candidate_source
                )
                break

    # Prefer the canonical producer-backed briefing reference from the original
    # U0 contract.  A lane's stored text remains a valuable fallback, but text
    # alone has no adjacent handoff envelope and therefore cannot stand in for
    # a valid apps_research provenance chain during a patch continuation.
    persisted_brief = manual_brief
    persisted_brief_source = str(sources.get("manual_brief") or "")
    if not persisted_brief:
        for candidate_payload, candidate_source in payload_candidates:
            for field_name in ("briefing_artifact_ref", "manual_brief_path"):
                value = str(candidate_payload.get(field_name) or "").strip()
                if value:
                    persisted_brief = value
                    persisted_brief_source = candidate_source
                    break
            if persisted_brief:
                break

    resolved_persisted_brief = _path_from_briefing_value(repo, persisted_brief)
    if resolved_persisted_brief and _is_authorized_handoff_reference(
        brief_ref=resolved_persisted_brief,
        jd_ref=jd_ref,
        target_company=target_company,
        target_role=target_role,
    ):
        manual_brief = resolved_persisted_brief
        sources["manual_brief"] = persisted_brief_source or "ingress_raw.json"
    elif existing_briefing is not None:
        manual_brief, source = existing_briefing
        sources["manual_brief"] = source
    elif resolved_persisted_brief:
        manual_brief = resolved_persisted_brief
    else:
        # Path persisted but no longer on disk — fall back to an already-used
        # inline briefing only when no producer-bound reference remains.
        manual_brief = persisted_brief
        for candidate_payload, candidate_source in payload_candidates:
            uc = candidate_payload.get("user_constraints") or {}
            inline = str(uc.get("briefing_text") or "").strip() if isinstance(uc, dict) else ""
            if inline:
                manual_brief = inline
                sources["manual_brief"] = (
                    "lane:validated_request.user_constraints.briefing_text"
                    if candidate_source.startswith("lane:")
                    else f"{candidate_source}.user_constraints.briefing_text"
                )
                break

    missing: list[str] = []
    if not target_company:
        missing.append("target_company")
    if not target_role:
        missing.append("target_role")
    if not jd_ref and not jd_text:
        missing.append("jd (no --jd path on disk and no persisted job_description_text)")
    if missing:
        raise PatchRunInputError(
            "patch-run cannot re-derive targeting inputs from the run dir's persisted "
            f"artifacts ({run_dir}): missing {', '.join(missing)}. "
            "Expected ingress_raw.json and/or an executed lane's run_manifest.json / "
            "validated_request.json. Patch-run never asks interactively — re-run the "
            "full integrated CLI with explicit flags instead."
        )

    return PatchTargeting(
        target_company=target_company,
        target_role=target_role,
        target_level=target_level,
        job_description_ref=jd_ref,
        job_description_text=jd_text,
        manual_brief=manual_brief,
        generation_mode=generation_mode or "strategic_tailor",
        sources=sources,
    )


# --------------------------------------------------------------------- lane states


def _whole_resume_graph_digest_for_run(run_dir: Path) -> str:
    """Return the frozen whole-resume allocation digest, when this run has one."""

    plan = _load_json(
        Path(run_dir)
        / "modular_r4"
        / "resume_graph_allocation"
        / "resume_graph_allocation_plan.json"
    )
    if not isinstance(plan, dict):
        return ""
    return str(plan.get("allocation_plan_digest") or "").strip()


def _lane_matches_frozen_graph_authority(
    lane_run_dir: Path,
    *,
    expected_digest: str,
) -> tuple[bool, str]:
    """Require a lane's final visible claims to bind to the run's frozen plan.

    Per-lane X3 authorization proves section quality, but it does not prove
    that a banked lane belongs to the current whole-resume allocation.  Patch
    runs previously treated stale/missing graph bindings as green and later
    failed only at W7 aggregation.  When a whole-resume plan exists, banking is
    valid only with the final claim-binding contract for that exact digest.
    """

    if not expected_digest:
        return True, "whole_resume_graph_not_active"
    contract = _load_json(Path(lane_run_dir) / "graph_claim_bindings.json")
    if not isinstance(contract, dict):
        return False, "frozen_graph_claim_binding_missing"
    observed_digest = str(contract.get("allocation_plan_digest") or "").strip()
    if observed_digest != expected_digest:
        return (
            False,
            "frozen_graph_allocation_digest_mismatch:"
            f"expected={expected_digest}:observed={observed_digest or 'missing'}",
        )
    if contract.get("active") is not True:
        return False, "frozen_graph_claim_binding_inactive"
    if contract.get("pass") is not True or str(contract.get("status") or "") != "PASS":
        failures = ",".join(str(x) for x in (contract.get("failure_reasons") or []))
        return False, f"frozen_graph_claim_binding_nonpass:{failures or 'unspecified'}"
    claim_count = int(contract.get("claim_count") or 0)
    bound_claim_count = int(contract.get("bound_claim_count") or 0)
    section_id = str(contract.get("section_id") or "").strip()
    is_zero_claim_lane = (
        section_id in ("ey_bullets", "ey_narrative")
        and claim_count == 0
        and bound_claim_count == 0
    )
    if not is_zero_claim_lane and (claim_count <= 0 or bound_claim_count != claim_count):
        return (
            False,
            "frozen_graph_claim_binding_incomplete:"
            f"claims={claim_count}:bound={bound_claim_count}",
        )
    return True, "ok"


def classify_lane_state(repo: Path, run_dir: Path, lane: str) -> dict[str, Any]:
    """Classify one lane's current state from on-disk evidence (env-independent).

    AUTHORIZED iff ``latest_successful_real_run.json`` resolves to a run dir that
    meets the product lane bar (REAL_LLM + product PASS + X3 allow family) — the same
    bar ``resolve_latest_lane_run_dir`` applies on the product fail-closed path.
    """
    from apps_rg.runtime.integrated_lane_evidence_packaging import (
        _lane_x3_from_artifact_dir,
        load_integrated_lane_pre_run_failure,
    )
    from apps_rg.runtime.product_output_policy import lane_run_dir_meets_product_bar

    sections_root = _resolve_sections_root(run_dir)
    lane_base = sections_root / lane
    out: dict[str, Any] = {
        "lane": lane,
        "authorized": False,
        "state": "NOT_RUN",
        "reason": "",
        "run_dir": None,
        "run_id": None,
    }

    ptr = _load_json(lane_base / "latest_successful_real_run.json")
    if ptr:
        rel = str(ptr.get("run_dir") or "").strip()
        rd = (Path(repo) / rel).resolve() if rel and not Path(rel).is_absolute() else Path(rel)
        if rel and rd.is_dir():
            ok, reason = lane_run_dir_meets_product_bar(rd)
            x3 = _lane_x3_from_artifact_dir(rd) or "UNKNOWN"
            if ok:
                graph_ok, graph_reason = _lane_matches_frozen_graph_authority(
                    rd,
                    expected_digest=_whole_resume_graph_digest_for_run(run_dir),
                )
                if graph_ok:
                    out.update(
                        {
                            "authorized": True,
                            "state": f"AUTHORIZED:{x3}",
                            "run_dir": str(rd),
                            "run_id": str(ptr.get("run_id") or rd.name),
                            "reason": "ok",
                        }
                    )
                    return out
                out.update(
                    {
                        "state": "STALE_WHOLE_RESUME_GRAPH_AUTHORITY",
                        "run_dir": str(rd),
                        "run_id": str(ptr.get("run_id") or rd.name),
                        "reason": graph_reason,
                    }
                )
                return out
            out["reason"] = reason

    # Non-authorized: derive the most specific available state.
    pre_run = load_integrated_lane_pre_run_failure(Path(run_dir), lane) or {}
    blocker = str(pre_run.get("blocker") or "").strip()
    latest = latest_lane_run_dir_any(sections_root, lane)
    if latest is not None:
        x3 = _lane_x3_from_artifact_dir(latest)
        if x3:
            out.update(
                {
                    "state": f"EXECUTED_{x3}",
                    "run_dir": str(latest),
                    "run_id": latest.name,
                    "reason": out["reason"] or f"x3_not_authorized:{x3}",
                }
            )
            return out
    if blocker:
        out.update({"state": f"PRE_RUN_BLOCKED:{blocker}", "reason": blocker})
        return out
    out["reason"] = out["reason"] or "no_lane_run_dir"
    return out


def classify_all_lane_states(repo: Path, run_dir: Path) -> dict[str, dict[str, Any]]:
    return {lane: classify_lane_state(repo, run_dir, lane) for lane in GENERATED_LANES}


def select_patch_lanes(
    lane_states: Mapping[str, Mapping[str, Any]],
    *,
    sections_csv: str = "",
    force_lanes_csv: str = "",
) -> list[str]:
    """Target lanes in canonical dependency order (``GENERATED_LANES``).

    Default (no ``--sections``): exactly the non-authorized lanes. Explicit
    ``--sections`` must name known lanes; an authorized lane is refused unless it is
    also named in ``--force-lanes``.
    """
    force = {s.strip() for s in str(force_lanes_csv or "").split(",") if s.strip()}
    unknown_force = sorted(force - set(GENERATED_LANES))
    if unknown_force:
        raise PatchRunInputError(f"--force-lanes names unknown lane(s): {', '.join(unknown_force)}")

    explicit = [s.strip() for s in str(sections_csv or "").split(",") if s.strip()]
    if explicit:
        unknown = sorted(set(explicit) - set(GENERATED_LANES))
        if unknown:
            raise PatchRunInputError(
                f"--sections names unknown lane(s): {', '.join(unknown)}. "
                f"Known lanes: {', '.join(GENERATED_LANES)}"
            )
        targets = {lane for lane in explicit}
    else:
        targets = {
            lane
            for lane, st in lane_states.items()
            if not bool(st.get("authorized"))
        }

    blocked = sorted(
        lane
        for lane in targets
        if bool(lane_states.get(lane, {}).get("authorized")) and lane not in force
    )
    if blocked:
        raise PatchRunInputError(
            f"refusing to re-dispatch authorized lane(s) {', '.join(blocked)} — green lanes "
            "stay banked. Name them in --force-lanes to override."
        )
    return [lane for lane in GENERATED_LANES if lane in targets]


# --------------------------------------------------------------------- plan


@dataclass
class PatchPlan:
    repo: Path
    run_dir: Path
    targeting: PatchTargeting
    lane_states: dict[str, dict[str, Any]]
    target_lanes: list[str]
    force_lanes: tuple[str, ...] = ()


def build_patch_plan(
    run_dir: Path | str,
    *,
    sections_csv: str = "",
    force_lanes_csv: str = "",
) -> PatchPlan:
    rd = Path(str(run_dir)).expanduser()
    if not rd.is_dir():
        raise PatchRunInputError(f"--patch-run dir does not exist: {rd}")
    rd = rd.resolve()
    sections_root = _resolve_sections_root(rd)
    if not sections_root.is_dir():
        raise PatchRunInputError(
            f"--patch-run dir has no modular_r4/sections or lanes tree (not an integrated modular "
            f"run dir): {rd}"
        )
    repo = find_repo_root(rd)
    try:
        rd.relative_to(repo)
    except ValueError as exc:
        raise PatchRunInputError(
            f"--patch-run dir {rd} does not resolve inside a repo root ({repo})."
        ) from exc

    targeting = derive_patch_targeting(repo, rd)
    lane_states = classify_all_lane_states(repo, rd)
    target_lanes = select_patch_lanes(
        lane_states,
        sections_csv=sections_csv,
        force_lanes_csv=force_lanes_csv,
    )
    force = tuple(s.strip() for s in str(force_lanes_csv or "").split(",") if s.strip())
    return PatchPlan(
        repo=repo,
        run_dir=rd,
        targeting=targeting,
        lane_states=lane_states,
        target_lanes=target_lanes,
        force_lanes=force,
    )


def render_patch_plan(plan: PatchPlan) -> str:
    t = plan.targeting
    jd_desc = t.job_description_ref or (
        f"inline_text({len(t.job_description_text)} chars)" if t.job_description_text else "(none)"
    )
    brief_desc = t.manual_brief if t.manual_brief and Path(t.manual_brief).is_file() else (
        f"inline_text({len(t.manual_brief)} chars)" if t.manual_brief else "(none)"
    )
    lines = [
        f"PATCH RUN PLAN run_dir={plan.run_dir}",
        f"targeting: company={t.target_company!r} role={t.target_role!r} "
        f"level={t.target_level!r} mode={t.generation_mode}",
        f"  jd: {jd_desc}",
        f"  brief: {brief_desc}",
        "lane states:",
    ]
    for lane in GENERATED_LANES:
        st = plan.lane_states[lane]
        marker = "PATCH" if lane in plan.target_lanes else "keep "
        lines.append(f"  [{marker}] {lane:<22} {st['state']}")
    order = ", ".join(plan.target_lanes) if plan.target_lanes else "(none — all lanes authorized)"
    lines.append(f"target lanes (dispatch order): {order}")
    return "\n".join(lines)


# --------------------------------------------------------------------- dispatch


def _patch_lane_attempt_artifact_dir(plan: PatchPlan, lane: str) -> Path:
    """Return an isolated artifact root for one patch-lane invocation.

    A patch re-dispatch must never write into the flat lane directory left by a
    prior attempt: its previous receipts may be intentionally small while a
    later valid graph audit is materially larger. Isolating every retry below
    ``real/`` preserves both attempts and keeps the write-amplification guard
    meaningful instead of weakening it.
    """
    # Keep the immutable child name deliberately short. Fresh E2E run roots can
    # already put ordinary lane artifacts near the legacy Windows MAX_PATH
    # boundary; the old 34-character ``patch_<timestamp>_<uuid>`` suffix made
    # ``section_front_spine_receipt.json`` land at exactly 260 characters and
    # fail before provider dispatch. Six random hex digits are collision-safe
    # for this bounded local retry set, and the loop preserves immutability.
    attempt_root = plan.run_dir / "modular_r4" / "sections" / lane / "real"
    for _ in range(32):
        attempt_id = f"p_{uuid.uuid4().hex[:6]}"
        candidate = attempt_root / attempt_id
        if not candidate.exists():
            return candidate
    raise PatchRunInputError(
        f"could not allocate a unique short patch attempt directory for {lane}"
    )


def _default_dispatch_lane(
    *,
    plan: PatchPlan,
    lane: str,
    lane_provider: str,
) -> dict[str, Any]:
    """Dispatch one lane exactly like the integrated full run's serial Phase-1 loop."""
    from apps_rg.runtime.orchestration.canonical_dispatch import (
        run_canonical_apps_rg_from_cli_primitives,
    )
    from apps_rg.runtime.section_cli_defaults import (
        resolve_cli_x1d_judges,
        resolve_phase1_lane_allow_non_allow_exit_zero,
    )
    from apps_rg.runtime.section_lane_temperature import default_temperature_for_section

    t = plan.targeting
    effective_provider, provider_source = _resolve_patch_lane_provider_for_section(
        lane_provider,
        lane,
    )
    # Explicitly override the flat whole-run lane root with a new, immutable
    # attempt root. The section finalizer still updates the lane pointer only
    # when this real run clears its product bar.
    attempt_artifact_dir = _patch_lane_attempt_artifact_dir(plan, lane)
    result = run_canonical_apps_rg_from_cli_primitives(
        target_company=t.target_company,
        target_role=t.target_role,
        target_level=t.target_level,
        jd="",
        job_description_ref=t.job_description_ref,
        job_description_text=t.job_description_text,
        manual_brief=t.manual_brief,
        resume_path="",
        source_resume_text="",
        generation_mode=t.generation_mode or "strategic_tailor",
        artifact_dir=str(attempt_artifact_dir),
        section=lane,
        lane_provider=effective_provider,
        lane_provider_resolution_source=provider_source,
        lane_temperature=default_temperature_for_section(lane),
        lane_x1d_judges=resolve_cli_x1d_judges(None, section_id=lane),
        lane_mock_judges=False,
        lane_allow_non_allow_exit_zero=resolve_phase1_lane_allow_non_allow_exit_zero(False),
    )
    return dict(result) if isinstance(result, dict) else {}


def _dispatch_patch_lanes(
    plan: PatchPlan,
    *,
    lane_provider: str,
    dispatch_fn: DispatchFn | None = None,
    lane_timeout_s: float | None = None,
    run_timeout_s: float | None = None,
    start_time: float | None = None,
) -> dict[str, dict[str, Any]]:
    """Serial dispatch of target lanes with the full run's upstream + fault semantics."""
    from apps_rg.runtime.integrated_lane_evidence_packaging import (
        emit_integrated_lane_pre_run_failure,
    )
    from apps_rg.runtime.product_output_policy import (
        phase1_dispatch_hard_failed,
        product_fail_closed_runtime,
    )
    from apps_rg.runtime.reasoning.employment_bullet_pool import REQUIRED_BULLET_IDS
    from apps_rg.runtime.section_execution_plan import NARRATIVE_UPSTREAM_BULLET_LANE
    from apps_rg.runtime.validators.companion_bullet_finalization import (
        PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER,
        companion_accepted_in_modular_sections_root,
    )

    dispatch = dispatch_fn or _default_dispatch_lane
    repo = plan.repo
    sections_root = _resolve_sections_root(plan.run_dir)
    results: dict[str, dict[str, Any]] = {}
    aborted = False
    abort_reason = ""

    lane_timeout = resolve_patch_lane_timeout_s(lane_timeout_s)
    run_timeout = resolve_patch_run_timeout_s(run_timeout_s)
    clock_start = start_time if start_time is not None else time.monotonic()
    total_lanes = len(plan.target_lanes)

    for idx, lane in enumerate(plan.target_lanes, start=1):
        if aborted:
            results[lane] = {"prior_abort": abort_reason, "exit_status": "error"}
            print(
                f"[patch_run] [{idx}/{total_lanes}] Skipping lane '{lane}' (prior abort: {abort_reason})",
                flush=True,
            )
            emit_integrated_lane_pre_run_failure(
                sections_root=sections_root,
                integrated_dir=plan.run_dir,
                repo_root=repo,
                lane_id=lane,
                blocker="PHASE1_PRIOR_LANE_FAILED",
                dispatch_result=results[lane],
                lane_exec_status="pre_run_blocked:PHASE1_PRIOR_LANE_FAILED",
            )
            continue

        if (time.monotonic() - clock_start) >= run_timeout:
            aborted = True
            abort_reason = f"run_timeout_exceeded:{run_timeout:.1f}s"
            results[lane] = {
                "prior_abort": abort_reason,
                "exit_status": "error",
                "fault": "patch_run_timeout",
            }
            print(
                f"[patch_run] [{idx}/{total_lanes}] Aborting lane '{lane}': "
                f"total patch-run timeout exceeded ({run_timeout:.1f}s)",
                flush=True,
            )
            emit_integrated_lane_pre_run_failure(
                sections_root=sections_root,
                integrated_dir=plan.run_dir,
                repo_root=repo,
                lane_id=lane,
                blocker="PATCH_RUN_TIMEOUT",
                dispatch_result=results[lane],
                lane_exec_status="pre_run_blocked:PATCH_RUN_TIMEOUT",
            )
            continue

        upstream = NARRATIVE_UPSTREAM_BULLET_LANE.get(lane)
        if upstream is not None:
            expected_ids = tuple(REQUIRED_BULLET_IDS.get(upstream, ()))
            if not companion_accepted_in_modular_sections_root(
                repo,
                sections_root,
                upstream_section_id=upstream,
                expected_bullet_ids=expected_ids,
            ):
                results[lane] = {
                    "fault": "upstream_not_finalized",
                    "upstream_lane": upstream,
                    "exit_status": "error",
                }
                print(
                    f"[patch_run] [{idx}/{total_lanes}] Lane '{lane}' blocked: "
                    f"upstream '{upstream}' not finalized",
                    flush=True,
                )
                emit_integrated_lane_pre_run_failure(
                    sections_root=sections_root,
                    integrated_dir=plan.run_dir,
                    repo_root=repo,
                    lane_id=lane,
                    blocker=PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER,
                    dispatch_result=results[lane],
                    lane_exec_status=(
                        f"pre_run_blocked:{PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER}"
                    ),
                )
                continue

        print(
            f"[patch_run] [{idx}/{total_lanes}] Dispatching lane '{lane}' "
            f"(lane_timeout={lane_timeout:.0f}s)...",
            flush=True,
        )
        lane_start = time.monotonic()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        timed_out = False
        try:
            future = executor.submit(dispatch, plan=plan, lane=lane, lane_provider=lane_provider)
            results[lane] = future.result(timeout=lane_timeout)
        except concurrent.futures.TimeoutError:
            timed_out = True
            executor.shutdown(wait=False, cancel_futures=True)
            results[lane] = {
                "fault": "timeout",
                "error": f"Lane '{lane}' timed out after {lane_timeout:.1f}s",
                "exit_status": "error",
            }
            print(
                f"[patch_run] [{idx}/{total_lanes}] ERROR: Lane '{lane}' TIMED OUT after {lane_timeout:.1f}s",
                flush=True,
            )
            emit_integrated_lane_pre_run_failure(
                sections_root=sections_root,
                integrated_dir=plan.run_dir,
                repo_root=repo,
                lane_id=lane,
                blocker="LANE_TIMEOUT",
                dispatch_result=results[lane],
                lane_exec_status="pre_run_blocked:LANE_TIMEOUT",
            )
        except (ImportError, AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
            executor.shutdown(wait=False)
            results[lane] = {"fault": "exception", "error": str(exc), "exit_status": "error"}
            print(
                f"[patch_run] [{idx}/{total_lanes}] ERROR: Lane '{lane}' exception: {exc}",
                flush=True,
            )
        else:
            executor.shutdown(wait=False)

        lane_elapsed = time.monotonic() - lane_start
        exit_status = str(results[lane].get("exit_status") or "unknown")
        x3_code = str(results[lane].get("x3_disposition") or results[lane].get("fault") or "")
        if not timed_out and "fault" not in results[lane]:
            print(
                f"[patch_run] [{idx}/{total_lanes}] Lane '{lane}' finished in {lane_elapsed:.1f}s "
                f"(exit_status={exit_status}, x3={x3_code})",
                flush=True,
            )

        if product_fail_closed_runtime() and phase1_dispatch_hard_failed(results[lane]):
            aborted = True
            abort_reason = f"dispatch_failed:{lane}"
    return results


# --------------------------------------------------------------------- aggregation


def aggregate_patched_run(
    plan: PatchPlan,
    *,
    lane_dispatch_results: Mapping[str, Mapping[str, Any]],
    lane_provider: str,
    run_token: str,
) -> dict[str, Any]:
    """Re-run the integrated run's app-side aggregation chain with the SAME functions.

    Mirrors the Phase-1 tail of ``run_modular_resume_generation``: lane run-dir
    materialization → generated_lane_rollup → locked copy → final resume assembly →
    rg_output merge → outputs/generated_resume.json → artifact gate → recipe lane
    policy → ``finalize_integrated_run_lane_evidence`` (evidence status + RUN_LINKS).
    """
    from apps_rg.l2_recipe.modular_lane_adapter import build_section_provider_call_record
    from apps_rg.l2_recipe.modular_lane_recipe_policy import (
        summarize_modular_lane_recipe_policy,
    )
    from apps_rg.l2_recipe.modular_resume_generation import (
        LANE_DISPATCH_MODULES,
        ModularResumeInputPackage,
        _phase1_materialize_lane_run_dir,
        _phase1_missing_lane_record,
    )
    from apps_rg.l2_recipe.modular_rg_output_builder import (
        build_rg_output_from_modular_sections,
        load_lane_l2_from_section_refs,
    )
    from apps_rg.l2_recipe.resume_artifact_gate import (
        merge_manifest_after_artifact_gate,
        persist_json_product_outputs,
        verify_full_resume_artifact_bundle,
    )
    from apps_rg.runtime.assembly.final_resume_manifest import FinalResumePaths
    from apps_rg.runtime.integrated_lane_evidence_packaging import (
        emit_integrated_lane_pre_run_failure,
        finalize_integrated_run_lane_evidence,
    )
    from apps_rg.runtime.internal.final_resume_assembler import assemble_final_resume
    from apps_rg.runtime.internal.generated_lane_rollup import build_modular_lane_rollup
    from apps_rg.runtime.internal.locked_copy_builder import build_locked_copy
    from apps_rg.runtime.product_output_policy import product_fail_closed_runtime
    from apps_rg.runtime.resume_resolution import load_lane_base_resume_json

    repo = plan.repo
    art = plan.run_dir
    modular_root = art / "modular_r4"
    sections_root = modular_root / "sections"
    dispatch_results: dict[str, dict[str, Any]] = {
        k: dict(v) for k, v in lane_dispatch_results.items()
    }
    lane_exec_status: dict[str, str] = {}
    lane_provider_by_lane: dict[str, str] = {}
    lane_provider_source_by_lane: dict[str, str] = {}

    def _lane_provider_for_lane(lane: str) -> str:
        if lane not in lane_provider_by_lane:
            provider, source = _resolve_patch_lane_provider_for_section(lane_provider, lane)
            lane_provider_by_lane[lane] = provider
            lane_provider_source_by_lane[lane] = source
        return lane_provider_by_lane[lane]

    def _lane_provider_source_for_lane(lane: str) -> str:
        _lane_provider_for_lane(lane)
        return lane_provider_source_by_lane[lane]

    lane_run_dirs: dict[str, Path] = {}
    for lane in GENERATED_LANES:
        rd = _phase1_materialize_lane_run_dir(
            repo=repo,
            sections_root=sections_root,
            integrated_dir=art,
            lane=lane,
            lane_provider=_lane_provider_for_lane(lane),
            lane_dispatch_results=dispatch_results,
            lane_exec_status=lane_exec_status,
            emit_integrated_lane_pre_run_failure=emit_integrated_lane_pre_run_failure,
            product_fail_closed=product_fail_closed_runtime(),
        )
        if rd is not None:
            lane_run_dirs[lane] = rd

    rollup_blob: dict[str, Any] | None = None
    assembly_gates_ok: bool | None = None
    section_output_refs: dict[str, str] = {}
    merge_receipt_rel: str | None = None
    rg_output_merge_receipt_rel: str | None = None
    gen_resume: dict[str, Any] | None = None
    final_schema_valid = False
    build_ok = False
    merged_err = "patch_merge_not_attempted"
    lane_load_errors: dict[str, str] = {}
    final_output_contract: dict[str, Any] = {}

    if len(lane_run_dirs) == len(GENERATED_LANES):
        rollup_blob = build_modular_lane_rollup(repo, lane_run_dirs)
        rollup_blob.update(
            _whole_resume_graph_rollup_authority(repo=repo, run_dir=art)
        )
        for lane in GENERATED_LANES:
            row = rollup_blob["lanes"].get(lane)
            if isinstance(row, dict):
                rel_run = str(row.get("rollup_source_run_dir") or "")
                if rel_run:
                    section_output_refs[lane] = f"{rel_run}/l2_output.json"
        rollup_dir = modular_root / "generated_lane_rollup"
        rollup_dir.mkdir(parents=True, exist_ok=True)
        _write_json(rollup_dir / "generated_lane_rollup.json", rollup_blob)

        build_locked_copy(repo, modular_output_root=modular_root)

        locked_dir = modular_root / "locked_copy"
        base_resume_obj, canonical_base_resume_path, _ = load_lane_base_resume_json(repo_root=repo)
        paths = FinalResumePaths(
            repo_root=repo,
            rollup_json=rollup_dir / "generated_lane_rollup.json",
            locked_manifest=locked_dir / "locked_copy_manifest.json",
            locked_x2=locked_dir / "locked_copy_x2_gate_outputs.json",
            base_resume=canonical_base_resume_path,
            output_dir=modular_root / "final_resume_assembly",
        )
        asm = assemble_final_resume(paths, skip_preflight=False)
        assembly_gates_ok = bool(asm.get("gates_all_pass"))
        receipt_path = asm["paths"]["receipt"]
        try:
            merge_receipt_rel = receipt_path.relative_to(art).as_posix()
        except ValueError:
            merge_receipt_rel = str(receipt_path)

        if assembly_gates_ok:
            input_package = ModularResumeInputPackage(
                repo_root=repo,
                target_company=plan.targeting.target_company,
                target_role=plan.targeting.target_role,
            )
            rollup_lanes = rollup_blob.get("lanes") if isinstance(rollup_blob, dict) else {}
            lane_map, lane_load_errors = load_lane_l2_from_section_refs(
                repo,
                section_output_refs,
                rollup_lanes=rollup_lanes if isinstance(rollup_lanes, dict) else None,
            )
            build = build_rg_output_from_modular_sections(
                lane_l2_by_id=lane_map,
                base_resume=base_resume_obj,
                input_package=input_package,
                modular_root=modular_root,
                artifact_dir=art,
                run_id=run_token,
                reject_mocked_lanes=True,
            )
            build_ok = bool(build.ok)
            merged_err = build.failure_reason or build.schema_error or ""
            final_schema_valid = bool(build.schema_valid and build.ok)
            gen_resume = build.rg_output if build_ok else None
            merge_out = modular_root / "outputs" / "rg_output_merge_receipt.json"
            _write_json(merge_out, build.merge_receipt)
            try:
                rg_output_merge_receipt_rel = merge_out.relative_to(art).as_posix()
            except ValueError:
                rg_output_merge_receipt_rel = str(merge_out).replace("\\", "/")
            if build_ok and gen_resume is not None:
                prod_out = art / "outputs" / "generated_resume.json"
                prod_out.parent.mkdir(parents=True, exist_ok=True)
                prod_out.write_text(
                    json.dumps(gen_resume, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
    else:
        assembly_gates_ok = False

    # Section provider call records — same shapes as the full run.
    section_call_records: list[dict[str, Any]] = []
    for i, lane in enumerate(GENERATED_LANES):
        rd = lane_run_dirs.get(lane)
        if rd is None or not rd.is_dir():
            from apps_rg.runtime.integrated_lane_evidence_packaging import (
                load_integrated_lane_pre_run_failure,
            )

            pre_run = load_integrated_lane_pre_run_failure(art, lane)
            decisive = str((pre_run or {}).get("blocker") or "PHASE1_NO_RUN_DIR")
            section_call_records.append(
                _phase1_missing_lane_record(
                    lane,
                    i,
                    0,
                    0,
                    _lane_provider_for_lane(lane),
                    decisive_reason_code=decisive,
                ),
            )
            continue
        section_call_records.append(
            build_section_provider_call_record(
                lane=lane,
                candidate_index=i,
                run_dir=rd,
                artifact_dir=art,
                self_consistency_requested=0,
                self_consistency_executed=0,
                provider_profile=_lane_provider_for_lane(lane),
            ),
        )

    recipe_lane_policy = summarize_modular_lane_recipe_policy(
        section_call_records,
        enforce_product_lane_requirements=True,
    )

    # Decisive status — same rules as the full run's Phase-1 branch.
    decisive = "FAIL"
    failure = ""
    if rollup_blob is None:
        failure = "phase1_incomplete_lane_artifacts"
    elif assembly_gates_ok is False:
        failure = "deterministic_assembly_gates_failed"
    elif lane_load_errors:
        failure = "lane_l2_load_errors:" + ";".join(
            f"{k}={v}" for k, v in sorted(lane_load_errors.items())
        )
    elif build_ok:
        decisive = "PASS"
    elif assembly_gates_ok is True:
        failure = merged_err or "modular_rg_output_merge_failed"
    else:
        failure = "deterministic_assembly_failed_unknown"

    if recipe_lane_policy.get("fatal_lane_failures"):
        decisive = "FAIL"
        failure = "fatal_lane_recipe_policy:" + "; ".join(
            f'{f["section_lane"]}:{f.get("decisive_reason_code") or ""}'
            for f in recipe_lane_policy["fatal_lane_failures"][:8]
        )

    # Artifact gate (full-run ResumeArtifactGateStep equivalent).
    artifact_gate_status = "not_attempted"
    if decisive == "PASS" and isinstance(gen_resume, dict) and gen_resume:
        try:
            persist_json_product_outputs(art, generated_resume=gen_resume)
            rep = verify_full_resume_artifact_bundle(art)
            merge_manifest_after_artifact_gate(art, shape_rep=rep)
            # Patch aggregation creates a new final-resume snapshot.  A prior
            # failed run may still contain a stale FINAL_RESUME_OUTPUT/DOCX
            # contract, so presence alone cannot authorize this patched
            # product. Re-render and validate both outputs from this run's
            # current final_resume.json before evaluating eligibility.
            from apps_rg.runtime.final_resume_outputs import (
                emit_final_resume_product_outputs,
            )

            final_output_contract = emit_final_resume_product_outputs(
                art,
                repo_root=repo,
                required=True,
            )
            if final_output_contract.get("status") != "PASS":
                failed = list(final_output_contract.get("failed_gate_ids") or [])
                raise RuntimeError(
                    "FAILED_PATCH_FINAL_OUTPUT_CONTRACT:"
                    + (",".join(str(value) for value in failed) or "unknown")
                )
            artifact_gate_status = "verified_with_current_final_outputs"
        except RuntimeError as exc:
            decisive = "FAIL"
            failure = str(exc)
            artifact_gate_status = "failed"

    # Evidence status refresh + parent RUN_LINKS (same finalizer as the full run).
    finalize_integrated_run_lane_evidence(
        repo,
        art,
        correlation_id=run_token,
        section_call_records=section_call_records,
        recipe_lane_policy=recipe_lane_policy,
    )

    _write_json(
        modular_root / "section_provider_calls.json",
        {
            "schema_version": "apps_rg.section_provider_calls.phase1.v2",
            "run_id": run_token,
            "modular_root_rel": "modular_r4",
            "provider_call_count": sum(
                1 for r in section_call_records if r.get("provider_call_attempted") is True
            ),
            "locked_sections_provider_calls_detected": False,
            "real_lane_invocation_attempted": True,
            "records": section_call_records,
            "lane_dispatch_modules": list(LANE_DISPATCH_MODULES),
            "lane_provider_global_override": str(lane_provider or ""),
            "lane_provider_by_lane": {
                lane: _lane_provider_for_lane(lane) for lane in GENERATED_LANES
            },
            "lane_provider_resolution_source_by_lane": {
                lane: _lane_provider_source_for_lane(lane) for lane in GENERATED_LANES
            },
            "decisive_status": decisive,
            "pass_source": "merged_rg_output_direct_lanes" if decisive == "PASS" else "",
            "recipe_lane_policy": recipe_lane_policy,
            "patch_run": True,
        },
    )

    from apps_rg.runtime.orchestration.canonical_dispatch import (
        _augment_integrated_manifest_with_apps_rg_docx,
    )

    _augment_integrated_manifest_with_apps_rg_docx(art)

    eligibility: dict[str, Any] = {"eligible": False, "reasons": ["output_manifest_missing"]}
    manifest_doc = _load_json(art / "apps_rg_output_manifest.json")
    if manifest_doc is not None:
        from apps_rg.runtime.package.apps_rg_full_resume_x3_eligibility import (
            evaluate_apps_rg_full_success_eligibility,
        )

        ok, reasons = evaluate_apps_rg_full_success_eligibility(
            manifest=manifest_doc,
            run_root=art,
        )
        eligibility = {"eligible": ok, "reasons": reasons}

    return {
        "decisive_status": decisive,
        "failure_reason": failure,
        "lanes_resolved": sorted(lane_run_dirs),
        "lane_run_dirs": {k: str(v) for k, v in lane_run_dirs.items()},
        "assembly_gates_ok": assembly_gates_ok,
        "merge_receipt_rel": merge_receipt_rel,
        "rg_output_merge_receipt_rel": rg_output_merge_receipt_rel,
        "final_schema_valid": final_schema_valid,
        "artifact_gate_status": artifact_gate_status,
        "final_output_contract": final_output_contract,
        "recipe_lane_policy": recipe_lane_policy,
        "full_success_eligibility": eligibility,
        "lane_provider_global_override": str(lane_provider or ""),
        "lane_provider_by_lane": {
            lane: _lane_provider_for_lane(lane) for lane in GENERATED_LANES
        },
        "lane_provider_resolution_source_by_lane": {
            lane: _lane_provider_source_for_lane(lane) for lane in GENERATED_LANES
        },
    }


# --------------------------------------------------------------------- execute


def execute_patch_run(
    plan: PatchPlan,
    *,
    dry_run: bool = False,
    dispatch_fn: DispatchFn | None = None,
    aggregate_fn: Callable[..., dict[str, Any]] | None = None,
    lane_timeout_s: float | None = None,
    run_timeout_s: float | None = None,
) -> dict[str, Any]:
    """Run the patch plan: dispatch target lanes, re-aggregate, write receipt.

    Returns a result dict including ``exit_code`` (0 only when all 11 lanes are
    authorized post-patch AND the aggregation decisive status is PASS — same outcome
    bar as the integrated full run).
    """
    if dry_run:
        print(render_patch_plan(plan), flush=True)
        print("DRY RUN: patch-run plan only — no lanes dispatched, nothing executed.", flush=True)
        return {"exit_code": 0, "dry_run": True, "target_lanes": list(plan.target_lanes)}

    from apps_rg.l2_recipe.r4_generation_mode import resolve_apps_rg_modular_lane_provider_override
    from apps_rg.runtime.run_bundle_index import repo_relative_posix
    from apps_rg.runtime.runtime_proof_layout import (
        require_manifest_for_modular_sections_root,
    )
    from apps_rg.runtime.sections_root_manifest import emit_sections_root_manifest

    repo_here = find_repo_root()
    if repo_here.resolve() != plan.repo.resolve():
        raise PatchRunInputError(
            f"patch-run execution requires the run dir's repo root ({plan.repo}) to be the "
            f"active checkout ({repo_here}); run patch-run from that checkout "
            "(dry-run works from anywhere)."
        )

    lane_timeout = resolve_patch_lane_timeout_s(lane_timeout_s)
    run_timeout = resolve_patch_run_timeout_s(run_timeout_s)
    run_start_time = time.monotonic()

    _run_patch_runtime_preflight(plan.run_dir)

    # Whole-run env preflight parity (live defect 2026-06-11, patch_run_1.log):
    # the --patch-run CLI branch returns from main() BEFORE the embedding bootstrap
    # block every full run executes (apps_rg/__main__.py + r3r4_whole_run_orchestration),
    # so CHROMA_PERSIST_DIR / EMBEDDING_ENABLED / APPS_RG_C0_DENSE_SPARSE_MANDATORY were
    # never set and every dispatched lane failed C0.2 product hybrid composition
    # PRE-provider with REQUIRED_PROOF_ABSENT ("CHROMA_PERSIST_DIR required").
    # Mirror run_whole_run_with_route_governance exactly: bootstrap + env guards +
    # embedding settings receipt into the run dir.
    from apps_rg.runtime.embedding_settings import (
        apply_apps_rg_embedding_env_guards,
        bootstrap_apps_rg_embedding_env,
        write_embedding_settings_receipt,
    )

    bootstrap_apps_rg_embedding_env(repo_root=plan.repo)
    emb = apply_apps_rg_embedding_env_guards(
        chroma_persist_dir=os.environ.get("CHROMA_PERSIST_DIR")
    )
    write_embedding_settings_receipt(plan.run_dir, emb)

    lane_provider = resolve_apps_rg_modular_lane_provider_override()
    sections_root = _resolve_sections_root(plan.run_dir)
    if not (sections_root / "sections_root_manifest.json").is_file():
        emit_sections_root_manifest(
            repo_root=plan.repo,
            sections_root_abs=sections_root,
            source_env_literal=MODULAR_R4_SECTIONS_ROOT_ENV,
            correlation_id=None,
            integrated_run_ref=repo_relative_posix(plan.repo, plan.run_dir.resolve()),
            run_links_ref=None,
            notes=f"patch_run sections root (run_dir={plan.run_dir.name})",
        )

    prior_states = {lane: plan.lane_states[lane]["state"] for lane in GENERATED_LANES}
    run_token = f"patch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    graph_env = _whole_resume_graph_env_for_patch(plan.run_dir)

    # Validate the mandatory whole-resume graph rollup before this process
    # enters _dispatch_patch_lanes. The same helper supplies the aggregation
    # binding below; calling it early prevents a replacement lane or aggregate
    # judge from running against an unreadable or mismatched graph plan.
    from apps_rg.runtime.product_output_policy import product_fail_closed_runtime

    if product_fail_closed_runtime() and _whole_resume_graph_digest_for_run(plan.run_dir):
        _whole_resume_graph_rollup_authority(repo=plan.repo, run_dir=plan.run_dir)

    saved_env = {
        name: os.environ.get(name)
        for name in (
            MODULAR_R4_SECTIONS_ROOT_ENV,
            _WHOLE_RUN_ENVELOPE_ENV,
            _CORRELATED_CLI_RUN_ENV,
            *graph_env,
        )
    }
    os.environ[MODULAR_R4_SECTIONS_ROOT_ENV] = str(sections_root.resolve())
    os.environ[_WHOLE_RUN_ENVELOPE_ENV] = "1"
    os.environ[_CORRELATED_CLI_RUN_ENV] = repo_relative_posix(plan.repo, plan.run_dir.resolve())
    os.environ.update(graph_env)
    try:
        require_manifest_for_modular_sections_root(
            sections_root, env_name=MODULAR_R4_SECTIONS_ROOT_ENV
        )
        from apps_rg.runtime.orchestration.canonical_identity_context import (
            canonical_run_identity_scope,
        )

        patch_identity = _patch_canonical_run_identity(plan.run_dir)
        with canonical_run_identity_scope(patch_identity or None):
            dispatch_results = _dispatch_patch_lanes(
                plan,
                lane_provider=lane_provider,
                dispatch_fn=dispatch_fn,
                lane_timeout_s=lane_timeout,
                run_timeout_s=run_timeout,
                start_time=run_start_time,
            )
        print("[patch_run] Lane dispatch complete; beginning aggregation...", flush=True)
        aggregate = aggregate_fn or aggregate_patched_run
        agg = aggregate(
            plan,
            lane_dispatch_results=dispatch_results,
            lane_provider=lane_provider,
            run_token=run_token,
        )
    finally:
        for name, val in saved_env.items():
            if val is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = val

    new_states_full = classify_all_lane_states(plan.repo, plan.run_dir)
    new_states = {lane: new_states_full[lane]["state"] for lane in GENERATED_LANES}
    lane_dir_chosen = {
        lane: new_states_full[lane].get("run_dir") for lane in GENERATED_LANES
    }
    all_authorized = all(bool(new_states_full[lane]["authorized"]) for lane in GENERATED_LANES)
    decisive = str(agg.get("decisive_status") or "FAIL")
    exit_code = 0 if (all_authorized and decisive == "PASS") else 1

    receipt = {
        "schema_version": "apps_rg_patch_run_receipt_v1",
        "generated_at_utc": _utc_now(),
        "run_dir": str(plan.run_dir),
        "run_token": run_token,
        "patched_lanes": list(plan.target_lanes),
        "force_lanes": list(plan.force_lanes),
        "timeouts": {
            "lane_timeout_seconds": lane_timeout,
            "run_timeout_seconds": run_timeout,
            "total_elapsed_seconds": round(time.monotonic() - run_start_time, 3),
        },
        "prior_states": prior_states,
        "new_states": new_states,
        "lane_dir_chosen_per_lane": lane_dir_chosen,
        "lane_dispatch_results": {
            lane: {
                "exit_status": str(res.get("exit_status") or ""),
                "x3_disposition": str(res.get("x3_disposition") or ""),
                "fault": str(res.get("fault") or ""),
                "artifact_dir": str(res.get("artifact_dir") or ""),
            }
            for lane, res in dispatch_results.items()
        },
        "targeting_sources": dict(plan.targeting.sources),
        "lane_provider": lane_provider or "per_section_default",
        "lane_provider_global_override": lane_provider,
        "lane_provider_by_lane": agg.get("lane_provider_by_lane"),
        "lane_provider_resolution_source_by_lane": agg.get(
            "lane_provider_resolution_source_by_lane"
        ),
        "decisive_status": decisive,
        "failure_reason": str(agg.get("failure_reason") or ""),
        "all_lanes_authorized": all_authorized,
        "full_success_eligibility": agg.get("full_success_eligibility"),
        "whole_resume_graph_env_restored": {
            name: repo_relative_posix(plan.repo, Path(path))
            for name, path in graph_env.items()
        },
        "exit_code": exit_code,
        "explicit_non_claims": [
            "patch-run does not re-emit root X3 — root x3_disposition_receipt.json / "
            "r4_run_manifest.json / terminal_ret_packet.json remain the original "
            "integrated run's Exit record (apps_rg never emits X3)",
            "authorized lanes were not re-dispatched (banked evidence preserved)",
            "locked deterministic sections untouched",
        ],
    }
    _write_json(plan.run_dir / PATCH_RUN_RECEIPT_ARTIFACT, receipt)

    total_elapsed = time.monotonic() - run_start_time
    print(
        f"[patch_run] Completed in {total_elapsed:.1f}s: decisive_status={decisive} "
        f"all_lanes_authorized={all_authorized} exit_code={exit_code}",
        flush=True,
    )
    print(f"patch_run_receipt={(plan.run_dir / PATCH_RUN_RECEIPT_ARTIFACT).as_posix()}", flush=True)

    return {
        "exit_code": exit_code,
        "dry_run": False,
        "decisive_status": decisive,
        "all_lanes_authorized": all_authorized,
        "patched_lanes": list(plan.target_lanes),
        "prior_states": prior_states,
        "new_states": new_states,
        "receipt_path": str(plan.run_dir / PATCH_RUN_RECEIPT_ARTIFACT),
        "aggregation": agg,
    }


def run_patch_from_cli(args: Any) -> int:
    """CLI entry: ``python -m apps_rg --patch-run <run_dir> [...]``."""
    try:
        plan = build_patch_plan(
            str(getattr(args, "patch_run", "") or ""),
            sections_csv=str(getattr(args, "sections", "") or ""),
            force_lanes_csv=str(getattr(args, "force_lanes", "") or ""),
        )
    except PatchRunInputError as exc:
        print(f"ERROR: {exc}", flush=True)
        return PatchRunInputError.exit_code

    if not bool(getattr(args, "dry_run", False)):
        print(render_patch_plan(plan), flush=True)

    lane_timeout = getattr(args, "lane_timeout", None)
    run_timeout = getattr(args, "timeout", None)
    try:
        result = execute_patch_run(
            plan,
            dry_run=bool(getattr(args, "dry_run", False)),
            lane_timeout_s=float(lane_timeout) if lane_timeout is not None else None,
            run_timeout_s=float(run_timeout) if run_timeout is not None else None,
        )
    except PatchRunInputError as exc:
        print(f"ERROR: {exc}", flush=True)
        return PatchRunInputError.exit_code
    return int(result.get("exit_code", 1))


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python -m apps_rg.runtime.orchestration.patch_run")
    parser.add_argument("patch_run", nargs="?", default="", help="Existing run directory to patch.")
    parser.add_argument("--run-dir", dest="run_dir_opt", default="", help="Alternative flag for run directory.")
    parser.add_argument("--sections", default="", help="CSV of section/lane IDs to patch.")
    parser.add_argument("--force-lanes", default="", help="CSV of lane IDs to force re-dispatch.")
    parser.add_argument(
        "--lane-timeout",
        type=float,
        default=None,
        help="Per-lane dispatch timeout in seconds (default: 360).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Total patch run timeout in seconds (default: 1200).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run only.")
    args = parser.parse_args(argv)
    if not args.patch_run and args.run_dir_opt:
        args.patch_run = args.run_dir_opt
    return run_patch_from_cli(args)


__all__ = [
    "DEFAULT_PATCH_LANE_TIMEOUT_SECONDS",
    "DEFAULT_PATCH_RUN_TIMEOUT_SECONDS",
    "PATCH_RUN_RECEIPT_ARTIFACT",
    "PatchPlan",
    "PatchRunInputError",
    "PatchTargeting",
    "aggregate_patched_run",
    "build_patch_plan",
    "classify_all_lane_states",
    "classify_lane_state",
    "derive_patch_targeting",
    "execute_patch_run",
    "latest_lane_run_dir_any",
    "main",
    "parse_cli_command_flags",
    "render_patch_plan",
    "resolve_patch_lane_timeout_s",
    "resolve_patch_run_timeout_s",
    "run_patch_from_cli",
    "select_patch_lanes",
]


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
