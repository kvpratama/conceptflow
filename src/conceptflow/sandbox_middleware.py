"""Lifecycle middleware for one Modal sandbox per manim-coder subagent run."""

from __future__ import annotations

import asyncio
from typing import Any, NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime

from conceptflow.config import get_settings
from conceptflow.render import create_render_sandbox, terminate_sandbox


class ManimSandboxState(AgentState):
    """Agent state extended with the shared render sandbox object id."""

    render_sandbox_id: NotRequired[str | None]


class ManimSandboxMiddleware(AgentMiddleware[ManimSandboxState]):
    """Provision and tear down one Modal sandbox around a subagent run."""

    state_schema = ManimSandboxState

    async def abefore_agent(
        self, state: ManimSandboxState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """Create the shared render sandbox before the subagent starts.

        Args:
            state: Current agent state. It is unused because each subagent run
                receives a fresh sandbox.
            runtime: LangGraph runtime context. It is unused.

        Returns:
            State update carrying the new sandbox object id.
        """
        settings = get_settings()
        sandbox = await asyncio.to_thread(create_render_sandbox, settings)
        return {"render_sandbox_id": sandbox.object_id}

    async def aafter_agent(
        self, state: ManimSandboxState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """Terminate the shared render sandbox after the subagent finishes.

        Args:
            state: Current agent state containing ``render_sandbox_id`` when a
                sandbox was provisioned.
            runtime: LangGraph runtime context. It is unused.

        Returns:
            State update clearing ``render_sandbox_id``, or ``None`` when no
            sandbox was provisioned.
        """
        sandbox_id = state.get("render_sandbox_id")
        if not sandbox_id:
            return None
        await asyncio.to_thread(terminate_sandbox, sandbox_id)
        return {"render_sandbox_id": None}
