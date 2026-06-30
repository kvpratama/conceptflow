"""LLM-as-judge content moderation for ConceptFlow.

Provides a single :func:`moderate` entry point used by the orchestrator's input
and output moderation middleware. The judge reuses the configured "small" model
(:func:`conceptflow.config.get_model_small`) with structured output, so no
dedicated moderation-API provider is required.

The policy is intentionally narrow: it blocks operational instructions to cause
serious harm while letting explanatory, educational framing of
sensitive-but-legitimate topics through, consistent with ConceptFlow's
3Blue1Brown educational mission.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from conceptflow.config import get_model_small

Kind = Literal["input", "output"]


class SafetyVerdict(BaseModel):
    """Structured moderation verdict returned by the judge model.

    Attributes:
        allowed: True when the content is permissible, False when it violates
            the policy rubric.
        categories: The matched policy category labels when ``allowed`` is
            False; empty when the content is allowed.
        reason: A short, human-readable explanation of the verdict.
    """

    allowed: bool = Field(description="True if the content is permissible under the policy.")
    categories: list[str] = Field(
        default_factory=list,
        description="Matched policy category labels when the content is blocked.",
    )
    reason: str = Field(default="", description="Short human-readable explanation of the verdict.")


SAFETY_RUBRIC = """\
You are a strict but fair content-safety classifier for an educational video \
generator that produces 3Blue1Brown-style explainer videos. Decide whether the \
provided text is permissible.

BLOCK the content (allowed = false) if it falls into any of these categories:
1. csae — sexual content involving minors.
2. violent_extremism — terrorism or violent-extremism instructions or promotion.
3. weapons — instructions to synthesise or build weapons, explosives, or bioweapons.
4. harassment — credible threats, targeted harassment, or doxxing.
5. self_harm — promotion or encouragement of self-harm or suicide.
6. illicit_howto — actionable how-to for illicit behaviour (e.g. malware, drug synthesis).

ALLOW the content (allowed = true) otherwise. Critically, EDUCATIONAL or \
CONCEPTUAL framing of sensitive-but-legitimate topics must be ALLOWED. \
Explaining how something works at a conceptual level (e.g. "how nuclear \
fission works", "the history of a war", "how viruses infect cells") is allowed. \
Only block when the text provides, or explicitly requests, OPERATIONAL \
INSTRUCTIONS that enable real-world harm.

Return your verdict in the required structured format. When blocking, list the \
matched category labels and give a brief reason. When allowing, set categories \
to an empty list."""

_FRAME = {
    "input": (
        "The following is a USER-SUPPLIED TOPIC requesting an educational video. "
        "Classify the topic:\n\n"
    ),
    "output": (
        "The following is a GENERATED VIDEO SCRIPT (narration and scene plan). "
        "Classify the script:\n\n"
    ),
}


async def moderate(text: str, *, kind: Kind) -> SafetyVerdict:
    """Classify text against the content-safety rubric using the judge model.

    Fails closed: any error from the judge model or its structured output is
    treated as a blocking verdict rather than silently allowing the content.

    Args:
        text: The content to classify (a user topic or a generated script).
        kind: ``"input"`` to frame the text as a user topic, ``"output"`` to
            frame it as a generated script.

    Returns:
        A :class:`SafetyVerdict`. On judge failure, a fail-closed verdict with
        ``allowed=False`` and category ``"moderation_error"``.
    """
    judge = get_model_small().with_structured_output(SafetyVerdict)
    messages = [
        SystemMessage(content=SAFETY_RUBRIC),
        HumanMessage(content=f"{_FRAME[kind]}{text}"),
    ]
    try:
        verdict = await judge.ainvoke(messages)
    except Exception as exc:  # fail closed on any judge failure
        return SafetyVerdict(
            allowed=False,
            categories=["moderation_error"],
            reason=f"Moderation judge failed; failing closed: {exc!s}",
        )
    if not isinstance(verdict, SafetyVerdict):
        return SafetyVerdict(
            allowed=False,
            categories=["moderation_error"],
            reason="Moderation judge returned an unexpected payload; failing closed.",
        )
    return verdict
