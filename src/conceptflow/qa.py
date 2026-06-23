"""Vision-LLM QA review of rendered Manim scenes for ConceptFlow.

`qa_scene` uploads a rendered ``video_<SceneClass>.mp4`` to the reused
Modal render sandbox, extracts a handful of evenly-spaced frames with ffmpeg,
and asks a multimodal model to flag the most common 3Blue1Brown-style visual
defects: off-screen mobjects, caption overflow/overlap, and blank frames. The
model returns a structured ``SceneQA`` so the manim-coder subagent can act
on it.
"""

from __future__ import annotations

import asyncio
import base64
import re
from typing import Annotated, Any, Literal, cast

import modal
import modal.exception
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_modal import ModalSandbox
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from conceptflow.config import get_qa_model, get_settings
from conceptflow.paths import out_dir_from_config
from conceptflow.render import _RENDER_TIMEOUT_SECONDS, _resolve_sandbox

# Number of evenly-spaced frames sampled per scene for the vision QA review.
_FRAME_SAMPLE_COUNT: int = 5

# Downscale width (px) for sampled frames to bound vision-token cost.
_FRAME_WIDTH: int = 640

_SCENE_CLASS_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_QA_SYSTEM_PROMPT: str = (
    "You are a strict visual reviewer for 3Blue1Brown-style explainer animations. "
    "You are shown several evenly-spaced frames sampled from a single rendered scene. "
    "Identify ONLY clear, visible defects in these categories: "
    "offscreen_mobject (an element drawn partly or fully outside the frame), "
    "caption_overflow (a caption running past the screen edges), "
    "caption_overlap (a caption overlapping another caption or mobject), "
    "blank_frame (an empty or near-empty frame), and other (any other obvious "
    "visual defect). Mark an issue 'blocking' only when it clearly degrades the "
    "video; use 'warning' for minor concerns. If the scene looks fine, return no "
    "issues. Always give a concrete, actionable suggestion for each issue."
)


class QAIssue(BaseModel):
    """A single visual defect found in a rendered scene."""

    category: Literal[
        "offscreen_mobject",
        "caption_overflow",
        "caption_overlap",
        "blank_frame",
        "other",
    ] = Field(description="The kind of visual defect.")
    severity: Literal["blocking", "warning"] = Field(
        description="'blocking' if it must be fixed, 'warning' if minor."
    )
    frames: list[int] = Field(
        default_factory=list,
        description="Indices of the sampled frames that show this issue.",
    )
    description: str = Field(description="What is wrong, concretely.")
    suggestion: str = Field(description="An actionable fix for the manim-coder.")


class SceneQA(BaseModel):
    """The QA review result for one rendered scene."""

    scene_class: str = Field(description="The Scene subclass name that was reviewed.")
    passed: bool = Field(description="True when the scene has no blocking issues.")
    issues: list[QAIssue] = Field(default_factory=list, description="All visual defects found.")


def _parse_duration(output: str) -> float | None:
    """Parse a float duration (seconds) from ffprobe output.

    Args:
        output: Raw stdout from ffprobe's duration query.

    Returns:
        The duration in seconds, or None if it cannot be parsed or is <= 0.
    """
    try:
        value = float(output.strip().splitlines()[0])
    except ValueError, IndexError:
        return None
    return value if value > 0 else None


