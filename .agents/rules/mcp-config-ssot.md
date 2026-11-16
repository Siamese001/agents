---
trigger: model_decision
---

# MCP Config SSOT — stub

> On-demand when editing MCP config; enforcement unchanged. `.mcp.json` (mirrored in `.agents/mcp_config.json`, native `mcpServers` format) is the repo-local MCP SSOT — strict JSON, `${VAR}` for secrets, stable server IDs, and verified local stdio target scripts (`tools/mcp/vector_db_server.py`). Detail: [`mcp-engineering`](../skills/mcp-engineering/SKILL.md) skill. Enforced by `tools/ssot_boundary_auditor.py` and `tools/ssot_sprawl_scanner.py`.
