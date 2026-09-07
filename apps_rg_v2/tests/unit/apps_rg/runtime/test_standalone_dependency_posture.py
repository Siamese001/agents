from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from apps_rg.runtime.standalone_dependency_posture import (
    APP_RUNTIME_INDEPENDENCE_RECEIPT_FILENAME,
    APP_RUNTIME_INDEPENDENT,
    AppRuntimeIndependenceError,
    validate_app_runtime_independence_receipt,
    verify_app_runtime_independence,
    write_app_runtime_independence_receipt,
)


def _local_source_checkout(root: Path) -> Path:
    source = root / "src" / "apps_rg"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("\n", encoding="utf-8")
    (source / "pipeline.py").write_text(
        "from apps_rg import contracts\nimport json\n",
        encoding="utf-8",
    )
    return root


def test_local_runtime_receipt_is_digest_bound_and_non_authorizing(
    tmp_path: Path,
) -> None:
    root = _local_source_checkout(tmp_path / "checkout")

    receipt = verify_app_runtime_independence(
        repo_root=root,
        generated_at_utc=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )

    assert receipt["status"] == APP_RUNTIME_INDEPENDENT
    assert receipt["authority_class"] == "TECHNICAL_RUNTIME_OBSERVATION_ONLY"
    assert receipt["product_authorized"] is False
    assert receipt["release_qualified"] is False
    assert receipt["inventory"] == {
        "python_file_count": 2,
        "import_statement_count": 2,
        "apps_rg_import_count": 1,
    }
    validate_app_runtime_independence_receipt(receipt)


def test_runtime_receipt_writer_round_trips_a_valid_receipt(tmp_path: Path) -> None:
    root = _local_source_checkout(tmp_path / "checkout")
    receipt = verify_app_runtime_independence(repo_root=root)
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()

    receipt_path = write_app_runtime_independence_receipt(
        artifact_dir=artifact_dir,
        receipt=receipt,
    )

    assert receipt_path.name == APP_RUNTIME_INDEPENDENCE_RECEIPT_FILENAME
    persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert persisted == receipt
    validate_app_runtime_independence_receipt(persisted)


def test_runtime_receipt_rejects_digest_and_inventory_tampering(tmp_path: Path) -> None:
    root = _local_source_checkout(tmp_path / "checkout")
    receipt = verify_app_runtime_independence(repo_root=root)
    receipt["inventory"]["python_file_count"] = 0

    with pytest.raises(AppRuntimeIndependenceError, match="digest"):
        validate_app_runtime_independence_receipt(receipt)


def test_runtime_receipt_rejects_a_missing_application_source_root(tmp_path: Path) -> None:
    with pytest.raises(AppRuntimeIndependenceError, match="source root is unavailable"):
        verify_app_runtime_independence(repo_root=tmp_path)


def test_writer_rejects_a_receipt_with_a_non_passing_status(tmp_path: Path) -> None:
    root = _local_source_checkout(tmp_path / "checkout")
    receipt = verify_app_runtime_independence(repo_root=root)
    receipt["status"] = "BLOCKED_LOCAL_RUNTIME_UNAVAILABLE"

    with pytest.raises(AppRuntimeIndependenceError, match="not passing"):
        write_app_runtime_independence_receipt(
            artifact_dir=tmp_path,
            receipt=receipt,
        )
