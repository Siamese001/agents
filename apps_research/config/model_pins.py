"""App-owned model pin resolvers for apps_research.

The provider and judge profiles are the routing source of truth. Downstream
consumers must use emitted observations from handoff receipts rather than
importing these requested pins.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_DOMAIN_CONTRACT_ROOT = Path(__file__).resolve().parent / "domain_contract"
COMPANY_BRIEF_PROVIDER_PROFILE_PATH = (
    _DOMAIN_CONTRACT_ROOT / "provider_profile.company_brief.v1.yaml"
)
COMPANY_BRIEF_JUDGE_PROFILE_PATH = (
    _DOMAIN_CONTRACT_ROOT / "judge_profile.company_brief.v1.yaml"
)


class AppsResearchModelPinError(RuntimeError):
    """Raised when an app-owned model-pin profile is unreadable or invalid."""


@dataclass(frozen=True)
class AppsResearchModelPin:
    role: str
    provider_key: str
    provider: str
    model: str
    reasoning_effort: str
    owner: str
    review_after: str


def _load_profile(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, TypeError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise AppsResearchModelPinError(
            f"Cannot load apps_research model-pin profile: {path}"
        ) from exc
    if not isinstance(data, dict):
        raise AppsResearchModelPinError(
            f"apps_research model-pin profile must be a mapping: {path}"
        )
    return data


def _pin_from_mapping(*, role: str, row: Any, path: Path) -> AppsResearchModelPin:
    if not isinstance(row, dict):
        raise AppsResearchModelPinError(f"Missing model pin {role!r} in {path}")
    values = {
        "provider_key": str(row.get("provider_key") or "").strip(),
        "provider": str(row.get("provider") or "").strip(),
        "model": str(row.get("model") or "").strip(),
        "owner": str(row.get("owner") or "").strip(),
        "review_after": str(row.get("review_after") or "").strip(),
    }
    missing = sorted(key for key, value in values.items() if not value)
    if missing:
        raise AppsResearchModelPinError(
            f"Model pin {role!r} is missing {missing!r} in {path}"
        )
    return AppsResearchModelPin(
        role=role,
        reasoning_effort=str(row.get("reasoning_effort") or "").strip().lower(),
        **values,
    )


def company_brief_generation_pin() -> AppsResearchModelPin:
    """Resolve the sole executable company-brief synthesis lane."""
    data = _load_profile(COMPANY_BRIEF_PROVIDER_PROFILE_PATH)
    lanes = data.get("approved_model_lanes")
    if not isinstance(lanes, dict) or set(lanes) != {"primary"}:
        raise AppsResearchModelPinError(
            "apps_research company-brief profile must define exactly one primary lane"
        )
    lane_selection = data.get("lane_selection")
    if not isinstance(lane_selection, dict) or lane_selection.get("strategy") != (
        "single_lane_fail_closed"
    ):
        raise AppsResearchModelPinError(
            "apps_research company-brief lane selection must be single_lane_fail_closed"
        )
    primary = lanes["primary"]
    pin = _pin_from_mapping(
        role="company_brief_generation",
        row=primary,
        path=COMPANY_BRIEF_PROVIDER_PROFILE_PATH,
    )
    if (pin.provider_key, pin.provider) != ("openai_chatgpt", "external_openai"):
        raise AppsResearchModelPinError(
            "apps_research company-brief generation is restricted to external_openai"
        )
    if pin.reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise AppsResearchModelPinError(
            "apps_research company-brief generation must pin an explicit reasoning_effort"
        )
    return pin


def apps_rg_handoff_judge_pin() -> AppsResearchModelPin:
    """Resolve the apps_rg handoff judge from the app-owned judge profile."""
    data = _load_profile(COMPANY_BRIEF_JUDGE_PROFILE_PATH)
    pin = _pin_from_mapping(
        role="apps_rg_handoff_judge",
        row=data.get("apps_rg_handoff_judge"),
        path=COMPANY_BRIEF_JUDGE_PROFILE_PATH,
    )
    if (pin.provider_key, pin.provider) != ("gemini_pro", "google_gemini"):
        raise AppsResearchModelPinError(
            "apps_research handoff judge is restricted to google_gemini"
        )
    if pin.reasoning_effort != "high":
        raise AppsResearchModelPinError(
            "apps_research apps_rg handoff judge must pin reasoning_effort=high"
        )
    return pin


def active_model_manifest() -> tuple[AppsResearchModelPin, ...]:
    """Return requested apps_research pins; receipts remain observation authority."""
    return (company_brief_generation_pin(), apps_rg_handoff_judge_pin())


__all__ = [
    "COMPANY_BRIEF_JUDGE_PROFILE_PATH",
    "COMPANY_BRIEF_PROVIDER_PROFILE_PATH",
    "AppsResearchModelPin",
    "AppsResearchModelPinError",
    "active_model_manifest",
    "apps_rg_handoff_judge_pin",
    "company_brief_generation_pin",
]
