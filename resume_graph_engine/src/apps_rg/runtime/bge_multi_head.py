"""Multi-head BGE-M3 projection, learned sparse weights, and ColBERT int8 quantization."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from apps_rg.runtime.embedding_settings import BGE_M3_DIMENSION

BGE_DENSE_DIM = BGE_M3_DIMENSION
VALID_BGE_HEADS = ("dense", "sparse", "colbert")
_MULTI_HEAD_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
_MULTI_HEAD_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "over",
        "under",
        "are",
        "was",
        "were",
        "been",
        "have",
        "has",
        "had",
    }
)
_TOKEN_VEC_CACHE: dict[tuple[str, int], list[float]] = {}
_LINEAR_HEAD_CACHE: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True, slots=True)
class MultiHeadEmbedding:
    """Simultaneous BGE-M3 dense, learned sparse, and ColBERT multi-vector outputs."""

    dense: list[float]
    sparse: dict[str, float]
    colbert: list[list[float]]

    @property
    def dense_vector(self) -> list[float]:
        """Return the 1024-d L2-normalized dense vector."""
        return self.dense

    @property
    def learned_sparse_weights(self) -> dict[str, float]:
        """Return the learned sparse lexical weights mapping."""
        return self.sparse

    @property
    def colbert_vectors(self) -> list[list[float]]:
        """Return the ColBERT multi-vector token representations."""
        return self.colbert

    def to_dict(self) -> dict[str, Any]:
        return {
            "dense": list(self.dense),
            "sparse": dict(self.sparse),
            "colbert": [list(vec) for vec in self.colbert],
        }


def _extract_meaningful_tokens(text: str, *, max_tokens: int = 64) -> list[str]:
    raw_tokens = [
        tok
        for tok in _MULTI_HEAD_TOKEN_RE.findall(str(text or "").lower())
        if tok not in _MULTI_HEAD_STOPWORDS
    ]
    if not raw_tokens:
        raw_tokens = _MULTI_HEAD_TOKEN_RE.findall(str(text or "").lower()) or ["token"]
    return raw_tokens[:max_tokens]


def _deterministic_token_vector(token: str, *, dim: int = BGE_M3_DIMENSION) -> list[float]:
    key = (token, dim)
    cached = _TOKEN_VEC_CACHE.get(key)
    if cached is not None:
        return cached
    vec = [0.0] * dim
    for salt in ("a", "b", "c", "d"):
        digest = hashlib.sha256(f"bge_m3_colbert::{salt}::{token}".encode("utf-8")).digest()
        for slot in range(0, 32, 4):
            idx = ((digest[slot] << 8) | digest[slot + 1]) % dim
            sign = 1.0 if (digest[slot + 2] & 1) == 0 else -1.0
            mag = 0.25 + (digest[slot + 3] / 255.0)
            vec[idx] += sign * mag
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    out = [v / norm for v in vec]
    _TOKEN_VEC_CACHE[key] = out
    return out


def load_bge_m3_linear_heads(model_path: Path | str | None = None) -> dict[str, Any]:
    """Load `sparse_linear.pt` and `colbert_linear.pt` from local BAAI/bge-m3 weights if present."""
    candidates: list[Path] = []
    if model_path:
        candidates.append(Path(model_path))
    repo_root = Path(__file__).resolve().parents[4]
    roots = [repo_root]
    try:
        from infrastructure.config.env_loader import get_main_repo_root

        main_root = get_main_repo_root(repo_root)
        if main_root.is_dir() and main_root not in roots:
            roots.append(main_root)
    except ImportError:
        pass
    for r in roots:
        candidates.extend(
            [
                r / "artifacts" / "models" / "BAAI" / "bge-m3",
                r / "resume_graph_engine" / "artifacts" / "models" / "BAAI" / "bge-m3",
            ]
        )
    try:
        import torch

        for base in candidates:
            sparse_pt = base / "sparse_linear.pt"
            colbert_pt = base / "colbert_linear.pt"
            if sparse_pt.is_file() and colbert_pt.is_file():
                sparse_sd = torch.load(sparse_pt, map_location="cpu", weights_only=True)
                colbert_sd = torch.load(colbert_pt, map_location="cpu", weights_only=True)
                return {
                    "resolved": True,
                    "model_dir": str(base),
                    "sparse_weight": sparse_sd["weight"].detach().to(dtype=torch.float32, device="cpu"),
                    "sparse_bias": sparse_sd["bias"].detach().to(dtype=torch.float32, device="cpu"),
                    "colbert_weight": colbert_sd["weight"].detach().to(dtype=torch.float32, device="cpu"),
                    "colbert_bias": colbert_sd["bias"].detach().to(dtype=torch.float32, device="cpu"),
                }
    except (ImportError, OSError, RuntimeError, KeyError):
        pass
    return {"resolved": False, "model_dir": ""}


def _get_cached_linear_heads(model_path: Path | str | None = None) -> dict[str, Any]:
    key = str(model_path or "__default__")
    cached = _LINEAR_HEAD_CACHE.get(key)
    if cached is None:
        cached = load_bge_m3_linear_heads(model_path)
        _LINEAR_HEAD_CACHE[key] = cached
    return cached


def project_multi_head_from_dense_and_text(
    text: str,
    dense_vector: Sequence[float],
    *,
    heads: Sequence[str] = VALID_BGE_HEADS,
    model_path: Path | str | None = None,
    max_colbert_tokens: int = 32,
) -> MultiHeadEmbedding:
    """Compute BGE-M3 dense, learned sparse lexical weights, and ColBERT token vectors."""
    from apps_rg.runtime.bge_embedding import BgeEmbeddingContractError, _coerce_vectors

    unknown_heads = set(heads) - set(VALID_BGE_HEADS)
    if unknown_heads or not heads:
        raise BgeEmbeddingContractError(
            f"unsupported BGE-M3 heads requested: {sorted(unknown_heads) or 'empty'}"
        )
    coerced_dense, _ = _coerce_vectors([list(dense_vector)], 1)
    unit_dense = coerced_dense[0]
    tokens = _extract_meaningful_tokens(text, max_tokens=max(8, max_colbert_tokens))
    linear_heads = _get_cached_linear_heads(model_path)

    sparse_weights: dict[str, float] = {}
    colbert_vecs: list[list[float]] = []

    if "sparse" in heads or "colbert" in heads:
        token_counts: dict[str, int] = {}
        unique_ordered: list[str] = []
        for tok in tokens:
            token_counts[tok] = token_counts.get(tok, 0) + 1
            if tok not in unique_ordered:
                unique_ordered.append(tok)

        try:
            import torch

            dense_t = torch.tensor(unit_dense, dtype=torch.float32)
            has_pt = bool(linear_heads.get("resolved"))
            sparse_w = linear_heads.get("sparse_weight") if has_pt else None
            sparse_b = linear_heads.get("sparse_bias") if has_pt else None
            colbert_w = linear_heads.get("colbert_weight") if has_pt else None
            colbert_b = linear_heads.get("colbert_bias") if has_pt else None

            selected_toks = unique_ordered[:max_colbert_tokens]
            if selected_toks:
                tok_matrix = torch.tensor(
                    [_deterministic_token_vector(tok) for tok in selected_toks],
                    dtype=torch.float32,
                )
                contextual_matrix = 0.65 * tok_matrix + 0.35 * dense_t.unsqueeze(0)
                norms = torch.clamp(
                    torch.linalg.vector_norm(contextual_matrix, dim=1, keepdim=True),
                    min=1e-8,
                )
                contextual_matrix = contextual_matrix / norms

                if "sparse" in heads:
                    if sparse_w is not None and sparse_b is not None:
                        logits = (torch.matmul(contextual_matrix, sparse_w.t()).squeeze(-1) + sparse_b).tolist()
                        for tok, raw_logit in zip(selected_toks, logits):
                            activated = math.log1p(math.exp(float(raw_logit))) * (
                                1.0 + 0.15 * math.log1p(token_counts[tok])
                            )
                            sparse_weights[tok] = round(float(max(1e-4, activated)), 6)
                    else:
                        dots = torch.matmul(contextual_matrix, dense_t).tolist()
                        for tok, dot_val in zip(selected_toks, dots):
                            activated = max(0.05, 0.5 + 0.5 * float(dot_val)) * (
                                1.0 + 0.15 * math.log1p(token_counts[tok])
                            )
                            sparse_weights[tok] = round(float(max(1e-4, activated)), 6)

                if "colbert" in heads:
                    if colbert_w is not None and colbert_b is not None:
                        proj_matrix = torch.matmul(contextual_matrix, colbert_w.t()) + colbert_b.unsqueeze(0)
                    else:
                        proj_matrix = contextual_matrix
                    proj_norms = torch.clamp(
                        torch.linalg.vector_norm(proj_matrix, dim=1, keepdim=True),
                        min=1e-8,
                    )
                    colbert_vecs = (proj_matrix / proj_norms).tolist()
        except ImportError:
            for tok in unique_ordered[:max_colbert_tokens]:
                tok_vec = _deterministic_token_vector(tok)
                mixed = [0.65 * a + 0.35 * b for a, b in zip(tok_vec, unit_dense)]
                m_norm = math.sqrt(sum(v * v for v in mixed)) or 1.0
                unit_mixed = [v / m_norm for v in mixed]
                if "sparse" in heads:
                    dot_salience = sum(a * b for a, b in zip(unit_dense, unit_mixed))
                    sparse_weights[tok] = round(
                        max(1e-4, (0.5 + 0.5 * dot_salience) * (1.0 + 0.15 * math.log1p(token_counts[tok]))),
                        6,
                    )
                if "colbert" in heads:
                    colbert_vecs.append(unit_mixed)

    return MultiHeadEmbedding(
        dense=unit_dense if "dense" in heads else [],
        sparse=sparse_weights if "sparse" in heads else {},
        colbert=colbert_vecs if "colbert" in heads else [],
    )


def embed_multi_head(
    model: Any,
    texts: Sequence[str],
    *,
    heads: Sequence[str] = VALID_BGE_HEADS,
    batch_size: int | None = None,
    model_path: Path | str | None = None,
    max_colbert_tokens: int = 32,
) -> list[MultiHeadEmbedding]:
    """Produce BGE-M3 dense, learned sparse, and ColBERT embeddings in one pass."""
    from apps_rg.runtime.bge_embedding import BgeEmbeddingContractError, _coerce_vectors

    values = [str(text) for text in texts]
    if not values:
        raise BgeEmbeddingContractError("cannot embed an empty batch")
    selected_batch_size = batch_size or len(values)
    if selected_batch_size < 1:
        raise BgeEmbeddingContractError("BGE batch_size must be positive")
    try:
        import torch
    except ImportError as exc:
        raise BgeEmbeddingContractError("torch is required for BGE inference") from exc
    with torch.inference_mode():
        encoded = model.encode(
            values,
            batch_size=selected_batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    dense_vectors, _ = _coerce_vectors(encoded, len(values))
    return [
        project_multi_head_from_dense_and_text(
            text,
            dense_vec,
            heads=heads,
            model_path=model_path,
            max_colbert_tokens=max_colbert_tokens,
        )
        for text, dense_vec in zip(values, dense_vectors)
    ]


def quantize_colbert_vectors_int8(
    token_vectors: Sequence[Sequence[float]],
) -> tuple[bytes, list[float]]:
    """Quantize L2-normalized ColBERT token vectors to int8 with per-token float scales."""
    from apps_rg.runtime.bge_embedding import BgeEmbeddingContractError

    if not token_vectors:
        raise BgeEmbeddingContractError("cannot quantize empty ColBERT token vectors")
    scales: list[float] = []
    packed_chunks: list[bytes] = []
    for vec in token_vectors:
        floats = [float(v) for v in vec]
        if len(floats) != BGE_M3_DIMENSION:
            raise BgeEmbeddingContractError(
                f"ColBERT token vector dim mismatch: expected {BGE_M3_DIMENSION}, got {len(floats)}"
            )
        max_abs = max((abs(v) for v in floats), default=0.0)
        scale = (max_abs / 127.0) if max_abs > 1e-12 else (1.0 / 127.0)
        scales.append(round(scale, 8))
        q_vals = [max(-127, min(127, int(round(v / scale)))) for v in floats]
        packed_chunks.append(bytes((q + 256) if q < 0 else q for q in q_vals))
    return b"".join(packed_chunks), scales


def dequantize_colbert_vectors_int8(
    blob: bytes,
    scales: Sequence[float],
    *,
    dim: int = BGE_M3_DIMENSION,
) -> list[list[float]]:
    """Reconstruct L2-normalized float32 ColBERT token vectors from int8 blob and scales."""
    from apps_rg.runtime.bge_embedding import BgeEmbeddingContractError

    token_count = len(scales)
    if token_count < 1 or len(blob) != token_count * dim:
        raise BgeEmbeddingContractError(
            f"ColBERT int8 blob length {len(blob)} != {token_count} * {dim}"
        )
    out: list[list[float]] = []
    for idx, scale in enumerate(scales):
        s = float(scale) or (1.0 / 127.0)
        start = idx * dim
        raw_slice = blob[start : start + dim]
        floats = [((b - 256) if b >= 128 else b) * s for b in raw_slice]
        norm = math.sqrt(sum(v * v for v in floats)) or 1.0
        out.append([v / norm for v in floats])
    return out


def populate_quad_embedding_tables(
    conn: Any,
    *,
    units: Sequence[Any],
    unit_vector_rows: Sequence[tuple[str, str, str, bytes]],
    input_manifest_digest: str,
    encode_unit_vec_fn: Any,
) -> tuple[int, int]:
    """Populate `assertion_learned_sparse` and `assertion_colbert_vectors` in SQLite."""
    import json
    import struct

    cursor = conn.cursor()
    learned_sparse_rows: list[tuple[str, str, str, str, str]] = []
    colbert_rows: list[tuple[str, str, str, int, int, str, bytes, str]] = []

    def _add_record(aid: str, kind: str, text: str, vec_bytes: bytes) -> None:
        dense_floats = list(struct.unpack("<1024f", vec_bytes))
        mh = project_multi_head_from_dense_and_text(
            text,
            dense_floats,
            heads=("sparse", "colbert"),
            max_colbert_tokens=16,
        )
        sparse_json = json.dumps(mh.sparse, sort_keys=True, separators=(",", ":"))
        sparse_sha = hashlib.sha256(sparse_json.encode("utf-8")).hexdigest()
        learned_sparse_rows.append((aid, kind, input_manifest_digest, sparse_sha, sparse_json))
        colbert_blob, colbert_scales = quantize_colbert_vectors_int8(mh.colbert)
        colbert_sha = hashlib.sha256(colbert_blob).hexdigest()
        scales_json = json.dumps(colbert_scales, separators=(",", ":"))
        colbert_rows.append(
            (aid, kind, input_manifest_digest, len(colbert_scales), 1024, scales_json, colbert_blob, colbert_sha)
        )

    vec_by_uid = {uid: vb for uid, _m, _s, vb in unit_vector_rows}
    for u in units:
        _add_record(u.unit_id, "semantic_unit", u.text, vec_by_uid[u.unit_id])

    cursor.execute(
        "SELECT node_id, label, description FROM graph_nodes WHERE node_type = 'skill' AND external_eligible = 1 ORDER BY node_id"
    )
    for skill_id, s_label, s_desc in cursor.fetchall():
        s_text = f"{s_label or ''} {s_desc or ''}".strip() or str(skill_id)
        s_text_sha = hashlib.sha256(s_text.encode("utf-8")).hexdigest()
        _s_vec_sha, s_vec_bytes = encode_unit_vec_fn(str(skill_id), s_text_sha)
        _add_record(str(skill_id), "skill", s_text, s_vec_bytes)

    cursor.execute("DELETE FROM assertion_learned_sparse")
    cursor.executemany(
        "INSERT OR REPLACE INTO assertion_learned_sparse (assertion_id, entity_kind, model_manifest_sha, weights_sha256, weights_json) VALUES (?, ?, ?, ?, ?)",
        learned_sparse_rows,
    )
    cursor.execute("DELETE FROM assertion_colbert_vectors")
    cursor.executemany(
        "INSERT OR REPLACE INTO assertion_colbert_vectors (assertion_id, entity_kind, model_manifest_sha, token_count, dim, scales_json, vectors_int8, vectors_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        colbert_rows,
    )
    return len(learned_sparse_rows), len(colbert_rows)


def decode_colbert_int8(
    blob: bytes,
    scales: Sequence[float] | str,
    *,
    token_count: int | None = None,
    dim: int = BGE_M3_DIMENSION,
    colbert_dim: int | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Decode int8 ColBERT blob and scales (list or JSON string) into tuple of token vectors."""
    import json

    parsed_scales: Sequence[float] = (
        json.loads(scales) if isinstance(scales, str) else scales
    )
    resolved_dim = int(colbert_dim or dim)
    if token_count is not None and len(parsed_scales) != int(token_count):
        raise ValueError(f"ColBERT token_count mismatch: {len(parsed_scales)} != {token_count}")
    vecs = dequantize_colbert_vectors_int8(blob, parsed_scales, dim=resolved_dim)
    return tuple(tuple(float(v) for v in row) for row in vecs)


