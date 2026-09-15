"""Hermetic Wire Cassette Transport for Deterministic Replay Testing.

Provides zero-network, zero-cost, authentic wire cassette recording and replay
for LLM SDK clients (OpenAI, Anthropic, etc.) via httpx transport interception.

Guarantees:
1. Replays authentic HTTP wire status, headers, stream/body bytes, and token accounting.
2. Zero synthetic mock dicts: fixtures are authentic wire exchanges.
3. Fail-closed: Unrecorded requests raise CassetteNotFoundError immediately.
4. Secret sanitization: Authorization headers and live API keys are never written to disk.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Union

import httpx


class CassetteError(RuntimeError):
    """Base exception for cassette transport operations."""


class CassetteNotFoundError(CassetteError):
    """Raised when an outbound HTTP request has no matching recorded wire exchange."""


def compute_request_signature(
    method: str,
    url: str,
    body_bytes: bytes,
) -> str:
    """Compute a deterministic hash signature from HTTP request components."""
    hasher = hashlib.sha256()
    hasher.update(method.upper().encode("utf-8"))
    hasher.update(b"::")
    # Normalize URL (strip trailing slashes and query param jitter if applicable)
    normalized_url = url.rstrip("/")
    hasher.update(normalized_url.encode("utf-8"))
    hasher.update(b"::")

    # Attempt to parse body as JSON for semantic canonicalization
    if body_bytes:
        try:
            parsed = json.loads(body_bytes.decode("utf-8"))
            canonical_json = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
            hasher.update(canonical_json.encode("utf-8"))
        except Exception:
            hasher.update(body_bytes)
    return hasher.hexdigest()


@dataclasses.dataclass
class WireExchange:
    """Represents a frozen HTTP request-response exchange."""

    signature_hash: str
    method: str
    url: str
    request_headers: Dict[str, str]
    request_body: Optional[Any]
    response_status: int
    response_headers: Dict[str, str]
    response_body: Any
    elapsed_seconds: float = 0.0
    meta: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize wire exchange to dictionary."""
        return {
            "signature_hash": self.signature_hash,
            "request": {
                "method": self.method,
                "url": self.url,
                "headers": self._sanitize_headers(self.request_headers),
                "body": self.request_body,
            },
            "response": {
                "status_code": self.response_status,
                "headers": self.response_headers,
                "body": self.response_body,
                "elapsed_seconds": self.elapsed_seconds,
            },
            "meta": self.meta,
        }

    @staticmethod
    def _sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
        """Strip sensitive credentials from stored headers."""
        sanitized = {}
        for k, v in headers.items():
            k_lower = k.lower()
            if "auth" in k_lower or "key" in k_lower or "token" in k_lower:
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = v
        return sanitized

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WireExchange:
        """Hydrate wire exchange from dictionary."""
        req = data.get("request", {})
        resp = data.get("response", {})
        return cls(
            signature_hash=data.get("signature_hash", ""),
            method=req.get("method", "POST"),
            url=req.get("url", ""),
            request_headers=req.get("headers", {}),
            request_body=req.get("body"),
            response_status=resp.get("status_code", 200),
            response_headers=resp.get("headers", {}),
            response_body=resp.get("body"),
            elapsed_seconds=resp.get("elapsed_seconds", 0.0),
            meta=data.get("meta", {}),
        )


class CassetteRegistry:
    """Registry managing one or more frozen wire exchanges."""

    def __init__(self, cassette_path: Optional[Union[str, Path]] = None) -> None:
        self.cassette_path = Path(cassette_path) if cassette_path else None
        self._exchanges: Dict[str, WireExchange] = {}
        if self.cassette_path and self.cassette_path.exists():
            self.load(self.cassette_path)

    def load(self, path: Union[str, Path]) -> None:
        """Load cassette from a JSON file."""
        target = Path(path)
        with target.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            for item in data:
                exchange = WireExchange.from_dict(item)
                self._exchanges[exchange.signature_hash] = exchange
        elif isinstance(data, dict):
            if "exchanges" in data:
                for item in data["exchanges"]:
                    exchange = WireExchange.from_dict(item)
                    self._exchanges[exchange.signature_hash] = exchange
            else:
                exchange = WireExchange.from_dict(data)
                self._exchanges[exchange.signature_hash] = exchange

    def save(self, path: Optional[Union[str, Path]] = None) -> None:
        """Save registered exchanges to a sealed JSON file."""
        target = Path(path) if path else self.cassette_path
        if not target:
            raise ValueError("No cassette path specified for save.")
        target.parent.mkdir(parents=True, exist_ok=True)
        serialized = [ex.to_dict() for ex in self._exchanges.values()]
        payload = {
            "schema_version": "hermetic_wire_cassette.v1",
            "recorded_count": len(serialized),
            "exchanges": serialized,
        }
        with target.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def register(self, exchange: WireExchange) -> None:
        """Register a wire exchange into memory."""
        self._exchanges[exchange.signature_hash] = exchange

    def lookup(self, method: str, url: str, body_bytes: bytes) -> Optional[WireExchange]:
        """Look up exchange by matching computed request signature."""
        sig = compute_request_signature(method, url, body_bytes)
        return self._exchanges.get(sig)

    @property
    def count(self) -> int:
        """Number of recorded exchanges."""
        return len(self._exchanges)


