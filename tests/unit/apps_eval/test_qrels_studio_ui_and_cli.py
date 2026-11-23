"""Unit and live localhost HTTP tests for Pure-White QRELS Studio UI, 1-by-1 chat panel, and legacy UI parity."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from apps_eval.qrels.qrels_human_store import (
    ExternalQrelsHumanStore,
    validate_human_qrels_annotator_id,
)
from apps_eval.qrels.qrels_rubric_contract import BLIND_FORBIDDEN_FIELDS
from apps_eval.qrels.qrels_studio_server import create_qrels_studio_server
from apps_eval.qrels.qrels_studio_template import QRELS_STUDIO_HTML
from ops_scripts.qrels_calibration_cli import (
    cmd_anchor_chat,
    format_one_by_one_blind_qrels_chat_panel,
    main as cli_main,
    parse_four_passage_chat_reply,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RUBRIC_PATH = REPO_ROOT / "config/governance/external_qrels_rubric_v1.json"


def _sample_pool_payload() -> dict[str, Any]:
    return {
        "surface": "candidate_graph",
        "presentation_seed": 42,
        "queries": [
            {
                "query_id": "q_01",
                "query_text": "Which governed AI control plane generated $22M IP revenue?",
                "topic_id": "topic_01",
                "topic_family": "topic_01",
                "surface": "resume_graph_engine",
                "target_section": "executive_summary",
                "partition": "calibration",
                "answerable": True,
                "target_record_id": "fact_1",
                "candidates": [
                    {
                        "pair_id": f"q_01::fact_{i}",
                        "record_id": f"fact_{i}",
                        "surface": "resume_graph_engine",
                        "title": f"Fact {i}",
                        "core_statement": f"Core evidence statement {i} dated 10/15/2026.",
                        "boilerplate_footer": f"Scope: Repeated organizational hierarchy {i}.",
                        "source_evidence_excerpts": [{"source": "Graph Fact", "date": "10/15/2026", "excerpt": f"Linked excerpt {i}"}],
                        "artifact_sha256": f"{i:064x}",
                        "dense_rank": i,
                        "bm25_rank": 5 - i,
                        "fused_rank": i,
                        "fused_score": round(0.1 / i, 4),
                    }
                    for i in range(1, 5)
                ],
            }
        ],
    }


def _http_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, dict[str, str], dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, dict(resp.headers.items()), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers.items()), json.loads(err.read().decode("utf-8"))


def test_qrels_studio_live_http_pure_white_blinding_and_fail_closed_locks(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.json"
    store_path = tmp_path / "store.json"
    pool_path.write_text(json.dumps(_sample_pool_payload()), encoding="utf-8")

    server = create_qrels_studio_server(
        pool_path,
        store_path=store_path,
        rubric_path=RUBRIC_PATH,
        port=0,
        annotator_id="amit.ayer",
        seed=42,
    )
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
            html_body = resp.read().decode("utf-8")
            cc = resp.headers.get("Cache-Control", "")
            assert resp.status == 200
            assert "no-store" in cc and "no-cache" in cc
            assert "background: #ffffff !important" in html_body
            assert 'content="light only"' in html_body
            assert "Quick Start Guide" in html_body
            assert "Reference Only: Repeated Scope &amp; Boilerplate Footer (do not grade)" in html_body
            assert "1-Click" not in html_body
            assert "#f5f7fb" not in html_body

        st, headers, state = _http_json(f"http://127.0.0.1:{port}/api/state")
        assert st == 200
        assert "no-store" in headers.get("Cache-Control", "")
        assert len(state["items"]) == 4
        for item in state["items"]:
            assert not (set(item.keys()) & BLIND_FORBIDDEN_FIELDS)

        first = state["items"][0]
        # Fail-closed: Grade 0 without rejection tag or >= 8 char rationale
        st_bad0, _, body_bad0 = _http_json(
            f"http://127.0.0.1:{port}/api/grade",
            method="POST",
            payload={
                "pair_id": first["pair_id"],
                "query_id": first["query_id"],
                "record_id": first["record_id"],
                "surface": first["surface"],
                "topic_family": first["topic_family"],
                "partition": first["partition"],
                "artifact_sha256": first["artifact_sha256"],
                "relevance_grade": 0,
                "rejection_tags": [],
                "notes": "no",
            },
        )
        assert st_bad0 == 400
        assert "Grade 0 requires" in body_bad0["error"]

        # Fail-closed: Grade 3 when not_boilerplate_stub is False
        st_bad3, _, body_bad3 = _http_json(
            f"http://127.0.0.1:{port}/api/grade",
            method="POST",
            payload={
                "pair_id": first["pair_id"],
                "query_id": first["query_id"],
                "record_id": first["record_id"],
                "surface": first["surface"],
                "topic_family": first["topic_family"],
                "partition": first["partition"],
                "artifact_sha256": first["artifact_sha256"],
                "relevance_grade": 3,
                "atomic_checks": {"not_boilerplate_stub": False},
            },
        )
        assert st_bad3 == 400
        assert "Maximum permitted grade is 1" in body_bad3["error"]

        # Valid Grade 3 submission
        st_ok, _, body_ok = _http_json(
            f"http://127.0.0.1:{port}/api/grade",
            method="POST",
            payload={
                "pair_id": first["pair_id"],
                "query_id": first["query_id"],
                "record_id": first["record_id"],
                "surface": first["surface"],
                "topic_family": first["topic_family"],
                "partition": first["partition"],
                "artifact_sha256": first["artifact_sha256"],
                "relevance_grade": 3,
                "atomic_checks": {"core_answers_query": True, "not_boilerplate_stub": True},
                "notes": "Direct concrete answer",
            },
        )
        assert st_ok == 200
        assert body_ok["record"]["relevance_grade"] == 3

        # Quarantine second item cleanly without contaminating load_records()
        second = state["items"][1]
        st_q, _, body_q = _http_json(
            f"http://127.0.0.1:{port}/api/quarantine",
            method="POST",
            payload={
                "pair_id": second["pair_id"],
                "query_id": second["query_id"],
                "record_id": second["record_id"],
                "surface": second["surface"],
                "topic_family": second["topic_family"],
                "partition": second["partition"],
                "artifact_sha256": second["artifact_sha256"],
                "reason": "ABSTAIN_INSUFFICIENT_EVIDENCE",
                "notes": "Excerpts missing employer date",
            },
        )
        assert st_q == 200
        assert body_q["quarantined"]["reason"] == "ABSTAIN_INSUFFICIENT_EVIDENCE"

        store = ExternalQrelsHumanStore(store_path, rubric_path=RUBRIC_PATH)
        assert store.verify_integrity() is True
        assert len(store.load_records()) == 1
        assert len(store.load_quarantined()) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_human_store_rejects_synthetic_annotator_and_tamper(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Synthetic or automated"):
        validate_human_qrels_annotator_id("llm_auto_judge")

    store_path = tmp_path / "tamper.json"
    store = ExternalQrelsHumanStore(store_path, rubric_path=RUBRIC_PATH)
    store.append_grade(
        {
            "pair_id": "q1::r1",
            "query_id": "q1",
            "record_id": "r1",
            "artifact_sha256": "a" * 64,
            "relevance_grade": 2,
            "annotator_id": "amit.ayer",
            "graded_at_utc": "2026-11-23T06:15:00Z",
        }
    )
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    raw["records"][0]["relevance_grade"] = 3
    store_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="tamper detected"):
        store.load_records()


def test_one_by_one_blind_four_passage_chat_cli_and_reply_parser(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.json"
    store_path = tmp_path / "cli_store.json"
    pool_path.write_text(json.dumps(_sample_pool_payload()), encoding="utf-8")

    res = cmd_anchor_chat(pool_path, "q_01", seed=42)
    md = res["markdown"]
    assert "| **3** | **Authoritative / Perfect**" in md
    assert "#### Passage A" in md and "#### Passage D" in md
    assert "Reference Only (do not grade):" in md
    assert "dense_rank" not in md and "fused_rank" not in md

    parsed = parse_four_passage_chat_reply("A=3, B=1, C=0, D=2")
    assert parsed == {"A": 3, "B": 1, "C": 0, "D": 2}
    with pytest.raises(ValueError, match="All four slots"):
        parse_four_passage_chat_reply("A=3, B=1")

    rc = cli_main(
        [
            "qrels-grade",
            "--query-id",
            "q_01",
            "--record-id",
            "fact_1",
            "--artifact-sha256",
            "1" * 64,
            "--grade",
            "0",
            "--rejection-tags",
            "LEXICAL_CONFOUNDER_TRAP",
            "--store",
            str(store_path),
            "--rubric",
            str(RUBRIC_PATH),
        ]
    )
    assert rc == 0
    assert cli_main(["qrels-verify-rubric", "--rubric", str(RUBRIC_PATH)]) == 0
    assert "Blind QRELS Relevance Calibration Studio" in QRELS_STUDIO_HTML
    assert format_one_by_one_blind_qrels_chat_panel(
        {"query_text": "Q?", "passages": [{"slot": "A", "core_statement": "Core"}]}
    )
