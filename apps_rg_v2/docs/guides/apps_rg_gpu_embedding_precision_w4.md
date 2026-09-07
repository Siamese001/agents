# Apps RG GPU embedding precision W4

W4 compares the governed resident BGE-M3 runtime in FP32, FP16, and BF16 on
the four tracked W0 workload shapes using the W3 batch profile. Selection is
based on measured current-device results, not a GPU-generation assumption.

The tracked profile is
`src/apps_rg/config/domain_contract/bge_precision_profile.v1.json`. It keeps
`fp32_control` as the explicit rollback profile. Set
`APPS_RG_BGE_PRECISION_PROFILE=fp32_control` to invoke that rollback; an
ungoverned dtype override fails closed.

Run the benchmark from the repository root:

```powershell
python tools/apps_rg_standalone/gpu_embedding_precision_w4.py
```

The benchmark requires at least 1.30x aggregate warm throughput, 1024-D finite
unit vectors, minimum same-index cosine 0.999, equal top-10 sets for all six
proxy queries, peak allocation below 3200 MiB, no network or fallback, and
explicit unload after every profile. Lower-precision output is post-normalized
in FP32 after a bounded pre-normalization sanity check.

Eligible candidates within 2% aggregate throughput are treated as a timing tie;
minimum cosine and then exact proxy rank order choose between them. This avoids
changing the selected profile because of sub-2% run-to-run timing noise.

The rank comparison uses six tracked queries against 26 tracked workload texts.
It documents technical precision drift only. It does not use human QRELs,
measure Recall@10/nDCG/MRR, qualify retrieval, or authorize production/release.
