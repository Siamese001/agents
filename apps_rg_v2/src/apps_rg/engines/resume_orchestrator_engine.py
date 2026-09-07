"""Receipt-backed legacy adapter for the governed Apps RG whole-run spine.

``ResumeOrchestratorEngine`` remains as a compatibility entrypoint for older
scripts, but it is no longer an execution façade.  It performs the local
anti-overfit guard then delegates to the canonical product entrypoint, which
owns preflight, U0, L1, L0, C0, L2, and Exit.  No synthetic hop values,
quality scores, or success states are emitted here.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Mapping
from typing import Any


def _flatten_artifact(artifact: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append(str(artifact.get("headline", "") or ""))
    parts.append(str(artifact.get("summary", "") or ""))
    for row in artifact.get("experience") or []:
        if not isinstance(row, dict):
            continue
        parts.append(str(row.get("company", "") or ""))
        parts.append(str(row.get("title", "") or ""))
        for b in row.get("bullets") or []:
            parts.append(str(b))
    for sk in artifact.get("skills") or []:
        parts.append(str(sk))
    return " ".join(parts)


def _token_set(text: str) -> set[str]:
    return {m.group(0).lower() for m in re.finditer(r"[A-Za-z]{4,}", text)}


def _mimicry_max(score_text: str, jd: str) -> float:
    a, b = _token_set(score_text), _token_set(jd or "")
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / max(len(a), 1)


def _fake_history_blob(blob_l: str) -> bool:
    # Fabricated interviewer-style memory cues + first-person past interaction.
    if "as we discussed" in blob_l and ("last week" in blob_l or "yesterday" in blob_l):
        return True
    if "we talked about" in blob_l and ("before" in blob_l or "already" in blob_l):
        return True
    if "talked about this before" in blob_l:
        return True
    if "discussed" in blob_l and "as promised" in blob_l and " i " in blob_l.replace("\n", " "):
        return True
    return False


class ResumeOrchestratorEngine:
    """Legacy adapter that delegates execution to the governed product spine."""

    def __init__(
        self,
        ctx: Any,
        *,
        logger: logging.Logger | None = None,
        product_runner: Callable[..., Mapping[str, Any]] | None = None,
    ):
        self.ctx = ctx
        self.logger = logger or logging.getLogger(__name__)
        self._product_runner = product_runner

    def _resume_to_overfit_artifact(self) -> dict[str, Any]:
        m = getattr(self.ctx, "master_resume", {}) or {}
        headline = ""
        ci = m.get("contact_info")
        if isinstance(ci, dict):
            headline = str(ci.get("title") or ci.get("name") or "").strip()
        return {
            "headline": str(m.get("headline") or headline or ""),
            "summary": str(m.get("summary") or ""),
            "experience": list(m.get("experience") or []),
            "skills": list(m.get("skills") or []),
        }

    def _run_anti_overfit_check(self, artifact: dict[str, Any], jd: str) -> dict[str, Any]:
        flags: list[str] = []
        blob = _flatten_artifact(artifact)
        blob_l = blob.lower()
        jd_l = (jd or "").lower()

        score = 0.0

        if _fake_history_blob(blob_l):
            flags.append("fake_history_detected")
            score += 4.0

        mim = _mimicry_max(blob + " " + jd_l, jd_l)
        mimicry_floor = getattr(self, "_MIMICRY_MAX_CALIBRATED", 0.85)
        if mim >= mimicry_floor:
            flags.append("mimicry_max_breach")
            score += 1.2

        # Soft emotional stuffing (kept narrow so clean resumes rarely trip it).
        if re.search(r"\b(thrilled beyond words|so excited to collaborate again)\b", blob_l):
            flags.append("forced_warmth_detected")
            score += 2.5

        escalate = "fake_history_detected" in flags or "forced_warmth_detected" in flags
        warning = bool(score >= 2.0 and not escalate)

        return {
            "score": float(score),
            "flags": flags,
            "warning": warning,
            "escalate": escalate,
        }

    def _context_value(self, *names: str) -> str:
        """Read explicitly supplied legacy context without inferring new inputs."""

        master_resume = getattr(self.ctx, "master_resume", {}) or {}
        for name in names:
            value = getattr(self.ctx, name, None)
            if value is None and isinstance(master_resume, Mapping):
                value = master_resume.get(name)
            normalized = str(value or "").strip()
            if normalized:
                return normalized
        return ""

    def _source_resume_text(self) -> str:
        supplied = self._context_value("source_resume_text", "resume_text")
        if supplied:
            return supplied
        master_resume = getattr(self.ctx, "master_resume", {}) or {}
        if not isinstance(master_resume, Mapping) or not master_resume:
            return ""
        # The legacy context itself is the user-supplied resume source.  A
        # deterministic representation preserves it for U0 without fabricating
        # a résumé summary or score.
        import json

        return json.dumps(master_resume, ensure_ascii=False, sort_keys=True)

    def _governed_inputs(self, jd: str) -> tuple[dict[str, str], list[str]]:
        jd_text = str(jd or "").strip() or self._context_value(
            "job_description_text", "jd_text"
        )
        inputs = {
            "target_company": self._context_value("target_company", "company_name"),
            "target_role": self._context_value("target_role", "job_title", "role"),
            "target_level": self._context_value("target_level"),
            "jd": jd_text,
            "job_description_ref": self._context_value("job_description_ref", "jd_ref"),
            "job_description_text": jd_text,
            "manual_brief": self._context_value("manual_brief", "manual_brief_path"),
            "resume_path": self._context_value("resume_path", "source_resume_ref"),
            "source_resume_text": self._source_resume_text(),
            "generation_mode": self._context_value("generation_mode")
            or "strategic_tailor",
            "artifact_dir": self._context_value("artifact_dir"),
        }
        missing = [
            field
            for field in ("target_company", "target_role")
            if not inputs[field]
        ]
        if not inputs["jd"] and not inputs["job_description_ref"]:
            missing.append("job_description_text_or_ref")
        return inputs, missing

    @staticmethod
    def _actual_receipt_refs(result: Mapping[str, Any]) -> list[str]:
        refs: list[str] = []
        for key in (
            "artifact_dir",
            "spine_run_manifest",
            "terminal_manifest_ref",
            "pipeline_completion_receipt_ref",
            "mandatory_run_output_json",
        ):
            value = str(result.get(key) or "").strip()
            if value and value not in refs:
                refs.append(value)
        return refs

    def _write_governed_receipt(self, receipt: Mapping[str, Any]) -> None:
        buffer = getattr(self.ctx, "buffer", None)
        write = getattr(buffer, "write", None)
        if callable(write):
            write("governed_run_receipt", dict(receipt))

    def _run_product_spine(self, inputs: Mapping[str, str]) -> Mapping[str, Any]:
        if self._product_runner is not None:
            result = self._product_runner(**dict(inputs))
        else:
            from apps_rg.runtime.product_entry import run_product_whole_run_from_primitives

            result = run_product_whole_run_from_primitives(**dict(inputs))
        if not isinstance(result, Mapping):
            raise TypeError("governed Apps RG product runner returned a non-mapping result")
        return result

    async def execute(self, jd: str) -> dict[str, Any]:
        """Run the canonical product spine or return a fail-closed adapter receipt."""

        inputs, missing_inputs = self._governed_inputs(jd)
        overfit = self._run_anti_overfit_check(
            self._resume_to_overfit_artifact(), inputs["jd"]
        )

        if missing_inputs:
            receipt = {
                "status": "BLOCKED_INPUT",
                "execution_status": "not_started",
                "outcome_authorized": False,
                "product_authorized": False,
                "pipeline_complete": False,
                "missing_inputs": missing_inputs,
                "overfit": overfit,
                "checkpoints": ["legacy_adapter_input_gate"],
                "receipt_refs": [],
            }
            self._write_governed_receipt(receipt)
            return receipt

        if overfit["escalate"]:
            receipt = {
                "status": "ESCALATED_OVERFIT",
                "execution_status": "blocked",
                "outcome_authorized": False,
                "product_authorized": False,
                "pipeline_complete": False,
                "overfit": overfit,
                "checkpoints": ["anti_overfit_gate"],
                "receipt_refs": [],
            }
            self._write_governed_receipt(receipt)
            return receipt

        try:
            result = await asyncio.to_thread(self._run_product_spine, inputs)
        except Exception as exc:  # guardian: legacy adapter must return a sealed failure receipt
            self.logger.exception("governed Apps RG product spine failed")
            receipt = {
                "status": "EXECUTION_ERROR",
                "execution_status": "failed",
                "outcome_authorized": False,
                "product_authorized": False,
                "pipeline_complete": False,
                "overfit": overfit,
                "checkpoints": ["governed_product_spine"],
                "receipt_refs": [],
                "error_type": type(exc).__name__,
                "error_message": " ".join(str(exc).split()),
            }
            self._write_governed_receipt(receipt)
            return receipt

        product_authorized = result.get("product_authorized") is True
        outcome_authorized = result.get("outcome_authorized") is True
        pipeline_complete = result.get("pipeline_complete") is True
        receipt = {
            "status": (
                "COMPLETE"
                if product_authorized and outcome_authorized and pipeline_complete
                else "BLOCKED"
            ),
            "execution_status": str(result.get("execution_status") or "unknown"),
            "exit_status": str(result.get("exit_status") or "unknown"),
            "outcome_authorized": outcome_authorized,
            "product_authorized": product_authorized,
            "pipeline_complete": pipeline_complete,
            "overfit": overfit,
            "checkpoints": ["governed_product_spine"],
            "receipt_refs": self._actual_receipt_refs(result),
            "governed_result": dict(result),
        }
        self._write_governed_receipt(receipt)
        return receipt
