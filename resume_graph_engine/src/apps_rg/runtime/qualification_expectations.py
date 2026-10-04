"""Loader for historical offline qualification run expectations.

Decouples historical run model expectations from production AST constants.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def load_historical_qualification_expectations() -> dict[str, Any]:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "fixtures"
        / "historical_qualification_expectations.json"
    )
    if not fixture_path.is_file():
        # Fallback to repo root or empty dict
        return {}
    return json.loads(fixture_path.read_text(encoding="utf-8"))
