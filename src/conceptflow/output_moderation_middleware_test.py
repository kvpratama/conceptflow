"""Unit tests for OutputModerationMiddleware (generated-script check)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from conceptflow import output_moderation_middleware
from conceptflow.moderation import SafetyVerdict
from conceptflow.output_moderation_middleware import OutputModerationMiddleware


def _script_delegation(call_id: str) -> tuple[AIMessage, ToolMessage]:
    """An AIMessage delegating to script-writer + its completion ToolMessage."""
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "args": {"subagent_type": "script-writer", "description": "write script"},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )
    done = ToolMessage(content="/script.md written", name="task", tool_call_id=call_id)
    return ai, done


def _new_script_request(messages: list[Any]) -> SimpleNamespace:
    """A request object representing a NEW script-writer task call."""
    return SimpleNamespace(
        tool_call={
            "name": "task",
            "args": {"subagent_type": "script-writer", "description": "write script"},
            "id": "new-call",
        },
        state={"messages": messages},
    )


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    script: str | None,
    verdict: SafetyVerdict,
) -> AsyncMock:
    """Patch script loading + moderation; return the moderate mock."""
    monkeypatch.setattr(
        output_moderation_middleware,
        "_load_script_text",
        AsyncMock(return_value=script),
    )
    moderate_mock = AsyncMock(return_value=verdict)
    monkeypatch.setattr(output_moderation_middleware, "moderate", moderate_mock)
    return moderate_mock


async def test_allowed_script_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, script="safe script", verdict=SafetyVerdict(allowed=True))
    mw = OutputModerationMiddleware()
    handler = AsyncMock(
        return_value=ToolMessage(content="ran", name="task", tool_call_id="new-call")
    )

    result = await mw.awrap_tool_call(cast(Any, _new_script_request([])), handler)

    handler.assert_awaited_once()
    assert isinstance(result, ToolMessage)
    assert result.content == "ran"


async def test_first_flag_requests_regeneration(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        script="unsafe script",
        verdict=SafetyVerdict(allowed=False, categories=["weapons"], reason="bomb how-to"),
    )
    mw = OutputModerationMiddleware()
    handler = AsyncMock(
        return_value=ToolMessage(content="ran", name="task", tool_call_id="new-call")
    )

    # No prior completed script-writer delegations.
    result = await mw.awrap_tool_call(cast(Any, _new_script_request([])), handler)

    handler.assert_awaited_once()
    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "new-call"
    assert "once more" in result.content
    assert "bomb how-to" in result.content


async def test_second_flag_hard_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        script="still unsafe",
        verdict=SafetyVerdict(allowed=False, categories=["weapons"], reason="bomb how-to"),
    )
    mw = OutputModerationMiddleware()
    handler = AsyncMock(
        return_value=ToolMessage(content="ran", name="task", tool_call_id="new-call")
    )

    ai1, done1 = _script_delegation("c1")  # one prior completed delegation
    result = await mw.awrap_tool_call(cast(Any, _new_script_request([ai1, done1])), handler)

    assert isinstance(result, Command)
    update = cast(dict[str, Any], result.update)
    assert update["unsafe_script_halt"] is True
    msg = update["messages"][0]
    assert isinstance(msg, ToolMessage)
    assert msg.tool_call_id == "new-call"
    assert "Halting" in msg.content


async def test_before_model_halts_when_flagged() -> None:
    """The before_model hook jumps to end once the halt flag is set."""
    mw = OutputModerationMiddleware()

    result = await mw.abefore_model(cast(Any, {"unsafe_script_halt": True}), cast(Any, None))

    assert result is not None
    assert result["jump_to"] == "end"
    assert isinstance(result["messages"][0], AIMessage)


async def test_before_model_noop_without_flag() -> None:
    """The before_model hook is a no-op on the normal path."""
    mw = OutputModerationMiddleware()

    result = await mw.abefore_model(cast(Any, {"messages": []}), cast(Any, None))

    assert result is None


async def test_before_model_can_jump_to_end_declared() -> None:
    """The before_model hook must declare it can jump to end."""
    can_jump_to = getattr(OutputModerationMiddleware.abefore_model, "__can_jump_to__", [])
    assert "end" in can_jump_to


async def test_missing_script_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    moderate_mock = _patch(monkeypatch, script=None, verdict=SafetyVerdict(allowed=True))
    mw = OutputModerationMiddleware()
    handler = AsyncMock(
        return_value=ToolMessage(content="ran", name="task", tool_call_id="new-call")
    )

    result = await mw.awrap_tool_call(cast(Any, _new_script_request([])), handler)

    moderate_mock.assert_not_awaited()
    assert isinstance(result, ToolMessage)
    assert result.content == "ran"


async def test_non_script_writer_task_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    load_mock = AsyncMock(return_value="x")
    monkeypatch.setattr(output_moderation_middleware, "_load_script_text", load_mock)
    mw = OutputModerationMiddleware()
    handler = AsyncMock(return_value=ToolMessage(content="ran", name="task", tool_call_id="x"))

    request = SimpleNamespace(
        tool_call={
            "name": "task",
            "args": {"subagent_type": "research-agent", "description": "research"},
            "id": "x",
        },
        state={"messages": []},
    )
    result = await mw.awrap_tool_call(cast(Any, request), handler)

    handler.assert_awaited_once()
    load_mock.assert_not_awaited()
    assert isinstance(result, ToolMessage)
    assert result.content == "ran"
