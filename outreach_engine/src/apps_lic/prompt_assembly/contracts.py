"""Frozen contracts for the apps_lic 8-slot Prompt Assembly (PA) subsystem.

Enforces canonical slot ordering (S0 > D0 > I0 > C0 > E0 > Y0 > U0 > R0),
NO FABRICATION oath governance, C0 [fact_id:...] claim binding, <untrusted_data>
XML fencing, and deterministic R0 JSON schema output contracts.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

PA_COMPILED_SCHEMA_VERSION = "apps_lic.compiled_outreach_prompt.v1"
NO_FABRICATION_OATH_TOKEN = "NO FABRICATION"
UNTRUSTED_OPEN_TAG = "<untrusted_data>"
UNTRUSTED_CLOSE_TAG = "</untrusted_data>"


class PromptSlotId(str, Enum):
    """Canonical 8-slot Prompt Assembly identifiers in strict authority order."""

    S0 = "S0"
    D0 = "D0"
    I0 = "I0"
    C0 = "C0"
    E0 = "E0"
    Y0 = "Y0"
    U0 = "U0"
    R0 = "R0"


CANONICAL_SLOT_ORDER: tuple[str, ...] = (
    PromptSlotId.S0.value,
    PromptSlotId.D0.value,
    PromptSlotId.I0.value,
    PromptSlotId.C0.value,
    PromptSlotId.E0.value,
    PromptSlotId.Y0.value,
    PromptSlotId.U0.value,
    PromptSlotId.R0.value,
)


class SlotAuthority(str, Enum):
    """Authority classes for the 8-slot prompt assembly model."""

    SYSTEM_AUTHORITY = "SYSTEM_AUTHORITY"
    BINDING_AUTHORITY = "BINDING_AUTHORITY"
    GOVERNED_AUTHORITY = "GOVERNED_AUTHORITY"
    INFORMATIONAL_AUTHORITY = "INFORMATIONAL_AUTHORITY"
    EXAMPLE_AUTHORITY = "EXAMPLE_AUTHORITY"
    STYLE_AUTHORITY = "STYLE_AUTHORITY"
    ZERO_AUTHORITY = "ZERO_AUTHORITY"
    SCHEMA_AUTHORITY = "SCHEMA_AUTHORITY"


SLOT_TO_AUTHORITY: dict[str, SlotAuthority] = {
    "S0": SlotAuthority.SYSTEM_AUTHORITY,
    "D0": SlotAuthority.BINDING_AUTHORITY,
    "I0": SlotAuthority.GOVERNED_AUTHORITY,
    "C0": SlotAuthority.INFORMATIONAL_AUTHORITY,
    "E0": SlotAuthority.EXAMPLE_AUTHORITY,
    "Y0": SlotAuthority.STYLE_AUTHORITY,
    "U0": SlotAuthority.ZERO_AUTHORITY,
    "R0": SlotAuthority.SCHEMA_AUTHORITY,
}

SLOT_AUTHORITY_PRECEDENCE: dict[str, int] = {
    "S0": 80,
    "D0": 70,
    "I0": 60,
    "C0": 50,
    "E0": 40,
    "Y0": 30,
    "U0": 20,
    "R0": 10,
}

PROTECTED_SLOTS: frozenset[str] = frozenset({"S0", "D0", "I0", "R0"})
LOWER_AUTHORITY_SLOTS: frozenset[str] = frozenset({"C0", "E0", "Y0", "U0"})

R0_REQUIRED_FIELDS: tuple[str, ...] = (
    "touch_number",
    "subject",
    "body",
    "cited_fact_ids",
    "metric_bindings",
)

DEFAULT_R0_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "OutreachTouchResponseContract",
    "type": "object",
    "additionalProperties": False,
    "required": list(R0_REQUIRED_FIELDS),
    "properties": {
        "touch_number": {"type": "integer", "minimum": 1},
        "subject": {"type": "string"},
        "body": {"type": "string", "minLength": 1},
        "cited_fact_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "metric_bindings": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    },
}


class PromptAssemblyError(ValueError):
    """Fail-closed error raised on PA slot order, oath, fencing, or C0 tag violations."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "PA_COMPILATION_ERROR",
        slot_id: str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = str(code)
        self.message = str(message)
        self.slot_id = str(slot_id) if slot_id is not None else None
        self.context: dict[str, Any] = dict(context) if context else {}
        formatted = f"[{self.code}] {self.message}"
        if self.slot_id:
            formatted += f" (slot={self.slot_id})"
        super().__init__(formatted)


