# State and memory design contract

```json
{
  "system": "...",
  "stores": [{"id": "...", "role": "task-state|conversation|working|user-memory|episodic|knowledge|evidence|guidance", "owner": "...", "durability": "...", "sensitivity": "..."}],
  "write_policies": [{"store": "...", "writers": [], "qualification": "...", "dedupe": "...", "conflict": "..."}],
  "read_policies": [{"store": "...", "readers": [], "scope": "...", "retrieval": "..."}],
  "provenance": {"required_roles": [], "fact_promotion": "human-governed"},
  "isolation": {"tenant": "...", "user": "...", "task": "..."},
  "retention": {"ttl": "...", "deletion": "...", "legal_hold": "..."},
  "concurrency": {"model": "...", "versioning": "..."},
  "open_decisions": []
}
```
