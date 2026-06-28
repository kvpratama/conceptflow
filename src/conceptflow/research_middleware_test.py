"""Unit tests for ResearchBudgetMiddleware (per-run search budget)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import ToolMessage

from conceptflow.research_middleware import ResearchBudgetMiddleware


def _completed_search(call_id: str, name: str = "tavily_search") -> ToolMessage:
    """A completed search-tool ToolMessage."""
    return ToolMessage(content="results", name=name, tool_call_id=call_id)


def _new_search_request(messages: list, name: str = "tavily_search") -> SimpleNamespace:
    """A request representing a NEW search-tool call."""
    return SimpleNamespace(
        tool_call={"name": name, "args": {"query": "x"}, "id": "new-call"},
        state={"messages": messages},
    )


async def test_passes_through_when_under_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow import research_middleware

    monkeypatch.setattr(
        research_middleware, "get_settings", lambda: SimpleNamespace(max_research_searches=3)
    )
    mw = ResearchBudgetMiddleware()
    handler = AsyncMock(
        return_value=ToolMessage(content="ran", name="tavily_search", tool_call_id="new-call")
    )

    result = await mw.awrap_tool_call(
        cast(Any, _new_search_request([_completed_search("c1")])), handler
    )

    handler.assert_awaited_once()
    assert result.content == "ran"


async def test_short_circuits_at_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow import research_middleware

    monkeypatch.setattr(
        research_middleware, "get_settings", lambda: SimpleNamespace(max_research_searches=2)
    )
    mw = ResearchBudgetMiddleware()
    handler = AsyncMock()

    messages = [_completed_search("c1"), _completed_search("c2", name="wikipedia")]
    result = await mw.awrap_tool_call(cast(Any, _new_search_request(messages)), handler)

    handler.assert_not_awaited()
    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "new-call"
    assert isinstance(result.content, str)
    assert "budget exhausted" in result.content.lower()


async def test_counts_both_search_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow import research_middleware

    monkeypatch.setattr(
        research_middleware, "get_settings", lambda: SimpleNamespace(max_research_searches=2)
    )
    mw = ResearchBudgetMiddleware()
    handler = AsyncMock()

    messages = [_completed_search("c1", name="wikipedia"), _completed_search("c2")]
    result = await mw.awrap_tool_call(
        cast(Any, _new_search_request(messages, name="wikipedia")), handler
    )
    handler.assert_not_awaited()
    assert isinstance(result.content, str)
    assert "budget exhausted" in result.content.lower()


async def test_ignores_non_search_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow import research_middleware

    monkeypatch.setattr(
        research_middleware, "get_settings", lambda: SimpleNamespace(max_research_searches=0)
    )
    mw = ResearchBudgetMiddleware()
    handler = AsyncMock(
        return_value=ToolMessage(content="ran", name="write_file", tool_call_id="w")
    )

    request = SimpleNamespace(
        tool_call={"name": "write_file", "args": {}, "id": "w"},
        state={"messages": []},
    )
    await mw.awrap_tool_call(cast(Any, request), handler)
    handler.assert_awaited_once()
