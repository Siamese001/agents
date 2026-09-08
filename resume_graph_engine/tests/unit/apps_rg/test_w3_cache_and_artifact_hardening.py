"""Wave 3 adversarial regressions for cache trust and product artifact ownership."""

from __future__ import annotations

import json
from pathlib import Path

from apps_rg.cache.r1b_derived_index import (
    derived_index_available,
    list_derived_index_record_ids,
    load_derived_index_entry,
)
from apps_rg.cache.r1b_store import default_store_root
from apps_rg.cache.r1b_uwg_promotion import (
    AppsRgR1BUwgGateway,
    build_r1b_promotion_candidate,
    promote_and_project_r1b_cache,
)
from apps_rg.runtime.runtime_proof_layout import allocate_product_full_resume_artifact_dir
from tests.unit.apps_rg.r1b_fixture_builders import (
    build_admissible_intent_record,
    build_admissible_output_chunks,
    build_post_exit_eligibility,
    write_post_exit_artifacts,
)


def _project(tmp_path: Path) -> tuple[Path, str]:
    record = build_admissible_intent_record(record_id="hir_w3_tamper")
    chunks = build_admissible_output_chunks(record.record_id)
    run_dir = tmp_path / "run"
    write_post_exit_artifacts(run_dir, record)
    candidate = build_r1b_promotion_candidate(
        record=record,
        chunks=chunks,
        post_exit_eligibility=build_post_exit_eligibility(record, chunks),
        run_dir=run_dir,
    )
    outcome = promote_and_project_r1b_cache(
        candidate=candidate,
        projection_root=tmp_path / "projection",
        gateway=AppsRgR1BUwgGateway(),
    )
    assert outcome.status == "ADMITTED"
    return tmp_path / "projection", record.record_id


def test_r1b_tampered_derived_entry_is_not_readable(tmp_path: Path) -> None:
    root, record_id = _project(tmp_path)
    entry_path = root / "derived_index" / "intent_vectors" / f"{record_id}.json"
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["cache_admissible"] = True
    entry["vector"]["values"][0] = 999.0
    entry_path.write_text(json.dumps(entry), encoding="utf-8")

    assert derived_index_available(root) is True
    assert record_id in list_derived_index_record_ids(root)
    assert load_derived_index_entry(root, record_id) is None


def test_r1b_tampered_durable_bundle_invalidates_projection_refresh(tmp_path: Path) -> None:
    root, record_id = _project(tmp_path)
    bundle_path = root / "durable" / "uwg_admitted" / "intents" / f"{record_id}.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["parent_intent_record"]["source_run_id"] = "attacker-run"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    # A new projection cannot turn unsigned/tampered durable data into a read surface.
    from apps_rg.cache.r1b_derived_index import project_durable_to_derived_index

    receipt = project_durable_to_derived_index(root)
    assert receipt.entries_projected == 0


def test_product_artifacts_must_stay_under_checkout_proof_root(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    allowed = repo / "artifacts" / "apps_rg" / "runtime_proofs" / "full_resume_explicit"
    assert allocate_product_full_resume_artifact_dir(repo, str(allowed)) == allowed.resolve()

    outside = tmp_path / "shared" / "run"
    try:
        allocate_product_full_resume_artifact_dir(repo, str(outside))
    except ValueError as exc:
        assert "checkout-owned runtime proofs" in str(exc)
    else:  # pragma: no cover - documents the security boundary
        raise AssertionError("external product artifact root was accepted")


def test_product_whole_run_ignores_cache_root_environment_override(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "checkout"
    monkeypatch.setenv("APPS_RG_R1B_CACHE_ROOT", str(tmp_path / "attacker-cache"))
    monkeypatch.setenv("APPS_RG_WHOLE_RUN_ENVELOPE", "1")

    assert default_store_root(repo) == repo / "artifacts" / "apps_rg" / "r1b_semantic_cache"
