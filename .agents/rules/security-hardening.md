---
trigger: model_decision
---

# Security Hardening — stub

> On-demand when changing prod code / deps / logging (plan `always-on-rule-surface-cut-c7f3a1`); enforcement unchanged. No hardcoded secrets; no PII/secrets in logs (mask); CVE-scan new deps (Author-Gate); authz checks on sensitive ops (agent deletion, config/DB/schema). Detail: [`security-hardening`](../skills/security-hardening/SKILL.md) skill. Enforced: `lint_secrets.py` (T20), `lint_secrets.py`, `verify_commit.py`.
