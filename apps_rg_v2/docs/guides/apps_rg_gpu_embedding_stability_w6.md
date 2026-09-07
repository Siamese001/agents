# Apps RG GPU embedding stability W6

W6 extends the completed W0-W5 plan with sustained runtime evidence. Eight
concurrent callers must resolve to one resident local model, then that runtime
executes six cycles of the four tracked W0 workloads with the W3 batch limits
and W4 precision selection.

The tracked stability controls are in
`src/apps_rg/config/domain_contract/bge_stability_profile.v1.json`. They bind
the exact W5 receipt and fail closed on repeated model loads, registry growth,
unstable vector digests, latency drift, W5 performance regression, or CUDA
allocation growth.

Run the physical-GPU proof from the repository root:

```powershell
python tools/apps_rg_standalone/gpu_embedding_stability_w6.py
```

The receipt is written beneath
`.runtime/apps_rg/gpu-embedding-stability-w6/current/receipt.json`. The proof
does not open retrieval stores, read QRELs, qualify retrieval, authorize
production promotion, or authorize release.
