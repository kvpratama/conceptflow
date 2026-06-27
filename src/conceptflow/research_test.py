"""Tests for the research tools factory."""

from __future__ import annotations

import pytest

from conceptflow.research import build_research_tools


def test_wikipedia_only_when_no_tavily_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without TAVILY_API_KEY the factory returns Wikipedia only."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    tools = build_research_tools()
    names = {t.name for t in tools}
    assert names == {"wikipedia"}


def test_includes_tavily_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """With TAVILY_API_KEY set the factory returns both search tools."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
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
