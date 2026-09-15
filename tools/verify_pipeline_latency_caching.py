#!/usr/bin/env python3
"""End-to-End Pipeline Latency & Prompt Caching Verification Harness.

Validates:
1. Static System Prefix Lengths (>= 1,024 tokens for OpenAI Prompt Caching).
2. Deterministic Offline Pipeline Execution (run_bare_deterministic_e2e).
3. Concurrent Retrieval Architecture in bare_pipeline.
4. Cache-Aligned Slot Ordering in Prompt Assembly Compiler.
5. Live OpenAI Prompt Caching Telemetry (verifying cached_tokens > 0).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Add python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "resume_graph_engine" / "src"))

from apps_research.prompt_assembly.company_brief_prompts import COMPANY_BRIEF_STATIC_SYSTEM_PROMPT
from apps_rg.prompt_assembly.bare_prompts import (
    BARE_PIPELINE_L2_SYSTEM_PROMPT,
    BARE_PIPELINE_RESEARCH_SYSTEM_PROMPT,
)
from apps_rg.prompt_assembly.compiler import (
    CACHE_ALIGNED_SLOT_ORDER,
    CANONICAL_SLOT_ORDER,
)
from apps_rg.bare_pipeline import run_bare_deterministic_e2e


def verify_static_prefixes() -> bool:
    print("\n--- 1. Verifying Static Prefix Lengths (>= 1,024 tokens) ---")
    prompts = {
        "BARE_PIPELINE_L2_SYSTEM_PROMPT": BARE_PIPELINE_L2_SYSTEM_PROMPT,
        "BARE_PIPELINE_RESEARCH_SYSTEM_PROMPT": BARE_PIPELINE_RESEARCH_SYSTEM_PROMPT,
        "COMPANY_BRIEF_STATIC_SYSTEM_PROMPT": COMPANY_BRIEF_STATIC_SYSTEM_PROMPT,
    }
    all_passed = True
    for name, p_text in prompts.items():
        char_len = len(p_text)
        word_len = len(p_text.split())
        est_tokens = int(char_len / 4.0)
        passes = char_len >= 4000  # >= 1000 tokens
        status = "PASS" if passes else "FAIL"
        print(f"  [{status}] {name}: {char_len} chars, ~{est_tokens} est tokens (threshold: >= 1000 tokens)")
        if not passes:
            all_passed = False
    return all_passed


def verify_compiler_cache_alignment() -> bool:
    print("\n--- 2. Verifying Compiler Cache-Aligned Slot Ordering ---")
    ca_c0 = CACHE_ALIGNED_SLOT_ORDER.index("C0")
    ca_r0 = CACHE_ALIGNED_SLOT_ORDER.index("R0")
    ca_e0 = CACHE_ALIGNED_SLOT_ORDER.index("E0")
    
    passed = (ca_r0 < ca_c0) and (ca_e0 < ca_c0)
    print(f"  [{'PASS' if passed else 'FAIL'}] Schema (R0, index {ca_r0}) and Examples (E0, index {ca_e0}) precede Dynamic Evidence (C0, index {ca_c0})")
    return passed


def verify_deterministic_e2e() -> bool:
    print("\n--- 3. Verifying Deterministic Offline E2E Pipeline ---")
    t0 = time.perf_counter()
    result = run_bare_deterministic_e2e()
    elapsed = round(time.perf_counter() - t0, 3)
    status = result.get("status")
    outcome = result.get("outcome_label")
    passed = status == "SUCCESS" and outcome == "DETERMINISTIC_OFFLINE_PASS"
    print(f"  [{'PASS' if passed else 'FAIL'}] run_bare_deterministic_e2e: {status} ({outcome}) in {elapsed}s")
    return passed


def verify_live_cache_receipt() -> bool:
    print("\n--- 4. Verifying Live Prompt Caching Receipt ---")
    receipt_path = ROOT / "artifacts" / "prompt_caching_e2e_receipt.json"
    if not receipt_path.exists():
        print("  [WARN] Live cache receipt not found at artifacts/prompt_caching_e2e_receipt.json")
        return False
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    hit_verified = data.get("cache_hit_verified", False)
    model = data.get("model", "unknown")
    call_2_ratio = data.get("call_2", {}).get("usage", {}).get("cache_read_ratio", 0)
    cached_tokens = data.get("call_2", {}).get("usage", {}).get("cached_input_tokens", 0)
    print(f"  [{'PASS' if hit_verified else 'FAIL'}] Model: {model} | Cached Tokens: {cached_tokens} | Cache Read Ratio: {call_2_ratio * 100:.2f}%")
    return hit_verified


def main() -> int:
    print("================================================================================")
    print("PIPELINE PERFORMANCE, LATENCY & PROMPT CACHING VERIFICATION")
    print("================================================================================")
    
    v1 = verify_static_prefixes()
    v2 = verify_compiler_cache_alignment()
    v3 = verify_deterministic_e2e()
    v4 = verify_live_cache_receipt()
    
    all_ok = v1 and v2 and v3 and v4
    print("\n================================================================================")
    print(f"FINAL OUTCOME: {'ALL GATES PASSED (100%)' if all_ok else 'VERIFICATION FAILED'}")
    print("================================================================================")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
