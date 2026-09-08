from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.apps_rg_standalone import c03_embeddings

ROOT = Path(__file__).resolve().parents[4]
ACTIVE = ROOT / "artifacts/apps_rg/c03/graph_skill_embeddings"


def test_script_bootstraps_src_without_preconfigured_pythonpath() -> None:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/apps_rg_standalone/c03_embeddings.py"),
            "--help",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "preflight" in completed.stdout
    assert "rebuild" in completed.stdout


def test_standalone_source_paths_use_src_owned_inputs() -> None:
    paths = c03_embeddings.standalone_source_paths(ROOT)

    assert paths == {
        "graph": ROOT / "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json",
        "candidate_facts": ROOT
        / (
            "artifacts/apps_rg/fact_inventory/"
            "master_candidate_skills_fact_ledger_20260518T1100Z.json"
        ),
        "base_resume": ROOT / "src/apps_rg/resume/base/amit_ayer_base_resume_v1.json",
    }
    assert all(path.is_file() for path in paths.values())


def test_runtime_contract_remains_historical_and_offline_pinned() -> None:
    contract = c03_embeddings.verify_embedding_runtime_contract(ROOT)
    raw_contract = json.loads(
        (
            ROOT / "tools/apps_rg_standalone/c03_embedding_runtime_contract.json"
        ).read_text(encoding="utf-8")
    )

    assert contract["python_major_minor"] == "3.12"
    assert contract["packages"] == {
        "torch": "2.12.0.dev20260228+cu128",
        "sentence-transformers": "5.2.3",
    }
    assert contract["promoted_device"] == "cuda:0"
    assert raw_contract["network_allowed"] is False
    assert raw_contract["fallback_allowed"] is False


def test_retired_artifact_directory_is_absent() -> None:
    assert not ACTIVE.exists()


@pytest.mark.parametrize(
    ("operation", "kwargs"),
    [
        (
            c03_embeddings.build_candidate,
            {
                "output_dir": ROOT / ".runtime/retired-build-probe",
                "model_path": None,
                "device": None,
            },
        ),
        (
            c03_embeddings.qualify_candidate,
            {
                "generation_dir": ROOT / ".runtime/retired-generation-probe",
                "query_qrels_path": ROOT / ".runtime/retired-qrels-probe.json",
                "model_path": None,
                "device": None,
            },
        ),
        (
            c03_embeddings.activate_candidate,
            {"candidate_dir": ROOT / ".runtime/retired-activation-probe"},
        ),
        (c03_embeddings.preflight, {}),
        (
            c03_embeddings.smoke_query,
            {
                "query_text": "retirement probe",
                "section_id": "competencies",
                "model_path": None,
                "device": None,
                "k": 1,
            },
        ),
    ],
)
def test_all_legacy_operator_functions_fail_before_artifact_or_model_access(
    operation: object,
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(
        c03_embeddings.StandaloneEmbeddingError, match="lane is retired"
    ):
        operation(repository_root=ROOT, **kwargs)  # type: ignore[operator]


@pytest.mark.parametrize(
    "command", ["preflight", "build", "qualify", "activate", "smoke"]
)
def test_legacy_cli_commands_report_retirement(command: str, tmp_path: Path) -> None:
    args = [
        sys.executable,
        str(ROOT / "tools/apps_rg_standalone/c03_embeddings.py"),
        command,
    ]
    if command == "build":
        args.extend(["--output-dir", str(tmp_path / "build")])
    elif command == "qualify":
        args.extend(
            [
                "--generation-dir",
                str(tmp_path / "generation"),
                "--query-qrels",
                str(tmp_path / "qrels.json"),
            ]
        )
    elif command == "activate":
        args.extend(["--candidate-dir", str(tmp_path / "candidate")])
    elif command == "smoke":
        args.extend(["--query", "retirement probe"])

    completed = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    failure = json.loads(completed.stderr)
    assert failure["status"] == "FAIL"
    assert "lane is retired" in failure["error"]


def test_retired_legacy_environment_flag_is_not_repurposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPS_RG_GRAPH_SKILL_EMBEDDINGS_REQUIRED", "true")

    with pytest.raises(
        c03_embeddings.StandaloneEmbeddingError, match="lane is retired"
    ):
        c03_embeddings.preflight(repository_root=ROOT)
