#!/usr/bin/env python3
"""Operational Benchmark and Memory Leak Verification for Local Apple Silicon MacBook Runtime."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import json
import math
import os
from pathlib import Path
import platform
import psutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RG_SRC = REPO_ROOT / "resume_graph_engine" / "src"
for p in (REPO_ROOT, RG_SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import torch

try:
    from infrastructure.device.device_manager import (
        allocated_memory_bytes,
        empty_cache,
        resolve_optimal_device,
        synchronize,
    )
except ImportError:
    def resolve_optimal_device() -> str:
        return "mps" if sys.platform == "darwin" and torch.backends.mps.is_available() else "cpu"

    def synchronize(device: str | None = None) -> None:
        if device == "mps" or (device is None and torch.backends.mps.is_available()):
            if hasattr(torch, "mps") and hasattr(torch.mps, "synchronize"):
                torch.mps.synchronize()

    def empty_cache(device: str | None = None) -> None:
        if device == "mps" or (device is None and torch.backends.mps.is_available()):
            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()

    def allocated_memory_bytes(device: str | None = None) -> int:
        if device == "mps" or (device is None and torch.backends.mps.is_available()):
            if hasattr(torch, "mps") and hasattr(torch.mps, "current_allocated_memory"):
                return int(torch.mps.current_allocated_memory())
        return psutil.Process(os.getpid()).memory_info().rss


def _get_cpu_brand() -> str:
    try:
        res = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return platform.processor() or "Apple Silicon"


def _compute_stats(
    latencies_ms: list[float],
    jitter_threshold_ms: float = 2.0,
) -> dict[str, Any]:
    """Compute summary statistics and chronological execution drift.

    Percentiles are computed from the sorted array. Drift ratio and absolute delta
    are computed from the raw chronological sequence to assess temporal degradation
    without conflating sample dispersion with systemic slowdown.
    """
    if not latencies_ms:
        return {
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p99": 0.0,
            "drift_ratio": 1.0,
            "drift_delta_ms": 0.0,
            "latencies_ms": [],
        }
    sorted_lats = sorted(latencies_ms)
    n = len(sorted_lats)
    p50 = sorted_lats[n // 2]
    p90 = sorted_lats[int(n * 0.90)]
    p99 = sorted_lats[min(int(n * 0.99), n - 1)]

    # Chronological execution drift: preserve raw temporal sequence order
    mid = n // 2
    if mid > 0:
        first_half = latencies_ms[:mid]
        second_half = latencies_ms[mid:] if (n % 2 == 0) else latencies_ms[mid + 1:]
        p50_first = float(statistics.median(first_half))
        p50_second = float(statistics.median(second_half))

        delta = p50_second - p50_first
        if p50_first <= 0:
            drift_ratio = 1.0
        elif delta <= 0:
            # Performance maintained or improved chronologically
            drift_ratio = round(p50_second / p50_first, 3)
        elif delta <= jitter_threshold_ms:
            # Latency delta is within OS kernel scheduling noise floor
            drift_ratio = 1.0
        else:
            drift_ratio = round(p50_second / p50_first, 3)
        drift_delta_ms = round(delta, 3)
    else:
        drift_ratio = 1.0
        drift_delta_ms = 0.0

    return {
        "min": round(sorted_lats[0], 2),
        "max": round(sorted_lats[-1], 2),
        "mean": round(sum(sorted_lats) / n, 2),
        "p50": round(p50, 2),
        "p90": round(p90, 2),
        "p99": round(p99, 2),
        "drift_ratio": drift_ratio,
        "drift_delta_ms": drift_delta_ms,
        "latencies_ms": [round(x, 2) for x in latencies_ms],
    }


def _safe_run_workload(fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        return {
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "iterations": 0,
            "cold_latency_ms": 0.0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p99": 0.0,
            "drift_ratio": 1.0,
            "drift_delta_ms": 0.0,
            "latencies_ms": [],
            "rss_warm_start_mib": 0.0,
            "rss_final_mib": 0.0,
            "rss_delta_mib": 0.0,
            "leak_gate_passed": False,
            "drift_gate_passed": False,
        }


def benchmark_bge_m3_embedding(iterations: int = 10, quiet: bool = False) -> dict[str, Any]:
    from sentence_transformers import SentenceTransformer

    model_path = REPO_ROOT / "artifacts" / "models" / "BAAI" / "bge-m3"
    if not model_path.exists():
        return {"status": "SKIPPED", "reason": "model_not_found"}

    device = resolve_optimal_device()
    proc = psutil.Process(os.getpid())

    # Cold start: Load model & first forward pass
    t0_cold = time.perf_counter()
    model = SentenceTransformer(str(model_path), device=device)
    _ = model.encode(["Cold start query text for embedding initialization"], normalize_embeddings=True)
    synchronize(device)
    cold_latency_ms = round((time.perf_counter() - t0_cold) * 1000.0, 2)

    # 3 Warmup iterations for Metal command buffer stabilization
    batch = [
        "Governed agentic platform architecture",
        "Deterministic multi-hop graph traversal and hybrid RRF retrieval",
        "Apple Silicon Metal Performance Shaders runtime optimization",
        "Enterprise C-suite target briefing resolution",
        "L2 normalized dense vector similarity search",
        "Zero CUDA dependency verification",
    ]
    for _ in range(3):
        _ = model.encode(batch, normalize_embeddings=True)
        synchronize(device)

    empty_cache(device)
    gc.collect()

    rss_warm_start = proc.memory_info().rss / (1024 * 1024)
    mps_warm_start = (allocated_memory_bytes(device) / (1024 * 1024)) if device == "mps" else 0.0

    warm_latencies = []
    for i in range(iterations):
        t0 = time.perf_counter()
        _ = model.encode(batch, normalize_embeddings=True)
        synchronize(device)
        warm_latencies.append((time.perf_counter() - t0) * 1000.0)

    empty_cache(device)
    gc.collect()
    rss_final = proc.memory_info().rss / (1024 * 1024)
    mps_final = (allocated_memory_bytes(device) / (1024 * 1024)) if device == "mps" else 0.0

    delta_rss = round(rss_final - rss_warm_start, 2)
    delta_mps = round(mps_final - mps_warm_start, 2)
    stats = _compute_stats(warm_latencies, jitter_threshold_ms=3.0)
    leak_passed = delta_rss < 5.0 and delta_mps <= 0.5
    drift_passed = stats["drift_ratio"] <= 1.25 or stats.get("drift_delta_ms", 999.0) <= 3.0

    return {
        "status": "PASS" if (leak_passed and drift_passed) else "WARN",
        "device": device,
        "iterations": iterations,
        "cold_latency_ms": cold_latency_ms,
        **stats,
        "rss_warm_start_mib": round(rss_warm_start, 2),
        "rss_final_mib": round(rss_final, 2),
        "rss_delta_mib": delta_rss,
        "mps_allocated_mib": round(mps_final, 2),
        "mps_delta_mib": delta_mps,
        "leak_gate_passed": bool(leak_passed),
        "drift_gate_passed": bool(drift_passed),
    }


def benchmark_graph_sqlite_traversal(iterations: int = 10, quiet: bool = False) -> dict[str, Any]:
    from apps_rg.fact_inventory.augmented_skills_graph_sqlite import materialize_augmented_skills_graph_sqlite
    from apps_rg.runtime.graph_skill_hybrid_retrieval import sqlite_fts5_bm25_rank
    from apps_rg.runtime.graph_traversal import JOURNEY_DOMAIN_SKILL_EVIDENCE, traverse_journey

    proc = psutil.Process(os.getpid())
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "bench_graph.sqlite"
        t0_cold = time.perf_counter()
        materialize_augmented_skills_graph_sqlite(db_path=db_path)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            seeds = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT source_node_id FROM graph_edges WHERE edge_type = 'capability_domain_contains_skill' LIMIT 25"
                ).fetchall()
            ]
            _ = traverse_journey(conn, JOURNEY_DOMAIN_SKILL_EVIDENCE, seeds, max_paths=200)
            cold_latency_ms = round((time.perf_counter() - t0_cold) * 1000.0, 2)

            # Warmup (3 passes for query plan and cache stabilization)
            for _ in range(3):
                _ = traverse_journey(conn, JOURNEY_DOMAIN_SKILL_EVIDENCE, seeds, max_paths=200)
                _ = sqlite_fts5_bm25_rank(conn, "governed platform architecture", node_type="skill")

            gc.collect()
            rss_warm_start = proc.memory_info().rss / (1024 * 1024)

            warm_latencies = []
            for _ in range(iterations):
                t0 = time.perf_counter()
                _ = traverse_journey(conn, JOURNEY_DOMAIN_SKILL_EVIDENCE, seeds, max_paths=200)
                _ = sqlite_fts5_bm25_rank(conn, "governed platform architecture", node_type="skill")
                warm_latencies.append((time.perf_counter() - t0) * 1000.0)

            gc.collect()
            rss_final = proc.memory_info().rss / (1024 * 1024)
            delta_rss = round(rss_final - rss_warm_start, 2)
            stats = _compute_stats(warm_latencies, jitter_threshold_ms=2.0)
            leak_passed = delta_rss < 5.0
            drift_passed = stats["drift_ratio"] <= 1.25 or stats.get("drift_delta_ms", 999.0) <= 3.0

            return {
                "status": "PASS" if (leak_passed and drift_passed) else "WARN",
                "iterations": iterations,
                "cold_latency_ms": cold_latency_ms,
                **stats,
                "rss_warm_start_mib": round(rss_warm_start, 2),
                "rss_final_mib": round(rss_final, 2),
                "rss_delta_mib": delta_rss,
                "leak_gate_passed": bool(leak_passed),
                "drift_gate_passed": bool(drift_passed),
            }
        finally:
            conn.close()


def benchmark_dense_hybrid_rrf_fusion(iterations: int = 10, quiet: bool = False) -> dict[str, Any]:
    from apps_rg.runtime.graph_skill_hybrid_retrieval import fuse_dense_bm25

    proc = psutil.Process(os.getpid())
    assertion_ids = {f"aid_{i}" for i in range(100)}
    dense = [{"assertion_id": f"aid_{i}", "similarity": 1.0 - (i * 0.009)} for i in range(100)]
    bm25 = [{"assertion_id": f"aid_{99 - i}", "bm25_score": 10.0 - (i * 0.09)} for i in range(100)]

    # Cold
    t0_cold = time.perf_counter()
    _ = fuse_dense_bm25(dense, bm25, assertion_ids=assertion_ids)
    cold_latency_ms = round((time.perf_counter() - t0_cold) * 1000.0, 2)

    # 3 Warmup passes
    for _ in range(3):
        _ = fuse_dense_bm25(dense, bm25, assertion_ids=assertion_ids)

    gc.collect()
    rss_warm_start = proc.memory_info().rss / (1024 * 1024)

    warm_latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        _ = fuse_dense_bm25(dense, bm25, assertion_ids=assertion_ids)
        warm_latencies.append((time.perf_counter() - t0) * 1000.0)

    gc.collect()
    rss_final = proc.memory_info().rss / (1024 * 1024)
    delta_rss = round(rss_final - rss_warm_start, 2)
    stats = _compute_stats(warm_latencies, jitter_threshold_ms=1.0)
    leak_passed = delta_rss < 5.0
    drift_passed = stats["drift_ratio"] <= 1.25 or stats.get("drift_delta_ms", 999.0) <= 1.0

    return {
        "status": "PASS" if (leak_passed and drift_passed) else "WARN",
        "iterations": iterations,
        "cold_latency_ms": cold_latency_ms,
        **stats,
        "rss_warm_start_mib": round(rss_warm_start, 2),
        "rss_final_mib": round(rss_final, 2),
        "rss_delta_mib": delta_rss,
        "leak_gate_passed": bool(leak_passed),
        "drift_gate_passed": bool(drift_passed),
    }


def benchmark_deterministic_resume_pipeline(iterations: int = 3, quiet: bool = False) -> dict[str, Any]:
    from apps_rg.bare_pipeline import run_bare_deterministic_e2e

    proc = psutil.Process(os.getpid())
    with tempfile.TemporaryDirectory() as td:
        t0_cold = time.perf_counter()
        _ = run_bare_deterministic_e2e(artifact_root=str(Path(td) / "cold"))
        cold_latency_ms = round((time.perf_counter() - t0_cold) * 1000.0, 2)

        # 2 Warmup passes
        for w in range(2):
            _ = run_bare_deterministic_e2e(artifact_root=str(Path(td) / f"warmup_{w}"))

        gc.collect()
        rss_warm_start = proc.memory_info().rss / (1024 * 1024)

        warm_latencies = []
        for i in range(iterations):
            t0 = time.perf_counter()
            _ = run_bare_deterministic_e2e(artifact_root=str(Path(td) / f"warm_{i}"))
            warm_latencies.append((time.perf_counter() - t0) * 1000.0)

        gc.collect()
        rss_final = proc.memory_info().rss / (1024 * 1024)
        delta_rss = round(rss_final - rss_warm_start, 2)
        stats = _compute_stats(warm_latencies, jitter_threshold_ms=5.0)
        leak_passed = delta_rss < 20.0
        drift_passed = stats["drift_ratio"] <= 1.25 or stats.get("drift_delta_ms", 999.0) <= 50.0

        return {
            "status": "PASS" if (leak_passed and drift_passed) else "WARN",
            "iterations": iterations,
            "cold_latency_ms": cold_latency_ms,
            **stats,
            "rss_warm_start_mib": round(rss_warm_start, 2),
            "rss_final_mib": round(rss_final, 2),
            "rss_delta_mib": delta_rss,
            "leak_gate_passed": bool(leak_passed),
            "drift_gate_passed": bool(drift_passed),
        }


def benchmark_outreach_validation(iterations: int = 10, quiet: bool = False) -> dict[str, Any]:
    from apps_lic.runtime.dispatch.canonical_dispatch import run_canonical_apps_lic_spine

    proc = psutil.Process(os.getpid())
    ingress = {
        "company": "Truist",
        "channel": "email",
        "recipient_class": "recruiter",
        "manual_brief": "Platform modernization and agentic governance",
    }
    with tempfile.TemporaryDirectory() as td:
        t0_cold = time.perf_counter()
        _ = run_canonical_apps_lic_spine(ingress, artifact_dir=Path(td) / "cold")
        cold_latency_ms = round((time.perf_counter() - t0_cold) * 1000.0, 2)

        # 3 Warmup passes
        for w in range(3):
            _ = run_canonical_apps_lic_spine(ingress, artifact_dir=Path(td) / f"warmup_{w}")

        gc.collect()
        rss_warm_start = proc.memory_info().rss / (1024 * 1024)

        warm_latencies = []
        for i in range(iterations):
            t0 = time.perf_counter()
            _ = run_canonical_apps_lic_spine(ingress, artifact_dir=Path(td) / f"warm_{i}")
            warm_latencies.append((time.perf_counter() - t0) * 1000.0)

        gc.collect()
        rss_final = proc.memory_info().rss / (1024 * 1024)
        delta_rss = round(rss_final - rss_warm_start, 2)
        stats = _compute_stats(warm_latencies, jitter_threshold_ms=2.0)
        leak_passed = delta_rss < 5.0
        drift_passed = stats["drift_ratio"] <= 1.25 or stats.get("drift_delta_ms", 999.0) <= 5.0

        return {
            "status": "PASS" if (leak_passed and drift_passed) else "WARN",
            "iterations": iterations,
            "cold_latency_ms": cold_latency_ms,
            **stats,
            "rss_warm_start_mib": round(rss_warm_start, 2),
            "rss_final_mib": round(rss_final, 2),
            "rss_delta_mib": delta_rss,
            "leak_gate_passed": bool(leak_passed),
            "drift_gate_passed": bool(drift_passed),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apple Silicon MacBook Runtime Benchmark Suite")
    parser.add_argument("--iterations", type=int, default=10, help="Number of warm benchmark iterations")
    parser.add_argument(
        "--workloads",
        type=str,
        default="embedding,traversal,fusion,outreach,resume",
        help="Comma-separated workload names",
    )
    parser.add_argument("--output-receipt", type=str, default=None, help="Receipt JSON file destination")
    parser.add_argument("--assert-gates", action="store_true", help="Exit non-zero if any gate fails")
    parser.add_argument("--quiet", action="store_true", help="Quiet stdout mode")
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).isoformat()
    selected_workloads = set(args.workloads.split(","))

    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "timestamp": timestamp,
        "hardware": {
            "platform": platform.platform(),
            "processor": _get_cpu_brand(),
            "python_version": platform.python_version(),
            "torch_version": torch.__version__,
            "mps_available": bool(torch.backends.mps.is_available()),
            "cuda_available": bool(torch.cuda.is_available()),
        },
        "workloads": {},
        "overall_status": "PASS",
    }

    if not args.quiet:
        print(f"=== MacBook Local Runtime Benchmark ({timestamp}) ===")
        print(f"Hardware: {receipt['hardware']['processor']} | MPS: {receipt['hardware']['mps_available']} | CUDA: {receipt['hardware']['cuda_available']}")

    if "embedding" in selected_workloads:
        receipt["workloads"]["bge_m3_embedding_mps"] = _safe_run_workload(
            benchmark_bge_m3_embedding, args.iterations, args.quiet
        )
    if "traversal" in selected_workloads:
        receipt["workloads"]["graph_sqlite_traversal"] = _safe_run_workload(
            benchmark_graph_sqlite_traversal, args.iterations, args.quiet
        )
    if "fusion" in selected_workloads:
        receipt["workloads"]["dense_hybrid_rrf_fusion"] = _safe_run_workload(
            benchmark_dense_hybrid_rrf_fusion, args.iterations, args.quiet
        )
    if "outreach" in selected_workloads:
        receipt["workloads"]["outreach_validation"] = _safe_run_workload(
            benchmark_outreach_validation, args.iterations, args.quiet
        )
    if "resume" in selected_workloads:
        receipt["workloads"]["deterministic_resume_pipeline"] = _safe_run_workload(
            benchmark_deterministic_resume_pipeline, min(args.iterations, 3), args.quiet
        )

    def _is_workload_passed(w: dict[str, Any]) -> bool:
        status = w.get("status")
        if status == "SKIPPED":
            return True
        if status != "PASS":
            return False
        leak_ok = bool(w.get("leak_gate_passed", False))
        drift_ok = bool(w.get("drift_gate_passed", False))
        return leak_ok and drift_ok

    has_workloads = len(receipt["workloads"]) > 0
    all_passed = has_workloads and all(
        _is_workload_passed(w) for w in receipt["workloads"].values()
    )
    receipt["overall_status"] = "PASS" if all_passed else "FAIL"

    # Save receipt
    receipt_dest = (
        Path(args.output_receipt)
        if args.output_receipt
        else REPO_ROOT / ".runtime" / "benchmarks" / f"macbook_runtime_receipt_{int(time.time())}_{os.getpid()}.json"
    )
    receipt_dest.parent.mkdir(parents=True, exist_ok=True)
    receipt_dest.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    if not args.quiet:
        print(f"\nBenchmark Receipt Written to: {receipt_dest}")
        print("\n| Workload | Cold (ms) | p50 (ms) | p90 (ms) | Drift | RSS Δ (MiB) | Status |")
        print("|---|---|---|---|---|---|---|")
        for name, data in receipt["workloads"].items():
            if data.get("status") == "SKIPPED":
                print(f"| {name} | - | - | - | - | - | SKIPPED |")
            elif data.get("status") == "ERROR":
                print(f"| {name} | ERROR | - | - | - | - | ERROR |")
            else:
                print(
                    f"| {name} | {data.get('cold_latency_ms')} | {data.get('p50')} | {data.get('p90')} | "
                    f"{data.get('drift_ratio')} | {data.get('rss_delta_mib')} | {data.get('status')} |"
                )
        print(f"\nOverall Result: {receipt['overall_status']}")
        failed_items = [
            (name, data)
            for name, data in receipt["workloads"].items()
            if not _is_workload_passed(data)
        ]
        if failed_items:
            print("\nGate Failure Diagnostics:")
            for name, data in failed_items:
                diag = []
                if data.get("status") == "ERROR":
                    diag.append(f"Crash: {data.get('error')}")
                elif data.get("status") == "WARN":
                    diag.append("Status is WARN")
                if not data.get("leak_gate_passed", False):
                    diag.append(f"Memory leak (RSS Δ={data.get('rss_delta_mib')} MiB, MPS Δ={data.get('mps_delta_mib', 0.0)} MiB)")
                if not data.get("drift_gate_passed", False):
                    diag.append(f"Latency drift (ratio={data.get('drift_ratio')}, delta={data.get('drift_delta_ms')} ms)")
                print(f"  - {name}: " + "; ".join(diag))

    return 0 if (not args.assert_gates or all_passed) else 1


if __name__ == "__main__":
    sys.exit(main())
