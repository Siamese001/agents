"""Process-scoped, local-only BGE-M3 runtime owned by standalone Apps RG."""

from __future__ import annotations

import atexit
from collections import deque
import hashlib
import json
import math
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.runtime.embedding_settings import BGE_M3_DIMENSION

RUNTIME_SCHEMA = "apps_rg.bge_resident_runtime_w2.v1"
DEFAULT_BACKEND = "sentence_transformers"
DEFAULT_DTYPE = "float32"
WARMUP_TEXT = "apps_rg resident BGE-M3 runtime warmup"
MAX_PRE_NORMALIZATION_ERROR = 5e-3
BATCH_PROFILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "domain_contract"
    / "bge_batch_profile.v1.json"
)
PRECISION_PROFILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "domain_contract"
    / "bge_precision_profile.v1.json"
)


class BgeEmbeddingContractError(RuntimeError):
    """The local runtime could not preserve the pinned BGE-M3 contract."""


@dataclass(frozen=True, order=True)
class BgeRuntimeKey:
    model_path: str
    device: str
    dtype: str
    backend: str


def _canonical_device(value: str) -> str:
    device = value.strip().lower()
    if device == "cuda":
        return "cuda:0"
    return device or "cuda:0"


def resolve_bge_runtime_key(
    *,
    model_path: Path | str,
    device: str | None = None,
    dtype: str | None = None,
    backend: str | None = None,
) -> BgeRuntimeKey:
    root = Path(model_path).resolve()
    if not root.is_dir():
        raise BgeEmbeddingContractError(f"local BGE-M3 directory missing: {root}")
    selected_device = device or (
        os.environ.get("APPS_RG_HYDRATION_DEVICE", "").strip()
        or os.environ.get("EMBEDDING_DEVICE", "").strip()
        or os.environ.get("VECTOR_DB_DEVICE", "").strip()
        or "cuda:0"
    )
    if dtype is None:
        selected_dtype = resolve_bge_precision_dtype()
        legacy_dtype = os.environ.get("APPS_RG_BGE_DTYPE", "").strip().lower()
        if legacy_dtype and legacy_dtype != selected_dtype:
            raise BgeEmbeddingContractError(
                "APPS_RG_BGE_DTYPE conflicts with the governed precision profile; "
                "use APPS_RG_BGE_PRECISION_PROFILE for rollback"
            )
    else:
        selected_dtype = dtype.lower()
    selected_backend = (
        backend or os.environ.get("APPS_RG_BGE_BACKEND") or DEFAULT_BACKEND
    ).lower()
    if selected_dtype not in {"float32", "float16", "bfloat16"}:
        raise BgeEmbeddingContractError(f"unsupported BGE dtype: {selected_dtype}")
    if selected_backend != DEFAULT_BACKEND:
        raise BgeEmbeddingContractError(f"unsupported BGE backend: {selected_backend}")
    return BgeRuntimeKey(
        model_path=str(root),
        device=_canonical_device(selected_device),
        dtype=selected_dtype,
        backend=selected_backend,
    )


def load_bge_precision_profile(path: Path | str | None = None) -> dict[str, Any]:
    profile_path = Path(path).resolve() if path is not None else PRECISION_PROFILE_PATH
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BgeEmbeddingContractError(
            f"cannot load BGE precision profile: {profile_path}"
        ) from exc
    if not isinstance(profile, dict) or profile.get("schema_version") != (
        "apps_rg.bge_precision_profile.v1"
    ):
        raise BgeEmbeddingContractError("BGE precision profile schema mismatch")
    if profile.get("fallback_allowed") is not False or profile.get(
        "network_allowed"
    ) is not False:
        raise BgeEmbeddingContractError("BGE precision profile controls are invalid")
    profiles = profile.get("profiles")
    selected = str(profile.get("selected_profile_id") or "")
    rollback = str(profile.get("rollback_profile_id") or "")
    if not isinstance(profiles, dict) or selected not in profiles or rollback not in profiles:
        raise BgeEmbeddingContractError("BGE precision profile selection is invalid")
    if (profiles.get(rollback) or {}).get("dtype") != DEFAULT_DTYPE:
        raise BgeEmbeddingContractError("BGE precision rollback must remain float32")
    for profile_id, row in profiles.items():
        if not isinstance(row, dict) or row.get("dtype") not in {
            "float32",
            "float16",
            "bfloat16",
        }:
            raise BgeEmbeddingContractError(
                f"BGE precision dtype is invalid: {profile_id}"
            )
    return profile


