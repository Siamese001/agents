"""CrossAppEnvelope base — seal/hash/TTL contract for producer->consumer handoffs."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class EnvelopeLoadError(RuntimeError):
    """Base class for envelope load-time failures."""


class EnvelopeSchemaError(EnvelopeLoadError):
    """Envelope schema_version is incompatible with the consumer."""


class EnvelopeHashMismatchError(EnvelopeLoadError):
    """Envelope payload bytes do not match the declared source_sha256."""


class EnvelopeExpiredError(EnvelopeLoadError):
    """Envelope's emitted_at + ttl_days is in the past."""


def compute_sha256(payload: Any) -> str:
    """Return the SHA256 of payload JSON-serialized with sort_keys=True."""
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class CrossAppEnvelope(BaseModel):
    """Base envelope for cross-app producer->consumer handoffs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    SCHEMA_NAME: ClassVar[str] = "cross_app.base"
    COMPATIBLE_MAJOR: ClassVar[int] = 1

    schema_name: str
    schema_version: str = Field(
        description="semver major.minor.patch; consumer checks major compat."
    )
    trace_id: str = Field(description="Producer's run trace id.")
    producer_app: str = Field(description="e.g. 'apps_research', 'apps_shared'.")
    emitted_at: datetime = Field(description="UTC timestamp of producer emit.")
    source_sha256: str = Field(description="SHA256 of the payload JSON.")
    ttl_days: int = Field(default=30, ge=0)

    def age(self) -> timedelta:
        now = datetime.now(timezone.utc)
        emitted = self.emitted_at
        if emitted.tzinfo is None:
            emitted = emitted.replace(tzinfo=timezone.utc)
        return now - emitted

    def is_expired(self) -> bool:
        if self.ttl_days == 0:
            return False
        return self.age() > timedelta(days=self.ttl_days)

    @classmethod
    def _check_compat(cls, schema_name: str, schema_version: str) -> None:
        if schema_name != cls.SCHEMA_NAME:
            raise EnvelopeSchemaError(
                f"schema_name mismatch: expected {cls.SCHEMA_NAME!r}, "
                f"got {schema_name!r}"
            )
        if not _SEMVER_RE.match(schema_version):
            raise EnvelopeSchemaError(
                f"schema_version {schema_version!r} is not major.minor.patch"
            )
        major = int(schema_version.split(".", 1)[0])
        if major != cls.COMPATIBLE_MAJOR:
            raise EnvelopeSchemaError(
                f"schema_version major {major} incompatible with consumer "
                f"(expects major {cls.COMPATIBLE_MAJOR})"
            )

    @classmethod
    def _envelope_fields(
        cls,
        *,
        trace_id: str,
        producer_app: str,
        payload: Any,
        schema_version: str = "1.0.0",
        ttl_days: int = 30,
        emitted_at: datetime | None = None,
    ) -> dict[str, Any]:
        if emitted_at is None:
            emitted_at = datetime.now(timezone.utc)
        return dict(
            schema_name=cls.SCHEMA_NAME,
            schema_version=schema_version,
            trace_id=trace_id,
            producer_app=producer_app,
            emitted_at=emitted_at,
            source_sha256=compute_sha256(payload),
            ttl_days=ttl_days,
        )

    def dump_json(self) -> str:
        return self.model_dump_json(indent=2)

    def write_sidecar(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dump_json(), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path, *, check_expiry: bool = True) -> "CrossAppEnvelope":
        if not path.is_file():
            raise FileNotFoundError(f"Envelope not found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EnvelopeLoadError(f"Malformed envelope JSON at {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise EnvelopeLoadError(f"Envelope must be a JSON object, got {type(data).__name__}")
        cls._check_compat(data.get("schema_name", ""), data.get("schema_version", ""))
        try:
            env = cls.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            raise EnvelopeSchemaError(
                f"Envelope at {path} failed {cls.__name__} validation: {exc}"
            ) from exc
        payload = getattr(env, "payload", None)
        if payload is not None:
            expected = compute_sha256(payload)
            if expected != env.source_sha256:
                raise EnvelopeHashMismatchError(
                    f"Envelope hash mismatch at {path}: declared={env.source_sha256} computed={expected}"
                )
        if check_expiry and env.is_expired():
            raise EnvelopeExpiredError(
                f"Envelope at {path} expired: age={env.age()} ttl={env.ttl_days}d"
            )
        return env


__all__ = [
    "CrossAppEnvelope",
    "EnvelopeExpiredError",
    "EnvelopeHashMismatchError",
    "EnvelopeLoadError",
    "EnvelopeSchemaError",
    "compute_sha256",
]
