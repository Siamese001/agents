"""Root conftest ensuring repo root, apps_rg, outreach_engine, and test helpers are discoverable."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_RG_SRC = _REPO_ROOT / "resume_graph_engine" / "src"
if str(_RG_SRC) not in sys.path:
    sys.path.insert(0, str(_RG_SRC))

_OE_SRC = _REPO_ROOT / "outreach_engine" / "src"
if str(_OE_SRC) not in sys.path:
    sys.path.insert(0, str(_OE_SRC))

_RG_TESTS = str(_REPO_ROOT / "resume_graph_engine" / "tests")
try:
    import tests
    if hasattr(tests, "__path__") and _RG_TESTS not in tests.__path__:
        tests.__path__.append(_RG_TESTS)
except ImportError:
    pass
