"""W4 — executable manifest coverage across all generated lanes."""

from __future__ import annotations

from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
from apps_rg.runtime.sections.section_prompt_authority_ssot import (
    EXECUTABLE_PROMPT_SOURCES,
    assert_all_generated_lanes_executable_corpus_non_empty,
    collect_executable_prompt_corpus,
)


def test_executable_prompt_sources_cover_all_generated_lanes() -> None:
    assert set(EXECUTABLE_PROMPT_SOURCES) == set(GENERATED_LANES)
    for lane in GENERATED_LANES:
        sources = EXECUTABLE_PROMPT_SOURCES[lane]
        assert sources, f"{lane}: missing sources"
        kinds = {s["kind"] for s in sources}
        assert "yaml_template" in kinds


def test_headline_executable_corpus_includes_u0_snippet() -> None:
    corpus = collect_executable_prompt_corpus("headline")
    assert "SVP Engineering" in corpus
    assert "headline_line" in corpus
    assert len(corpus.strip()) >= 200


def test_assert_all_generated_lanes_executable_corpus_non_empty() -> None:
    assert_all_generated_lanes_executable_corpus_non_empty()
