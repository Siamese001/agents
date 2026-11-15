"""8-Slot Prompt Assembly (PA) compiler for apps_lic.

Enforces canonical 8-slot order (S0 > D0 > I0 > C0 > E0 > Y0 > U0 > R0),
NO FABRICATION oath in S0/D0, [fact_id:...] tagged C0 claims matching the
C0 sequence allocation plan, <untrusted_data> XML fencing with breakout
neutralization, and deterministic R0 JSON schema + SHA-256 prompt_hash.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from apps_lic.prompt_assembly.contracts import (
    CANONICAL_SLOT_ORDER,
    DEFAULT_R0_JSON_SCHEMA,
    LOWER_AUTHORITY_SLOTS,
    NO_FABRICATION_OATH_TOKEN,
    PA_COMPILED_SCHEMA_VERSION,
    PromptAssemblyError,
    PromptSlotId,
    PromptSlotSpec,
    R0_REQUIRED_FIELDS,
    SLOT_TO_AUTHORITY,
    UNTRUSTED_CLOSE_TAG,
    UNTRUSTED_OPEN_TAG,
    CompiledOutreachPrompt,
    compute_compiled_prompt_hash,
)

FACT_TAG_PATTERN: re.Pattern[str] = re.compile(r"\[fact_id:([A-Za-z0-9_.:-]+)\]")
EMPTY_FACT_TAG_PATTERN: re.Pattern[str] = re.compile(r"\[fact_id:\s*\]")
BREAKOUT_CLOSE_RE: re.Pattern[str] = re.compile(r"</\s*untrusted_data\s*>", re.IGNORECASE)
BREAKOUT_OPEN_RE: re.Pattern[str] = re.compile(r"<\s*untrusted_data\b[^>]*>", re.IGNORECASE)
SLOT_MARKER_SPOOF_RE: re.Pattern[str] = re.compile(r"<!--\s*SLOT\s*:", re.IGNORECASE)
_C0_STRUCTURAL_HEADERS: frozenset[str] = frozenset(
    {
        "<candidate_facts>",
        "</candidate_facts>",
        "<candidate_evidence>",
        "</candidate_evidence>",
        "candidate evidence:",
        "verified candidate facts:",
        "allocated candidate facts:",
    }
)


def neutralize_untrusted_breakouts(raw_text: str) -> str:
    """Neutralize any embedded <untrusted_data> or </untrusted_data> breakout tags."""
    cleaned = BREAKOUT_CLOSE_RE.sub("[NEUTRALIZED_UNTRUSTED_CLOSE]", str(raw_text or ""))
    return BREAKOUT_OPEN_RE.sub("[NEUTRALIZED_UNTRUSTED_OPEN]", cleaned)


def fence_untrusted_text(raw_text: str) -> str:
    """Wrap untrusted text in <untrusted_data>...</untrusted_data> and neutralize breakouts."""
    stripped = str(raw_text or "").strip()
    if stripped.lower().startswith(UNTRUSTED_OPEN_TAG) and stripped.lower().endswith(UNTRUSTED_CLOSE_TAG):
        inner = stripped[len(UNTRUSTED_OPEN_TAG) : len(stripped) - len(UNTRUSTED_CLOSE_TAG)].strip()
    else:
        inner = stripped
    sanitized = neutralize_untrusted_breakouts(inner)
    return f"{UNTRUSTED_OPEN_TAG}\n{sanitized}\n{UNTRUSTED_CLOSE_TAG}"


def _sanitize_embedded_untrusted_block(text: str) -> tuple[str, str, bool]:
    """Extract and sanitize any <untrusted_data>...</untrusted_data> span inside a slot."""
    lower = text.lower()
    first_open, last_close = lower.find(UNTRUSTED_OPEN_TAG), lower.rfind(UNTRUSTED_CLOSE_TAG)
    if first_open == -1 and last_close == -1:
        return text, text, False
    if first_open == -1 or last_close == -1 or last_close < first_open:
        sanitized = neutralize_untrusted_breakouts(text)
        return sanitized, sanitized, False
    before = text[:first_open]
    inner = text[first_open + len(UNTRUSTED_OPEN_TAG) : last_close].strip()
    after = text[last_close + len(UNTRUSTED_CLOSE_TAG) :]
    fenced_block = fence_untrusted_text(inner)
    return f"{before}{fenced_block}{after}", f"{before}\n{after}", True


def validate_canonical_slot_order(
    slot_ids: Sequence[str | PromptSlotId | PromptSlotSpec],
) -> tuple[str, ...]:
    """Validate that slot_ids match strict 8-slot order S0 > D0 > I0 > C0 > E0 > Y0 > U0 > R0."""
    normalized = [
        str(item.slot_id).strip()
        if isinstance(item, PromptSlotSpec)
        else (item.value if isinstance(item, PromptSlotId) else str(item).strip())
        for item in slot_ids
    ]
    canonical_set = set(CANONICAL_SLOT_ORDER)
    seen: set[str] = set()
    for sid in normalized:
        if sid not in canonical_set:
            raise PromptAssemblyError(
                f"Unauthorized or unknown override slot '{sid}'; allowed: {CANONICAL_SLOT_ORDER}",
                code="UNAUTHORIZED_SLOT_ID",
                slot_id=sid,
            )
        if sid in seen:
            raise PromptAssemblyError(f"Duplicate slot '{sid}'.", code="DUPLICATE_SLOT_ID", slot_id=sid)
        seen.add(sid)

    missing = [s for s in CANONICAL_SLOT_ORDER if s not in seen]
    if missing:
        raise PromptAssemblyError(f"Missing required PA slots: {missing}", code="MISSING_CANONICAL_SLOTS", slot_id=missing[0])
    if tuple(normalized) != CANONICAL_SLOT_ORDER:
        raise PromptAssemblyError(
            f"Invalid slot order {tuple(normalized)}; must strictly follow {CANONICAL_SLOT_ORDER}",
            code="INVALID_SLOT_ORDER",
        )
    return CANONICAL_SLOT_ORDER


def validate_no_fabrication_oath(s0_content: str, d0_content: str = "") -> None:
    """Enforce 'NO FABRICATION' oath presence in S0/D0; fails closed if omitted."""
    s0_text, d0_text = str(s0_content or "").strip(), str(d0_content or "").strip()
    if not s0_text:
        raise PromptAssemblyError("S0 slot cannot be empty.", code="EMPTY_S0_SLOT", slot_id="S0")
    if NO_FABRICATION_OATH_TOKEN not in s0_text:
        raise PromptAssemblyError(
            f"S0/D0 must include '{NO_FABRICATION_OATH_TOKEN}' oath; failed closed.",
            code="MISSING_NO_FABRICATION_OATH",
            slot_id="S0",
        )
    if not d0_text:
        raise PromptAssemblyError("D0 boundary slot cannot be empty.", code="EMPTY_D0_SLOT", slot_id="D0")


def _extract_allowed_facts_from_plan(
    allocation_plan: Any, touch_number: int
) -> tuple[set[str], list[str], str, str]:
    """Extract allowed fact_ids, formatted claim lines, plan digest, and db sha256 from plan."""
    if allocation_plan is None:
        return set(), [], "", ""
    plan_dict: Mapping[str, Any] = (
        allocation_plan.to_dict()
        if hasattr(allocation_plan, "to_dict")
        else (allocation_plan if isinstance(allocation_plan, Mapping) else {})
    )
    if not plan_dict:
        return set(), [], "", ""

    plan_digest = str(plan_dict.get("allocation_plan_digest") or "")
    db_sha256 = str(plan_dict.get("candidate_graph_db_sha256") or "")
    by_touch = plan_dict.get("allocated_fact_ids_by_touch") or {}
    raw_list = (by_touch.get(touch_number) or by_touch.get(str(touch_number)) or []) if isinstance(by_touch, Mapping) else []
    touch_ids = [str(x).strip() for x in raw_list if str(x).strip()]

    claim_lines: list[str] = []
    all_plan_ids: set[str] = set(touch_ids)
    for assign in plan_dict.get("assignments") or ():
        a_dict = assign.to_dict() if hasattr(assign, "to_dict") else (assign if isinstance(assign, Mapping) else {})
        for fid in a_dict.get("allocated_fact_ids") or ():
            if str(fid).strip():
                all_plan_ids.add(str(fid).strip())
        if int(a_dict.get("touch_number") or 0) == int(touch_number):
            for f_obj in a_dict.get("allocated_facts") or ():
                if isinstance(f_obj, Mapping):
                    fid = str(f_obj.get("fact_id") or "").strip()
                    stmt = str(f_obj.get("raw_text") or f_obj.get("statement") or "").strip()
                    if fid and stmt:
                        claim_lines.append(f"[fact_id:{fid}] {stmt}")
            if not claim_lines:
                claim_lines.extend(
                    f"[fact_id:{str(fid).strip()}] Allocated candidate proof claim."
                    for fid in (a_dict.get("allocated_fact_ids") or ())
                    if str(fid).strip()
                )
    return (set(touch_ids) if touch_ids else all_plan_ids), claim_lines, plan_digest, db_sha256


def validate_c0_claims(
    c0_content: str | Sequence[str],
    *,
    allowed_fact_ids: Sequence[str] | set[str] | None = None,
) -> tuple[str, ...]:
    """Validate that every candidate claim in C0 has a valid [fact_id:...] tag."""
    if isinstance(c0_content, str):
        _, non_untrusted, _ = _sanitize_embedded_untrusted_block(c0_content)
        raw_lines = [ln.strip() for ln in non_untrusted.splitlines() if ln.strip()]
    else:
        raw_lines = [str(item).strip() for item in c0_content if str(item).strip()]

    claim_lines = [
        ln
        for ln in raw_lines
        if ln.lower() not in _C0_STRUCTURAL_HEADERS and not ln.startswith("<!--") and not ln.startswith("#")
    ]
    if not claim_lines:
        raise PromptAssemblyError("C0 requires at least one [fact_id:...] claim.", code="EMPTY_C0_CLAIMS", slot_id="C0")

    extracted_fact_ids: list[str] = []
    for line in claim_lines:
        if EMPTY_FACT_TAG_PATTERN.search(line):
            raise PromptAssemblyError(f"Empty [fact_id:] tag in C0: {line!r}", code="EMPTY_FACT_ID_TAG", slot_id="C0")
        tags = FACT_TAG_PATTERN.findall(line)
        if not tags:
            raise PromptAssemblyError(f"Untagged candidate claim in C0: {line!r}", code="UNTAGGED_C0_CLAIM", slot_id="C0")
        for tag in tags:
            if tag not in extracted_fact_ids:
                extracted_fact_ids.append(tag)

    if allowed_fact_ids is not None:
        allowed_set = {str(fid).strip() for fid in allowed_fact_ids if str(fid).strip()}
        if not allowed_set:
            raise PromptAssemblyError("C0 allowed_fact_ids is empty.", code="EMPTY_ALLOWED_FACT_IDS", slot_id="C0")
        for fid in extracted_fact_ids:
            if fid not in allowed_set:
                raise PromptAssemblyError(
                    f"C0 claim [fact_id:{fid}] not in C0 allocation plan {sorted(allowed_set)}.",
                    code="UNALLOCATED_C0_FACT_ID",
                    slot_id="C0",
                )
    return tuple(extracted_fact_ids)


def validate_r0_schema(r0_input: Mapping[str, Any] | str | None = None) -> dict[str, Any]:
    """Validate and return deterministic R0 output JSON schema contract."""
    if r0_input is None:
        schema = copy.deepcopy(DEFAULT_R0_JSON_SCHEMA)
    elif isinstance(r0_input, Mapping):
        schema = copy.deepcopy(dict(r0_input))
    elif isinstance(r0_input, str):
        stripped = r0_input.strip()
        if not stripped:
            raise PromptAssemblyError("R0 schema slot cannot be empty.", code="EMPTY_R0_SCHEMA", slot_id="R0")
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise PromptAssemblyError(f"Invalid R0 JSON: {exc}", code="INVALID_R0_JSON", slot_id="R0") from exc
            if not isinstance(parsed, dict):
                raise PromptAssemblyError("R0 JSON must be an object.", code="INVALID_R0_TYPE", slot_id="R0")
            schema = parsed
        else:
            schema = copy.deepcopy(DEFAULT_R0_JSON_SCHEMA)
    else:
        raise PromptAssemblyError(f"Unsupported R0 type: {type(r0_input).__name__}", code="INVALID_R0_TYPE", slot_id="R0")

    props, req = schema.get("properties"), schema.get("required")
    if not isinstance(props, Mapping) or not isinstance(req, Sequence):
        raise PromptAssemblyError("R0 schema requires 'properties' and 'required'.", code="MALFORMED_R0_SCHEMA", slot_id="R0")
    missing_fields = [f for f in R0_REQUIRED_FIELDS if f not in props or f not in req]
    if missing_fields:
        raise PromptAssemblyError(f"R0 missing required fields: {missing_fields}", code="MISSING_R0_CONTRACT_FIELDS", slot_id="R0")
    return schema


class OutreachPromptCompiler:
    """Deterministic 8-slot Prompt Assembly compiler for apps_lic."""

    def __init__(self, registry_path: Path | str | None = None) -> None:
        self.registry_path = (
            Path(registry_path) if registry_path is not None else Path(__file__).resolve().parent / "prompt_registry.yaml"
        )
        self._registry_cache: dict[str, Any] | None = None

    def load_registry(self) -> dict[str, Any]:
        """Load and cache prompt_registry.yaml."""
        if self._registry_cache is not None:
            return self._registry_cache
        if not self.registry_path.is_file():
            raise PromptAssemblyError(f"Missing {self.registry_path}", code="MISSING_PROMPT_REGISTRY")
        with open(self.registry_path, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
        if not isinstance(loaded, dict):
            raise PromptAssemblyError("Invalid prompt_registry.yaml", code="INVALID_PROMPT_REGISTRY")
        self._registry_cache = loaded
        return loaded

    def validate_slot_order(self, slot_ids: Sequence[str | PromptSlotId | PromptSlotSpec]) -> tuple[str, ...]:
        """Validate strict canonical 8-slot ordering S0 > D0 > I0 > C0 > E0 > Y0 > U0 > R0."""
        return validate_canonical_slot_order(slot_ids)

    def fence_untrusted(self, raw_text: str) -> str:
        """Wrap untrusted text in <untrusted_data>...</untrusted_data> and neutralize breakouts."""
        return fence_untrusted_text(raw_text)

    def _default_slot_body(self, slot_id: str) -> str:
        slots_cfg = self.load_registry().get("slots") or {}
        return str((slots_cfg.get(slot_id) or {}).get("default_body") or "").strip()

    def compile(
        self,
        slots: Sequence[PromptSlotSpec] | Mapping[str, str | PromptSlotSpec] | None = None,
        *,
        template_id: str = "outreach_draft_v2",
        touch_number: int = 1,
        s0: str | None = None,
        d0: str | None = None,
        i0: str | None = None,
        c0: str | Sequence[str] | None = None,
        e0: str | None = None,
        y0: str | None = None,
        u0: str | None = None,
        r0: str | Mapping[str, Any] | None = None,
        candidate_claims: Sequence[str] | None = None,
        untrusted_brief: str | None = None,
        opportunity_brief: str | None = None,
        allowed_fact_ids: Sequence[str] | set[str] | None = None,
        allocation_plan: Any = None,
        allocation_plan_digest: str = "",
        candidate_graph_db_sha256: str = "",
        slot_order: Sequence[str | PromptSlotId] | None = None,
    ) -> CompiledOutreachPrompt:
        """Compile and validate an 8-slot outreach prompt artifact."""
        if slot_order is not None:
            validate_canonical_slot_order(slot_order)

        plan_allowed, plan_claims, plan_digest, plan_db_sha = _extract_allowed_facts_from_plan(allocation_plan, touch_number)
        eff_plan_digest = allocation_plan_digest or plan_digest or "sha256:unadorned_allocation_plan"
        eff_db_sha = candidate_graph_db_sha256 or plan_db_sha or "sha256:unadorned_candidate_graph"
        eff_allowed_ids: set[str] | None = (
            {str(x).strip() for x in allowed_fact_ids if str(x).strip()}
            if allowed_fact_ids is not None
            else (plan_allowed if plan_allowed else None)
        )

        raw_slot_map: dict[str, str] = {}
        explicit_r0: Mapping[str, Any] | str | None = r0
        if slots is not None:
            if isinstance(slots, Mapping):
                validate_canonical_slot_order(list(slots.keys()))
                for k, v in slots.items():
                    sid = k.value if isinstance(k, PromptSlotId) else str(k).strip()
                    raw_slot_map[sid] = v.content if isinstance(v, PromptSlotSpec) else str(v)
            elif isinstance(slots, Sequence):
                validate_canonical_slot_order(slots)
                for item in slots:
                    if not isinstance(item, PromptSlotSpec):
                        raise PromptAssemblyError("Expected PromptSlotSpec in slots.", code="INVALID_SLOT_SPEC")
                    raw_slot_map[str(item.slot_id)] = item.content
            else:
                raise PromptAssemblyError("Invalid slots container.", code="INVALID_SLOTS_CONTAINER")
            if explicit_r0 is None and "R0" in raw_slot_map:
                explicit_r0 = raw_slot_map["R0"]
        else:
            for sid, val in (("S0", s0), ("D0", d0), ("I0", i0), ("E0", e0), ("Y0", y0)):
                raw_slot_map[sid] = val if val is not None else self._default_slot_body(sid)
            c0_parts: list[str] = []
            if isinstance(c0, str) and c0.strip():
                c0_parts.append(c0.strip())
            elif isinstance(c0, Sequence) and not isinstance(c0, str):
                c0_parts.extend(str(x).strip() for x in c0 if str(x).strip())
            if candidate_claims is not None:
                c0_parts.extend(str(x).strip() for x in candidate_claims if str(x).strip())
            if not c0_parts and plan_claims:
                c0_parts.extend(plan_claims)
            raw_slot_map["C0"] = "\n".join(c0_parts)
            u0_base = u0 if u0 is not None else self._default_slot_body("U0")
            brief_text = untrusted_brief if untrusted_brief is not None else opportunity_brief
            raw_slot_map["U0"] = (f"{u0_base}\n{brief_text}".strip() if u0_base else str(brief_text)) if brief_text is not None else u0_base

        validate_no_fabrication_oath(raw_slot_map.get("S0", ""), raw_slot_map.get("D0", ""))
        c0_sanitized, _, c0_had_fence = _sanitize_embedded_untrusted_block(raw_slot_map.get("C0", ""))
        if candidate_claims is not None and slots is not None:
            validate_c0_claims(candidate_claims, allowed_fact_ids=eff_allowed_ids)
        validated_facts = validate_c0_claims(c0_sanitized, allowed_fact_ids=eff_allowed_ids)
        raw_slot_map["C0"] = c0_sanitized

        u0_raw = raw_slot_map.get("U0", "")
        if not str(u0_raw).strip():
            raise PromptAssemblyError("U0 slot cannot be empty.", code="EMPTY_U0_SLOT", slot_id="U0")
        if slots is not None and (untrusted_brief is not None or opportunity_brief is not None):
            extra_brief = untrusted_brief if untrusted_brief is not None else opportunity_brief
            u0_raw = f"{u0_raw}\n{extra_brief}".strip()
        raw_slot_map["U0"] = fence_untrusted_text(u0_raw)

        r0_schema = validate_r0_schema(explicit_r0)
        raw_slot_map["R0"] = json.dumps(r0_schema, sort_keys=True, separators=(",", ":"))

        built_slots: list[PromptSlotSpec] = []
        slot_digests: dict[str, str] = {}
        rendered_sections: list[str] = []
        for sid in CANONICAL_SLOT_ORDER:
            content = str(raw_slot_map.get(sid, "")).strip()
            if not content:
                raise PromptAssemblyError(f"Slot '{sid}' cannot be empty.", code="EMPTY_REQUIRED_SLOT", slot_id=sid)
            if sid in LOWER_AUTHORITY_SLOTS and SLOT_MARKER_SPOOF_RE.search(content):
                raise PromptAssemblyError(f"Slot '{sid}' contains spoofed marker.", code="SPOOFED_SLOT_MARKER", slot_id=sid)
            spec = PromptSlotSpec(
                slot_id=sid,
                content=content,
                authority=SLOT_TO_AUTHORITY[sid],
                source_tag="candidate_evidence" if sid == "C0" else ("untrusted_data" if sid == "U0" else ""),
                fenced=(sid == "U0") or (sid == "C0" and c0_had_fence),
            )
            built_slots.append(spec)
            slot_digests[sid] = spec.slot_digest
            rendered_sections.append(f"<!-- SLOT: {sid} ({spec.authority}) -->\n{content}")

        rendered_prompt = "\n\n".join(rendered_sections)
        untrusted_fenced = UNTRUSTED_OPEN_TAG in rendered_prompt and UNTRUSTED_CLOSE_TAG in rendered_prompt
        prompt_hash = compute_compiled_prompt_hash(
            slot_order=CANONICAL_SLOT_ORDER,
            slot_digests=slot_digests,
            rendered_prompt=rendered_prompt,
            r0_json_schema=r0_schema,
            allocation_plan_digest=eff_plan_digest,
            candidate_graph_db_sha256=eff_db_sha,
            template_id=template_id,
            touch_number=touch_number,
            schema_version=PA_COMPILED_SCHEMA_VERSION,
        )
        return CompiledOutreachPrompt(
            prompt_hash=prompt_hash,
            allocation_plan_digest=eff_plan_digest,
            candidate_graph_db_sha256=eff_db_sha,
            slot_order=CANONICAL_SLOT_ORDER,
            slot_digests=slot_digests,
            rendered_prompt=rendered_prompt,
            r0_json_schema=r0_schema,
            untrusted_fenced=untrusted_fenced,
            template_id=template_id,
            touch_number=touch_number,
            slots=tuple(built_slots),
            validated_fact_ids=validated_facts,
            has_no_fabrication_oath=True,
        )


def compile_outreach_prompt(
    slots: Sequence[PromptSlotSpec] | Mapping[str, str | PromptSlotSpec] | None = None,
    *,
    registry_path: Path | str | None = None,
    **kwargs: Any,
) -> CompiledOutreachPrompt:
    """Module-level convenience entrypoint for 8-slot OutreachPromptCompiler."""
    return OutreachPromptCompiler(registry_path=registry_path).compile(slots, **kwargs)


__all__ = [
    "FACT_TAG_PATTERN",
    "OutreachPromptCompiler",
    "compile_outreach_prompt",
    "fence_untrusted_text",
    "neutralize_untrusted_breakouts",
    "validate_c0_claims",
    "validate_canonical_slot_order",
    "validate_no_fabrication_oath",
    "validate_r0_schema",
]
