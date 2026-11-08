# MCP design contract

Create `mcp-design.json` with this minimum structure:

```json
{
  "protocol": "mcp",
  "target_version": "current-official-version",
  "environment": "development|test|production",
  "host": {"id": "...", "owner": "..."},
  "server": {"id": "...", "owner": "...", "remote": true},
  "transport": {"kind": "...", "endpoint": "..."},
  "capabilities": {
    "tools": [],
    "resources": [],
    "prompts": [],
    "extensions": []
  },
  "security": {
    "authentication": "...",
    "authorization": "...",
    "user_delegation": "...",
    "scopes": [],
    "approval_policy": "..."
  },
  "routing_and_scale": {"stateless": true, "gateway": "...", "caching": "..."},
  "resilience": {"timeouts": "...", "retries": "...", "idempotency": "..."},
  "observability": {"correlation": "...", "audit": "..."},
  "compatibility": {"supported_versions": [], "fallback": "explicit|none"},
  "open_decisions": []
}
```
