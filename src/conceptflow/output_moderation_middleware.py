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
import logging
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, NotRequired

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ToolCallRequest,
    hook_config,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.config import get_config
from langgraph.runtime import Runtime
from langgraph.types import Command

from conceptflow.moderation import MODERATION_ERROR_CATEGORY, moderate
from conceptflow.paths import out_dir_from_config

_logger = logging.getLogger(__name__)

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
    """Count completed script-writer delegations in the current user turn.

    Correlates each script-writer ``task`` tool call with its completion
    ToolMessage so only finished delegations are counted, and scopes the walk to
    the current turn (messages after the last :class:`HumanMessage`) so the
    per-turn regeneration budget is not leaked across turns in a multi-turn
    thread.

    Args:
        state: The orchestrator's agent state.

    Returns:
        The number of completed script-writer delegations in the current turn.
    """
    messages = state.get("messages") or []

    # Scope to the current user turn: only messages after the last HumanMessage.
    last_human = max(
        (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)),
        default=-1,
    )
    messages = messages[last_human + 1 :]

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


def _script_path() -> Path:
    """Resolve the on-disk ``/script.md`` path for the active run.

    Resolves the per-thread output directory from the active LangGraph run
    config, mirroring how the render tool locates ``scene.py`` on disk.

    Returns:
        The absolute path to ``script.md`` in the run's output directory.
    """
    return out_dir_from_config(get_config()) / "script.md"


async def _load_script_text() -> str | None:
    """Read ``/script.md`` from the per-thread output directory.

    Returns:
        The script text, or ``None`` when the file does not exist.
    """
    script_path = _script_path()

    def _read() -> str | None:
        try:
            return script_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    return await asyncio.to_thread(_read)


async def _delete_script() -> None:
    """Remove the on-disk ``/script.md`` so a regeneration can write a fresh file.

    ``FilesystemBackend.write`` (backing the ``write_file`` tool) refuses to
    overwrite an existing file, so the flagged script must be deleted before
    ``script-writer`` is re-delegated; otherwise the regeneration's write fails
    and moderation re-reads the same flagged content. Missing files are ignored.
    """
    script_path = _script_path()

    def _unlink() -> None:
        script_path.unlink(missing_ok=True)

    await asyncio.to_thread(_unlink)


def _halt(tool_call_id: str | None, *, content: str) -> Command[Any]:
    """Build a hard-stop Command that flags the run for termination.

    Sets ``unsafe_script_halt`` so the ``before_model`` hook ends the run before
    any further model call, and records a completion ToolMessage for the
    intercepted ``task`` call.

    Args:
        tool_call_id: The intercepted ``task`` tool call id to complete.
        content: The ToolMessage body explaining the halt.

    Returns:
        A :class:`Command` state update carrying the halt flag and message.
    """
    return Command(
        update={
            "unsafe_script_halt": True,
            "messages": [ToolMessage(content=content, name="task", tool_call_id=tool_call_id)],
        },
    )


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
            # A script-writer delegation is contractually required to produce
            # /script.md. Its absence means moderation cannot run, so fail closed
            # and hard-stop rather than letting the pipeline proceed unmoderated.
            _logger.error("script-writer delegation produced no /script.md; failing closed.")
            return _halt(
                tool_call["id"],
                content=(
                    "The script-writer delegation did not produce a script, so "
                    "content moderation could not run. Halting; no video will be rendered."
                ),
            )

        verdict = await moderate(script, kind="output")
        if verdict.allowed:
            return result

        detail = f" Reason: {verdict.reason}" if verdict.reason else ""

        if MODERATION_ERROR_CATEGORY in verdict.categories:
            # The judge itself failed (fail-closed). Regenerating the script
            # cannot fix a broken judge and would send misleading "flagged"
            # feedback to script-writer, so hard-stop immediately regardless of
            # the regeneration budget.
            return _halt(
                tool_call["id"],
                content=(
                    "Content moderation could not be completed and failed closed."
                    f"{detail} Halting; no video will be rendered."
                ),
            )

        prior = _count_prior_script_delegations(request.state)
        if prior >= 1:
            # Already regenerated once and still unsafe: flag for hard stop. The
            # before_model hook ends the run before manim-coder/render can run.
            return _halt(
                tool_call["id"],
                content=(
                    "The regenerated script was flagged again by the "
                    f"content-safety policy.{detail} Halting; no video "
                    "will be rendered."
                ),
            )

        # First flag: delete the flagged script so the re-delegated
        # script-writer can write a fresh /script.md (the write_file tool
        # refuses to overwrite an existing file), then instruct exactly one
        # regeneration with the safety feedback.
        await _delete_script()
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
