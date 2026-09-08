"""Apps RG-owned filesystem operations for app artifacts and receipts.

The public gateway remains intentionally small. It exposes the only operations
used by Apps RG and performs them with the standard library, so ordinary app
paths cannot acquire an external runtime dependency merely to write an
artifact.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping


class _AppsRgWriteGateway:
    """Small, app-local filesystem gateway with atomic JSON replacement."""

    @staticmethod
    def _path(path: Path | str) -> Path:
        return Path(path)

    @staticmethod
    def _ensure_not_filesystem_root(path: Path) -> None:
        resolved = path.resolve()
        if resolved == Path(resolved.anchor):
            raise ValueError("Apps RG gateway refuses to remove a filesystem root")

    def ensure_dir(self, path: Path | str) -> Path:
        target = self._path(path)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def copy_file(self, source: Path | str, destination: Path | str) -> Path:
        target = self._path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._path(source), target)
        return target

    def write_text(
        self,
        path: Path | str,
        data: str,
        *,
        encoding: str = "utf-8",
    ) -> Path:
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding=encoding)
        return target

    def write_bytes(self, path: Path | str, data: bytes) -> Path:
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def write_json_atomic(
        self,
        path: Path | str,
        payload: Mapping[str, Any] | list[Any],
        *,
        encoding: str = "utf-8",
        indent: int = 2,
        sort_keys: bool = True,
    ) -> Path:
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=indent,
            sort_keys=sort_keys,
        ) + "\n"
        handle, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        try:
            with os.fdopen(handle, "w", encoding=encoding, newline="\n") as stream:
                stream.write(serialized)
            os.replace(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return target

    def remove_file(self, path: Path | str) -> None:
        target = self._path(path)
        self._ensure_not_filesystem_root(target)
        target.unlink(missing_ok=True)

    def remove_tree(self, path: Path | str) -> None:
        target = self._path(path)
        self._ensure_not_filesystem_root(target)
        if target.exists():
            shutil.rmtree(target)


write_gateway = _AppsRgWriteGateway()

__all__ = ["write_gateway"]
