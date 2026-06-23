"""SubAgent configurations for the ConceptFlow orchestrator.

Each subagent is a `deepagents.SubAgent` dict registered with the root
agent. The orchestrator addresses them by name via the `task` tool.
"""

from __future__ import annotations

from typing import Any, cast

from deepagents import SubAgent
from langchain.agents.middleware import AgentMiddleware, AgentState

from conceptflow import prompts
from conceptflow.config import get_settings
from conceptflow.critique import critique_scene
from conceptflow.render import render_manim, stitch_videos
from conceptflow.sandbox_middleware import ManimSandboxMiddleware


def build_subagents() -> list[SubAgent]:
    """Return the list of subagents to register with the root deep agent.

    Returns:
        A list of three `SubAgent` dicts:

        * ``"script-writer"`` — uses only the built-in toolset
          (`write_file`, `read_file`, etc.).
        * ``"manim-coder"`` — built-ins plus the custom `render_manim` tool.
        * ``"qa-agent"`` — built-ins plus the custom `critique_scene` tool.
    """
    max_render_attempts = get_settings().max_render_attempts
    return [
        SubAgent(
            name="script-writer",
            description=(
                "Turn a user-supplied topic into a short narration and a "
                "one-scene visual plan for a Manim CE animation. Persists "
                "the result to /script.md in the shared workspace."
            ),
            system_prompt=prompts.SCRIPT_WRITER_PROMPT,
            skills=["/skills/script-writer/"],
        ),
        SubAgent(
            name="manim-coder",
            description=(
                "Read /script.md, write /scene.py as a Manim CE module, and "
                "render it via the render_manim tool. Self-corrects up to "
                f"{max_render_attempts} render attempts on render errors."
            ),
            system_prompt=prompts.MANIM_CODER_PROMPT,
            tools=[render_manim, stitch_videos],
            middleware=[
                cast(
                    AgentMiddleware[AgentState[Any], None, Any],
                    ManimSandboxMiddleware(),
                )
            ],
            skills=["/skills/manim-coder/"],
        ),
        SubAgent(
            name="qa-agent",
            description=(
                "Review each rendered video_<Scene>.mp4 for visual defects "
                "(off-screen mobjects, caption overflow/overlap, blank frames) "
                "via critique_scene, and write structured findings to "
                "/critique.json."
            ),
            system_prompt=prompts.QA_AGENT_PROMPT,
            tools=[critique_scene],
            middleware=[
                cast(
                    AgentMiddleware[AgentState[Any], None, Any],
                    ManimSandboxMiddleware(),
                )
            ],
            skills=["/skills/qa-agent/"],
        ),
    ]