def resolve_bge_precision_profile_id(
    *, profile_path: Path | str | None = None
) -> str:
    profile = load_bge_precision_profile(profile_path)
    requested = os.environ.get("APPS_RG_BGE_PRECISION_PROFILE", "").strip()
    selected = requested or str(profile["selected_profile_id"])
    if selected not in profile["profiles"]:
        raise BgeEmbeddingContractError(
            f"BGE precision profile is unconfigured: {selected}"
        )
    return selected


def resolve_bge_precision_dtype(
    *, profile_path: Path | str | None = None
) -> str:
    profile = load_bge_precision_profile(profile_path)
    profile_id = resolve_bge_precision_profile_id(profile_path=profile_path)
    return str(profile["profiles"][profile_id]["dtype"])


def load_bge_batch_profile(path: Path | str | None = None) -> dict[str, Any]:
    profile_path = Path(path).resolve() if path is not None else BATCH_PROFILE_PATH
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BgeEmbeddingContractError(
            f"cannot load BGE batch profile: {profile_path}"
        ) from exc
    if not isinstance(profile, dict) or profile.get("schema_version") != (
        "apps_rg.bge_batch_profile.v1"
    ):
        raise BgeEmbeddingContractError("BGE batch profile schema mismatch")
    if profile.get("adaptive_growth_allowed") is not False or profile.get(
        "fallback_allowed"
    ) is not False:
        raise BgeEmbeddingContractError("BGE batch profile control flags are invalid")
    return profile


def resolve_bge_batch_size(
    workload_id: str,
    item_count: int,
    *,
    requested: int | None = None,
    profile_path: Path | str | None = None,
) -> int:
    if item_count < 1:
        raise BgeEmbeddingContractError("BGE batch item_count must be positive")
    profile = load_bge_batch_profile(profile_path)
    row = (profile.get("workloads") or {}).get(workload_id)
    if not isinstance(row, dict):
        raise BgeEmbeddingContractError(f"BGE batch workload is unconfigured: {workload_id}")
    target = int(row.get("target_batch_size") or 0)
    maximum = int(row.get("maximum_batch_size") or 0)
    if target < 1 or maximum < target:
        raise BgeEmbeddingContractError(f"invalid BGE batch limits: {workload_id}")
    selected = target if requested is None else int(requested)
    if selected < 1 or selected > maximum:
        raise BgeEmbeddingContractError(
            f"BGE batch size outside profile for {workload_id}: {selected} > {maximum}"
        )
    return min(item_count, selected)


def load_local_bge_model(key: BgeRuntimeKey) -> Any:
    """Construct one explicitly local SentenceTransformer for ``key``."""

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise BgeEmbeddingContractError(
            "BGE-M3 runtime dependencies are unavailable"
        ) from exc
    if key.device.startswith("cuda") and not torch.cuda.is_available():
        raise BgeEmbeddingContractError(
            f"{key.device} requested but torch.cuda.is_available() is false"
        )
    kwargs: dict[str, Any] = {
        "device": key.device,
        "local_files_only": True,
    }
    if key.dtype != DEFAULT_DTYPE:
        kwargs["model_kwargs"] = {"torch_dtype": getattr(torch, key.dtype)}
    return SentenceTransformer(key.model_path, **kwargs)


def _coerce_vectors(
    encoded: Any, expected_count: int
) -> tuple[list[list[float]], float]:
    rows = encoded.tolist() if hasattr(encoded, "tolist") else encoded
    if rows is None or len(rows) != expected_count:
        raise BgeEmbeddingContractError(
            f"BGE-M3 batch mismatch: expected {expected_count}, got "
            f"{None if rows is None else len(rows)}"
        )
    vectors: list[list[float]] = []
    maximum_pre_normalization_error = 0.0
    for row in rows:
        vector = [float(value) for value in row]
        if len(vector) != BGE_M3_DIMENSION:
            raise BgeEmbeddingContractError(
                "BGE-M3 embedding dimension mismatch: "
                f"expected {BGE_M3_DIMENSION}, got {len(vector)}"
            )
        norm = math.sqrt(sum(value * value for value in vector))
        pre_normalization_error = abs(norm - 1.0)
        if (
            not math.isfinite(norm)
            or norm <= 0.0
            or pre_normalization_error > MAX_PRE_NORMALIZATION_ERROR
        ):
            raise BgeEmbeddingContractError(
                f"BGE-M3 embedding is not L2 normalized: observed norm={norm!r}"
            )
        maximum_pre_normalization_error = max(
            maximum_pre_normalization_error, pre_normalization_error
        )
        normalized = [value / norm for value in vector]
        post_norm = math.sqrt(sum(value * value for value in normalized))
        if not math.isclose(post_norm, 1.0, rel_tol=1e-7, abs_tol=1e-7):
            raise BgeEmbeddingContractError(
                f"BGE-M3 FP32 post-normalization failed: observed norm={post_norm!r}"
            )
        vectors.append(normalized)
    return vectors, maximum_pre_normalization_error


