"""L1 Post-L2 Deterministic Check Engine.

This module implements authoritative, objective verification of sealed L2
tool execution outputs against L1 plans and signed execution packets.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Final, Mapping

from apps_rg.runtime.contracts.l1_post_tool_review_contracts import (
    L1_DETERMINISTIC_CHECK_SCHEMA_VERSION,
    L1DeterministicCheckResult,
)

SUCCESS_EXECUTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"completed", "success", "sealed", "ok", "passed", "done"}
)


def _get_attr_or_key(target: Any, key: str, default: Any = None) -> Any:
    """Safely extract attribute or dictionary key."""
    if target is None:
        return default
    if isinstance(target, Mapping):
        return target.get(key, default)
    return getattr(target, key, default)


def _content_contains_section(content: str, section_name: str) -> bool:
    """Check if markdown content contains a section header matching section_name."""
    escaped = re.escape(section_name.strip())
    # Match markdown headings e.g. '# Section', '## Section', '### Section' or bold '**Section**'
    heading_pattern = rf"(?mi)^\s*(?:#{{1,6}}\s+|\*\*\s*){escaped}(?:\s*\*|\s*:|\s*$)"
    if re.search(heading_pattern, content):
        return True
    # Fallback: check case-insensitive presence followed by colon or newline
    fallback_pattern = rf"(?mi)^\s*{escaped}\s*:"
    return bool(re.search(fallback_pattern, content))


def _payload_contains_evidence(
    evidence_id: str,
    content: str,
    state_diff: Mapping[str, Any],
) -> bool:
    """Check if evidence/fact ID is present in generated text or structured diff."""
    ev_str = str(evidence_id).strip()
    if not ev_str:
        return True

    # 1. Search in generated content
    if content and ev_str in content:
        return True

    # 2. Search in state_diff (recursive walk or json dump)
    if state_diff:
        try:
            dumped = json.dumps(state_diff, default=str)
            if ev_str in dumped:
                return True
        except Exception:  # guardian: allow-silent-swallow -- fallback to False if state_diff is not json-serializable
            pass

    return False


def l1_post_l2_deterministic_check(
    sealed_artifact: Any,
    execution_packet: Any | None = None,
    l1_plan: Any | None = None,
    *,
    custom_assertions: Mapping[str, Any] | None = None,
) -> L1DeterministicCheckResult:
    """Execute authoritative deterministic checks on a sealed L2 tool execution artifact.

    Evaluates:
      1. Tool execution success code and status.
      2. Schema conformance (JSON, markdown, or registered format validator).
      3. Presence of required fields and sections from L1 plan and execution packet.
      4. Fulfillment of evidence obligations (fact/evidence IDs bound in output).
      5. Explicit success criteria assertions.

    Returns:
      L1DeterministicCheckResult with status 'PASS' or 'FAIL' and detailed telemetry.
    """
    failure_reasons: list[str] = []
    missing_fields: list[str] = []
    missing_evidence_ids: list[str] = []
    checked_assertions: dict[str, bool] = {}

    # 1. Extract sealed artifact attributes
    raw_status = _get_attr_or_key(sealed_artifact, "execution_status", None)
    if not raw_status:
        raw_status = _get_attr_or_key(sealed_artifact, "status", None)
    if not raw_status and isinstance(sealed_artifact, Mapping):
        for candidate_key in ("section_result", "payload", "result"):
            nested = sealed_artifact.get(candidate_key)
            if isinstance(nested, Mapping):
                raw_status = nested.get("execution_status") or nested.get("status")
                if raw_status:
                    break
    if not raw_status and isinstance(sealed_artifact, Mapping):
        step_results = sealed_artifact.get("step_results")
        if isinstance(step_results, list) and step_results:
            step_statuses = []
            for s in step_results:
                if isinstance(s, Mapping):
                    sec_res = s.get("section_result")
                    if isinstance(sec_res, Mapping) and sec_res.get("execution_status"):
                        step_statuses.append(str(sec_res.get("execution_status")).strip().lower())
                    elif s.get("status"):
                        step_statuses.append(str(s.get("status")).strip().lower())
                    elif s.get("execution_status"):
                        step_statuses.append(str(s.get("execution_status")).strip().lower())
            if step_statuses and all(st in SUCCESS_EXECUTION_STATUSES for st in step_statuses):
                raw_status = "completed"

    execution_status = str(raw_status).strip().lower() if raw_status is not None else ""
    generated_content = str(_get_attr_or_key(sealed_artifact, "generated_content", "") or "")
    if not generated_content and isinstance(sealed_artifact, Mapping):
        for k in ("output_text", "content", "result"):
            val = sealed_artifact.get(k)
            if val and isinstance(val, str):
                generated_content = val
                break
        if not generated_content:
            step_results = sealed_artifact.get("step_results")
            if isinstance(step_results, list) and step_results:
                for step in step_results:
                    if isinstance(step, Mapping):
                        sec_res = step.get("section_result")
                        if isinstance(sec_res, Mapping):
                            for k, v in sec_res.items():
                                if (k.endswith("_cli_output_text") or k in ("output_text", "content")) and isinstance(v, str) and v.strip():
                                    generated_content = v
                                    break
    raw_state_diff = _get_attr_or_key(sealed_artifact, "proposed_state_diff", {})
    proposed_state_diff: Mapping[str, Any] = raw_state_diff if isinstance(raw_state_diff, Mapping) else {}
    sovereign_receipt = str(_get_attr_or_key(sealed_artifact, "sovereign_execution_receipt", "") or "")
    state_diff_authorized = bool(_get_attr_or_key(sealed_artifact, "state_diff_authorized", False))

    # 2. Evaluate tool execution status
    tool_execution_success = execution_status in SUCCESS_EXECUTION_STATUSES
    checked_assertions["tool_execution_success"] = tool_execution_success
    if not tool_execution_success:
        failure_reasons.append(
            f"Tool execution status '{execution_status}' is not successful "
            f"(expected one of: {sorted(SUCCESS_EXECUTION_STATUSES)})"
        )

    # 3. Extract execution packet criteria and descriptors
    schema_ref = ""
    packet_success_criteria: tuple[str, ...] = ()
    packet_evidence_requirements: tuple[str, ...] = ()

    if execution_packet is not None:
        schema_ref = str(_get_attr_or_key(execution_packet, "expected_output_schema_ref", "") or "")
        raw_sc = _get_attr_or_key(execution_packet, "success_criteria_refs", ())
        if isinstance(raw_sc, (list, tuple)):
            packet_success_criteria = tuple(str(x) for x in raw_sc)
        raw_ev = _get_attr_or_key(execution_packet, "evidence_requirement_refs", ())
        if isinstance(raw_ev, (list, tuple)):
            packet_evidence_requirements = tuple(str(x) for x in raw_ev)

    # Extract L1 plan expectations
    plan_output_exp: Mapping[str, Any] = {}
    plan_support_exp: Mapping[str, Any] = {}
    if l1_plan is not None:
        raw_oe = _get_attr_or_key(l1_plan, "output_expectation", {})
        if isinstance(raw_oe, Mapping):
            plan_output_exp = raw_oe
        raw_se = _get_attr_or_key(l1_plan, "support_expectation", {})
        if isinstance(raw_se, Mapping):
            plan_support_exp = raw_se

        if not schema_ref:
            schema_ref = str(plan_output_exp.get("schema_ref", "") or "")

    # 4. Evaluate Schema Conformance
    schema_valid = True
    if schema_ref:
        if schema_ref.startswith("json:") or schema_ref.endswith(".json"):
            # Requires valid JSON structure in proposed_state_diff or generated_content
            has_dict = bool(proposed_state_diff)
            parsed_json = False
            if not has_dict and generated_content.strip():
                try:
                    json.loads(generated_content)
                    parsed_json = True
                except Exception:
                    parsed_json = False

            if not (has_dict or parsed_json):
                schema_valid = False
                failure_reasons.append(
                    f"Schema '{schema_ref}' requires valid JSON output, but content is not parseable JSON"
                )
        elif schema_ref.startswith("markdown:") or schema_ref.endswith(".md"):
            # Markdown schema check: must be a string and contain non-whitespace text
            if not generated_content.strip():
                schema_valid = False
                failure_reasons.append(
                    f"Schema '{schema_ref}' requires markdown content, but generated_content is empty"
                )

    # Check custom schema validator if provided
    if custom_assertions and "schema_validator" in custom_assertions:
        validator = custom_assertions["schema_validator"]
        if callable(validator):
            try:
                is_valid = bool(validator(sealed_artifact))
                if not is_valid:
                    schema_valid = False
                    failure_reasons.append("Custom schema_validator rejected the sealed artifact")
            except Exception as exc:
                schema_valid = False
                failure_reasons.append(f"Custom schema_validator raised exception: {exc}")

    checked_assertions["schema_valid"] = schema_valid

    # 5. Evaluate Required Fields and Sections
    required_sections: list[str] = []
    required_keys: list[str] = []

    # From L1 plan
    raw_req_sections = plan_output_exp.get("required_sections")
    if isinstance(raw_req_sections, (list, tuple)):
        required_sections.extend(str(s) for s in raw_req_sections)

    raw_req_fields = plan_output_exp.get("required_fields")
    if isinstance(raw_req_fields, (list, tuple)):
        required_keys.extend(str(f) for f in raw_req_fields)

    # From success criteria refs (e.g. 'require_section:experience', 'require_field:skills')
    for crit in packet_success_criteria:
        if crit.startswith("require_section:"):
            required_sections.append(crit.split("require_section:", 1)[1].strip())
        elif crit.startswith("require_field:"):
            required_keys.append(crit.split("require_field:", 1)[1].strip())

    # Verify sections in markdown
    for sec in required_sections:
        if not _content_contains_section(generated_content, sec):
            missing_fields.append(f"section:{sec}")

    # Verify fields in proposed_state_diff or parsed JSON
    for key in required_keys:
        if key not in proposed_state_diff:
            # Also check if generated_content parses as JSON containing key
            found_in_json = False
            if generated_content.strip():
                try:
                    parsed = json.loads(generated_content)
                    if isinstance(parsed, Mapping) and key in parsed:
                        found_in_json = True
                except Exception:  # guardian: allow-silent-swallow -- fallback if generated_content is not JSON
                    pass
            if not found_in_json:
                missing_fields.append(f"field:{key}")

    required_fields_present = len(missing_fields) == 0
    checked_assertions["required_fields_present"] = required_fields_present
    if not required_fields_present:
        failure_reasons.append(f"Missing required fields/sections: {missing_fields}")

    # 6. Evaluate Evidence Obligations
    all_evidence_requirements: list[str] = list(packet_evidence_requirements)
    raw_plan_ev = plan_support_exp.get("required_fact_ids") or plan_support_exp.get("evidence_ids")
    if isinstance(raw_plan_ev, (list, tuple)):
        for ev in raw_plan_ev:
            ev_str = str(ev).strip()
            if ev_str and ev_str not in all_evidence_requirements:
                all_evidence_requirements.append(ev_str)

    for ev_id in all_evidence_requirements:
        if not _payload_contains_evidence(ev_id, generated_content, proposed_state_diff):
            missing_evidence_ids.append(ev_id)

    evidence_obligations_satisfied = len(missing_evidence_ids) == 0
    checked_assertions["evidence_obligations_satisfied"] = evidence_obligations_satisfied
    if not evidence_obligations_satisfied:
        failure_reasons.append(f"Missing required evidence obligations: {missing_evidence_ids}")

    # 7. Evaluate Explicit Success Criteria
    for crit in packet_success_criteria:
        crit_clean = crit.strip()
        if not crit_clean or crit_clean.startswith("require_section:") or crit_clean.startswith("require_field:"):
            continue

        passed = False
        if crit_clean == "non_empty_content":
            passed = bool(generated_content.strip() or proposed_state_diff)
        elif crit_clean.startswith("min_chars:"):
            try:
                min_chars = int(crit_clean.split(":", 1)[1])
                passed = len(generated_content) >= min_chars
            except ValueError:
                passed = False
        elif crit_clean.startswith("max_chars:"):
            try:
                max_chars = int(crit_clean.split(":", 1)[1])
                passed = len(generated_content) <= max_chars
            except ValueError:
                passed = False
        elif crit_clean.startswith("min_words:"):
            try:
                min_words = int(crit_clean.split(":", 1)[1])
                passed = len(generated_content.split()) >= min_words
            except ValueError:
                passed = False
        elif crit_clean == "sovereign_receipt_present":
            passed = bool(sovereign_receipt)
        elif crit_clean == "state_diff_authorized":
            passed = state_diff_authorized
        else:
            # Unknown criteria default to True unless marked in custom assertions
            passed = True

        checked_assertions[crit_clean] = passed
        if not passed:
            failure_reasons.append(f"Explicit success criterion '{crit_clean}' failed")

    # Evaluate extra custom assertions
    if custom_assertions:
        for name, value in custom_assertions.items():
            if name == "schema_validator":
                continue
            if callable(value):
                try:
                    passed = bool(value(sealed_artifact))
                except Exception as exc:
                    passed = False
                    failure_reasons.append(f"Custom assertion '{name}' raised: {exc}")
            else:
                passed = bool(value)

            checked_assertions[name] = passed
            if not passed:
                failure_reasons.append(f"Custom assertion '{name}' evaluated to False")

    # 8. Compile Final Verdict and Result
    status = "PASS" if len(failure_reasons) == 0 else "FAIL"

    return L1DeterministicCheckResult(
        schema_version=L1_DETERMINISTIC_CHECK_SCHEMA_VERSION,
        status=status,
        tool_execution_success=tool_execution_success,
        schema_valid=schema_valid,
        required_fields_present=required_fields_present,
        missing_fields=tuple(missing_fields),
        missing_evidence_ids=tuple(missing_evidence_ids),
        checked_assertions=checked_assertions,
        failure_reasons=tuple(failure_reasons),
    )


__all__ = [
    "L1_DETERMINISTIC_CHECK_SCHEMA_VERSION",
    "SUCCESS_EXECUTION_STATUSES",
    "l1_post_l2_deterministic_check",
]
