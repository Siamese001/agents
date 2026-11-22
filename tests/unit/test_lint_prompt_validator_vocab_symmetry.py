"""Bilateral recall-and-precision tests for INV-PROMPT-VALIDATOR-VOCAB-SYMMETRY."""

from __future__ import annotations

import shutil
from pathlib import Path

from tools.lint_prompt_validator_vocab_symmetry import (
    ARSENAL_LEDGER_REL_PATH,
    HEADLINE_PA_REL_PATH,
    MANDATORY_CONSUMER_IMPORTS,
    SSOT_REL_PATH,
    audit_prompt_validator_vocab_symmetry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _stage_minimal_repo(tmp_path: Path) -> Path:
    for rel in (SSOT_REL_PATH, ARSENAL_LEDGER_REL_PATH, *MANDATORY_CONSUMER_IMPORTS.keys()):
        src = REPO_ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return tmp_path


def test_live_repository_passes_prompt_validator_vocab_symmetry() -> None:
    """Precision gate: live repository SSOT and consumers must pass with zero false positives."""
    violations = audit_prompt_validator_vocab_symmetry(REPO_ROOT)
    assert violations == []


def test_linter_detects_prompt_noun_rejected_by_validator_regex(tmp_path: Path) -> None:
    """Recall gate: adding a prompt noun not matched by HEADLINE_EXECUTIVE_ABSTRACTION_RE fails."""
    staged = _stage_minimal_repo(tmp_path)
    ssot_file = staged / SSOT_REL_PATH
    text = ssot_file.read_text(encoding="utf-8")
    ssot_file.write_text(
        text.replace('"Enterprise",\n)', '"Enterprise",\n    "UnmatchedBuzzwordToken",\n)'),
        encoding="utf-8",
    )
    violations = audit_prompt_validator_vocab_symmetry(staged)
    assert any("UnmatchedBuzzwordToken" in v for v in violations)


def test_linter_detects_root_phrase_violating_compact_or_abstraction_gate(tmp_path: Path) -> None:
    """Recall gate: headline_pa root phrase >3 words or missing abstraction noun fails."""
    staged = _stage_minimal_repo(tmp_path)
    pa_file = staged / HEADLINE_PA_REL_PATH
    text = pa_file.read_text(encoding="utf-8")
    pa_file.write_text(
        text.replace('"Agentic AI Platforms"', '"Four Word Agile Scrum"'),
        encoding="utf-8",
    )
    violations = audit_prompt_validator_vocab_symmetry(staged)
    assert any("exceeds 3-word compact cap" in v for v in violations)
    assert any("fails HEADLINE_EXECUTIVE_ABSTRACTION_RE" in v for v in violations)


def test_linter_detects_credential_leak_and_local_validator_shadow(tmp_path: Path) -> None:
    """Recall gate: unsanitized credential hint or local shadow regex in headline_x2 fails."""
    staged = _stage_minimal_repo(tmp_path)
    ssot_file = staged / SSOT_REL_PATH
    ssot_text = ssot_file.read_text(encoding="utf-8")
    ssot_file.write_text(
        ssot_text.replace(
            "tok not in _FORBIDDEN_CREDENTIAL_TOKEN_SET",
            "True",
        ),
        encoding="utf-8",
    )
    hx2_file = staged / "resume_graph_engine/src/apps_rg/runtime/validators/headline_x2.py"
    hx2_text = hx2_file.read_text(encoding="utf-8")
    hx2_file.write_text(
        hx2_text.replace(
            "_EXECUTIVE_ABSTRACTION_RE = HEADLINE_EXECUTIVE_ABSTRACTION_RE",
            '_EXECUTIVE_ABSTRACTION_RE = re.compile(r"\\bplatforms?\\b")',
        ),
        encoding="utf-8",
    )
    violations = audit_prompt_validator_vocab_symmetry(staged)
    assert any("leaks forbidden credential tokens" in v for v in violations)
    assert any("locally redefines _EXECUTIVE_ABSTRACTION_RE" in v for v in violations)
