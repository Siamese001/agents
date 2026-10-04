"""Token counting and estimation service for model requests and budget governance.

Picks the tokenizer per `tokenizer_family` from the single model registry SSOT.
- OpenAI families: exact token count from lazily-imported `tiktoken` if installed,
  otherwise calibrated heuristic.
- Anthropic/Gemini: calibrated offline heuristic with provider family ratios.
- BGE: HF tokenizer if available, otherwise calibrated BGE heuristic.
- Tokenizer instances are cached.
"""

from __future__ import annotations

import functools
import re
from typing import Any, Optional

# Calibrated character-to-token ratios by tokenizer family
_FAMILY_CHARS_PER_TOKEN: dict[str, float] = {
    "o200k_base": 3.8,
    "cl100k_base": 3.8,
    "p50k_base": 3.8,
    "claude_bpe": 3.5,
    "gemini_tokenizer": 3.7,
    "bert_bge": 3.2,
}
_DEFAULT_CHARS_PER_TOKEN: float = 3.6


class TokenCounterService:
    """Singleton service for token estimation and counting."""

    _instance: Optional[TokenCounterService] = None
    _tokenizers: dict[str, Any] = {}

    def __init__(self) -> None:
        self._tokenizers = {}

    @classmethod
    def get_instance(cls) -> TokenCounterService:
        if cls._instance is None:
            cls._instance = TokenCounterService()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def resolve_family_and_context(
        self,
        *,
        model_id: str | None = None,
        role: str | None = None,
        tokenizer_family: str | None = None,
    ) -> tuple[str, int]:
        """Resolve tokenizer family and context window from model registry SSOT."""
        if tokenizer_family:
            return tokenizer_family, 131072

        try:
            from apps_rg.runtime.model_registry import get_model_registry

            registry = get_model_registry()
            resolved = None
            if role:
                resolved = registry.resolve(role)
            elif model_id:
                # Search models by id or snapshot_id
                for r in registry.roles.values():
                    if r.model_id == model_id or r.snapshot_id == model_id:
                        resolved = r
                        break

            if resolved:
                return resolved.tokenizer_family or "o200k_base", resolved.context_window or 131072
        except Exception:
            pass

        return "o200k_base", 131072

    def count_tokens(
        self,
        text: str,
        *,
        model_id: str | None = None,
        role: str | None = None,
        tokenizer_family: str | None = None,
    ) -> int:
        """Count tokens with highest precision available for the tokenizer family."""
        if not text:
            return 0

        family, _ = self.resolve_family_and_context(
            model_id=model_id, role=role, tokenizer_family=tokenizer_family
        )

        # 1. Exact tokenizer for OpenAI families if tiktoken is available
        if family in ("o200k_base", "cl100k_base", "p50k_base"):
            enc = self._get_tiktoken_encoding(family)
            if enc is not None:
                try:
                    return len(enc.encode(text))
                except Exception:
                    pass

        # 2. Exact tokenizer for BGE / HF if available
        if family == "bert_bge":
            tok = self._get_hf_tokenizer("BAAI/bge-m3")
            if tok is not None:
                try:
                    return len(tok.encode(text, add_special_tokens=False))
                except Exception:
                    pass

        # 3. Calibrated offline heuristic
        return self.estimate_tokens(
            text, model_id=model_id, role=role, tokenizer_family=family
        )

    def estimate_tokens(
        self,
        text: str,
        *,
        model_id: str | None = None,
        role: str | None = None,
        tokenizer_family: str | None = None,
        chars_per_token_ratio: float | None = None,
        safety_multiplier: float = 1.0,
    ) -> int:
        """Conservative token estimate using calibrated ratio and optional safety multiplier."""
        if not text:
            return 0

        if chars_per_token_ratio is not None and chars_per_token_ratio > 0:
            ratio = chars_per_token_ratio
        else:
            family, _ = self.resolve_family_and_context(
                model_id=model_id, role=role, tokenizer_family=tokenizer_family
            )
            ratio = _FAMILY_CHARS_PER_TOKEN.get(family, _DEFAULT_CHARS_PER_TOKEN)

        if ratio.is_integer():
            int_ratio = int(ratio)
            raw_tokens = max(1, (len(text) + int_ratio - 1) // int_ratio)
        else:
            raw_tokens = max(1, int(len(text) / ratio + 0.999))
        return max(1, int(raw_tokens * safety_multiplier + 0.999999))

    def context_window(
        self,
        *,
        model_id: str | None = None,
        role: str | None = None,
        section_context_window: int | None = None,
    ) -> int:
        """Return the effective context window: min(model, section)."""
        _, model_cw = self.resolve_family_and_context(model_id=model_id, role=role)
        if section_context_window is not None and section_context_window > 0:
            return min(model_cw, section_context_window)
        return model_cw

    def _get_tiktoken_encoding(self, family: str) -> Any:
        if family in self._tokenizers:
            return self._tokenizers[family]
        try:
            import tiktoken  # type: ignore

            enc = tiktoken.get_encoding(family)
            self._tokenizers[family] = enc
            return enc
        except Exception:
            self._tokenizers[family] = None
            return None

    def _get_hf_tokenizer(self, model_name: str) -> Any:
        if model_name in self._tokenizers:
            return self._tokenizers[model_name]
        try:
            from transformers import AutoTokenizer  # type: ignore

            tok = AutoTokenizer.from_pretrained(model_name)
            self._tokenizers[model_name] = tok
            return tok
        except Exception:
            self._tokenizers[model_name] = None
            return None


# Module-level convenience functions
def estimate_tokens(
    text: str,
    *,
    model_id: str | None = None,
    role: str | None = None,
    tokenizer_family: str | None = None,
    chars_per_token_ratio: float | None = None,
    safety_multiplier: float = 1.0,
) -> int:
    return TokenCounterService.get_instance().estimate_tokens(
        text,
        model_id=model_id,
        role=role,
        tokenizer_family=tokenizer_family,
        chars_per_token_ratio=chars_per_token_ratio,
        safety_multiplier=safety_multiplier,
    )


def count_tokens(
    text: str,
    *,
    model_id: str | None = None,
    role: str | None = None,
    tokenizer_family: str | None = None,
) -> int:
    return TokenCounterService.get_instance().count_tokens(
        text,
        model_id=model_id,
        role=role,
        tokenizer_family=tokenizer_family,
    )


def context_window_for(
    *,
    model_id: str | None = None,
    role: str | None = None,
    section_context_window: int | None = None,
) -> int:
    return TokenCounterService.get_instance().context_window(
        model_id=model_id,
        role=role,
        section_context_window=section_context_window,
    )
