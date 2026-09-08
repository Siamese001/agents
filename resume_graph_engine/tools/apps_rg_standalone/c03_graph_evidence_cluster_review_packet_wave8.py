"""Build or verify the controlled W8 C0.3 cluster-review prelabel packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.c03_graph_evidence_cluster_qualification import (  # noqa: E402
    ACTIVATION_MANIFEST_PATH,
    QUERY_MANIFEST_PATH,
    W6_RECEIPT_PATH,
    W7_RECEIPT_PATH,
    expected_judgment_keys,
    ranking_identity_sha256,
    validate_query_manifest,
    validate_w7_receipt,
)
from apps_rg.evals.c03_graph_evidence_cluster_review_packet import (  # noqa: E402
    COHORTS,
    CONTRACT_PATH,
    W8_RECEIPT_PATH,
    blinding_nonce_commitment,
    build_prelabel_packet_content,
    build_w8_receipt,
    validate_prelabel_packet_content,
    validate_review_packet_contract,
    validate_w8_receipt,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (  # noqa: E402
    REGISTRY_PATH,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_registry import (  # noqa: E402
    validate_registry,
)
from apps_rg.fact_inventory.c03_skill_embedding_builder import (  # noqa: E402
    build_local_model_manifest,
    encode_bge_m3,
)
from apps_rg.runtime.graph_evidence_cluster_embedding_projection import (  # noqa: E402
    GraphEvidenceClusterEmbeddingIndex,
    validate_cluster_embedding_projection,
)

DEFAULT_BASELINE_REF = "05c5670632d160be1c4d9c7f80bf0a50e7d4e121"
DEFAULT_RUNTIME_ROOT = Path(".runtime/c03-cluster-w8")
DEFAULT_NONCE_PATH = DEFAULT_RUNTIME_ROOT / "blinding_nonce.hex"
DEFAULT_PACKET_PATH = DEFAULT_RUNTIME_ROOT / "prelabel_packet"


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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


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


def _write_new_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _write_new_json(path: Path, value: Any) -> None:
    _write_new_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _write_new_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    _write_new_text(path, "".join(_canonical_json(row) + "\n" for row in rows))


def _assert_runtime_path(repo_root: Path, path: Path, label: str) -> Path:
    runtime = (repo_root / ".runtime").resolve()
    resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
    try:
        resolved.relative_to(runtime)
    except ValueError as exc:
        raise SystemExit(f"{label} must remain below the ignored .runtime directory") from exc
    return resolved


def _read_nonce(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise SystemExit("blinding nonce must be a regular, non-symlink file")
    value = path.read_text(encoding="utf-8").strip()
    blinding_nonce_commitment(value)
    return value


def _initialize_nonce(path: Path) -> dict[str, Any]:
    if path.exists():
        raise SystemExit("nonce already exists; W8 nonce creation is create-once")
    nonce = secrets.token_hex(32)
    _write_new_text(path, nonce + "\n")
    return {
        "status": "NONCE_INITIALIZED",
        "nonce_disclosed": False,
        "nonce_commitment": blinding_nonce_commitment(nonce),
    }


def _assert_w7_authority_unchanged(repo_root: Path, baseline_ref: str) -> None:
    for path in (QUERY_MANIFEST_PATH, REGISTRY_PATH, W6_RECEIPT_PATH, W7_RECEIPT_PATH):
        if (repo_root / path).read_bytes() != _git_bytes(repo_root, baseline_ref, path):
            raise SystemExit(f"W7 authority changed after baseline: {path.as_posix()}")
    if (repo_root / ACTIVATION_MANIFEST_PATH).exists():
        raise SystemExit("W8 cannot create or coexist with an activation manifest")


def _load_authority(
    repo_root: Path, baseline_ref: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    _assert_w7_authority_unchanged(repo_root, baseline_ref)
    query_manifest = _load_json(repo_root / QUERY_MANIFEST_PATH)
    registry = _load_json(repo_root / REGISTRY_PATH)
    w6_receipt = _load_json(repo_root / W6_RECEIPT_PATH)
    w7_receipt = _load_json(repo_root / W7_RECEIPT_PATH)
    validate_query_manifest(query_manifest, repository_root=repo_root)
    validate_registry(registry)
    validate_w7_receipt(w7_receipt)
    generation_path = repo_root / str(w6_receipt["generation"]["manifest_path"])
    if _file_sha256(generation_path) != w6_receipt["generation"][
        "manifest_file_sha256"
    ]:
        raise SystemExit("W6 generation manifest digest drifted")
    generation = _load_json(generation_path)
    projection_path = repo_root / str(generation["projection"]["path"])
    if _file_sha256(projection_path) != generation["projection"]["file_sha256"]:
        raise SystemExit("W6 projection file digest drifted")
    return query_manifest, registry, w7_receipt, generation, projection_path


def _validate_receipt_sources(
    *,
    receipt: dict[str, Any],
    contract: dict[str, Any],
    w7_receipt: dict[str, Any],
    baseline_ref: str,
    repo_root: Path,
) -> None:
    validate_w8_receipt(receipt)
    source = receipt["source_baseline"]
    expected = {
        "commit": baseline_ref,
        "tree": _git_value(repo_root, "rev-parse", f"{baseline_ref}^{{tree}}"),
        "wave7_receipt_sha256": w7_receipt["receipt_sha256"],
        "query_manifest_sha256": w7_receipt["query_manifest"][
            "query_manifest_sha256"
        ],
        "wave4_registry_sha256": w7_receipt["source_baseline"][
            "wave4_registry_sha256"
        ],
        "projection_generation_sha256": w7_receipt["source_baseline"][
            "projection_generation_sha256"
        ],
        "ranking_identity_sha256": w7_receipt["diagnostic_proof"][
            "ranking_identity_sha256"
        ],
    }
    if any(source.get(field) != value for field, value in expected.items()):
        raise SystemExit("W8 receipt source authority drifted")
    if receipt["contract"]["canonical_sha256"] != _canonical_sha256(contract):
        raise SystemExit("W8 receipt contract binding drifted")


def _compute_frozen_rankings(
    *,
    repo_root: Path,
    query_manifest: dict[str, Any],
    registry: dict[str, Any],
    w7_receipt: dict[str, Any],
    generation: dict[str, Any],
    projection_path: Path,
    model_path: Path,
    device: str,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    model_manifest = build_local_model_manifest(model_path)
    if model_manifest["artifact_sha256"] != generation["model"]["artifact_sha256"]:
        raise SystemExit("Local model does not match the W6 model artifact")
    issues = validate_cluster_embedding_projection(
        projection_path, registry=registry, model_manifest=model_manifest
    )
    if issues:
        raise SystemExit(f"W6 projection validation failed: {issues}")
    query_texts: dict[str, str] = {}
    for query in query_manifest["queries"]:
        query_id = str(query["query_id"])
        query_texts[query_id] = (
            (repo_root / str(query["jd_path"])).read_text(encoding="utf-8").strip()
            + "\n\n"
            + (repo_root / str(query["brief_path"])).read_text(encoding="utf-8").strip()
        )
    query_ids = sorted(query_texts)
    runtime_proof, vectors = encode_bge_m3(
        [query_texts[query_id] for query_id in query_ids],
        model_path=model_path,
        device=device,
        batch_size=6,
    )
    vectors_by_query = dict(zip(query_ids, vectors, strict=True))
    expected: dict[str, set[str]] = {}
    for query_id, section_id, cluster_id in expected_judgment_keys(
        query_manifest, registry
    ):
        expected.setdefault(f"{query_id}|{section_id}", set()).add(cluster_id)
    rankings: dict[str, list[str]] = {}
    with GraphEvidenceClusterEmbeddingIndex(
        projection_path,
        expected_registry_sha256=str(registry["registry_sha256"]),
        expected_model_artifact_sha256=str(model_manifest["artifact_sha256"]),
    ) as index:
        for query_id in query_ids:
            for section_id in sorted(str(value) for value in query_manifest["section_ids"]):
                pair = f"{query_id}|{section_id}"
                candidates = index.query(
                    vectors_by_query[query_id], k=37, section_id=section_id
                )
                rankings[pair] = [str(row["cluster_id"]) for row in candidates]
                if set(rankings[pair]) != expected.get(pair, set()):
                    raise SystemExit(f"W8 candidate denominator drifted for {pair}")
    if len(rankings) != 48 or sum(map(len, rankings.values())) != 456:
        raise SystemExit("W8 did not conserve the frozen 48-pair/456-candidate universe")
    observed = ranking_identity_sha256(rankings)
    expected_digest = str(w7_receipt["diagnostic_proof"]["ranking_identity_sha256"])
    if observed != expected_digest:
        raise SystemExit("W8 recomputed ranking identity does not match frozen W7")
    return rankings, runtime_proof


def _review_return_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "C0.3 cluster relevance return",
        "type": "object",
        "additionalProperties": False,
        "required": ["item_ref", "human_identity", "candidate_grades"],
        "properties": {
            "item_ref": {"type": "string", "pattern": "^item-[0-9a-f]{24}$"},
            "human_identity": {"type": "string", "minLength": 1},
            "candidate_grades": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["candidate_ref", "relevance_grade", "rationale"],
                    "properties": {
                        "candidate_ref": {
                            "type": "string",
                            "pattern": "^candidate-[0-9a-f]{24}$",
                        },
                        "relevance_grade": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 3,
                        },
                        "rationale": {"type": "string"},
                    },
                },
            },
        },
    }


def _instructions(cohort: str) -> str:
    return f"""# C0.3 semantic-cluster review: {cohort}

