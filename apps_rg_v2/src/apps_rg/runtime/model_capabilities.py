"""Exact model capability metadata for apps_rg runtime validation.

The shared catalog describes what an exact model ID can do.  It never selects a
model for an app role; apps_rg routing remains owned by provider_profiles.yaml.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MODEL_CAPABILITY_CATALOG_PATH = Path(__file__).resolve().parents[3] / "config" / "model_catalog.json"


class ModelCapabilityError(RuntimeError):
    """Raised when exact model capability metadata is missing or inconsistent."""


@dataclass(frozen=True)
class ModelCapabilities:
    model_id: str
    provider: str
    capability_class: str
    endpoints: tuple[str, ...]
    reasoning_efforts: tuple[str, ...]
    temperature_parameter: str
    structured_output: bool
    proof_eligible: bool
    thinking_mode: str | None
    max_output_tokens_parameters: tuple[tuple[str, str], ...]

    def supports_endpoint(self, endpoint: str) -> bool:
        return str(endpoint or "").strip() in self.endpoints

    def supports_reasoning_effort(self, effort: str | None) -> bool:
        value = str(effort or "").strip().lower()
        return not value or value in self.reasoning_efforts

    def max_output_tokens_parameter_for(self, endpoint: str) -> str | None:
        requested = str(endpoint or "").strip()
        return dict(self.max_output_tokens_parameters).get(requested)


def _catalog_models() -> dict[str, Any]:
    try:
        payload = json.loads(MODEL_CAPABILITY_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelCapabilityError(
            f"Cannot load model capability catalog: {MODEL_CAPABILITY_CATALOG_PATH}"
        ) from exc
    if payload.get("catalog_role") != "capability_metadata_only" or payload.get(
        "routing_allowed"
    ) is not False:
        raise ModelCapabilityError(
            "Model capability catalog must be capability_metadata_only with routing_allowed=false"
        )
    models = payload.get("models")
    if not isinstance(models, dict):
        raise ModelCapabilityError("Model capability catalog is missing models")
    return models


def model_capabilities(model_id: str) -> ModelCapabilities:
    """Resolve one exact model ID; aliases and prefix matches are forbidden."""
    mid = str(model_id or "").strip()
    raw = _catalog_models().get(mid)
    if not isinstance(raw, dict):
        raise ModelCapabilityError(f"MODEL_CAPABILITY_NOT_REGISTERED: {mid or '<empty>'}")

    required = {
        "provider",
        "capability_class",
        "endpoints",
        "reasoning_efforts",
        "temperature_parameter",
        "structured_output",
        "proof_eligible",
        "max_output_tokens_parameters",
    }
    missing = sorted(required.difference(raw))
    if missing:
        raise ModelCapabilityError(
            f"MODEL_CAPABILITY_METADATA_INCOMPLETE: {mid}: {','.join(missing)}"
        )
    endpoints = raw.get("endpoints")
    efforts = raw.get("reasoning_efforts")
    output_token_parameters = raw.get("max_output_tokens_parameters")
    if not isinstance(endpoints, list) or not all(isinstance(value, str) for value in endpoints):
        raise ModelCapabilityError(f"MODEL_CAPABILITY_ENDPOINTS_INVALID: {mid}")
    if not isinstance(efforts, list) or not all(isinstance(value, str) for value in efforts):
        raise ModelCapabilityError(f"MODEL_CAPABILITY_EFFORTS_INVALID: {mid}")
    if not isinstance(output_token_parameters, dict) or not all(
        isinstance(endpoint, str) and isinstance(parameter, str) and endpoint in endpoints
        for endpoint, parameter in output_token_parameters.items()
    ):
        raise ModelCapabilityError(f"MODEL_CAPABILITY_OUTPUT_TOKEN_PARAMETERS_INVALID: {mid}")
    temperature_parameter = str(raw.get("temperature_parameter") or "")
    if temperature_parameter not in {"supported", "omit", "not_applicable"}:
        raise ModelCapabilityError(f"MODEL_CAPABILITY_TEMPERATURE_INVALID: {mid}")

    return ModelCapabilities(
        model_id=mid,
        provider=str(raw["provider"]),
        capability_class=str(raw["capability_class"]),
        endpoints=tuple(endpoints),
        reasoning_efforts=tuple(str(value).lower() for value in efforts),
        temperature_parameter=temperature_parameter,
        structured_output=bool(raw["structured_output"]),
        proof_eligible=bool(raw["proof_eligible"]),
        thinking_mode=(str(raw.get("thinking_mode")) if raw.get("thinking_mode") else None),
        max_output_tokens_parameters=tuple(
            (str(endpoint), str(parameter))
            for endpoint, parameter in output_token_parameters.items()
        ),
    )


def try_model_capabilities(model_id: str) -> ModelCapabilities | None:
    try:
        return model_capabilities(model_id)
    except ModelCapabilityError:
        return None


def assert_model_request_capabilities(
    model_id: str,
    *,
    provider: str,
    endpoint: str,
    reasoning_effort: str | None = None,
    structured_output_required: bool = False,
    proof_required: bool = False,
) -> ModelCapabilities:
    capabilities = model_capabilities(model_id)
    if capabilities.provider != provider:
        raise ModelCapabilityError(
            f"MODEL_PROVIDER_CAPABILITY_MISMATCH: {model_id}: "
            f"expected={provider} actual={capabilities.provider}"
        )
    if not capabilities.supports_endpoint(endpoint):
        raise ModelCapabilityError(
            f"MODEL_ENDPOINT_CAPABILITY_MISMATCH: {model_id}: {endpoint}"
        )
    if not capabilities.supports_reasoning_effort(reasoning_effort):
        raise ModelCapabilityError(
            f"MODEL_EFFORT_CAPABILITY_MISMATCH: {model_id}: {reasoning_effort}"
        )
    if structured_output_required and not capabilities.structured_output:
        raise ModelCapabilityError(f"MODEL_STRUCTURED_OUTPUT_UNSUPPORTED: {model_id}")
    if proof_required and not capabilities.proof_eligible:
        raise ModelCapabilityError(f"MODEL_PROOF_INELIGIBLE: {model_id}")
    return capabilities


__all__ = [
    "MODEL_CAPABILITY_CATALOG_PATH",
    "ModelCapabilities",
    "ModelCapabilityError",
    "assert_model_request_capabilities",
    "model_capabilities",
    "try_model_capabilities",
]
