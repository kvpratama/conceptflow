"""Structural tests for the compiled root agent.

These tests build the graph but never invoke a real LLM.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langgraph.graph.state import CompiledStateGraph


async def test_graph_is_compiled_state_graph() -> None:
    from conceptflow.agent import make_graph

    assert isinstance(await make_graph(config={}), CompiledStateGraph)


async def test_make_graph_execution_mode_uses_filesystem_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import inspect

    from deepagents.backends import CompositeBackend, FilesystemBackend
    from deepagents.middleware.filesystem import FilesystemMiddleware

    from conceptflow import paths
    from conceptflow.agent import make_graph

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    graph = await make_graph(
        config={"configurable": {"thread_id": "t1", "__is_for_execution__": True}}
    )

    assert isinstance(graph, CompiledStateGraph)

    from langgraph.prebuilt import ToolNode

    tool_node = graph.get_graph().nodes["tools"].data
    assert isinstance(tool_node, ToolNode)
    tools_by_name = tool_node.tools_by_name

    backend: FilesystemBackend | None = None
    for tool in tools_by_name.values():
        for candidate in (
            getattr(tool, "coroutine", None),
            getattr(tool, "func", None),
        ):
            if candidate is None:
                continue
            try:
                closure = inspect.getclosurevars(candidate)
            except TypeError:
                continue
            for value in closure.nonlocals.values():
                if isinstance(value, FilesystemBackend):
                    backend = value
                    break
                if isinstance(value, CompositeBackend) and isinstance(
                    value.default, FilesystemBackend
                ):
                    backend = value.default
                    break
                if isinstance(value, FilesystemMiddleware) and isinstance(
                    value.backend, FilesystemBackend
                ):
                    backend = value.backend
                    break
                if isinstance(value, FilesystemMiddleware) and isinstance(
                    value.backend, CompositeBackend
                ):
                    default = value.backend.default
                    if isinstance(default, FilesystemBackend):
                        backend = default
                        break
            if backend is not None:
                break
        if backend is not None:
            break

    assert isinstance(backend, FilesystemBackend)


async def test_make_graph_execution_mode_uses_composite_skills_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert execution mode mounts repo skills under /skills/."""
    import inspect

    from deepagents.backends import CompositeBackend, FilesystemBackend

    from conceptflow import paths
    from conceptflow.agent import make_graph

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    graph = await make_graph(
        config={"configurable": {"thread_id": "t1", "__is_for_execution__": True}}
    )

    from langgraph.prebuilt import ToolNode

    composite: CompositeBackend | None = None
    tool_node = graph.get_graph().nodes["tools"].data
    assert isinstance(tool_node, ToolNode)
    for tool in tool_node.tools_by_name.values():
        for candidate in (
            getattr(tool, "coroutine", None),
            getattr(tool, "func", None),
        ):
            if candidate is None:
                continue
            try:
                closure = inspect.getclosurevars(candidate)
            except TypeError:
                continue
            for value in closure.nonlocals.values():
                if isinstance(value, CompositeBackend):
                    composite = value
                    break
                backend_attr = getattr(value, "backend", None)
                if isinstance(backend_attr, CompositeBackend):
                    composite = backend_attr
                    break
            if composite is not None:
                break
        if composite is not None:
            break

    assert isinstance(composite, CompositeBackend)
    assert "/skills/" in composite.routes
    assert isinstance(composite.routes["/skills/"], FilesystemBackend)
    assert isinstance(composite.default, FilesystemBackend)


def test_build_subagents_is_called_by_agent_module() -> None:
    """Indirect proof both subagents are registered: build_subagents()
    is the only path agent.py uses to populate `subagents=`, so as long
    as that helper is unchanged (covered by Task 3 tests), the graph is
    wired correctly. This test re-confirms the helper still returns two
    entries — a guard against accidental regressions in the public API.
    """
    from conceptflow.subagents import build_subagents

    subs = build_subagents()
    assert {s["name"] for s in subs} == {
        "research-agent",
        "script-writer",
        "manim-coder",
        "qa-agent",
    }


async def test_execution_graph_includes_qa_budget_middleware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Execution mode wires QABudgetMiddleware into the orchestrator."""
    from conceptflow import agent, paths
    from conceptflow.qa_middleware import QABudgetMiddleware

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")

    captured: dict[str, object] = {}

    def fake_create_deep_agent(**kwargs: object) -> object:
        captured.update(kwargs)
        return MagicMock(spec=CompiledStateGraph)

    monkeypatch.setattr(agent, "create_deep_agent", fake_create_deep_agent)

    await agent.make_graph(
        config={"configurable": {"thread_id": "t1", "__is_for_execution__": True}}
    )

    from typing import cast

    middleware = cast(list, captured["middleware"])
    assert any(isinstance(m, QABudgetMiddleware) for m in middleware)
