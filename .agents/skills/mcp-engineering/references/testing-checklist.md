# MCP testing checklist

- Target version behavior is explicit.
- Server discovery/capability catalog matches implementation.
- Tool input validation rejects malformed or excessive input.
- Tool authorization prevents unauthorized side effects.
- Resource access respects identity, scope, freshness, and size limits.
- Destructive tools require the intended approval/policy control.
- Retry behavior does not duplicate non-idempotent side effects.
- Gateway/routing headers and metadata are validated for the target version.
- Current authorization error paths work.
- Extension required/optional behavior works.
- Compatibility tests cover every supported protocol version.
- Older clients cannot silently force insecure or semantically degraded behavior.
