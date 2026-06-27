"""Research tools for the ConceptFlow research-agent.

Exposes a ``build_research_tools`` factory returning the in-process LangChain
search tools the research-agent uses to gather grounded information:

* ``tavily_search`` — live web search (requires ``TAVILY_API_KEY``).
* ``wikipedia`` — reliable structured background (no key required).

When ``TAVILY_API_KEY`` is absent the factory falls back to Wikipedia only, so
the pipeline still runs without a Tavily account.
"""

from __future__ import annotations

import os

from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import BaseTool
from langchain_tavily import TavilySearch


def build_research_tools() -> list[BaseTool]:
    """Return the research-agent's search tools.

    Includes ``tavily_search`` only when ``TAVILY_API_KEY`` is set in the
    environment; ``wikipedia`` is always included as a no-key fallback.

    Returns:
        A list of LangChain ``BaseTool`` instances for web/Wikipedia search.
    """
    tools: list[BaseTool] = []
    if os.environ.get("TAVILY_API_KEY"):
        tools.append(TavilySearch(max_results=5))
    tools.append(WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper()))  # ty: ignore[missing-argument]
    return tools
