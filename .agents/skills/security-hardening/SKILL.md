---
name: security-hardening
description: Pass security validation before commit by preventing hardcoded secrets, masking sensitive logs, vetting dependencies, and enforcing authorization gates.
---

# Security Hardening

Operationalizes security and credential hygiene across the repository. All production code changes must pass security validation before commit with zero bypass exceptions.

## 1. When to Invoke

- Modifying production code (`outreach_engine/`, `resume_graph_engine/`, `infrastructure/`, `agents/`).
- Adding or updating package dependencies in `requirements.txt` or `pyproject.toml`.
- Introducing or modifying log output statements.
- Touching authorization, token signing, or sensitive data paths.

## 2. Mandatory Security Rules

| Rule | Enforcement Tool / Mechanism | Failure Consequence |
| :--- | :--- | :--- |
| **No Hardcoded Secrets** | `tools/lint_secrets.py --all` | Pre-commit blocks commit |
| **No PII/Tokens in Logs** | Code review & sensitive string masking (`***` / `[REDACTED]`) | PR review rejection |
| **Vetted Dependencies** | Vulnerability scanning and explicit approval | Security block |
| **Authorization on Sensitive Ops** | `tools/hitl_governance.py` & `.agents/rules/hitl-decisions.md` | Pre-tool guard denial |
| **Zero Bypass Exceptions** | Tier 1 commit gate (`tools/verify_commit.py`) | Direct push / merge blocked |

## 3. Standard Security Procedure

1. **Scan for Secrets**:
   - Ensure credentials resolve only via `os.environ.get(...)` or configuration files, never inline string literals.
   - Placeholder tokens like `"test_api_key"` or `"YOUR_KEY_HERE"` are permitted only in tests or documentation.
2. **Audit Logging Output**:
   - Verify log lines contain no auth headers, bearer tokens, passwords, customer PII, or raw database connection strings.
3. **Dependency Assessment**:
   - Verify package integrity and license compatibility before introducing external libraries.
4. **Enforce Authorization Checks**:
   - Sensitive mutations (agent deletion, state wipe, production deployment, external publication) require Human-in-the-Loop authorization via `ask_question`.

## 4. Verification Commands

```bash
.venv/bin/python tools/lint_secrets.py --all
.venv/bin/python tools/verify_commit.py
```
