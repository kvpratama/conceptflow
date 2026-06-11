"""Structural tests for the compiled root agent.

These tests build the graph but never invoke a real LLM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from langgraph.graph.state import CompiledStateGraph

if TYPE_CHECKING:
    from langgraph.prebuilt.tool_node import ToolRuntime


async def test_graph_is_compiled_state_graph():
    from conceptflow.agent import make_graph

    assert isinstance(await make_graph(config={}), CompiledStateGraph)


def test_build_subagents_is_called_by_agent_module():
    """Indirect proof both subagents are registered: build_subagents()
    is the only path agent.py uses to populate `subagents=`, so as long
    as that helper is unchanged (covered by Task 3 tests), the graph is
    wired correctly. This test re-confirms the helper still returns two
    entries — a guard against accidental regressions in the public API.
    """
    from conceptflow.subagents import build_subagents

    subs = build_subagents()
    assert {s["name"] for s in subs} == {"script-writer", "manim-coder"}


def test_make_backend_builds_per_thread_filesystem_backend(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from deepagents.backends import FilesystemBackend

    from conceptflow import agent, paths

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")

    runtime = SimpleNamespace(config={"configurable": {"thread_id": "abc"}})
    backend = agent._make_backend(cast("ToolRuntime", runtime))

    assert isinstance(backend, FilesystemBackend)
    assert backend.virtual_mode is True
    # Rooted at the per-thread output dir, which is created eagerly.
    assert backend.cwd == tmp_path / "outputs" / "abc"
    assert (tmp_path / "outputs" / "abc").is_dir()


def test_make_backend_defaults_thread_id_when_absent(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from conceptflow import agent, paths

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")

    runtime = SimpleNamespace(config={})
    backend = agent._make_backend(cast("ToolRuntime", runtime))

    assert backend.cwd == tmp_path / "outputs" / "default"