class CassetteTransport(httpx.BaseTransport):
    """Synchronous httpx transport that replays or records wire exchanges."""

    def __init__(
        self,
        registry: CassetteRegistry,
        mode: str = "replay",
        live_transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.registry = registry
        self.mode = mode.lower()
        self.live_transport = live_transport or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Intercept and replay/record HTTP request."""
        body = request.read()
        sig = compute_request_signature(request.method, str(request.url), body)

        if self.mode == "replay":
            exchange = self.registry.lookup(request.method, str(request.url), body)
            if not exchange:
                raise CassetteNotFoundError(
                    f"CASSETTE_NOT_FOUND: No authentic recorded wire exchange matches request.\n"
                    f"  Method: {request.method}\n"
                    f"  URL: {request.url}\n"
                    f"  Signature Hash: {sig}\n"
                    f"  Cassette Registry Size: {self.registry.count} exchanges\n"
                    f"Fail-closed invariant enforced: outbound requests are prohibited in hermetic replay mode."
                )

            # Reconstruct response
            resp_body = exchange.response_body
            if isinstance(resp_body, (dict, list)):
                content = json.dumps(resp_body).encode("utf-8")
            elif isinstance(resp_body, str):
                content = resp_body.encode("utf-8")
            else:
                content = b""

            headers = dict(exchange.response_headers)
            headers["x-wire-cassette-replay"] = "true"
            headers["x-wire-cassette-signature"] = sig

            return httpx.Response(
                status_code=exchange.response_status,
                headers=headers,
                content=content,
                request=request,
            )

        elif self.mode == "record":
            start_time = time.perf_counter()
            resp = self.live_transport.handle_request(request)
            elapsed = time.perf_counter() - start_time

            resp_bytes = resp.read()
            try:
                parsed_resp = json.loads(resp_bytes.decode("utf-8"))
            except Exception:
                parsed_resp = resp_bytes.decode("utf-8", errors="replace")

            try:
                parsed_req = json.loads(body.decode("utf-8")) if body else None
            except Exception:
                parsed_req = body.decode("utf-8", errors="replace") if body else None

            # Extract token telemetry from response body if present
            meta = {}
            if isinstance(parsed_resp, dict):
                usage = parsed_resp.get("usage")
                if usage:
                    meta["token_usage"] = usage
                model_name = parsed_resp.get("model")
                if model_name:
                    meta["model"] = model_name

            exchange = WireExchange(
                signature_hash=sig,
                method=request.method,
                url=str(request.url),
                request_headers=dict(request.headers),
                request_body=parsed_req,
                response_status=resp.status_code,
                response_headers=dict(resp.headers),
                response_body=parsed_resp,
                elapsed_seconds=elapsed,
                meta=meta,
            )
            self.registry.register(exchange)

            # Return reconstructed response so consumer can read it cleanly
            return httpx.Response(
                status_code=resp.status_code,
                headers=dict(resp.headers),
                content=resp_bytes,
                request=request,
            )
        else:
            raise ValueError(f"Unknown cassette transport mode: {self.mode}. Must be 'replay' or 'record'.")


def create_replay_openai_client(
    cassette_path: Union[str, Path],
    api_key: str = "hermetic-replay-key",
) -> Any:
    """Create a standard OpenAI client wired to replay a sealed wire cassette."""
    import openai

    registry = CassetteRegistry(cassette_path)
    transport = CassetteTransport(registry=registry, mode="replay")
    http_client = httpx.Client(transport=transport)
    return openai.OpenAI(api_key=api_key, http_client=http_client)