def _length_summary(values: Sequence[int]) -> dict[str, int] | None:
    if not values:
        return None
    ordered = sorted(int(value) for value in values)
    return {
        "min": ordered[0],
        "p50": ordered[max(0, math.ceil(0.50 * len(ordered)) - 1)],
        "p95": ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
        "max": ordered[-1],
    }


class BgeResidentRuntime:
    """One loaded BGE model plus serialized inference and lifecycle metrics."""

    def __init__(self, key: BgeRuntimeKey, model: Any, *, load_ordinal: int) -> None:
        self.key = key
        self._model: Any | None = model
        self._lock = threading.RLock()
        self.created_at = datetime.now(UTC).isoformat()
        self.load_ordinal = load_ordinal
        self.warmup_completed = False
        self.warmup_elapsed_ms: float | None = None
        self.encode_call_count = 0
        self.encoded_text_count = 0
        self.last_batch_size: int | None = None
        self.last_pre_normalization_max_error: float | None = None
        self.maximum_pre_normalization_error = 0.0
        self.cold_caller_elapsed_ms: float | None = None
        self.warm_caller_elapsed_ms: deque[float] = deque(maxlen=128)
        self.last_encode_observation: dict[str, Any] | None = None
        self.unloaded = False

    @property
    def model(self) -> Any:
        if self._model is None or self.unloaded:
            raise BgeEmbeddingContractError("BGE-M3 resident runtime is unloaded")
        return self._model

    def _encode(self, texts: Sequence[str], *, batch_size: int) -> list[list[float]]:
        try:
            import torch
        except ImportError as exc:
            raise BgeEmbeddingContractError(
                "torch is required for BGE inference"
            ) from exc
        with torch.inference_mode():
            encoded = self.model.encode(
                list(texts),
                batch_size=batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        vectors, pre_normalization_error = _coerce_vectors(encoded, len(texts))
        self.last_pre_normalization_max_error = pre_normalization_error
        self.maximum_pre_normalization_error = max(
            self.maximum_pre_normalization_error, pre_normalization_error
        )
        return vectors

    def _sequence_observation(self, texts: Sequence[str]) -> dict[str, Any]:
        observation: dict[str, Any] = {
            "character_lengths": _length_summary([len(text) for text in texts]),
            "token_lengths_available": False,
            "token_lengths": None,
            "model_max_length": None,
            "over_model_max_count": None,
        }
        tokenizer = getattr(self.model, "tokenizer", None)
        if not callable(tokenizer):
            return observation
        try:
            encoded = tokenizer(
                list(texts),
                add_special_tokens=True,
                padding=False,
                truncation=False,
            )
            lengths = [len(row) for row in encoded["input_ids"]]
            model_max = int(getattr(tokenizer, "model_max_length", 0) or 0)
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
            return observation
        observation.update(
            {
                "token_lengths_available": True,
                "token_lengths": _length_summary(lengths),
                "model_max_length": model_max,
                "over_model_max_count": (
                    sum(length > model_max for length in lengths)
                    if 0 < model_max < 10**9
                    else 0
                ),
            }
        )
        return observation

    def _cuda_memory_observation(self) -> dict[str, float] | None:
        if not self.key.device.startswith("cuda"):
            return None
        try:
            import torch

            if not torch.cuda.is_available():
                return None
            divisor = 1024.0 * 1024.0
            return {
                "allocated_mib": round(torch.cuda.memory_allocated() / divisor, 3),
                "reserved_mib": round(torch.cuda.memory_reserved() / divisor, 3),
                "peak_allocated_mib": round(
                    torch.cuda.max_memory_allocated() / divisor, 3
                ),
                "peak_reserved_mib": round(
                    torch.cuda.max_memory_reserved() / divisor, 3
                ),
            }
        except (ImportError, RuntimeError):
            return None

    def warmup(self) -> None:
        with self._lock:
            if self.warmup_completed:
                return
            started = time.perf_counter()
            self._encode([WARMUP_TEXT], batch_size=1)
            if self.key.device.startswith("cuda"):
                import torch

                torch.cuda.synchronize(int(self.key.device.split(":", 1)[1]))
            self.warmup_elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
            self.warmup_completed = True

    def encode(
        self, texts: Sequence[str], *, batch_size: int | None = None
    ) -> list[list[float]]:
        values = [str(text) for text in texts]
        if not values:
            raise BgeEmbeddingContractError("cannot embed an empty batch")
        selected_batch_size = batch_size or len(values)
        if selected_batch_size < 1:
            raise BgeEmbeddingContractError("BGE batch_size must be positive")
        with self._lock:
            sequence_observation = self._sequence_observation(values)
            started = time.perf_counter()
            vectors = self._encode(values, batch_size=selected_batch_size)
            if self.key.device.startswith("cuda"):
                import torch

                torch.cuda.synchronize()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            call_kind = "cold_caller" if self.encode_call_count == 0 else "warm_caller"
            if self.encode_call_count == 0:
                self.cold_caller_elapsed_ms = elapsed_ms
            else:
                self.warm_caller_elapsed_ms.append(elapsed_ms)
            self.encode_call_count += 1
            self.encoded_text_count += len(values)
            self.last_batch_size = selected_batch_size
            self.last_encode_observation = {
                "call_kind": call_kind,
                "input_count": len(values),
                "batch_size": selected_batch_size,
                "elapsed_ms": round(elapsed_ms, 3),
                "texts_per_second": round(len(values) * 1000.0 / elapsed_ms, 3),
                **sequence_observation,
                "cuda_memory": self._cuda_memory_observation(),
            }
            return vectors

    def observation(self) -> dict[str, Any]:
        model = self._model
        warm_samples = list(self.warm_caller_elapsed_ms)
        warm_summary = (
            {
                "sample_count": len(warm_samples),
                "p50_ms": _length_summary(
                    [round(value * 1000.0) for value in warm_samples]
                )["p50"]
                / 1000.0,
                "p95_ms": _length_summary(
                    [round(value * 1000.0) for value in warm_samples]
                )["p95"]
                / 1000.0,
            }
            if warm_samples
            else {"sample_count": 0, "p50_ms": None, "p95_ms": None}
        )
        runtime_environment: dict[str, Any] = {}
        try:
            import torch

            runtime_environment = {
                "torch_version": str(torch.__version__),
                "cuda_runtime_version": str(torch.version.cuda),
                "gpu_name": (
                    torch.cuda.get_device_name()
                    if self.key.device.startswith("cuda") and torch.cuda.is_available()
                    else None
                ),
                "compute_capability": (
                    list(torch.cuda.get_device_capability())
                    if self.key.device.startswith("cuda") and torch.cuda.is_available()
                    else None
                ),
            }
        except (ImportError, RuntimeError):
            runtime_environment = {}
        return {
            "key": asdict(self.key),
            "created_at": self.created_at,
            "load_ordinal": self.load_ordinal,
            "model_object_id": id(model) if model is not None else None,
            "model_device": str(getattr(model, "device", ""))
            if model is not None
            else None,
            "warmup_completed": self.warmup_completed,
            "warmup_elapsed_ms": self.warmup_elapsed_ms,
            "encode_call_count": self.encode_call_count,
            "encoded_text_count": self.encoded_text_count,
            "last_batch_size": self.last_batch_size,
            "runtime_environment": runtime_environment,
            "caller_timing": {
                "cold_elapsed_ms": (
                    round(self.cold_caller_elapsed_ms, 3)
                    if self.cold_caller_elapsed_ms is not None
                    else None
                ),
                "warm": warm_summary,
                "history_limit": 128,
            },
            "last_encode": self.last_encode_observation,
            "fp32_post_normalization": True,
            "last_pre_normalization_max_error": self.last_pre_normalization_max_error,
            "maximum_pre_normalization_error": self.maximum_pre_normalization_error,
            "local_files_only": True,
            "inference_mode": True,
            "fallback_used": False,
            "unloaded": self.unloaded,
        }

    def unload(self) -> None:
        with self._lock:
            if self.unloaded:
                return
            model = self._model
            self._model = None
            self.unloaded = True
            try:
                if model is not None and hasattr(model, "to"):
                    model.to("cpu")
                import torch

                if self.key.device.startswith("cuda") and torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except (ImportError, RuntimeError):
                pass


_registry_lock = threading.RLock()
_runtime_registry: dict[BgeRuntimeKey, BgeResidentRuntime] = {}
_model_load_count = 0


def get_bge_runtime(
    *,
    model_path: Path | str,
    device: str | None = None,
    dtype: str | None = None,
    backend: str | None = None,
    warmup: bool = True,
) -> BgeResidentRuntime:
    global _model_load_count
    key = resolve_bge_runtime_key(
        model_path=model_path, device=device, dtype=dtype, backend=backend
    )
    with _registry_lock:
        runtime = _runtime_registry.get(key)
        if runtime is None:
            model = load_local_bge_model(key)
            _model_load_count += 1
            runtime = BgeResidentRuntime(key, model, load_ordinal=_model_load_count)
            _runtime_registry[key] = runtime
    if warmup:
        runtime.warmup()
    return runtime


def get_bge_runtime_for_settings(
    settings: Any, *, warmup: bool = True
) -> BgeResidentRuntime:
    if not bool(getattr(settings, "embeddings_enabled", False)):
        raise BgeEmbeddingContractError(
            "BGE load forbidden when embeddings are disabled"
        )
    path = str(getattr(settings, "embedding_model_path", "") or "")
    if not bool(getattr(settings, "embedding_model_resolved", False)) or not path:
        raise BgeEmbeddingContractError(
            str(getattr(settings, "decisive_reason", "") or "BGE path unresolved")
        )
    return get_bge_runtime(model_path=path, warmup=warmup)


def resident_runtime_observation() -> dict[str, Any]:
    with _registry_lock:
        runtimes = [
            runtime.observation()
            for _key, runtime in sorted(
                _runtime_registry.items(), key=lambda item: item[0]
            )
        ]
        return {
            "schema_version": RUNTIME_SCHEMA,
            "process_id": os.getpid(),
            "registry_size": len(runtimes),
            "model_load_count": _model_load_count,
            "runtimes": runtimes,
            "scope": {
                "runtime_residency_verified": True,
                "retrieval_quality_measured": False,
                "production_promotion_authorized": False,
                "release_authorizing": False,
            },
        }


def unload_bge_runtime(key: BgeRuntimeKey | None = None) -> int:
    with _registry_lock:
        selected = list(_runtime_registry) if key is None else [key]
        unloaded = 0
        for runtime_key in selected:
            runtime = _runtime_registry.pop(runtime_key, None)
            if runtime is not None:
                runtime.unload()
                unloaded += 1
        return unloaded


def reset_bge_runtime_for_testing() -> None:
    global _model_load_count
    unload_bge_runtime()
    with _registry_lock:
        _model_load_count = 0


def embed_text(model: Any, text: str) -> list[float]:
    """Compatibility helper for an already loaded local model."""

    try:
        import torch
    except ImportError as exc:
        raise BgeEmbeddingContractError("torch is required for BGE inference") from exc
    with torch.inference_mode():
        encoded = model.encode(
            [str(text)],
            batch_size=1,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    return _coerce_vectors(encoded, 1)[0][0]


def receipt_sha256(receipt: Mapping[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    rendered = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


atexit.register(unload_bge_runtime)

__all__ = [
    "BgeEmbeddingContractError",
    "BgeResidentRuntime",
    "BgeRuntimeKey",
    "embed_text",
    "get_bge_runtime",
    "get_bge_runtime_for_settings",
    "load_local_bge_model",
    "load_bge_precision_profile",
    "receipt_sha256",
    "reset_bge_runtime_for_testing",
    "resident_runtime_observation",
    "resolve_bge_batch_size",
    "resolve_bge_precision_dtype",
    "resolve_bge_precision_profile_id",
    "resolve_bge_runtime_key",
    "unload_bge_runtime",
]
