# apps_rg GPU embedding baseline W0

W0 measures the four governed BGE-M3 embedding shapes on the current local GPU:

1. the frozen six-query C0.3 set;
2. the eleven whole-resume C0.3 section queries;
3. representative C0.2 section-retrieval queries; and
4. a representative R1B projection batch containing one canonical intent and
   seven base-resume chunks.

It is an execution baseline, not a retrieval evaluation. The harness does not
open Chroma or a graph projection, does not read QREL judgments, and cannot
authorize a release or production promotion. It loads the pinned local
`BAAI/bge-m3` revision with offline mode and `local_files_only=True`; CPU and
fallback execution fail closed.

Run from the repository root:

```powershell
python tools/apps_rg_standalone/gpu_embedding_baseline_w0.py
```

The model path defaults to the pinned Hugging Face cache snapshot. Override it
only with the same pinned artifact:

```powershell
python tools/apps_rg_standalone/gpu_embedding_baseline_w0.py `
  --model-path C:\path\to\bge-m3\5617a9f61b028005a4858fdac845db406aefb181 `
  --warm-repetitions 5 `
  --output .runtime\apps_rg\gpu-baseline-w0\operator-run
```

Every output is confined to the ignored `.runtime/` tree. The receipt records:

- exact source, runtime-contract, and model-artifact digests;
- device, driver, CUDA runtime, Torch, and Sentence Transformers identity;
- input counts and digests, batch sizes, character and token-length buckets;
- model-load and cold-first-pass time;
- warm latency samples, p50/p95, and texts per second;
- allocated and reserved CUDA memory peaks; and
- 1024-dimensional, finite, L2-normalized vector proof without raw vectors.

For comparison runs, retain the full receipt. The compact CLI output is only an
operator summary and is not sufficient to reproduce or audit the baseline.
