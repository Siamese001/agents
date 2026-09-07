"""Test-only process used to prove the controller launches a real command."""

from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    source = Path(os.environ["APPS_RG_EVAL_INPUT"])
    target = Path(os.environ["APPS_RG_EVAL_OUTPUT"])
    target.write_bytes(source.read_bytes())
