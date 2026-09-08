"""Backward-compatibility shim for apps_eval.adapters.outreach_engine."""

from __future__ import annotations

import sys
from apps_eval.adapters import outreach_engine

sys.modules[__name__] = outreach_engine
