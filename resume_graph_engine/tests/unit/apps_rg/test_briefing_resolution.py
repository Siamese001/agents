"""Unit tests for apps_rg.runtime.briefing_resolution."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest

from apps_rg.runtime.briefing_resolution import (
    BriefingResolutionError,
    BriefingSource,
    resolve_briefing_for_lanes,
)
from apps_rg.runtime.briefing_ssot import default_targeting_briefing_text


def test_resolve_default_ssot_when_ref_empty() -> None:
    r = resolve_briefing_for_lanes(briefing_artifact_ref=None)
    assert r.briefing_source == BriefingSource.DEFAULT_SSOT
    assert r.text == default_targeting_briefing_text()
    assert r.briefing_digest == hashlib.sha256(r.text.encode("utf-8")).hexdigest()
    assert "DEFAULT_SSOT" in r.ref_used


def test_require_run_specific_fails_closed() -> None:
    with pytest.raises(BriefingResolutionError, match="required briefing"):
        resolve_briefing_for_lanes(briefing_artifact_ref=None, require_run_specific=True)


def test_local_file_rejects_disallowed_suffix(tmp_path: Path) -> None:
    p = tmp_path / "x.exe"
    p.write_text("nope", encoding="utf-8")
    logging.info("C3 write receipt: rejected briefing fixture written")
    with pytest.raises(BriefingResolutionError, match="extension"):
        resolve_briefing_for_lanes(briefing_artifact_ref=str(p))


def test_local_file_rejects_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "nope.txt"
    with pytest.raises(BriefingResolutionError, match="does not exist"):
        resolve_briefing_for_lanes(briefing_artifact_ref=str(missing))


def test_inline_text_when_not_path_like() -> None:
    r = resolve_briefing_for_lanes(briefing_artifact_ref="plain briefing phrase")
    assert r.briefing_source == BriefingSource.RUN_SPECIFIC
    assert r.text == "plain briefing phrase"
    assert r.ref_used == "inline:text"


def test_local_md_briefing_with_markdown_table(tmp_path: Path) -> None:
    p = tmp_path / "role_briefing.md"
    p.write_text(
        "| Col A | Col B |\n| --- | --- |\n| one | two |\n",
        encoding="utf-8",
    )
    r = resolve_briefing_for_lanes(briefing_artifact_ref=str(p))
    assert r.briefing_source == BriefingSource.RUN_SPECIFIC
    assert "| Col A | Col B |" in r.text
    assert "| --- | --- |" in r.text


def test_resolve_canonical_targeting_brief_never_falls_back_across_roles() -> None:
    from apps_rg.integrations.apps_research_bridge import (
        _CANONICAL_TARGETING_BRIEF_CACHE,
        _resolve_canonical_targeting_brief,
    )

    _CANONICAL_TARGETING_BRIEF_CACHE.clear()
    brief_partnerships, path_partnerships = _resolve_canonical_targeting_brief(
        company_name="Anthropic",
        job_title="Manager of Applied AI Architecture, Partnerships",
    )
    assert "anthropic_manager_applied_ai_architecture_partnerships_briefing.md" in path_partnerships
    assert brief_partnerships

    # When multiple Anthropic role briefings exist and job_title is empty or non-matching,
    # it must NOT silently fall back to the first alphabetical briefing (Research Engineer).
    brief_empty, path_empty = _resolve_canonical_targeting_brief(
        company_name="Anthropic",
        job_title="",
    )
    assert brief_empty == ""
    assert path_empty == ""
