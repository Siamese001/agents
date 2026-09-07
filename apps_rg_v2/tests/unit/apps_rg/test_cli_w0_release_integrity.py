from __future__ import annotations


def test_whole_resume_cli_does_not_expose_a_fresh_e2e_bypass() -> None:
    from apps_rg.__main__ import _build_parser

    parser = _build_parser()
    run = parser.parse_args(["run"])

    assert not hasattr(run, "fresh_e2e")
