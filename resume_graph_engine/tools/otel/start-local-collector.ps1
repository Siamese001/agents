[CmdletBinding()]
param(
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..')).Path
$configPath = Join-Path $scriptRoot 'collector.yaml'
$outputDir = Join-Path $repoRoot '.runtime\otel-collector'
$containerName = 'apps-rg-otel-collector'
$image = 'otel/opentelemetry-collector-contrib:0.111.0'
$hostPort = 14318

if ($Stop) {
    $existing = docker ps -aq --filter "name=^/$containerName$"
    if ($existing) {
        docker rm -f $containerName | Out-Null
    }
    Write-Output "Stopped $containerName."
    return
}

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Collector configuration is missing: $configPath"
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$running = docker ps -q --filter "name=^/$containerName$"
if (-not $running) {
    $existing = docker ps -aq --filter "name=^/$containerName$"
    if ($existing) {
        docker rm -f $containerName | Out-Null
    }
    docker run --detach --rm --name $containerName `
        --publish "127.0.0.1:${hostPort}:4318" `
        --volume "${configPath}:/etc/otelcol-contrib/config.yaml:ro" `
        --volume "${outputDir}:/var/otel" `
        $image `
        '--config=/etc/otelcol-contrib/config.yaml' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker could not start $containerName."
    }
}

for ($attempt = 1; $attempt -le 20; $attempt++) {
    $listening = Test-NetConnection -ComputerName '127.0.0.1' -Port $hostPort -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($listening) {
        $collectorEndpoint = "http://127.0.0.1:${hostPort}"
        $collectorSpansFile = (Join-Path $outputDir 'traces.jsonl')

        # Apps RG loads the shared dotenv after this launcher runs. Seed the
        # supported legacy aliases too, so dotenv's non-overriding load cannot
        # reintroduce a conflicting stale collector configuration.
        $env:OTEL_EXPORTER_OTLP_ENDPOINT = $collectorEndpoint
        $env:APPS_OTEL_EXPORTER_OTLP_ENDPOINT = $collectorEndpoint
        $env:APPS_OTEL_COLLECTOR_SPANS_FILE = $collectorSpansFile
        $env:APPS_OTEL_COLLECTOR_FILE = $collectorSpansFile
        $env:OTEL_COLLECTOR_SPANS_FILE = $collectorSpansFile
        Write-Output "OTEL_EXPORTER_OTLP_ENDPOINT=$env:OTEL_EXPORTER_OTLP_ENDPOINT"
        Write-Output "APPS_OTEL_COLLECTOR_SPANS_FILE=$env:APPS_OTEL_COLLECTOR_SPANS_FILE"
        Write-Output "Collector=$containerName"
        return
    }
    Start-Sleep -Milliseconds 250
}

docker logs $containerName
throw "Collector did not listen on 127.0.0.1:$hostPort"
