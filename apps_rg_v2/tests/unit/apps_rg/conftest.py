"""conftest for apps_rg tests - handles Pydantic V2 deprecation warnings and package shadowing."""

import os
import shutil
import sys
import warnings
from pathlib import Path

import pytest

# Omitted source-only dependencies are reported by their individual modules as
# explicit skips. No whole-file collection quarantine is permitted here.

# Ensure repo root is on sys.path BEFORE any test module import
_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Purge any apps_rg shadow registered from tests/unit/apps_rg/__init__.py
# so imports like `from apps_rg.config.X import Y` resolve to the real package
_TESTS_ROOT = str(Path(__file__).resolve().parents[2])
_to_purge = [
    k
    for k, m in sys.modules.items()
    if k != __name__
    and (k == "apps_rg" or k.startswith("apps_rg."))
    and _TESTS_ROOT in (getattr(m, "__file__", "") or "")
]
for _k in _to_purge:
    del sys.modules[_k]

# Filter Pydantic V2 deprecation warnings to prevent collection errors
warnings.filterwarnings(
    "ignore",
    message=".*PydanticDeprecatedSince20.*",
    category=DeprecationWarning,
)


@pytest.fixture(scope="session", autouse=True)
def _repository_artifact_isolation(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Keep graph refreshes and R1B caches out of repository-owned artifacts."""
    session_root = tmp_path_factory.mktemp("apps_rg_repository_artifacts")
    source_graph = (
        Path(_REPO_ROOT)
        / "artifacts"
        / "apps_rg"
        / "fact_inventory"
        / "augmented_skills_graph.sqlite"
    )
    isolated_graph = session_root / "augmented_skills_graph.sqlite"
    shutil.copy2(source_graph, isolated_graph)

    isolated_env = {
        "APPS_RG_AUGMENTED_SKILLS_GRAPH_SQLITE_PATH": str(isolated_graph),
        "APPS_RG_R1B_CACHE_ROOT": str(session_root / "r1b_cache"),
        # The unit harness owns this test-only secret. Production has no
        # fallback: missing cache signing material fails cache reads closed.
        "APPS_RG_R1B_CACHE_INTEGRITY_HMAC_KEY": "apps-rg-unit-test-cache-integrity-key-0001",
    }
    previous = {name: os.environ.get(name) for name in isolated_env}
    os.environ.update(isolated_env)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
warnings.filterwarnings(
    "ignore",
    message=".*Pydantic V1 style.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*Support for class-based.*",
    category=DeprecationWarning,
)


@pytest.fixture(autouse=True)
def _apps_rg_unit_test_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unit tests are not ``python -m apps_rg`` product runs — relax fail-closed shortcuts."""
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")
    monkeypatch.setenv(
        "APPS_RG_C03_GRAPH_SQLITE_CONTEXT_RECEIPT_DIR",
        str(tmp_path / "c03_context_receipts"),
    )


@pytest.fixture(autouse=True)
def _w6_r1b_order_isolation(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """W6 receipt tests fail under full-suite env leaks; isolate cache/Chroma per test."""
    nodeid = request.node.nodeid.replace("\\", "/")
    if "section_evidence_w6" not in nodeid:
        yield
        return
    from apps_rg.cache.r1b_bge_embedding import reset_bge_model_for_testing

    reset_bge_model_for_testing()
    cache_root = tmp_path / "r1b_cache"
    chroma_dir = tmp_path / "chroma"
    monkeypatch.setenv("APPS_RG_R1B_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(chroma_dir))
    monkeypatch.delenv("APPS_RG_R1B_SKIP_CHROMA_PROJECTION", raising=False)
    monkeypatch.delenv("APPS_RG_R1B_SKIP_UWG", raising=False)
    yield
    reset_bge_model_for_testing()
