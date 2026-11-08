"""Non-mock regression and breakage reproduction tests for Subsystems 1, 2, and 4.

Reproduces breakages identified during the Outreach Engine Red Team campaign
and verifies subsequent remediations under live, non-mock engine execution.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from apps_lic.domain.models import (
    CandidateProfileLoader,
    ChannelType,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.domain.repair import DeterministicDraftRepairer
from apps_lic.domain.validators import (
    ChannelLengthValidator,
    EmDashValidator,
    ForbiddenClaimsValidator,
    GroundingValidator,
    MarkdownLinkValidator,
    OutboundPrivacyValidator,
    QuestionEndingValidator,
    SpamTriggerValidator,
    SubordinateToneValidator,
    UnsupportedPersonalizationValidator,
)
from apps_lic.pipeline.briefing_resolver import GovernedBriefingResolver
from apps_lic.pipeline.mission_loader import MissionLoader


# ==============================================================================
# Subsystem 1: CLI Entry Points
# ==============================================================================


def test_cli_eval_null_grounded_facts_used() -> None:
    """ISSUE-CLI-01: Reconstructing eval draft handles null grounded_facts_used."""
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "run_manifest.json").write_text(
            json.dumps({
                "candidate": {"candidate_id": "c1", "full_name": "Test Candidate", "verified_facts": []},
                "opportunity": {"company_name": "Acme Corp", "role_title": "Leader"},
                "grounded_facts_used": None,
            }),
            encoding="utf-8",
        )
        (t / "outreach_draft.json").write_text(
            json.dumps({"channel": "inmail", "subject": "Hello", "body": "Open to discussing?"}),
            encoding="utf-8",
        )
        res = subprocess.run(
            [sys.executable, "-m", "outreach_engine", "eval", "--run-dir", str(t), "--json"],
            capture_output=True,
            text=True,
        )
        # Should not crash with TypeError: 'NoneType' object is not iterable
        assert "TypeError: 'NoneType' object is not iterable" not in res.stderr
        assert res.returncode in (0, 1)


def test_cli_run_malformed_brief_emits_json_error() -> None:
    """ISSUE-CLI-02: Non-dict / array JSON brief returns structured error instead of crashing."""
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
        f.write("[1, 2, 3]")
        f.flush()
        res = subprocess.run(
            [sys.executable, "-m", "outreach_engine", "run", "--brief", f.name, "--offline-smoke", "--json"],
            capture_output=True,
            text=True,
        )
        assert res.returncode != 0
        # Under --json, it should emit structured JSON with status FAILED
        data = json.loads(res.stdout)
        assert data.get("status") == "FAILED"
        assert "error" in data


def test_cli_unicode_decode_error_handled_cleanly() -> None:
    """ISSUE-CLI-03: Corrupted non-UTF8 files fail cleanly with error message rather than unhandled exception."""
    with tempfile.NamedTemporaryFile("wb", suffix=".json") as f:
        f.write(b"\x80\x81\xff\xfe")
        f.flush()
        res = subprocess.run(
            [sys.executable, "-m", "outreach_engine", "run", "--brief", f.name, "--offline-smoke", "--json"],
            capture_output=True,
            text=True,
        )
        assert res.returncode != 0
        assert "Traceback" not in res.stderr
        data = json.loads(res.stdout)
        assert data.get("status") == "FAILED"


def test_cli_unwritable_artifact_dir_handled() -> None:
    """ISSUE-CLI-04: Uncreatable artifact-dir returns structured error rather than unhandled OSError."""
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "outreach_engine",
            "run",
            "--demo",
            "--artifact-dir",
            "/proc/nonexistent/unwritable_dir_xyz",
            "--offline-smoke",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    assert "Traceback" not in res.stderr
    data = json.loads(res.stdout)
    assert data.get("status") == "FAILED"


def test_cli_validate_supports_stdin_and_dash() -> None:
    """ISSUE-CLI-05: Validating via stdin with '--file -' or pipe works cleanly."""
    draft_body = "Hi Sarah, Truist platform modernization scaled $4.2B with 99.995% reliability. Open to connecting?"
    res = subprocess.run(
        [sys.executable, "-m", "outreach_engine", "validate", "--file", "-", "--json"],
        input=draft_body,
        capture_output=True,
        text=True,
    )
    assert "Error: Draft file not found: -" not in res.stderr
    data = json.loads(res.stdout)
    assert "status" in data


def test_cli_show_json_selects_json_artifact() -> None:
    """ISSUE-CLI-06: 'show --artifact draft --json' selects JSON draft over markdown wrapper."""
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "outreach_draft.md").write_text("# Outreach Draft: INMAIL\nSubject: Hi\n```text\nBody\n```", encoding="utf-8")
        (t / "outreach_draft.json").write_text(json.dumps({"channel": "inmail", "subject": "Hi", "body": "Body"}), encoding="utf-8")

        res = subprocess.run(
            [sys.executable, "-m", "outreach_engine", "show", "--run-dir", str(t), "--artifact", "draft", "--json"],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        data = json.loads(res.stdout)
        # Should output the JSON draft object directly, not wrapped with file="outreach_draft.md"
        assert data.get("channel") == "inmail"


# ==============================================================================
# Subsystem 2: Pipeline Loaders & Resolvers
# ==============================================================================


def test_mission_loader_corrupted_json_raises_value_error() -> None:
    """ISSUE-LOAD-01: Corrupted .json files raise ValueError instead of falling back to text."""
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
        f.write('{"sender_profile": {"name": "Alice"')  # Truncated
        f.flush()
        with pytest.raises(ValueError, match="Corrupted JSON"):
            MissionLoader.load_from_file(f.name)


def test_mission_loader_structured_yaml_parsed() -> None:
    """ISSUE-LOAD-02: Structured YAML mission files are parsed into dicts, not raw text."""
    yaml_content = """