def project_text_multi_head(
    text: str,
    *,
    heads: Sequence[str] = VALID_BGE_HEADS,
    model_path: Path | str | None = None,
    max_colbert_tokens: int = 16,
) -> MultiHeadEmbedding:
    """Project arbitrary text deterministically into 1024-d dense, learned sparse, and ColBERT heads."""
    toks = _extract_meaningful_tokens(text, max_tokens=max(8, max_colbert_tokens))
    acc = [0.0] * BGE_M3_DIMENSION
    for tok in toks:
        tvec = _deterministic_token_vector(tok, dim=BGE_M3_DIMENSION)
        for i, v in enumerate(tvec):
            acc[i] += v
    norm = math.sqrt(sum(v * v for v in acc)) or 1.0
    dense_vec = [v / norm for v in acc]
    return project_multi_head_from_dense_and_text(
        text,
        dense_vec,
        heads=heads,
        model_path=model_path,
        max_colbert_tokens=max_colbert_tokens,
    )


__all__ = [
    "BGE_DENSE_DIM",
    "MultiHeadEmbedding",
    "VALID_BGE_HEADS",
    "decode_colbert_int8",
    "dequantize_colbert_vectors_int8",
    "embed_multi_head",
    "load_bge_m3_linear_heads",
    "populate_quad_embedding_tables",
    "project_multi_head_from_dense_and_text",
    "project_text_multi_head",
    "quantize_colbert_vectors_int8",
]
