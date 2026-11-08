# Apple Silicon Local MacBook Runtime Invariant

Governs local development and execution across macOS (Darwin) environments.

## 1. Zero CUDA Deprecation Invariant
- All runtime components, graph skills, and dependencies must execute natively on Apple Silicon without requiring CUDA or NVIDIA hardware.
- No repository manifest (`pyproject.toml`) or lockfile (`uv.lock`) may include CUDA-specific binary wheels (`flashinfer`, `vllm`, `nvidia-cutlass`, `cuda-python`).
- CI/CD and local development configurations must enforce `uv lock --check` ensuring zero CUDA artifacts.

## 2. Hardware Acceleration & CPU Fallback
- Model embeddings, tensor evaluations, and dense vector operations must query `infrastructure/device/device_manager.py:resolve_optimal_device()`.
- On macOS with Apple Silicon, the runtime must prioritize Metal Performance Shaders (`mps`).
- If MPS is unavailable or uninitialized, execution must seamlessly fall back to `cpu` without unhandled exceptions or device mismatches.
- Control-plane orchestration, graph database queries (SQLite FTS5), and formatting stay on CPU.

## 3. Verification & Benchmark Standard
- Standalone verification must be maintained under `tests/macbook_runtime/` (verifying device resolution, CUDA absence, local graph skill execution, and end-to-end pipeline sanity).
- Operational performance must be verifiable via `tools/benchmark_macbook_runtime.py --iterations 10 --assert-gates`, confirming:
  - Temporal latency drift $\le 1.15$ (or sub-1.5ms jitter deadband on micro-benchmarks).
  - RSS memory delta $\le 5.0$ MiB.
  - Active Metal (MPS) allocated memory leak of $0.0$ MiB.
