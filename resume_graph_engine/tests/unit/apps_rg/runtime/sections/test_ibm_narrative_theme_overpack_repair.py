"""ibm_narrative theme-overpack repair rung (live flap postW4fix_20260610_2200).

Structural math: the clause decomposer splits on ', establishing' (maxsplit=1 → max 2 ledger
rows) and clause-decomposition allows max 2 bul_ibm_* roots per row → ledger union ≤ 4 roots.
A narrative tripping 5 theme triggers can NEVER pass both x2_ibm_narrative_claim_theme_coverage
and x2_ibm_narrative_claim_ledger_clause_decomposition. The bounded same-authority rung also
repairs mechanism-only support failures, with fail-closed acceptance; gates unchanged.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from apps_rg.runtime.sections import ibm_narrative_lane_runtime as lane_runtime
from apps_rg.runtime.section_model_limits import resolve_section_generation_model
from apps_rg.runtime.sections.ibm_narrative_lane_defaults import NARRATIVE_MAX_OUTPUT_TOKENS
from apps_rg.runtime.validators.ibm_narrative_x2 import (
    check_ibm_narrative_claim_ledger_clause_decomposition,
    ibm_narrative_material_fact_ids_for_sentence,
)

_RECEIPT = lane_runtime.THEME_REPAIR_RECEIPT_FILENAME
ALL_IBM_POOL = ["bul_ibm_001", "bul_ibm_002", "bul_ibm_003", "bul_ibm_004", "bul_ibm_005"]


def test_attempt1_lane_cap_has_headroom_beyond_live_truncation() -> None:
    """Live postRungs_20260610_2246 hit max_tokens at the old 1200 cap on attempt 1."""
    assert NARRATIVE_MAX_OUTPUT_TOKENS >= 4000

# 5-theme overpack (today's flap shape): clause 1 trips 001/002/004, clause 2 trips 003/005.
OVERPACK_CLAUSE_1 = (
    "At IBM led cloud modernization, lineage and observability programs "
    "for regulated financial services"
)
OVERPACK_CLAUSE_2 = (
    "establishing reusable platform discipline and hyperscaler partnership "
    "execution across complex delivery portfolios"
)
OVERPACK_NARRATIVE = f"{OVERPACK_CLAUSE_1}, {OVERPACK_CLAUSE_2}."

# 4-theme regen within budget: ≤2 theme families per clause (002/004 then 003/005).
GOOD_REGEN_NARRATIVE = (
    "At IBM led cloud modernization and data lineage programs across complex institutions, "
    "establishing reusable platform discipline and hyperscaler partnership execution "
    "for governed delivery."
)

# 3 themes but single clause (no ', establishing') — one row, max 2 roots → coverage must miss one.
SINGLE_CLAUSE_3_THEME_NARRATIVE = (
    "At IBM led cloud modernization with data lineage and hyperscaler partnership programs."
)


def _post_chain_overpack_ledger() -> list[dict]:
    """Attempt-1 ledger as the deterministic chain leaves it: 2 rows, 2 roots each, 004 uncovered."""
    return [
        {"claim_text": OVERPACK_CLAUSE_1, "source_fact_ids": ["bul_ibm_001", "bul_ibm_002"]},
        {"claim_text": OVERPACK_CLAUSE_2, "source_fact_ids": ["bul_ibm_003", "bul_ibm_005"]},
    ]


def _attempt1_parsed(narrative: str = OVERPACK_NARRATIVE, ledger: list[dict] | None = None) -> dict:
    return {
        "narrative_sentence": narrative,
        "claim_ledger": _post_chain_overpack_ledger() if ledger is None else ledger,
        "selected_fact_plan": {"section_id": "ibm_narrative", "facts": []},
        "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
        "gap_notes": [],
        "change_log": [],
        "self_check": {},
    }


def _runtime_payload() -> dict:
    return {
        "run_id": "theme-repair-test",
        "allowed_fact_ids": list(ALL_IBM_POOL),
        "selected_fact_plan": {"section_id": "ibm_narrative", "facts": []},
        "proof_pool_metadata": {},
    }


def _regen_json(narrative: str) -> str:
    return json.dumps(
        {
            "narrative_sentence": narrative,
            "selected_fact_plan": {"section_id": "ibm_narrative", "facts": []},
            "claim_ledger": [],
            "jd_alignment": {"targeting_only": True},
            "gap_notes": [],
            "change_log": [],
            "self_check": {},
        }
    )


class _RecordingProvider:
    def __init__(self, status: str, raw: str | list[str]) -> None:
        self.status = status
        self.raws = list(raw) if isinstance(raw, list) else [raw]
        self.calls = 0
        self.payloads: list[dict] = []

    def __call__(self, payload: dict, **kwargs) -> SimpleNamespace:
        self.calls += 1
        self.last_payload = payload
        self.payloads.append(payload)
        self.last_kwargs = kwargs
        raw = self.raws[min(self.calls - 1, len(self.raws) - 1)]
        return SimpleNamespace(
            runtime_generation_status=self.status,
            raw_model_output=raw,
            provider_requested="external_openai",
            provider_attempted=self.status == "REAL_LLM",
            provider_available=self.status == "REAL_LLM",
            model=resolve_section_generation_model("ibm_narrative"),
            exact_provider_error="" if self.status == "REAL_LLM" else "blocked",
        )


def _run_rung(
    tmp_path,
    monkeypatch,
    *,
    provider,
    parsed,
    runtime_payload=None,
    runtime_generation_status="REAL_LLM",
    raw_output=None,
    companion_text="",
):
    monkeypatch.setattr(lane_runtime, "generate_section", provider)
    payload = runtime_payload if runtime_payload is not None else _runtime_payload()
    if raw_output is None:
        raw_output = json.dumps(parsed, sort_keys=True) if isinstance(parsed, dict) else ""
    return lane_runtime.apply_ibm_narrative_theme_overpack_repair(
        messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        provider_payload={"messages": [], "temperature": 0.35},
        raw_output=raw_output,
        parsed=parsed,
        runtime_payload=payload,
        artifact_dir=tmp_path,
        runtime_generation_status=runtime_generation_status,
        companion_text=companion_text,
    )


def _read_receipt(tmp_path) -> dict:
    return json.loads((tmp_path / _RECEIPT).read_text(encoding="utf-8"))


def test_fixture_sentences_have_expected_theme_counts() -> None:
    """Structural premise of the suite: 5-theme overpack, 4-theme regen, 3-theme single clause."""
    assert ibm_narrative_material_fact_ids_for_sentence(OVERPACK_NARRATIVE) == frozenset(
        ALL_IBM_POOL
    )
    assert ibm_narrative_material_fact_ids_for_sentence(GOOD_REGEN_NARRATIVE) == frozenset(
        {"bul_ibm_002", "bul_ibm_003", "bul_ibm_004", "bul_ibm_005"}
    )
    assert ibm_narrative_material_fact_ids_for_sentence(
        SINGLE_CLAUSE_3_THEME_NARRATIVE
    ) == frozenset({"bul_ibm_002", "bul_ibm_004", "bul_ibm_005"})


def test_regen_sanitizer_removes_only_unsupported_companion_theme_words() -> None:
    companion = (
        "- bul_ibm_001: Led IBM-AWS alliance co-sell motions for financial-services modernization.\n"
        "- bul_ibm_002: Applied pipeline discipline to client portfolio expansion motions.\n"
        "- bul_ibm_003: Built decision-support data models and BI views."
    )
    parsed = {
        "narrative_sentence": (
            "Championed AWS alliance leadership at IBM, establishing pipeline discipline "
            "across regulated financial-services portfolios and partner ecosystems at scale."
        ),
        "change_log": [],
    }

    out = lane_runtime._sanitize_regen_unsupported_companion_theme_phrases(
        parsed,
        companion,
    )

    narrative = out["narrative_sentence"]
    assert "regulated financial" not in narrative.lower()
    assert "ecosystem" not in narrative.lower()
    themes = ibm_narrative_material_fact_ids_for_sentence(narrative, companion)
    assert not [value for value in themes if value.startswith("unsupported_companion_theme:")]
    assert "financial-services" in narrative
    assert any(
        row.get("operation") == "sanitize_regen_unsupported_companion_theme_phrases"
        for row in out["change_log"]
    )


class TestThemeOverpackRepairRung:
    @pytest.fixture(autouse=True)
    def _default_kill_switch_on(self, monkeypatch):
        monkeypatch.delenv("APPS_RG_IBM_NARRATIVE_THEME_REPAIR", raising=False)

    def test_trigger_skips_non_real_llm(self, tmp_path, monkeypatch):
        provider = _RecordingProvider("REAL_LLM", _regen_json(GOOD_REGEN_NARRATIVE))
        _raw, out, accepted = _run_rung(
            tmp_path,
            monkeypatch,
            provider=provider,
            parsed=_attempt1_parsed(),
            runtime_generation_status="MOCKED",
        )
        assert provider.calls == 0
        assert not accepted
        assert not (tmp_path / _RECEIPT).exists()

    def test_trigger_skips_when_themes_within_budget_and_covered(self, tmp_path, monkeypatch):
        provider = _RecordingProvider("REAL_LLM", _regen_json(GOOD_REGEN_NARRATIVE))
        parsed = _attempt1_parsed(
            GOOD_REGEN_NARRATIVE,
            ledger=[
                {
                    "claim_text": "At IBM led cloud modernization and data lineage programs",
                    "source_fact_ids": ["bul_ibm_002", "bul_ibm_004"],
                },
                {
                    "claim_text": "establishing reusable platform discipline and hyperscaler partnership execution",
                    "source_fact_ids": ["bul_ibm_003", "bul_ibm_005"],
                },
            ],
        )
        _raw, out, accepted = _run_rung(tmp_path, monkeypatch, provider=provider, parsed=parsed)
        assert provider.calls == 0
        assert not accepted and out is parsed
        assert not (tmp_path / _RECEIPT).exists()

    def test_trigger_skips_srfs_membership_mode(self, tmp_path, monkeypatch):
        import apps_rg.runtime.validators.proof_pool_source_fact_validation as ppv

        monkeypatch.setattr(ppv, "proof_source_from_metadata", lambda _m: "srfs")
        provider = _RecordingProvider("REAL_LLM", _regen_json(GOOD_REGEN_NARRATIVE))
        _raw, out, accepted = _run_rung(
            tmp_path, monkeypatch, provider=provider, parsed=_attempt1_parsed()
        )
        assert provider.calls == 0
        assert not accepted
        assert not (tmp_path / _RECEIPT).exists()

    def test_kill_switch_off_makes_zero_calls_with_receipt(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPS_RG_IBM_NARRATIVE_THEME_REPAIR", "0")
        provider = _RecordingProvider("REAL_LLM", _regen_json(GOOD_REGEN_NARRATIVE))
        parsed = _attempt1_parsed()
        _raw, out, accepted = _run_rung(tmp_path, monkeypatch, provider=provider, parsed=parsed)
        assert provider.calls == 0
        assert not accepted and out is parsed
        receipt = _read_receipt(tmp_path)
        assert receipt["fired"] is False
        assert receipt["rejected_reason"] == "kill_switch_off"
        assert receipt["kill_switch"] == "0"
        assert receipt["bounded"] == {"max_attempts": 2, "attempts_used": 0}
        assert receipt["trigger"]["count_pre"] == 5
        assert receipt["trigger"]["themes_detected_pre"] == ALL_IBM_POOL
        assert receipt["trigger"]["missing_in_ledger_union_pre"] == ["bul_ibm_004"]

    def test_budget_consumed_by_prior_ledger_regen(self, tmp_path, monkeypatch):
        from apps_rg.runtime.section_repair_ledger import (
            KIND_REGEN_LLM,
            init_ledger,
            record_repair,
        )

        init_ledger(tmp_path, section_id="ibm_narrative", run_id="theme-repair-test")
        record_repair(
            tmp_path,
            kind=KIND_REGEN_LLM,
            operation="companion_metric_budget_regen",
            replaced_l2=True,
        )
        provider = _RecordingProvider("REAL_LLM", _regen_json(GOOD_REGEN_NARRATIVE))
        _raw, out, accepted = _run_rung(
            tmp_path, monkeypatch, provider=provider, parsed=_attempt1_parsed()
        )
        assert provider.calls == 0
        assert not accepted
        receipt = _read_receipt(tmp_path)
        assert receipt["rejected_reason"] == "regen_budget_consumed"
        assert receipt["fired"] is False

    def test_accept_path_swaps_output_records_regen_and_passes_both_predicates(
        self, tmp_path, monkeypatch
    ):
        from apps_rg.runtime.section_repair_ledger import KIND_REGEN_LLM, init_ledger, load_ledger
        from tests.unit.apps_rg.section_rigor.repair_authority import (
            assert_single_repair_authority_path,
        )

        init_ledger(tmp_path, section_id="ibm_narrative", run_id="theme-repair-test")
        provider = _RecordingProvider("REAL_LLM", _regen_json(GOOD_REGEN_NARRATIVE))
        raw, out, accepted = _run_rung(
            tmp_path, monkeypatch, provider=provider, parsed=_attempt1_parsed()
        )
        assert provider.calls == 1
        assert provider.last_kwargs == {
            "artifact_dir": tmp_path,
            "run_id": "theme-repair-test",
        }
        assert accepted is True
        narrative_post = str(out["narrative_sentence"]).strip()
        themes_post = ibm_narrative_material_fact_ids_for_sentence(narrative_post)
        assert len(themes_post) <= 4
        rows = [r for r in out["claim_ledger"] if isinstance(r, dict)]
        cited = {
            str(s).split("_metric_")[0]
            for r in rows
            for s in (r.get("source_fact_ids") or [])
        }
        assert themes_post <= cited  # theme-coverage predicate
        ok, detail = check_ibm_narrative_claim_ledger_clause_decomposition(narrative_post, rows)
        assert ok is True, detail  # clause-decomposition predicate
        ledger = load_ledger(tmp_path) or {}
        regen_rows = [
            r
            for r in (ledger.get("repairs") or [])
            if r.get("kind") == KIND_REGEN_LLM and r.get("replaced_l2")
        ]
        assert len(regen_rows) == 1
        assert regen_rows[0]["operation"] == "ibm_narrative_theme_overpack_repair"
        ok_auth, reason = assert_single_repair_authority_path(ledger)
        assert ok_auth, reason
        receipt = _read_receipt(tmp_path)
        assert receipt["fired"] is True
        assert receipt["accepted"] is True
        assert receipt["rejected_reason"] is None
        assert receipt["bounded"] == {"max_attempts": 2, "attempts_used": 1}
        assert receipt["themes_post"] == sorted(themes_post)
        assert any(
            e.get("operation") == "ibm_narrative_theme_overpack_repair"
            for e in (out.get("change_log") or [])
        )
        # Precise-miss feedback reached the provider.
        regen_user_msg = provider.last_payload["messages"][-1]["content"]
        assert "5 theme families" in regen_user_msg
        assert "at most 2 per" in regen_user_msg.lower()
        assert "', establishing'" in regen_user_msg
        # postRungs_20260610_2246 fix: regen mirrors attempt 1's proven parse-retry output
        # contract (compact JSON, same key list) instead of "one full JSON object".
        assert "compact JSON object" in regen_user_msg
        assert "narrative_sentence (one sentence), selected_fact_plan" in regen_user_msg
        # Regen cap is floored at the lane default and recorded in the receipt.
        assert provider.last_payload["max_tokens"] >= lane_runtime.NARRATIVE_MAX_OUTPUT_TOKENS
        assert receipt["regen_max_tokens"] == provider.last_payload["max_tokens"]
        # Regen raw response is persisted and referenced even on accept.
        ref = receipt["regen_raw_response_ref"]
        assert ref == lane_runtime.THEME_REPAIR_REGEN_RAW_FILENAME
        assert (tmp_path / ref).read_text(encoding="utf-8") == _regen_json(
            GOOD_REGEN_NARRATIVE
        )
        assert receipt["regen_parse_error"] is None
        assert receipt["regen_provider_result"] == {
            "runtime_generation_status": "REAL_LLM",
            "provider_requested": "external_openai",
            "provider_attempted": True,
            "provider_available": True,
            "model": resolve_section_generation_model("ibm_narrative"),
            "exact_provider_error": "",
        }

    def test_reject_themes_still_overpacked_keeps_attempt1(self, tmp_path, monkeypatch):
        from apps_rg.runtime.section_repair_ledger import KIND_REGEN_LLM, init_ledger, load_ledger

        init_ledger(tmp_path, section_id="ibm_narrative", run_id="theme-repair-test")
        provider = _RecordingProvider("REAL_LLM", _regen_json(OVERPACK_NARRATIVE))
        parsed = _attempt1_parsed()
        _raw, out, accepted = _run_rung(tmp_path, monkeypatch, provider=provider, parsed=parsed)
        assert provider.calls == 1
        assert not accepted and out is parsed
        assert out["narrative_sentence"] == OVERPACK_NARRATIVE
        receipt = _read_receipt(tmp_path)
        assert receipt["rejected_reason"] == "themes_still_overpacked"
        assert receipt["fired"] is True
        assert receipt["accepted"] is False
        ledger = load_ledger(tmp_path) or {}
        assert not [
            r for r in (ledger.get("repairs") or []) if r.get("kind") == KIND_REGEN_LLM
        ]

    def test_second_attempt_corrects_cited_companion_mechanism_support(
        self, tmp_path, monkeypatch
    ):
        from apps_rg.runtime.section_repair_ledger import init_ledger

        companion = (
            "- bul_ibm_001: Led IBM-AWS alliance co-sell motions.\n"
            "- bul_ibm_002: Built decision-support BI views.\n"
            "- bul_ibm_003: Led technical discovery and solution architecture.\n"
            "- bul_ibm_004: Owned pipeline governance across enterprise pursuits.\n"
            "- bul_ibm_005: Architected cloud modernization reference architectures."
        )
        bad = (
            "Drove AWS alliance and solution architecture across enterprise client pursuits at "
            "IBM, establishing a BI and microservices operating discipline for repeatable growth."
        )
        good = (
            "Drove AWS alliance and solution architecture across enterprise client pursuits at "
            "IBM, establishing a BI operating discipline for repeatable growth."
        )

        def candidate(narrative: str) -> str:
            opening, closing = narrative.split(", establishing ", 1)
            return json.dumps(
                {
                    "narrative_sentence": narrative,
                    "selected_fact_plan": {"section_id": "ibm_narrative", "facts": []},
                    "claim_ledger": [
                        {"claim_text": opening, "source_fact_ids": ["bul_ibm_001"]},
                        {
                            "claim_text": "establishing " + closing.rstrip("."),
                            "source_fact_ids": ["bul_ibm_002"],
                        },
                    ],
                    "jd_alignment": {"targeting_only": True},
                    "gap_notes": [],
                    "change_log": [],
                    "self_check": {},
                }
            )

        init_ledger(tmp_path, section_id="ibm_narrative", run_id="theme-repair-test")
        provider = _RecordingProvider("REAL_LLM", [candidate(bad), candidate(good)])
        _raw, out, accepted = _run_rung(
            tmp_path,
            monkeypatch,
            provider=provider,
            parsed=_attempt1_parsed(),
            companion_text=companion,
        )

        assert provider.calls == 2
        assert accepted is True
        assert "microservices" not in out["narrative_sentence"].lower()
        receipt = _read_receipt(tmp_path)
        assert receipt["bounded"] == {"max_attempts": 2, "attempts_used": 2}
        assert [row["rejected_reason"] for row in receipt["attempts"]] == [
            "mechanism_support_unsatisfied",
            None,
        ]
        assert "MECHANISM_CITATION_CORRECTION" in provider.payloads[1]["messages"][-1][
            "content"
        ]

    def test_mechanism_only_failure_triggers_same_authority_repair(
        self, tmp_path, monkeypatch
    ):
        """Live retry8: in-budget themes must not suppress the mechanism support rung."""
        from apps_rg.runtime.section_repair_ledger import init_ledger

        companion = (
            "- bul_ibm_001: Led IBM-AWS alliance co-sell motions.\n"
            "- bul_ibm_002: Built decision-support BI views.\n"
            "- bul_ibm_003: Led technical discovery and solution architecture.\n"
            "- bul_ibm_004: Owned pipeline governance across enterprise pursuits.\n"
            "- bul_ibm_005: Architected cloud modernization reference architectures."
        )
        initial_narrative = (
            "Drove AWS alliance work at IBM, establishing a pipeline for pursuits."
        )
        initial = _attempt1_parsed(
            initial_narrative,
            [
                {
                    "claim_text": "Drove AWS alliance work at IBM",
                    "source_fact_ids": ["bul_ibm_001"],
                },
                {
                    "claim_text": (
                        "establishing a pipeline for pursuits"
                    ),
                    "source_fact_ids": ["bul_ibm_001"],
                },
            ],
        )
        repaired_narrative = (
            "Drove AWS alliance and solution architecture across enterprise client pursuits at "
            "IBM, establishing a BI operating discipline for repeatable growth."
        )
        opening, closing = repaired_narrative.split(", establishing ", 1)
        repaired = json.dumps(
            {
                "narrative_sentence": repaired_narrative,
                "selected_fact_plan": {"section_id": "ibm_narrative", "facts": []},
                "claim_ledger": [
                    {"claim_text": opening, "source_fact_ids": ["bul_ibm_001"]},
                    {
                        "claim_text": "establishing " + closing.rstrip("."),
                        "source_fact_ids": ["bul_ibm_002"],
                    },
                ],
                "jd_alignment": {"targeting_only": True},
                "gap_notes": [],
                "change_log": [],
                "self_check": {},
            }
        )

        init_ledger(tmp_path, section_id="ibm_narrative", run_id="theme-repair-test")
        provider = _RecordingProvider("REAL_LLM", repaired)
        _raw, out, accepted = _run_rung(
            tmp_path,
            monkeypatch,
            provider=provider,
            parsed=initial,
            companion_text=companion,
        )

        assert provider.calls == 1
        assert accepted is True
        assert out["narrative_sentence"] == repaired_narrative
        receipt = _read_receipt(tmp_path)
        assert receipt["trigger"]["unsupported_mechanisms_pre"] == ["pipeline"]
        assert receipt["gate_id"] == (
            "x2_ibm_narrative_mechanisms_supported_by_cited_companion_bullets"
        )
        assert "MECHANISM_CITATION_REVISION" in provider.payloads[0]["messages"][-1][
            "content"
        ]

    def test_reject_theme_coverage_unsatisfied_keeps_attempt1(self, tmp_path, monkeypatch):
        provider = _RecordingProvider("REAL_LLM", _regen_json(SINGLE_CLAUSE_3_THEME_NARRATIVE))
        parsed = _attempt1_parsed()
        _raw, out, accepted = _run_rung(tmp_path, monkeypatch, provider=provider, parsed=parsed)
        assert provider.calls == 1
        assert not accepted and out is parsed
        receipt = _read_receipt(tmp_path)
        assert receipt["rejected_reason"] == "theme_coverage_unsatisfied"
        assert sorted(receipt["themes_post"]) == ["bul_ibm_002", "bul_ibm_004", "bul_ibm_005"]

    def test_reject_parse_failed_keeps_attempt1(self, tmp_path, monkeypatch):
        provider = _RecordingProvider("REAL_LLM", "not-json {{{")
        parsed = _attempt1_parsed()
        _raw, out, accepted = _run_rung(tmp_path, monkeypatch, provider=provider, parsed=parsed)
        assert provider.calls == 1
        assert not accepted and out is parsed
        receipt = _read_receipt(tmp_path)
        assert receipt["rejected_reason"] == "parse_failed"

    def test_reject_bare_sentence_regen_persists_raw_and_parse_error(
        self, tmp_path, monkeypatch
    ):
        """Regen replying with just a rewritten sentence (no JSON doc) is rejected fail-open,
        and the receipt now carries the raw-response ref + parse_error detail for RCA."""
        bare = (
            "At IBM led cloud modernization and data lineage programs, "
            "establishing platform discipline for governed delivery."
        )
        provider = _RecordingProvider("REAL_LLM", bare)
        parsed = _attempt1_parsed()
        _raw, out, accepted = _run_rung(tmp_path, monkeypatch, provider=provider, parsed=parsed)
        assert provider.calls == 1
        assert not accepted and out is parsed
        receipt = _read_receipt(tmp_path)
        assert receipt["rejected_reason"] == "parse_failed"
        assert receipt["regen_parse_error"]
        ref = receipt["regen_raw_response_ref"]
        assert ref == lane_runtime.THEME_REPAIR_REGEN_RAW_FILENAME
        assert (tmp_path / ref).read_text(encoding="utf-8") == bare

    def test_reject_truncated_json_live_shape_persists_raw_and_parse_error(
        self, tmp_path, monkeypatch
    ):
        """Proven live failure shape (postRungs_20260610_2246): full JSON doc cut at the
        token cap mid-string (provider stop_reason=max_tokens) → unterminated JSON."""
        truncated = _regen_json(GOOD_REGEN_NARRATIVE)[:-40]
        provider = _RecordingProvider("REAL_LLM", truncated)
        parsed = _attempt1_parsed()
        _raw, out, accepted = _run_rung(tmp_path, monkeypatch, provider=provider, parsed=parsed)
        assert provider.calls == 1
        assert not accepted and out is parsed
        receipt = _read_receipt(tmp_path)
        assert receipt["rejected_reason"] == "parse_failed"
        assert "JSON parse failed" in receipt["regen_parse_error"]
        ref = receipt["regen_raw_response_ref"]
        assert (tmp_path / ref).read_text(encoding="utf-8") == truncated

    def test_regen_max_tokens_sized_from_attempt1_with_margin(self, tmp_path, monkeypatch):
        """Live root cause: attempt 1 needed ~1,130 of the 1,200-token lane cap (attempt 1's own
        provider call stopped at max_tokens), so a regen reusing the flat cap truncates. The
        regen cap must scale from attempt 1's observed length with margin."""
        provider = _RecordingProvider("REAL_LLM", _regen_json(GOOD_REGEN_NARRATIVE))
        parsed = _attempt1_parsed()
        # Padding must exceed the 4000-token floor so margin scaling is observable.
        long_raw = json.dumps(parsed, sort_keys=True) + ("x" * 20000)
        _raw, _out, _accepted = _run_rung(
            tmp_path, monkeypatch, provider=provider, parsed=parsed, raw_output=long_raw
        )
        assert provider.calls == 1
        expected = lane_runtime._theme_repair_regen_max_tokens(long_raw)
        assert provider.last_payload["max_tokens"] == expected
        assert expected > lane_runtime.NARRATIVE_MAX_OUTPUT_TOKENS
        receipt = _read_receipt(tmp_path)
        assert receipt["regen_max_tokens"] == expected
        # Floor: a short attempt-1 raw never drops the cap below the lane default.
        assert (
            lane_runtime._theme_repair_regen_max_tokens("{}")
            == lane_runtime.NARRATIVE_MAX_OUTPUT_TOKENS
        )

    def test_reject_provider_not_real_keeps_attempt1(self, tmp_path, monkeypatch):
        provider = _RecordingProvider("BLOCKED", "")
        parsed = _attempt1_parsed()
        _raw, out, accepted = _run_rung(tmp_path, monkeypatch, provider=provider, parsed=parsed)
        assert provider.calls == 1
        assert not accepted and out is parsed
        receipt = _read_receipt(tmp_path)
        assert receipt["rejected_reason"] == "provider_not_real"
        assert receipt["fired"] is True

    def test_attempt1_failure_shape_still_fails_gate_honestly(self, tmp_path, monkeypatch):
        """Fail-open: rejected regen leaves attempt 1 with the exact live-flap X2 failure."""
        from apps_rg.runtime.validators.ibm_narrative_x2 import (
            _ledger_fact_ids,
        )

        provider = _RecordingProvider("BLOCKED", "")
        parsed = _attempt1_parsed()
        _raw, out, accepted = _run_rung(tmp_path, monkeypatch, provider=provider, parsed=parsed)
        assert not accepted
        themes = ibm_narrative_material_fact_ids_for_sentence(out["narrative_sentence"])
        cited = {s for s in _ledger_fact_ids(out["claim_ledger"]) if s.startswith("bul_ibm_")}
        assert sorted(themes - cited) == ["bul_ibm_004"]  # theme-coverage gate still fails

    def test_kill_switch_default_on_and_hard_cap(self, monkeypatch):
        from apps_rg.runtime.sections.ibm_narrative_repair_policy import (
            THEME_REPAIR_MAX_ATTEMPTS,
            theme_repair_enabled,
        )

        monkeypatch.delenv("APPS_RG_IBM_NARRATIVE_THEME_REPAIR", raising=False)
        assert theme_repair_enabled() is True
        assert THEME_REPAIR_MAX_ATTEMPTS == 2
        for off in ("0", "false", "no", "off"):
            monkeypatch.setenv("APPS_RG_IBM_NARRATIVE_THEME_REPAIR", off)
            assert theme_repair_enabled() is False


