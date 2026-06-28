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


def test_qa_agent_prompt_references_tool_skill_and_file() -> None:
    """Assert the QA agent prompt references its tool, skill, and output file."""
    assert isinstance(prompts.QA_AGENT_PROMPT, str)
    assert "qa_scene" in prompts.QA_AGENT_PROMPT
    assert "/qa.json" in prompts.QA_AGENT_PROMPT
    assert "qa-review" in prompts.QA_AGENT_PROMPT


def test_orchestrator_prompt_mentions_video_critic() -> None:
    """Assert the orchestrator prompt mentions the QA agent."""
    assert "qa-agent" in prompts.ORCHESTRATOR_PROMPT


def test_research_agent_prompt_is_non_empty_string() -> None:
    """Assert the research-agent prompt is a non-trivial string."""
    assert isinstance(prompts.RESEARCH_AGENT_PROMPT, str)
    assert len(prompts.RESEARCH_AGENT_PROMPT) > 100


def test_research_agent_prompt_references_skill_and_file() -> None:
    """Assert the research-agent prompt references its skill and output file."""
    assert "research-method" in prompts.RESEARCH_AGENT_PROMPT
    assert "/research.md" in prompts.RESEARCH_AGENT_PROMPT


def test_orchestrator_prompt_mentions_research_agent() -> None:
    """Assert the orchestrator prompt mentions the research-agent."""
    assert "research-agent" in prompts.ORCHESTRATOR_PROMPT


def test_script_writer_prompt_references_research_md() -> None:
    """Assert the script-writer prompt references the research output file."""
    assert "/research.md" in prompts.SCRIPT_WRITER_PROMPT
