"""Load a src-layout package before the external editable source checkout."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


def bootstrap_src_package(package_name: str, namespace: dict[str, Any]) -> None:
    """Execute ``src/<package>/__init__.py`` in its root shim module."""
    repository_root = Path(__file__).resolve().parent
    src_root = repository_root / "src"
    package_root = src_root / package_name
    real_init = package_root / "__init__.py"
    if not real_init.is_file():
        raise ImportError(f"Missing standalone package initializer: {real_init}")

    src_entry = str(src_root)
    try:
        sys.path.remove(src_entry)
    except ValueError:
        pass
    sys.path.insert(0, src_entry)

    namespace["__file__"] = str(real_init)
    namespace["__path__"] = [str(package_root)]
    namespace["__package__"] = package_name
    spec = namespace.get("__spec__")
    if spec is not None:
        spec.origin = str(real_init)
        spec.submodule_search_locations = [str(package_root)]

    source = real_init.read_bytes()
    exec(compile(source, str(real_init), "exec"), namespace)


__all__ = ["bootstrap_src_package"]
