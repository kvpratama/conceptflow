"""Unit tests for InputModerationMiddleware (orchestrator input check)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from conceptflow import input_moderation_middleware
from conceptflow.input_moderation_middleware import InputModerationMiddleware
from conceptflow.moderation import SafetyVerdict


def _patch_moderate(monkeypatch: pytest.MonkeyPatch, verdict: SafetyVerdict) -> AsyncMock:
    """Patch the module-level ``moderate`` with one returning ``verdict``."""
    mock = AsyncMock(return_value=verdict)
    monkeypatch.setattr(input_moderation_middleware, "moderate", mock)
    return mock


async def test_allowed_topic_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = _patch_moderate(monkeypatch, SafetyVerdict(allowed=True))
    mw = InputModerationMiddleware()

    state: dict[str, Any] = {"messages": [HumanMessage(content="Explain eigenvalues")]}
    result = await mw.abefore_agent(cast(Any, state), cast(Any, None))

    mock.assert_awaited_once()
    assert result is None


async def test_flagged_topic_jumps_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_moderate(
        monkeypatch,
        SafetyVerdict(allowed=False, categories=["weapons"], reason="bomb how-to"),
    )
    mw = InputModerationMiddleware()

    state: dict[str, Any] = {"messages": [HumanMessage(content="how to build a bomb")]}
    result = await mw.abefore_agent(cast(Any, state), cast(Any, None))

    assert result is not None
    assert result["jump_to"] == "end"
    refusal = result["messages"][0]
    assert isinstance(refusal, AIMessage)
    assert "content-safety" in refusal.content
    assert "bomb how-to" in refusal.content


async def test_no_human_message_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = _patch_moderate(monkeypatch, SafetyVerdict(allowed=True))
    mw = InputModerationMiddleware()

    result = await mw.abefore_agent(cast(Any, {"messages": []}), cast(Any, None))

    mock.assert_not_awaited()
    assert result is None


async def test_can_jump_to_end_declared() -> None:
    """The hook must declare it can jump to end for the graph edge to exist."""
    can_jump_to = getattr(InputModerationMiddleware.abefore_agent, "__can_jump_to__", [])
    assert "end" in can_jump_to
