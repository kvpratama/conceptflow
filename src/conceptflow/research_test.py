"""Tests for the research tools factory."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.tools import BaseTool
from pydantic import SecretStr

from conceptflow.research import build_research_tools


def _wikipedia_tool() -> BaseTool:
    """Return the built-in ``wikipedia`` tool from the factory."""
    return next(t for t in build_research_tools() if t.name == "wikipedia")


async def test_wikipedia_tool_returns_formatted_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wikipedia tool searches, fetches pages, and formats summaries."""
    from conceptflow import research

    monkeypatch.setattr(research.wikipedia, "search", lambda q, results: ["Pi", "Tau"])
    pages = {
        "Pi": SimpleNamespace(summary="Pi is a constant."),
        "Tau": SimpleNamespace(summary="Tau is two pi."),
    }
    monkeypatch.setattr(research.wikipedia, "page", lambda title, auto_suggest: pages[title])

    result = await _wikipedia_tool().ainvoke({"query": "pi"})

    assert "Page: Pi" in result
    assert "Summary: Pi is a constant." in result
    assert "Page: Tau" in result


async def test_wikipedia_tool_handles_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """When search finds nothing, a clear message is returned."""
    from conceptflow import research

    monkeypatch.setattr(research.wikipedia, "search", lambda q, results: [])

    result = await _wikipedia_tool().ainvoke({"query": "asdfqwerty"})

    assert result == "No good Wikipedia Search Result was found"


async def test_wikipedia_tool_skips_unresolvable_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pages raising PageError/DisambiguationError are skipped, not fatal."""
    from conceptflow import research

    monkeypatch.setattr(research.wikipedia, "search", lambda q, results: ["Bad", "Good"])

    def fake_page(title: str, auto_suggest: bool) -> object:
        if title == "Bad":
            raise research.wikipedia.exceptions.PageError(title)
        return SimpleNamespace(summary="Good summary.")

    monkeypatch.setattr(research.wikipedia, "page", fake_page)

    result = await _wikipedia_tool().ainvoke({"query": "x"})

    assert "Bad" not in result
    assert "Summary: Good summary." in result


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
    from langchain_core.tools import BaseTool

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    tools = build_research_tools()
    assert tools
    assert all(isinstance(t, BaseTool) for t in tools)
