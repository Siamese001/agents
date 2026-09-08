"""Alias and backward-compatibility re-export for ExecutiveVoiceRepairAgent."""

from apps_rg.runtime.sections.ExecutiveVoiceRepairAgent import (
    DEFAULT_REPAIR_MODEL,
    EXECUTIVE_VOICE_REPAIR_AGENT_ENABLED_DEFAULT,
    EXECUTIVE_VOICE_REPAIR_MAX_ATTEMPTS,
    ExecutiveVoiceRepairAgent,
    ExecutiveVoiceRepairReceipt,
    X1_REPAIR_AGENT_ENABLED_DEFAULT,
    X1_REPAIR_MAX_ATTEMPTS,
    X1RepairAgent,
    X1RepairReceipt,
    _split_into_sentences,
    executive_voice_repair_enabled,
    repair_section_with_executive_voice_agent,
    repair_section_with_x1_agent,
    x1_repair_enabled,
)

__all__ = [
    "DEFAULT_REPAIR_MODEL",
    "ExecutiveVoiceRepairAgent",
    "ExecutiveVoiceRepairReceipt",
    "EXECUTIVE_VOICE_REPAIR_AGENT_ENABLED_DEFAULT",
    "EXECUTIVE_VOICE_REPAIR_MAX_ATTEMPTS",
    "repair_section_with_executive_voice_agent",
    "executive_voice_repair_enabled",
    "_split_into_sentences",
    "X1RepairAgent",
    "X1RepairReceipt",
    "X1_REPAIR_AGENT_ENABLED_DEFAULT",
    "X1_REPAIR_MAX_ATTEMPTS",
    "repair_section_with_x1_agent",
    "x1_repair_enabled",
]
