# Apps RG GPU embedding batching W3

W3 replaces per-item embedding calls in C0.2 fact-vector ingest and C0.2
section retrieval with bounded, stable-order batches. R1B projection now uses
the same tracked batch profile by default while continuing to reuse the W2
resident runtime.

The production limits are stored in
`src/apps_rg/config/domain_contract/bge_batch_profile.v1.json`. Adaptive growth
and fallback are disabled. A caller may request a smaller batch, but a request
above the workload maximum fails closed.

Run the current-GPU benchmark from the repository root:

```powershell
python tools/apps_rg_standalone/gpu_embedding_batching_w3.py
```

The benchmark compares the prior per-item call shape with one bounded call,
sweeps practical batch sizes, verifies same-index vector equivalence, captures
peak CUDA memory, proves one resident model load, and unloads explicitly. Its
receipt is written only to
`.runtime/apps_rg/gpu-embedding-batching-w3/current/receipt.json`.
The ingest measurement deterministically repeats the tracked eight-item
claim-sized source shape to sweep through the tested 32-item cap. The tracked
target is the measured current-device throughput knee, not a device-generation
assumption.

This receipt measures embedding throughput only. It does not open Chroma or a
graph projection, read QRELs, qualify retrieval, authorize production, or
authorize release.
