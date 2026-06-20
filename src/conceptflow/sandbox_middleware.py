"""Lifecycle middleware for one Modal sandbox per manim-coder subagent run."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, NotRequired, cast

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
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
        await self._aterminate_state_sandbox(state)
        return {"render_sandbox_id": None}

    async def _aterminate_state_sandbox(self, state: ManimSandboxState) -> None:
        """Best-effort terminate the sandbox recorded in agent state.

        Args:
            state: Agent state that may contain ``render_sandbox_id``.
        """
        sandbox_id = state.get("render_sandbox_id")
        if sandbox_id:
            await asyncio.to_thread(terminate_sandbox, sandbox_id)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        """Terminate the render sandbox if an unhandled model error aborts the agent.

        LangChain wires ``aafter_agent`` as a normal exit node rather than a
        ``finally`` hook, so an unhandled model-call exception aborts the
        subagent graph and skips ``aafter_agent``, leaking the sandbox until its
        Modal timeout. This performs best-effort cleanup on that failure path and
        re-raises the original exception so the failure is not masked.

        Args:
            request: Model call request whose ``state`` carries
                ``render_sandbox_id``.
            handler: Async callable that executes the underlying model call.

        Returns:
            The model response produced by ``handler`` on the success path.
        """
        try:
            return await handler(request)
        except Exception:
            await self._aterminate_state_sandbox(cast(ManimSandboxState, request.state))
            raise