class TestThemeBudgetPromptContract:
    def _i0(self) -> str:
        from apps_rg.runtime.sections.ibm_narrative_pa import _i0_from_spec

        return _i0_from_spec(
            {
                "ibm_header": {
                    "employer": "IBM",
                    "title": "Lead Client Partner",
                    "location": "Edgewater, NJ",
                    "start_date": "2017-04",
                    "end_date": "2022-10",
                },
                "allowed_fact_ids": list(ALL_IBM_POOL),
            }
        )

    def test_prompt_states_structural_theme_budget(self):
        i0 = self._i0()
        assert "THEME BUDGET (STRUCTURAL" in i0
        assert "AT MOST 4 of the 5 IBM bullet theme" in i0
        assert "AT MOST 2 theme families per clause" in i0
        assert "', establishing'" in i0

    def test_prompt_theme_families_derive_from_gate_triggers(self):
        from apps_rg.runtime.validators.ibm_narrative_x2 import IBM_NARRATIVE_THEME_TRIGGERS

        i0 = self._i0()
        for fid, phrases in IBM_NARRATIVE_THEME_TRIGGERS:
            assert f"- {fid}:" in i0
            # At least one trigger phrase from each family is summarized in the prompt.
            assert any(p in i0 for p in phrases), fid

    def test_prompt_does_not_dump_full_trigger_lists(self):
        from apps_rg.runtime.validators.ibm_narrative_x2 import IBM_NARRATIVE_THEME_TRIGGERS

        i0 = self._i0()
        budget_block = i0.split("THEME BUDGET (STRUCTURAL", 1)[1]
        budget_block = budget_block.split("\n\n", 1)[0]
        for _fid, phrases in IBM_NARRATIVE_THEME_TRIGGERS:
            present = sum(1 for p in phrases if p in budget_block)
            assert present <= 3, _fid

    def test_yaml_spec_carries_same_budget_statement(self):
        from apps_rg.runtime.sections.ibm_narrative_pa import _ibm_position_narrative_spec

        contract = str(_ibm_position_narrative_spec().get("claim_ledger_coverage_contract") or "")
        assert "STRUCTURAL THEME BUDGET" in contract
        assert "AT MOST 4 of the 5 theme families" in contract
