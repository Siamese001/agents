"""Wave 5 ADG testing-hotspots — apps_research.company_brief_engine.

CompanyBriefEngine.execute() drives SearXNG + an LLM synthesis cascade, but the
engine carries a substantial *pure* static/deterministic surface that needs no
provider: payload extraction, the env-flagged V2 toggle, prompt construction,
tolerant JSON parsing with fail-closed errors, the stub-disabled synthesis gate, JD
context normalization (incl. content hashing), and schema-shaped brief
assembly. This module covers that surface with real inputs. No mocks.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# The apps_research conftest inserts ``tests/`` onto sys.path, which would
# otherwise shadow the real top-level ``apps_research`` package with the
# ``tests/apps_research`` fixtures package. Front-load the repo root so the
# production package resolves first (house pattern from test_base_research_engine).
_REPO_ROOT = str(Path(__file__).resolve().parents[4])
if sys.path[0] != _REPO_ROOT:
    sys.path.insert(0, _REPO_ROOT)

from apps_research.config.model_pins import (  # noqa: E402
    apps_rg_handoff_judge_pin,
    company_brief_generation_pin,
)
from apps_research.engines.company_brief_engine import (  # noqa: E402
    CompanyBriefEngine,
    CompanyBriefUnavailableError,
)
from apps_research.integrations.search_retrieval import RetrievedDoc  # noqa: E402


_FULL_SYNTHESIS_JSON = json.dumps(
    {
        "company_archetype": "scale-up enterprise vendor",
        "company_dna": {
            "archetype": "scale-up enterprise vendor",
            "commercial_motion": "partner-led growth",
            "partner_ecosystem": "GSI + ISV",
            "adoption_motion": "technical close and enablement",
            "operating_tension": "speed versus governance",
            "distinguishing_traits": ["co-sell discipline", "ecosystem revenue"],
        },
        "tagline": "Acme modernizes enterprise workflows through partner-led platform adoption.",
        "core_offerings": ["platform", "services"],
        "strategic_priorities": ["partner scale", "AI adoption"],
        "verticals": ["insurance"],
        "buyer_titles": ["SVP"],
        "tech_stack_signals": ["AWS"],
        "commercial_motion": ["co-sell"],
        "partner_ecosystem": ["GSI", "ISV"],
        "adoption_motion": ["pilot to production"],
        "leadership": [{"name": "A", "title": "CEO", "background": "exec"}],
        "competitive_set": ["Competitor"],
        "recent_moves": [{"date": "2026-01-01", "event": "launch", "signal": "partner"}],
        "language_to_mirror": ["partner-led"],
        "language_to_avoid": ["generic"],
    }
)


_TARGETING_BRIEF_MD = "\n".join(
    [
        "## JD Complement",
        "- Partner ecosystem scale through repeatable architecture across enterprise accounts.",
        "",
        "## Company Strategy & Operating Pressure",
        "- Enterprise AI deployment momentum drives cloud standardization across regulated buyers.",
        "",
        "## Leadership & Stakeholder Map",
        "- Executive sponsors balance platform consolidation with governance discipline.",
        "",
        "## AI, Data, Platform, Architecture Signals",
        "- Cloud platform investments focus on multi-model orchestration and observability.",
    ]
)


def _pass_x2_receipt() -> dict[str, object]:
    judge_pin = apps_rg_handoff_judge_pin()
    return {
        "schema_version": "apps_research.apps_rg_handoff_x2_judge_receipt.v1",
        "gate_id": "X2_RESEARCH_SEMANTIC_GATE",
        "judge_name": judge_pin.provider_key,
        "judge_provider": judge_pin.provider,
        "judge_model_requested": judge_pin.model,
        "judge_model": judge_pin.model,
        "thinking_level": judge_pin.reasoning_effort,
        "model_observation_status": "OBSERVED_PROVIDER_RESPONSE",
        "threshold": 0.75,
        "model_backed": True,
        "status": "PASS",
        "score": 0.91,
        "verdict": "PASS",
        "provider_status": "MODEL_BACKED_PASS",
    }


def _patch_company_brief_gateways(
    monkeypatch,
    *,
    retrieve_fn=None,
    openai_content: str | None = None,
    captured_messages: list[list[dict[str, str]]] | None = None,
    x2_receipt: dict[str, object] | None = None,
) -> None:
    generation_pin = company_brief_generation_pin()
    if retrieve_fn is None:
        counter = [0]

        def _default_retrieve(query: str, *, top_k: int = 10):
            counter[0] += 1
            return [
                RetrievedDoc(
                    url=f"https://example.com/research/{counter[0]}",
                    title="Grounded public company signal",
                    snippet=f"Verified public operating signal for {query}",
                    score=1.0,
                    engines=("bing",),
                )
            ]

        retrieve_fn = _default_retrieve

    monkeypatch.setattr("apps_research.integrations.search_retrieval.retrieve", retrieve_fn)
    monkeypatch.setattr(
        "apps_research.integrations.reranker_adapter.rerank",
        lambda _query, docs, *, cutoff=5: list(docs)[:cutoff],
    )
    payload = _FULL_SYNTHESIS_JSON if openai_content is None else openai_content

    class _StubCompletions:
        def create(self, **kwargs):
            if captured_messages is not None:
                captured_messages.append(list(kwargs.get("messages") or []))
            return SimpleNamespace(
                id="resp-company-brief-test",
                model=generation_pin.model,
                choices=[SimpleNamespace(message=SimpleNamespace(content=payload))],
                usage={"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
            )

    stub_client = SimpleNamespace(chat=SimpleNamespace(completions=_StubCompletions()))
    monkeypatch.setattr(
        "apps_research.integrations.provider_gateway.create_openai_sync_client",
        lambda: stub_client,
    )
    if x2_receipt is not None:
        monkeypatch.setattr(
            "apps_research.integrations.apps_rg_handoff.run_apps_rg_handoff_x2_judge",
            lambda **_kwargs: dict(x2_receipt),
        )


@pytest.fixture
def engine() -> CompanyBriefEngine:
    return CompanyBriefEngine()


class TestFacetQueries:
    def test_facet_query_templates_present(self, engine):
        facets = [f for f, _ in engine._FACET_QUERIES]
        assert "overview" in facets
        assert "leadership" in facets
        assert "commercial_motion" in facets
        assert "partner_ecosystem" in facets
        assert "adoption_motion" in facets
        assert len(engine._FACET_QUERIES) == 10

    def test_templates_use_company_placeholder(self, engine):
        for _facet, template in engine._FACET_QUERIES:
            assert "{company}" in template


class TestW4AdaptiveResearchLoop:
    def test_v2_retrieval_runs_bounded_jd_promoted_follow_up_for_coverage_gap(
        self, monkeypatch, engine, tmp_path
    ):
        calls: list[str] = []

        def _retrieve(query: str, *, top_k: int = 10):
            calls.append(query)
            if query == "Anthropic partners alliances cloud partnerships co-sell GSI ISV ecosystem":
                return []
            return [
                RetrievedDoc(
                    url=f"https://www.anthropic.com/{len(calls)}",
                    title="Anthropic official evidence",
                    snippet=f"Anthropic evidence for {query}",
                    score=1.0,
                    engines=("bing",),
                )
            ]

        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "1")
        _patch_company_brief_gateways(monkeypatch, retrieve_fn=_retrieve)
        receipt_path = tmp_path / "run" / "retrieval_receipt.json"
        (receipt_path.parent / "runs").mkdir(parents=True)

        brief = engine.execute(
            {
                "topic": "Anthropic",
                "depth": "standard",
                "jd_context": {
                    "company_name": "Anthropic",
                    "job_title": "Partnerships Architect",
                    "content": "Lead GSI and cloud partnerships with partner enablement.",
                    "_retrieval_receipt_path": str(receipt_path),
                },
            }
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

        assert "Anthropic official partnerships alliances cloud ecosystem primary sources" in calls
        partner_family = next(
            row
            for row in brief["_c0_bundle"]["briefing_coverage_matrix"]["families"]
            if row["family"] == "partner_ecosystem"
        )
        assert partner_family["covered"] is True
        assert partner_family["source_count"] >= 1
        assert receipt["adaptive_research_revision"]["revision_status"] == "FOLLOW_UP_PROPOSED"
        follow_up = next(
            row
            for row in receipt["adaptive_research_execution"]
            if row["family"] == "partner_ecosystem"
        )
        assert follow_up["retrieval_attempt_status"] == "PASS"
        family = next(
            row for row in receipt["families"] if row["family"] == "partner_ecosystem"
        )
        assert family["retrieval_attempt_status"] == "RECOVERED_BY_ADAPTIVE_FOLLOW_UP"


class TestV2Flag:
    @staticmethod
    def _v2_stage_flag(brief: dict) -> bool:
        fetch_stage = next(
            stage
            for stage in brief["_sub_stages"]
            if stage["sub_stage_id"] == "research.fetch"
        )
        return bool(fetch_stage["meta"]["v2"])

    def test_disabled_by_default(self, monkeypatch, engine):
        monkeypatch.delenv("APPS_RESEARCH_RETRIEVAL_V2", raising=False)
        _patch_company_brief_gateways(monkeypatch)
        brief = engine.execute({"topic": "Acme Corp"})
        assert self._v2_stage_flag(brief) is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on"])
    def test_truthy_values_enable(self, monkeypatch, engine, val):
        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", val)
        _patch_company_brief_gateways(monkeypatch)
        brief = engine.execute({"topic": "Acme Corp"})
        assert self._v2_stage_flag(brief) is True

    @pytest.mark.parametrize("val", ["0", "false", "no", ""])
    def test_falsey_values_disable(self, monkeypatch, engine, val):
        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", val)
        _patch_company_brief_gateways(monkeypatch)
        brief = engine.execute({"topic": "Acme Corp"})
        assert self._v2_stage_flag(brief) is False


class TestExtract:
    def test_extract_from_dict(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch)
        brief = engine.execute({"topic": "Acme"})
        assert brief["company"] == "Acme"

    def test_extract_from_attr(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch)

        class Obj:
            topic = "Beta"

        brief = engine.execute(Obj())
        assert brief["company"] == "Beta"

    def test_extract_missing_returns_default(self, engine):
        with pytest.raises(ValueError, match="non-empty 'topic'"):
            engine.execute({})

    def test_extract_non_dict_non_attr_returns_default(self, engine):
        with pytest.raises(ValueError, match="non-empty 'topic'"):
            engine.execute(42)


class TestBuildSynthesisPrompt:
    def test_includes_topic_and_facets(self, monkeypatch, engine, tmp_path):
        captured: list[list[dict[str, str]]] = []
        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "0")
        _patch_company_brief_gateways(
            monkeypatch,
            retrieve_fn=lambda _q, top_k=10: [
                RetrievedDoc(
                    url="https://acme.example.com/about",
                    title="Acme Overview",
                    snippet="founded 2010",
                    score=1.0,
                    engines=("bing",),
                )
            ],
            captured_messages=captured,
        )
        jd_anchor = tmp_path / "jd.json"
        jd_anchor.write_text(
            json.dumps({"keywords": ["python", "data"]}),
            encoding="utf-8",
        )
        engine.execute({"topic": "Acme Corp", "jd_anchor": jd_anchor})
        prompt = captured[-1][1]["content"]
        assert "Acme Corp" in prompt
        assert "python, data" in prompt
        assert "founded 2010" in prompt
        assert "strictly JSON" in prompt

    def test_empty_findings_marked(self, monkeypatch, engine):
        captured: list[list[dict[str, str]]] = []
        calls = [0]

        def _partial_retrieve(_q: str, *, top_k: int = 10):
            calls[0] += 1
            if calls[0] > 1:
                return []
            return [
                RetrievedDoc(
                    url="https://x.example.com/about",
                    title="X Overview",
                    snippet="founded 2015",
                    score=1.0,
                    engines=("bing",),
                )
            ]

        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "0")
        _patch_company_brief_gateways(
            monkeypatch,
            retrieve_fn=_partial_retrieve,
            captured_messages=captured,
        )
        engine.execute({"topic": "X"})
        prompt = captured[-1][1]["content"]
        assert "(no research available)" in prompt
        assert "(none provided)" in prompt


class TestParseSynthesis:
    def test_extracts_embedded_json(self, monkeypatch, engine):
        _patch_company_brief_gateways(
            monkeypatch,
            openai_content='noise {"tagline": "hi", "core_offerings": ["x"]} trailing',
        )
        out = engine.execute({"topic": "X"})
        assert out["overview"]["tagline"] == "hi"

    def test_invalid_json_raises(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch, openai_content="no json here")
        with pytest.raises(
            CompanyBriefUnavailableError, match="structured synthesis JSON parse failed"
        ):
            engine.execute({"topic": "Acme"})

    def test_malformed_braces_raises(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch, openai_content="{not valid json")
        with pytest.raises(
            CompanyBriefUnavailableError, match="structured synthesis JSON parse failed"
        ):
            engine.execute({"topic": "Acme"})


class TestStubSynthesis:
    def test_stub_synthesis_disabled(self, engine):
        with pytest.raises(CompanyBriefUnavailableError, match="stub synthesis disabled"):
            engine._stub_synthesis(topic="Acme", jd_facets=[])


class TestResolveJdContext:
    def test_no_jd_returns_empty(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch)
        brief = engine.execute({"topic": "X"})
        assert brief.get("_jd_context", {}) == {}

    def test_empty_jd_dict_returns_empty(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch)
        brief = engine.execute({"topic": "X", "jd_context": {}})
        assert brief.get("_jd_context", {}) == {}

    def test_content_hash_computed_when_absent(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch)
        brief = engine.execute({"topic": "X", "jd_context": {"content": "JD body text"}})
        expected = "sha256-" + hashlib.sha256(b"JD body text").hexdigest()[:16]
        assert brief["_jd_context"]["jd_content_hash"] == expected

    def test_existing_hash_preserved(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch)
        brief = engine.execute(
            {"topic": "X", "jd_context": {"content": "x", "jd_content_hash": "preset"}}
        )
        assert brief["_jd_context"]["jd_content_hash"] == "preset"

    def test_reads_attribute_form(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch)

        class Obj:
            topic = "X"
            jd_context = {"jd_ref": "ref-1"}

        brief = engine.execute(Obj())
        assert brief["_jd_context"]["jd_content_hash"].startswith("sha256-")


class TestCuratedTargetingFallback:
    def test_targeting_handoff_blocks_weak_c0_gate_without_jd_coverage(
        self, monkeypatch, engine
    ):
        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "1")
        idx = [0]

        def _selective_retrieve(query: str, *, top_k: int = 10):
            if "company overview founding" in query or "executive team" in query:
                return [
                    RetrievedDoc(
                        url=f"https://unify.example.com/{i}",
                        title="Unify Consulting evidence",
                        snippet="Unify Consulting verified operating signal",
                        score=1.0,
                        engines=("bing",),
                    )
                    for i in range(idx[0], idx[0] + 3)
                ]
            idx[0] += 3
            return []

        _patch_company_brief_gateways(
            monkeypatch,
            retrieve_fn=_selective_retrieve,
            openai_content=_TARGETING_BRIEF_MD,
            x2_receipt=_pass_x2_receipt(),
        )

        brief = engine.execute(
            {
                "topic": "Unify Consulting",
                "depth": "shallow",
                "jd_context": {
                    "company_name": "Unify Consulting",
                    "job_title": "SVP Technical Pre-Sales",
                    "output_format": "apps_rg_targeting_brief_v1",
                    "synthesis_template": "apps_rg_targeting_brief_synthesis_v1",
                },
            }
        )

        assert brief["targeting_brief_disposition"] == "BLOCKED"
        assert brief["targeting_brief_block_reason"] == (
            "c0_support_gate=WEAK_WITH_CAVEATS"
        )
        assert "company_brief_text" not in brief

    def test_targeting_handoff_accepts_caveated_jd_complete_c0_bundle(
        self, monkeypatch, engine
    ):
        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "1")
        url_counter = [0]

        def _selective_retrieve(query: str, *, top_k: int = 10):
            if any(
                marker in query
                for marker in (
                    "company overview founding",
                    "commercial motion",
                    "competitors alternatives",
                    "latest funding valuation",
                    "AI technology innovation",
                )
            ):
                docs = []
                for _ in range(4):
                    url_counter[0] += 1
                    docs.append(
                        RetrievedDoc(
                            url=f"https://unify.example.com/caveat/{url_counter[0]}",
                            title="Unify Consulting public evidence",
                            snippet="Unify Consulting commercial and platform signal",
                            score=1.0,
                            engines=("bing",),
                        )
                    )
                return docs
            return []

        _patch_company_brief_gateways(
            monkeypatch,
            retrieve_fn=_selective_retrieve,
            openai_content=_TARGETING_BRIEF_MD,
            x2_receipt=_pass_x2_receipt(),
        )

        brief = engine.execute(
            {
                "topic": "Unify Consulting",
                "depth": "deep",
                "jd_context": {
                    "company_name": "Unify Consulting",
                    "job_title": "SVP Technical Pre-Sales",
                    "content": "Lead SVP technical pre-sales.",
                    "output_format": "apps_rg_targeting_brief_v1",
                    "synthesis_template": "apps_rg_targeting_brief_synthesis_v1",
                },
            }
        )

        assert brief["targeting_brief_disposition"] == "SEALED"
        assert "Partner ecosystem scale through repeatable architecture" in brief["company_brief_text"]
        assert brief["targeting_brief_c0_disposition"] == "CAVEATED_JD_COMPLETE"
        assert brief["targeting_brief_c0_caveat"]

    def test_v2_research_returns_coverage_family_keys(self, monkeypatch, engine):
        calls: list[str] = []

        def _retrieve(query: str, *, top_k: int = 10):
            calls.append(query)
            return [
                RetrievedDoc(
                    url=f"https://example.com/{len(calls)}",
                    title=f"Anthropic evidence {len(calls)}",
                    snippet=f"Anthropic evidence for {query}",
                    score=1.0,
                    engines=("bing",),
                )
            ]

        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "1")
        _patch_company_brief_gateways(monkeypatch, retrieve_fn=_retrieve)

        brief = engine.execute(
            {
                "topic": "Anthropic",
                "depth": "standard",
                "jd_context": {
                    "company_name": "Anthropic",
                    "job_title": "Manager of Applied AI Architecture, Partnerships",
                    "content": (
                        "Lead partner solutions architects for GSIs, cloud partners, "
                        "joint solution development, indirect revenue, GTM strategy, "
                        "enterprise AI deployments, API integrations, and Claude adoption."
                    ),
                },
            }
        )
        fetch_stage = next(
            stage
            for stage in brief["_sub_stages"]
            if stage["sub_stage_id"] == "research.fetch"
        )
        query_families = set(fetch_stage["meta"]["query_families"])

        assert "overview" not in query_families
        assert "company_basics" in query_families
        assert "partner_ecosystem" in query_families
        assert "commercial_motion" in query_families
        assert "adoption_motion" in query_families
        assert "tech_stack_and_tools" in query_families
        assert "recent_news_and_signals" in query_families
        assert "competitive_landscape" in query_families
        assert "leadership_and_org" in query_families
        assert "financials_and_growth" in query_families
        assert any(
            url.startswith("https://example.com/")
            for url in brief["_c0_bundle"]["source_portfolio_summary"]["source_urls"]
        )

    def test_adaptive_research_blocks_when_search_is_empty_instead_of_curated_pack(
        self, monkeypatch, engine
    ):
        def _boom(*_args, **_kwargs):
            raise RuntimeError("usage limit")

        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "0")
        _patch_company_brief_gateways(monkeypatch, retrieve_fn=_boom)

        with pytest.raises(
            CompanyBriefUnavailableError,
            match="adaptive research returned no grounded findings",
        ):
            engine.execute(
                {
                    "topic": "Anthropic",
                    "depth": "standard",
                    "jd_context": {
                        "company_name": "Anthropic",
                        "job_title": "Manager of Applied AI Architecture, Partnerships",
                    },
                }
            )

    def test_active_company_brief_retrieval_path_does_not_import_tavily(self):
        import inspect

        source = inspect.getsource(CompanyBriefEngine)
        assert "apps_research.integrations.tavily_retrieval" not in source

    def test_jd_restatement_bullet_scrub_is_deterministic(self, monkeypatch, engine):
        draft = "\n".join(
            [
                "## JD Complement",
                "- Partner ecosystem scale through repeatable architecture",
                "",
                "## Company Strategy & Operating Pressure",
                "- Enterprise cloud adoption accelerates governance priorities",
                "",
                "## Leadership & Stakeholder Map",
                "- Executive leadership aligns platform roadmap to commercial goals",
                "",
                "## Apps_RG Positioning Themes (targeting only, not proof)",
                "- Building foundational teams in uncertain growth phases",
                "- Ecosystem architecture differentiates regulated enterprise delivery",
            ]
        )
        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "1")
        _patch_company_brief_gateways(
            monkeypatch,
            openai_content=draft,
            x2_receipt=_pass_x2_receipt(),
        )
        brief = engine.execute(
            {
                "topic": "Anthropic",
                "depth": "shallow",
                "jd_context": {
                    "company_name": "Anthropic",
                    "job_title": "Partnerships Architect",
                    "content": "Building foundational teams in uncertain growth phases across cloud accounts.",
                    "output_format": "apps_rg_targeting_brief_v1",
                    "synthesis_template": "apps_rg_targeting_brief_synthesis_v1",
                },
            }
        )

        scrubbed = brief["company_brief_text"]
        assert "Building foundational teams" not in scrubbed
        assert "Partner ecosystem scale" in scrubbed

    def test_unsupported_named_leadership_claim_scrub_is_deterministic(
        self, monkeypatch, engine
    ):
        draft = "\n".join(
            [
                "## JD Complement",
                "- Partner ecosystem scale through repeatable architecture",
                "",
                "## Company Strategy & Operating Pressure",
                "- Platform adoption spans regulated financial buyers",
                "",
                "## Leadership & Stakeholder Map",
                "- Dario Amodei is the CEO and a central strategic voice for Anthropic.",
                "- The likely stakeholder map spans partnerships, sales, product, and engineering.",
                "",
                "## AI, Data, Platform, Architecture Signals",
                "- Enterprise API orchestration prioritizes safety and reliability.",
            ]
        )
        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "1")
        idx = [0]

        def _partners_only_retrieve(query: str, *, top_k: int = 10):
            idx[0] += 1
            return [
                RetrievedDoc(
                    url=f"https://www.anthropic.com/partners/{idx[0]}",
                    title="Anthropic Partner Ecosystem",
                    snippet="Anthropic has public partner ecosystem and platform adoption signals.",
                    score=1.0,
                    engines=("bing",),
                )
            ]

        _patch_company_brief_gateways(
            monkeypatch,
            retrieve_fn=_partners_only_retrieve,
            openai_content=draft,
            x2_receipt=_pass_x2_receipt(),
        )
        brief = engine.execute(
            {
                "topic": "Anthropic",
                "depth": "shallow",
                "jd_context": {
                    "company_name": "Anthropic",
                    "job_title": "Partnerships Architect",
                    "content": "Lead partner ecosystem architecture.",
                    "output_format": "apps_rg_targeting_brief_v1",
                    "synthesis_template": "apps_rg_targeting_brief_synthesis_v1",
                },
            }
        )

        scrubbed = brief["company_brief_text"]
        assert "## Leadership & Stakeholder Map" in scrubbed
        assert "Dario Amodei" not in scrubbed
        assert "likely stakeholder map spans partnerships" in scrubbed

    def test_supported_named_leadership_claim_is_preserved(self, monkeypatch, engine):
        draft = "\n".join(
            [
                "## JD Complement",
                "- Partner ecosystem scale through repeatable architecture",
                "",
                "## Company Strategy & Operating Pressure",
                "- Platform adoption spans regulated financial buyers",
                "",
                "## Leadership & Stakeholder Map",
                "- Dario Amodei is the CEO and a central strategic voice for Anthropic.",
                "",
                "## AI, Data, Platform, Architecture Signals",
                "- Enterprise API orchestration prioritizes safety and reliability.",
            ]
        )
        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "1")
        idx = [0]

        def _leadership_retrieve(query: str, *, top_k: int = 10):
            idx[0] += 1
            return [
                RetrievedDoc(
                    url=f"https://www.anthropic.com/leadership/{idx[0]}",
                    title="Anthropic Leadership",
                    snippet="Anthropic leadership coverage names Dario Amodei as CEO.",
                    score=1.0,
                    engines=("bing",),
                )
            ]

        _patch_company_brief_gateways(
            monkeypatch,
            retrieve_fn=_leadership_retrieve,
            openai_content=draft,
            x2_receipt=_pass_x2_receipt(),
        )
        brief = engine.execute(
            {
                "topic": "Anthropic",
                "depth": "shallow",
                "jd_context": {
                    "company_name": "Anthropic",
                    "job_title": "Partnerships Architect",
                    "content": "Lead partner ecosystem architecture.",
                    "output_format": "apps_rg_targeting_brief_v1",
                    "synthesis_template": "apps_rg_targeting_brief_synthesis_v1",
                },
            }
        )

        assert "Dario Amodei is the CEO" in brief["company_brief_text"]

    def test_sidecar_reason_preserves_deterministic_semantic_block(
        self, monkeypatch, engine
    ):
        incomplete_sections_md = "\n".join(
            [
                "## JD Complement",
                "- Valid targeting brief text aligning company dna, operating model, strategy, leadership, and urgency.",
                "",
                "## Company Strategy & Operating Pressure",
                "- Scaling cloud platform execution across enterprise customers with co-sell partner motion.",
                "",
                "## AI, Data, Platform, Architecture Signals",
                "- Governed orchestration pipelines standardize model adoption across ecosystem partners.",
                "",
                "## Apps_RG Positioning Themes",
                "- Align delivery operating model with partner ecosystem leverage and leadership priorities.",
            ]
        )
        monkeypatch.setenv("APPS_RESEARCH_RETRIEVAL_V2", "1")
        idx = [0]

        def _full_coverage_retrieve(query: str, *, top_k: int = 10):
            idx[0] += 1
            return [
                RetrievedDoc(
                    url=f"https://www.anthropic.com/sidecar/{idx[0]}",
                    title="Anthropic ecosystem partner co-sell overview",
                    snippet="Anthropic public strategy, leadership, and partner ecosystem co-sell signals.",
                    score=1.0,
                    engines=("bing",),
                )
            ]

        _patch_company_brief_gateways(
            monkeypatch,
            retrieve_fn=_full_coverage_retrieve,
            openai_content=incomplete_sections_md,
            x2_receipt=_pass_x2_receipt(),
        )
        brief = engine.execute(
            {
                "topic": "Anthropic",
                "depth": "deep",
                "jd_context": {
                    "company_name": "Anthropic",
                    "job_title": "Partnerships Architect",
                    "content": "Lead partner architecture.",
                    "output_format": "apps_rg_targeting_brief_v1",
                    "synthesis_template": "apps_rg_targeting_brief_synthesis_v1",
                },
            }
        )
        sidecar = brief["apps_rg_targeting_brief_sidecar"]

        assert sidecar["handoff_eligible"] is False
        assert "missing_sections" in sidecar["reason"]
        assert "leadership & stakeholder map" in sidecar["missing_sections"]


class TestAssembleBrief:
    def test_schema_shape(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch, openai_content=_FULL_SYNTHESIS_JSON)
        brief = engine.execute({"topic": "Acme"})
        assert brief["company"] == "Acme"
        assert brief["source"] == "apps_research"
        assert brief["freshness_ttl_days"] == 30
        assert "overview" in brief
        assert "core_offerings" in brief["overview"]
        assert "company_dna" in brief
        assert "commercial_motion" in brief
        assert "partner_ecosystem" in brief
        assert "customer_profile" in brief

    def test_missing_synthesis_keys_default_to_empty(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch, openai_content="{}")
        brief = engine.execute({"topic": "Acme"})
        assert brief["overview"]["tagline"] == "Acme"  # falls back to topic
        assert brief["strategic_priorities"] == []
        assert brief["language_to_mirror"] == []

    def test_fetched_at_is_iso_timestamp(self, monkeypatch, engine):
        _patch_company_brief_gateways(monkeypatch, openai_content="{}")
        brief = engine.execute({"topic": "Acme"})
        # ISO 8601 with timezone — contains a 'T' separator.
        assert "T" in brief["fetched_at"]
