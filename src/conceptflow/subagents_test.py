"""Structural tests for SubAgent configurations."""

from __future__ import annotations

from conceptflow import prompts
from conceptflow.subagents import build_subagents


def test_build_subagents_returns_two_entries():
    subs = build_subagents()
    assert len(subs) == 2
    names = {s["name"] for s in subs}
    assert names == {"script-writer", "manim-coder"}


def test_script_writer_uses_correct_prompt_and_no_extra_tools():
    subs = {s["name"]: s for s in build_subagents()}
    sw = subs["script-writer"]
    assert sw["system_prompt"] == prompts.SCRIPT_WRITER_PROMPT
    assert isinstance(sw["description"], str)
    assert sw["description"].strip()
    # script-writer relies only on the built-in toolset — no custom tools.
    assert "tools" not in sw or sw["tools"] == []


def test_manim_coder_includes_render_manim_tool():
    from langchain_core.tools import BaseTool

    from conceptflow.render import render_manim

    subs = {s["name"]: s for s in build_subagents()}
    mc = subs["manim-coder"]
    assert mc["system_prompt"] == prompts.MANIM_CODER_PROMPT
    assert "tools" in mc
    tools = list(mc["tools"])
    tool_names = {t.name for t in tools if isinstance(t, BaseTool)}
    assert "render_manim" in tool_names
    # And exactly one custom tool.
    assert len(tools) == 1
    assert tools[0] is render_manim


def test_subagents_declare_namespace_scoped_skills() -> None:
    """Assert each subagent only sees its own skill namespace."""
    subs = {s["name"]: s for s in build_subagents()}

    assert subs["script-writer"]["skills"] == ["/skills/script-writer/"]
    assert subs["manim-coder"]["skills"] == ["/skills/manim-coder/"]

    for name, spec in subs.items():
        for source in spec["skills"]:
            assert source == f"/skills/{name}/"
