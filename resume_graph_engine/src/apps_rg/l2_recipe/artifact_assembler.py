"""Artifact Assembler for modular resume generation.

Handles:
- Writing JSON artifacts.
- Synthetic Phase 0 lane bundles and rollups.
- Deterministic locked copy generation.
- Modular final resume assembly (structural vs. full review).
- RG output merging from section references.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps_rg.l2_recipe.modular_rg_output_builder import (
    build_rg_output_from_modular_sections,
    load_lane_l2_from_section_refs,
)
from apps_rg.runtime.assembly.final_resume_manifest import FinalResumePaths
from apps_rg.runtime.env_bootstrap import temporary_env_override
from apps_rg.runtime.internal.final_resume_assembler import assemble_final_resume
from apps_rg.runtime.internal.generated_lane_rollup import (
    GENERATED_LANES,
    build_modular_lane_rollup,
)
from apps_rg.runtime.internal.locked_copy_builder import build_locked_copy
from apps_rg.runtime.resume_resolution import load_lane_base_resume_json
from apps_rg.runtime.section_execution_plan import BULLET_LANES, NARRATIVE_LANES
from apps_rg.runtime.section_judge_policy import REQUIRED_JUDGE_PROVIDER_KEYS
from apps_rg.runtime.spine.section_x3_finalize import FINAL_MATERIALIZED_ACCEPTANCE_CONTRACT

_PLUMBING_ASSEMBLY_PROVIDERS = frozenset({"mock", "mocked", "stub"})


class ArtifactAssembler:
    """Encapsulates artifact compilation, synthetic rollup, locked copy, and final merge."""

    @staticmethod
    def write_json(path: Path, data: Any) -> None:
        """Write a formatted JSON artifact ensuring parent directories exist."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def rel_under_repo(path: Path, repo: Path) -> str:
        """Return relative path under repo root, or fallback string."""
        try:
            return path.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            return str(path.resolve()).replace("\\", "/")

    @staticmethod
    def minimal_judge_blob() -> dict[str, Any]:
        """Generate a minimal judge output blob for synthetic phase 0."""
        return {
            "judges": [
                {"provider_key": provider_key, "provider_status": "OK", "pass": True}
                for provider_key in REQUIRED_JUDGE_PROVIDER_KEYS
            ],
        }

    @staticmethod
    def minimal_x2_blob() -> dict[str, Any]:
        """Generate a minimal X2 gate output blob for synthetic phase 0."""
        return {
            "gate_family": "lane_x2_phase0_synthetic",
            "gates": [{"gate_id": "phase0_stub", "pass": True}],
            "x2_passed": 1,
            "x2_failed": 0,
            "total_x2_gates": 1,
            "failed_gates": [],
        }

    @staticmethod
    def minimal_l2_blob(lane: str, *, run_id: str) -> dict[str, Any]:
        """Generate a minimal L2 section output blob for synthetic phase 0."""
        from apps_rg.runtime.live_judge_only_guard import is_test_harness

        if not is_test_harness() and os.environ.get("APPS_RG_PRODUCTION_RUN", "").strip() == "1":
            from apps_rg.runtime.providers.provider_run_mode import AppsRgEnvelopeProviderResolutionError

            raise AppsRgEnvelopeProviderResolutionError(
                f"LIVE_REQUIRED_ENFORCEMENT: Synthetic phase0 minimal_l2_blob for lane={lane!r} is forbidden in production runtime"
            )

        common = {
            "run_id": run_id,
            "section_id": lane,
            "runtime_generation_status": "MOCKED",
            "product_quality_status": "PHASE0_SYNTHETIC",
        }
        if lane == "headline":
            return {**common, "headline_line": "Phase0 synthetic headline | R4 modular readiness"}
        if lane == "executive_summary":
            return {
                **common,
                "resume_display_text": (
                    "Phase0 synthetic executive summary for modular R4 API readiness proof only."
                ),
            }
        if lane in NARRATIVE_LANES:
            return {
                **common,
                "narrative_sentence": (
                    "Phase0 synthetic narrative sentence with sufficient length for assembly proof."
                ),
            }
        if lane in BULLET_LANES:
            return {
                **common,
                "bullets": [
                    {
                        "text": (
                            "Phase0 synthetic achievement bullet with enough characters for deterministic "
                            "merge and assembler gates."
                        ),
                        "source_fact_id": "phase0_synthetic",
                        "has_metric": False,
                    },
                    {
                        "text": (
                            "Second Phase0 bullet text to satisfy multi-bullet structural expectations "
                            "where applicable."
                        ),
                        "source_fact_id": "phase0_synthetic",
                        "has_metric": False,
                    },
                    {
                        "text": (
                            "Third Phase0 bullet text so list-based sections have minimal depth."
                        ),
                        "source_fact_id": "phase0_synthetic",
                        "has_metric": False,
                    },
                ],
            }
        if lane == "competencies":
            return {
                **common,
                "competencies": [
                    {
                        "category_label": "Phase0 Synthetic",
                        "terms": [{"text": "modular readiness", "source_fact_id": "phase0_synthetic"}],
                        "source_fact_ids": ["phase0_synthetic"],
                    },
                ],
            }
        return common

    @classmethod
    def write_synthetic_lane_bundle(cls, repo: Path, modular_root: Path, lane: str) -> str:
        """Write synthetic lane bundle on disk and return relative run path."""
        run_id = f"phase0_{lane}_synthetic"
        run_dir = modular_root / "lanes" / lane / "real" / "phase0_synthetic"
        run_dir.mkdir(parents=True, exist_ok=True)
        cls.write_json(run_dir / "l2_output.json", cls.minimal_l2_blob(lane, run_id=run_id))
        cls.write_json(run_dir / "x2_gate_outputs.json", cls.minimal_x2_blob())
        cls.write_json(run_dir / "x1d_llm_judge_outputs.json", cls.minimal_judge_blob())
        cls.write_json(
            run_dir / FINAL_MATERIALIZED_ACCEPTANCE_CONTRACT,
            {
                "schema_version": "apps_rg.final_materialized_acceptance_contract.v1",
                "section_id": lane,
                "gate_id": "x3_final_materialized_acceptance_contract",
                "pass": True,
                "x2_final_materialized_binding_pass": True,
                "phase0_synthetic": True,
                "authorization_scope": "PHASE0_SYNTHETIC",
                "enforcement": "Synthetic phase0 plumbing contract; forbidden as product-shape proof.",
            },
        )
        cls.write_json(
            run_dir / "x3_disposition.json",
            {
                "x3_code": "X3_ALLOW",
                "authorization_scope": "PHASE0_SYNTHETIC",
                "runtime_generation_status": "MOCKED",
                "proceed_to_runtime": True,
            },
        )
        cls.write_json(run_dir / "l6_shadow_eval_package.json", {"offline_only": True})
        try:
            return run_dir.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            return run_dir.resolve().as_posix()

    @classmethod
    def synthetic_lane_row(cls, repo: Path, modular_root: Path, lane: str) -> dict[str, Any]:
        """Produce synthetic lane row metadata for rollup."""
        rel_run = cls.write_synthetic_lane_bundle(repo, modular_root, lane)
        contract_path = repo / rel_run / FINAL_MATERIALIZED_ACCEPTANCE_CONTRACT
        return {
            "lane_key": lane,
            "section_id": lane,
            "rollup_source_run_dir": rel_run,
            "latest_successful_real_artifact_path": rel_run,
            "accepted_real_evidence_resolution": "latest_successful_real_run.json",
            "runtime_generation_status": "MOCKED",
            "x2_passed": 1,
            "x2_failed": 0,
            "x2_total_gates": 1,
            "x2_failed_gate_ids": [],
            "x2_artifact_failed_gates": [],
            "gemini_provider_status": "OK",
            "openai_provider_status": "OK",
            "soft_failed_judges": [],
            "blocked_judges": [],
            "x3_code": "X3_ALLOW",
            "final_materialized_acceptance_ok": True,
            "final_materialized_acceptance_contract_ref": f"{rel_run}/{FINAL_MATERIALIZED_ACCEPTANCE_CONTRACT}",
            "final_materialized_acceptance_contract_digest": hashlib.sha256(
                contract_path.read_bytes()
            ).hexdigest(),
            "final_materialized_acceptance_failure_reasons": [],
            "authorization_scope": "PHASE0_SYNTHETIC",
            "proceed_to_runtime": True,
            "l6_offline_only": True,
            "artifact_refs": {n: f"{rel_run}/{n}" for n in [
                "l2_output.json",
                "x2_gate_outputs.json",
                "x1d_llm_judge_outputs.json",
                "x3_disposition.json",
                FINAL_MATERIALIZED_ACCEPTANCE_CONTRACT,
                "l6_shadow_eval_package.json",
            ]},
        }

    @classmethod
    def build_synthetic_rollup(cls, repo: Path, modular_root: Path) -> dict[str, Any]:
        """Construct synthetic rollup across all GENERATED_LANES."""
        lanes = {lane: cls.synthetic_lane_row(repo, modular_root, lane) for lane in GENERATED_LANES}
        now = datetime.now(timezone.utc).isoformat()
        return {
            "rollup_id": f"phase0_generated_lane_rollup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "generated_at_utc": now,
            "repo_root": str(repo.resolve()).replace("\\", "/"),
            "current_rollup_artifact_mode": "phase0_synthetic",
            "rollup_artifact_mode_arg": "phase0_synthetic",
            "lanes": lanes,
            "summary": {
                "lane_keys": list(GENERATED_LANES),
                "phase0_synthetic": True,
            },
        }

    @staticmethod
    def assembly_plumbing_mode(profile: Any, *, use_phase0_synthetic: bool) -> bool:
        """Determine whether assembly runs in lightweight plumbing mode."""
        if getattr(profile, "phase1_invoke_real_lanes", False):
            return False
        if use_phase0_synthetic:
            return True
        prov = str(getattr(profile, "phase1_lane_provider", "") or "").strip().lower()
        return prov in _PLUMBING_ASSEMBLY_PROVIDERS or prov.startswith("mock")

    @staticmethod
    def assemble_modular_final_resume(
        paths: FinalResumePaths,
        *,
        plumbing_mode: bool,
    ) -> dict[str, Any]:
        """Run modular final resume assembly under temporary env overrides."""
        overrides = (
            {
                "APPS_RG_ASSEMBLY_STRUCTURAL_ONLY": "1",
                "APPS_RG_FULL_RESUME_LLM_COHERENCE_REVIEW": "0",
            }
            if plumbing_mode
            else {}
        )
        with temporary_env_override(overrides):
            return assemble_final_resume(paths, skip_preflight=plumbing_mode)

    @classmethod
    def execute_phase1_assembly(
        cls,
        *,
        repo: Path,
        modular_root: Path,
        art: Path,
        rollup_blob: dict[str, Any],
        profile: Any,
    ) -> tuple[bool | None, str | None]:
        """Run locked copy and final resume assembly for Phase 1."""
        rollup_dir = modular_root / "generated_lane_rollup"
        rollup_dir.mkdir(parents=True, exist_ok=True)
        cls.write_json(rollup_dir / "generated_lane_rollup.json", rollup_blob)

        build_locked_copy(repo, modular_output_root=modular_root)

        locked_dir = modular_root / "locked_copy"
        _, canonical_base_resume_path, _ = load_lane_base_resume_json(repo_root=repo)
        paths = FinalResumePaths(
            repo_root=repo,
            rollup_json=rollup_dir / "generated_lane_rollup.json",
            locked_manifest=locked_dir / "locked_copy_manifest.json",
            locked_x2=locked_dir / "locked_copy_x2_gate_outputs.json",
            base_resume=canonical_base_resume_path,
            output_dir=modular_root / "final_resume_assembly",
        )
        plumbing = cls.assembly_plumbing_mode(profile, use_phase0_synthetic=False)
        asm = cls.assemble_modular_final_resume(paths, plumbing_mode=plumbing)
        assembly_gates_ok = bool(asm.get("gates_all_pass"))
        receipt_path = asm["paths"]["receipt"]
        try:
            merge_receipt_rel = receipt_path.relative_to(art).as_posix()
        except ValueError:
            merge_receipt_rel = str(receipt_path)
        return assembly_gates_ok, merge_receipt_rel

    @classmethod
    def execute_phase0_synthetic_assembly(
        cls,
        *,
        repo: Path,
        modular_root: Path,
        art: Path,
        rollup_blob: dict[str, Any],
        profile: Any,
    ) -> tuple[bool | None, str | None]:
        """Run locked copy and synthetic final resume assembly for Phase 0."""
        rollup_dir = modular_root / "generated_lane_rollup"
        rollup_dir.mkdir(parents=True, exist_ok=True)
        cls.write_json(rollup_dir / "generated_lane_rollup.json", rollup_blob)

        build_locked_copy(repo, modular_output_root=modular_root)

        locked_dir = modular_root / "locked_copy"
        _, canonical_base_resume_path, _ = load_lane_base_resume_json(repo_root=repo)
        paths = FinalResumePaths(
            repo_root=repo,
            rollup_json=rollup_dir / "generated_lane_rollup.json",
            locked_manifest=locked_dir / "locked_copy_manifest.json",
            locked_x2=locked_dir / "locked_copy_x2_gate_outputs.json",
            base_resume=canonical_base_resume_path,
            output_dir=modular_root / "final_resume_assembly",
        )
        plumbing = cls.assembly_plumbing_mode(profile, use_phase0_synthetic=True)
        asm = cls.assemble_modular_final_resume(paths, plumbing_mode=plumbing)
        assembly_gates_ok = bool(asm.get("structural_x2_all_pass"))
        receipt_path = asm["paths"]["receipt"]
        try:
            merge_receipt_rel = receipt_path.relative_to(art).as_posix()
        except ValueError:
            merge_receipt_rel = str(receipt_path)
        return assembly_gates_ok, merge_receipt_rel


__all__ = ["ArtifactAssembler"]