sender_profile:
  name: "Jane Doe"
  title: "Chief Architect"
  key_competencies:
    - "Distributed Systems"
recipient_profile:
  company: "Stripe"
  title: "CTO"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as f:
        f.write(yaml_content)
        f.flush()
        cand, opp = MissionLoader.load_from_file(f.name)
        assert cand.full_name == "Jane Doe"
        assert opp.company_name == "Stripe"
        assert "sender_profile:" not in opp.briefing_text


def test_mission_loader_non_dict_payload_raises() -> None:
    """ISSUE-LOAD-03: Non-dict root payloads (None, 123, list) raise ValueError."""
    with pytest.raises(ValueError, match="Expected dictionary payload"):
        MissionLoader.load_from_dict(None)  # type: ignore

    with pytest.raises(ValueError, match="Expected dictionary payload"):
        MissionLoader.load_from_dict(123)  # type: ignore

    with pytest.raises(ValueError, match="Expected dictionary payload"):
        MissionLoader.load_from_dict(["not", "a", "dict"])  # type: ignore


def test_mission_loader_null_sub_objects() -> None:
    """ISSUE-LOAD-04: Null sub-objects do not cause AttributeError or TypeError."""
    # Structure 1 with null sender/recipient
    cand, opp = MissionLoader.load_from_dict({
        "sender_profile": None,
        "recipient_profile": None,
        "job_description": None,
    })
    assert cand is not None
    assert opp is not None

    # Structure 2 with null recipient_title
    cand2, opp2 = MissionLoader.load_from_dict({
        "recipient_company": "Acme",
        "recipient_title": None,
    })
    assert opp2.recipient_title == "Head of Engineering"

    # Structure 3 with null payload
    with pytest.raises(ValueError):
        MissionLoader.load_from_dict({"payload": None})


def test_mission_loader_coerce_str_list_character_explosion() -> None:
    """ISSUE-LOAD-05: Single string does not explode into character list."""
    cand, opp = MissionLoader.load_from_dict({
        "sender_profile": {"key_competencies": "Agentic AI"},
        "recipient_profile": {},
        "job_description": {"responsibilities": "Lead systems"},
    })
    assert cand.key_competencies == ["Agentic AI"]
    assert "Lead systems" in opp.strategic_priorities


