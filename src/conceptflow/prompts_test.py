"""Smoke tests for the prompts module."""

from conceptflow import prompts


def test_orchestrator_prompt_is_non_empty_string():
    assert isinstance(prompts.ORCHESTRATOR_PROMPT, str)
    assert len(prompts.ORCHESTRATOR_PROMPT) > 100


def test_script_writer_prompt_is_non_empty_string():
    assert isinstance(prompts.SCRIPT_WRITER_PROMPT, str)
    assert len(prompts.SCRIPT_WRITER_PROMPT) > 100


def test_manim_coder_prompt_mentions_render_and_stitch_tools():
    assert "render_manim" in prompts.MANIM_CODER_PROMPT
    # Multi-scene workflow: scenes are rendered then stitched into /video.mp4.
    assert "stitch_videos" in prompts.MANIM_CODER_PROMPT
    assert "/video.mp4" in prompts.MANIM_CODER_PROMPT
    assert "/scene.py" in prompts.MANIM_CODER_PROMPT


def test_script_writer_prompt_writes_script_md():
    assert "/script.md" in prompts.SCRIPT_WRITER_PROMPT


def test_prompts_reference_their_skills() -> None:
    """Assert each agent prompt points to its on-demand skill."""
    assert "orchestrator-workflow" in prompts.ORCHESTRATOR_PROMPT
    assert "script-writing-3b1b" in prompts.SCRIPT_WRITER_PROMPT
    assert "manim-ce-coding" in prompts.MANIM_CODER_PROMPT
