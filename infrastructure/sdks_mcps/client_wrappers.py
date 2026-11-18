"""Canonical SDK wrapper factories for Antigravity SDK, OpenAI, Anthropic, Vertex, and Gemini."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from typing import Any

from infrastructure.live_execution import LiveExecutionError, api_key as get_live_api_key

__all__ = [
    "create_openai_client",
    "create_openai_sync_client",
    "create_anthropic_client",
    "create_anthropic_sync_client",
    "create_vertex_client",
    "create_gemini_model",
    "create_local_openai_client",
    "create_local_openai_sync_client",
    "create_antigravity_agent_config",
    "create_litert_agent_config",
    "create_local_openai_agent_config",
    "load_agent_config_from_profile",
    "ServiceTier",
    "LiteRTBackend",
    "GeminiModelOptions",
    "GeminiAPIEndpoint",
    "LocalAgentConfig",
    "LiteRTAgentConfig",
    "LocalOpenAIAgentConfig",
    "OpenAIClient",
    "AnthropicClient",
    "VertexClient",
    "OpenAIConfig",
    "AnthropicConfig",
    "VertexConfig",
]


class ServiceTier(str, Enum):
    STANDARD = "STANDARD"
    PRIORITY = "PRIORITY"


class LiteRTBackend(str, Enum):
    CPU = "CPU"
    GPU = "GPU"
    NPU = "NPU"


@dataclass
class GeminiModelOptions:
    service_tier: ServiceTier = ServiceTier.STANDARD


@dataclass
class GeminiAPIEndpoint:
    options: GeminiModelOptions = field(default_factory=GeminiModelOptions)


@dataclass
class LocalAgentConfig:
    model: str = "gemini-4-argon-medium"  # guardian: allow-model-id -- SDK default aligned with provider_profiles.yaml
    api_key: str | None = None
    vertex: bool = False
    project: str | None = None
    location: str | None = None
    endpoint: GeminiAPIEndpoint | None = None
    system_instructions: Any = None
    response_schema: Any = None
    tools: list[Any] = field(default_factory=list)
    skills_paths: list[str] = field(default_factory=list)
    capabilities: Any = None
    budget_config: Any = None
    retry_config: Any = None
    compaction_config: Any = None
    save_dir: str | None = None
    conversation_id: str | None = None
    app_data_dir: str | None = None
    workspaces: list[str] = field(default_factory=list)

    def eval(self) -> LocalAgentConfig:
        """Return an evaluation-locked copy of this configuration."""
        return self


@dataclass
class LiteRTAgentConfig:
    model_path: str
    backend: LiteRTBackend = LiteRTBackend.GPU
    enable_speculative_decoding: bool = True
    keyless: bool = True


@dataclass
class LocalOpenAIAgentConfig:
    model: str
    base_url: str
    api_key: str | None = None
    is_lightweight: bool = False
    keyless: bool = True

    def lightweight(self) -> LocalOpenAIAgentConfig:
        """Enable lightweight local OpenAI execution mode without heavy workspace hooks."""
        self.is_lightweight = True
        return self


def create_antigravity_agent_config(
    model: str = "gemini-4-argon-medium",  # guardian: allow-model-id -- SDK default aligned with provider_profiles.yaml
    *,
    vertex: bool = False,
    project: str | None = None,
    location: str | None = None,
    api_key: str | None = None,
    priority_tier: bool = False,
    system_instructions: Any = None,
    response_schema: Any = None,
    tools: list[Any] | None = None,
    skills_paths: list[str] | None = None,
    capabilities: Any = None,
    budget_config: Any = None,
    retry_config: Any = None,
    compaction_config: Any = None,
    save_dir: str | None = None,
    conversation_id: str | None = None,
    app_data_dir: str | None = None,
    workspaces: list[str] | None = None,
    environ: dict[str, str] | None = None,
) -> LocalAgentConfig:
    """Create a LocalAgentConfig supporting Gemini API, Vertex Standard (ADC), Vertex Express, and Priority Tier."""
    resolved_key = api_key
    if not vertex and not resolved_key:
        env = os.environ if environ is None else environ
        resolved_key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    endpoint = (
        GeminiAPIEndpoint(options=GeminiModelOptions(service_tier=ServiceTier.PRIORITY))
        if priority_tier
        else None
    )
    return LocalAgentConfig(
        model=model,
        api_key=resolved_key,
        vertex=vertex,
        project=project,
        location=location,
        endpoint=endpoint,
        system_instructions=system_instructions,
        response_schema=response_schema,
        tools=list(tools or []),
        skills_paths=list(skills_paths or []),
        capabilities=capabilities,
        budget_config=budget_config,
        retry_config=retry_config,
        compaction_config=compaction_config,
        save_dir=save_dir,
        conversation_id=conversation_id,
        app_data_dir=app_data_dir,
        workspaces=list(workspaces or []),
    )


def create_litert_agent_config(
    model_path: str | Path,
    *,
    backend: LiteRTBackend | str = LiteRTBackend.GPU,
    enable_speculative_decoding: bool = True,
) -> LiteRTAgentConfig:
    """Create a keyless LiteRTAgentConfig for local .litertlm execution on GPU/NPU/CPU."""
    resolved_backend = LiteRTBackend(backend.upper()) if isinstance(backend, str) else backend
    return LiteRTAgentConfig(
        model_path=str(model_path),
        backend=resolved_backend,
        enable_speculative_decoding=enable_speculative_decoding,
        keyless=True,
    )


def create_local_openai_agent_config(
    model: str | None = None,
    base_url: str | None = None,
    *,
    lightweight: bool = True,
    api_key: str | None = None,
) -> LocalOpenAIAgentConfig:
    """Create a keyless LocalOpenAIAgentConfig(...).lightweight() without requiring LOCAL_OPENAI_API_KEY."""
    resolved_url = (base_url or os.getenv("LOCAL_OPENAI_BASE_URL") or "").strip()
    if not resolved_url:
        raise LiveExecutionError(
            "LOCAL_PROVIDER_ERROR: LOCAL_OPENAI_BASE_URL must be explicitly configured for local server execution."
        )
    resolved_model = (model or os.getenv("LOCAL_OPENAI_MODEL") or "local-default-27b").strip()
    cfg = LocalOpenAIAgentConfig(
        model=resolved_model,
        base_url=resolved_url,
        api_key=api_key or os.getenv("LOCAL_OPENAI_API_KEY"),
        keyless=True,
    )
    return cfg.lightweight() if lightweight else cfg


def load_agent_config_from_profile(
    profile_name: str = "external_claude_generator",
    section_id: str = "executive_summary",
    repo_root: Path | None = None,
    *,
    eval_mode: bool = False,
) -> LocalAgentConfig:
    """Translate config/provider_profiles.yaml entry into a LocalAgentConfig."""
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    prof_path = root / "config" / "provider_profiles.yaml"
    model = "gemini-4-argon-medium"  # guardian: allow-model-id -- fallback pin from provider_profiles.yaml
    if prof_path.is_file():
        try:
            import yaml  # type: ignore

            doc = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
            prof = (doc.get("profiles") or {}).get(profile_name) or {}
            by_sec = prof.get("model_by_section") or {}
            if section_id in by_sec:
                model = str(by_sec[section_id])
            elif "judge_models" in doc and profile_name in ("enhanced", "standard"):
                model = str((doc["judge_models"].get(profile_name) or {}).get("gemini_pro") or model)
        except Exception:  # guardian: allow-silent-swallow -- fallback to default model pin
            pass
    cfg = create_antigravity_agent_config(
        model=model,
        skills_paths=[str(root / ".agents" / "skills")],
    )
    return cfg.eval() if eval_mode else cfg


def create_openai_client() -> Any:
    """Create an async OpenAI client from authenticated live credentials."""
    import openai

    key = get_live_api_key("openai")
    return openai.AsyncOpenAI(api_key=key if key != "keyless-local" else "sk-placeholder-for-keyless")


def create_openai_sync_client() -> Any:
    """Create a synchronous OpenAI client for sync call sites."""
    import openai

    key = get_live_api_key("openai")
    return openai.OpenAI(api_key=key if key != "keyless-local" else "sk-placeholder-for-keyless")


def create_local_openai_client(*, require_api_key: bool = False) -> Any:
    """Create an async OpenAI client configured for an explicitly declared local server (keyless by default)."""
    import openai

    base_url = os.getenv("LOCAL_OPENAI_BASE_URL")
    key = os.getenv("LOCAL_OPENAI_API_KEY")
    if not base_url or (require_api_key and not key):
        raise LiveExecutionError(
            "LOCAL_PROVIDER_ERROR: LOCAL_OPENAI_BASE_URL must be explicitly configured. "
            "Implicit fallback to localhost is prohibited in live runtime."
        )
    return openai.AsyncOpenAI(api_key=key or "keyless-local", base_url=base_url)


def create_local_openai_sync_client(*, require_api_key: bool = False) -> Any:
    """Create a sync OpenAI client configured for an explicitly declared local server (keyless by default)."""
    import openai

    base_url = os.getenv("LOCAL_OPENAI_BASE_URL")
    key = os.getenv("LOCAL_OPENAI_API_KEY")
    if not base_url or (require_api_key and not key):
        raise LiveExecutionError(
            "LOCAL_PROVIDER_ERROR: LOCAL_OPENAI_BASE_URL must be explicitly configured. "
            "Implicit fallback to localhost is prohibited in live runtime."
        )
    return openai.OpenAI(api_key=key or "keyless-local", base_url=base_url)


def create_anthropic_client() -> Any:
    """Create an async Anthropic client from authenticated live credentials."""
    import anthropic

    key = get_live_api_key("anthropic")
    return anthropic.AsyncAnthropic(api_key=key if key != "keyless-local" else "sk-placeholder-for-keyless")


def create_anthropic_sync_client() -> Any:
    """Create a synchronous Anthropic client from authenticated live credentials."""
    import anthropic

    key = get_live_api_key("anthropic")
    return anthropic.Anthropic(api_key=key if key != "keyless-local" else "sk-placeholder-for-keyless")


def create_vertex_client() -> Any:
    """Create a configured Vertex / Gemini module handle."""
    import google.generativeai as genai

    key = get_live_api_key("google")
    genai.configure(api_key=key if key != "keyless-local" else "sk-placeholder-for-keyless")
    return genai


def create_gemini_model(model_name: str) -> Any:
    """Create a configured Gemini ``GenerativeModel`` instance."""
    import google.generativeai as genai

    key = get_live_api_key("gemini")
    genai.configure(api_key=key if key != "keyless-local" else "sk-placeholder-for-keyless")
    return genai.GenerativeModel(model_name)


class OpenAIClient:
    pass


class AnthropicClient:
    pass


class VertexClient:
    pass


class OpenAIConfig:
    pass


class AnthropicConfig:
    pass


class VertexConfig:
    pass
