"""Subagent middleware that bounds the research-agent's search budget.

The research-agent gathers grounded facts by calling its search tools
(``tavily_search`` and ``wikipedia``). Live web search costs money and adds
latency, so — mirroring the QA round budget — this middleware caps the number
of completed search calls per run at ``max_research_searches`` and
short-circuits further ones with a synthetic ToolMessage instructing the agent
to write /research.md with what it has.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from conceptflow.config import get_settings

_SEARCH_TOOLS = {"tavily_search", "wikipedia"}


def _count_prior_searches(state: dict[str, Any]) -> int:
    """Count completed search-tool calls in the research-agent's state.

    Args:
        state: The research-agent's agent state.

    Returns:
        The number of completed ``tavily_search``/``wikipedia`` tool calls.
    """
    messages = state.get("messages") or []
    return sum(
        1
        for m in messages
        if isinstance(m, ToolMessage) and getattr(m, "name", None) in _SEARCH_TOOLS
    )


class ResearchBudgetMiddleware(AgentMiddleware):
    """Short-circuit research search calls once the budget is spent."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Enforce ``max_research_searches`` on search-tool calls.

        Args:
            request: The intercepted tool call (with ``tool_call`` and ``state``).
            handler: Executes the tool call when allowed.

        Returns:
            The handler's result, or a synthetic "budget exhausted" ToolMessage
            when the cap is reached.
        """
        tool_call = request.tool_call
        if tool_call.get("name") in _SEARCH_TOOLS:
            cap = get_settings().max_research_searches
            prior = _count_prior_searches(request.state)
            if prior >= cap:
                return ToolMessage(
                    content=(
                        f"Research search budget exhausted after {cap} search(es). "
                        "Stop searching and write /research.md with what you have."
                    ),
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )

        return await handler(request)
