"""Unit tests for ManimSandboxMiddleware.

The Modal sandbox helpers are mocked, so no real sandbox is created.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from langgraph.runtime import Runtime


async def test_abefore_agent_creates_sandbox_and_sets_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """abefore_agent creates one sandbox and publishes its object id."""
    from conceptflow import sandbox_middleware

    fake_sb = MagicMock()
    fake_sb.object_id = "sb-new"
    monkeypatch.setattr(
        sandbox_middleware, "create_render_sandbox", MagicMock(return_value=fake_sb)
    )

    mw = sandbox_middleware.ManimSandboxMiddleware()
    runtime = cast(Runtime[Any], None)
    update = await mw.abefore_agent({"messages": []}, runtime)

    assert update == {"render_sandbox_id": "sb-new"}


async def test_aafter_agent_terminates_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """aafter_agent terminates and clears a provisioned sandbox."""
    from conceptflow import sandbox_middleware

    terminate = MagicMock()
    monkeypatch.setattr(sandbox_middleware, "terminate_sandbox", terminate)

    mw = sandbox_middleware.ManimSandboxMiddleware()
    runtime = cast(Runtime[Any], None)
    update = await mw.aafter_agent({"messages": [], "render_sandbox_id": "sb-1"}, runtime)

    terminate.assert_called_once_with("sb-1")
    assert update == {"render_sandbox_id": None}


async def test_aafter_agent_noop_when_no_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """aafter_agent is a no-op when no sandbox id is present."""
    from conceptflow import sandbox_middleware

    terminate = MagicMock()
    monkeypatch.setattr(sandbox_middleware, "terminate_sandbox", terminate)

    mw = sandbox_middleware.ManimSandboxMiddleware()
    runtime = cast(Runtime[Any], None)
    update = await mw.aafter_agent({"messages": []}, runtime)

    terminate.assert_not_called()
    assert update is None
