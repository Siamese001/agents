from __future__ import annotations

import json
from pathlib import Path

from tools.apps_rg_standalone.w1d_adjudication import (
    _asset_decision,
    canonical_asset_inventory,
    third_party_package_reconciliation,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_asset_decisions_do_not_default_visible_source_inputs_to_zero_scope() -> None:
    assert _asset_decision("apps_rg/resume/base/candidate.json")[0] == "MIGRATE_CANONICAL_INPUT"
    assert _asset_decision("apps_rg/fact_inventory/schemas/facts.schema.json")[0] == "MIGRATE_SCHEMA"
    assert _asset_decision("apps_rg/prompt_assembly/templates/lane.yaml")[0] == "MIGRATE_TEMPLATE"
    assert _asset_decision("apps_eval/fixtures/dev/apps_rg/basic/input.json")[0] == "MIGRATE_REPLAY_FIXTURE"


def test_asset_inventory_has_digests_owners_and_no_unknowns(tmp_path: Path) -> None:
    _write_json(tmp_path / "apps_rg" / "resume" / "base" / "candidate.json", {"id": "candidate"})
    _write_json(tmp_path / "apps_rg" / "fact_inventory" / "schemas" / "facts.schema.json", {"type": "object"})
    (tmp_path / "apps_rg" / "config").mkdir(parents=True)
    (tmp_path / "apps_rg" / "config" / "provider_profiles.yaml").write_text("providers: []\n", encoding="utf-8")

    inventory, reconciliation = canonical_asset_inventory(tmp_path)

    assert inventory["candidate_count"] == 3
    assert reconciliation["unknown_asset_candidate_count"] == 0
    assert reconciliation["canonical_asset_missing_digest_count"] == 0
    assert reconciliation["canonical_asset_unowned_count"] == 0
    assert reconciliation["canonical_migration_asset_count"] == 3


def test_third_party_normalization_keeps_redis_pending_behavioral_reachability(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "artifacts/apps_rg_standalone/w1/runtime-import-smoke-0004/runtime_module_trace.json",
        {
            "runs": [
                {
                    "third_party_modules": [
                        {"module": "redis"},
                        {"module": "redis.client"},
                        {"module": "yaml"},
                    ]
                }
            ]
        },
    )
    (tmp_path / "apps_rg").mkdir()
    (tmp_path / "apps_rg" / "cache").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps_rg" / "cache" / "redis_cache_client.py").write_text("import redis\n", encoding="utf-8")

    reconciliation = third_party_package_reconciliation(tmp_path)
    redis = next(row for row in reconciliation["records"] if row["package_root"] == "redis")

    assert reconciliation["unknown_third_party_package_count"] == 0
    assert redis["target_disposition"] == "SOURCE_BOOTSTRAP_ONLY"
    assert redis["target_dependency_decision"] == "UNDECIDED_PENDING_BEHAVIORAL_REACHABILITY"
    assert redis["complete_first_import_chain"] == [
        "apps_rg.__main__",
        "apps_rg.runtime.orchestration.canonical_dispatch",
        "apps_rg.cache.redis_cache_client",
        "redis",
    ]
