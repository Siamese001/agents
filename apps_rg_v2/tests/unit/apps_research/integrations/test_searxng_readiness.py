from __future__ import annotations

import json

from apps_research.integrations import searxng_readiness as readiness


class _Response:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self._body


def test_json_probe_rejects_http_200_with_zero_results(monkeypatch) -> None:
    monkeypatch.setattr(
        readiness,
        "urlopen",
        lambda *_args, **_kwargs: _Response({"results": []}),
    )

    ready, detail = readiness._probe_json_search(
        "http://localhost:8080", timeout=1
    )

    assert ready is False
    assert detail == "results=0"


def test_json_probe_requires_and_accepts_nonempty_result_list(monkeypatch) -> None:
    monkeypatch.setattr(
        readiness,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {"results": [{"url": "https://www.anthropic.com/"}]}
        ),
    )

    ready, detail = readiness._probe_json_search(
        "http://localhost:8080", timeout=1
    )

    assert ready is True
    assert detail == "results=1"
