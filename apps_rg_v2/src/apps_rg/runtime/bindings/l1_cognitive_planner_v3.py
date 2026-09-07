"""Source-bound, advisory cognitive planning for the Apps RG L1 boundary.

V3 is deliberately separate from the compatibility v1/v2 capsules.  It
improves the planner's representation and self-checking without taking route,
evidence, prompt, execution, model, tool, state-write, or release authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_planning_capsule import FrozenDict, _freeze
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    L1PlanningV2IntegrityError,
    _classify_requirement,
    _declared_jd_hash,
    _inline_jd_text,
    _load_taxonomy,
    _modality,
    _qualifiers,
    build_apps_rg_l1_planning_capsule_v2,
    verify_apps_rg_l1_planning_capsule_v2,
)


L1_COGNITIVE_V3_SCHEMA_VERSION: Final[str] = "apps_rg.l1_cognitive_plan.v3"
L1_COGNITIVE_V3_REVISION_SCHEMA_VERSION: Final[str] = "apps_rg.l1_cognitive_revision.v2"
_AUTHORITY_CLASS: Final[str] = "PLANNING_ADVISORY_ONLY"
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_FORBIDDEN_AUTHORITY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "route_id",
        "route_family",
        "selected_route",
        "evidence_items",
        "evidence_refs",
        "provider",
        "model",
        "tool_call",
        "write_path",
        "release_approval",
    }
)
_VALID_COVERAGE: Final[frozenset[str]] = frozenset({"MAPPED", "ESCALATED", "UNMAPPED"})
_VALID_C0_FAILURE_OUTCOMES: Final[frozenset[str]] = frozenset(
    {"C0_CONTRADICTED", "C0_INSUFFICIENT"}
)
_RELATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\s+(?P<relation>and|or|but\s+not|except|unless)\s+",
    re.IGNORECASE,
)
_EXPLICIT_SENTENCE_BOUNDARY_RE: Final[re.Pattern[str]] = re.compile(
    r"[.;](?=\s+[A-Za-z])"
)
_ACTION_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?:must|should|need\s+to|have\s+to|be\s+able\s+to)\s+)?"
    r"(?P<verb>have|lead|own|manage|build|deliver|drive|demonstrate|ensure|"
    r"create|develop|maintain|operate|scale|architect|design|govern|partner|"
    r"influence|communicate|hire|mentor)\b",
    re.IGNORECASE,
)
_COORDINATED_REQUIREMENT_HEAD_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:strategy|governance|engineering|operations|leadership|infrastructure|"
    r"architecture|delivery|ownership|experience|platform|systems|programs|"
    r"organization|team|portfolio|roadmap|p&l)\b",
    re.IGNORECASE,
)
_BULLET_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^(?:[-*\u2022]+|\d+[.)])\s*")
_RELATION_TYPES: Final[frozenset[str]] = frozenset({"AND", "OR", "NOT", "EXCEPTION"})
_GOAL_CONSTRAINT_FRAME_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_goal_constraint_frame.v3"
)
_ALTERNATIVE_PLAN_LEDGER_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_alternative_plan_ledger.v4"
)
_CONTEXT_CONSTRAINT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "allow_test_l5_cert_ref",
        "auto_research_internal",
        "auto_research_tavily",
        "briefing_text",
        "caller_app_id",
        "generation_mode",
        "l1_cognitive_treatment_arm",
        "research_via",
        "source_channel",
    }
)
_SECTION_SCOPE_CONSTRAINT_KEYS: Final[frozenset[str]] = frozenset(
    {"section_id", "sections"}
)
_SAFE_OUTPUT_FORMAT_CODES: Final[dict[str, str]] = {
    "cv": "CURRICULUM_VITAE",
    "curriculum_vitae": "CURRICULUM_VITAE",
    "executive_resume": "EXECUTIVE_RESUME",
    "json": "JSON",
    "markdown": "MARKDOWN",
    "resume": "RESUME",
}
_OUTPUT_FORMAT_FAMILY_BY_CODE: Final[dict[str, str]] = {
    "CURRICULUM_VITAE": "CURRICULUM_VITAE",
    "EXECUTIVE_RESUME": "RESUME",
    "JSON": "JSON",
    "MARKDOWN": "MARKDOWN",
    "RESUME": "RESUME",
}
_SAFE_STYLE_CODES: Final[dict[str, str]] = {
    "concise": "CONCISE",
    "executive": "EXECUTIVE",
    "formal": "FORMAL",
    "professional": "PROFESSIONAL",
}
_SAFE_BOOLEAN_CONSTRAINT_DIRECTIVES: Final[dict[str, tuple[str, str, str]]] = {
    "exclude_first_person": ("EXCLUSION", "FORBID", "FIRST_PERSON"),
    "forbid_first_person": ("EXCLUSION", "FORBID", "FIRST_PERSON"),
    "include_executive_summary": (
        "INCLUSION",
        "REQUIRE",
        "EXECUTIVE_SUMMARY",
    ),
    "include_headline": ("INCLUSION", "REQUIRE", "HEADLINE"),
    "no_first_person": ("EXCLUSION", "FORBID", "FIRST_PERSON"),
}
_VALID_CONSTRAINT_SEMANTIC_KINDS: Final[frozenset[str]] = frozenset(
    {
        "EXCLUSION",
        "INCLUSION",
        "LENGTH_LIMIT",
        "OUTPUT_FORMAT",
        "SECTION_SCOPE",
        "STYLE",
        "SYSTEM_CONTEXT",
        "UNKNOWN",
    }
)
_VALID_CONSTRAINT_POLARITIES: Final[frozenset[str]] = frozenset(
    {"CONFLICT", "CONTEXT", "FORBID", "PREFER", "REQUIRE", "SCOPE"}
)
_VALID_CONSTRAINT_SCOPES: Final[frozenset[str]] = frozenset(
    {
        "CONTENT",
        "INGRESS_CONTEXT",
        "SECTION_SELECTION",
        "UNRESOLVED",
        "WHOLE_OUTPUT",
    }
)
_VALID_CONSTRAINT_INTERPRETATION_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "ACTIONABLE",
        "CONFLICT",
        "DEFERRED_PREFERENCE",
        "OUT_OF_SCOPE",
        "REVIEW_REQUIRED",
    }
)
_VALID_CONSTRAINT_DOWNSTREAM_HANDLING: Final[frozenset[str]] = frozenset(
    {
        "GOVERNED_U0_RESOLUTION",
        "L1_WORK_UNIT_SELECTION",
        "NO_DOWNSTREAM_EFFECT",
        "OMIT_UNSAFE_PREFERENCE_VALUE",
        "PA_SAFE_CONSTRAINT_DIRECTIVE",
        "PA_SAFE_PREFERENCE_DIRECTIVE",
    }
)
_VALID_CONSTRAINT_INPUT_ORIGINS: Final[frozenset[str]] = frozenset(
    {"OUTPUT_PREFERENCE", "USER_CONSTRAINT"}
)
_VALID_CONSTRAINT_RESOLUTION_REASONS: Final[frozenset[str]] = frozenset(
    {
        "DECLARED_CONFLICT",
        "PREFERENCE_CONFLICT_DEFERRED",
        "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT",
        "SAFE_DIRECTIVE",
        "SECTION_SCOPE",
        "SYSTEM_CONTEXT",
        "UNSAFE_HARD_VALUE",
        "UNSAFE_PREFERENCE_VALUE",
    }
)


class L1CognitivePlanError(ValueError):
    """Raised when an L1 v3 cognitive plan or bounded revision is invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def _digest_without(value: Mapping[str, Any], field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    return _sha256(body)


def cognitive_plan_digest(plan: Mapping[str, Any]) -> str:
    """Return the canonical digest of a cognitive plan excluding itself."""

    return _digest_without(plan, "plan_digest")


def cognitive_revision_digest(revision: Mapping[str, Any]) -> str:
    """Return the canonical digest of a revision excluding itself."""

    return _digest_without(revision, "revision_digest")


def _required_string(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise L1CognitivePlanError(f"{field} is required")
    return normalized


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _source_text_for_requirement(
    jd_text: str, requirement: Mapping[str, Any]
) -> tuple[str, int]:
    span = _mapping(requirement.get("source_span"))
    start = span.get("start_offset")
    end = span.get("end_offset")
    if (
        not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end < start
    ):
        raise L1CognitivePlanError("v2 requirement source span is invalid")
    source = jd_text[start:end]
    if not source.strip():
        raise L1CognitivePlanError("v2 requirement source span has no text")
    leading = len(source) - len(source.lstrip())
    trimmed = source.strip()
    match = _BULLET_PREFIX_RE.match(trimmed)
    prefix_size = match.end() if match else 0
    text = trimmed[prefix_size:].strip()
    if not text:
        raise L1CognitivePlanError("v2 requirement source span has no requirement text")
    content_start = start + leading + prefix_size
    while content_start < end and jd_text[content_start].isspace():
        content_start += 1
    return text, content_start


def _relation_kind(value: str) -> str:
    normalized = " ".join(str(value or "").lower().split())
    if normalized == "and":
        return "AND"
    if normalized == "or":
        return "OR"
    if normalized == "but not":
        return "NOT"
    if normalized in {"except", "unless"}:
        return "EXCEPTION"
    raise L1CognitivePlanError("atomic relation is invalid")


def _leading_action(text: str) -> str:
    match = _ACTION_RE.match(str(text or "").strip())
    return str(match.group("verb") or "").upper() if match else ""


def _predicate_class(value: str) -> str:
    verb = str(value or "").upper()
    if verb in {"LEAD", "OWN", "MANAGE", "HIRE", "MENTOR", "INFLUENCE"}:
        return "LEADERSHIP_ACTION"
    if verb in {"BUILD", "DELIVER", "CREATE", "DEVELOP", "DESIGN", "ARCHITECT"}:
        return "BUILD_DELIVER_ACTION"
    if verb in {"OPERATE", "SCALE", "GOVERN", "ENSURE", "MAINTAIN"}:
        return "OPERATE_GOVERN_ACTION"
    if verb in {"HAVE", "DEMONSTRATE", "COMMUNICATE", "PARTNER"}:
        return "CAPABILITY_ACTION"
    return "UNSPECIFIED_ACTION"


def _inherited_predicate_segment_allowed(*, predicate: str, text: str) -> bool:
    """Accept a predicate-less coordination only when its scope is explicit.

    The caller carries the most recent explicit predicate across a complete
    coordination chain.  A known requirement head is deliberately required
    before that predicate can be inherited: otherwise a bare noun may be an
    object, qualifier, or another grammatical role rather than a second
    requirement.
    """

    if not predicate or _leading_action(text):
        return False
    normalized_text = str(text or "").strip()
    if not normalized_text or normalized_text.lower().startswith(
        ("with ", "for ", "in ", "across ", "while ", "through ")
    ):
        return False
    return bool(_COORDINATED_REQUIREMENT_HEAD_RE.search(normalized_text))


def _semantic_text_with_inherited_predicate(*, predicate: str, source_text: str) -> str:
    """Recover a predicate for classification without changing the source span."""

    return f"{predicate.lower()} {source_text}".strip() if predicate else source_text


def _explicit_sentence_clause_rows(
    text: str, *, absolute_start: int
) -> list[dict[str, Any]]:
    """Split only plainly independent action sentences from one source line.

    The v2 parent capsule is intentionally line-oriented.  A single bullet can
    still contain several explicit requirements, so a conjunction-only parser
    leaves a material cognition gap.  We split punctuation only when every
    resulting segment begins with a recognized action; otherwise the source
    remains one clause and later ambiguity handling decides whether to
    escalate.  The punctuation itself is not part of an atom's source span.
    """

    candidates = list(_EXPLICIT_SENTENCE_BOUNDARY_RE.finditer(text))
    if not candidates:
        return []
    raw_segments: list[tuple[str, int]] = []
    cursor = 0
    for candidate in candidates:
        raw_segments.append((text[cursor : candidate.start()], cursor))
        cursor = candidate.end()
    raw_segments.append((text[cursor:], cursor))

    rows: list[dict[str, Any]] = []
    for ordinal, (raw_segment, relative_start) in enumerate(raw_segments):
        leading = len(raw_segment) - len(raw_segment.lstrip())
        source_text = raw_segment.strip()
        if not source_text or not _leading_action(source_text):
            return []
        start_offset = absolute_start + relative_start + leading
        rows.append(
            {
                "source_text": source_text,
                "semantic_text": source_text,
                "start_offset": start_offset,
                "end_offset": start_offset + len(source_text),
                "relation_to_previous": "ROOT" if ordinal == 0 else "AND",
                "decomposition_mode": "EXPLICIT_SENTENCE_PREDICATE",
                "inherited_predicate": "",
            }
        )
    return rows if len(rows) > 1 else []


def _atomic_clause_rows(text: str, *, absolute_start: int) -> list[dict[str, Any]]:
    """Recover unambiguous atomic clauses while retaining source and scope links.

    A connector alone is not enough to split a requirement.  We split when both
    sides contain an explicit action, or when a leading action unambiguously
    scopes a coordinated requirement head (for example, ``lead engineering and
    delivery operations``).  All other coordination remains source-bound as a
    single atom rather than inventing semantic scope.
    """

    explicit_sentences = _explicit_sentence_clause_rows(
        text, absolute_start=absolute_start
    )
    if explicit_sentences:
        rows: list[dict[str, Any]] = []
        for sentence_ordinal, sentence in enumerate(explicit_sentences):
            nested_rows = _atomic_clause_rows(
                str(sentence["source_text"]),
                absolute_start=int(sentence["start_offset"]),
            )
            if len(nested_rows) == 1:
                nested_rows[0]["decomposition_mode"] = "EXPLICIT_SENTENCE_PREDICATE"
            if sentence_ordinal:
                nested_rows[0]["relation_to_previous"] = "AND"
            rows.extend(nested_rows)
        return rows

    candidates = list(_RELATION_RE.finditer(text))
    source_text = text.strip()
    source_start = absolute_start + len(text) - len(text.lstrip())

    def preserved_row(*, mode: str) -> list[dict[str, Any]]:
        return [
            {
                "source_text": source_text,
                "semantic_text": source_text,
                "start_offset": source_start,
                "end_offset": source_start + len(source_text),
                "relation_to_previous": "ROOT",
                "decomposition_mode": mode,
                "inherited_predicate": "",
            }
        ]

    if not candidates:
        return preserved_row(mode="UNSPLIT_SOURCE_CLAUSE")

    # A linear relation ledger has no way to express precedence for a mixed
    # connector chain (for example, ``A and B or C``).  More importantly,
    # silently splitting a later safe-looking connector after an earlier
    # ambiguous one lets part of an uncertain clause acquire a target.  Treat
    # the entire source clause as unresolved unless every connector belongs to
    # one relation family and every segment can be interpreted under a known
    # explicit or inherited predicate.
    relations = [_relation_kind(str(match.group("relation"))) for match in candidates]
    if len(set(relations)) != 1:
        return preserved_row(mode="AMBIGUOUS_COORDINATION_PRESERVED")

    raw_segments: list[tuple[str, int]] = []
    cursor = 0
    for match in candidates:
        raw_segments.append((text[cursor : match.start()], cursor))
        cursor = match.end()
    raw_segments.append((text[cursor:], cursor))

    segments: list[tuple[str, int]] = []
    for raw_segment, relative_start in raw_segments:
        leading = len(raw_segment) - len(raw_segment.lstrip())
        segment_text = raw_segment.strip()
        if not segment_text:
            return preserved_row(mode="AMBIGUOUS_COORDINATION_PRESERVED")
        segments.append((segment_text, relative_start + leading))

    active_predicate = _leading_action(segments[0][0])
    if not active_predicate:
        return preserved_row(mode="AMBIGUOUS_COORDINATION_PRESERVED")

    rows: list[dict[str, Any]] = []
    for ordinal, (segment_text, relative_start) in enumerate(segments):
        relation_to_previous = "ROOT" if ordinal == 0 else relations[ordinal - 1]
        inherited_predicate = ""
        if ordinal:
            explicit_predicate = _leading_action(segment_text)
            if explicit_predicate:
                active_predicate = explicit_predicate
            elif relations[ordinal - 1] in {"NOT", "EXCEPTION"}:
                # A restrictive clause remains source-bound and escalated by
                # relation review even when its semantic head is unknown.
                inherited_predicate = active_predicate
            elif _inherited_predicate_segment_allowed(
                predicate=active_predicate,
                text=segment_text,
            ):
                inherited_predicate = active_predicate
            else:
                return preserved_row(mode="AMBIGUOUS_COORDINATION_PRESERVED")
        rows.append(
            {
                "source_text": segment_text,
                "semantic_text": _semantic_text_with_inherited_predicate(
                    predicate=inherited_predicate,
                    source_text=segment_text,
                ),
                "start_offset": absolute_start + relative_start,
                "end_offset": absolute_start + relative_start + len(segment_text),
                "relation_to_previous": relation_to_previous,
                "decomposition_mode": (
                    "INHERITED_PREDICATE"
                    if inherited_predicate
                    else "EXPLICIT_PREDICATE"
                ),
                "inherited_predicate": inherited_predicate,
            }
        )
    return rows


def _constraint_classification(key: str, value: Any) -> str:
    normalized_key = str(key or "").lower()
    normalized_value = str(value or "").lower()
    combined = f"{normalized_key} {normalized_value}"
    if any(token in combined for token in ("conflict", "contradict", "incompatible")):
        return "CONFLICT"
    if any(
        token in combined
        for token in ("prefer", "optional", "nice to have", "style", "tone")
    ):
        return "PREFERENCE"
    return "HARD"


def _constraint_key_token(value: Any) -> str:
    """Return a deterministic identifier token without retaining request prose."""

    return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")


def _normalized_constraint_value(value: Any) -> str:
    """Normalize only for equality/digest checks; callers never persist this text."""

    if isinstance(value, Mapping):
        return _sha256(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return "|".join(sorted(_normalized_constraint_value(item) for item in value))
    return _constraint_key_token(value)


def _constraint_value_digest(value: Any) -> str:
    return _sha256({"normalized_value": _normalized_constraint_value(value)})


def _constraint_is_truthy(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    return _constraint_key_token(value) in {"1", "required", "true", "yes"}


def _safe_output_format_code(value: Any) -> str:
    values = (
        list(value)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        else [value]
    )
    if not values:
        return ""
    codes: list[str] = []
    for item in values:
        code = _SAFE_OUTPUT_FORMAT_CODES.get(_constraint_key_token(item))
        if not code:
            return ""
        codes.append(code)
    return "_AND_".join(sorted(set(codes)))


def _output_format_families(
    slot: Mapping[str, Any],
) -> frozenset[str] | None:
    """Return compatible output families for one closed-vocabulary directive.

    An executive resume is a narrower form of a resume, but a resume and JSON
    are competing final-artifact formats.  Keeping the comparison in terms of
    closed directive families avoids retaining a raw user value in the plan.
    ``None`` signals an invalid directive code so validation can fail closed.
    """

    if slot.get("semantic_kind") != "OUTPUT_FORMAT":
        return frozenset()
    directive_code = str(slot.get("directive_code") or "").strip()
    if not directive_code:
        return frozenset()
    codes = directive_code.split("_AND_")
    if any(not code for code in codes):
        return None
    families: set[str] = set()
    for code in codes:
        family = _OUTPUT_FORMAT_FAMILY_BY_CODE.get(code)
        if not family:
            return None
        families.add(family)
    return frozenset(families)


def _safe_style_code(value: Any) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return ""
    return _SAFE_STYLE_CODES.get(_constraint_key_token(value), "")


def _numeric_constraint_limit(key: str, value: Any) -> dict[str, Any] | None:
    """Return a non-sensitive numeric output limit when its unit is unambiguous."""

    key_token = _constraint_key_token(key).removeprefix("output_preferences_")
    key_tokens = set(key_token.split("_"))
    bound_candidates: set[str] = set()
    if key_tokens & {"max", "maximum", "limit"}:
        bound_candidates.add("MAXIMUM")
    if key_tokens & {"min", "minimum"}:
        bound_candidates.add("MINIMUM")
    if key_tokens & {"exact", "exactly", "count"}:
        bound_candidates.add("EXACT")
    if len(bound_candidates) != 1:
        return None

    unit = ""
    for token, candidate in (
        ("page", "PAGES"),
        ("pages", "PAGES"),
        ("word", "WORDS"),
        ("words", "WORDS"),
        ("character", "CHARACTERS"),
        ("characters", "CHARACTERS"),
        ("char", "CHARACTERS"),
        ("chars", "CHARACTERS"),
        ("bullet", "BULLETS"),
        ("bullets", "BULLETS"),
        ("item", "ITEMS"),
        ("items", "ITEMS"),
        ("line", "LINES"),
        ("lines", "LINES"),
    ):
        if token in key_tokens:
            unit = candidate
            break

    if isinstance(value, bool):
        return None
    rendered_value = str(value or "").strip()
    match = re.fullmatch(
        r"(?P<quantity>\d{1,5})(?:\s*(?P<unit>pages?|words?|characters?|chars?|"
        r"bullets?|items?|lines?))?",
        rendered_value,
        re.IGNORECASE,
    )
    if match is None:
        return None
    if not unit:
        unit = {
            "page": "PAGES",
            "pages": "PAGES",
            "word": "WORDS",
            "words": "WORDS",
            "character": "CHARACTERS",
            "characters": "CHARACTERS",
            "char": "CHARACTERS",
            "chars": "CHARACTERS",
            "bullet": "BULLETS",
            "bullets": "BULLETS",
            "item": "ITEMS",
            "items": "ITEMS",
            "line": "LINES",
            "lines": "LINES",
        }.get(str(match.group("unit") or "").casefold(), "")
    if not unit:
        return None
    return {
        "comparison": next(iter(bound_candidates)),
        "quantity": int(match.group("quantity")),
        "unit": unit,
    }


def _constraint_semantic_kind(key_token: str) -> str:
    key_token = key_token.removeprefix("output_preferences_")
    if key_token.startswith("_") or key_token in _CONTEXT_CONSTRAINT_KEYS:
        return "SYSTEM_CONTEXT"
    if key_token in _SECTION_SCOPE_CONSTRAINT_KEYS:
        return "SECTION_SCOPE"
    if key_token in _SAFE_BOOLEAN_CONSTRAINT_DIRECTIVES:
        return _SAFE_BOOLEAN_CONSTRAINT_DIRECTIVES[key_token][0]
    if "format" in key_token:
        return "OUTPUT_FORMAT"
    tokens = set(key_token.split("_"))
    if tokens & {
        "page",
        "pages",
        "word",
        "words",
        "character",
        "characters",
        "char",
        "chars",
        "bullet",
        "bullets",
        "item",
        "items",
        "line",
        "lines",
    }:
        return "LENGTH_LIMIT"
    if tokens & {"style", "tone", "voice"}:
        return "STYLE"
    if tokens & {"exclude", "forbid", "omit", "avoid", "no"}:
        return "EXCLUSION"
    if tokens & {"include", "must", "required", "only"}:
        return "INCLUSION"
    return "UNKNOWN"


def _constraint_slot(
    *,
    key: str,
    input_origin: str,
    classification: str,
    value: Any,
    value_digest: str,
) -> dict[str, Any]:
    """Represent a constraint as a safe semantic directive or explicit escalation.

    This is intentionally a small closed vocabulary.  L1 may carry only an
    unambiguous, non-sensitive directive downstream; arbitrary request prose is
    withheld and either escalated (hard constraint) or deferred (preference).
    """

    if input_origin not in _VALID_CONSTRAINT_INPUT_ORIGINS:
        raise L1CognitivePlanError("constraint input origin is invalid")
    key_token = _constraint_key_token(key)
    semantic_key_token = key_token.removeprefix("output_preferences_")
    kind = _constraint_semantic_kind(semantic_key_token)
    polarity = "PREFER" if classification == "PREFERENCE" else "REQUIRE"
    scope = "UNRESOLVED"
    directive_code = ""
    numeric_limit: dict[str, Any] | None = None

    if kind == "SYSTEM_CONTEXT":
        polarity = "CONTEXT"
        scope = "INGRESS_CONTEXT"
        interpretation_status = "OUT_OF_SCOPE"
        downstream_handling = "NO_DOWNSTREAM_EFFECT"
        resolution_reason = "SYSTEM_CONTEXT"
    elif kind == "SECTION_SCOPE":
        polarity = "SCOPE"
        scope = "SECTION_SELECTION"
        interpretation_status = "OUT_OF_SCOPE"
        downstream_handling = "L1_WORK_UNIT_SELECTION"
        resolution_reason = "SECTION_SCOPE"
    else:
        if kind == "OUTPUT_FORMAT":
            scope = "WHOLE_OUTPUT"
            directive_code = _safe_output_format_code(value)
        elif kind == "LENGTH_LIMIT":
            scope = "WHOLE_OUTPUT"
            numeric_limit = _numeric_constraint_limit(key, value)
            if numeric_limit is not None:
                directive_code = (
                    f"{numeric_limit['comparison']}_{numeric_limit['unit']}"
                )
        elif kind == "STYLE":
            scope = "WHOLE_OUTPUT"
            directive_code = _safe_style_code(value)
        elif (
            semantic_key_token in _SAFE_BOOLEAN_CONSTRAINT_DIRECTIVES
            and _constraint_is_truthy(value)
        ):
            _kind, polarity, directive_code = _SAFE_BOOLEAN_CONSTRAINT_DIRECTIVES[
                semantic_key_token
            ]
            kind = _kind
            scope = "CONTENT"
        elif kind in {"INCLUSION", "EXCLUSION"}:
            scope = "CONTENT"

        if classification == "CONFLICT":
            polarity = "CONFLICT"
            directive_code = ""
            numeric_limit = None
            interpretation_status = "CONFLICT"
            downstream_handling = "GOVERNED_U0_RESOLUTION"
            resolution_reason = "DECLARED_CONFLICT"
        elif directive_code:
            interpretation_status = "ACTIONABLE"
            downstream_handling = (
                "PA_SAFE_PREFERENCE_DIRECTIVE"
                if classification == "PREFERENCE"
                else "PA_SAFE_CONSTRAINT_DIRECTIVE"
            )
            resolution_reason = "SAFE_DIRECTIVE"
        elif classification == "PREFERENCE":
            interpretation_status = "DEFERRED_PREFERENCE"
            downstream_handling = "OMIT_UNSAFE_PREFERENCE_VALUE"
            resolution_reason = "UNSAFE_PREFERENCE_VALUE"
        else:
            interpretation_status = "REVIEW_REQUIRED"
            downstream_handling = "GOVERNED_U0_RESOLUTION"
            resolution_reason = "UNSAFE_HARD_VALUE"

    body = {
        "source_key_digest": _sha256(
            {"input_origin": input_origin, "source_key": str(key)}
        ),
        "input_origin": input_origin,
        "classification": classification,
        "semantic_kind": kind,
        "polarity": polarity,
        "scope": scope,
        "value_digest": value_digest,
        "normalized_value_digest": _constraint_value_digest(value),
        "directive_code": directive_code,
        "numeric_limit": numeric_limit,
        "interpretation_status": interpretation_status,
        "downstream_handling": downstream_handling,
        "resolution_reason": resolution_reason,
    }
    body["constraint_id"] = "l1constraint-" + _sha256(body).removeprefix("sha256:")[:16]
    return body


def _refresh_constraint_identity(slot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical slot after a safe precedence resolution changes it."""

    body = dict(slot)
    body.pop("constraint_id", None)
    body["constraint_id"] = "l1constraint-" + _sha256(body).removeprefix("sha256:")[:16]
    return body


def _preference_conflict_resolutions(
    constraint_slots: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    """Return non-binding preference slots that must yield to a conflict.

    A U0 constraint and a separately supplied output preference do not have
    equal authority.  A hard constraint wins; conflicting preferences are
    withheld rather than sent downstream with incompatible safe directives.
    This preserves the explicit hard goal without silently treating a
    preference as if it were satisfied.
    """

    resolutions: dict[str, str] = {}

    def mark_preference_rows(*rows: Mapping[str, Any]) -> None:
        preference_rows = [
            row for row in rows if row.get("classification") == "PREFERENCE"
        ]
        if not preference_rows:
            return
        reason = (
            "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT"
            if any(row.get("classification") == "HARD" for row in rows)
            else "PREFERENCE_CONFLICT_DEFERRED"
        )
        for row in preference_rows:
            source_key_digest = str(row.get("source_key_digest") or "")
            if not source_key_digest:
                raise L1CognitivePlanError(
                    "preference conflict source identity is invalid"
                )
            if (
                resolutions.get(source_key_digest)
                != "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT"
            ):
                resolutions[source_key_digest] = reason

    actionable = [
        dict(row)
        for row in constraint_slots
        if row.get("interpretation_status") == "ACTIONABLE"
    ]
    numeric_by_scope_unit: dict[tuple[str, str], list[dict[str, Any]]] = {}
    content_directives: dict[str, list[dict[str, Any]]] = {}
    output_format_slots: list[dict[str, Any]] = []
    for slot in actionable:
        numeric_limit = slot.get("numeric_limit")
        if isinstance(numeric_limit, Mapping):
            unit = str(numeric_limit.get("unit") or "")
            if unit:
                numeric_by_scope_unit.setdefault(
                    (str(slot.get("scope") or ""), unit), []
                ).append(slot)
        if slot.get("semantic_kind") in {"INCLUSION", "EXCLUSION"}:
            directive_code = str(slot.get("directive_code") or "")
            if directive_code:
                content_directives.setdefault(directive_code, []).append(slot)
        if slot.get("semantic_kind") == "OUTPUT_FORMAT":
            output_format_slots.append(slot)

    for rows in numeric_by_scope_unit.values():
        lower_bounds = [
            row
            for row in rows
            if str(_mapping(row.get("numeric_limit")).get("comparison") or "")
            in {"MINIMUM", "EXACT"}
        ]
        upper_bounds = [
            row
            for row in rows
            if str(_mapping(row.get("numeric_limit")).get("comparison") or "")
            in {"MAXIMUM", "EXACT"}
        ]
        for lower in lower_bounds:
            lower_quantity = int(
                _mapping(lower.get("numeric_limit")).get("quantity") or -1
            )
            for upper in upper_bounds:
                upper_quantity = int(
                    _mapping(upper.get("numeric_limit")).get("quantity") or -1
                )
                if lower_quantity > upper_quantity:
                    mark_preference_rows(lower, upper)

    for rows in content_directives.values():
        required = [row for row in rows if row.get("polarity") == "REQUIRE"]
        forbidden = [row for row in rows if row.get("polarity") == "FORBID"]
        for required_row in required:
            for forbidden_row in forbidden:
                mark_preference_rows(required_row, forbidden_row)

    # A preference must not add a competing final-artifact format beside an
    # actionable hard constraint.  A multi-family preference is equally
    # unresolved: defer it rather than passing a synthetic ``JSON_AND_RESUME``
    # directive to PA.
    for slot in output_format_slots:
        families = _output_format_families(slot)
        if families is None or len(families) > 1:
            mark_preference_rows(slot)
    for index, left in enumerate(output_format_slots):
        left_families = _output_format_families(left)
        if not left_families:
            continue
        for right in output_format_slots[index + 1 :]:
            right_families = _output_format_families(right)
            if right_families and len(left_families | right_families) > 1:
                mark_preference_rows(left, right)

    return resolutions


def _defer_conflicting_preference(
    slot: Mapping[str, Any], *, reason: str
) -> dict[str, Any]:
    """Remove a non-binding directive that conflicts with a hard goal or peer."""

    if reason not in {
        "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT",
        "PREFERENCE_CONFLICT_DEFERRED",
    }:
        raise L1CognitivePlanError("preference conflict resolution is invalid")
    result = dict(slot)
    if (
        result.get("classification") != "PREFERENCE"
        or result.get("interpretation_status") != "ACTIONABLE"
    ):
        raise L1CognitivePlanError("preference conflict slot is invalid")
    result.update(
        {
            "directive_code": "",
            "numeric_limit": None,
            "interpretation_status": "DEFERRED_PREFERENCE",
            "downstream_handling": "OMIT_UNSAFE_PREFERENCE_VALUE",
            "resolution_reason": reason,
        }
    )
    return _refresh_constraint_identity(result)


def _constraint_conflicts(
    constraint_slots: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Find only deterministic semantic conflicts from non-sensitive slot data."""

    conflicts: list[dict[str, Any]] = []
    seen_conflicts: set[tuple[str, tuple[str, ...]]] = set()

    def add_conflict(*, code: str, constraint_ids: Sequence[str]) -> None:
        normalized_ids = tuple(sorted(set(str(item) for item in constraint_ids)))
        conflict_key = (code, normalized_ids)
        if conflict_key in seen_conflicts:
            return
        seen_conflicts.add(conflict_key)
        body = {
            "code": code,
            "constraint_ids": list(normalized_ids),
            "resolver": "U0",
            "planning_effect": "BLOCKED",
        }
        body["conflict_id"] = (
            "l1constraintconflict-" + _sha256(body).removeprefix("sha256:")[:16]
        )
        conflicts.append(body)

    for slot in constraint_slots:
        if slot.get("interpretation_status") == "CONFLICT":
            add_conflict(
                code="DECLARED_CONSTRAINT_CONFLICT",
                constraint_ids=[str(slot["constraint_id"])],
            )

    numeric_by_scope_unit: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    content_directives: dict[str, list[Mapping[str, Any]]] = {}
    output_format_slots: list[Mapping[str, Any]] = []
    for slot in constraint_slots:
        if slot.get("interpretation_status") != "ACTIONABLE":
            continue
        numeric_limit = slot.get("numeric_limit")
        if isinstance(numeric_limit, Mapping):
            unit = str(numeric_limit.get("unit") or "")
            if unit:
                numeric_by_scope_unit.setdefault(
                    (str(slot.get("scope") or ""), unit), []
                ).append(slot)
        if slot.get("semantic_kind") in {"INCLUSION", "EXCLUSION"}:
            directive_code = str(slot.get("directive_code") or "")
            if directive_code:
                content_directives.setdefault(directive_code, []).append(slot)
        if slot.get("semantic_kind") == "OUTPUT_FORMAT":
            output_format_slots.append(slot)

    for rows in numeric_by_scope_unit.values():
        lower_bounds: list[Mapping[str, Any]] = []
        upper_bounds: list[Mapping[str, Any]] = []
        for row in rows:
            limit = _mapping(row.get("numeric_limit"))
            comparison = str(limit.get("comparison") or "")
            if comparison in {"MINIMUM", "EXACT"}:
                lower_bounds.append(row)
            if comparison in {"MAXIMUM", "EXACT"}:
                upper_bounds.append(row)
        if not lower_bounds or not upper_bounds:
            continue
        lower = max(
            lower_bounds,
            key=lambda row: int(
                _mapping(row.get("numeric_limit")).get("quantity") or -1
            ),
        )
        upper = min(
            upper_bounds,
            key=lambda row: int(
                _mapping(row.get("numeric_limit")).get("quantity") or -1
            ),
        )
        lower_quantity = int(_mapping(lower.get("numeric_limit")).get("quantity") or -1)
        upper_quantity = int(_mapping(upper.get("numeric_limit")).get("quantity") or -1)
        if lower_quantity > upper_quantity:
            add_conflict(
                code="SEMANTIC_LENGTH_CONSTRAINT_CONFLICT",
                constraint_ids=[
                    str(lower["constraint_id"]),
                    str(upper["constraint_id"]),
                ],
            )

    for rows in content_directives.values():
        required = [row for row in rows if row.get("polarity") == "REQUIRE"]
        forbidden = [row for row in rows if row.get("polarity") == "FORBID"]
        if required and forbidden:
            add_conflict(
                code="SEMANTIC_REQUIRE_FORBID_CONFLICT",
                constraint_ids=[
                    str(row["constraint_id"]) for row in [required[0], forbidden[0]]
                ],
            )

    # Multiple distinct output families cannot describe one final artifact.
    # Same-family codes (for example RESUME and EXECUTIVE_RESUME) are
    # compatible; unknown codes are invalid rather than silently accepted.
    for slot in output_format_slots:
        families = _output_format_families(slot)
        if families is None:
            add_conflict(
                code="INVALID_SAFE_OUTPUT_FORMAT_DIRECTIVE",
                constraint_ids=[str(slot["constraint_id"])],
            )
        elif len(families) > 1:
            add_conflict(
                code="SEMANTIC_OUTPUT_FORMAT_CONFLICT",
                constraint_ids=[str(slot["constraint_id"])],
            )
    for index, left in enumerate(output_format_slots):
        left_families = _output_format_families(left)
        if not left_families:
            continue
        for right in output_format_slots[index + 1 :]:
            right_families = _output_format_families(right)
            if right_families and len(left_families | right_families) > 1:
                add_conflict(
                    code="SEMANTIC_OUTPUT_FORMAT_CONFLICT",
                    constraint_ids=[
                        str(left["constraint_id"]),
                        str(right["constraint_id"]),
                    ],
                )
    return sorted(conflicts, key=lambda row: str(row["conflict_id"]))


def _goal_constraint_frame(app_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a source-bound problem frame without persisting raw request text.

    Earlier L1 v3 work recorded only a key and value digest.  That made every
    ordinary constraint observational: it could be tested for a literal word
    such as ``conflict`` but neither constrain deliberation nor safely affect a
    downstream artifact.  The frame now carries a closed, source-bound semantic
    slot for every constraint and makes unsafe values explicit escalations.
    """

    task = _mapping(app_payload.get("task_spec"))
    user_constraints = _mapping(app_payload.get("user_constraints"))
    output_preferences = _mapping(app_payload.get("output_preferences"))
    constraint_entries: list[dict[str, Any]] = []
    constraint_slots: list[dict[str, Any]] = []
    request_values: list[tuple[str, str, Any, str]] = [
        (
            str(raw_key),
            "USER_CONSTRAINT",
            value,
            _constraint_classification(str(raw_key), value),
        )
        for raw_key, value in user_constraints.items()
    ]
    request_values.extend(
        (
            str(raw_key),
            "OUTPUT_PREFERENCE",
            value,
            "PREFERENCE",
        )
        for raw_key, value in output_preferences.items()
    )
    for key, input_origin, value, classification in request_values:
        if value in (None, "", [], {}, False):
            continue
        value_digest = _sha256({"value": value})
        source_key_digest = _sha256({"input_origin": input_origin, "source_key": key})
        constraint_entries.append(
            {
                "source_key_digest": source_key_digest,
                "input_origin": input_origin,
                "classification": classification,
                "value_digest": value_digest,
            }
        )
        constraint_slots.append(
            _constraint_slot(
                key=key,
                input_origin=input_origin,
                classification=classification,
                value=value,
                value_digest=value_digest,
            )
        )
    constraint_entries.sort(
        key=lambda row: (
            str(row["classification"]),
            str(row["input_origin"]),
            str(row["source_key_digest"]),
        )
    )
    preference_resolutions = _preference_conflict_resolutions(constraint_slots)
    constraint_slots = [
        _defer_conflicting_preference(
            row,
            reason=preference_resolutions[str(row["source_key_digest"])],
        )
        if str(row["source_key_digest"]) in preference_resolutions
        else row
        for row in constraint_slots
    ]
    constraint_slots.sort(
        key=lambda row: (
            str(row["input_origin"]),
            str(row["source_key_digest"]),
            str(row["constraint_id"]),
        )
    )
    constraint_conflicts = _constraint_conflicts(constraint_slots)
    hard_constraint_ids = sorted(
        str(row["constraint_id"])
        for row in constraint_slots
        if row["classification"] == "HARD"
    )
    preference_constraint_ids = sorted(
        str(row["constraint_id"])
        for row in constraint_slots
        if row["classification"] == "PREFERENCE"
    )
    conflict_constraint_ids = sorted(
        str(row["constraint_id"])
        for row in constraint_slots
        if row["classification"] == "CONFLICT"
    )
    actionable_constraint_ids = sorted(
        str(row["constraint_id"])
        for row in constraint_slots
        if row["interpretation_status"] == "ACTIONABLE"
    )
    conflicted_constraint_ids = {
        str(constraint_id)
        for conflict in constraint_conflicts
        for constraint_id in conflict["constraint_ids"]
    }
    blocking_constraint_ids = sorted(
        str(row["constraint_id"])
        for row in constraint_slots
        if str(row["constraint_id"]) in conflicted_constraint_ids
        or row["interpretation_status"] == "CONFLICT"
        or (
            row["classification"] == "HARD"
            and row["interpretation_status"] == "REVIEW_REQUIRED"
        )
    )
    body = {
        "schema_version": _GOAL_CONSTRAINT_FRAME_SCHEMA_VERSION,
        "requested_artifact": str(
            task.get("task_class")
            or app_payload.get("task_class")
            or "resume_generation"
        ),
        "generation_mode": str(
            task.get("generation_mode") or app_payload.get("generation_mode") or ""
        ),
        "target_role_digest": _sha256(
            {"target_role": str(app_payload.get("target_role") or "")}
        ),
        "target_level": str(app_payload.get("target_level") or ""),
        # A boolean evidence-input state is sufficient for critique and avoids
        # retaining resume text in an L1 planning artifact.
        "source_resume_available": bool(
            str(app_payload.get("source_resume_text") or "").strip()
        ),
        "source_output_preferences_digest": _sha256(output_preferences),
        "source_user_constraints_digest": _sha256(user_constraints),
        "constraint_entries": constraint_entries,
        "constraint_slots": constraint_slots,
        "constraint_conflicts": constraint_conflicts,
        "actionable_constraint_ids": actionable_constraint_ids,
        "blocking_constraint_ids": blocking_constraint_ids,
        "hard_constraint_ids": hard_constraint_ids,
        "preference_constraint_ids": preference_constraint_ids,
        "conflict_constraint_ids": conflict_constraint_ids,
        "input_authority": {
            "job_description": "TARGETING_INPUT_ONLY",
            "source_resume": "CANDIDATE_EVIDENCE_INPUT",
            "briefing": "CONTEXT_INPUT_ONLY",
            "user_constraints": "REQUEST_CONSTRAINTS_ONLY",
            "output_preferences": "REQUEST_PREFERENCES_ONLY",
        },
        "definition_of_done": {
            "all_critical_requirements_targeted_or_escalated": True,
            "candidate_evidence_claims_forbidden": True,
            "downstream_authority_required": True,
            "unsupported_requirement_must_be_escalated_or_omitted": True,
            "all_hard_constraints_actionable_or_escalated": True,
            "hard_constraints_override_preferences": True,
            "unsafe_constraint_text_omitted": True,
        },
        "authority_class": _AUTHORITY_CLASS,
    }
    body["goal_frame_id"] = "l1goal-" + _sha256(body).removeprefix("sha256:")[:16]
    return body


def _atomic_requirement_graph(
    *,
    v2_capsule: Mapping[str, Any],
    jd_text: str,
    taxonomy: Mapping[str, Any],
) -> dict[str, Any]:
    parent_rows = v2_capsule.get("requirements")
    if not isinstance(parent_rows, Sequence) or isinstance(parent_rows, (str, bytes)):
        raise L1CognitivePlanError("v2 requirements are invalid")
    requirements: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    jd_hash = _declared_jd_hash({}, jd_text)
    for parent in parent_rows:
        if not isinstance(parent, Mapping):
            raise L1CognitivePlanError("v2 requirement is invalid")
        parent_id = _required_string(
            parent.get("requirement_id"), field="parent requirement_id"
        )
        text, content_start = _source_text_for_requirement(jd_text, parent)
        clauses = _atomic_clause_rows(text, absolute_start=content_start)
        source_kind = str(parent.get("source_kind") or "JD_STATEMENT")
        parent_qualifiers = _qualifiers(text)
        for ordinal, clause in enumerate(clauses, start=1):
            clause_text = str(clause["source_text"])
            semantic_clause_text = str(clause["semantic_text"])
            requirement_type, target_unit_id, confidence, rule_id = (
                _classify_requirement(
                    text=semantic_clause_text,
                    source_kind=source_kind,
                    taxonomy=taxonomy,
                )
            )
            if rule_id == "hard_requirement_unspecified" and not target_unit_id:
                requirement_type = "UNKNOWN"
                confidence = "LOW"
                rule_id = "generic_hard_requirement_requires_semantic_review"
            parent_critical = parent.get("criticality") == "CRITICAL"
            criticality = (
                "CRITICAL"
                if parent_critical
                else str(parent.get("criticality") or "STANDARD")
            )
            parent_coverage_status = str(parent.get("coverage_status") or "").strip()
            if parent_coverage_status not in _VALID_COVERAGE:
                raise L1CognitivePlanError("v2 parent requirement coverage is invalid")
            relation_to_previous = str(clause["relation_to_previous"])
            relation_requires_review = relation_to_previous in {
                "OR",
                "NOT",
                "EXCEPTION",
            }
            ambiguous_coordination = (
                clause.get("decomposition_mode") == "AMBIGUOUS_COORDINATION_PRESERVED"
            )
            if (
                requirement_type == "UNKNOWN"
                or relation_requires_review
                or ambiguous_coordination
                or not target_unit_id
            ):
                coverage_status = (
                    "ESCALATED" if criticality == "CRITICAL" else "UNMAPPED"
                )
                target_unit_ids: list[str] = []
                escalation_reason = (
                    "UNKNOWN_SEMANTICS_REVIEW_REQUIRED"
                    if requirement_type == "UNKNOWN"
                    else "AMBIGUOUS_COORDINATION_REVIEW_REQUIRED"
                    if ambiguous_coordination
                    else "RELATION_OR_UNMAPPED_TARGET_REVIEW_REQUIRED"
                )
            else:
                coverage_status = "MAPPED"
                target_unit_ids = [target_unit_id]
                escalation_reason = ""
            local_qualifiers = _qualifiers(semantic_clause_text)
            if local_qualifiers:
                qualifiers = local_qualifiers
                qualifier_scope = "LOCAL"
            elif parent_qualifiers and len(clauses) > 1:
                qualifiers = parent_qualifiers
                qualifier_scope = "SHARED_PARENT"
            else:
                qualifiers = []
                qualifier_scope = "NONE"
            span = {
                "source_field": str(
                    _mapping(parent.get("source_span")).get("source_field")
                    or "job_description_text"
                ),
                "start_offset": int(clause["start_offset"]),
                "end_offset": int(clause["end_offset"]),
                "text_digest": _sha256({"text": " ".join(clause_text.lower().split())}),
            }
            span["span_digest"] = _sha256({"jd_hash": jd_hash, **span})
            seed = {
                "parent_requirement_id": parent_id,
                "ordinal": ordinal,
                "span_digest": span["span_digest"],
            }
            requirement_id = "l1cogreq-" + _sha256(seed).removeprefix("sha256:")[:16]
            requirements.append(
                {
                    "requirement_id": requirement_id,
                    "parent_requirement_id": parent_id,
                    "parent_coverage_status": parent_coverage_status,
                    "parent_c0_obligation_eligible": parent_coverage_status == "MAPPED",
                    "ordinal": ordinal,
                    "source_span": span,
                    "semantic_clause_digest": _sha256(
                        {"text": " ".join(semantic_clause_text.lower().split())}
                    ),
                    "decomposition_mode": str(clause["decomposition_mode"]),
                    "inherited_predicate_class": _predicate_class(
                        str(clause["inherited_predicate"])
                    ),
                    "requirement_type": requirement_type,
                    "classification_rule_id": rule_id,
                    "extraction_confidence": confidence,
                    "criticality": criticality,
                    "modality": _modality(clause_text, source_kind),
                    "qualifiers": qualifiers,
                    "qualifier_scope": qualifier_scope,
                    "target_unit_ids": target_unit_ids,
                    "coverage_status": coverage_status,
                    "escalation_reason": escalation_reason,
                }
            )
            if ordinal > 1:
                relations.append(
                    {
                        "from_requirement_id": requirements[-2]["requirement_id"],
                        "to_requirement_id": requirement_id,
                        "relation": relation_to_previous,
                        "relation_scope": (
                            "ALTERNATIVE"
                            if relation_to_previous == "OR"
                            else "RESTRICTION"
                            if relation_to_previous in {"NOT", "EXCEPTION"}
                            else "CONJUNCTIVE"
                        ),
                    }
                )
    # An OR, NOT, or exception relation is not a set of independently
    # satisfiable atoms.  Until a relation-aware resolver can select a path,
    # no member of that connected relation may be silently targeted.  This is
    # deliberately conservative: it prevents an arbitrary first clause from
    # becoming a proxy for the whole conditional requirement.
    relation_review_ids = {
        str(requirement_id)
        for relation in relations
        if str(relation.get("relation") or "") in {"OR", "NOT", "EXCEPTION"}
        for requirement_id in (
            relation.get("from_requirement_id"),
            relation.get("to_requirement_id"),
        )
        if str(requirement_id or "")
    }
    for requirement in requirements:
        if str(requirement["requirement_id"]) in relation_review_ids:
            requirement["coverage_status"] = "ESCALATED"
            requirement["target_unit_ids"] = []
            requirement["escalation_reason"] = "RELATION_SCOPE_REVIEW_REQUIRED"

    requirements.sort(key=lambda row: str(row["requirement_id"]))
    relations.sort(
        key=lambda row: (str(row["from_requirement_id"]), str(row["to_requirement_id"]))
    )
    body = {
        "schema_version": "apps_rg.l1_atomic_requirement_graph.v1",
        "authority_class": _AUTHORITY_CLASS,
        "requirements": requirements,
        "relations": relations,
    }
    body["graph_digest"] = _sha256(body)
    return body


def _empty_atomic_requirement_graph() -> dict[str, Any]:
    body = {
        "schema_version": "apps_rg.l1_atomic_requirement_graph.v1",
        "authority_class": _AUTHORITY_CLASS,
        "requirements": [],
        "relations": [],
    }
    body["graph_digest"] = _sha256(body)
    return body


def _feasibility_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Compare an evidence-conditioned target path with a safe escalation path."""

    options: list[dict[str, Any]] = []
    for requirement in graph["requirements"]:
        requirement_id = str(requirement["requirement_id"])
        targets = list(requirement["target_unit_ids"])
        if targets:
            parent_c0_eligible = (
                requirement.get("parent_c0_obligation_eligible") is True
            )
            qualifier_scope = str(requirement.get("qualifier_scope") or "NONE")
            preconditions = [
                "SEMANTIC_TYPE_KNOWN",
                "TARGET_UNIT_TYPE_COMPATIBLE",
                "C0_EVIDENCE_OUTCOME_REQUIRED",
            ]
            risk_codes = ["CANDIDATE_EVIDENCE_UNVERIFIED"]
            if qualifier_scope != "NONE":
                preconditions.append("QUALIFIER_SCOPE_PRESERVED")
            if parent_c0_eligible:
                feasibility_status = "READY_FOR_C0_VERIFICATION"
                assumption_code = "C0_CAN_VERIFY_REQUIREMENT_SUPPORT"
            else:
                feasibility_status = "CONDITIONAL_C0_PARENT_OBLIGATION"
                preconditions.append("C0_PARENT_OBLIGATION_CONFIRMATION")
                risk_codes.append("C0_PARENT_OBLIGATION_MISSING")
                assumption_code = "C0_PARENT_OBLIGATION_EXISTS_OR_GAP_WILL_BE_ESCALATED"
            option = {
                "requirement_id": requirement_id,
                "option_kind": "TARGET_WORK_UNIT",
                "work_unit_id": targets[0],
                "required_source_shape": [
                    "candidate_support",
                    "candidate_counterevidence",
                ],
                "precondition_codes": preconditions,
                "dependency_codes": ["C0_REQUIREMENT_OUTCOME"],
                "counterevidence_risk_codes": risk_codes,
                "counterevidence_check_required": True,
                "coverage_status": "MAPPED",
                "feasibility_status": feasibility_status,
                "rationale_code": "TYPE_AND_QUALIFIER_COMPATIBLE_TARGET",
                "assumption_code": assumption_code,
            }
            option["assumption_id"] = (
                "l1assume-"
                + _sha256(
                    {
                        "requirement_id": requirement_id,
                        "assumption_code": option["assumption_code"],
                    }
                ).removeprefix("sha256:")[:16]
            )
            option["option_id"] = (
                "l1opt-" + _sha256(option).removeprefix("sha256:")[:16]
            )
            options.append(option)
        escalation = {
            "requirement_id": requirement_id,
            "option_kind": "ESCALATE",
            "work_unit_id": "",
            "required_source_shape": [],
            "precondition_codes": ["NAMED_RESOLVER_REQUIRED"],
            "dependency_codes": ["HUMAN_OR_UPSTREAM_RESOLUTION"],
            "counterevidence_risk_codes": [],
            "counterevidence_check_required": False,
            "coverage_status": "ESCALATED",
            "feasibility_status": "FEASIBLE_SAFE_FALLBACK",
            "rationale_code": str(
                requirement.get("escalation_reason") or "ALTERNATIVE_SAFE_PATH"
            ),
            "assumption_code": "NAMED_RESOLVER_CAN_RESOLVE_UNSUPPORTED_SCOPE",
        }
        escalation["assumption_id"] = (
            "l1assume-"
            + _sha256(
                {
                    "requirement_id": requirement_id,
                    "assumption_code": escalation["assumption_code"],
                }
            ).removeprefix("sha256:")[:16]
        )
        escalation["option_id"] = (
            "l1opt-" + _sha256(escalation).removeprefix("sha256:")[:16]
        )
        options.append(escalation)
    options.sort(key=lambda row: str(row["option_id"]))
    body = {
        "schema_version": "apps_rg.l1_feasibility_graph.v2",
        "authority_class": _AUTHORITY_CLASS,
        "options": options,
    }
    body["graph_digest"] = _sha256(body)
    return body


def _goal_constraint_decisions(goal_frame: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Choose a safe treatment for every source-bound user constraint.

    A semantic slot is not merely a label: L1 explicitly chooses either a
    closed-vocabulary directive, a retained upstream scope decision, or a
    governed U0 escalation.  It never forwards arbitrary constraint text.
    """

    slots = goal_frame.get("constraint_slots")
    if not isinstance(slots, Sequence) or isinstance(slots, (str, bytes)):
        raise L1CognitivePlanError("goal constraint slots are invalid")
    raw_conflicts = goal_frame.get("constraint_conflicts")
    if not isinstance(raw_conflicts, Sequence) or isinstance(
        raw_conflicts, (str, bytes)
    ):
        raise L1CognitivePlanError("goal constraint conflicts are invalid")
    conflicted_constraint_ids = {
        str(constraint_id)
        for conflict in raw_conflicts
        if isinstance(conflict, Mapping)
        for constraint_id in (conflict.get("constraint_ids") or ())
        if str(constraint_id)
    }
    decisions: list[dict[str, Any]] = []
    for raw_slot in slots:
        if not isinstance(raw_slot, Mapping):
            raise L1CognitivePlanError("goal constraint slot is invalid")
        slot = dict(raw_slot)
        constraint_id = _required_string(
            slot.get("constraint_id"), field="constraint_id"
        )
        status = str(slot.get("interpretation_status") or "")
        resolution_reason = str(slot.get("resolution_reason") or "")
        if constraint_id in conflicted_constraint_ids:
            primary_action = "ESCALATE_TO_U0"
            alternative_action = "OMIT_UNSAFE_OR_CONFLICTING_VALUE"
            selection_rule = "SEMANTIC_CONFLICT_REQUIRES_U0_RESOLUTION"
            risk = "CONSTRAINT_CONFLICT"
        elif status == "ACTIONABLE":
            primary_action = "PROJECT_SAFE_DIRECTIVE"
            alternative_action = "ESCALATE_IF_DOWNSTREAM_PRESERVATION_UNAVAILABLE"
            selection_rule = "CLOSED_VOCABULARY_DIRECTIVE_ONLY"
            risk = "DOWNSTREAM_CONSTRAINT_LOSS"
        elif status == "OUT_OF_SCOPE":
            primary_action = "RETAIN_UPSTREAM_SCOPE"
            alternative_action = ""
            selection_rule = "ALREADY_CONSUMED_BY_L1_OR_INGRESS"
            risk = "NONE"
        elif status == "DEFERRED_PREFERENCE":
            if resolution_reason == "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT":
                primary_action = "OMIT_CONFLICTING_PREFERENCE"
                alternative_action = "ESCALATE_IF_PREFERENCE_IS_MANDATORY"
                selection_rule = "HARD_CONSTRAINT_TAKES_PRECEDENCE"
                risk = "PREFERENCE_LOSS_DUE_TO_HARD_CONSTRAINT"
            elif resolution_reason == "PREFERENCE_CONFLICT_DEFERRED":
                primary_action = "OMIT_CONFLICTING_PREFERENCE"
                alternative_action = "ESCALATE_IF_PREFERENCE_IS_MANDATORY"
                selection_rule = "CONFLICTING_PREFERENCES_DEFERRED"
                risk = "PREFERENCE_CONFLICT"
            else:
                primary_action = "OMIT_UNSAFE_PREFERENCE_VALUE"
                alternative_action = "ESCALATE_IF_PREFERENCE_IS_MANDATORY"
                selection_rule = "DO_NOT_FORWARD_ARBITRARY_PREFERENCE_TEXT"
                risk = "PREFERENCE_LOSS"
        else:
            primary_action = "ESCALATE_TO_U0"
            alternative_action = "OMIT_UNSAFE_OR_CONFLICTING_VALUE"
            selection_rule = "HARD_CONSTRAINT_REQUIRES_SAFE_INTERPRETATION"
            risk = (
                "CONSTRAINT_CONFLICT"
                if status == "CONFLICT"
                else "SEMANTIC_REVIEW_REQUIRED"
            )
        body = {
            "constraint_id": constraint_id,
            "primary_action": primary_action,
            "alternative_action": alternative_action,
            "selection_rule": selection_rule,
            "risk": risk,
        }
        body["constraint_decision_id"] = (
            "l1constraintdecision-" + _sha256(body).removeprefix("sha256:")[:16]
        )
        decisions.append(body)
    return sorted(decisions, key=lambda row: str(row["constraint_decision_id"]))


def _alternative_plan_ledger(
    graph: Mapping[str, Any],
    feasibility: Mapping[str, Any],
    goal_frame: Mapping[str, Any],
) -> dict[str, Any]:
    """Choose requirements and goal constraints only along safe, explicit paths."""

    options_by_requirement: dict[str, list[Mapping[str, Any]]] = {}
    for option in feasibility["options"]:
        options_by_requirement.setdefault(str(option["requirement_id"]), []).append(
            option
        )
    decisions: list[dict[str, Any]] = []
    for requirement in graph["requirements"]:
        requirement_id = str(requirement["requirement_id"])
        options = options_by_requirement[requirement_id]
        target = next(
            (row for row in options if row["option_kind"] == "TARGET_WORK_UNIT"),
            None,
        )
        escalation = next(
            (row for row in options if row["option_kind"] == "ESCALATE"),
            None,
        )
        if escalation is None:
            raise L1CognitivePlanError("feasibility graph lacks an escalation option")
        primary = target if target is not None else escalation
        alternative = escalation if target is not None else None
        tradeoff_present = target is not None
        selection_rule = (
            "CONDITIONAL_TARGET_REQUIRES_C0_OUTCOME"
            if target is not None
            else "NO_SEMANTICALLY_DEFENSIBLE_TARGET_ESCALATE"
        )
        body = {
            "requirement_id": requirement_id,
            "primary_option_id": str(primary["option_id"]),
            "alternative_option_id": str(alternative["option_id"])
            if alternative
            else "",
            "decision": str(primary["coverage_status"]),
            "tradeoff_present": tradeoff_present,
            "selection_rule": selection_rule,
            "required_preconditions": list(primary["precondition_codes"]),
            "counterevidence_risk_codes": list(primary["counterevidence_risk_codes"]),
            "risk": (
                "COUNTEREVIDENCE_REQUIRED"
                if primary["option_kind"] == "TARGET_WORK_UNIT"
                else "SEMANTIC_REVIEW_REQUIRED"
            ),
            "rationale_code": str(primary["rationale_code"]),
            "assumption_id": str(primary["assumption_id"]),
            "assumption_code": str(primary["assumption_code"]),
        }
        body["decision_id"] = "l1decide-" + _sha256(body).removeprefix("sha256:")[:16]
        decisions.append(body)
    decisions.sort(key=lambda row: str(row["decision_id"]))
    body = {
        "schema_version": _ALTERNATIVE_PLAN_LEDGER_SCHEMA_VERSION,
        "authority_class": _AUTHORITY_CLASS,
        "decisions": decisions,
        "constraint_decisions": _goal_constraint_decisions(goal_frame),
    }
    body["ledger_digest"] = _sha256(body)
    return body


def _critique_finding(
    *,
    requirement_id: str,
    severity: str,
    code: str,
    failed_invariant: str,
    resolver: str,
    counterexample_or_missing_precondition: str,
) -> dict[str, Any]:
    finding = {
        "requirement_id": requirement_id,
        "severity": severity,
        "code": code,
        "failed_invariant": failed_invariant,
        "resolver": resolver,
        "counterexample_or_missing_precondition": counterexample_or_missing_precondition,
    }
    finding["finding_id"] = "l1crit-" + _sha256(finding).removeprefix("sha256:")[:16]
    return finding


def _append_goal_constraint_findings(
    findings: list[dict[str, Any]], *, goal_frame: Mapping[str, Any]
) -> None:
    """Challenge unresolved constraints before they can become silent omissions."""

    raw_slots = goal_frame.get("constraint_slots")
    if not isinstance(raw_slots, Sequence) or isinstance(raw_slots, (str, bytes)):
        raise L1CognitivePlanError("goal constraint slots are invalid")
    for raw_slot in raw_slots:
        if not isinstance(raw_slot, Mapping):
            raise L1CognitivePlanError("goal constraint slot is invalid")
        slot = dict(raw_slot)
        status = str(slot.get("interpretation_status") or "")
        classification = str(slot.get("classification") or "")
        resolution_reason = str(slot.get("resolution_reason") or "")
        constraint_id = _required_string(
            slot.get("constraint_id"), field="constraint_id"
        )
        if status == "REVIEW_REQUIRED" and classification == "HARD":
            findings.append(
                _critique_finding(
                    requirement_id="",
                    severity="HIGH",
                    code="HARD_CONSTRAINT_SEMANTIC_REVIEW_REQUIRED",
                    failed_invariant="HARD_CONSTRAINT_MUST_BE_ACTIONABLE_OR_ESCALATED",
                    resolver="U0",
                    counterexample_or_missing_precondition=(
                        "UNSAFE_HARD_CONSTRAINT_VALUE_OMITTED_" + constraint_id.upper()
                    ),
                )
            )
        elif status == "DEFERRED_PREFERENCE":
            if resolution_reason == "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT":
                code = "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT"
                failed_invariant = "HARD_CONSTRAINT_TAKES_PRECEDENCE"
                counterexample = (
                    "CONFLICTING_PREFERENCE_OMITTED_TO_PRESERVE_HARD_CONSTRAINT_"
                    + constraint_id.upper()
                )
            elif resolution_reason == "PREFERENCE_CONFLICT_DEFERRED":
                code = "CONFLICTING_PREFERENCES_DEFERRED"
                failed_invariant = (
                    "CONFLICTING_PREFERENCES_CANNOT_BE_SIMULTANEOUSLY_PROJECTED"
                )
                counterexample = (
                    "CONFLICTING_PREFERENCE_OMITTED_" + constraint_id.upper()
                )
            else:
                code = "PREFERENCE_CONSTRAINT_VALUE_OMITTED"
                failed_invariant = "UNSAFE_PREFERENCE_TEXT_MUST_NOT_REACH_PA"
                counterexample = (
                    "UNSAFE_PREFERENCE_VALUE_OMITTED_" + constraint_id.upper()
                )
            findings.append(
                _critique_finding(
                    requirement_id="",
                    severity="MEDIUM",
                    code=code,
                    failed_invariant=failed_invariant,
                    resolver="U0",
                    counterexample_or_missing_precondition=counterexample,
                )
            )

    raw_conflicts = goal_frame.get("constraint_conflicts")
    if not isinstance(raw_conflicts, Sequence) or isinstance(
        raw_conflicts, (str, bytes)
    ):
        raise L1CognitivePlanError("goal constraint conflicts are invalid")
    for raw_conflict in raw_conflicts:
        if not isinstance(raw_conflict, Mapping):
            raise L1CognitivePlanError("goal constraint conflict is invalid")
        conflict = dict(raw_conflict)
        conflict_id = _required_string(
            conflict.get("conflict_id"), field="constraint conflict_id"
        )
        code = _required_string(conflict.get("code"), field="constraint conflict code")
        findings.append(
            _critique_finding(
                requirement_id="",
                severity="HIGH",
                code=code,
                failed_invariant="CONFLICTING_CONSTRAINTS_REQUIRE_RESOLUTION",
                resolver="U0",
                counterexample_or_missing_precondition=(
                    "GOAL_CONSTRAINT_CONFLICT_" + conflict_id.upper()
                ),
            )
        )


def _critique_ledger(
    *,
    goal_frame: Mapping[str, Any],
    graph: Mapping[str, Any],
    alternatives: Mapping[str, Any],
) -> dict[str, Any]:
    """Perform an inspectable pre-execution challenge of every selected option."""

    findings: list[dict[str, Any]] = []
    decisions = {
        str(row.get("requirement_id") or ""): row
        for row in alternatives["decisions"]
        if isinstance(row, Mapping)
    }

    def add_finding(
        *,
        requirement_id: str,
        severity: str,
        code: str,
        failed_invariant: str,
        resolver: str,
        counterexample_or_missing_precondition: str,
    ) -> None:
        findings.append(
            _critique_finding(
                requirement_id=requirement_id,
                severity=severity,
                code=code,
                failed_invariant=failed_invariant,
                resolver=resolver,
                counterexample_or_missing_precondition=counterexample_or_missing_precondition,
            )
        )

    for requirement in graph["requirements"]:
        requirement_id = str(requirement["requirement_id"])
        decision = decisions.get(requirement_id, {})
        status = str(decision.get("decision") or requirement["coverage_status"])
        critical = requirement.get("criticality") == "CRITICAL"
        if critical and status != "MAPPED":
            add_finding(
                requirement_id=requirement_id,
                severity="HIGH",
                code="CRITICAL_REQUIREMENT_NOT_PRECISELY_TARGETED",
                failed_invariant="CRITICAL_REQUIREMENT_HAS_DEFENSIBLE_OPTION",
                resolver="HUMAN",
                counterexample_or_missing_precondition="NO_CONDITIONALLY_FEASIBLE_TARGET",
            )
        if status == "MAPPED":
            preconditions = set(decision.get("required_preconditions") or ())
            if "C0_EVIDENCE_OUTCOME_REQUIRED" not in preconditions:
                add_finding(
                    requirement_id=requirement_id,
                    severity="HIGH",
                    code="TARGET_MISSING_C0_EVIDENCE_PRECONDITION",
                    failed_invariant="TARGETED_REQUIREMENT_REQUIRES_C0_OUTCOME",
                    resolver="L1",
                    counterexample_or_missing_precondition="TARGET_COULD_BE_PRESENTED_AS_SATISFIED_WITHOUT_C0",
                )
            if requirement.get("parent_c0_obligation_eligible") is False:
                add_finding(
                    requirement_id=requirement_id,
                    # The source-bound C0 outcome contract will explicitly turn
                    # this into insufficiency and a bounded safe revision. It is
                    # a condition to observe, not an invented assertion that
                    # should suppress all planning before C0 can inspect it.
                    severity="MEDIUM",
                    code="C0_PARENT_OBLIGATION_PRECONDITION_MISSING",
                    failed_invariant="TARGET_REQUIRES_PARENT_C0_OBLIGATION_OR_SAFE_GAP",
                    resolver="C0",
                    counterexample_or_missing_precondition="C0_PARENT_OBLIGATION_MISSING",
                )
            if str(requirement.get("qualifier_scope") or "NONE") == "SHARED_PARENT":
                add_finding(
                    requirement_id=requirement_id,
                    severity="MEDIUM",
                    code="SHARED_QUALIFIER_SCOPE_REVIEW_REQUIRED",
                    failed_invariant="QUALIFIER_SCOPE_MUST_SURVIVE_TARGETING",
                    resolver="PA",
                    counterexample_or_missing_precondition="QUALIFIER_APPLIES_TO_MULTIPLE_ATOMS",
                )
        elif requirement.get("requirement_type") == "UNKNOWN":
            add_finding(
                requirement_id=requirement_id,
                severity="HIGH" if critical else "MEDIUM",
                code="UNKNOWN_SEMANTICS_NOT_TARGETED",
                failed_invariant="UNKNOWN_SEMANTICS_CANNOT_BE_SILENTLY_TARGETED",
                resolver="HUMAN",
                counterexample_or_missing_precondition="TAXONOMY_HAS_NO_DEFENSIBLE_TYPE",
            )

    mapped_by_target: dict[str, list[Mapping[str, Any]]] = {}
    for requirement in graph["requirements"]:
        for target in requirement.get("target_unit_ids") or ():
            mapped_by_target.setdefault(str(target), []).append(requirement)
    for target, mapped_requirements in sorted(mapped_by_target.items()):
        if len(mapped_requirements) > 1:
            for requirement in mapped_requirements:
                add_finding(
                    requirement_id=str(requirement["requirement_id"]),
                    severity="MEDIUM",
                    code="BROAD_TARGET_COLLISION_REQUIRES_DISTINCT_COVERAGE",
                    failed_invariant="ONE_GENERIC_OUTPUT_ELEMENT_CANNOT_COVER_MULTIPLE_ATOMS",
                    resolver="PA",
                    counterexample_or_missing_precondition=(
                        "MULTIPLE_REQUIREMENT_TYPES_SHARE_TARGET_" + target.upper()
                    ),
                )

    if goal_frame.get("source_resume_available") is not True:
        for requirement in graph["requirements"]:
            if str(requirement.get("coverage_status") or "") == "MAPPED":
                add_finding(
                    requirement_id=str(requirement["requirement_id"]),
                    severity="HIGH",
                    code="CANDIDATE_EVIDENCE_INPUT_MISSING",
                    failed_invariant="TARGETED_REQUIREMENT_REQUIRES_CANDIDATE_EVIDENCE_INPUT",
                    resolver="U0",
                    counterexample_or_missing_precondition="SOURCE_RESUME_TEXT_UNAVAILABLE",
                )
    _append_goal_constraint_findings(findings, goal_frame=goal_frame)
    findings.sort(key=lambda row: str(row["finding_id"]))
    body = {
        "schema_version": "apps_rg.l1_critique_ledger.v2",
        "authority_class": _AUTHORITY_CLASS,
        "finding_count": len(findings),
        "findings": findings,
        "assertions": {
            "does_not_create_candidate_evidence": True,
            "does_not_resolve_conflicts": True,
            "does_not_select_route": True,
            "alternative_ledger_digest": str(alternatives["ledger_digest"]),
            "every_selected_target_has_been_challenged": True,
        },
    }
    body["ledger_digest"] = _sha256(body)
    return body


def _missing_jd_critique(
    *, goal_frame: Mapping[str, Any], alternatives: Mapping[str, Any]
) -> dict[str, Any]:
    """Record missing targeting input without concealing goal-constraint risk."""

    findings = [
        _critique_finding(
            requirement_id="",
            severity="HIGH",
            code="JD_TEXT_NOT_AVAILABLE_FOR_COGNITIVE_PLAN",
            failed_invariant="COGNITIVE_PLAN_REQUIRES_U0_JD_TEXT",
            resolver="U0",
            counterexample_or_missing_precondition="U0_JD_TEXT_UNAVAILABLE",
        )
    ]
    _append_goal_constraint_findings(findings, goal_frame=goal_frame)
    findings.sort(key=lambda row: str(row["finding_id"]))
    body = {
        "schema_version": "apps_rg.l1_critique_ledger.v2",
        "authority_class": _AUTHORITY_CLASS,
        "finding_count": len(findings),
        "findings": findings,
        "assertions": {
            "does_not_create_candidate_evidence": True,
            "does_not_resolve_conflicts": True,
            "does_not_select_route": True,
            "alternative_ledger_digest": str(alternatives["ledger_digest"]),
            "every_selected_target_has_been_challenged": True,
        },
    }
    body["ledger_digest"] = _sha256(body)
    return body


def _contains_forbidden_authority(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key) in _FORBIDDEN_AUTHORITY_KEYS or _contains_forbidden_authority(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_forbidden_authority(item) for item in value)
    return False


def _plan_body(
    *,
    app_payload: Mapping[str, Any],
    request_id: str,
    run_id: str,
    trace_id: str,
    replay_key: str,
    planning_profile_ref: str,
    planning_profile_digest: str,
    v2_capsule: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        if v2_capsule is not None:
            v2 = v2_capsule
        else:
            v2 = build_apps_rg_l1_planning_capsule_v2(
                app_payload=app_payload,
                request_id=request_id,
                run_id=run_id,
                trace_id=trace_id,
                replay_key=replay_key,
                planning_profile_ref=planning_profile_ref,
                planning_profile_digest=planning_profile_digest,
            )
        verification = verify_apps_rg_l1_planning_capsule_v2(v2)
    except L1PlanningV2IntegrityError as exc:
        raise L1CognitivePlanError("v2 planning baseline is invalid") from exc
    jd_text, _source_field = _inline_jd_text(app_payload)
    taxonomy, taxonomy_ref, taxonomy_digest = _load_taxonomy()
    goal_frame = _goal_constraint_frame(app_payload)
    graph = (
        _atomic_requirement_graph(v2_capsule=v2, jd_text=jd_text, taxonomy=taxonomy)
        if jd_text
        else _empty_atomic_requirement_graph()
    )
    feasibility = _feasibility_graph(graph)
    alternatives = _alternative_plan_ledger(graph, feasibility, goal_frame)
    critique = (
        _critique_ledger(
            goal_frame=goal_frame,
            graph=graph,
            alternatives=alternatives,
        )
        if jd_text
        else _missing_jd_critique(
            goal_frame=goal_frame,
            alternatives=alternatives,
        )
    )
    body = {
        "schema_version": L1_COGNITIVE_V3_SCHEMA_VERSION,
        "authority_class": _AUTHORITY_CLASS,
        "app_scope": _APP_SCOPE,
        "request_id": _required_string(request_id, field="request_id"),
        "run_id": _required_string(run_id, field="run_id"),
        "trace_id": _required_string(trace_id, field="trace_id"),
        # The established Apps RG L1/v2 contract permits an empty replay key
        # for a validated request.  Preserve that optional identity field here
        # rather than making the cognitive add-on reject an otherwise valid
        # request before its normal briefing and safety gates can run.
        "replay_key": str(replay_key or ""),
        "v2_parent": {
            "capsule_digest": str(verification["capsule_digest"]),
            "schema_version": str(v2["schema_version"]),
        },
        "planning_priors": [
            {
                "ref": taxonomy_ref,
                "digest": taxonomy_digest,
                "authority_class": "PLANNING_PRIOR_ONLY",
            },
            {
                "ref": planning_profile_ref,
                "digest": planning_profile_digest,
                "authority_class": "PLANNING_PRIOR_ONLY",
            },
        ],
        "goal_constraint_frame": goal_frame,
        "atomic_requirement_graph": graph,
        "feasibility_graph": feasibility,
        "alternative_plan_ledger": alternatives,
        "critique_ledger": critique,
        "planning_status": (
            "BLOCKED"
            if any(row.get("severity") == "HIGH" for row in critique["findings"])
            else "READY"
        ),
        "validation": {
            "u0_payload_only": True,
            "no_route_selection": True,
            "no_evidence_retrieval": True,
            "no_prompt_assembly": True,
            "no_model_call": True,
            "no_tool_call": True,
            "no_l4_write": True,
            "no_candidate_evidence_claim": True,
        },
    }
    return body


def build_l1_cognitive_plan_v3(
    *,
    app_payload: Mapping[str, Any],
    request_id: str,
    run_id: str,
    trace_id: str,
    replay_key: str,
    planning_profile_ref: str,
    planning_profile_digest: str,
    v2_capsule: Mapping[str, Any] | None = None,
) -> FrozenDict:
    """Build an immutable v3 cognitive plan beside the v1/v2 projections."""

    plan = _plan_body(
        app_payload=app_payload,
        request_id=request_id,
        run_id=run_id,
        trace_id=trace_id,
        replay_key=replay_key,
        planning_profile_ref=planning_profile_ref,
        planning_profile_digest=planning_profile_digest,
        v2_capsule=v2_capsule,
    )
    plan["plan_digest"] = cognitive_plan_digest(plan)
    validate_l1_cognitive_plan_v3(plan)
    return _freeze(plan)


def _validate_goal_constraint_frame(frame: Mapping[str, Any]) -> None:
    """Verify the complete non-sensitive goal and constraint representation."""

    if not isinstance(frame, Mapping):
        raise L1CognitivePlanError("goal constraint frame is invalid")
    if (
        frame.get("schema_version") != _GOAL_CONSTRAINT_FRAME_SCHEMA_VERSION
        or frame.get("authority_class") != _AUTHORITY_CLASS
    ):
        raise L1CognitivePlanError("goal constraint frame authority is invalid")
    if not str(frame.get("requested_artifact") or "").strip():
        raise L1CognitivePlanError("goal constraint frame artifact is invalid")
    if not str(frame.get("target_role_digest") or "").startswith("sha256:"):
        raise L1CognitivePlanError("goal constraint frame role digest is invalid")
    if not str(frame.get("source_user_constraints_digest") or "").startswith("sha256:"):
        raise L1CognitivePlanError("goal constraint source binding is invalid")
    if not str(frame.get("source_output_preferences_digest") or "").startswith(
        "sha256:"
    ):
        raise L1CognitivePlanError("goal preference source binding is invalid")
    if not isinstance(frame.get("source_resume_available"), bool):
        raise L1CognitivePlanError(
            "goal constraint frame evidence-input state is invalid"
        )

    entries = frame.get("constraint_entries")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise L1CognitivePlanError("goal constraint entries are invalid")
    classifications = {"HARD", "PREFERENCE", "CONFLICT"}
    entry_rows: list[dict[str, Any]] = []
    seen_source_key_digests: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {
            "source_key_digest",
            "input_origin",
            "classification",
            "value_digest",
        }:
            raise L1CognitivePlanError("goal constraint entry is invalid")
        row = dict(entry)
        source_key_digest = _required_string(
            row.get("source_key_digest"), field="constraint source key digest"
        )
        input_origin = str(row.get("input_origin") or "")
        classification = str(row.get("classification") or "")
        if (
            not source_key_digest.startswith("sha256:")
            or source_key_digest in seen_source_key_digests
            or input_origin not in _VALID_CONSTRAINT_INPUT_ORIGINS
            or classification not in classifications
            or (input_origin == "OUTPUT_PREFERENCE" and classification != "PREFERENCE")
            or not str(row.get("value_digest") or "").startswith("sha256:")
        ):
            raise L1CognitivePlanError("goal constraint entry is incoherent")
        seen_source_key_digests.add(source_key_digest)
        entry_rows.append(row)
    if entry_rows != sorted(
        entry_rows,
        key=lambda row: (
            str(row["classification"]),
            str(row["input_origin"]),
            str(row["source_key_digest"]),
        ),
    ):
        raise L1CognitivePlanError("goal constraint entries are not canonical")

    slots = frame.get("constraint_slots")
    if not isinstance(slots, Sequence) or isinstance(slots, (str, bytes)):
        raise L1CognitivePlanError("goal constraint slots are invalid")
    slot_rows: list[dict[str, Any]] = []
    slot_by_source_key_digest: dict[str, dict[str, Any]] = {}
    expected_slot_fields = {
        "constraint_id",
        "source_key_digest",
        "input_origin",
        "classification",
        "semantic_kind",
        "polarity",
        "scope",
        "value_digest",
        "normalized_value_digest",
        "directive_code",
        "numeric_limit",
        "interpretation_status",
        "downstream_handling",
        "resolution_reason",
    }
    for slot in slots:
        if not isinstance(slot, Mapping) or set(slot) != expected_slot_fields:
            raise L1CognitivePlanError("goal constraint slot is invalid")
        row = dict(slot)
        constraint_id = _required_string(
            row.get("constraint_id"), field="constraint_id"
        )
        source_key_digest = _required_string(
            row.get("source_key_digest"), field="source_key_digest"
        )
        input_origin = str(row.get("input_origin") or "")
        classification = str(row.get("classification") or "")
        kind = str(row.get("semantic_kind") or "")
        polarity = str(row.get("polarity") or "")
        scope = str(row.get("scope") or "")
        status = str(row.get("interpretation_status") or "")
        handling = str(row.get("downstream_handling") or "")
        resolution_reason = str(row.get("resolution_reason") or "")
        directive_code = str(row.get("directive_code") or "")
        if (
            not constraint_id.startswith("l1constraint-")
            or not source_key_digest.startswith("sha256:")
            or source_key_digest in slot_by_source_key_digest
            or input_origin not in _VALID_CONSTRAINT_INPUT_ORIGINS
            or classification not in classifications
            or (input_origin == "OUTPUT_PREFERENCE" and classification != "PREFERENCE")
            or kind not in _VALID_CONSTRAINT_SEMANTIC_KINDS
            or polarity not in _VALID_CONSTRAINT_POLARITIES
            or scope not in _VALID_CONSTRAINT_SCOPES
            or status not in _VALID_CONSTRAINT_INTERPRETATION_STATUSES
            or handling not in _VALID_CONSTRAINT_DOWNSTREAM_HANDLING
            or resolution_reason not in _VALID_CONSTRAINT_RESOLUTION_REASONS
            or not str(row.get("value_digest") or "").startswith("sha256:")
            or not str(row.get("normalized_value_digest") or "").startswith("sha256:")
        ):
            raise L1CognitivePlanError("goal constraint slot is incoherent")
        if kind == "OUTPUT_FORMAT" and directive_code and _output_format_families(row) is None:
            raise L1CognitivePlanError("goal constraint output format directive is invalid")
        numeric_limit = row.get("numeric_limit")
        if numeric_limit is not None:
            if not isinstance(numeric_limit, Mapping) or set(numeric_limit) != {
                "comparison",
                "quantity",
                "unit",
            }:
                raise L1CognitivePlanError("goal constraint numeric limit is invalid")
            if (
                kind != "LENGTH_LIMIT"
                or str(numeric_limit.get("comparison") or "")
                not in {"EXACT", "MAXIMUM", "MINIMUM"}
                or not isinstance(numeric_limit.get("quantity"), int)
                or int(numeric_limit["quantity"]) < 0
                or int(numeric_limit["quantity"]) > 99999
                or str(numeric_limit.get("unit") or "")
                not in {"BULLETS", "CHARACTERS", "ITEMS", "LINES", "PAGES", "WORDS"}
            ):
                raise L1CognitivePlanError(
                    "goal constraint numeric limit is incoherent"
                )
        if status == "ACTIONABLE":
            expected_handling = (
                "PA_SAFE_PREFERENCE_DIRECTIVE"
                if classification == "PREFERENCE"
                else "PA_SAFE_CONSTRAINT_DIRECTIVE"
            )
            if (
                classification == "CONFLICT"
                or not directive_code
                or handling != expected_handling
                or (kind == "LENGTH_LIMIT") != (numeric_limit is not None)
                or resolution_reason != "SAFE_DIRECTIVE"
            ):
                raise L1CognitivePlanError("goal constraint directive is invalid")
        elif status == "CONFLICT":
            if (
                classification != "CONFLICT"
                or polarity != "CONFLICT"
                or directive_code
                or numeric_limit is not None
                or handling != "GOVERNED_U0_RESOLUTION"
                or resolution_reason != "DECLARED_CONFLICT"
            ):
                raise L1CognitivePlanError("goal constraint conflict is incoherent")
        elif status == "REVIEW_REQUIRED":
            if (
                classification != "HARD"
                or directive_code
                or numeric_limit is not None
                or handling != "GOVERNED_U0_RESOLUTION"
                or resolution_reason != "UNSAFE_HARD_VALUE"
            ):
                raise L1CognitivePlanError("goal constraint review is incoherent")
        elif status == "DEFERRED_PREFERENCE":
            if (
                classification != "PREFERENCE"
                or directive_code
                or numeric_limit is not None
                or handling != "OMIT_UNSAFE_PREFERENCE_VALUE"
                or resolution_reason
                not in {
                    "PREFERENCE_CONFLICT_DEFERRED",
                    "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT",
                    "UNSAFE_PREFERENCE_VALUE",
                }
            ):
                raise L1CognitivePlanError("goal constraint preference is incoherent")
        elif status == "OUT_OF_SCOPE":
            expected_handling = (
                "L1_WORK_UNIT_SELECTION"
                if kind == "SECTION_SCOPE"
                else "NO_DOWNSTREAM_EFFECT"
            )
            if (
                kind not in {"SECTION_SCOPE", "SYSTEM_CONTEXT"}
                or directive_code
                or numeric_limit is not None
                or handling != expected_handling
                or resolution_reason
                != ("SECTION_SCOPE" if kind == "SECTION_SCOPE" else "SYSTEM_CONTEXT")
            ):
                raise L1CognitivePlanError("goal constraint scope is incoherent")
        body = dict(row)
        body.pop("constraint_id", None)
        expected_constraint_id = (
            "l1constraint-" + _sha256(body).removeprefix("sha256:")[:16]
        )
        if constraint_id != expected_constraint_id:
            raise L1CognitivePlanError("goal constraint slot identity is invalid")
        slot_rows.append(row)
        slot_by_source_key_digest[source_key_digest] = row
    if slot_rows != sorted(
        slot_rows,
        key=lambda row: (
            str(row["input_origin"]),
            str(row["source_key_digest"]),
            str(row["constraint_id"]),
        ),
    ):
        raise L1CognitivePlanError("goal constraint slots are not canonical")
    if set(slot_by_source_key_digest) != seen_source_key_digests:
        raise L1CognitivePlanError("goal constraint slots do not match entries")
    for entry in entry_rows:
        slot = slot_by_source_key_digest[str(entry["source_key_digest"])]
        if (
            slot.get("input_origin") != entry["input_origin"]
            or slot.get("classification") != entry["classification"]
            or slot.get("value_digest") != entry["value_digest"]
        ):
            raise L1CognitivePlanError("goal constraint slot is not source bound")

    expected_ids_by_class = {
        classification: sorted(
            str(row["constraint_id"])
            for row in slot_rows
            if row["classification"] == classification
        )
        for classification in classifications
    }
    expected_lists = {
        "hard_constraint_ids": expected_ids_by_class["HARD"],
        "preference_constraint_ids": expected_ids_by_class["PREFERENCE"],
        "conflict_constraint_ids": expected_ids_by_class["CONFLICT"],
    }
    for field, expected in expected_lists.items():
        if frame.get(field) != expected:
            raise L1CognitivePlanError(
                "goal constraint frame classification is invalid"
            )

    expected_conflicts = _constraint_conflicts(slot_rows)
    conflicted_constraint_ids = {
        str(constraint_id)
        for conflict in expected_conflicts
        for constraint_id in conflict["constraint_ids"]
    }
    expected_actionable_ids = sorted(
        str(row["constraint_id"])
        for row in slot_rows
        if row["interpretation_status"] == "ACTIONABLE"
    )
    expected_blocking_ids = sorted(
        str(row["constraint_id"])
        for row in slot_rows
        if str(row["constraint_id"]) in conflicted_constraint_ids
        or row["interpretation_status"] == "CONFLICT"
        or (
            row["classification"] == "HARD"
            and row["interpretation_status"] == "REVIEW_REQUIRED"
        )
    )
    if (
        frame.get("actionable_constraint_ids") != expected_actionable_ids
        or frame.get("blocking_constraint_ids") != expected_blocking_ids
    ):
        raise L1CognitivePlanError("goal constraint actionability is invalid")
    if _canonical_json(frame.get("constraint_conflicts")) != _canonical_json(
        expected_conflicts
    ):
        raise L1CognitivePlanError("goal constraint conflicts are invalid")
    if frame.get("input_authority") != {
        "job_description": "TARGETING_INPUT_ONLY",
        "source_resume": "CANDIDATE_EVIDENCE_INPUT",
        "briefing": "CONTEXT_INPUT_ONLY",
        "user_constraints": "REQUEST_CONSTRAINTS_ONLY",
        "output_preferences": "REQUEST_PREFERENCES_ONLY",
    }:
        raise L1CognitivePlanError("goal constraint input authority is invalid")
    if frame.get("definition_of_done") != {
        "all_critical_requirements_targeted_or_escalated": True,
        "candidate_evidence_claims_forbidden": True,
        "downstream_authority_required": True,
        "unsupported_requirement_must_be_escalated_or_omitted": True,
        "all_hard_constraints_actionable_or_escalated": True,
        "hard_constraints_override_preferences": True,
        "unsafe_constraint_text_omitted": True,
    }:
        raise L1CognitivePlanError("goal constraint definition of done is invalid")
    body = dict(frame)
    body.pop("goal_frame_id", None)
    expected_id = "l1goal-" + _sha256(body).removeprefix("sha256:")[:16]
    if frame.get("goal_frame_id") != expected_id:
        raise L1CognitivePlanError("goal constraint frame identity is invalid")


def validate_l1_cognitive_plan_v3(plan: Mapping[str, Any]) -> None:
    """Fail closed unless a v3 plan is source-bound, coherent, and advisory."""

    if not isinstance(plan, Mapping):
        raise L1CognitivePlanError("cognitive plan must be a mapping")
    if plan.get("schema_version") != L1_COGNITIVE_V3_SCHEMA_VERSION:
        raise L1CognitivePlanError("cognitive plan schema_version is invalid")
    if (
        plan.get("authority_class") != _AUTHORITY_CLASS
        or plan.get("app_scope") != _APP_SCOPE
    ):
        raise L1CognitivePlanError("cognitive plan authority is invalid")
    if plan.get("plan_digest") != cognitive_plan_digest(plan):
        raise L1CognitivePlanError("cognitive plan digest mismatch")
    if _contains_forbidden_authority(plan):
        raise L1CognitivePlanError("cognitive plan contains forbidden authority")
    goal_frame = _mapping(plan.get("goal_constraint_frame"))
    _validate_goal_constraint_frame(goal_frame)
    graph = _mapping(plan.get("atomic_requirement_graph"))
    if (
        graph.get("schema_version") != "apps_rg.l1_atomic_requirement_graph.v1"
        or graph.get("authority_class") != _AUTHORITY_CLASS
    ):
        raise L1CognitivePlanError("atomic requirement graph authority is invalid")
    graph_body = dict(graph)
    graph_body.pop("graph_digest", None)
    if graph.get("graph_digest") != _sha256(graph_body):
        raise L1CognitivePlanError("atomic requirement graph digest is invalid")
    requirements = graph.get("requirements")
    if not isinstance(requirements, Sequence) or isinstance(requirements, (str, bytes)):
        raise L1CognitivePlanError("atomic requirement graph is invalid")
    relations = graph.get("relations")
    if not isinstance(relations, Sequence) or isinstance(relations, (str, bytes)):
        raise L1CognitivePlanError("atomic requirement relations are invalid")
    ids: set[str] = set()
    requirements_by_id: dict[str, Mapping[str, Any]] = {}
    for requirement in requirements:
        if not isinstance(requirement, Mapping):
            raise L1CognitivePlanError("atomic requirement is invalid")
        requirement_id = _required_string(
            requirement.get("requirement_id"), field="requirement_id"
        )
        if requirement_id in ids:
            raise L1CognitivePlanError("atomic requirement IDs must be unique")
        ids.add(requirement_id)
        requirements_by_id[requirement_id] = requirement
        _required_string(
            requirement.get("parent_requirement_id"), field="parent requirement_id"
        )
        ordinal = requirement.get("ordinal")
        if not isinstance(ordinal, int) or ordinal < 1:
            raise L1CognitivePlanError("atomic requirement ordinal is invalid")
        status = str(requirement.get("coverage_status") or "")
        if status not in _VALID_COVERAGE:
            raise L1CognitivePlanError("atomic requirement coverage is invalid")
        span = _mapping(requirement.get("source_span"))
        if (
            str(span.get("source_field") or "") != "job_description_text"
            or not isinstance(span.get("start_offset"), int)
            or not isinstance(span.get("end_offset"), int)
            or int(span["start_offset"]) < 0
            or int(span["end_offset"]) <= int(span["start_offset"])
            or not str(span.get("text_digest") or "").startswith("sha256:")
            or not str(span.get("span_digest") or "").startswith("sha256:")
        ):
            raise L1CognitivePlanError("atomic requirement must have a source span")
        if not str(requirement.get("semantic_clause_digest") or "").startswith(
            "sha256:"
        ):
            raise L1CognitivePlanError("atomic requirement semantic digest is invalid")
        if str(requirement.get("decomposition_mode") or "") not in {
            "UNSPLIT_SOURCE_CLAUSE",
            "AMBIGUOUS_COORDINATION_PRESERVED",
            "EXPLICIT_SENTENCE_PREDICATE",
            "EXPLICIT_PREDICATE",
            "INHERITED_PREDICATE",
        }:
            raise L1CognitivePlanError(
                "atomic requirement decomposition mode is invalid"
            )
        if str(requirement.get("qualifier_scope") or "") not in {
            "NONE",
            "LOCAL",
            "SHARED_PARENT",
        }:
            raise L1CognitivePlanError("atomic requirement qualifier scope is invalid")
        if str(requirement.get("inherited_predicate_class") or "") not in {
            "LEADERSHIP_ACTION",
            "BUILD_DELIVER_ACTION",
            "OPERATE_GOVERN_ACTION",
            "CAPABILITY_ACTION",
            "UNSPECIFIED_ACTION",
        }:
            raise L1CognitivePlanError("atomic requirement predicate class is invalid")
        qualifiers = requirement.get("qualifiers")
        if not isinstance(qualifiers, Sequence) or isinstance(qualifiers, (str, bytes)):
            raise L1CognitivePlanError("atomic requirement qualifiers are invalid")
        if any(not isinstance(qualifier, Mapping) for qualifier in qualifiers):
            raise L1CognitivePlanError("atomic requirement qualifier is invalid")
        qualifier_scope = str(requirement.get("qualifier_scope") or "")
        if (qualifier_scope == "NONE" and qualifiers) or (
            qualifier_scope != "NONE" and not qualifiers
        ):
            raise L1CognitivePlanError(
                "atomic requirement qualifier scope is incoherent"
            )
        targets = requirement.get("target_unit_ids")
        if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)):
            raise L1CognitivePlanError("atomic requirement targets are invalid")
        if (status == "MAPPED" and len(targets) != 1) or (
            status != "MAPPED" and targets
        ):
            raise L1CognitivePlanError("atomic requirement targets are incoherent")
        if status == "MAPPED" and str(requirement.get("escalation_reason") or ""):
            raise L1CognitivePlanError("mapped requirement cannot carry escalation")
        if status != "MAPPED" and not str(requirement.get("escalation_reason") or ""):
            raise L1CognitivePlanError("unresolved requirement lacks escalation")
        if requirement.get("requirement_type") == "UNKNOWN" and status == "MAPPED":
            raise L1CognitivePlanError("unknown requirement cannot be silently mapped")
        parent_coverage_status = str(requirement.get("parent_coverage_status") or "")
        if parent_coverage_status:
            if parent_coverage_status not in _VALID_COVERAGE:
                raise L1CognitivePlanError(
                    "atomic requirement parent coverage is invalid"
                )
        parent_c0_obligation_eligible = requirement.get("parent_c0_obligation_eligible")
        if parent_c0_obligation_eligible is not None:
            if not isinstance(parent_c0_obligation_eligible, bool):
                raise L1CognitivePlanError(
                    "atomic requirement C0 parent eligibility is invalid"
                )
            if parent_coverage_status and parent_c0_obligation_eligible != (
                parent_coverage_status == "MAPPED"
            ):
                raise L1CognitivePlanError(
                    "atomic requirement C0 parent eligibility is inconsistent"
                )
    relation_keys: set[tuple[str, str, str]] = set()
    relation_review_ids: set[str] = set()
    for relation in relations:
        if not isinstance(relation, Mapping):
            raise L1CognitivePlanError("atomic requirement relation is invalid")
        from_id = _required_string(
            relation.get("from_requirement_id"), field="relation from requirement_id"
        )
        to_id = _required_string(
            relation.get("to_requirement_id"), field="relation to requirement_id"
        )
        relation_type = str(relation.get("relation") or "")
        if (
            from_id not in ids
            or to_id not in ids
            or relation_type not in _RELATION_TYPES
        ):
            raise L1CognitivePlanError("atomic requirement relation is unbound")
        expected_scope = {
            "AND": "CONJUNCTIVE",
            "OR": "ALTERNATIVE",
            "NOT": "RESTRICTION",
            "EXCEPTION": "RESTRICTION",
        }[relation_type]
        from_requirement = requirements_by_id[from_id]
        to_requirement = requirements_by_id[to_id]
        if (
            relation.get("relation_scope") != expected_scope
            or from_requirement.get("parent_requirement_id")
            != to_requirement.get("parent_requirement_id")
            or int(to_requirement["ordinal"]) != int(from_requirement["ordinal"]) + 1
        ):
            raise L1CognitivePlanError("atomic requirement relation scope is invalid")
        key = (from_id, to_id, relation_type)
        if key in relation_keys:
            raise L1CognitivePlanError("atomic requirement relations must be unique")
        relation_keys.add(key)
        if relation_type in {"OR", "NOT", "EXCEPTION"}:
            relation_review_ids.update((from_id, to_id))
    for requirement_id in relation_review_ids:
        requirement = requirements_by_id[requirement_id]
        if (
            requirement.get("coverage_status") != "ESCALATED"
            or requirement.get("target_unit_ids")
            or requirement.get("escalation_reason") != "RELATION_SCOPE_REVIEW_REQUIRED"
        ):
            raise L1CognitivePlanError(
                "conditional relation cannot be silently targeted"
            )

    feasibility = _mapping(plan.get("feasibility_graph"))
    if (
        feasibility.get("schema_version") != "apps_rg.l1_feasibility_graph.v2"
        or feasibility.get("authority_class") != _AUTHORITY_CLASS
    ):
        raise L1CognitivePlanError("feasibility graph authority is invalid")
    feasibility_body = dict(feasibility)
    feasibility_body.pop("graph_digest", None)
    if feasibility.get("graph_digest") != _sha256(feasibility_body):
        raise L1CognitivePlanError("feasibility graph digest is invalid")
    options = feasibility.get("options")
    if not isinstance(options, Sequence) or isinstance(options, (str, bytes)):
        raise L1CognitivePlanError("feasibility options are invalid")
    option_by_id: dict[str, Mapping[str, Any]] = {}
    options_by_requirement: dict[str, list[Mapping[str, Any]]] = {}
    for option in options:
        if not isinstance(option, Mapping):
            raise L1CognitivePlanError("feasibility option is invalid")
        option_id = _required_string(option.get("option_id"), field="option_id")
        requirement_id = _required_string(
            option.get("requirement_id"), field="option requirement_id"
        )
        if option_id in option_by_id or requirement_id not in ids:
            raise L1CognitivePlanError("feasibility option identity is invalid")
        if option.get("option_kind") not in {"TARGET_WORK_UNIT", "ESCALATE"}:
            raise L1CognitivePlanError("feasibility option kind is invalid")
        if option.get("coverage_status") not in _VALID_COVERAGE:
            raise L1CognitivePlanError("feasibility option coverage is invalid")
        if not isinstance(option.get("precondition_codes"), Sequence) or isinstance(
            option.get("precondition_codes"), (str, bytes)
        ):
            raise L1CognitivePlanError("feasibility option preconditions are invalid")
        if not str(option.get("assumption_id") or "").startswith("l1assume-"):
            raise L1CognitivePlanError("feasibility option assumption is invalid")
        option_by_id[option_id] = option
        options_by_requirement.setdefault(requirement_id, []).append(option)
    for requirement in requirements:
        requirement_id = str(requirement["requirement_id"])
        scoped_options = options_by_requirement.get(requirement_id, [])
        if (
            sum(option.get("option_kind") == "ESCALATE" for option in scoped_options)
            != 1
        ):
            raise L1CognitivePlanError("every requirement needs one escalation option")
        if requirement.get("coverage_status") == "MAPPED" and not any(
            option.get("option_kind") == "TARGET_WORK_UNIT" for option in scoped_options
        ):
            raise L1CognitivePlanError("mapped requirement lacks a target option")
    expected_feasibility = _feasibility_graph({"requirements": requirements})
    if _canonical_json(options) != _canonical_json(expected_feasibility["options"]):
        raise L1CognitivePlanError("feasibility graph does not match atomic plan")

    alternatives = _mapping(plan.get("alternative_plan_ledger"))
    if (
        alternatives.get("schema_version") != _ALTERNATIVE_PLAN_LEDGER_SCHEMA_VERSION
        or alternatives.get("authority_class") != _AUTHORITY_CLASS
    ):
        raise L1CognitivePlanError("alternative plan ledger authority is invalid")
    alternatives_body = dict(alternatives)
    alternatives_body.pop("ledger_digest", None)
    if alternatives.get("ledger_digest") != _sha256(alternatives_body):
        raise L1CognitivePlanError("alternative plan ledger digest is invalid")
    decisions = alternatives.get("decisions")
    if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes)):
        raise L1CognitivePlanError("alternative plan decisions are invalid")
    decision_ids: set[str] = set()
    decision_requirement_ids: set[str] = set()
    for decision in decisions:
        if not isinstance(decision, Mapping):
            raise L1CognitivePlanError("alternative plan decision is invalid")
        decision_id = _required_string(decision.get("decision_id"), field="decision_id")
        requirement_id = _required_string(
            decision.get("requirement_id"), field="decision requirement_id"
        )
        primary_id = _required_string(
            decision.get("primary_option_id"), field="primary option_id"
        )
        primary = option_by_id.get(primary_id)
        if (
            decision_id in decision_ids
            or requirement_id in decision_requirement_ids
            or primary is None
            or primary.get("requirement_id") != requirement_id
            or decision.get("decision") != primary.get("coverage_status")
        ):
            raise L1CognitivePlanError("alternative plan decision is unbound")
        alternative_id = str(decision.get("alternative_option_id") or "")
        tradeoff_present = decision.get("tradeoff_present")
        if not isinstance(tradeoff_present, bool):
            raise L1CognitivePlanError("alternative plan tradeoff state is invalid")
        if tradeoff_present:
            alternative = option_by_id.get(alternative_id)
            if (
                alternative is None
                or alternative.get("requirement_id") != requirement_id
                or alternative_id == primary_id
            ):
                raise L1CognitivePlanError("alternative plan tradeoff is unbound")
        elif alternative_id:
            raise L1CognitivePlanError(
                "non-tradeoff decision cannot carry an alternative"
            )
        if not str(decision.get("risk") or ""):
            raise L1CognitivePlanError("alternative plan decision risk is invalid")
        decision_ids.add(decision_id)
        decision_requirement_ids.add(requirement_id)
    if decision_requirement_ids != ids:
        raise L1CognitivePlanError("alternative plan must decide every requirement")
    constraint_decisions = alternatives.get("constraint_decisions")
    if not isinstance(constraint_decisions, Sequence) or isinstance(
        constraint_decisions, (str, bytes)
    ):
        raise L1CognitivePlanError("alternative constraint decisions are invalid")
    expected_constraint_ids = {
        str(row["constraint_id"])
        for row in goal_frame.get("constraint_slots") or ()
        if isinstance(row, Mapping)
    }
    observed_constraint_ids: set[str] = set()
    constraint_decision_ids: set[str] = set()
    for raw_decision in constraint_decisions:
        if not isinstance(raw_decision, Mapping) or set(raw_decision) != {
            "constraint_id",
            "constraint_decision_id",
            "primary_action",
            "alternative_action",
            "selection_rule",
            "risk",
        }:
            raise L1CognitivePlanError("alternative constraint decision is invalid")
        decision = dict(raw_decision)
        constraint_id = _required_string(
            decision.get("constraint_id"), field="alternative constraint_id"
        )
        constraint_decision_id = _required_string(
            decision.get("constraint_decision_id"),
            field="alternative constraint_decision_id",
        )
        if (
            constraint_id not in expected_constraint_ids
            or constraint_id in observed_constraint_ids
            or constraint_decision_id in constraint_decision_ids
            or not constraint_decision_id.startswith("l1constraintdecision-")
            or not str(decision.get("primary_action") or "")
            or not str(decision.get("selection_rule") or "")
            or not str(decision.get("risk") or "")
        ):
            raise L1CognitivePlanError("alternative constraint decision is incoherent")
        body = dict(decision)
        body.pop("constraint_decision_id", None)
        expected_decision_id = (
            "l1constraintdecision-" + _sha256(body).removeprefix("sha256:")[:16]
        )
        if constraint_decision_id != expected_decision_id:
            raise L1CognitivePlanError(
                "alternative constraint decision identity is invalid"
            )
        observed_constraint_ids.add(constraint_id)
        constraint_decision_ids.add(constraint_decision_id)
    if observed_constraint_ids != expected_constraint_ids:
        raise L1CognitivePlanError("alternative constraint decisions are incomplete")
    expected_alternatives = _alternative_plan_ledger(graph, feasibility, goal_frame)
    if _canonical_json(alternatives) != _canonical_json(expected_alternatives):
        raise L1CognitivePlanError("alternative plan ledger does not match feasibility")

    critique = _mapping(plan.get("critique_ledger"))
    if (
        critique.get("schema_version") != "apps_rg.l1_critique_ledger.v2"
        or critique.get("authority_class") != _AUTHORITY_CLASS
        or _mapping(critique.get("assertions")).get("alternative_ledger_digest")
        != alternatives.get("ledger_digest")
    ):
        raise L1CognitivePlanError("critique ledger authority is invalid")
    critique_body = dict(critique)
    critique_body.pop("ledger_digest", None)
    if critique.get("ledger_digest") != _sha256(critique_body):
        raise L1CognitivePlanError("critique ledger digest is invalid")
    findings = critique.get("findings")
    if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)):
        raise L1CognitivePlanError("critique ledger is invalid")
    for finding in findings:
        if not isinstance(finding, Mapping):
            raise L1CognitivePlanError("critique finding is invalid")
        if finding.get("severity") not in {"LOW", "MEDIUM", "HIGH"}:
            raise L1CognitivePlanError("critique finding severity is invalid")
        if not str(finding.get("code") or "") or not str(
            finding.get("counterexample_or_missing_precondition") or ""
        ):
            raise L1CognitivePlanError("critique finding is incomplete")
        finding_requirement_id = str(finding.get("requirement_id") or "")
        if finding_requirement_id and finding_requirement_id not in ids:
            raise L1CognitivePlanError("critique finding exceeds plan scope")
    if not requirements and not any(
        _mapping(finding).get("code") == "JD_TEXT_NOT_AVAILABLE_FOR_COGNITIVE_PLAN"
        for finding in findings
    ):
        raise L1CognitivePlanError(
            "empty cognitive plan must record missing U0 JD text"
        )
    expected_critique = (
        _critique_ledger(
            goal_frame=goal_frame,
            graph=graph,
            alternatives=alternatives,
        )
        if requirements
        else _missing_jd_critique(
            goal_frame=goal_frame,
            alternatives=alternatives,
        )
    )
    if _canonical_json(critique) != _canonical_json(expected_critique):
        raise L1CognitivePlanError("critique ledger does not match selected plan")
    expected_status = (
        "BLOCKED"
        if any(_mapping(finding).get("severity") == "HIGH" for finding in findings)
        else "READY"
    )
    if plan.get("planning_status") != expected_status:
        raise L1CognitivePlanError("cognitive planning status is invalid")


def _build_l1_cognitive_revision_from_validated_c0_outcomes(
    *,
    plan: Mapping[str, Any],
    observed_outcomes: Sequence[Mapping[str, Any]],
    c0_outcome_receipt_digest: str,
) -> FrozenDict:
    """Produce one bounded delta from already-validated C0 failure outcomes.

    This is intentionally internal to the C0 outcome contract. C0 is currently
    the only Apps RG authority that can prove an L1 assumption false. PA/L2/L3
    disposition failures are recorded as downstream defects by their own
    source-bound contracts; they cannot be passed here to manufacture an L1
    replan.

    The revision replaces only the failed atom's selected option with that
    atom's already-declared escalation alternative, records the disproved
    assumption, and predicts the safe correction. It remains advisory and
    never retries or executes.
    """

    validate_l1_cognitive_plan_v3(plan)
    outcome_receipt_digest = _required_string(
        c0_outcome_receipt_digest,
        field="C0 outcome receipt digest",
    )
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", outcome_receipt_digest):
        raise L1CognitivePlanError("C0 outcome receipt digest is invalid")
    requirement_ids = {
        str(row["requirement_id"])
        for row in plan["atomic_requirement_graph"]["requirements"]
    }
    alternatives = _mapping(plan.get("alternative_plan_ledger"))
    decisions = {
        str(row.get("requirement_id") or ""): row
        for row in alternatives.get("decisions") or ()
        if isinstance(row, Mapping)
    }
    options_by_requirement: dict[str, list[Mapping[str, Any]]] = {}
    for option in _mapping(plan.get("feasibility_graph")).get("options") or ():
        if isinstance(option, Mapping):
            options_by_requirement.setdefault(
                str(option.get("requirement_id") or ""), []
            ).append(option)
    changes: list[dict[str, Any]] = []
    observed_requirement_ids: set[str] = set()
    for outcome in observed_outcomes:
        if not isinstance(outcome, Mapping):
            raise L1CognitivePlanError("observed outcome is invalid")
        requirement_id = _required_string(
            outcome.get("requirement_id"), field="outcome requirement_id"
        )
        if requirement_id not in requirement_ids:
            raise L1CognitivePlanError("observed outcome is outside the cognitive plan")
        if requirement_id in observed_requirement_ids:
            raise L1CognitivePlanError("observed outcome repeats a requirement")
        observed_requirement_ids.add(requirement_id)
        code = _required_string(outcome.get("code"), field="outcome code")
        if code not in _VALID_C0_FAILURE_OUTCOMES:
            raise L1CognitivePlanError("observed outcome code is invalid")
        observation_ref = _required_string(
            outcome.get("observation_ref"), field="observation_ref"
        )
        if (
            Path(observation_ref.split("#", 1)[0]).is_absolute()
            or ".." in Path(observation_ref.split("#", 1)[0]).parts
        ):
            raise L1CognitivePlanError("observed outcome reference is invalid")
        decision = decisions.get(requirement_id)
        if decision is None:
            raise L1CognitivePlanError("observed outcome lacks a plan decision")
        options = options_by_requirement.get(requirement_id, [])
        primary_option_id = str(decision.get("primary_option_id") or "")
        primary_option = next(
            (
                row
                for row in options
                if str(row.get("option_id") or "") == primary_option_id
            ),
            None,
        )
        escalation_option = next(
            (row for row in options if row.get("option_kind") == "ESCALATE"),
            None,
        )
        if primary_option is None or escalation_option is None:
            raise L1CognitivePlanError(
                "observed outcome lacks a bounded fallback option"
            )
        already_escalated = primary_option.get("option_kind") == "ESCALATE"
        change = {
            "requirement_id": requirement_id,
            "observed_outcome_code": code,
            "observation_ref": observation_ref,
            "disproved_assumption_id": str(decision.get("assumption_id") or ""),
            "disproved_assumption_code": str(decision.get("assumption_code") or ""),
            "superseded_decision_id": str(decision.get("decision_id") or ""),
            "superseded_option_id": primary_option_id,
            "replacement_option_id": str(escalation_option.get("option_id") or ""),
            "revised_decision": "ESCALATED",
            "action": (
                "RETAIN_ESCALATION_AFTER_OBSERVATION"
                if already_escalated
                else "REPLACE_TARGET_WITH_ESCALATION"
            ),
            "predicted_correction": "PREVENT_UNSUPPORTED_REQUIREMENT_SATISFACTION",
            "new_risk": "NAMED_RESOLVER_REQUIRED",
            "automatic_retry": False,
            "route_change": False,
            "evidence_authority_change": False,
        }
        change["change_id"] = "l1rev-" + _sha256(change).removeprefix("sha256:")[:16]
        changes.append(change)
    changes.sort(key=lambda row: str(row["change_id"]))
    body = {
        "schema_version": L1_COGNITIVE_V3_REVISION_SCHEMA_VERSION,
        "authority_class": _AUTHORITY_CLASS,
        "app_scope": _APP_SCOPE,
        "parent_plan_digest": str(plan["plan_digest"]),
        "c0_outcome_receipt_digest": outcome_receipt_digest,
        "revision_scope_requirement_ids": sorted(
            {str(change["requirement_id"]) for change in changes}
        ),
        "changes": changes,
        "parent_vs_revised_comparison": {
            "changed_requirement_count": len(changes),
            "unrelated_requirement_change_count": 0,
            "replacement_policy": "FAILED_ATOM_ONLY_TO_DECLARED_ESCALATION_OPTION",
            "predicted_safety_effect": "UNSUPPORTED_REQUIREMENT_CANNOT_REMAIN_SELECTED",
        },
        "status": "PROPOSED" if changes else "NO_REVISION",
        "assertions": {
            "one_bounded_revision": True,
            "automatic_retry": False,
            "does_not_execute": True,
            "does_not_select_route": True,
            "does_not_create_evidence": True,
            "does_not_change_unaffected_requirements": True,
        },
    }
    body["revision_digest"] = cognitive_revision_digest(body)
    validate_l1_cognitive_revision_v3(body, plan=plan)
    return _freeze(body)


def validate_l1_cognitive_revision_v3(
    revision: Mapping[str, Any], *, plan: Mapping[str, Any]
) -> None:
    """Fail closed unless a revision is bounded to observed plan failures."""

    validate_l1_cognitive_plan_v3(plan)
    if not isinstance(revision, Mapping):
        raise L1CognitivePlanError("cognitive revision must be a mapping")
    if revision.get("schema_version") != L1_COGNITIVE_V3_REVISION_SCHEMA_VERSION:
        raise L1CognitivePlanError("cognitive revision schema_version is invalid")
    if (
        revision.get("authority_class") != _AUTHORITY_CLASS
        or revision.get("app_scope") != _APP_SCOPE
    ):
        raise L1CognitivePlanError("cognitive revision authority is invalid")
    if revision.get("revision_digest") != cognitive_revision_digest(revision):
        raise L1CognitivePlanError("cognitive revision digest mismatch")
    if revision.get("parent_plan_digest") != plan.get("plan_digest"):
        raise L1CognitivePlanError("cognitive revision parent plan is invalid")
    outcome_receipt_digest = _required_string(
        revision.get("c0_outcome_receipt_digest"),
        field="cognitive revision C0 outcome receipt digest",
    )
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", outcome_receipt_digest):
        raise L1CognitivePlanError("cognitive revision C0 outcome receipt digest is invalid")
    if _contains_forbidden_authority(revision):
        raise L1CognitivePlanError("cognitive revision contains forbidden authority")
    changes = revision.get("changes")
    if not isinstance(changes, Sequence) or isinstance(changes, (str, bytes)):
        raise L1CognitivePlanError("cognitive revision changes are invalid")
    scope = set(revision.get("revision_scope_requirement_ids") or ())
    if scope != {str(change.get("requirement_id") or "") for change in changes}:
        raise L1CognitivePlanError("cognitive revision scope is invalid")
    if len(scope) != len(changes):
        raise L1CognitivePlanError("cognitive revision cannot repeat a requirement")
    expected_status = "PROPOSED" if changes else "NO_REVISION"
    if revision.get("status") != expected_status:
        raise L1CognitivePlanError("cognitive revision status is invalid")
    comparison = revision.get("parent_vs_revised_comparison")
    if comparison != {
        "changed_requirement_count": len(changes),
        "unrelated_requirement_change_count": 0,
        "replacement_policy": "FAILED_ATOM_ONLY_TO_DECLARED_ESCALATION_OPTION",
        "predicted_safety_effect": "UNSUPPORTED_REQUIREMENT_CANNOT_REMAIN_SELECTED",
    }:
        raise L1CognitivePlanError("cognitive revision comparison is invalid")
    if revision.get("assertions") != {
        "one_bounded_revision": True,
        "automatic_retry": False,
        "does_not_execute": True,
        "does_not_select_route": True,
        "does_not_create_evidence": True,
        "does_not_change_unaffected_requirements": True,
    }:
        raise L1CognitivePlanError("cognitive revision assertions are invalid")
    alternatives = _mapping(plan.get("alternative_plan_ledger"))
    decisions = {
        str(row.get("requirement_id") or ""): row
        for row in alternatives.get("decisions") or ()
        if isinstance(row, Mapping)
    }
    feasibility = _mapping(plan.get("feasibility_graph"))
    options_by_id = {
        str(row.get("option_id") or ""): row
        for row in feasibility.get("options") or ()
        if isinstance(row, Mapping)
    }
    for change in changes:
        if not isinstance(change, Mapping):
            raise L1CognitivePlanError("cognitive revision change is invalid")
        if (
            change.get("automatic_retry") is not False
            or change.get("route_change") is not False
            or change.get("evidence_authority_change") is not False
        ):
            raise L1CognitivePlanError("cognitive revision must remain advisory")
        requirement_id = _required_string(
            change.get("requirement_id"), field="revision requirement_id"
        )
        observed_outcome_code = _required_string(
            change.get("observed_outcome_code"),
            field="revision observed outcome code",
        )
        if observed_outcome_code not in _VALID_C0_FAILURE_OUTCOMES:
            raise L1CognitivePlanError("revision observed outcome code is invalid")
        observation_ref = _required_string(
            change.get("observation_ref"),
            field="revision observation reference",
        )
        observation_path = observation_ref.split("#", 1)[0]
        if (
            not observation_path
            or Path(observation_path).is_absolute()
            or ".." in Path(observation_path).parts
        ):
            raise L1CognitivePlanError("revision observation reference is invalid")
        decision = decisions.get(requirement_id)
        if decision is None:
            raise L1CognitivePlanError("cognitive revision decision is unbound")
        superseded_option_id = _required_string(
            change.get("superseded_option_id"), field="revision superseded option_id"
        )
        replacement_option_id = _required_string(
            change.get("replacement_option_id"), field="revision replacement option_id"
        )
        superseded = options_by_id.get(superseded_option_id)
        replacement = options_by_id.get(replacement_option_id)
        if (
            superseded is None
            or replacement is None
            or superseded.get("requirement_id") != requirement_id
            or replacement.get("requirement_id") != requirement_id
            or replacement.get("option_kind") != "ESCALATE"
            or change.get("superseded_decision_id") != decision.get("decision_id")
            or superseded_option_id != decision.get("primary_option_id")
        ):
            raise L1CognitivePlanError("cognitive revision option delta is invalid")
        if (
            change.get("disproved_assumption_id") != decision.get("assumption_id")
            or change.get("disproved_assumption_code")
            != decision.get("assumption_code")
            or change.get("revised_decision") != "ESCALATED"
            or change.get("predicted_correction")
            != "PREVENT_UNSUPPORTED_REQUIREMENT_SATISFACTION"
            or change.get("new_risk") != "NAMED_RESOLVER_REQUIRED"
        ):
            raise L1CognitivePlanError("cognitive revision reasoning delta is invalid")
        expected_action = (
            "RETAIN_ESCALATION_AFTER_OBSERVATION"
            if superseded.get("option_kind") == "ESCALATE"
            else "REPLACE_TARGET_WITH_ESCALATION"
        )
        if change.get("action") != expected_action:
            raise L1CognitivePlanError("cognitive revision action is invalid")
        change_body = dict(change)
        change_body.pop("change_id", None)
        expected_change_id = (
            "l1rev-" + _sha256(change_body).removeprefix("sha256:")[:16]
        )
        if change.get("change_id") != expected_change_id:
            raise L1CognitivePlanError("cognitive revision change digest is invalid")


__all__ = [
    "L1CognitivePlanError",
    "L1_COGNITIVE_V3_REVISION_SCHEMA_VERSION",
    "L1_COGNITIVE_V3_SCHEMA_VERSION",
    "build_l1_cognitive_plan_v3",
    "cognitive_plan_digest",
    "cognitive_revision_digest",
    "validate_l1_cognitive_plan_v3",
    "validate_l1_cognitive_revision_v3",
]
