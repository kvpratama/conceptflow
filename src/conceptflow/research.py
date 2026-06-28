"""Research tools for the ConceptFlow research-agent.

Exposes a ``build_research_tools`` factory returning the in-process LangChain
search tools the research-agent uses to gather grounded information:

* ``tavily_search`` — live web search (requires ``TAVILY_API_KEY``).
* ``wikipedia`` — reliable structured background (no key required).

When ``TAVILY_API_KEY`` is absent the factory falls back to Wikipedia only, so
the pipeline still runs without a Tavily account.

The ``wikipedia`` tool wraps the standalone ``wikipedia`` PyPI package directly
rather than ``langchain-community`` (which is sunset and unmaintained).
"""

from __future__ import annotations

import os

import wikipedia
from langchain_core.tools import BaseTool, tool
from langchain_tavily import TavilySearch

_WIKIPEDIA_MAX_QUERY_LENGTH = 300
_WIKIPEDIA_TOP_K_RESULTS = 3
_WIKIPEDIA_DOC_CONTENT_CHARS_MAX = 4000


@tool("wikipedia")
def search_wikipedia(query: str) -> str:
    """Search Wikipedia for background on a topic.

    Useful for definitions, history, and general facts about people, places,
    concepts, and events. Returns formatted page summaries for the top
    matching articles.

    Args:
        query: The search query.

    Returns:
        Newline-separated ``Page``/``Summary`` blocks for the top results, or a
        message when nothing relevant is found.
    """
    page_titles = wikipedia.search(
        query[:_WIKIPEDIA_MAX_QUERY_LENGTH], results=_WIKIPEDIA_TOP_K_RESULTS
    )
    summaries: list[str] = []
    for page_title in page_titles[:_WIKIPEDIA_TOP_K_RESULTS]:
        try:
            page = wikipedia.page(title=page_title, auto_suggest=False)
        except wikipedia.exceptions.PageError, wikipedia.exceptions.DisambiguationError:
            continue
        summaries.append(f"Page: {page_title}\nSummary: {page.summary}")
    if not summaries:
        return "No good Wikipedia Search Result was found"
    return "\n\n".join(summaries)[:_WIKIPEDIA_DOC_CONTENT_CHARS_MAX]


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
    tools.append(search_wikipedia)
    return tools
