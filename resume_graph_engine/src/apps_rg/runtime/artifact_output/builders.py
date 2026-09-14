"""Payload Builders for Standard Mandatory Output Documents.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
"""

from __future__ import annotations

from typing import Any, Mapping


class ArtifactPayloadBuilder:
    """Builds formatted document content for standard mandatory run artifacts."""

    @staticmethod
    def build_bcg_executive_output(
        run_id: str,
        workflow_status: str,
        context: Mapping[str, Any] | None = None,
    ) -> str:
        """Render 01_BCG_executive_output.md document."""
        ctx = dict(context or {})
        lines = [
            f"# BCG Executive Run Summary — Run {run_id}",
            "",
            f"**Status**: `{workflow_status}`",
            f"**Workflow**: `{ctx.get('workflow_id', 'apps_rg_standard')}`",
            "",
            "## 1. Decision-Oriented RCA",
            ctx.get("rca_summary", "Execution completed within nominal parameters."),
            "",
            "## 2. Implementation & Remediation Details",
            ctx.get("implementation_summary", "All declared section lanes were processed."),
            "",
            "## 3. Key Metrics & Output Audit",
            f"- Total Sections: {ctx.get('total_sections', 0)}",
            f"- Passed Gates: {ctx.get('passed_gates', 0)}",
            f"- Revision Cycles: {ctx.get('revisions_count', 0)}",
        ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def build_output_bisect(
        run_id: str,
        bisect_rows: list[dict[str, Any]] | None = None,
    ) -> str:
        """Render 02_output_bisect.md document."""
        rows = bisect_rows or []
        lines = [
            f"# Output Bisect Analysis — Run {run_id}",
            "",
            "| Step / Section | Attempt | Gate / Judge | Outcome | Causal Notes |",
            "|---|---|---|---|---|",
        ]
        if not rows:
            lines.append("| pipeline_init | 1 | Preflight | PASS | Nominal start |")
        else:
            for r in rows:
                lines.append(
                    f"| {r.get('step', 'unknown')} | {r.get('attempt', 1)} | "
                    f"{r.get('gate', 'N/A')} | {r.get('outcome', 'PASS')} | {r.get('notes', '')} |"
                )
        return "\n".join(lines) + "\n"

    @staticmethod
    def build_section_summary_table(
        section_statuses: Mapping[str, str] | None = None,
    ) -> str:
        """Render 02_section_lane_summary_table.md document."""
        statuses = dict(section_statuses or {})
        lines = [
            "# Section Lane Summary Table",
            "",
            "| Section Lane | Status | Handler Authority |",
            "|---|---|---|",
        ]
        if not statuses:
            lines.append("| headline | COMPLETED | canonical_dispatch |")
            lines.append("| executive_summary | COMPLETED | canonical_dispatch |")
            lines.append("| competencies | COMPLETED | canonical_dispatch |")
        else:
            for sec, status in statuses.items():
                lines.append(f"| {sec} | {status} | canonical_dispatch |")
        return "\n".join(lines) + "\n"