def _extract_frames_blocking(
    *,
    video_bytes: bytes,
    scene_class: str,
    sandbox_id: str | None,
    frame_count: int,
) -> dict[str, Any]:
    """Upload a scene video to a sandbox and extract evenly-spaced PNG frames.

    Fully synchronous; intended to run in a worker thread.

    Args:
        video_bytes: The rendered scene MP4 bytes.
        scene_class: The Scene subclass name (validated; used as a path segment).
        sandbox_id: Object id of the shared render sandbox, or None for an
            ephemeral one.
        frame_count: Number of evenly-spaced frames to sample.

    Returns:
        On success: {\"ok\": True, \"frames\": list[bytes]}.
        On failure: {\"ok\": False, \"kind\": \"infra\", \"message\": str}.
    """
    try:
        settings = get_settings()
        modal_sb, owned = _resolve_sandbox(sandbox_id, settings)
    except modal.exception.Error as exc:
        return {
            "ok": False,
            "kind": "infra",
            "message": f"Modal sandbox failed to start: {exc!s}",
        }

    try:
        work_dir = f"/work/qa_{scene_class}"
        video_path = f"{work_dir}/video.mp4"
        sandbox = ModalSandbox(sandbox=modal_sb)

        mkdir = sandbox.execute(f"mkdir -p {work_dir}", timeout=_RENDER_TIMEOUT_SECONDS)
        if mkdir.exit_code != 0:
            return {
                "ok": False,
                "kind": "infra",
                "message": f"Failed to create QA work dir {work_dir}:\n{mkdir.output}",
            }

        sandbox.upload_files([(video_path, video_bytes)])

        probe = sandbox.execute(
            "ffprobe -v error -show_entries format=duration "
            f"-of default=noprint_wrappers=1:nokey=1 {video_path}",
            timeout=_RENDER_TIMEOUT_SECONDS,
        )
        if probe.exit_code != 0:
            return {
                "ok": False,
                "kind": "infra",
                "message": f"ffprobe failed for {video_path}:\n{probe.output}",
            }
        duration = _parse_duration(probe.output)
        if duration is None:
            return {
                "ok": False,
                "kind": "infra",
                "message": (
                    f"Could not determine video duration from ffprobe output: {probe.output!r}"
                ),
            }

        remote_frames: list[str] = []
        for i in range(frame_count):
            timestamp = duration * (i + 0.5) / frame_count
            frame_path = f"{work_dir}/frame_{i}.png"
            extract = sandbox.execute(
                f"ffmpeg -y -ss {timestamp:.3f} -i {video_path} -frames:v 1 "
                f"-vf scale={_FRAME_WIDTH}:-2 {frame_path}",
                timeout=_RENDER_TIMEOUT_SECONDS,
            )
            if extract.exit_code != 0:
                return {
                    "ok": False,
                    "kind": "infra",
                    "message": (
                        f"ffmpeg frame extraction failed at {timestamp:.3f}s:\n{extract.output}"
                    ),
                }
            remote_frames.append(frame_path)

        downloads = sandbox.download_files(remote_frames)
        frames: list[bytes] = []
        for d in downloads:
            if d.content is None:
                return {
                    "ok": False,
                    "kind": "infra",
                    "message": f"Failed to download frame {d.path}: {d.error!r}",
                }
            frames.append(d.content)

        return {"ok": True, "frames": frames}

    except modal.exception.Error as exc:
        return {
            "ok": False,
            "kind": "infra",
            "message": f"Modal sandbox error during QA review: {exc!s}",
        }
    finally:
        if owned:
            try:
                modal_sb.terminate()
            except modal.exception.Error:  # teardown failure is non-fatal
                pass


async def _qa_frames(scene_class: str, frames: list[bytes]) -> SceneQA:
    """Ask the vision model to review sampled frames, returning a SceneQA.

    Args:
        scene_class: The Scene subclass name under review.
        frames: PNG-encoded sampled frames, in temporal order.

    Returns:
        A SceneQA whose ``scene_class`` is forced to ``scene_class`` and
        whose ``passed`` is recomputed from the presence of blocking issues.
    """
    content: list[Any] = [
        {
            "type": "text",
            "text": (
                f"Review scene '{scene_class}'. The following {len(frames)} frames are "
                "in temporal order (index 0 first)."
            ),
        }
    ]
    for png in frames:
        b64 = base64.b64encode(png).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

    model = get_qa_model().with_structured_output(SceneQA)
    result = cast(
        SceneQA,
        await model.ainvoke(
            [SystemMessage(content=_QA_SYSTEM_PROMPT), HumanMessage(content=content)]
        ),
    )

    # Guarantee correctness regardless of what the model returned.
    result.scene_class = scene_class
    result.passed = not any(issue.severity == "blocking" for issue in result.issues)
    return result


@tool
async def qa_scene(
    scene_class: str,
    state: Annotated[dict[str, Any], InjectedState],
    config: RunnableConfig,
) -> dict[str, Any]:
    """Review a rendered scene's visuals and return structured QA findings.

    Samples evenly-spaced frames from ``video_<scene_class>.mp4`` and asks a
    multimodal model to flag off-screen mobjects, caption overflow/overlap, and
    blank frames.

    Args:
        scene_class: Name of the Scene subclass whose render to review.

    Returns:
        On success::

            {"ok": True, "qa": <SceneQA dict>}

        On a bad scene_class or missing video::

            {"ok": False, "kind": "logic", "message": "..."}

        On sandbox / ffmpeg failure::

            {"ok": False, "kind": "infra", "message": "..."}
    """
    if _SCENE_CLASS_RE.fullmatch(scene_class) is None:
        return {
            "ok": False,
            "kind": "logic",
            "message": (
                "Invalid scene_class. Expected a valid Python identifier "
                "matching ^[A-Za-z_][A-Za-z0-9_]*$."
            ),
        }

    out_dir = out_dir_from_config(config)
    video_path = out_dir / f"video_{scene_class}.mp4"
    if not video_path.is_file():
        return {
            "ok": False,
            "kind": "logic",
            "message": (
                f"video_{scene_class}.mp4 not found at {video_path}. Render the scene "
                "before reviewing it."
            ),
        }

    video_bytes = await asyncio.to_thread(video_path.read_bytes)
    extraction = await asyncio.to_thread(
        _extract_frames_blocking,
        video_bytes=video_bytes,
        scene_class=scene_class,
        sandbox_id=state.get("render_sandbox_id"),
        frame_count=_FRAME_SAMPLE_COUNT,
    )
    if not extraction["ok"]:
        return extraction

    qa = await _qa_frames(scene_class, extraction["frames"])
    return {"ok": True, "qa": qa.model_dump()}
