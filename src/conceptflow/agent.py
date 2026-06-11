"""Root ConceptFlow deep agent, exported as `graph` for LangGraph Studio.

`langgraph dev` loads this module via `langgraph.json` and discovers the
module-level `graph` attribute below. The graph is compiled at import
time so Studio can introspect it without invoking the model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
)

from conceptflow.config import get_model, get_model_small, get_settings, load_environment
from conceptflow.paths import out_dir_from_config
from conceptflow.prompts import ORCHESTRATOR_PROMPT
from conceptflow.subagents import build_subagents

if TYPE_CHECKING:
    from langgraph.prebuilt.tool_node import ToolRuntime

# Populate os.environ before init_chat_model reads provider keys.
load_environment()

_settings = get_settings()
_model = get_model(_settings)


def _make_backend(runtime: ToolRuntime) -> FilesystemBackend:
    """Build a per-thread FilesystemBackend rooted at the run's output dir.

    The per-run directory depends on ``thread_id`` (known only at runtime), so
    the backend is created lazily per invocation. Every artifact a run
    produces — ``script.md`` (script-writer), ``scene.py`` (manim-coder), and
    ``video.mp4`` (render_manim) — lands together in ``./outputs/<thread_id>/``
    on disk so a human can review the full output of a run.

    Args:
        runtime: The tool runtime, whose ``config`` carries the run's
            ``thread_id`` under ``configurable``.

    Returns:
        A ``FilesystemBackend`` with ``virtual_mode=True`` rooted at the
        per-thread output directory.
    """
    out_dir = out_dir_from_config(runtime.config)
    out_dir.mkdir(parents=True, exist_ok=True)
    return FilesystemBackend(root_dir=str(out_dir), virtual_mode=True)


base_middleware: list[AgentMiddleware] = [
    ModelRetryMiddleware(
        max_retries=_settings.retry_max_retries,
        backoff_factor=_settings.retry_backoff_factor,
        initial_delay=_settings.retry_initial_delay,
    ),
    ModelFallbackMiddleware(get_model_small(_settings)),
]

graph = create_deep_agent(
    model=_model,
    tools=[],
    system_prompt=ORCHESTRATOR_PROMPT,
    middleware=base_middleware,
    subagents=build_subagents(),
    backend=_make_backend,
    name="conceptflow",
)
"""Compiled LangGraph for the ConceptFlow root deep agent."""
