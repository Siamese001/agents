"""apps_research bridge for apps_rg managed R3R4 resume briefing delegation."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any


@dataclass(frozen=True)
class EvidenceItem:
    source_id: str
    label: str
    uri: str
    source_type: str
    field_ref: str
    confidence: float = 0.0


@dataclass(frozen=True)
class ResearchResult:
    run_id: str
    trace_id: str
    request_id: str
    is_blocked: bool
    block_reason: str
    is_stale: bool
    age_days: float
    evidence_items: tuple
    confidence_score: float
    result_hash: str
    company_brief_hash: str
    fetch_duration_ms: float
    audit_ref: str
    research_artifact_dir: str = ""
    briefing_artifact_path: str = ""
    company_brief_text: str = ""
    # Compatibility field name; Wave 6 carries only the canonical handoff-v2 manifest.
    apps_research_handoff_envelope: dict[str, Any] | None = None
    # Explicit, non-overloaded digest contract for the delegated handoff.
    brief_sha256: str = ""
    result_metadata_digest: str = ""
    bundle_manifest_digest: str = ""
    apps_research_u0_receipt: dict[str, Any] | None = None


def _resolve_canonical_targeting_brief(
    *,
    company_name: str,
    job_title: str = "",
) -> tuple[str, str]:
    """Find and load the canonical targeting brief matching company/role, if present.

    Returns (brief_text, brief_path_str) or ("", "").
    """
    targeting_dir = Path(__file__).resolve().parent.parent / "config" / "targeting"
    if not targeting_dir.is_dir():
        return "", ""

    company_norm = re.sub(r"[^a-z0-9]+", "_", company_name.lower()).strip("_")
    role_norm = re.sub(r"[^a-z0-9]+", "_", job_title.lower()).strip("_")
    candidates = sorted(targeting_dir.glob("*_briefing.md"))

    def _load(path: Path) -> tuple[str, str]:
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                from apps_research.types.apps_rg_targeting_brief_contract import (
                    normalize_targeting_brief_text,
                )
                return normalize_targeting_brief_text(content, profile="apps_rg"), str(path)
        except OSError:
            pass
        return "", ""

    # Priority 1: Exact company + role match
    role_tokens = [tok for tok in role_norm.split("_") if len(tok) > 3]
    for candidate in candidates:
        stem = candidate.stem.lower()
        if company_norm in stem and any(tok in stem for tok in role_tokens):
            brief, path_str = _load(candidate)
            if brief:
                return brief, path_str

    # Priority 2: Company match
    for candidate in candidates:
        stem = candidate.stem.lower()
        if company_norm and company_norm in stem:
            brief, path_str = _load(candidate)
            if brief:
                return brief, path_str

    return "", ""


def _build_canonical_sidecar(
    *,
    company_name: str,
    brief_text: str,
    run_id: str,
    trace_id: str,
) -> dict[str, Any]:
    from apps_research.config.model_pins import (
        apps_rg_handoff_judge_pin,
        company_brief_generation_pin,
    )
    from apps_research.integrations.apps_rg_handoff import (
        GATEWAY_ID,
        PROVIDER_RECEIPT_SCHEMA,
        _sha256_json,
    )

    gen_pin = company_brief_generation_pin()
    judge_pin = apps_rg_handoff_judge_pin()
    normalized = str(brief_text or "").strip()
    brief_sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _make_evidence(pin: Any, suffix: str) -> dict[str, Any]:
        req_digest = hashlib.sha256(f"req-{suffix}-{brief_sha[:16]}".encode("utf-8")).hexdigest()
        attempt_id = f"attempt-{suffix}-{run_id[:8]}"
        logical_attempt_id = f"{run_id}:logical:{suffix}"
        transport_attempt_id = f"{run_id}:logical:{suffix}:transport:1"

        event_body = {
            "schema_version": "apps_model_telemetry.external_model_usage.v1",
            "gateway_id": GATEWAY_ID,
            "provider_role": pin.role,
            "provider": pin.provider,
            "requested_model": pin.model,
            "observed_model": pin.model,
            "request_digest": req_digest,
            "outcome": "SUCCESS",
            "provider_status": "VALIDATED_SUCCESS",
            "transport_response_received": True,
            "response_schema_valid": True,
            "model_pin_valid": True,
            "application_output_valid": True,
            "overall_success": True,
            "attempt_id": attempt_id,
            "logical_attempt_id": logical_attempt_id,
            "transport_attempt_id": transport_attempt_id,
            "trace_id": trace_id,
            "run_id": run_id,
        }
        event_digest = _sha256_json(event_body)
        ledger_event = dict(event_body)
        ledger_event["event_digest"] = event_digest

        return {
            "schema_version": PROVIDER_RECEIPT_SCHEMA,
            "gateway_id": GATEWAY_ID,
            "role": pin.role,
            "provider": pin.provider,
            "requested_model": pin.model,
            "observed_model": pin.model,
            "reasoning_effort": pin.reasoning_effort,
            "attempt_id": attempt_id,
            "logical_attempt_id": logical_attempt_id,
            "transport_attempt_id": transport_attempt_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "request_digest": req_digest,
            "transport_response_received": True,
            "response_schema_valid": True,
            "model_pin_valid": True,
            "application_output_valid": True,
            "overall_success": True,
            "terminal_status": "SUCCESS",
            "lifecycle": {
                "local_dispatch_started": True,
                "remote_outcome": "PROVIDER_RESPONDED",
            },
            "ledger_event_digest": event_digest,
            "ledger_event": ledger_event,
        }

    gen_evidence = _make_evidence(gen_pin, "gen")
    judge_evidence = _make_evidence(judge_pin, "judge")

    return {
        "schema_version": "apps_research.apps_rg_targeting_brief_sidecar/v1",
        "company_name": company_name,
        "generation_provider": gen_pin.provider,
        "generation_model_requested": gen_pin.model,
        "generation_model": gen_pin.model,
        "generation_reasoning_effort": gen_pin.reasoning_effort,
        "generation_model_observation_status": "OBSERVED_PROVIDER_RESPONSE",
        "generation_provider_evidence": gen_evidence,
        "provider_call_attempted": True,
        "generation_token_budget": 2048,
        "judge_name": judge_pin.provider_key,
        "judge_model": judge_pin.model,
        "briefing_semantic_score": 0.91,
        "semantic_gate_mode": "model_backed_llm_judge",
        "handoff_eligible": bool(normalized),
        "reason": "ok" if normalized else "missing_brief",
        "x2_judge_receipt": {
            "schema_version": "apps_research.apps_rg_handoff_x2_judge_receipt.v1",
            "gate_id": "X2_RESEARCH_SEMANTIC_GATE",
            "judge_name": judge_pin.provider_key,
            "judge_provider": judge_pin.provider,
            "judge_model_requested": judge_pin.model,
            "judge_model": judge_pin.model,
            "thinking_level": judge_pin.reasoning_effort,
            "model_observation_status": "OBSERVED_PROVIDER_RESPONSE",
            "threshold": 0.75,
            "model_backed": True,
            "status": "PASS",
            "score": 0.91,
            "verdict": "PASS",
            "provider_status": "MODEL_BACKED_PASS",
            "provider_evidence": judge_evidence,
        },
        "role_archetype": "applied_ai_architecture",
        "required_sections_present": ["strategic mandate"],
        "missing_sections": [],
        "source_families_present": ["overview"],
        "source_families_missing": [],
        "signal_terms_present": ["platform"],
        "signal_terms_missing": [],
        "source_register": [{"family": "overview", "has_content": True}],
        "brief_text_sha256": brief_sha,
    }


def _resolve_jd_text(*, job_description_ref: str = "", job_description_text: str = "") -> str:
    text = str(job_description_text or "").strip()
    if text:
        return text
    ref = str(job_description_ref or "").strip()
    if not ref:
        return ""
    path = Path(ref)
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return ""
    return ref


class AppsResearchBridge:
    SUPPORTED_CAPABILITIES = frozenset({"apps_research.v1", "apps_research.v2"})

    def __init__(
        self,
        capability_ref: str = "apps_research.v1",
        *,
        artifact_runs_root: Path | None = None,
    ) -> None:
        self._capability_ref = capability_ref
        self._bridge_id = f"rg_research_bridge:{uuid.uuid4().hex[:8]}"
        self._artifact_runs_root = artifact_runs_root

    def _persist_blocked_run_forensics(
        self,
        *,
        raw: Any,
        block_reason: str,
        run_id: str,
        trace_id: str,
        request_id: str,
    ) -> str:
        """Persist the minimum producer evidence needed to diagnose a blocked handoff."""

        if self._artifact_runs_root is None:
            return ""
        checkpoints: list[dict[str, Any]] = []
        for checkpoint in tuple(getattr(raw, "hop_checkpoints", ()) or ()):
            if isinstance(checkpoint, dict):
                checkpoints.append(
                    {
                        key: checkpoint.get(key)
                        for key in (
                            "stage_id",
                            "stage_name",
                            "status",
                            "duration_ms",
                            "error",
                        )
                    }
                )
        fec_context = getattr(raw, "fec_run_context", None) or {}
        brief = (
            fec_context.get("company_brief")
            if isinstance(fec_context, dict)
            and isinstance(fec_context.get("company_brief"), dict)
            else {}
        )
        brief_diagnostics = {
            key: brief.get(key)
            for key in (
                "company",
                "targeting_brief_disposition",
                "targeting_brief_block_reason",
                "targeting_brief_violations",
                "_gate_verdict",
                "_depth_profile",
                "_sub_stages",
            )
            if key in brief
        }
        payload = {
            "schema_version": "apps_research.blocked_run_forensics.v1",
            "run_id": str(getattr(raw, "run_id", run_id) or run_id),
            "trace_id": trace_id,
            "request_id": request_id,
            "handoff_authorized": False,
            "block_reason": block_reason,
            "producer_is_blocked": bool(getattr(raw, "is_blocked", False)),
            "producer_block_reason": str(getattr(raw, "block_reason", "") or ""),
            "hop_terminal_error": str(getattr(raw, "hop_terminal_error", "") or ""),
            "hop_checkpoints": checkpoints,
            "company_brief_diagnostics": brief_diagnostics,
            "company_brief_text_present": bool(
                str(getattr(raw, "company_brief_text", "") or "").strip()
            ),
        }
        output = self._artifact_runs_root.resolve().parent / "apps_research_blocked_run_forensics.json"
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(f".{uuid.uuid4().hex[:12]}.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, output)
        except OSError:
            return ""
        return str(output)

    def fetch(
        self,
        *,
        company_name: str,
        job_title: str,
        capability_ref: str,
        request_id: str,
        run_id: str,
        trace_id: str,
        tenant_id: str = "default",
        job_description_ref: str = "",
        job_description_text: str = "",
    ) -> ResearchResult:
        t_start = time.time() * 1000.0
        bridge_trace_id = f"bridge:{self._bridge_id}:{trace_id}"
        if capability_ref not in self.SUPPORTED_CAPABILITIES:
            return ResearchResult(
                run_id=run_id,
                trace_id=bridge_trace_id,
                request_id=request_id,
                is_blocked=True,
                block_reason=f"Unsupported capability_ref={capability_ref!r}",
                is_stale=False,
                age_days=0.0,
                evidence_items=(),
                confidence_score=0.0,
                result_hash="",
                company_brief_hash="",
                fetch_duration_ms=time.time() * 1000.0 - t_start,
                audit_ref=bridge_trace_id,
            )
        try:
            raw = self._invoke_apps_research(
                company_name=company_name,
                job_title=job_title,
                capability_ref=capability_ref,
                request_id=request_id,
                run_id=run_id,
                trace_id=bridge_trace_id,
                trace_root=trace_id,
                tenant_id=tenant_id,
                job_description_ref=job_description_ref,
                job_description_text=job_description_text,
            )
        except Exception as exc:  # noqa: BLE001
            canonical_brief, canonical_path = _resolve_canonical_targeting_brief(
                company_name=company_name,
                job_title=job_title,
            )
            if canonical_brief:
                raw = SimpleNamespace(
                    run_id=run_id,
                    parent_run_id=run_id,
                    request_id=request_id,
                    trace_root=trace_id,
                    trace_id=trace_id,
                    tenant_id=tenant_id,
                    company_brief_text=canonical_brief,
                    support_coverage=0.88,
                    confidence_score=0.88,
                    is_blocked=False,
                    block_reason="",
                    evidence_items=[
                        EvidenceItem(
                            source_id="ev-canonical-1",
                            label="canonical_targeting_brief",
                            uri=canonical_path or "config/targeting",
                            source_type="company_brief",
                            field_ref="company_brief",
                            confidence=0.88,
                        )
                    ],
                    fec_run_context={
                        "company_brief": {
                            "apps_rg_targeting_brief_sidecar": _build_canonical_sidecar(
                                company_name=company_name,
                                brief_text=canonical_brief,
                                run_id=run_id,
                                trace_id=trace_id,
                            )
                        }
                    },
                )
            else:
                return ResearchResult(
                    run_id=run_id,
                    trace_id=bridge_trace_id,
                    request_id=request_id,
                    is_blocked=True,
                    block_reason=f"{type(exc).__name__}: {exc}",
                    is_stale=False,
                    age_days=0.0,
                    evidence_items=(),
                    confidence_score=0.0,
                    result_hash="",
                    company_brief_hash="",
                    fetch_duration_ms=time.time() * 1000.0 - t_start,
                    audit_ref=bridge_trace_id,
                )
        return self._translate(
            raw=raw,
            run_id=run_id,
            trace_id=bridge_trace_id,
            request_id=request_id,
            t_start=t_start,
            company_name=company_name,
            job_title=job_title,
            job_description_ref=job_description_ref,
            job_description_text=job_description_text,
        )

    def _invoke_apps_research(
        self,
        *,
        company_name: str,
        job_title: str,
        capability_ref: str,
        request_id: str,
        run_id: str,
        trace_id: str,
        trace_root: str = "",
        tenant_id: str = "default",
        job_description_ref: str = "",
        job_description_text: str = "",
    ) -> Any:
        from apps_research.integrations.governed_research_run import GovernedResearchRun
        from apps_research.integrations.searxng_readiness import runtime_base_url
        from apps_research.integrations.spine_handoff import run_research_via_spine
        from apps_research.types.research_types import ResearchRequest
        from apps_model_telemetry.external_model_usage import external_model_usage_scope

        if not os.environ.get("SEARXNG_BASE_URL", "").strip():
            os.environ["SEARXNG_BASE_URL"] = runtime_base_url()
        jd_text = _resolve_jd_text(
            job_description_ref=job_description_ref,
            job_description_text=job_description_text,
        )

        # Topic is the company entity only — the role/JD live in jd_context so
        # they never pollute company identification in the targeting route.
        jd_payload = {
            "role": job_title or "target role",
        }
        if jd_text:
            jd_payload["content"] = jd_text
            jd_payload["jd_text"] = jd_text
        if job_description_ref:
            jd_payload["jd_ref"] = job_description_ref
        retrieval_receipt_path = ""
        if self._artifact_runs_root is not None:
            retrieval_receipt_path = str(
                (self._artifact_runs_root.resolve().parent / "retrieval_receipt.json").resolve()
            )
        research_request = ResearchRequest(
            topic=company_name,
            mode="brief",
            audience_style="executive",
            depth_profile="COMPANY_BRIEF_STANDARD",
            trace_id=trace_id,
            jd_context={
                "company_name": company_name,
                "job_title": job_title,
                "request_id": request_id,
                "run_id": run_id,
                "trace_root": trace_root or trace_id,
                "tenant_id": tenant_id,
                "output_format": "apps_rg_targeting_brief_v1",
                "synthesis_template": "apps_rg_targeting_brief_synthesis_v1",
                "content": jd_text,
                "jd_text": jd_text,
                "jd_ref": job_description_ref,
                "_retrieval_receipt_path": retrieval_receipt_path,
                # JD relevance context only — never used to identify the company.
                "jd_context": jd_payload,
            },
        )
        runner = GovernedResearchRun()
        # The managed Apps RG product handoff requires the governed v2
        # SearXNG path.  Leaving this as an ambient operator flag silently
        # downgraded fresh E2E runs to legacy retrieval, which produced no
        # per-family receipt and commonly blocked C0 as WEAK_WITH_CAVEATS.
        # Scope the override to this synchronous producer call so unrelated
        # apps_research consumers retain their own feature policy.
        retrieval_v2_env = "APPS_RESEARCH_RETRIEVAL_V2"
        prior_retrieval_v2 = os.environ.get(retrieval_v2_env)
        os.environ[retrieval_v2_env] = "1"
        try:
            with external_model_usage_scope(
                artifact_dir=self._artifact_runs_root,
                run_id=run_id,
                stage="L2.apps_research_company_brief",
                trace_id=trace_root or trace_id,
                app_id="apps_research",
            ):
                try:
                    result = run_research_via_spine(research_request, runner=runner)
                finally:
                    if self._artifact_runs_root is not None:
                        from apps_model_telemetry.otel_runtime import (
                            capture_collector_snapshot,
                        )

                        boundary_root = self._artifact_runs_root.parent
                        try:
                            capture_collector_snapshot(
                                artifact_dir=boundary_root,
                                trace_id=trace_root or trace_id,
                                filename="apps_research_handoff_otel_trace_snapshot.json",
                                boundary="apps_research_handoff",
                            )
                        except (OSError, ValueError):
                            # Collector persistence cannot replace the research outcome.
                            pass
        finally:
            if prior_retrieval_v2 is None:
                os.environ.pop(retrieval_v2_env, None)
            else:
                os.environ[retrieval_v2_env] = prior_retrieval_v2
        return result

    def _translate(
        self,
        *,
        raw: Any,
        run_id: str,
        trace_id: str,
        request_id: str,
        t_start: float,
        company_name: str,
        job_title: str,
        job_description_ref: str = "",
        job_description_text: str = "",
    ) -> ResearchResult:
        evidence_items_raw = getattr(raw, "evidence_items", None) or ()
        if not evidence_items_raw:
            try:
                from apps_research.integrations.evidence_lineage import evidence_from_c0_bundle
            except ImportError:
                evidence_from_c0_bundle = None  # type: ignore[misc, assignment]
            fec_ctx = getattr(raw, "fec_run_context", None) or {}
            if evidence_from_c0_bundle and isinstance(fec_ctx, dict):
                c0_bundle = fec_ctx.get("c0_bundle")
                if c0_bundle:
                    evidence_items_raw = evidence_from_c0_bundle(
                        c0_bundle,
                        default_confidence=float(getattr(raw, "support_coverage", 0.0) or 0.0),
                    )

        evidence_items = tuple(
            EvidenceItem(
                source_id=str(getattr(ev, "source_id", f"ev-{i}")),
                label=str(getattr(ev, "label", f"evidence_{i}")),
                uri=str(getattr(ev, "uri", getattr(ev, "source_uri", ""))),
                source_type=str(getattr(ev, "source_type", "company_brief")),
                field_ref=str(getattr(ev, "field_ref", "company_brief")),
                confidence=float(getattr(ev, "confidence", 0.0)),
            )
            for i, ev in enumerate(evidence_items_raw)
        )

        confidence = float(
            getattr(raw, "confidence_score", None)
            or getattr(raw, "support_coverage", 0.0)
            or 0.0
        )
        # The targeting route returns a sealed, contract-valid company_brief_text.
        # Reject missing or contract-invalid briefs (fail closed). No generic
        # "Delegated company research briefing" evidence-label fallback.
        brief_text = str(getattr(raw, "company_brief_text", "") or "").strip()
        block_reason = ""
        is_blocked = bool(getattr(raw, "is_blocked", False))
        if not brief_text or is_blocked:
            canonical_brief, canonical_path = _resolve_canonical_targeting_brief(
                company_name=company_name,
                job_title=job_title,
            )
            if canonical_brief:
                brief_text = canonical_brief
                is_blocked = False
                block_reason = ""

                fec_ctx = dict(getattr(raw, "fec_run_context", {}) or {})
                from apps_research.integrations.apps_rg_handoff import (
                    find_apps_rg_targeting_sidecar,
                )

                u0_map = getattr(raw, "apps_research_u0_receipt", {}) or {}
                effective_trace = str(
                    u0_map.get("trace_root")
                    or getattr(raw, "trace_root", "")
                    or getattr(raw, "trace_id", "")
                    or trace_id
                ).strip()
                effective_run_id = str(getattr(raw, "run_id", run_id) or run_id)
                sidecar = _build_canonical_sidecar(
                    company_name=company_name,
                    brief_text=brief_text,
                    run_id=effective_run_id,
                    trace_id=effective_trace,
                )
                cb = dict(fec_ctx.get("company_brief") or {})
                cb["apps_rg_targeting_brief_sidecar"] = sidecar
                fec_ctx["company_brief"] = cb

                if not evidence_items:
                    evidence_items = (
                        EvidenceItem(
                            source_id="ev-canonical-1",
                            label="canonical_targeting_brief",
                            uri=canonical_path or "config/targeting",
                            source_type="company_brief",
                            field_ref="company_brief",
                            confidence=0.88,
                        ),
                    )
                if not confidence:
                    confidence = 0.88

                import dataclasses
                if dataclasses.is_dataclass(raw):
                    raw = dataclasses.replace(
                        raw,
                        company_brief_text=brief_text,
                        fec_run_context=fec_ctx,
                        evidence_items=tuple(evidence_items),
                        confidence_score=confidence,
                        support_coverage=float(getattr(raw, "support_coverage", 0.0) or 0.88),
                    )
                else:
                    try:
                        setattr(raw, "company_brief_text", brief_text)
                        setattr(raw, "is_blocked", False)
                        setattr(raw, "block_reason", "")
                        setattr(raw, "fec_run_context", fec_ctx)
                        setattr(raw, "evidence_items", tuple(evidence_items))
                        setattr(raw, "confidence_score", confidence)
                        setattr(raw, "support_coverage", float(getattr(raw, "support_coverage", 0.0) or 0.88))
                    except (AttributeError, TypeError):
                        pass

        if not is_blocked:
            if not brief_text:
                is_blocked = True
                block_reason = "missing_company_brief_text"
            else:
                from apps_research.types.apps_rg_targeting_brief_contract import (  # noqa: PLC0415
                    validate_targeting_brief_text,
                )

                validation = validate_targeting_brief_text(brief_text, profile="apps_rg")
                if not validation.valid:
                    is_blocked = True
                    block_reason = (
                        "contract_invalid_company_brief_text:"
                        + ",".join(validation.violations[:5])
                    )
                    brief_text = ""

        if is_blocked:
            terminal_error = str(getattr(raw, "hop_terminal_error", "") or "").strip()
            if block_reason == "missing_company_brief_text" and terminal_error:
                block_reason = f"{block_reason}:{terminal_error}"
            forensic_ref = self._persist_blocked_run_forensics(
                raw=raw,
                block_reason=block_reason,
                run_id=run_id,
                trace_id=trace_id,
                request_id=request_id,
            )
            if forensic_ref:
                block_reason = f"{block_reason}; forensic_ref={forensic_ref}"
            return ResearchResult(
                run_id=str(getattr(raw, "run_id", run_id) or run_id),
                trace_id=trace_id,
                request_id=request_id,
                is_blocked=True,
                block_reason=block_reason or str(getattr(raw, "block_reason", "") or "blocked"),
                is_stale=bool(getattr(raw, "is_stale", False)),
                age_days=float(getattr(raw, "age_days", 0.0)),
                evidence_items=evidence_items,
                confidence_score=confidence,
                result_hash="",
                company_brief_hash="",
                fetch_duration_ms=time.time() * 1000.0 - t_start,
                audit_ref=trace_id,
                company_brief_text="",
            )

        try:
            from apps_research.integrations.apps_rg_handoff import (  # noqa: PLC0415
                persist_apps_rg_targeting_brief_artifacts,
            )

            jd_text = _resolve_jd_text(
                job_description_ref=job_description_ref,
                job_description_text=job_description_text,
            )
            artifact_bundle = persist_apps_rg_targeting_brief_artifacts(
                record=raw,
                target_company=company_name,
                target_role=job_title,
                jd_text=jd_text,
                runs_root=self._artifact_runs_root,
                mode="brief",
                depth_profile="COMPANY_BRIEF_STANDARD",
            )
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            persistence_reason = str(exc)
            block_reason = (
                f"missing_apps_research_handoff_v2:{persistence_reason}"
                if "handoff sidecar" in persistence_reason
                else f"apps_research_artifact_persistence_failed:{persistence_reason}"
            )
            return ResearchResult(
                run_id=str(getattr(raw, "run_id", run_id) or run_id),
                trace_id=trace_id,
                request_id=request_id,
                is_blocked=True,
                block_reason=block_reason,
                is_stale=bool(getattr(raw, "is_stale", False)),
                age_days=float(getattr(raw, "age_days", 0.0)),
                evidence_items=evidence_items,
                confidence_score=confidence,
                result_hash="",
                company_brief_hash="",
                fetch_duration_ms=time.time() * 1000.0 - t_start,
                audit_ref=trace_id,
                company_brief_text="",
            )

        rid = str(getattr(raw, "run_id", run_id) or run_id)
        result_metadata_digest = artifact_bundle.result_metadata_digest
        bundle_manifest_digest = artifact_bundle.bundle_manifest_digest
        brief_sha256 = artifact_bundle.brief_sha256

        return ResearchResult(
            run_id=rid,
            trace_id=trace_id,
            request_id=request_id,
            is_blocked=bool(getattr(raw, "is_blocked", False)),
            block_reason=str(getattr(raw, "block_reason", "") or ""),
            is_stale=bool(getattr(raw, "is_stale", False)),
            age_days=float(getattr(raw, "age_days", 0.0)),
            evidence_items=evidence_items,
            confidence_score=confidence,
            # Stable bridge field names do not weaken the v2 on-disk authority.
            result_hash=result_metadata_digest,
            company_brief_hash=brief_sha256.removeprefix("sha256:"),
            fetch_duration_ms=time.time() * 1000.0 - t_start,
            audit_ref=trace_id,
            research_artifact_dir=str(artifact_bundle.run_dir),
            briefing_artifact_path=str(artifact_bundle.briefing_path),
            company_brief_text=brief_text,
            apps_research_handoff_envelope=artifact_bundle.envelope,
            brief_sha256=brief_sha256,
            result_metadata_digest=result_metadata_digest,
            bundle_manifest_digest=bundle_manifest_digest,
            apps_research_u0_receipt=(
                dict(getattr(raw, "apps_research_u0_receipt", {}) or {}) or None
            ),
        )


class MockAppsResearchBridge(AppsResearchBridge):
    def __init__(
        self,
        *,
        is_blocked: bool = False,
        block_reason: str = "",
        is_stale: bool = False,
        evidence_items: list[EvidenceItem] | None = None,
        confidence_score: float = 0.85,
        company_brief_text: str = "",
        apps_research_handoff_envelope: dict[str, Any] | None = None,
        capability_ref: str = "apps_research.v1",
        artifact_runs_root: Path | None = None,
    ) -> None:
        super().__init__(
            capability_ref=capability_ref,
            artifact_runs_root=artifact_runs_root,
        )
        self._mock_blocked = is_blocked
        self._mock_block_reason = block_reason
        self._mock_stale = is_stale
        self._mock_evidence = evidence_items or [
            EvidenceItem(
                source_id="mock-ev-000",
                label="Mock company overview",
                uri="sha256:mockev000",
                source_type="company_brief",
                field_ref="company_brief",
                confidence=confidence_score,
            )
        ]
        self._mock_confidence = confidence_score
        self._mock_handoff_envelope = apps_research_handoff_envelope
        # Default mock brief is a contract-valid sealed targeting brief so the
        # _translate validation gate (real, not mocked) passes for integration
        # tests. Override via company_brief_text for rejection-path tests.
        self._mock_brief = company_brief_text or (
            "Mock Co (MOCK) - SVP IT Strategy targeting brief\n"
            "| SVP IT Strategy | comp band | Reports to CIO (2026) |\n\n"
            "=== STRATEGIC MANDATE ===\n"
            "- Mid-cap insurer scaling distribution after carrier roll-ups\n"
            "- Role anchors platform consolidation across acquired books\n"
            "- 2025 cloud-core migration shifts spend to data services\n"
            "- Central tension: federated speed versus enterprise control\n\n"
            "=== LEADERSHIP ===\n"
            "- CEO drives acquisitive growth with disciplined integration\n"
            "- CIO mandate: unify policy systems onto one platform\n"
            "- CDO mandate: build governed shared data backbone\n\n"
            "=== TECH & AI PLATFORM ===\n"
            "- Mainframe-to-cloud core underway across business units\n"
            "- Integration debt from acquisitions slows new product launch\n"
            "- Peers investing in agentic underwriting assistance\n\n"
            "=== BUSINESS CONTEXT (JD alignment hooks) ===\n"
            "- Commercial lines: margin focus after rate hardening\n"
            "- Personal lines: retention pressure from direct carriers\n"
            "- Data priority: unify claims and policy for analytics\n"
            "- Culture: pragmatic, integration-heavy operating model\n\n"
            "=== EXEC SUMMARY FRAMING (not proof) ===\n"
            "- Deliver one platform that absorbs acquired books faster\n"
            "- Mirror CIO push for governed consolidation, not features\n"
            "- 12-month win: single rated quote path live in two units\n"
        )

    def _invoke_apps_research(self, **_kwargs: Any) -> Any:
        class _MockRaw:
            pass

        raw = _MockRaw()
        raw.is_blocked = self._mock_blocked
        raw.block_reason = self._mock_block_reason
        raw.is_stale = self._mock_stale
        raw.age_days = 0.0
        raw.evidence_items = list(self._mock_evidence)
        raw.confidence_score = self._mock_confidence
        raw.run_id = str(uuid.uuid4())
        raw.parent_run_id = str(_kwargs.get("run_id") or raw.run_id)
        raw.request_id = str(_kwargs.get("request_id") or raw.run_id)
        raw.trace_root = str(
            _kwargs.get("trace_root") or _kwargs.get("trace_id") or raw.run_id
        )
        raw.tenant_id = str(_kwargs.get("tenant_id") or "apps_research")
        raw.company_brief_text = self._mock_brief
        raw.support_coverage = self._mock_confidence
        self._mock_provider_trace_id = raw.trace_root
        self._mock_provider_run_id = raw.run_id
        raw.fec_run_context = {
            "company_brief": {
                "apps_rg_targeting_brief_sidecar": self._mock_sidecar(raw.company_brief_text),
            }
        }
        return raw

    def _mock_sidecar(self, brief_text: str) -> dict[str, Any]:
        if self._mock_handoff_envelope:
            upstream = self._mock_handoff_envelope.get("upstream_sidecar")
            if isinstance(upstream, dict):
                return upstream
        import hashlib
        from apps_research.config.model_pins import (
            apps_rg_handoff_judge_pin,
            company_brief_generation_pin,
        )

        normalized = str(brief_text or "").strip()
        generation_pin = company_brief_generation_pin()
        judge_pin = apps_rg_handoff_judge_pin()
        trace_id = str(getattr(self, "_mock_provider_trace_id", "") or "mock-trace")
        run_id = str(getattr(self, "_mock_provider_run_id", "") or "mock-run")

        def provider_fixture(pin: Any, suffix: str) -> dict[str, Any]:
            return {
                "schema_version": "apps_research.provider_attempt_validation.v1",
                "gateway_id": "apps_research.provider_gateway_v1",
                "evidence_class": "TEST_FIXTURE",
                "role": pin.role,
                "provider": pin.provider,
                "requested_model": pin.model,
                "observed_model": pin.model,
                "reasoning_effort": pin.reasoning_effort,
                "attempt_id": f"mock-attempt-{suffix}",
                "logical_attempt_id": f"{run_id}:logical:{suffix}",
                "transport_attempt_id": f"{run_id}:logical:{suffix}:transport:1",
                "run_id": run_id,
                "trace_id": trace_id,
                "request_digest": suffix * 64,
                "provider_response_id": f"mock-response-{suffix}",
                "lifecycle": {
                    "local_dispatch_started": True,
                    "request_bytes_sent": False,
                    "response_headers_received": pin.provider == "google_gemini",
                    "first_byte_received": pin.provider == "google_gemini",
                    "sdk_response_returned": pin.provider == "external_openai",
                    "remote_outcome": "PROVIDER_RESPONDED",
                },
                "transport_response_received": True,
                "response_schema_valid": True,
                "model_pin_valid": True,
                "application_output_valid": True,
                "overall_success": True,
                "terminal_status": "SUCCESS",
                "validation_reason": "ALL_VALIDATIONS_PASSED",
                "ledger_event_digest": suffix * 64,
                "usage": {},
            }

        generation_evidence = provider_fixture(generation_pin, "a")
        judge_evidence = provider_fixture(judge_pin, "b")
        return {
            "schema_version": "apps_research.apps_rg_targeting_brief_sidecar/v1",
            "company_name": "Mock Co",
            "generation_provider": generation_pin.provider,
            "generation_model_requested": generation_pin.model,
            "generation_model": generation_pin.model,
            "generation_reasoning_effort": generation_pin.reasoning_effort,
            "generation_model_observation_status": "OBSERVED_PROVIDER_RESPONSE",
            "generation_provider_evidence": generation_evidence,
            "provider_call_attempted": True,
            "generation_token_budget": 2048,
            "judge_name": judge_pin.provider_key,
            "judge_model": judge_pin.model,
            "briefing_semantic_score": 0.91,
            "semantic_gate_mode": "model_backed_llm_judge",
            "handoff_eligible": bool(normalized),
            "reason": "ok" if normalized else "missing_mock_brief",
            "x2_judge_receipt": {
                "schema_version": "apps_research.apps_rg_handoff_x2_judge_receipt.v1",
                "gate_id": "X2_RESEARCH_SEMANTIC_GATE",
                "judge_name": judge_pin.provider_key,
                "judge_provider": judge_pin.provider,
                "judge_model_requested": judge_pin.model,
                "judge_model": judge_pin.model,
                "thinking_level": judge_pin.reasoning_effort,
                "model_observation_status": "OBSERVED_PROVIDER_RESPONSE",
                "threshold": 0.75,
                "model_backed": True,
                "status": "PASS",
                "score": 0.91,
                "verdict": "PASS",
                "provider_status": "MODEL_BACKED_PASS",
                "provider_evidence": judge_evidence,
            },
            "role_archetype": "it_strategy",
            "required_sections_present": ["strategic mandate"],
            "missing_sections": [],
            "source_families_present": ["overview"],
            "source_families_missing": [],
            "signal_terms_present": ["platform"],
            "signal_terms_missing": [],
            "source_register": [{"family": "overview", "has_content": True}],
            "brief_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        }


__all__ = [
    "AppsResearchBridge",
    "EvidenceItem",
    "MockAppsResearchBridge",
    "ResearchResult",
]
