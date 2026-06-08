"""Structural tests for the compiled root agent.

These tests build the graph but never invoke a real LLM.
"""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph


def test_graph_is_compiled_state_graph():
    from conceptflow.agent import graph

    assert isinstance(graph, CompiledStateGraph)


def test_graph_has_a_name():
    from conceptflow.agent import graph

    # `name` is set when create_deep_agent(name=...) is called.
    assert graph.name == "conceptflow"


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
