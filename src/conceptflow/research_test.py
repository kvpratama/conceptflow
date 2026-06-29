"""Tests for the research tools factory."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from langchain_core.tools import BaseTool
from pydantic import SecretStr

from conceptflow.research import build_research_tools


def _wikipedia_tool() -> BaseTool:
    """Return the built-in ``wikipedia`` tool from the factory."""
    return next(t for t in build_research_tools() if t.name == "wikipedia")


def _patch_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: dict[str, Any] | None = None,
    get_exc: Exception | None = None,
    json_exc: Exception | None = None,
    status_exc: Exception | None = None,
    capture: dict[str, Any] | None = None,
) -> None:
    """Replace ``research.httpx.AsyncClient`` with a controllable fake.

    Exactly one outcome is exercised per call: a successful JSON ``payload``,
    a transport error from ``get`` (``get_exc``), a non-JSON body
    (``json_exc``), or an HTTP status error (``status_exc``). When ``capture``
    is provided, the client/request kwargs are recorded into it.
    """
    from conceptflow import research

    class _FakeResponse:
        def raise_for_status(self) -> None:
            if status_exc is not None:
                raise status_exc

        def json(self) -> dict[str, Any]:
            if json_exc is not None:
                raise json_exc
            return payload or {}

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            if capture is not None:
                capture["client_kwargs"] = kwargs

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def get(self, url: str, params: dict[str, Any] | None = None) -> _FakeResponse:
            if capture is not None:
                capture["url"] = url
                capture["params"] = params
            if get_exc is not None:
                raise get_exc
            return _FakeResponse()

    monkeypatch.setattr(research.httpx, "AsyncClient", _FakeAsyncClient)


async def test_wikipedia_tool_returns_formatted_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wikipedia tool returns Page/Summary blocks ordered by search rank."""
    payload = {
        "query": {
            "pages": [
                {"index": 2, "title": "Tau", "extract": "Tau is two pi."},
                {"index": 1, "title": "Pi", "extract": "Pi is a constant."},
            ]
        }
    }
    _patch_client(monkeypatch, payload=payload)

    result = await _wikipedia_tool().ainvoke({"query": "pi"})

    assert "Page: Pi\nSummary: Pi is a constant." in result
    assert "Page: Tau\nSummary: Tau is two pi." in result
    # Ordered by search rank (index): Pi before Tau.
    assert result.index("Page: Pi") < result.index("Page: Tau")


async def test_wikipedia_tool_handles_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the API returns no pages, a clear message is returned."""
    _patch_client(monkeypatch, payload={"query": {"pages": []}})

    result = await _wikipedia_tool().ainvoke({"query": "asdfqwerty"})

    assert result == "No good Wikipedia Search Result was found"


async def test_wikipedia_tool_skips_pages_without_extract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pages missing an extract are skipped, not fatal."""
    payload = {
        "query": {
            "pages": [
                {"index": 1, "title": "Empty"},
                {"index": 2, "title": "Good", "extract": "Good summary."},
            ]
        }
    }
    _patch_client(monkeypatch, payload=payload)

    result = await _wikipedia_tool().ainvoke({"query": "x"})

    assert "Empty" not in result
    assert "Summary: Good summary." in result


async def test_wikipedia_tool_handles_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transport/HTTP error degrades to the fallback message, not a crash."""
    _patch_client(monkeypatch, get_exc=httpx.ConnectError("boom"))

    result = await _wikipedia_tool().ainvoke({"query": "pi"})

    assert result == "No good Wikipedia Search Result was found"


async def test_wikipedia_tool_handles_non_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-JSON body (the original crash) degrades to the fallback message."""
    _patch_client(monkeypatch, json_exc=json.JSONDecodeError("Expecting value", "", 0))

    result = await _wikipedia_tool().ainvoke({"query": "pi"})

    assert result == "No good Wikipedia Search Result was found"


async def test_wikipedia_tool_sends_descriptive_user_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The MediaWiki request carries the configured User-Agent header."""
    from conceptflow import research

    monkeypatch.setattr(
        research,
        "get_settings",
        lambda: SimpleNamespace(
            tavily_api_key=None,
            wikipedia_user_agent="MyApp/2.0 (me@example.com)",
        ),
    )
    capture: dict[str, Any] = {}
    _patch_client(monkeypatch, payload={"query": {"pages": []}}, capture=capture)

    await _wikipedia_tool().ainvoke({"query": "pi"})

    headers = capture["client_kwargs"]["headers"]
    assert headers["User-Agent"] == "MyApp/2.0 (me@example.com)"


def test_wikipedia_only_when_no_tavily_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a Tavily key in Settings the factory returns Wikipedia only."""
    from conceptflow import research

    monkeypatch.setattr(research, "get_settings", lambda: SimpleNamespace(tavily_api_key=None))
    tools = build_research_tools()
    names = {t.name for t in tools}
    assert names == {"wikipedia"}


def test_includes_tavily_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a Tavily key in Settings the factory returns both search tools."""
    from conceptflow import research

    monkeypatch.setattr(
        research,
        "get_settings",
        lambda: SimpleNamespace(tavily_api_key=SecretStr("test-key")),
    )
    tools = build_research_tools()
    names = {t.name for t in tools}
    assert "tavily_search" in names
    assert "wikipedia" in names


def test_returns_base_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every returned object is a LangChain BaseTool."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    tools = build_research_tools()
    assert tools
    assert all(isinstance(t, BaseTool) for t in tools)
