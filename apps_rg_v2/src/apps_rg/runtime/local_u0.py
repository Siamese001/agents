"""App-owned U0 ingress reflection receipt."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AppsRgU0ReflectionReceipt:
    contract_version: str
    schema_version: str
    field_map_version: str
    input_payload_digest: str
    validated_request_digest: str
    pointers_total: int
    pointers_mapped: int
    pointers_derived: int
    pointers_rejected: int
    pointers_deferred: int
    deferred_reasons: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    silently_dropped: tuple[str, ...] = field(default_factory=tuple)
    unknown_mappings: tuple[str, ...] = field(default_factory=tuple)
    pass_status: bool = False
    timestamp_iso: str = ""


__all__ = ["AppsRgU0ReflectionReceipt"]
