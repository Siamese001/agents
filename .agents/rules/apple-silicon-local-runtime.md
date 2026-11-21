---
trigger: model_decision
description: Apple Silicon macOS MPS-first runtime invariant with CPU fallback and zero CUDA dependencies.
---

# Apple Silicon Local MacBook Runtime Invariant

Governs local development and execution across macOS (Darwin) environments.

## 1. Zero CUDA Deprecation Invariant
- All runtime components, graph skills, and dependencies must execute natively on Apple Silicon without requiring CUDA or NVIDIA hardware.
- No repository manifest (`pyproject.toml`) or lockfile (`uv.lock`) may include CUDA-specific binary wheels (`flashinfer`, `vllm`, `nvidia-cutlass`, `cuda-python`).
- CI/CD and local development configurations must enforce `uv lock --check` ensuring zero CUDA artifacts.

## 2. Hardware Acceleration & CPU Fallback
- Hardware acceleration (Apple Silicon Metal `mps`) is restricted to transformer/BGE embeddings and opt-in large vector math (`APPS_SHARED_VECTOR_GPU_ENABLED` + `APPS_SHARED_VECTOR_GPU_MIN_ROWS`), resolved via `infrastructure/device/device_manager.py:resolve_optimal_device()`.
- If MPS is unavailable or uninitialized, execution must fall back cleanly to `cpu` without unhandled exceptions or device mismatches.
- Control-plane orchestration, C0.3 graph traversal, SQLite FTS5 queries, receipt assembly, and JSON/file I/O stay on CPU.

## 3. Verification & Benchmark Standard
- Standalone verification must be maintained under `tests/macbook_runtime/` (verifying device resolution, CUDA absence, local graph skill execution, and end-to-end pipeline sanity).
- Operational performance must be verifiable via `tools/benchmark_macbook_runtime.py --iterations 10 --assert-gates`, confirming:
  - Temporal latency drift $\le 1.15$ (or sub-1.5ms jitter deadband on micro-benchmarks).
  - RSS memory delta $\le 5.0$ MiB.
  - Active Metal (MPS) allocated memory leak of $0.0$ MiB.
