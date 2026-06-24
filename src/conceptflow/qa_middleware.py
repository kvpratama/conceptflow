"""Orchestrator middleware that bounds the QA correction loop.

The QA loop is orchestrator-mediated: the root agent delegates a QA pass to
the ``qa-agent`` subagent, relays blocking findings to ``manim-coder``, and
repeats. Because each delegation spawns a fresh, stateless subagent, the round
budget cannot live in subagent state. Instead this middleware enforces it at
the orchestrator, where the message history is durable and checkpointed: it
counts completed ``task(subagent_type="qa-agent")`` delegations and
short-circuits further ones once ``max_qa_rounds`` is hit.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from conceptflow.config import get_settings

_QA_AGENT = "qa-agent"


def _count_prior_qa_delegations(state: dict[str, Any]) -> int:
    """Count completed ``task`` delegations to the qa-agent subagent.

    Correlates each qa-agent ``task`` tool call with its completion
    ToolMessage so only finished QA rounds are counted.

    Args:
        state: The orchestrator's agent state.

    Returns:
        The number of completed qa-agent QA rounds.
    """
    messages = state.get("messages") or []

    qa_ids: set[str] = set()
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in getattr(m, "tool_calls", []):
                if (
                    isinstance(tc, dict)
                    and tc.get("name") == "task"
                    and tc.get("args", {}).get("subagent_type") == _QA_AGENT
                ):
                    qa_ids.add(tc["id"])

    return sum(
        1
        for m in messages
        if isinstance(m, ToolMessage) and getattr(m, "tool_call_id", None) in qa_ids
    )


class QABudgetMiddleware(AgentMiddleware):
    """Short-circuit qa-agent delegations once the round budget is spent."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Enforce ``max_qa_rounds`` on qa-agent task delegations.

        Args:
            request: The intercepted tool call (with ``tool_call`` and ``state``).
            handler: Executes the tool call when allowed.

        Returns:
            The handler's result, or a synthetic "budget exhausted" ToolMessage
            when the cap is reached.
        """
        tool_call = request.tool_call
        is_qa_task = (
            tool_call.get("name") == "task"
            and tool_call.get("args", {}).get("subagent_type") == _QA_AGENT
        )
        if is_qa_task:
            max_rounds = get_settings().max_qa_rounds
            prior = _count_prior_qa_delegations(request.state)
            if prior >= max_rounds:
                return ToolMessage(
                    content=(
                        f"QA budget exhausted after {max_rounds} round(s). "
                        "Stop reviewing and finalize the current /video.mp4 as-is."
                    ),
                    name="task",
                    tool_call_id=tool_call["id"],
                )

        return await handler(request)
