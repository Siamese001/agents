"""Precision audit logger with cryptographic chain of custody."""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime, timedelta
from typing import Any

from .types import PrecisionAuditLog

logger = logging.getLogger(__name__)


class PrecisionAuditLogger:
    """Precision audit logger with cryptographic chain of custody."""

    def __init__(self) -> None:
        self.audit_logs: deque = deque(maxlen=10000)  # Keep last 10,000 logs
        self.log_chain: list[PrecisionAuditLog] = []
        self.current_hash = ""
        self.audit_metrics = {
            "total_logs": 0,
            "logs_per_hour": 0,
            "security_events": 0,
            "compliance_violations": 0,
        }

    def log_event(
        self,
        event_type: str,
        user_id: str,
        session_id: str,
        action: str,
        resource: str,
        outcome: str,
        details: dict[str, Any] | None = None,
    ) -> str:
        """Log security event with cryptographic chain."""
        log_id = f"audit_{uuid.uuid4().hex}"

        audit_log = PrecisionAuditLog(
            log_id=log_id,
            timestamp=datetime.now(),
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            action=action,
            resource=resource,
            outcome=outcome,
            details=details or {},
            previous_log_hash=self.current_hash,
        )

        # Add to chain
        self.log_chain.append(audit_log)
        self.current_hash = audit_log.log_hash
        self.audit_logs.append(audit_log)

        # Update metrics
        self.audit_metrics["total_logs"] += 1

        if event_type in ["security_breach", "unauthorized_access", "privilege_escalation"]:
            self.audit_metrics["security_events"] += 1

        if event_type in ["gdpr_violation", "hipaa_violation", "pci_violation"]:
            self.audit_metrics["compliance_violations"] += 1

        return log_id

    def verify_audit_chain(self) -> bool:
        """Verify integrity of audit log chain."""
        for i in range(1, len(self.log_chain)):
            current_log = self.log_chain[i]
            previous_log = self.log_chain[i - 1]

            if not current_log.verify_chain_integrity(previous_log.log_hash):
                logger.error(f"Audit chain broken at log {current_log.log_id}")
                return False

        return True

    def query_logs(self, filters: dict[str, Any] | None = None, limit: int = 100) -> list[PrecisionAuditLog]:
        """Query audit logs with filters."""
        filtered_logs = list(self.log_chain)

        if filters:
            if "user_id" in filters:
                filtered_logs = [log for log in filtered_logs if log.user_id == filters["user_id"]]

            if "event_type" in filters:
                filtered_logs = [log for log in filtered_logs if log.event_type == filters["event_type"]]

            if "start_time" in filters:
                start_time = filters["start_time"]
                if isinstance(start_time, str):
                    start_time = datetime.fromisoformat(start_time)
                filtered_logs = [log for log in filtered_logs if log.timestamp >= start_time]

            if "end_time" in filters:
                end_time = filters["end_time"]
                if isinstance(end_time, str):
                    end_time = datetime.fromisoformat(end_time)
                filtered_logs = [log for log in filtered_logs if log.timestamp <= end_time]

        # Return most recent logs
        filtered_logs.sort(key=lambda x: x.timestamp, reverse=True)
        return filtered_logs[:limit]

    def get_audit_metrics(self) -> dict[str, Any]:
        """Get audit logging metrics."""
        # Calculate logs per hour
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        recent_logs = [log for log in self.log_chain if log.timestamp >= one_hour_ago]
        self.audit_metrics["logs_per_hour"] = len(recent_logs)

        return {
            "total_logs": len(self.log_chain),
            "chain_integrity": self.verify_audit_chain(),
            "metrics": self.audit_metrics,
            "oldest_log": self.log_chain[0].timestamp.isoformat() if self.log_chain else None,
            "newest_log": self.log_chain[-1].timestamp.isoformat() if self.log_chain else None,
        }


__all__ = ["PrecisionAuditLogger"]