Review every candidate in every item. Do not search the repository, sealed mapping,
other cohort, or model output. Judge only whether the evidence-cluster text is useful
for the target role and named resume section.

Grades: 0 irrelevant; 1 weak/contextual; 2 relevant; 3 highly relevant and directly
useful. Return exactly one grade for every candidate_ref. Preserve item_ref and
candidate_ref. Supply your real approved human identity and a short rationale.

This input contains no model ranks, similarity values, graph IDs, selected flags,
labels, or other-human output. Do not combine this cohort with another distribution.
"""


def _checksums(paths: list[Path], root: Path) -> str:
    return "".join(
        f"{_file_sha256(path)}  {path.relative_to(root).as_posix()}\n"
        for path in sorted(paths, key=lambda item: item.as_posix())
    )


def _write_packet(
    *,
    packet_dir: Path,
    content: dict[str, Any],
    runtime_proof: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    if packet_dir.exists():
        raise SystemExit("packet output already exists; W8 packet creation is create-once")
    packet_dir.mkdir(parents=True, mode=0o700)
    cohort_manifests: dict[str, dict[str, Any]] = {}
    cohort_files: list[Path] = []
    for cohort in COHORTS:
        root = packet_dir / cohort
        items_path = root / "review_items.jsonl"
        schema_path = root / "review_return_schema.v1.json"
        instructions_path = root / "INSTRUCTIONS.md"
        _write_new_jsonl(items_path, content["cohorts"][cohort])
        _write_new_json(schema_path, _review_return_schema())
        _write_new_text(instructions_path, _instructions(cohort))
        manifest = {
            "schema_version": "apps_rg.c03_graph_evidence_cluster_reviewer_manifest.v1",
            "status": "FROZEN_UNLABELED_PRELABEL",
            "reviewer_cohort": cohort,
            "query_section_count": 48,
            "candidate_judgment_count": 456,
            "model_ranks_or_scores_present": False,
            "graph_ids_present": False,
            "labels_present": False,
            "other_cohort_outputs_present": False,
            "files": {
                path.name: _file_sha256(path)
                for path in (items_path, schema_path, instructions_path)
            },
        }
        manifest["manifest_sha256"] = _canonical_sha256(manifest)
        manifest_path = root / "reviewer_manifest.v1.json"
        _write_new_json(manifest_path, manifest)
        checksum_path = root / "SHA256SUMS"
        _write_new_text(
            checksum_path,
            _checksums(
                [items_path, schema_path, instructions_path, manifest_path], root
            ),
        )
        manifest["manifest_file_sha256"] = _file_sha256(manifest_path)
        manifest["checksum_file_sha256"] = _file_sha256(checksum_path)
        cohort_manifests[cohort] = manifest
        cohort_files.extend(
            [items_path, schema_path, instructions_path, manifest_path, checksum_path]
        )
    sealed_path = packet_dir / "sealed_internal" / "identity_and_rank_mapping.v1.json"
    _write_new_json(sealed_path, content["sealed_mapping"])
    packet_manifest: dict[str, Any] = {
        "schema_version": "apps_rg.c03_graph_evidence_cluster_packet_manifest.v1",
        "status": "FROZEN_UNLABELED_PRELABEL",
        "authority_bindings": content["authority_bindings"],
        "ranking_identity_sha256": content["ranking_identity_sha256"],
        "blinding_nonce_commitment": content["blinding_nonce_commitment"],
        "query_section_count_per_cohort": 48,
        "candidate_judgment_count_per_cohort": 456,
        "reviewer_cohort_count": 2,
        "total_reviewer_judgment_slots": 912,
        "runtime_proof": runtime_proof,
        "secret_nonce_present": False,
        "labels_present": False,
        "sealed_mapping_distribution_forbidden": True,
        "sealed_mapping_file_sha256": _file_sha256(sealed_path),
        "cohorts": {
            cohort: {
                "manifest_sha256": cohort_manifests[cohort]["manifest_sha256"],
                "manifest_file_sha256": cohort_manifests[cohort][
                    "manifest_file_sha256"
                ],
                "checksum_file_sha256": cohort_manifests[cohort][
                    "checksum_file_sha256"
                ],
            }
            for cohort in COHORTS
        },
    }
    packet_manifest["manifest_sha256"] = _canonical_sha256(packet_manifest)
    manifest_path = packet_dir / "packet_manifest.v1.json"
    _write_new_json(manifest_path, packet_manifest)
    _write_new_text(
        packet_dir / "SHA256SUMS",
        _checksums([*cohort_files, sealed_path, manifest_path], packet_dir),
    )
    return packet_manifest, _file_sha256(manifest_path)


def _validate_written_packet(
    *,
    packet_dir: Path,
    query_manifest: dict[str, Any],
    registry: dict[str, Any],
    expected_w7_receipt: dict[str, Any],
) -> dict[str, Any]:
    manifest_path = packet_dir / "packet_manifest.v1.json"
    manifest = _load_json(manifest_path)
    unsigned = dict(manifest)
    supplied = unsigned.pop("manifest_sha256", None)
    if _canonical_sha256(unsigned) != supplied:
        raise SystemExit("packet manifest digest is invalid")
    expected_bindings = {
        "wave7_receipt_sha256": expected_w7_receipt["receipt_sha256"],
        "query_manifest_sha256": expected_w7_receipt["query_manifest"][
            "query_manifest_sha256"
        ],
        "registry_sha256": expected_w7_receipt["source_baseline"][
            "wave4_registry_sha256"
        ],
        "projection_generation_sha256": expected_w7_receipt["source_baseline"][
            "projection_generation_sha256"
        ],
    }
    if manifest.get("authority_bindings") != expected_bindings:
        raise SystemExit("packet authority bindings drifted")
    if manifest.get("ranking_identity_sha256") != expected_w7_receipt[
        "diagnostic_proof"
    ]["ranking_identity_sha256"]:
        raise SystemExit("packet ranking identity drifted")
    sealed_path = packet_dir / "sealed_internal" / "identity_and_rank_mapping.v1.json"
    if _file_sha256(sealed_path) != manifest.get("sealed_mapping_file_sha256"):
        raise SystemExit("sealed mapping digest is invalid")
    cohort_items: dict[str, list[dict[str, Any]]] = {}
    for cohort in COHORTS:
        root = packet_dir / cohort
        cohort_manifest = _load_json(root / "reviewer_manifest.v1.json")
        unsigned_cohort = dict(cohort_manifest)
        cohort_digest = unsigned_cohort.pop("manifest_sha256", None)
        if _canonical_sha256(unsigned_cohort) != cohort_digest:
            raise SystemExit(f"{cohort} manifest digest is invalid")
        if cohort_digest != manifest["cohorts"][cohort]["manifest_sha256"]:
            raise SystemExit(f"{cohort} manifest is not bound to the packet")
        if _file_sha256(root / "reviewer_manifest.v1.json") != manifest["cohorts"][
            cohort
        ]["manifest_file_sha256"]:
            raise SystemExit(f"{cohort} manifest file digest is invalid")
        if _file_sha256(root / "SHA256SUMS") != manifest["cohorts"][cohort][
            "checksum_file_sha256"
        ]:
            raise SystemExit(f"{cohort} checksum file digest is invalid")
        for name, digest in cohort_manifest["files"].items():
            if _file_sha256(root / name) != digest:
                raise SystemExit(f"{cohort} file digest failed: {name}")
        expected_cohort_checksums = _checksums(
            [
                root / "review_items.jsonl",
                root / "review_return_schema.v1.json",
                root / "INSTRUCTIONS.md",
                root / "reviewer_manifest.v1.json",
            ],
            root,
        )
        if (root / "SHA256SUMS").read_text(encoding="utf-8") != (
            expected_cohort_checksums
        ):
            raise SystemExit(f"{cohort} checksum inventory is invalid")
        cohort_items[cohort] = _read_jsonl(root / "review_items.jsonl")
    expected_files = {
        Path("packet_manifest.v1.json"),
        Path("SHA256SUMS"),
        Path("sealed_internal/identity_and_rank_mapping.v1.json"),
        *(
            Path(cohort) / name
            for cohort in COHORTS
            for name in (
                "review_items.jsonl",
                "review_return_schema.v1.json",
                "INSTRUCTIONS.md",
                "reviewer_manifest.v1.json",
                "SHA256SUMS",
            )
        ),
    }
    observed_files = {
        path.relative_to(packet_dir) for path in packet_dir.rglob("*") if path.is_file()
    }
    if observed_files != expected_files:
        raise SystemExit(
            "packet file inventory drifted: "
            f"missing={sorted(map(str, expected_files - observed_files))}, "
            f"extra={sorted(map(str, observed_files - expected_files))}"
        )
    expected_top_checksums = _checksums(
        [
            path
            for path in packet_dir.rglob("*")
            if path.is_file() and path != packet_dir / "SHA256SUMS"
        ],
        packet_dir,
    )
    if (packet_dir / "SHA256SUMS").read_text(encoding="utf-8") != (
        expected_top_checksums
    ):
        raise SystemExit("top-level packet checksum inventory is invalid")
    content = {
        "schema_version": "apps_rg.c03_graph_evidence_cluster_review_packet.v1",
        "status": "FROZEN_UNLABELED_PRELABEL",
        "authority_bindings": manifest["authority_bindings"],
        "ranking_identity_sha256": manifest["ranking_identity_sha256"],
        "blinding_nonce_commitment": manifest["blinding_nonce_commitment"],
        "cohorts": cohort_items,
        "sealed_mapping": _load_json(sealed_path),
    }
    validate_prelabel_packet_content(
        content, query_manifest=query_manifest, registry=registry
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--baseline-ref", default=DEFAULT_BASELINE_REF)
    parser.add_argument("--nonce-file", type=Path, default=DEFAULT_NONCE_PATH)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_PATH)
    parser.add_argument(
        "--model-path",
        type=Path,
        default=(
            Path(os.environ["APPS_RG_EMBEDDING_MODEL_PATH"])
            if os.environ.get("APPS_RG_EMBEDDING_MODEL_PATH")
            else None
        ),
    )
    parser.add_argument("--device", default="cuda:0")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--init-nonce", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--check-receipt", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    nonce_path = _assert_runtime_path(repo_root, args.nonce_file, "nonce file")
    packet_dir = _assert_runtime_path(repo_root, args.packet_dir, "packet directory")
    if args.init_nonce:
        print(json.dumps(_initialize_nonce(nonce_path), indent=2))
        return 0

    contract = _load_json(repo_root / CONTRACT_PATH)
    validate_review_packet_contract(contract)
    query_manifest, registry, w7_receipt, generation, projection_path = _load_authority(
        repo_root, args.baseline_ref
    )
    receipt_path = repo_root / W8_RECEIPT_PATH

    if args.check_receipt:
        receipt = _load_json(receipt_path)
        _validate_receipt_sources(
            receipt=receipt,
            contract=contract,
            w7_receipt=w7_receipt,
            baseline_ref=args.baseline_ref,
            repo_root=repo_root,
        )
        packet_manifest = None
    elif args.write:
        if receipt_path.exists():
            raise SystemExit("W8 receipt already exists; use --check")
        if args.model_path is None:
            raise SystemExit(
                "--model-path or APPS_RG_EMBEDDING_MODEL_PATH is required for --write"
            )
        nonce = _read_nonce(nonce_path)
        rankings, runtime_proof = _compute_frozen_rankings(
            repo_root=repo_root,
            query_manifest=query_manifest,
            registry=registry,
            w7_receipt=w7_receipt,
            generation=generation,
            projection_path=projection_path,
            model_path=args.model_path.resolve(),
            device=args.device,
        )
        bindings = {
            "wave7_receipt_sha256": w7_receipt["receipt_sha256"],
            "query_manifest_sha256": query_manifest["query_manifest_sha256"],
            "registry_sha256": registry["registry_sha256"],
            "projection_generation_sha256": generation["projection"][
                "generation_sha256"
            ],
        }
        content = build_prelabel_packet_content(
            query_manifest=query_manifest,
            registry=registry,
            rankings=rankings,
            ranking_identity_sha256=ranking_identity_sha256(rankings),
            authority_bindings=bindings,
            blinding_nonce=nonce,
            repository_root=repo_root,
        )
        packet_manifest, packet_manifest_file_sha256 = _write_packet(
            packet_dir=packet_dir, content=content, runtime_proof=runtime_proof
        )
        on_disk_manifest = _validate_written_packet(
            packet_dir=packet_dir,
            query_manifest=query_manifest,
            registry=registry,
            expected_w7_receipt=w7_receipt,
        )
        if on_disk_manifest != packet_manifest:
            raise SystemExit("W8 on-disk packet differs from the generated manifest")
        receipt = build_w8_receipt(
            contract=contract,
            w7_receipt=w7_receipt,
            packet_manifest=packet_manifest,
            packet_manifest_file_sha256=packet_manifest_file_sha256,
            source_commit=args.baseline_ref,
            source_tree=_git_value(repo_root, "rev-parse", f"{args.baseline_ref}^{{tree}}"),
        )
        _write_new_json(receipt_path, receipt)
    else:
        if not receipt_path.is_file():
            raise SystemExit("W8 receipt is missing")
        receipt = _load_json(receipt_path)
        _validate_receipt_sources(
            receipt=receipt,
            contract=contract,
            w7_receipt=w7_receipt,
            baseline_ref=args.baseline_ref,
            repo_root=repo_root,
        )
        packet_manifest = _validate_written_packet(
            packet_dir=packet_dir,
            query_manifest=query_manifest,
            registry=registry,
            expected_w7_receipt=w7_receipt,
        )
        if _file_sha256(packet_dir / "packet_manifest.v1.json") != receipt[
            "controlled_packet"
        ]["packet_manifest_file_sha256"]:
            raise SystemExit("controlled packet does not match the committed receipt")

    output = {
        "status": receipt["status"],
        "wave": "W8",
        "packet_verified": packet_manifest is not None,
        "query_section_count_per_cohort": receipt["controlled_packet"][
            "query_section_count_per_cohort"
        ],
        "candidate_judgment_count_per_cohort": receipt["controlled_packet"][
            "candidate_judgment_count_per_cohort"
        ],
        "total_reviewer_judgment_slots": receipt["controlled_packet"][
            "total_reviewer_judgment_slots"
        ],
        "human_labels_present": receipt["label_authority"]["human_labels_present"],
        "semantic_retrieval_qualified": receipt["scope"][
            "semantic_retrieval_qualified"
        ],
        "production_promotion": receipt["wave_exit_gates"]["production_promotion"],
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
