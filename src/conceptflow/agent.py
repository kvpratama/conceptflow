"""Root ConceptFlow deep agent, exported as `graph` for LangGraph Studio.

`langgraph dev` loads this module via `langgraph.json` and discovers the
module-level `graph` attribute below. The graph is compiled at import
time so Studio can introspect it without invoking the model.
"""

from __future__ import annotations

from deepagents import create_deep_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
)

from conceptflow.config import get_model, get_model_small, get_settings, load_environment
from conceptflow.prompts import ORCHESTRATOR_PROMPT
from conceptflow.subagents import build_subagents

# Populate os.environ before init_chat_model reads provider keys.
load_environment()

_settings = get_settings()
_model = get_model(_settings)

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
    name="conceptflow",
)
"""Compiled LangGraph for the ConceptFlow root deep agent."""
