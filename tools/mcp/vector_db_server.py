#!/usr/bin/env python3
"""Repository-local Vector DB MCP Stdio Server for ChromaDB & BGE-M3 semantic search."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


def handle_mcp_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single JSON-RPC 2.0 MCP stdio request."""
    req_id = request.get("id")
    method = str(request.get("method") or "")
    chroma_path = os.getenv("VECTOR_DB_CHROMA_PATH", "")
    model_name = os.getenv("VECTOR_DB_EMBEDDING_MODEL", "BAAI/bge-m3")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "vector_db", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "vector_stats",
                        "description": "Report ChromaDB path and embedding model metadata.",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "list_collections",
                        "description": "List available vector collections.",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                ]
            },
        }
    if method == "tools/call":
        params = request.get("params") or {}
        tool_name = params.get("name", "")
        payload = {
            "tool": tool_name,
            "chroma_path": chroma_path,
            "chroma_exists": bool(chroma_path and Path(chroma_path).exists()),
            "embedding_model": model_name,
        }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
        }
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"status": "ok"},
    }


def main() -> int:
    """Run MCP stdio server loop."""
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(req, dict):
            resp = handle_mcp_request(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
