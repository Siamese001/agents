"""Run W9 C0.3 human-review intake readiness or controlled finalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.c03_graph_evidence_cluster_human_intake import (  # noqa: E402
    COHORTS,
    CONTRACT_PATH,
    W9_RECEIPT_PATH,
    build_w9_blocked_receipt,
    validate_completed_human_inputs,
    validate_human_intake_contract,
    validate_w9_receipt,
)
from apps_rg.evals.c03_graph_evidence_cluster_qualification import (  # noqa: E402
    ACTIVATION_MANIFEST_PATH,
    QUERY_MANIFEST_PATH,
    collect_qrel_issues,
)
from apps_rg.evals.c03_graph_evidence_cluster_review_packet import (  # noqa: E402
    W8_RECEIPT_PATH,
    validate_prelabel_packet_content,
    validate_w8_receipt,
)
from apps_rg.evals.c03_human_eval._io import (  # noqa: E402
    owner_only_security_error,
    private_path_error,
    write_json,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (  # noqa: E402
    REGISTRY_PATH,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (  # noqa: E402
    canonical_sha256,
)

DEFAULT_BASELINE_REF = "87499c22ae0bd8a366443f525356d40b9f4d7941"
DEFAULT_W8_PACKET_DIR = Path(".runtime/c03-cluster-w8/prelabel_packet")
DEFAULT_W9_RUNTIME_DIR = Path(".runtime/c03-cluster-w9")
DEFAULT_AUTHORITY_PATH = (
    DEFAULT_W9_RUNTIME_DIR / "authority/human_review_authority.v1.json"
)
DEFAULT_RETURNS_DIR = DEFAULT_W9_RUNTIME_DIR / "returns"
DEFAULT_FINAL_DIR = DEFAULT_W9_RUNTIME_DIR / "finalized"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON authority must be an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise SystemExit(f"Expected JSON object at {path}:{number}")
        rows.append(value)
    return rows


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_bytes(repo_root: Path, ref: str, path: Path) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path.as_posix()}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return result.stdout


def _write_new_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _runtime_path(repo_root: Path, raw: Path, label: str) -> Path:
    path = raw.resolve() if raw.is_absolute() else (repo_root / raw).resolve()
    runtime = (repo_root / ".runtime").resolve()
    try:
        path.relative_to(runtime)
    except ValueError as exc:
        raise SystemExit(f"{label} must remain below ignored .runtime") from exc
    return path


def _assert_source_authority(
    repo_root: Path, baseline_ref: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    if (repo_root / W8_RECEIPT_PATH).read_bytes() != _git_bytes(
        repo_root, baseline_ref, W8_RECEIPT_PATH
    ):
        raise SystemExit("W8 receipt changed after the W9 baseline")
    if (repo_root / ACTIVATION_MANIFEST_PATH).exists():
        raise SystemExit("W9 cannot create or coexist with an activation manifest")
    contract = _load_json(repo_root / CONTRACT_PATH)
    w8_receipt = _load_json(repo_root / W8_RECEIPT_PATH)
    validate_human_intake_contract(contract)
    validate_w8_receipt(w8_receipt)
    return contract, w8_receipt


def _load_w8_packet(
    repo_root: Path,
    packet_dir: Path,
    w8_receipt: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, list[dict[str, Any]]],
    dict[str, Any],
    dict[str, str],
]:
    manifest_path = packet_dir / "packet_manifest.v1.json"
    if not manifest_path.is_file():
        raise SystemExit("W8 controlled packet is missing")
    if _file_sha256(manifest_path) != w8_receipt["controlled_packet"][
        "packet_manifest_file_sha256"
    ]:
        raise SystemExit("W8 packet manifest file differs from its committed receipt")
    manifest = _load_json(manifest_path)
    unsigned = dict(manifest)
    supplied = unsigned.pop("manifest_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        raise SystemExit("W8 packet manifest digest is invalid")
    if supplied != w8_receipt["controlled_packet"]["packet_manifest_sha256"]:
        raise SystemExit("W8 packet manifest is not receipt-bound")

    packet_items: dict[str, list[dict[str, Any]]] = {}
    source_items_sha: dict[str, str] = {}
    for cohort in COHORTS:
        root = packet_dir / cohort
        reviewer_manifest_path = root / "reviewer_manifest.v1.json"
        reviewer_manifest = _load_json(reviewer_manifest_path)
        reviewer_unsigned = dict(reviewer_manifest)
        reviewer_digest = reviewer_unsigned.pop("manifest_sha256", None)
        if canonical_sha256(reviewer_unsigned) != reviewer_digest:
            raise SystemExit(f"W8 {cohort} manifest digest is invalid")
        if reviewer_manifest["manifest_sha256"] != w8_receipt[
            "controlled_packet"
        ]["reviewer_cohort_manifest_sha256"][cohort]:
            raise SystemExit(f"W8 {cohort} manifest is not receipt-bound")
        if _file_sha256(reviewer_manifest_path) != manifest["cohorts"][cohort][
            "manifest_file_sha256"
        ]:
            raise SystemExit(f"W8 {cohort} manifest file digest is invalid")
        items_path = root / "review_items.jsonl"
        source_items_sha[cohort] = _file_sha256(items_path)
        if source_items_sha[cohort] != reviewer_manifest["files"][
            "review_items.jsonl"
        ]:
            raise SystemExit(f"W8 {cohort} items digest is invalid")
        packet_items[cohort] = _read_jsonl(items_path)
    sealed_path = packet_dir / "sealed_internal/identity_and_rank_mapping.v1.json"
    if _file_sha256(sealed_path) != manifest["sealed_mapping_file_sha256"]:
        raise SystemExit("W8 sealed mapping digest is invalid")
    sealed_mapping = _load_json(sealed_path)
    query_manifest = _load_json(repo_root / QUERY_MANIFEST_PATH)
    registry = _load_json(repo_root / REGISTRY_PATH)
    content = {
        "schema_version": "apps_rg.c03_graph_evidence_cluster_review_packet.v1",
        "status": "FROZEN_UNLABELED_PRELABEL",
        "authority_bindings": manifest["authority_bindings"],
        "ranking_identity_sha256": manifest["ranking_identity_sha256"],
        "blinding_nonce_commitment": manifest["blinding_nonce_commitment"],
        "cohorts": packet_items,
        "sealed_mapping": sealed_mapping,
    }
    validate_prelabel_packet_content(
        content, query_manifest=query_manifest, registry=registry
    )
    return manifest, packet_items, sealed_mapping, source_items_sha


def _validate_receipt_sources(
    *,
    receipt: dict[str, Any],
    contract: dict[str, Any],
    w8_receipt: dict[str, Any],
    baseline_ref: str,
    repo_root: Path,
) -> None:
    validate_w9_receipt(receipt)
    source = receipt["source_baseline"]
    expected = {
        "commit": baseline_ref,
        "tree": _git_value(repo_root, "rev-parse", f"{baseline_ref}^{{tree}}"),
        "wave8_receipt_sha256": w8_receipt["receipt_sha256"],
        "packet_manifest_sha256": w8_receipt["controlled_packet"][
            "packet_manifest_sha256"
        ],
        "packet_manifest_file_sha256": w8_receipt["controlled_packet"][
            "packet_manifest_file_sha256"
        ],
        "ranking_identity_sha256": w8_receipt["source_baseline"][
            "ranking_identity_sha256"
        ],
    }
    if any(source.get(field) != value for field, value in expected.items()):
        raise SystemExit("W9 receipt source authority drifted")
    if receipt["contract"]["canonical_sha256"] != canonical_sha256(contract):
        raise SystemExit("W9 receipt contract binding drifted")


def _input_paths(authority_path: Path, returns_dir: Path) -> list[Path]:
    return [
        authority_path,
        *(returns_dir / cohort / "reviewer_return_manifest.v1.json" for cohort in COHORTS),
        *(returns_dir / cohort / "reviews.jsonl" for cohort in COHORTS),
        returns_dir / "adjudication/adjudication_manifest.v1.json",
        returns_dir / "adjudication/adjudications.jsonl",
    ]


def _load_completed_inputs(
    *,
    authority_path: Path,
    returns_dir: Path,
) -> tuple[dict[str, Any], str, dict[str, dict[str, Any]], dict[str, Any]]:
    authority = _load_json(authority_path)
    review_bundles: dict[str, dict[str, Any]] = {}
    for cohort in COHORTS:
        root = returns_dir / cohort
        reviews_path = root / "reviews.jsonl"
        review_bundles[cohort] = {
            "manifest": _load_json(root / "reviewer_return_manifest.v1.json"),
            "rows": _read_jsonl(reviews_path),
            "observed_file_sha256": _file_sha256(reviews_path),
        }
    adjudication_root = returns_dir / "adjudication"
    adjudications_path = adjudication_root / "adjudications.jsonl"
    adjudication_bundle = {
        "manifest": _load_json(
            adjudication_root / "adjudication_manifest.v1.json"
        ),
        "rows": _read_jsonl(adjudications_path),
        "observed_file_sha256": _file_sha256(adjudications_path),
    }
    return authority, _file_sha256(authority_path), review_bundles, adjudication_bundle


def _assert_official_control_storage(paths: list[Path]) -> None:
    platform_error = owner_only_security_error()
    if platform_error is not None:
        raise SystemExit(platform_error)
    for path in paths:
        error = private_path_error(path, directory=False)
        if error:
            raise SystemExit(f"official W9 input {error}: {path}")
        directory_error = private_path_error(path.parent, directory=True)
        if directory_error:
            raise SystemExit(
                f"official W9 input parent {directory_error}: {path.parent}"
            )


def _write_finalized_outputs(
    output_dir: Path,
    *,
    report: dict[str, Any],
    w8_receipt: dict[str, Any],
    authority_file_sha256: str,
) -> dict[str, Any]:
    if output_dir.exists():
        raise SystemExit("W9 final output already exists; finalization is create-once")
    qrels = report["qrels"]
    qrels_path = output_dir / "cluster_qrels.v1.json"
    write_json(qrels_path, qrels)
    finalization: dict[str, Any] = {
        "schema_version": "apps_rg.c03_cluster_embedding_w9_finalization.v1",
        "status": "PASS_HUMAN_QRELS_FROZEN",
        "wave8_receipt_sha256": w8_receipt["receipt_sha256"],
        "human_authority_file_sha256": authority_file_sha256,
        "reviewer_judgment_count": report["reviewer_judgment_count"],
        "adjudication_count": report["adjudication_count"],
        "qrel_sha256": qrels["qrel_sha256"],
        "qrels_file_sha256": _file_sha256(qrels_path),
        "semantic_retrieval_qualified": False,
        "production_promotion_authorized": False,
    }
    finalization["receipt_sha256"] = canonical_sha256(finalization)
    write_json(output_dir / "wave9_finalization_receipt.json", finalization)
    return finalization


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--baseline-ref", default=DEFAULT_BASELINE_REF)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_W8_PACKET_DIR)
    parser.add_argument("--authority-receipt", type=Path, default=DEFAULT_AUTHORITY_PATH)
    parser.add_argument("--returns-dir", type=Path, default=DEFAULT_RETURNS_DIR)
    parser.add_argument("--final-output-dir", type=Path, default=DEFAULT_FINAL_DIR)
    parser.add_argument("--expected-human-authority-file-sha256")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--check-receipt", action="store_true")
    mode.add_argument("--finalize", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    contract, w8_receipt = _assert_source_authority(repo_root, args.baseline_ref)
    receipt_path = repo_root / W9_RECEIPT_PATH
    if args.check_receipt:
        receipt = _load_json(receipt_path)
        _validate_receipt_sources(
            receipt=receipt,
            contract=contract,
            w8_receipt=w8_receipt,
            baseline_ref=args.baseline_ref,
            repo_root=repo_root,
        )
        packet_verified = False
    else:
        packet_dir = _runtime_path(repo_root, args.packet_dir, "W8 packet")
        packet_manifest, packet_items, sealed_mapping, source_items_sha = (
            _load_w8_packet(repo_root, packet_dir, w8_receipt)
        )
        packet_verified = True
        authority_path = _runtime_path(
            repo_root, args.authority_receipt, "human authority receipt"
        )
        returns_dir = _runtime_path(repo_root, args.returns_dir, "human returns")
        if args.write:
            if receipt_path.exists():
                raise SystemExit("W9 readiness receipt already exists; use --check")
            existing_inputs = [path for path in _input_paths(authority_path, returns_dir) if path.exists()]
            if existing_inputs:
                raise SystemExit(
                    "human inputs already exist; readiness cannot report zero observations"
                )
            receipt = build_w9_blocked_receipt(
                contract=contract,
                w8_receipt=w8_receipt,
                packet_manifest=packet_manifest,
                source_commit=args.baseline_ref,
                source_tree=_git_value(
                    repo_root, "rev-parse", f"{args.baseline_ref}^{{tree}}"
                ),
            )
            _write_new_json(receipt_path, receipt)
        elif args.check:
            receipt = _load_json(receipt_path)
            _validate_receipt_sources(
                receipt=receipt,
                contract=contract,
                w8_receipt=w8_receipt,
                baseline_ref=args.baseline_ref,
                repo_root=repo_root,
            )
        else:
            expected_authority_sha = str(
                args.expected_human_authority_file_sha256 or ""
            )
            _assert_official_control_storage(
                [
                    *_input_paths(authority_path, returns_dir),
                    packet_dir / "packet_manifest.v1.json",
                    packet_dir
                    / "sealed_internal/identity_and_rank_mapping.v1.json",
                    *(packet_dir / cohort / "review_items.jsonl" for cohort in COHORTS),
                    *(
                        packet_dir / cohort / "reviewer_manifest.v1.json"
                        for cohort in COHORTS
                    ),
                ]
            )
            authority, observed_authority_sha, reviews, adjudication = (
                _load_completed_inputs(
                    authority_path=authority_path, returns_dir=returns_dir
                )
            )
            report = validate_completed_human_inputs(
                w8_receipt=w8_receipt,
                packet_manifest=packet_manifest,
                packet_items=packet_items,
                sealed_mapping=sealed_mapping,
                source_review_items_sha256=source_items_sha,
                authority_receipt=authority,
                trusted_authority_file_sha256=expected_authority_sha,
                observed_authority_file_sha256=observed_authority_sha,
                review_bundles=reviews,
                adjudication_bundle=adjudication,
            )
            if report["status"] != "PASS_HUMAN_QRELS_FROZEN":
                print(json.dumps(report, indent=2))
                return 2
            qrel_issues = collect_qrel_issues(
                report["qrels"],
                query_manifest=_load_json(repo_root / QUERY_MANIFEST_PATH),
                registry=_load_json(repo_root / REGISTRY_PATH),
                projection_generation_sha256=w8_receipt["source_baseline"][
                    "projection_generation_sha256"
                ],
                expected_ranking_identity_sha256=w8_receipt["source_baseline"][
                    "ranking_identity_sha256"
                ],
                expected_human_review_authority_receipt_sha256=(
                    expected_authority_sha
                ),
            )
            if qrel_issues:
                raise SystemExit(
                    f"W9 output is not W7-compatible: {qrel_issues}"
                )
            final_output = _runtime_path(
                repo_root, args.final_output_dir, "W9 final output"
            )
            finalization = _write_finalized_outputs(
                final_output,
                report=report,
                w8_receipt=w8_receipt,
                authority_file_sha256=expected_authority_sha,
            )
            print(json.dumps(finalization, indent=2))
            return 0

    output = {
        "status": receipt["status"],
        "wave": "W9",
        "packet_verified": packet_verified,
        "validator_implemented": receipt["intake_readiness"][
            "validator_implemented"
        ],
        "observed_reviewer_judgment_slots": receipt["intake_readiness"][
            "observed_reviewer_judgment_slots"
        ],
        "observed_adjudications": receipt["intake_readiness"][
            "observed_adjudications"
        ],
        "human_qrels_frozen": receipt["scope"]["human_qrels_frozen"],
        "semantic_retrieval_qualified": receipt["scope"][
            "semantic_retrieval_qualified"
        ],
        "production_promotion": receipt["wave_exit_gates"][
            "production_promotion"
        ],
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
