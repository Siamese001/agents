"""apps_rg package."""
from __future__ import annotations

__version__ = "0.1.0"


def ensure_dotenv_loaded() -> None:
    """Load the repo-root ``.env`` lazily on explicit runtime entry rather than package import."""
    import os
    import sys

    if "pytest" in sys.modules:
        return
    if os.environ.get("APPS_RG_TEST_HARNESS"):
        return
    if os.environ.get("APPS_RG_SKIP_DOTENV_AUTOLOAD"):
        return
    try:
        from apps_rg.runtime.env_bootstrap import bootstrap_apps_rg_env

        bootstrap_apps_rg_env()
    except Exception:  # noqa: BLE001  # guardian: allow-broad-exception -- explicitly approved governance exemption
        pass
