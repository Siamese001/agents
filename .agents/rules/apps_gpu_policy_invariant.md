# ProceduralPattern:AppsGpuPolicyInvariant

- INVARIANT: apps_* GPU/hardware acceleration is limited to transformer/BGE inference and explicitly opted-in large vector math; graph traversal, receipt assembly, JSON/file IO, and control-plane orchestration stay CPU. On macOS (Darwin), hardware acceleration defaults to Apple Silicon Metal (MPS) with CPU fallback; legacy CUDA dependencies are strictly deprecated.
- scope: apps_rg/cache/r1b_bge_embedding.py, apps_rg/cache/r1b_chroma_read_surface_projection.py, apps_research/engines/integration/chroma_research_store.py, apps_shared/enforcement/GlobalcacheStrategy.py, infrastructure/device/device_manager.py.
- enforcement: tests/_apps_contract/test_w6_real_embeddings_and_ingestion.py; tests/macbook_runtime/test_apple_silicon_device_resolution.py; tests/macbook_runtime/test_cuda_absence.py; tools/benchmark_macbook_runtime.py.
- canonical_pattern: resolve devices through infrastructure/device/device_manager.py (resolve_optimal_device()); batch parent+chunk R1B embeddings before Chroma upsert; require APPS_SHARED_VECTOR_GPU_ENABLED plus APPS_SHARED_VECTOR_GPU_MIN_ROWS before hardware similarity search.
- violation_examples: moving C0.3 graph traversal onto GPU; using GPU for small generic apps_shared vector stores by default; assuming remote provider calls consume local GPU; reintroducing CUDA dependencies on macOS.
- discovered: 2026-06-23, validated: 2026-11-08.
