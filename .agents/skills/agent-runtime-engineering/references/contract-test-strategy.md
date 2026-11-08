# Contract test strategy

Use a real protocol parser/SDK in at least one side of interoperability tests when possible.

Keep golden fixtures for Agent Cards, tool schemas, protocol envelopes, artifacts, errors, and version negotiation cases.

Treat compatibility as directional: client-new/server-old can differ from client-old/server-new.

For non-idempotent operations, assert both response semantics and downstream side-effect count.

For asynchronous work, test polling/stream/reconnect from intermediate states rather than only completed tasks.

For security, test authenticated-but-unauthorized callers, expired credentials, wrong audience/resource, and delegated-scope narrowing.
