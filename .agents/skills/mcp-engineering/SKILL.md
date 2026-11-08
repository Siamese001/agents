---
name: mcp-engineering
description: Design, implement, test, and migrate Model Context Protocol (MCP) servers, clients, tools, resources, and transports. Use for capability exposure and tool schemas.
---

# MCP Engineering

Engineer MCP as a capability boundary for AI applications and agents. Keep tool/resource access distinct from peer agent collaboration.

## Required workflow

1. Identify the MCP host/AI application, server ownership, target capabilities, trust boundary, and deployment topology.
2. Verify the current official MCP specification before making version-specific claims. Read `references/protocol-baseline.md`.
3. Decide which capabilities belong in MCP and which belong in A2A, direct APIs, events, or ordinary application services.
4. Model tools, resources, prompts, and extensions explicitly rather than exposing a generic "agent API" through MCP.
5. Create `mcp-design.json` using `references/design-contract.md`.
6. Validate with `scripts/validate_mcp_design.py`.
7. Define authorization, user delegation, scopes, approval behavior, gateway controls, audit, and downstream credentials.
8. Define version handling and migration behavior for older clients/servers.
9. Implement with a current official SDK when practical and verify package/API details against current documentation.
10. Test contract, policy, failure, and compatibility behavior before production use.

## MCP vs A2A rule

Use MCP primarily for an AI application or agent to access capabilities such as tools, resources, prompts, and protocol extensions.

Use A2A primarily for collaboration between independent agentic applications.

Do not model every network call as MCP. Do not make an ordinary tool an A2A agent just to obtain dynamic routing.

## Current-generation MCP rules

MCP changed materially in 2026. Do not copy older session-oriented examples without checking the target version.

For a target version that uses a stateless core:
- do not invent session dependence that the protocol no longer requires;
- make each request self-describing as required by that version;
- use current discovery and routing conventions;
- treat long-running work through the applicable current extension model;
- implement the current authorization profile rather than obsolete flows.

For older supported versions, isolate compatibility code and document the migration boundary.

## Capability design

### Tools
Use tools for actions or computations. Define:
- stable names;
- precise descriptions;
- bounded input schemas;
- output schemas when supported/appropriate;
- side-effect classification;
- authorization scope;
- idempotency/retry behavior;
- approval requirements for destructive or high-impact actions;
- error semantics.

Do not create one mega-tool with a free-form command parameter when a small, typed capability surface is possible.

### Resources
Use resources for application-controlled contextual data. Define URI conventions, access policy, freshness, provenance, pagination/size handling, and caching behavior.

### Prompts
Use prompts for reusable interaction templates only when MCP prompt semantics are genuinely useful. Do not use prompts as hidden policy enforcement.

### Extensions
Use extensions deliberately. Record extension URI/version, required-vs-optional behavior, fallback, and compatibility impact.

## Security and authorization

Separate host trust from server authorization.

For remote production servers:
- use current MCP authorization standards;
- validate issuer/resource/audience as required by the target version;
- scope access to the smallest useful capability set;
- preserve user-vs-service authority;
- prevent token forwarding to unintended downstream services;
- avoid tool descriptions or resource metadata that leak sensitive internals;
- audit high-impact calls with correlation to the invoking agent/user.

## Output contract

Produce as applicable:
- `mcp-design.json`;
- tool/resource/prompt catalog;
- server/client implementation skeleton;
- authorization and scope matrix;
- migration plan for older MCP versions;
- MCP contract test plan;
- architecture/sequence source through `mermaid-architecture` when available.

## Blocking failures

Do not mark production-ready when:
- target MCP version is unknown;
- an older lifecycle/session model is assumed against a newer stateless target;
- tool schemas are unbounded or ambiguous;
- destructive operations lack explicit policy/approval treatment;
- authentication and downstream authorization are conflated;
- MCP is used as a synonym for arbitrary REST/network traffic;
- an independent peer agent collaboration is forced through MCP without rationale;
- current protocol behavior is asserted without official-source verification.
