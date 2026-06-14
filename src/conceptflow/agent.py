"""Root ConceptFlow deep agent, exported as `make_graph` for LangGraph Studio.

`langgraph dev` loads this module via `langgraph.json` and calls the
`make_graph` function to build the graph on-demand. The function inspects
the runnable config to decide whether to return a full execution graph or a
lightweight schema-only graph for Studio introspection.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from conceptflow.config import get_model, get_model_small, get_settings, load_environment
from conceptflow.paths import out_dir_from_config, skills_dir
from conceptflow.prompts import ORCHESTRATOR_PROMPT
from conceptflow.subagents import build_subagents

if TYPE_CHECKING:
    pass

# Populate os.environ before init_chat_model reads provider keys.
load_environment()

_settings = get_settings()
_model = get_model(_settings)


async def make_graph(config: RunnableConfig) -> CompiledStateGraph:
    """Build the ConceptFlow root deep agent graph for the given config.

    Inspects the runnable config to decide whether the call is a real
    execution or a schema-inspection-only call from LangGraph Studio. When
    ``__is_for_execution__`` is set, a full graph is built with a
    ``FilesystemBackend`` rooted at the configured output directory plus retry
    and model-fallback middleware. Otherwise a lightweight schema-only graph is
    returned (fail-closed) to avoid provisioning a real Modal sandbox.

    Args:
        config: The LangGraph runnable config. The ``configurable`` mapping may
            contain ``__is_for_execution__`` to opt in to a full execution
            graph.

    Returns:
        A compiled LangGraph state graph for the ConceptFlow root deep agent.
    """
    configurable = dict(config.get("configurable", {}))
    # Default to False (fail-closed): only provision a real Modal sandbox when
    # the caller explicitly signals this is an execution. Schema/read calls
    # from LangGraph Studio (assistants.read, threads.read, threads.update)
    # fall through to the cached no-op SchemaOnlySandboxBackend graph.
    is_execution = bool(configurable.get("__is_for_execution__", False))
    if is_execution:
        out_dir = out_dir_from_config(config)
        await asyncio.to_thread(out_dir.mkdir, parents=True, exist_ok=True)

        base_middleware: list[AgentMiddleware] = [
            ModelRetryMiddleware(
                max_retries=_settings.retry_max_retries,
                backoff_factor=_settings.retry_backoff_factor,
                initial_delay=_settings.retry_initial_delay,
            ),
            ModelFallbackMiddleware(get_model_small(_settings)),
        ]

        # FilesystemBackend.__init__ resolves root_dir, which makes blocking
        # os.getcwd/realpath calls; build both backends off the event loop.
        workspace_backend = await asyncio.to_thread(
            FilesystemBackend, root_dir=str(out_dir), virtual_mode=True
        )
        skills_backend = await asyncio.to_thread(
            FilesystemBackend, root_dir=str(skills_dir()), virtual_mode=True
        )
        # CompositeBackend strips the route prefix before delegating, so the
        # skills backend is rooted at the directory containing agent namespaces.
        backend = CompositeBackend(
            default=workspace_backend,
            routes={"/skills/": skills_backend},
        )

        # Compiled LangGraph for the ConceptFlow root deep agent.
        return create_deep_agent(
            model=_model,
            system_prompt=ORCHESTRATOR_PROMPT,
            middleware=base_middleware,
            subagents=build_subagents(),
            backend=backend,
            skills=["/skills/orchestrator/"],
            name="conceptflow",
        )

    # SchemaOnlySandboxBackend graph for Studio's schema-inspection-only calls.
    return create_deep_agent(
        model=_model,
        subagents=build_subagents(),
        name="conceptflow",
    )
