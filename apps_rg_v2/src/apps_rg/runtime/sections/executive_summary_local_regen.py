"""Application-owned bounded same-authority regeneration primitives.

The executive-summary retry path deliberately preserves the original compiled
prompt and appends only a bounded repair turn.  It is implemented here so the
application owns its retry semantics and evidence without a sibling runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping

from apps_rg.runtime.sections.executive_summary_regen_support import (
    DEFAULT_MAX_DELTA_LINES,
    DEFAULT_MAX_DELTA_TOKENS,
    PromptMessages,
    REPAIR_TACTIC_INCREMENTAL_DELTA,
    compute_system_prefix_hash,
    format_regen_delta_user_turn,
    sha256_hex,
)


class AnchorClassification(str, Enum):
    LAST_APPROVED = "LAST_APPROVED"


class DefectClass(str, Enum):
    SOFT_REPAIRABLE = "SOFT_REPAIRABLE"


class TriggerSource(str, Enum):
    X2 = "X2"
    X3_JUDGE = "X3_JUDGE"


class HealOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    REFUSED = "REFUSED"


@dataclass(frozen=True, slots=True)
class IncrementalRepairContract:
    request_id: str
    run_id: str
    trace_root: str
    parent_contract_ref: str
    parent_attempt_receipt_id: str
    replay_key: str
    policy_hash: str
    blueprint_hash: str
    registry_digest_set: tuple[str, ...]
    frozen_compile_ref: str
    prompt_hash: str
    provider_lane: str
    model_lane: str
    parent_provider_lane: str
    parent_model_lane: str
    anchor_output_hash: str
    anchor_output_text: str
    anchor_classification: AnchorClassification
    defect_class: DefectClass
    trigger_source: TriggerSource
    delta_lines: tuple[str, ...]
    semantic_regen_attempt_index: int
    transport_retry_count: int
    max_semantic_regen_attempts: int
    max_delta_tokens: int
    max_delta_lines: int
    prompt_messages: PromptMessages
    expected_system_prefix_hash: str
    nested_heal_without_new_attempt: bool
    runtime_gate_refs: tuple[str, ...]
    l5_governance_context_digest: str


@dataclass(frozen=True, slots=True)
class SameAuthorityRegenReceipt:
    request_id: str
    run_id: str
    accepted: bool
    repair_tactic: str
    next_action: str
    heal_outcome: HealOutcome
    no_prompt_recompile_assertion: bool
    system_prefix_hash: str
    anchor_output_hash: str
    candidate_output_hash: str
    delta_line_count: int
    delta_token_count: int
    provider_request_ref: str
    provider_response_ref: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "apps_rg.same_authority_regen_receipt.v1",
            "request_id": self.request_id,
            "run_id": self.run_id,
            "accepted": self.accepted,
            "repair_tactic": self.repair_tactic,
            "next_action": self.next_action,
            "heal_outcome": self.heal_outcome.value,
            "no_prompt_recompile_assertion": self.no_prompt_recompile_assertion,
            "system_prefix_hash": self.system_prefix_hash,
            "anchor_output_hash": self.anchor_output_hash,
            "candidate_output_hash": self.candidate_output_hash,
            "delta_line_count": self.delta_line_count,
            "delta_token_count": self.delta_token_count,
            "provider_request_ref": self.provider_request_ref,
            "provider_response_ref": self.provider_response_ref,
        }


@dataclass(frozen=True, slots=True)
class RegenRefusal:
    code: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class SameAuthorityRegenResult:
    accepted: bool
    regenerated_text: str
    receipt: SameAuthorityRegenReceipt | None
    refusal: RegenRefusal | None
    chat_messages: tuple[dict[str, str], ...]


def _delta_token_count(lines: tuple[str, ...]) -> int:
    return len(" ".join(lines).split())


def _chat_messages(contract: IncrementalRepairContract) -> tuple[dict[str, str], ...]:
    system, original_user = contract.prompt_messages.to_flat()
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if original_user:
        messages.append({"role": "user", "content": original_user})
    if contract.anchor_output_text:
        messages.append({"role": "assistant", "content": contract.anchor_output_text})
    messages.append(
        {
            "role": "user",
            "content": format_regen_delta_user_turn(contract.delta_lines),
        }
    )
    return tuple(messages)


class SameAuthorityRegenRunner:
    """Run bounded app-owned regeneration with a frozen prompt prefix."""

    def run(
        self,
        contract: IncrementalRepairContract,
        *,
        provider_generate: Callable[[list[dict[str, str]]], Mapping[str, Any]],
        provider_request_ref: str = "",
        provider_response_ref: str = "",
    ) -> SameAuthorityRegenResult:
        messages = _chat_messages(contract)
        actual_prefix_hash = compute_system_prefix_hash(contract.prompt_messages.system_text())
        delta_tokens = _delta_token_count(contract.delta_lines)
        refusal: RegenRefusal | None = None
        if actual_prefix_hash != contract.expected_system_prefix_hash:
            refusal = RegenRefusal("SYSTEM_PREFIX_HASH_MISMATCH", "frozen system prefix changed")
        elif not contract.anchor_output_text:
            refusal = RegenRefusal("ANCHOR_MISSING", "same-authority repair requires an anchor output")
        elif sha256_hex(contract.anchor_output_text) != contract.anchor_output_hash:
            refusal = RegenRefusal("ANCHOR_HASH_MISMATCH", "anchor output does not match its contract hash")
        elif contract.semantic_regen_attempt_index > contract.max_semantic_regen_attempts:
            refusal = RegenRefusal("SEMANTIC_ATTEMPT_EXHAUSTED", "semantic regeneration attempt budget exhausted")
        elif len(contract.delta_lines) > min(contract.max_delta_lines, DEFAULT_MAX_DELTA_LINES):
            refusal = RegenRefusal("DELTA_LINE_LIMIT_EXCEEDED", "repair delta exceeds its line budget")
        elif delta_tokens > min(contract.max_delta_tokens, DEFAULT_MAX_DELTA_TOKENS):
            refusal = RegenRefusal("DELTA_TOKEN_LIMIT_EXCEEDED", "repair delta exceeds its token budget")

        if refusal is not None:
            return SameAuthorityRegenResult(
                accepted=False,
                regenerated_text="",
                receipt=None,
                refusal=refusal,
                chat_messages=messages,
            )

        response = provider_generate([dict(message) for message in messages])
        candidate = str(response.get("content") or "").strip() if isinstance(response, Mapping) else ""
        if not candidate:
            return SameAuthorityRegenResult(
                accepted=False,
                regenerated_text="",
                receipt=None,
                refusal=RegenRefusal("PROVIDER_EMPTY_RESPONSE", "provider returned no repair candidate"),
                chat_messages=messages,
            )
        receipt = SameAuthorityRegenReceipt(
            request_id=contract.request_id,
            run_id=contract.run_id,
            accepted=True,
            repair_tactic=REPAIR_TACTIC_INCREMENTAL_DELTA,
            next_action="X2_POST_REGEN",
            heal_outcome=HealOutcome.ACCEPTED,
            no_prompt_recompile_assertion=True,
            system_prefix_hash=actual_prefix_hash,
            anchor_output_hash=contract.anchor_output_hash,
            candidate_output_hash=sha256_hex(candidate),
            delta_line_count=len(contract.delta_lines),
            delta_token_count=delta_tokens,
            provider_request_ref=str(provider_request_ref),
            provider_response_ref=str(provider_response_ref),
        )
        return SameAuthorityRegenResult(
            accepted=True,
            regenerated_text=candidate,
            receipt=receipt,
            refusal=None,
            chat_messages=messages,
        )


__all__ = [
    "AnchorClassification",
    "DefectClass",
    "HealOutcome",
    "IncrementalRepairContract",
    "RegenRefusal",
    "SameAuthorityRegenReceipt",
    "SameAuthorityRegenResult",
    "SameAuthorityRegenRunner",
    "TriggerSource",
]
