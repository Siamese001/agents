# MCP PyTest Enforcement

> On-demand when changing MCP-server code (plan `always-on-rule-surface-cut-c7f3a1`); enforcement unchanged. All MCP-server changes (`tools/*/mcp/`, MCP clients) pass pytest pre-commit — unit + integration + health + error-path (timeout / conn-fail / hung-process) for every `@mcp.tool`. Detail: [`testing-framework`](../skills/testing-framework/SKILL.md) skill.
