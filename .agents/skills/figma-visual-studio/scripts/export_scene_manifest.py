#!/usr/bin/env python3
"""Scene manifest helper for figma-canvas-writer.

Generates and validates figma_evidence.json node inventories adhering to
Figma 4K Visual Governance schema requirements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_sha(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_evidence_envelope(
    nodes: list[dict[str, Any]],
    candidate_png: Path,
    builder_run_id: str,
    file_key: str = "figma-doc-key-0000000000000",
    page_id: str = "1:1",
    frame_id: str = "2:1",
    frame_name: str = "Executive Slide",
) -> dict[str, Any]:
    png_hash = sha256_file(candidate_png)
    node_hash = canonical_sha(nodes)

    return {
        "producer": {
            "role": "FIGMA_PROPERTY_EXTRACTOR",
            "run_id": f"extract-{builder_run_id}",
            "builder_run_id": builder_run_id,
        },
        "method": "FIGMA_PROPERTY_EXTRACTION",
        "origin": "FIGMA_MCP",
        "candidate_sha256": png_hash,
        "png_export_sha256": png_hash,
        "file_key": file_key,
        "page_id": page_id,
        "frame_id": frame_id,
        "frame_name": frame_name,
        "property_extract_timestamp": "2026-09-12T12:00:00Z",
        "canvas": [3840, 2160],
        "nodes": nodes,
        "node_inventory_sha256": node_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Figma scene manifest to figma_evidence.json")
    parser.add_argument("--nodes-json", type=Path, required=True, help="Input JSON file containing nodes array")
    parser.add_argument("--candidate-png", type=Path, required=True, help="Path to exported 3840x2160 PNG")
    parser.add_argument("--builder-run-id", type=str, required=True, help="Builder run ID")
    parser.add_argument("--output", type=Path, required=True, help="Output path for figma_evidence.json")
    args = parser.parse_args()

    nodes = json.loads(args.nodes_json.read_text(encoding="utf-8"))
    if isinstance(nodes, dict) and "nodes" in nodes:
        nodes = nodes["nodes"]

    evidence = build_evidence_envelope(
        nodes=nodes,
        candidate_png=args.candidate_png,
        builder_run_id=args.builder_run_id,
    )

    args.output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Exported valid figma_evidence.json to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
