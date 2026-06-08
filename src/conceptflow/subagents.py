"""SubAgent configurations for the ConceptFlow orchestrator.

Each subagent is a `deepagents.SubAgent` dict registered with the root
agent. The orchestrator addresses them by name via the `task` tool.
"""

from __future__ import annotations

from deepagents import SubAgent

from conceptflow import prompts
from conceptflow.render import render_manim


def build_subagents() -> list[SubAgent]:
    """Return the list of subagents to register with the root deep agent.

    Returns:
        A list of two `SubAgent` dicts:

        * ``"script-writer"`` — uses only the built-in toolset
          (`write_file`, `read_file`, etc.).
        * ``"manim-coder"`` — built-ins plus the custom `render_manim` tool.
    """
    return [
        SubAgent(
            name="script-writer",
            description=(
                "Turn a user-supplied topic into a short narration and a "
                "one-scene visual plan for a Manim CE animation. Persists "
                "the result to /script.md in the shared workspace."
            ),
            system_prompt=prompts.SCRIPT_WRITER_PROMPT,
        ),
        SubAgent(
            name="manim-coder",
            description=(
                "Read /script.md, write /scene.py as a Manim CE module, and "
                "render it via the render_manim tool. Self-corrects up to "
                "3 times on render errors."
            ),
            system_prompt=prompts.MANIM_CODER_PROMPT,
            tools=[render_manim],
        ),
    ]
