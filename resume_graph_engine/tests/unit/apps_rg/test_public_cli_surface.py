"""Guard the one supported Apps RG end-to-end command surface."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps_rg.__main__ import _build_parser


REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_CLI_MODULE = REPO_ROOT / "src" / "apps_rg" / "__main__.py"
PUBLIC_DOCUMENTS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "APPS_RG_V2_CANONICAL_ENTRYPOINTS.md",
    REPO_ROOT / "src" / "apps_rg" / "runtime" / "RUNBOOK_E2E.md",
    REPO_ROOT / "src" / "apps_rg" / "config" / "targeting" / "README.md",
)


def test_public_cli_exposes_only_run_eval_and_show_actions() -> None:
    parser = _build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "action")

    assert set(subparsers.choices) == {"run", "eval", "show"}
    assert parser.parse_args(["run"]).action == "run"
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["run", "--mode", "deterministic"])
    assert excinfo.value.code == 2


def test_only_public_module_cli_invokes_the_whole_resume_runner() -> None:
    text = PUBLIC_CLI_MODULE.read_text(encoding="utf-8")
    assert "run_canonical_apps_rg_from_cli_primitives(" in text
    assert "run_bare_e2e(" not in text
    assert "_evaluate_product_run(" in text


def test_apps_rg_has_one_executable_module_cli() -> None:
    executable_modules: list[Path] = []
    for path in (REPO_ROOT / "src" / "apps_rg").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if 'if __name__ == "__main__":' not in text:
            continue
        if "raise SystemExit(" in text or "\n    main()" in text or "\n    sys.exit(main())" in text:
            executable_modules.append(path)

    assert executable_modules == [PUBLIC_CLI_MODULE]


def test_retired_pre_run_cli_is_physically_absent() -> None:
    assert not (REPO_ROOT / "src" / "apps_rg" / "runtime" / "prepare_orchestrator_inputs.py").exists()


def test_public_documentation_contains_no_retired_top_level_command_shape() -> None:
    for path in PUBLIC_DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        assert "python -m apps_rg --" not in text, path.as_posix()
        assert "python -m apps_rg run --mode" not in text, path.as_posix()
        assert "python -m apps_rg run --resume-run-dir" not in text, path.as_posix()
        assert "python -m apps_rg.runtime.prepare_orchestrator_inputs" not in text, path.as_posix()


def test_agentic_core_is_physically_absent() -> None:
    assert not (REPO_ROOT / "src" / "agentic_core").exists()
    assert not (REPO_ROOT / "tests" / "unit" / "agentic_core").exists()
    assert not (REPO_ROOT / "agentic_core").exists()


def test_competing_clis_fail_closed(capsys: pytest.CaptureFixture[str]) -> None:
    from apps_research import __main__ as research_main
    from apps_eval import __main__ as eval_main

    assert research_main.main([]) == 1
    captured = capsys.readouterr()
    assert "APPS_RG_CLI_VIOLATION" in captured.err
    assert "python -m apps_rg run" in captured.err

    assert eval_main.main([]) == 1
    captured = capsys.readouterr()
    assert "APPS_RG_CLI_VIOLATION" in captured.err
    assert "python -m apps_rg eval" in captured.err


def test_apps_rg_evals_subpackages_have_no_main_entrypoints() -> None:
    evals_mains = list((REPO_ROOT / "src" / "apps_rg" / "evals").rglob("__main__.py"))
    assert evals_mains == [], f"nested __main__.py found in evals: {evals_mains}"

