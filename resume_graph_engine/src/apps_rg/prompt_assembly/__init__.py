# apps_rg Prompt Assembly Package
# Local compile/validation path for declarative PA artifacts
# Wave 6: compiler + contracts skeleton (no runtime wiring)

from .contracts import (
    PromptAssemblyInput,
    PromptSlotPayload,
    CompiledPromptArtifact,
    PromptAssemblyError,
    EvidenceSource,
    ComponentHashMap,
    SlotAuthority,
    SlotName,
    AUTHORITY_PRECEDENCE,
)

from .compiler import (
    PromptCompiler,
    compile_prompt,
    map_slots,
    CANONICAL_SLOT_ORDER,
    OVERRIDE_ATTEMPT_PATTERNS,
    LOWER_AUTHORITY_SLOTS,
    PROTECTED_SLOTS,
)

from .prompt_segment import (
    PromptScope,
    PromptSegment,
    canonical_prompt_json,
    classify_slot_scope,
    compute_stable_prefix_hash,
)

__all__ = [
    # Contracts
    "PromptAssemblyInput",
    "PromptSlotPayload",
    "CompiledPromptArtifact",
    "PromptAssemblyError",
    "EvidenceSource",
    "ComponentHashMap",
    "SlotAuthority",
    "SlotName",
    "AUTHORITY_PRECEDENCE",
    # Compiler
    "PromptCompiler",
    "compile_prompt",
    "map_slots",
    "CANONICAL_SLOT_ORDER",
    # W7: Negative controls
    "OVERRIDE_ATTEMPT_PATTERNS",
    "LOWER_AUTHORITY_SLOTS",
    "PROTECTED_SLOTS",
    # Prompt Caching & Segments
    "PromptScope",
    "PromptSegment",
    "canonical_prompt_json",
    "classify_slot_scope",
    "compute_stable_prefix_hash",
]

__version__ = "1.0.0"