def test_mission_loader_structure3_company_name() -> None:
    """ISSUE-LOAD-06: Structure 3 assigns company_name, not company_brief."""
    payload = {
        "payload": {
            "company_name": "Acme Corp",
            "company_brief": "Detailed multi-paragraph analysis of Acme Corp founded in 2020...",
            "target_title": "VP Engineering",
        }
    }
    cand, opp = MissionLoader.load_from_dict(payload)
    assert opp.company_name == "Acme Corp"
    assert "Detailed multi-paragraph" not in opp.company_name


def test_mission_loader_unicode_title_parsing() -> None:
    """ISSUE-LOAD-07: Unicode and accented company names parsed properly from text."""
    for text in ["Münchener Rück - Chief Architect", "Société Générale - Head of AI", "🚀 Acme - CTO"]:
        cand, opp = MissionLoader.load_from_text(text)
        assert opp.company_name != "Target Company"


def test_briefing_resolver_missing_file_raises_filenotfound() -> None:
    """ISSUE-LOAD-08: Missing path passed as manual brief raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        GovernedBriefingResolver.resolve(
            company_name="Acme",
            manual_brief_or_fixture="data/missions/non_existent_file.txt",
            force_fresh=True,
        )


# ==============================================================================
# Subsystem 4: Domain Models, Validators & Repair
# ==============================================================================


def test_grounding_validator_mega_numeric_overflow() -> None:
    """ISSUE-VAL-01: Mega-numeric values (>1e308) do not crash GroundingValidator."""
    g = GroundingValidator()
    is_valid, viols = g.validate([], set(), body="Delivered $" + "9" * 400 + " in value")
    assert not is_valid
    assert len(viols) > 0


def test_forbidden_claims_validator_mega_numeric_overflow() -> None:
    """ISSUE-VAL-02: Mega-numeric figures in opportunity context do not crash ForbiddenClaimsValidator."""
    f = ForbiddenClaimsValidator()
    is_valid, viols = f.validate("Professional note", opportunity_context="Pipeline is $" + "9" * 400)
    assert isinstance(is_valid, bool)


def test_grounding_validator_non_usd_currencies() -> None:
    """ISSUE-VAL-03: Non-USD currencies (€, £, USD, EUR, GBP) are checked by GroundingValidator."""
    g = GroundingValidator()
    is_valid, viols = g.validate([], set(), body="Generated €50M in new revenue and £25M in margin.")
    assert not is_valid
    assert len(viols) >= 2


def test_repair_single_paragraph_respects_limits() -> None:
    """ISSUE-VAL-04: Single paragraph text is trimmed to fit within channel ceiling."""
    text = "Sentence word " * 200  # ~2800 chars
    repaired, _ = DeterministicDraftRepairer.repair_text(text, channel=ChannelType.LINKEDIN_INMAIL)
    is_valid, err = ChannelLengthValidator().validate(ChannelType.LINKEDIN_INMAIL, repaired)
    assert is_valid, err
    assert len(repaired) <= 1900


def test_repair_question_addition_respects_limits() -> None:
    """ISSUE-VAL-05: Appending terminal question does not cause body to exceed channel ceiling."""
    p1 = "Alpha " * 100
    p2 = "Beta " * 38 + "test."
    body = p1 + "\n\n" + p2  # 797 chars (under follow_up limit 800)
    repaired, _ = DeterministicDraftRepairer.repair_text(body, channel=ChannelType.FOLLOW_UP)
    is_valid, err = ChannelLengthValidator().validate(ChannelType.FOLLOW_UP, repaired)
    assert is_valid, f"Length {len(repaired)} exceeds ceiling: {err}"


def test_repair_signature_slicing_common_words() -> None:
    """ISSUE-VAL-06: Common words like 'lead' or 'partner' mid-body do not cause question slicing."""
    body = "Hi Alex,\nI would be thrilled to lead your engineering team.\nWe can scale your cloud platform."
    repaired, _ = DeterministicDraftRepairer.repair_text(body, channel=ChannelType.EMAIL)
    is_valid, err = QuestionEndingValidator().validate(repaired)
    assert is_valid, err


def test_question_ending_validator_false_positives() -> None:
    """ISSUE-VAL-07: Body ending with non-question statements fails QuestionEndingValidator."""
    body = "Would you be open to a call?\nWe have 100 clients\nOur product sells fast\nWe guarantee high returns"
    is_valid, err = QuestionEndingValidator().validate(body)
    assert not is_valid


def test_spam_and_subordinate_tone_whitespace_bypass() -> None:
    """ISSUE-VAL-08: Whitespace variations (newlines, multiple spaces) do not bypass triggers."""
    s_val = SpamTriggerValidator()
    t_val = SubordinateToneValidator()

    assert not s_val.validate("Please act  now on this")[0]
    assert not s_val.validate("Please act\nnow on this")[0]
    assert not t_val.validate("I would love\nto learn more")[0]
    assert not t_val.validate("I would love  to learn more")[0]


def test_markdown_link_validator_case_and_scheme() -> None:
    """ISSUE-VAL-09: Markdown links with uppercase scheme or www are blocked."""
    val = MarkdownLinkValidator()
    assert not val.validate("Check [profile](HTTPS://linkedin.com)")[0]
    assert not val.validate("Check [profile](www.linkedin.com)")[0]


def test_unsupported_personalization_unsealed_fails_closed() -> None:
    """ISSUE-VAL-10: UnsupportedPersonalizationValidator fails closed on unsealed or None resolution."""
    opp = TargetOpportunity(
        opportunity_id="opp_1",
        company_name="Acme",
        role_title="Lead",
        industry="Tech",
        recipient_name="Alex",
        recipient_title="Director",
        strategic_priorities=["cloud"],
        sealed_resolution=None,
    )
    val = UnsupportedPersonalizationValidator()
    is_valid, viols = val.validate("Following Acme's focus on cloud, I wanted to reach out.", opportunity=opp)
    assert not is_valid
    assert len(viols) > 0


def test_target_opportunity_enum_coercion() -> None:
    """ISSUE-VAL-11: TargetOpportunity coerces string enum values in __post_init__."""
    opp = TargetOpportunity(
        opportunity_id="opp_1",
        company_name="Acme",
        role_title="Lead",
        industry="Tech",
        recipient_name="Alex",
        recipient_title="Director",
        recipient_class="hiring_manager",  # type: ignore
        relationship_distance="cold",  # type: ignore
    )
    assert opp.recipient_class == RecipientClass.HIRING_MANAGER
    assert opp.recipient_class.value == "hiring_manager"
    assert opp.relationship_distance == RelationshipDistance.COLD
    assert opp.relationship_distance.value == "cold"


def test_candidate_profile_loader_unsanitized_overrides() -> None:
    """ISSUE-VAL-12: CandidateProfileLoader ignores unrecognized override keys without crashing."""
    profile = CandidateProfileLoader.load_default(overrides={"extra_metadata": "123", "target_title": "CTO"})
    assert profile.target_title == "CTO"
    assert not hasattr(profile, "extra_metadata")


def test_validators_and_repair_null_guard() -> None:
    """ISSUE-VAL-13: Validators and repair_text do not crash on None or empty input."""
    for fn in [
        lambda: ChannelLengthValidator().validate(ChannelType.EMAIL, None),  # type: ignore
        lambda: QuestionEndingValidator().validate(None),  # type: ignore
        lambda: SpamTriggerValidator().validate(None),  # type: ignore
        lambda: EmDashValidator().validate(None),  # type: ignore
        lambda: MarkdownLinkValidator().validate(None),  # type: ignore
        lambda: SubordinateToneValidator().validate(None),  # type: ignore
        lambda: GroundingValidator().validate([], set(), body=None),
        lambda: ForbiddenClaimsValidator().validate(None),  # type: ignore
        lambda: UnsupportedPersonalizationValidator().validate(None),  # type: ignore
        lambda: OutboundPrivacyValidator().validate(None),  # type: ignore
        lambda: DeterministicDraftRepairer.repair_text(None),  # type: ignore
    ]:
        # None of these should raise an exception
        res = fn()
        assert res is not None
