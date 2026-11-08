# Runtime patterns

## Deterministic workflow with agentic nodes
Use when process order is known but selected steps benefit from reasoning.

## Supervisor and workers
Use when dynamic decomposition/routing is useful. Centralizes coordination but can create bottlenecks and a large trust boundary.

## Planner and executor
Use when planning can be evaluated before execution. Useful for expensive or high-impact work.

## Peer mesh
Use when agents have independent capabilities and collaboration cannot be reduced to a fixed route. Requires stronger identity, protocol, loop, and observability controls.

## Parallel specialists and reducer
Use when subtasks are independent enough for concurrent execution and merge/conflict rules are explicit.

## Event-driven agents
Use when work is triggered by durable events and asynchronous continuation is central. Separate event delivery semantics from agent reasoning semantics.
