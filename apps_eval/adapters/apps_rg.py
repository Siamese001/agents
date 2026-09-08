"""Backward-compatibility shim for apps_eval.adapters.resume_graph_engine."""

from __future__ import annotations

import sys
from apps_eval.adapters import resume_graph_engine

sys.modules[__name__] = resume_graph_engine
