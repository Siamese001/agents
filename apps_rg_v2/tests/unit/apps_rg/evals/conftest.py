from __future__ import annotations

import os

import pytest

from apps_rg.evals import resume_graph_evaluation
from apps_rg.evals.c03_human_eval import cli as human_eval_main
from apps_rg.evals.c03_human_eval import _io


@pytest.fixture
def emulated_posix_private_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let packet-logic tests run when the host cannot inspect POSIX ownership.

    Product code still fails closed on that host. Dedicated I/O tests cover the
    unsupported-platform behavior; this fixture isolates content and authority
    assertions from the unavailable filesystem capability.
    """

    if callable(getattr(os, "getuid", None)):
        return

    def private_metadata_passes(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(_io, "owner_only_security_error", lambda: None)
    monkeypatch.setattr(_io, "private_metadata_error", private_metadata_passes)
    monkeypatch.setattr(
        human_eval_main,
        "private_metadata_error",
        private_metadata_passes,
    )
    monkeypatch.setattr(
        resume_graph_evaluation,
        "private_metadata_error",
        private_metadata_passes,
    )
