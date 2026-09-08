"""Apps RG-owned provider contracts and deterministic test gateway.

The application owns the provider boundary.  Live provider adapters remain
explicit application integrations; this module never imports another runtime
package to decide how an Apps RG request is represented or blocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


CACHE_TTL_1H = "1h"
CACHE_TTL_5M = "5m"


def min_cacheable_chars(_model: str) -> int:
    """Return the Apps RG prompt-cache floor in normalized characters."""

    return 1024


class ProviderKind(str, Enum):
    STUB = "stub"
    EXTERNAL_API = "external_api"
    LOCAL_VLLM = "local_vllm"


class ProviderMode(str, Enum):
    STUB_ONLY = "stub_only"
    LIVE_ALLOWED = "live_allowed"
    DISABLED = "disabled"
    LOCAL_ONLY = "local_only"


class ProviderModeBlockedError(RuntimeError):
    """The requested provider cannot run in the declared application mode."""


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    profile_id: str
    provider_kind: ProviderKind
    model_id: str | None = None
    api_key_env_var: str = ""
    vendor: str = ""
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    sandbox_safe: bool = True
    requires_network: bool = False


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    prompt_text: str
    provider_profile: ProviderProfile
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    openai_response_format: Mapping[str, Any] | None = None
    request_id: str = ""
    run_id: str = ""
    trace_root: str = ""
    node_id: str = ""
    prompt_artifact_ref: str = ""


@dataclass(frozen=True, slots=True)
class ProviderTokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ProviderReceipt:
    provider_profile_id: str
    model_id: str = ""
    token_usage: ProviderTokenUsage | None = None


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    success: bool
    text: str = ""
    receipt: ProviderReceipt | None = None
    error_message: str = ""
    invocation_meta: Mapping[str, Any] = field(default_factory=dict)


class ProviderGateway:
    """A narrow application-owned provider boundary.

    Stub mode is deterministic for regression work.  Any request for a live
    network call is rejected until an Apps RG adapter is supplied explicitly,
    preventing accidental execution through an unrelated runtime.
    """

    def __init__(self, *, provider_mode: ProviderMode = ProviderMode.LIVE_ALLOWED) -> None:
        self.provider_mode = provider_mode

    def invoke(self, request: ProviderRequest) -> ProviderResponse:
        profile = request.provider_profile
        if self.provider_mode == ProviderMode.DISABLED:
            raise ProviderModeBlockedError("Apps RG provider mode is disabled")
        if self.provider_mode == ProviderMode.STUB_ONLY and profile.provider_kind != ProviderKind.STUB:
            raise ProviderModeBlockedError(
                "Apps RG provider mode permits only the explicit stub profile"
            )
        if profile.provider_kind == ProviderKind.STUB:
            text = '{"stub_receipt": true, "request_id": "' + request.request_id + '"}'
            return ProviderResponse(
                success=True,
                text=text,
                receipt=ProviderReceipt(
                    provider_profile_id=profile.profile_id,
                    model_id=str(profile.model_id or ""),
                    token_usage=ProviderTokenUsage(),
                ),
                invocation_meta={"provider_mode": self.provider_mode.value, "stub": True},
            )
        raise ProviderModeBlockedError(
            "Apps RG has no configured local live-provider adapter for this request"
        )


__all__ = [
    "CACHE_TTL_1H",
    "CACHE_TTL_5M",
    "ProviderGateway",
    "ProviderKind",
    "ProviderMode",
    "ProviderModeBlockedError",
    "ProviderProfile",
    "ProviderReceipt",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderTokenUsage",
    "min_cacheable_chars",
]