@dataclass(frozen=True, slots=True)
class PromptSlotSpec:
    """Frozen specification for a single slot in the 8-slot PA pipeline."""

    slot_id: PromptSlotId | str
    content: str
    authority: SlotAuthority | str = ""
    source_tag: str = ""
    fenced: bool = False
    slot_digest: str = ""

    def __post_init__(self) -> None:
        norm_id = (
            self.slot_id.value
            if isinstance(self.slot_id, PromptSlotId)
            else str(self.slot_id).strip()
        )
        object.__setattr__(self, "slot_id", norm_id)
        if not self.authority:
            auth = SLOT_TO_AUTHORITY.get(norm_id, SlotAuthority.ZERO_AUTHORITY)
            object.__setattr__(self, "authority", auth.value)
        elif isinstance(self.authority, SlotAuthority):
            object.__setattr__(self, "authority", self.authority.value)
        if not self.slot_digest:
            digest = hashlib.sha256(str(self.content).encode("utf-8")).hexdigest()
            object.__setattr__(self, "slot_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this slot spec."""
        return {
            "slot_id": str(self.slot_id),
            "content": self.content,
            "authority": str(self.authority),
            "source_tag": self.source_tag,
            "fenced": self.fenced,
            "slot_digest": self.slot_digest,
        }


def compute_compiled_prompt_hash(
    *,
    slot_order: tuple[str, ...],
    slot_digests: Mapping[str, str],
    rendered_prompt: str,
    r0_json_schema: Mapping[str, Any],
    allocation_plan_digest: str,
    candidate_graph_db_sha256: str,
    template_id: str = "outreach_draft_v2",
    touch_number: int = 1,
    schema_version: str = PA_COMPILED_SCHEMA_VERSION,
) -> str:
    """Compute a deterministic SHA-256 hex digest over the canonical compiled prompt."""
    payload = {
        "schema_version": schema_version,
        "template_id": template_id,
        "touch_number": int(touch_number),
        "slot_order": list(slot_order),
        "slot_digests": {str(k): str(v) for k, v in sorted(slot_digests.items())},
        "rendered_prompt": rendered_prompt,
        "r0_json_schema": dict(r0_json_schema),
        "allocation_plan_digest": str(allocation_plan_digest),
        "candidate_graph_db_sha256": str(candidate_graph_db_sha256),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class CompiledOutreachPrompt:
    """Immutable compiled 8-slot outreach prompt with cryptographic lineage."""

    prompt_hash: str
    allocation_plan_digest: str
    candidate_graph_db_sha256: str
    slot_order: tuple[str, ...]
    slot_digests: dict[str, str]
    rendered_prompt: str
    r0_json_schema: dict[str, Any]
    untrusted_fenced: bool
    template_id: str = "outreach_draft_v2"
    touch_number: int = 1
    slots: tuple[PromptSlotSpec, ...] = ()
    validated_fact_ids: tuple[str, ...] = ()
    has_no_fabrication_oath: bool = True
    schema_version: str = PA_COMPILED_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def verify_hash(self) -> bool:
        """Verify that prompt_hash matches the recomputed canonical SHA-256 digest."""
        expected = compute_compiled_prompt_hash(
            slot_order=self.slot_order,
            slot_digests=self.slot_digests,
            rendered_prompt=self.rendered_prompt,
            r0_json_schema=self.r0_json_schema,
            allocation_plan_digest=self.allocation_plan_digest,
            candidate_graph_db_sha256=self.candidate_graph_db_sha256,
            template_id=self.template_id,
            touch_number=self.touch_number,
            schema_version=self.schema_version,
        )
        return self.prompt_hash == expected

    def to_dict(self) -> dict[str, Any]:
        """Serialize compiled prompt artifact to a JSON-compatible dictionary."""
        return {
            "schema_version": self.schema_version,
            "prompt_hash": self.prompt_hash,
            "allocation_plan_digest": self.allocation_plan_digest,
            "candidate_graph_db_sha256": self.candidate_graph_db_sha256,
            "template_id": self.template_id,
            "touch_number": self.touch_number,
            "slot_order": list(self.slot_order),
            "slot_digests": dict(self.slot_digests),
            "rendered_prompt": self.rendered_prompt,
            "r0_json_schema": copy.deepcopy(self.r0_json_schema),
            "untrusted_fenced": self.untrusted_fenced,
            "validated_fact_ids": list(self.validated_fact_ids),
            "has_no_fabrication_oath": self.has_no_fabrication_oath,
            "slots": [s.to_dict() for s in self.slots],
            "metadata": dict(self.metadata),
        }


__all__ = [
    "CANONICAL_SLOT_ORDER",
    " CompiledOutreachPrompt".strip(),
    "DEFAULT_R0_JSON_SCHEMA",
    "LOWER_AUTHORITY_SLOTS",
    "NO_FABRICATION_OATH_TOKEN",
    "PA_COMPILED_SCHEMA_VERSION",
    "PROTECTED_SLOTS",
    "PromptAssemblyError",
    "PromptSlotId",
    "PromptSlotSpec",
    "R0_REQUIRED_FIELDS",
    "SLOT_AUTHORITY_PRECEDENCE",
    "SLOT_TO_AUTHORITY",
    "SlotAuthority",
    "UNTRUSTED_CLOSE_TAG",
    "UNTRUSTED_OPEN_TAG",
    "compute_compiled_prompt_hash",
]
