# MCP protocol baseline

This file records the verification baseline as of 2026-08-11. Re-check official sources for current behavior before version-specific implementation.

The official MCP project announced specification version 2026-07-28 on 2026-07-28. The release materially changed the protocol compared with the 2025 generation, including a stateless protocol core, self-describing requests, optional server discovery, header-based routing, Multi Round-Trip Requests, a formal extensions framework, authorization hardening, and updated SDKs.

Important migration implication:
- Do not assume the older initialize/initialized handshake, protocol-level session identifier, or session-affinity architecture when targeting 2026-07-28.
- Keep compatibility behavior explicit if supporting 2025-era clients or servers.

Official sources:
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://modelcontextprotocol.io/
- https://github.com/modelcontextprotocol

Before generating code, verify the current specification page and current SDK documentation because official docs and SDK APIs may evolve after this baseline.
