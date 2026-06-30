"""Orchestrator middleware that moderates the generated script.

Wraps the ``task`` tool so that whenever the orchestrator delegates to the
``script-writer`` subagent, the resulting ``/script.md`` is moderated before it
can reach ``manim-coder`` and the Modal renderer.

On a first flag the orchestrator is instructed (via a synthetic ToolMessage) to
re-delegate to ``script-writer`` exactly once with the safety feedback. If the
regenerated script is also flagged, the run is hard-stopped before any Modal
sandbox is provisioned.

The hard stop cannot be performed directly from the tool wrapper: the
``tools -> model`` edge in the agent graph always routes back to the model and
ignores any ``goto`` returned from the tool node. Instead, the wrapper records a
``unsafe_script_halt`` flag in state, and a ``before_model`` hook (which *can*
jump to the graph end) terminates the run before the next model call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, NotRequired

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ToolCallRequest,
    hook_config,
)
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.config import get_config
from langgraph.runtime import Runtime
from langgraph.types import Command

from conceptflow.moderation import moderate
from conceptflow.paths import out_dir_from_config

_SCRIPT_WRITER = "script-writer"

_HALT_MESSAGE = (
    "The script could not be made safe after one regeneration and was blocked "
    "by ConceptFlow's content-safety policy. Halting; no video was rendered."
)


class OutputModerationState(AgentState):
    """Agent state extended with the unsafe-script halt flag."""

    unsafe_script_halt: NotRequired[bool]


def _is_script_writer_task(tool_call: Mapping[str, Any]) -> bool:
    """Return True when the tool call delegates to the script-writer subagent.

    Args:
        tool_call: The intercepted tool call dict.

    Returns:
        True for ``task(subagent_type="script-writer")`` calls, else False.
    """
    return (
        tool_call.get("name") == "task"
        and tool_call.get("args", {}).get("subagent_type") == _SCRIPT_WRITER
    )


def _count_prior_script_delegations(state: Mapping[str, Any]) -> int:
    """Count completed ``task`` delegations to the script-writer subagent.

    Correlates each script-writer ``task`` tool call with its completion
    ToolMessage so only finished delegations are counted.

    Args:
        state: The orchestrator's agent state.

    Returns:
        The number of completed script-writer delegations in the history.
    """
    messages = state.get("messages") or []

    script_ids: set[str] = set()
    for message in messages:
        if isinstance(message, AIMessage):
            for tool_call in getattr(message, "tool_calls", []):
                if isinstance(tool_call, dict) and _is_script_writer_task(tool_call):
                    script_ids.add(tool_call["id"])

    return sum(
        1
        for message in messages
        if isinstance(message, ToolMessage) and getattr(message, "tool_call_id", None) in script_ids
    )


async def _load_script_text() -> str | None:
    """Read ``/script.md`` from the per-thread output directory.

    Resolves the output directory from the active LangGraph run config, mirroring
    how the render tool locates ``scene.py`` on disk.

    Returns:
        The script text, or ``None`` when the file does not exist.
    """
    out_dir = out_dir_from_config(get_config())
    script_path = out_dir / "script.md"

    def _read() -> str | None:
        try:
            return script_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    return await asyncio.to_thread(_read)


class OutputModerationMiddleware(AgentMiddleware[OutputModerationState]):
    """Moderate the generated /script.md after each script-writer delegation."""

    state_schema = OutputModerationState

    @hook_config(can_jump_to=["end"])
    async def abefore_model(
        self, state: OutputModerationState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """Halt the run before the next model call when a script was unsafe.

        Args:
            state: The orchestrator's agent state.
            runtime: LangGraph runtime context. Unused.

        Returns:
            ``None`` normally, or a state update jumping to the graph end with a
            halt message when ``unsafe_script_halt`` was set by the tool wrapper.
        """
        if state.get("unsafe_script_halt"):
            return {"jump_to": "end", "messages": [AIMessage(content=_HALT_MESSAGE)]}
        return None

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Moderate ``/script.md`` after a script-writer delegation completes.

        Args:
            request: The intercepted tool call (with ``tool_call`` and ``state``).
            handler: Executes the underlying tool call.

        Returns:
            The handler's result when the call is not a script-writer delegation
            or the script is allowed; a synthetic ToolMessage instructing one
            regeneration on a first flag; or a :class:`Command` that sets the
            halt flag when the regenerated script is still flagged.
        """
        tool_call = request.tool_call
        if not _is_script_writer_task(tool_call):
            return await handler(request)

        result = await handler(request)

        script = await _load_script_text()
        if script is None:
            return result

        verdict = await moderate(script, kind="output")
        if verdict.allowed:
            return result

        detail = f" Reason: {verdict.reason}" if verdict.reason else ""
        prior = _count_prior_script_delegations(request.state)
        if prior >= 1:
            # Already regenerated once and still unsafe: flag for hard stop. The
            # before_model hook ends the run before manim-coder/render can run.
            return Command(
                update={
                    "unsafe_script_halt": True,
                    "messages": [
                        ToolMessage(
                            content=(
                                "The regenerated script was flagged again by the "
                                f"content-safety policy.{detail} Halting; no video "
                                "will be rendered."
                            ),
                            name="task",
                            tool_call_id=tool_call["id"],
                        )
                    ],
                },
            )

        # First flag: instruct exactly one regeneration with the safety feedback.
        return ToolMessage(
            content=(
                "The generated /script.md was flagged by the content-safety "
                f"policy.{detail} Delegate to script-writer once more, instructing "
                "it to produce a safe, educational script that avoids the flagged "
                "content. Do not render until the script passes."
            ),
            name="task",
            tool_call_id=tool_call["id"],
        )
