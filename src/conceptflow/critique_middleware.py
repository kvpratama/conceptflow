"""Orchestrator middleware that bounds the visual-critique correction loop.

The visual-critique loop is orchestrator-mediated: the root agent delegates a
critique pass to the ``video-critic`` subagent, relays blocking findings to
``manim-coder``, and repeats. Because each delegation spawns a fresh, stateless
subagent, the round budget cannot live in subagent state. Instead this
middleware enforces it at the orchestrator, where the message history is durable
and checkpointed: it counts completed ``task(subagent_type="video-critic")``
delegations and short-circuits further ones once ``max_critique_rounds`` is hit.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from conceptflow.config import get_settings

_VIDEO_CRITIC = "video-critic"


def _count_prior_critique_delegations(state: dict[str, Any]) -> int:
    """Count completed ``task`` delegations to the video-critic subagent.

    Correlates each video-critic ``task`` tool call with its completion
    ToolMessage so only finished critique rounds are counted.

    Args:
        state: The orchestrator's agent state.

    Returns:
        The number of completed video-critic critique rounds.
    """
    messages = state.get("messages") or []

    critic_ids: set[str] = set()
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in getattr(m, "tool_calls", []):
                if (
                    isinstance(tc, dict)
                    and tc.get("name") == "task"
                    and tc.get("args", {}).get("subagent_type") == _VIDEO_CRITIC
                ):
                    critic_ids.add(tc["id"])

    return sum(
        1
        for m in messages
        if isinstance(m, ToolMessage) and getattr(m, "tool_call_id", None) in critic_ids
    )


class CritiqueBudgetMiddleware(AgentMiddleware):
    """Short-circuit video-critic delegations once the round budget is spent."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Enforce ``max_critique_rounds`` on video-critic task delegations.

        Args:
            request: The intercepted tool call (with ``tool_call`` and ``state``).
            handler: Executes the tool call when allowed.

        Returns:
            The handler's result, or a synthetic "budget exhausted" ToolMessage
            when the cap is reached.
        """
        tool_call = request.tool_call
        is_critic_task = (
            tool_call.get("name") == "task"
            and tool_call.get("args", {}).get("subagent_type") == _VIDEO_CRITIC
        )
        if is_critic_task:
            max_rounds = get_settings().max_critique_rounds
            prior = _count_prior_critique_delegations(request.state)
            if prior >= max_rounds:
                return ToolMessage(
                    content=(
                        f"Critique budget exhausted after {max_rounds} round(s). "
                        "Stop critiquing and finalize the current /video.mp4 as-is."
                    ),
                    name="task",
                    tool_call_id=tool_call["id"],
                )

        return await handler(request)
