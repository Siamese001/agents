# Local OTel collector preflight

This starts a local OTLP/HTTP collector on `127.0.0.1:14318` that writes trace
exports to ignored `.runtime/otel-collector/traces.jsonl`. Port `14318` avoids
the Docker Desktop listener already using the conventional host port `4318`.
It is for local E2E proof only and does not contain credentials.

Start it in the shell that will launch Apps RG so the two variables persist:

```powershell
. .\tools\otel\start-local-collector.ps1
python .\tools\otel\verify_preflight.py --artifact-dir .runtime\otel-preflight
```

A passing verifier emits `otel_runtime_receipt.json`,
`otel_collector_preflight.json`, and `otel_preflight_snapshot.json` under the
specified artifact directory. It proves a fresh marker was received; it does
not call a model or authorize a product run.

Stop the collector when finished:

```powershell
.\tools\otel\start-local-collector.ps1 -Stop
```
