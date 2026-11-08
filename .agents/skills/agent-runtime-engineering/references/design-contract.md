# Runtime design contract

```json
{
  "agent_id": "...",
  "goal": "...",
  "pattern": "deterministic-agentic|supervisor-worker|planner-executor|peer-mesh|parallel-reducer|event-driven",
  "authority": {"tools": [], "delegation_targets": [], "subdelegation": false},
  "state": {"owner": "...", "durability": "...", "concurrency": "..."},
  "loop": {"observe": "...", "decide": "...", "act": "...", "evaluate": "..."},
  "termination": {"success": "...", "failure": "...", "max_steps": 20},
  "budgets": {"time": "...", "cost": "...", "tool_calls": 20, "delegation_depth": 2},
  "resilience": {"timeouts": "...", "retries": "...", "idempotency": "...", "compensation": "..."},
  "human_control": {"approvals": [], "escalations": []},
  "observability": {"correlation": "...", "events": []},
  "open_decisions": []
}
```
