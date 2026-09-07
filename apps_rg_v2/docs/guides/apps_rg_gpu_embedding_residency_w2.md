# Apps RG W2 resident BGE-M3 runtime

W2 consolidates local BGE-M3 ownership in
`src/apps_rg/runtime/bge_embedding.py`. One process registry is keyed by the
resolved model directory, explicit device, dtype, and backend. The current
control key is the pinned local model on `cuda:0`, using the W4 selected
precision profile and the `sentence_transformers` backend. W4 retains
`fp32_control` as the explicit rollback profile.

The runtime always loads from an on-disk path with offline guards and
`local_files_only=True`. It performs a fixed non-corpus warm-up once, serializes
model inference under `torch.inference_mode()`, preserves 1024-dimensional
L2-normalized vectors, and exposes load, warm-up, call, text-count, batch, and
lifecycle observations.

C0 and C0.2, the C0.3 projection builder, and R1B now resolve the same runtime.
C0.2 intentionally retains its ordered single-item calls until W3 introduces
profile-bounded batching.

Run the real-GPU residency proof:

```powershell
$env:APPS_RG_EMBEDDING_MODEL_PATH = '<absolute pinned BGE-M3 snapshot>'
$env:EMBEDDING_DEVICE = 'cuda:0'
python tools/apps_rg_standalone/gpu_embedding_residency_w2.py `
  --output .runtime/apps_rg/gpu-embedding-residency-w2/current/receipt.json
```

The command must report one model load and one registry entry before explicit
unload, then zero registry entries afterward. Its receipt is runtime evidence
only. It does not measure retrieval quality or authorize promotion or release.
