"""Orchestrator middleware that moderates the user's input topic.

Runs once before the agent starts (``abefore_agent``). If the latest human
message fails the content-safety rubric, the graph short-circuits to the end
with a brief refusal and no research, scripting, or rendering work begins.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from conceptflow.moderation import moderate

_REFUSAL = (
    "I can't help with this request. The topic was flagged by ConceptFlow's "
    "content-safety policy, so no video was generated.{detail}"
)


def _latest_human_text(state: AgentState) -> str | None:
    """Return the text of the most recent human message, if any.

    Args:
        state: The orchestrator's agent state.

    Returns:
        The latest human message's text content, or ``None`` when there is no
        human message or its content is not plain text.
    """
    messages = state.get("messages") or []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    part["text"]
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                ]
                return "\n".join(parts) if parts else None
            return None
    return None


class InputModerationMiddleware(AgentMiddleware):
    """Reject harmful user topics before any pipeline work starts."""

    @hook_config(can_jump_to=["end"])
    async def abefore_agent(
        self, state: AgentState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """Moderate the user topic and short-circuit to end when flagged.

        Args:
            state: The orchestrator's agent state.
            runtime: LangGraph runtime context. Unused.

        Returns:
            ``None`` when the topic is allowed (the agent proceeds normally), or
            a state update jumping to the graph end with a refusal message when
            the topic is flagged.
        """
        text = _latest_human_text(state)
        if not text:
            return None
        verdict = await moderate(text, kind="input")
        if verdict.allowed:
            return None
        detail = f" Reason: {verdict.reason}" if verdict.reason else ""
        return {
            "jump_to": "end",
            "messages": [AIMessage(content=_REFUSAL.format(detail=detail))],
        }
