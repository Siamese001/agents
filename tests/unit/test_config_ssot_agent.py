"""Unit tests for tools.config_ssot_agent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.config_ssot_agent import (
    ConfigDomain,
    ExemptionManager,
    SSOTRegistry,
    SSOTReporter,
    SSOTScanner,
    SSOTViolation,
    ViolationSeverity,
    ViolationType,
)
from tools.config_ssot_agent.cli import main


def test_registry_initialization():
    """Verify SSOTRegistry initializes domains and loads model catalog."""
    registry = SSOTRegistry()
    assert ConfigDomain.MODELS in registry.domains
    assert ConfigDomain.TIMEOUTS in registry.domains
    assert ConfigDomain.ENV_VARS in registry.domains

    # Known models should be registered
    assert "gpt-5.6-luna" in registry.known_models


def test_exemption_manager_inline_directives(tmp_path: Path):
    """Verify inline # ssot: exempt directives are respected."""
    mgr = ExemptionManager()
    assert mgr.is_line_exempt(
        "# ssot: exempt(HARDCODED_MODEL_LITERAL)", ViolationType.HARDCODED_MODEL_LITERAL
    )
    assert mgr.is_line_exempt("val = 'gpt-5.6'  # ssot: exempt(ALL)", ViolationType.HARDCODED_MODEL_LITERAL)
    assert not mgr.is_line_exempt("val = 'gpt-5.6'  # other comment", ViolationType.HARDCODED_MODEL_LITERAL)


def test_ast_hardcoded_model_detection(tmp_path: Path):
    """Verify scanner flags hardcoded model names."""
    code = """
def call_llm():
    model_name = "gpt-5.6"
    return model_name
"""
    test_file = tmp_path / "model_sample.py"
    test_file.write_text(code, encoding="utf-8")

    scanner = SSOTScanner()
    violations = scanner.scan_file(test_file)

    model_viols = [v for v in violations if v.violation_type == ViolationType.HARDCODED_MODEL_LITERAL]
    assert len(model_viols) == 1
    assert model_viols[0].detected_value == "gpt-5.6"
    assert model_viols[0].line == 3


def test_ast_hardcoded_model_with_exemption(tmp_path: Path):
    """Verify inline exemption suppresses model violation."""
    code = """
def call_llm():
    model_name = "gpt-5.6"  # ssot: exempt(HARDCODED_MODEL_LITERAL)
    return model_name
"""
    test_file = tmp_path / "model_exempt.py"
    test_file.write_text(code, encoding="utf-8")

    scanner = SSOTScanner()
    violations = scanner.scan_file(test_file)

    model_viols = [v for v in violations if v.violation_type == ViolationType.HARDCODED_MODEL_LITERAL]
    assert len(model_viols) == 0


def test_ast_direct_env_access(tmp_path: Path):
    """Verify scanner flags direct os.environ and os.getenv calls."""
    code = """
import os

def load_key():
    k = os.environ["OPENAI_API_KEY"]
    h = os.getenv("HOST", "localhost")
    return k, h
"""
    test_file = tmp_path / "env_sample.py"
    test_file.write_text(code, encoding="utf-8")

    scanner = SSOTScanner()
    violations = scanner.scan_file(test_file)

    env_viols = [v for v in violations if v.violation_type == ViolationType.DIRECT_ENV_ACCESS]
    assert len(env_viols) == 2


def test_ast_hardcoded_timeout(tmp_path: Path):
    """Verify scanner flags hardcoded timeout parameters."""
    code = """
import requests

def fetch():
    return requests.get("https://example.com", timeout=30.0)
"""
    test_file = tmp_path / "timeout_sample.py"
    test_file.write_text(code, encoding="utf-8")

    scanner = SSOTScanner()
    violations = scanner.scan_file(test_file)

    timeout_viols = [v for v in violations if v.violation_type == ViolationType.HARDCODED_TIMEOUT]
    assert len(timeout_viols) == 1
    assert timeout_viols[0].detected_value == "timeout=30.0"


def test_reporter_json_and_markdown(tmp_path: Path):
    """Verify SSOTReporter produces valid JSON and Markdown outputs."""
    code = """
import os
model = "gpt-5.6"
key = os.environ.get("MY_KEY")
"""
    test_file = tmp_path / "report_sample.py"
    test_file.write_text(code, encoding="utf-8")

    scanner = SSOTScanner()
    result = scanner.scan([test_file])
    reporter = SSOTReporter(result)

    json_path = tmp_path / "out.json"
    reporter.write_json(json_path)
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert data["stats"]["total_violations"] >= 2

    md_path = tmp_path / "out.md"
    reporter.write_markdown(md_path)
    assert md_path.exists()
    assert "# Config SSOT Violation Scan Report" in md_path.read_text()


def test_cli_scan_runner(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Verify CLI main entry point runs scan subcommand."""
    code = """
x = "gpt-5.6"
"""
    test_file = tmp_path / "cli_sample.py"
    test_file.write_text(code, encoding="utf-8")
    json_out = tmp_path / "cli_out.json"

    ret = main(["scan", "-p", str(test_file), "-o", str(json_out), "--format", "json"])
    assert ret == 0
    assert json_out.exists()

    captured = capsys.readouterr()
    assert "CONFIG SSOT ENFORCEMENT SCAN SUMMARY" in captured.out
