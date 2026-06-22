"""Unit tests for CritiqueBudgetMiddleware (orchestrator round budget)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from conceptflow.critique_middleware import CritiqueBudgetMiddleware


def _critic_delegation(call_id: str) -> tuple[AIMessage, ToolMessage]:
    """An AIMessage delegating to video-critic + its completion ToolMessage."""
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "args": {"subagent_type": "video-critic", "description": "review scenes"},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )
    done = ToolMessage(content="reviewed", name="task", tool_call_id=call_id)
    return ai, done


def _new_critic_request(messages: list) -> SimpleNamespace:
    """A request object representing a NEW video-critic task call."""
    return SimpleNamespace(
        tool_call={
            "name": "task",
            "args": {"subagent_type": "video-critic", "description": "review"},
            "id": "new-call",
        },
        state={"messages": messages},
    )


async def test_passes_through_when_under_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow import critique_middleware

    monkeypatch.setattr(
        critique_middleware, "get_settings", lambda: SimpleNamespace(max_critique_rounds=2)
    )
    mw = CritiqueBudgetMiddleware()
    handler = AsyncMock(
        return_value=ToolMessage(content="ran", name="task", tool_call_id="new-call")
    )

    ai1, done1 = _critic_delegation("c1")  # 1 prior completed round
    result = await mw.awrap_tool_call(cast(Any, _new_critic_request([ai1, done1])), handler)

    handler.assert_awaited_once()
    assert result.content == "ran"


async def test_short_circuits_at_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow import critique_middleware

    monkeypatch.setattr(
        critique_middleware, "get_settings", lambda: SimpleNamespace(max_critique_rounds=2)
    )
    mw = CritiqueBudgetMiddleware()
    handler = AsyncMock()

    ai1, done1 = _critic_delegation("c1")
    ai2, done2 = _critic_delegation("c2")  # 2 prior completed rounds == cap
    result = await mw.awrap_tool_call(
        cast(Any, _new_critic_request([ai1, done1, ai2, done2])), handler
    )

    handler.assert_not_awaited()
    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "new-call"
    assert isinstance(result.content, str)
    assert "budget exhausted" in result.content.lower()


async def test_ignores_non_critic_task_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow import critique_middleware

    monkeypatch.setattr(
        critique_middleware, "get_settings", lambda: SimpleNamespace(max_critique_rounds=1)
    )
    mw = CritiqueBudgetMiddleware()
    handler = AsyncMock(return_value=ToolMessage(content="ran", name="task", tool_call_id="x"))

    request = SimpleNamespace(
        tool_call={
            "name": "task",
            "args": {"subagent_type": "manim-coder", "description": "fix"},
            "id": "x",
        },
        state={"messages": []},
    )
    await mw.awrap_tool_call(cast(Any, request), handler)
    handler.assert_awaited_once()


async def test_ignores_non_task_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow import critique_middleware

    monkeypatch.setattr(
        critique_middleware, "get_settings", lambda: SimpleNamespace(max_critique_rounds=0)
    )
    mw = CritiqueBudgetMiddleware()
    handler = AsyncMock(
        return_value=ToolMessage(content="ran", name="write_file", tool_call_id="w")
    )

    request = SimpleNamespace(
        tool_call={"name": "write_file", "args": {}, "id": "w"},
        state={"messages": []},
    )
    await mw.awrap_tool_call(cast(Any, request), handler)
    handler.assert_awaited_once()
