"""Smoke tests for the prompts module."""

from conceptflow import prompts


def test_orchestrator_prompt_is_non_empty_string():
    assert isinstance(prompts.ORCHESTRATOR_PROMPT, str)
    assert len(prompts.ORCHESTRATOR_PROMPT) > 100


def test_script_writer_prompt_is_non_empty_string():
    assert isinstance(prompts.SCRIPT_WRITER_PROMPT, str)
    assert len(prompts.SCRIPT_WRITER_PROMPT) > 100


def test_manim_coder_prompt_mentions_render_tool_and_retry_cap():
    assert "render_manim" in prompts.MANIM_CODER_PROMPT
    assert "3" in prompts.MANIM_CODER_PROMPT  # retry cap documented
    assert "/scene.py" in prompts.MANIM_CODER_PROMPT


def test_script_writer_prompt_writes_script_md():
    assert "/script.md" in prompts.SCRIPT_WRITER_PROMPT
