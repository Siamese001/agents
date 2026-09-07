# apps_rg GPU embedding environment W1

W1 freezes the currently working Windows GPU embedding control without changing
the production runtime. It binds Python, the complete embedding dependency
closure, stable critical wheel payload digests, the local Apps RG source tree,
the C0.3 runtime contract, the BGE-M3 model bytes, offline policy, and the
observed single-GPU requirements.

The control remains CUDA 12.8. Alternative Torch or CUDA stacks belong in an
isolated A/B environment and cannot replace this contract automatically.

## Create an isolated control environment

Use CPython 3.12.10 on Windows x86-64:

```powershell
py -3.12 -m venv .runtime\venvs\apps-rg-gpu-w1
& .runtime\venvs\apps-rg-gpu-w1\Scripts\python.exe -m pip install --upgrade pip
& .runtime\venvs\apps-rg-gpu-w1\Scripts\python.exe -m pip install --no-deps `
  -r tools\apps_rg_standalone\gpu_embedding_environment_w1.lock.txt
```

The lock installs the external core as an editable checkout at one exact Git
revision. Its Torch line uses the exact PyTorch-hosted wheel URL and SHA-256,
not the moving nightly index. Pip must reject the artifact if its bytes differ.

The pinned BGE-M3 snapshot is separate from Python dependencies. Materialize it
at the revision named by the W1 contract and set its local path if it is not in
the standard Hugging Face cache:

```powershell
$env:APPS_RG_EMBEDDING_MODEL_PATH = 'C:\path\to\5617a9f61b028005a4858fdac845db406aefb181'
```

## Run the preflight

```powershell
$env:APPS_RG_SKIP_DOTENV_AUTOLOAD = '1'
python tools\apps_rg_standalone\gpu_embedding_preflight_w1.py `
  --output .runtime\apps_rg\gpu-embedding-environment-w1\operator-run
```

The CLI enforces offline guards before importing the embedding stack. It then
fails closed unless all of the following match the contract:

- Python implementation, exact version, operating system, and architecture;
- all 87 registry-resolved dependency pins plus the two direct source pins;
- versions, stable wheel payload digests, and module locations for eight critical
  distributions;
- local Apps RG source location, commit, tree, and working-tree state,
  and clean module subtree;
- `cuda:0`, the required compiled CUDA architecture, working CUDA kernel,
  minimum driver, total VRAM, and currently free VRAM;
- exact Torch CUDA runtime and offline environment;
- exact BGE-M3 revision, file inventory digest, dimension, and normalization.

The receipt is written only under ignored `.runtime/`. A PASS proves environment
identity and a working CUDA kernel. It does not benchmark embeddings, measure
retrieval quality, authorize production promotion, or authorize a release.
