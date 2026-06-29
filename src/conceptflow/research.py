"""Research tools for the ConceptFlow research-agent.

Exposes a ``build_research_tools`` factory returning the in-process LangChain
search tools the research-agent uses to gather grounded information:

* ``tavily_search`` — live web search (requires ``TAVILY_API_KEY``).
* ``wikipedia`` — reliable structured background (no key required).

When ``TAVILY_API_KEY`` is absent the factory falls back to Wikipedia only, so
the pipeline still runs without a Tavily account.

The ``wikipedia`` tool calls the MediaWiki Action API directly over async
``httpx`` rather than the unmaintained ``wikipedia`` PyPI package. A single
request uses ``generator=search`` + ``prop=extracts`` to search and fetch page
intros in one round-trip, and sends a descriptive ``User-Agent`` as required by
Wikimedia's API policy (generic agents get throttled, which yields the empty /
non-JSON responses the old package crashed on).
"""

from __future__ import annotations

import httpx
from langchain_core.tools import BaseTool, tool
from langchain_tavily import TavilySearch
from langchain_tavily._utilities import TavilySearchAPIWrapper

from conceptflow.config import get_settings

_WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
_WIKIPEDIA_MAX_QUERY_LENGTH = 300
_WIKIPEDIA_TOP_K_RESULTS = 3
_WIKIPEDIA_DOC_CONTENT_CHARS_MAX = 4000
_WIKIPEDIA_TIMEOUT_SECONDS = 10.0
_NO_RESULT_MESSAGE = "No good Wikipedia Search Result was found"


@tool("wikipedia")
async def search_wikipedia(query: str) -> str:
    """Search Wikipedia for background on a topic.

    Useful for definitions, history, and general facts about people, places,
    concepts, and events. Returns formatted page summaries for the top
    matching articles, ordered by search relevance.

    Args:
        query: The search query.

    Returns:
        Newline-separated ``Page``/``Summary`` blocks for the top results, or a
        message when nothing relevant is found or the API is unreachable.
    """
    settings = get_settings()
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "search",
        "gsrsearch": query[:_WIKIPEDIA_MAX_QUERY_LENGTH],
        "gsrlimit": _WIKIPEDIA_TOP_K_RESULTS,
        "prop": "extracts",
        "exintro": 1,
        "explaintext": 1,
        "redirects": 1,
    }
    headers = {
        "User-Agent": settings.wikipedia_user_agent,
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(
            timeout=_WIKIPEDIA_TIMEOUT_SECONDS,
            headers=headers,
        ) as client:
            response = await client.get(_WIKIPEDIA_API_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError, ValueError:
        # httpx.HTTPError: transport/timeout/status failures.
        # ValueError: non-JSON body (json.JSONDecodeError subclasses it).
        return _NO_RESULT_MESSAGE

    pages = payload.get("query", {}).get("pages", [])
    summaries = [
        f"Page: {page['title']}\nSummary: {page['extract']}"
        for page in sorted(pages, key=lambda page: page.get("index", 0))
        if page.get("extract")
    ]
    if not summaries:
        return _NO_RESULT_MESSAGE
    return "\n\n".join(summaries)[:_WIKIPEDIA_DOC_CONTENT_CHARS_MAX]


def build_research_tools() -> list[BaseTool]:
    """Return the research-agent's search tools.

    Includes ``tavily_search`` only when ``Settings.tavily_api_key`` is set;
    ``wikipedia`` is always included as a no-key fallback.

    Returns:
        A list of LangChain ``BaseTool`` instances for web/Wikipedia search.
    """
    settings = get_settings()
    tools: list[BaseTool] = []
    if settings.tavily_api_key:
        tools.append(
            TavilySearch(
                max_results=5,
                api_wrapper=TavilySearchAPIWrapper(tavily_api_key=settings.tavily_api_key),
            )
        )
    tools.append(search_wikipedia)
    return tools
