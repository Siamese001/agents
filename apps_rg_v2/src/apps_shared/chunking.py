"""Token-aware chunker with overlap."""

from __future__ import annotations


def _encode_tiktoken(text: str) -> list[int]:
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    return enc.encode(text)


def _decode_tiktoken(tokens: list[int]) -> str:
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    return enc.decode(tokens)


def _tiktoken_available() -> bool:
    try:
        import tiktoken  # noqa: F401

        return True
    except ImportError:
        return False


def chunk_text(
    text: str,
    chunk_tokens: int = 512,
    overlap_tokens: int = 50,
) -> list[str]:
    """Split text into chunks of at most chunk_tokens with overlap_tokens overlap."""
    if not text.strip():
        return []

    if _tiktoken_available():
        tokens = _encode_tiktoken(text)
        if len(tokens) <= chunk_tokens:
            return [text]
        chunks: list[str] = []
        step = max(1, chunk_tokens - overlap_tokens)
        for i in range(0, len(tokens), step):
            slice_tokens = tokens[i : i + chunk_tokens]
            chunks.append(_decode_tiktoken(slice_tokens))
            if i + chunk_tokens >= len(tokens):
                break
        return chunks

    # Whitespace fallback
    words = text.split()
    if len(words) <= chunk_tokens:
        return [text]
    step = max(1, chunk_tokens - overlap_tokens)
    chunks = []
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + chunk_tokens])
        chunks.append(chunk)
        if i + chunk_tokens >= len(words):
            break
    return chunks


__all__ = ["chunk_text"]
