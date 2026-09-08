"""Validate the new rendered-unit retrieval-QREL registry before owner review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.owner_solo.c03_rendered_unit_qrel import (  # noqa: E402
    RenderedUnitQrelError,
    _active_events,
    _read_jsonl,
    append_human_judgments,
    build_blinded_packet,
    build_packet_successor_transition,
    finalize_owner_solo_qrels,
    freeze_blinded_packet,
    load_contract,
    materialize_registry_from_w3,
    reconcile_prior_labels,
    resolved_active_events,
    validate_frozen_packet,
    validate_registry_file,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path, nargs="?", help="Frozen rendered-unit registry JSON")
    parser.add_argument("command", choices=("materialize-w3", "reconcile-brown-brown", "freeze-packet", "successor-transition", "validate", "status", "record", "finalize"), nargs="?", default="validate")
    parser.add_argument("--receipt", type=Path, help="Optional ignored readiness receipt path")
    parser.add_argument("--ledger", type=Path, default=REPO_ROOT / ".runtime/c03-rendered-unit-qrel/owner_events.jsonl")
    parser.add_argument("--item-ref")
    parser.add_argument("--candidate-ref")
    parser.add_argument("--grade", type=int)
    parser.add_argument("--rationale")
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--w3-review-items", type=Path)
    parser.add_argument("--w3-sealed-mapping", type=Path)
    parser.add_argument("--combined-registry", type=Path)
    parser.add_argument(
        "--competency-registry",
        type=Path,
        default=REPO_ROOT / "src/apps_rg/fact_inventory/competency_capability_bundles.json",
    )
    parser.add_argument("--output-registry", type=Path)
    parser.add_argument("--prior-reconciliation", type=Path)
    parser.add_argument("--confirmation-queue", type=Path)
    parser.add_argument("--reviewer-packet", type=Path)
    parser.add_argument("--sealed-mapping-output", type=Path)
    parser.add_argument("--sealed-mapping-input", type=Path)
    parser.add_argument("--transition", type=Path)
    parser.add_argument("--predecessor-packet", type=Path)
    parser.add_argument("--predecessor-sealed-mapping", type=Path)
    parser.add_argument("--predecessor-ledger", type=Path)
    parser.add_argument("--predecessor-transition", type=Path)
    parser.add_argument("--ancestor-packet", type=Path)
    parser.add_argument("--ancestor-ledger", type=Path)
    parser.add_argument("--ancestor-transition", type=Path)
    parser.add_argument("--root-packet", type=Path)
    parser.add_argument("--root-ledger", type=Path)
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    # Permit the natural materialization command without a meaningless registry
    # positional argument; the registry does not exist until this command writes it.
    if raw_argv and raw_argv[0] == "materialize-w3":
        raw_argv = ["_", *raw_argv]
    elif raw_argv and raw_argv[0] in {"reconcile-brown-brown", "freeze-packet", "successor-transition"}:
        if len(raw_argv) < 2 or raw_argv[1].startswith("-"):
            parser.error(f"{raw_argv[0]} requires a rendered-unit registry path")
        raw_argv = [raw_argv[1], raw_argv[0], *raw_argv[2:]]
    args = parser.parse_args(raw_argv)
    if args.command == "materialize-w3":
        if not all((args.w3_review_items, args.w3_sealed_mapping, args.combined_registry, args.output_registry)):
            parser.error("materialize-w3 requires --w3-review-items --w3-sealed-mapping --combined-registry --output-registry")
        try:
            review_items = [json.loads(line) for line in args.w3_review_items.read_text(encoding="utf-8").splitlines() if line.strip()]
            sealed = json.loads(args.w3_sealed_mapping.read_text(encoding="utf-8"))
            combined = json.loads(args.combined_registry.read_text(encoding="utf-8"))
            competency_registry = json.loads(args.competency_registry.read_text(encoding="utf-8"))
            registry = materialize_registry_from_w3(
                reviewer_items=review_items,
                sealed_mapping=sealed,
                combined_registry=combined,
                competency_registry=competency_registry,
            )
            args.output_registry.parent.mkdir(parents=True, exist_ok=True)
            args.output_registry.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
            issues = validate_registry_file(args.output_registry, repo_root=REPO_ROOT)
        except (OSError, json.JSONDecodeError, RenderedUnitQrelError) as exc:
            print(f"status=BLOCKED error={exc}")
            return 2
        print(json.dumps(issues, indent=2))
        return 0
    if args.command == "reconcile-brown-brown":
        if not all((args.registry, args.prior_reconciliation, args.w3_sealed_mapping, args.receipt, args.confirmation_queue)):
            parser.error("reconcile-brown-brown requires registry, --prior-reconciliation, --w3-sealed-mapping, --receipt, and --confirmation-queue")
        try:
            registry = json.loads(args.registry.read_text(encoding="utf-8"))
            prior = json.loads(args.prior_reconciliation.read_text(encoding="utf-8"))
            sealed = json.loads(args.w3_sealed_mapping.read_text(encoding="utf-8"))
            receipt, queue = reconcile_prior_labels(prior_reconciliation=prior, registry=registry, w8_sealed_mapping=sealed)
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.confirmation_queue.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            args.confirmation_queue.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError, RenderedUnitQrelError) as exc:
            print(f"status=BLOCKED error={exc}")
            return 2
        print(json.dumps({key: receipt[key] for key in ("status", "prior_human_label_count", "exact_final_unit_owner_import_candidates", "same_graph_evidence_re_rate_candidates", "historical_rubric_only_count", "formal_qrels_created", "human_grades_transferred")}, indent=2))
        return 0
    if args.command == "freeze-packet":
        if not all((args.registry, args.reviewer_packet, args.sealed_mapping_output, args.receipt)):
            parser.error("freeze-packet requires registry, --reviewer-packet, --sealed-mapping-output, and --receipt")
        try:
            if args.ledger.exists() and _read_jsonl(args.ledger):
                raise RenderedUnitQrelError("Cannot freeze a replacement packet after owner judgments exist")
            registry = json.loads(args.registry.read_text(encoding="utf-8"))
            contract = load_contract(REPO_ROOT)
            packet, sealed, receipt = freeze_blinded_packet(registry=registry, contract=contract)
            for path, value in ((args.reviewer_packet, packet), (args.sealed_mapping_output, sealed), (args.receipt, receipt)):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError, RenderedUnitQrelError) as exc:
            print(f"status=BLOCKED error={exc}")
            return 2
        print(json.dumps({key: receipt[key] for key in ("status", "query_section_case_count", "candidate_judgment_count", "packet_sha256", "sealed_mapping_sha256", "rank_score_split_graph_embedding_hidden", "human_grades_created")}, indent=2))
        return 0
    if args.command == "successor-transition":
        required = (args.registry, args.reviewer_packet, args.sealed_mapping_input, args.predecessor_packet, args.predecessor_sealed_mapping, args.predecessor_ledger, args.transition)
        if not all(required):
            parser.error("successor-transition requires registry, --reviewer-packet, --sealed-mapping-input, --predecessor-packet, --predecessor-sealed-mapping, --predecessor-ledger, and --transition")
        try:
            successor_packet = json.loads(args.reviewer_packet.read_text(encoding="utf-8"))
            successor_sealed = json.loads(args.sealed_mapping_input.read_text(encoding="utf-8"))
            predecessor_packet = json.loads(args.predecessor_packet.read_text(encoding="utf-8"))
            predecessor_sealed = json.loads(args.predecessor_sealed_mapping.read_text(encoding="utf-8"))
            predecessor_events = _read_jsonl(args.predecessor_ledger)
            predecessor_active = None
            chain_args = (args.predecessor_transition, args.ancestor_packet, args.ancestor_ledger)
            if any(chain_args):
                if not all(chain_args):
                    raise RenderedUnitQrelError("A predecessor chain requires --predecessor-transition --ancestor-packet and --ancestor-ledger together")
                ancestor_packet = json.loads(args.ancestor_packet.read_text(encoding="utf-8"))
                ancestor_events = _read_jsonl(args.ancestor_ledger)
                ancestor_active = None
                root_args = (args.ancestor_transition, args.root_packet, args.root_ledger)
                if any(root_args):
                    if not all(root_args):
                        raise RenderedUnitQrelError("A root chain requires --ancestor-transition --root-packet and --root-ledger together")
                    ancestor_active = resolved_active_events(
                        successor_packet=ancestor_packet,
                        successor_events=ancestor_events,
                        transition=json.loads(args.ancestor_transition.read_text(encoding="utf-8")),
                        predecessor_packet=json.loads(args.root_packet.read_text(encoding="utf-8")),
                        predecessor_events=_read_jsonl(args.root_ledger),
                    )
                predecessor_active = resolved_active_events(
                    successor_packet=predecessor_packet,
                    successor_events=predecessor_events,
                    transition=json.loads(args.predecessor_transition.read_text(encoding="utf-8")),
                    predecessor_packet=ancestor_packet,
                    predecessor_events=ancestor_events,
                    predecessor_active_events=ancestor_active,
                )
            transition = build_packet_successor_transition(
                predecessor_packet=predecessor_packet,
                predecessor_sealed_mapping=predecessor_sealed,
                predecessor_events=predecessor_events,
                successor_packet=successor_packet,
                successor_sealed_mapping=successor_sealed,
                predecessor_active_events=predecessor_active,
            )
            args.transition.parent.mkdir(parents=True, exist_ok=True)
            args.transition.write_text(json.dumps(transition, indent=2) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError, RenderedUnitQrelError) as exc:
            print(f"status=BLOCKED error={exc}")
            return 2
        print(json.dumps({key: transition[key] for key in ("status", "preserved_prior_event_count", "byte_identical_carried_forward_count", "prior_events_requiring_explicit_regrade_count", "changed_rendered_unit_count_among_prior_events", "human_grades_created", "human_grades_transferred")}, indent=2))
        return 0
    if args.registry is None:
        parser.error("registry is required unless using materialize-w3")
    try:
        receipt = validate_registry_file(args.registry, repo_root=REPO_ROOT)
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        contract = load_contract(REPO_ROOT)
        if bool(args.reviewer_packet) != bool(args.sealed_mapping_input):
            raise RenderedUnitQrelError("Use both --reviewer-packet and --sealed-mapping-input, or neither")
        if args.reviewer_packet:
            packet = json.loads(args.reviewer_packet.read_text(encoding="utf-8"))
            sealed = json.loads(args.sealed_mapping_input.read_text(encoding="utf-8"))
            issues = validate_frozen_packet(registry=registry, contract=contract, packet=packet, sealed_mapping=sealed)
            if issues:
                raise RenderedUnitQrelError("Frozen reviewer packet is blocked: " + ", ".join(issues))
        else:
            packet, sealed = build_blinded_packet(registry, contract)
        events = _read_jsonl(args.ledger) if args.ledger.exists() else []
        transition = None
        predecessor_packet = None
        predecessor_events = []
        predecessor_active = None
        if any((args.transition, args.predecessor_packet, args.predecessor_ledger)):
            if not all((args.transition, args.predecessor_packet, args.predecessor_ledger)):
                raise RenderedUnitQrelError("Successor review requires --transition, --predecessor-packet, and --predecessor-ledger together")
            transition = json.loads(args.transition.read_text(encoding="utf-8"))
            predecessor_packet = json.loads(args.predecessor_packet.read_text(encoding="utf-8"))
            predecessor_events = _read_jsonl(args.predecessor_ledger)
            chain_args = (args.predecessor_transition, args.ancestor_packet, args.ancestor_ledger)
            if any(chain_args):
                if not all(chain_args):
                    raise RenderedUnitQrelError("A predecessor chain requires --predecessor-transition --ancestor-packet and --ancestor-ledger together")
                ancestor_packet = json.loads(args.ancestor_packet.read_text(encoding="utf-8"))
                ancestor_events = _read_jsonl(args.ancestor_ledger)
                ancestor_active = None
                root_args = (args.ancestor_transition, args.root_packet, args.root_ledger)
                if any(root_args):
                    if not all(root_args):
                        raise RenderedUnitQrelError("A root chain requires --ancestor-transition --root-packet and --root-ledger together")
                    ancestor_active = resolved_active_events(
                        successor_packet=ancestor_packet,
                        successor_events=ancestor_events,
                        transition=json.loads(args.ancestor_transition.read_text(encoding="utf-8")),
                        predecessor_packet=json.loads(args.root_packet.read_text(encoding="utf-8")),
                        predecessor_events=_read_jsonl(args.root_ledger),
                    )
                predecessor_active = resolved_active_events(
                    successor_packet=predecessor_packet,
                    successor_events=predecessor_events,
                    transition=json.loads(args.predecessor_transition.read_text(encoding="utf-8")),
                    predecessor_packet=ancestor_packet,
                    predecessor_events=ancestor_events,
                    predecessor_active_events=ancestor_active,
                )
        active = resolved_active_events(successor_packet=packet, successor_events=events, transition=transition, predecessor_packet=predecessor_packet, predecessor_events=predecessor_events, predecessor_active_events=predecessor_active)
    except RenderedUnitQrelError as exc:
        print(f"status=BLOCKED error={exc}")
        return 2
    if args.command == "record":
        if not args.item_ref or not args.candidate_ref or args.grade is None or not args.rationale:
            parser.error("record requires --item-ref --candidate-ref --grade and --rationale")
        append_human_judgments(args.ledger, packet=packet, submissions=[{"item_ref": args.item_ref, "candidate_ref": args.candidate_ref, "grade": args.grade, "rationale": args.rationale}])
        events = _read_jsonl(args.ledger)
        active = resolved_active_events(successor_packet=packet, successor_events=events, transition=transition, predecessor_packet=predecessor_packet, predecessor_events=predecessor_events, predecessor_active_events=predecessor_active)
    if args.command == "finalize":
        artifact = finalize_owner_solo_qrels(registry=registry, contract=contract, packet=packet, sealed_mapping=sealed, events=events, active_events=active)
        if args.artifact is None:
            parser.error("finalize requires --artifact <ignored output path>")
        args.artifact.parent.mkdir(parents=True, exist_ok=True)
        args.artifact.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(artifact, indent=2))
        return 0
    output = {**receipt, "completed_human_judgment_count": len(active), "remaining_human_judgment_count": receipt["candidate_judgment_count"] - len(active), "packet_sha256": packet["packet_sha256"]}
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
