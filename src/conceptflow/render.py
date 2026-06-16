"""Custom `render_manim` and `stitch_videos` tools for ConceptFlow.

render_manim:
    Renders a single Manim CE scene from `./outputs/<thread_id>/scene.py`
    inside a Modal sandbox, then downloads the result to
    `./outputs/<thread_id>/video_<SceneClass>.mp4`.
    Retry budget is tracked per scene_class, not globally.

stitch_videos:
    Uploads per-scene MP4s to a Modal sandbox, runs ffmpeg concat inside
    it, and downloads the result to `./outputs/<thread_id>/video.mp4`.
    Single-scene shortcut: copies the file locally without spawning a sandbox.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

import modal
import modal.exception
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_modal import ModalSandbox
from langgraph.prebuilt import InjectedState

from conceptflow.config import get_settings
from conceptflow.paths import out_dir_from_config

# Pre-resolve and cache the system temp directory at import time, while no
# asyncio event loop is running.
#
# Modal's `Resolver` creates a `tempfile.TemporaryFile()` during
# `Sandbox.create`, and `tempfile.gettempdir()` *always* calls the blocking
# `os.getcwd()` the first time it runs (to build its candidate-directory
# list). Because Modal executes that work on an event loop, BlockBuster
# (enabled by `langgraph dev`) rejects the `os.getcwd()` call. Warming the
# cache here means the result is stored in `tempfile.tempdir` once, so the
# later call inside Modal never touches `os.getcwd()` again.
tempfile.gettempdir()

# Manim CE image. System packages are required for cairo/pango/ffmpeg;
# texlive-latex-extra is included so `MathTex` works when needed.
MANIM_IMAGE: modal.Image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install(
        "ffmpeg",
        "libcairo2-dev",
        "libpango1.0-dev",
        "texlive-latex-base",
        "texlive-fonts-recommended",
        "texlive-latex-extra",
        # pyttsx3 offline-fallback voice (espeak) + libespeak runtime, and
        # sox, a transitive manim-voiceover dependency.
        "espeak",
        "libespeak1",
        "sox",
    )
    .uv_pip_install(
        "manim==0.20.1",
        "manim-voiceover[gtts,pyttsx3]==0.4.0",
    )
)

# Hard wall-clock cap on a single render or stitch invocation.
_RENDER_TIMEOUT_SECONDS: int = 60 * 5

_SCENE_CLASS_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@lru_cache(maxsize=1)
def _read_sandbox_tts_source() -> str:
    """Read the sandbox-side TTS helper module source for upload.

    Returns:
        The text of ``sandbox_tts.py`` from this package, to be written into
        the render sandbox at ``/work/sandbox_tts.py``.
    """
    return (Path(__file__).resolve().parent / "sandbox_tts.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# render_manim
# ---------------------------------------------------------------------------


@tool
async def render_manim(
    scene_class: str,
    state: Annotated[dict[str, Any], InjectedState],
    config: RunnableConfig,
) -> dict[str, Any]:
    """Render one Manim scene class from /scene.py to /video_<SceneClass>.mp4.

    Args:
        scene_class: Name of the Scene subclass to render
            (e.g. ``"PythagoreanIntro"``).

    Returns:
        A dict in one of these shapes:

        * Success::

              {"ok": True, "mp4_path": "/video_<SceneClass>.mp4"}

        * Render failure (Manim subprocess exited non-zero)::

              {"ok": False, "kind": "render", "stderr": "...", "attempt": n}

        * Infrastructure failure (Modal API / sandbox error)::

              {"ok": False, "kind": "infra", "message": "..."}

        * Logic failure (bad scene_class or missing scene.py)::

              {"ok": False, "kind": "logic", "message": "..."}

        * Exhausted per-scene retry budget::

              {"ok": False, "kind": "exhausted", "message": "...", "attempt": n}
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

    scene_path = out_dir / "scene.py"
    if not scene_path.is_file():
        return {
            "ok": False,
            "kind": "logic",
            "message": (
                f"scene.py not found at {scene_path}. Write it with write_file "
                "before calling render_manim."
            ),
        }
    source: str = await asyncio.to_thread(scene_path.read_text, encoding="utf-8")

    # Per-scene retry budget.
    attempt: int = _count_prior_render_calls(state, scene_class) + 1
    max_attempts: int = get_settings().max_render_attempts
    if attempt > max_attempts:
        return {
            "ok": False,
            "kind": "exhausted",
            "attempt": attempt,
            "message": (
                f"Render retry budget exhausted after {max_attempts} attempts "
                f"for scene '{scene_class}'. Stop retrying and report the last "
                "render failure to the orchestrator."
            ),
        }

    return await _run_render(
        source=source,
        scene_class=scene_class,
        out_dir=out_dir,
        attempt=attempt,
    )


# ---------------------------------------------------------------------------
# stitch_videos
# ---------------------------------------------------------------------------


@tool
async def stitch_videos(
    mp4_paths: list[str],
    config: RunnableConfig,
) -> dict[str, Any]:
    """Concatenate per-scene MP4s into a single /video.mp4.

    Uploads the files to a Modal sandbox and runs ffmpeg concat inside it,
    so no local ffmpeg installation is required.

    Args:
        mp4_paths: Ordered list of mp4_path values returned by render_manim,
            e.g. ``["/video_Scene1.mp4", "/video_Scene2.mp4"]``.

    Returns:
        A dict in one of these shapes:

        * Success::

              {"ok": True, "mp4_path": "/video.mp4"}

        * Logic failure (empty list or missing file on disk)::

              {"ok": False, "kind": "logic", "message": "..."}

        * Infrastructure failure (Modal API / sandbox error or ffmpeg error)::

              {"ok": False, "kind": "infra", "message": "..."}
    """
    if not mp4_paths:
        return {
            "ok": False,
            "kind": "logic",
            "message": "mp4_paths is empty. Provide at least one rendered MP4 path.",
        }

    out_dir = out_dir_from_config(config)

    # Resolve logical paths ("/video_Foo.mp4") to local disk paths.
    local_paths: list[Path] = []
    out_dir_resolved = out_dir.resolve()
    for logical in mp4_paths:
        if not logical.startswith("/"):
            return {
                "ok": False,
                "kind": "logic",
                "message": (
                    f"Invalid path '{logical}': must start with '/' as an absolute "
                    "logical workspace path."
                ),
            }

        # Prefer using Path(logical).name to drop directories, and then validate the name.
        name = Path(logical).name
        if name != logical.lstrip("/") or name in ("", ".", "..") or "/" in name or "\\" in name:
            return {
                "ok": False,
                "kind": "logic",
                "message": (
                    f"Invalid path '{logical}': path traversal or subdirectories are not allowed."
                ),
            }

        candidate = (out_dir / name).resolve()
        if out_dir_resolved not in candidate.parents or candidate == out_dir_resolved:
            return {
                "ok": False,
                "kind": "logic",
                "message": f"Invalid path '{logical}': path escapes the output directory.",
            }

        if not candidate.is_file():
            return {
                "ok": False,
                "kind": "logic",
                "message": (
                    f"File not found: {candidate}. Ensure render_manim succeeded "
                    "for all scenes before calling stitch_videos."
                ),
            }
        local_paths.append(candidate)

    # Single scene: skip the sandbox, just copy locally.
    if len(local_paths) == 1:
        out_path = out_dir / "video.mp4"
        await asyncio.to_thread(shutil.copy2, str(local_paths[0]), str(out_path))
        return {"ok": True, "mp4_path": "/video.mp4"}

    return await asyncio.to_thread(_stitch_blocking, local_paths, out_dir)


def _stitch_blocking(local_paths: list[Path], out_dir: Path) -> dict[str, Any]:
    """Upload per-scene MP4s to a Modal sandbox, run ffmpeg concat, download result.

    This function is fully synchronous and intended to be invoked from a
    worker thread (see :func:`stitch_videos`).

    Args:
        local_paths: List of absolute file paths to the local per-scene MP4 files.
        out_dir: The directory where the final stitched video should be saved.

    Returns:
        A dictionary containing the result of the stitch operation. On success,
        keys are {"ok": True, "mp4_path": "/video.mp4"}. On failure, keys
        include {"ok": False, "kind": str, "message": str}.
    """
    try:
        settings = get_settings()
        hydrated_app = modal.App.lookup(settings.modal_app_name, create_if_missing=True)

        modal_sb = modal.Sandbox.create(
            "sleep",
            "infinity",
            app=hydrated_app,
            image=MANIM_IMAGE,
            timeout=settings.modal_sandbox_timeout,
            workdir="/work",
        )
    except modal.exception.Error as exc:
        return {
            "ok": False,
            "kind": "infra",
            "message": f"Modal sandbox failed to start: {exc!s}",
        }

    try:
        sandbox = ModalSandbox(sandbox=modal_sb)

        # Build the concat list and collect file uploads in one pass.
        concat_lines: list[str] = []
        file_uploads: list[tuple[str, bytes]] = []
        for p in local_paths:
            remote_path = f"/work/{p.name}"
            concat_lines.append(f"file '{remote_path}'")
            file_uploads.append((remote_path, p.read_bytes()))

        concat_content = "\n".join(concat_lines).encode("utf-8")
        sandbox.upload_files(
            [
                ("/work/concat_list.txt", concat_content),
                *file_uploads,
            ]
        )

        result = sandbox.execute(
            "ffmpeg -y -f concat -safe 0 -i /work/concat_list.txt -c copy /work/output.mp4",
            timeout=_RENDER_TIMEOUT_SECONDS,
        )
        if result.exit_code != 0:
            return {
                "ok": False,
                "kind": "infra",
                "message": f"ffmpeg concat failed:\n{result.output}",
            }

        downloads = sandbox.download_files(["/work/output.mp4"])
        content = downloads[0].content
        if content is None:
            return {
                "ok": False,
                "kind": "infra",
                "message": (f"Failed to download stitched video: {downloads[0].error!r}"),
            }

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "video.mp4"
        out_path.write_bytes(content)
        return {"ok": True, "mp4_path": "/video.mp4"}

    except modal.exception.Error as exc:
        return {
            "ok": False,
            "kind": "infra",
            "message": f"Modal sandbox error during stitch: {exc!s}",
        }
    finally:
        try:
            modal_sb.terminate()
        except Exception:  # noqa: BLE001 — teardown failure is non-fatal
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_prior_render_calls(state: dict[str, Any], scene_class: str) -> int:
    """Count completed render_manim calls for a specific scene_class.

    Correlates AIMessage tool_calls with their ToolMessage responses so that
    only completed attempts are counted, and only for the given scene_class.

    Args:
        state: The current LangGraph state dictionary.
        scene_class: The class name of the scene to count renders for.

    Returns:
        The number of completed render_manim attempts for the specified scene class.
    """
    messages = state.get("messages") or []

    # Map tool_call_id -> scene_class for every render_manim invocation.
    render_ids: dict[str, str] = {}
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in getattr(m, "tool_calls", []):
                if isinstance(tc, dict) and tc.get("name") == "render_manim":
                    render_ids[tc["id"]] = tc.get("args", {}).get("scene_class", "")

    # Count ToolMessages whose call completed for this scene_class.
    return sum(
        1
        for m in messages
        if (
            isinstance(m, ToolMessage)
            and getattr(m, "name", None) == "render_manim"
            and render_ids.get(getattr(m, "tool_call_id", None)) == scene_class  # ty:ignore[invalid-argument-type]
        )
    )


def _select_final_mp4(candidates: list[str], scene_class: str) -> str | None:
    """Pick the final rendered MP4, excluding Manim's partial_movie_files clips.

    Args:
        candidates: Absolute MP4 paths found under the sandbox media dir.
        scene_class: The scene class name whose final render we want.

    Returns:
        The path to the final render, or ``None`` if none qualifies.
    """
    final = [c for c in candidates if "partial_movie_files" not in c.split("/")]
    if not final:
        return None
    target = f"{scene_class}.mp4"
    for path in final:
        if path.rsplit("/", 1)[-1] == target:
            return path
    return final[0]


async def _run_render(
    *,
    source: str,
    scene_class: str,
    out_dir: Path,
    attempt: int,
) -> dict[str, Any]:
    """Offload the blocking Modal render to a worker thread.

    Args:
        source: The Manim Python source code content.
        scene_class: The name of the scene class to render.
        out_dir: The directory where the rendered video should be saved.
        attempt: The current attempt number for this render.

    Returns:
        A dictionary containing the result of the render invocation.
    """
    return await asyncio.to_thread(
        _run_render_blocking,
        source=source,
        scene_class=scene_class,
        out_dir=out_dir,
        attempt=attempt,
    )


def _run_render_blocking(
    *,
    source: str,
    scene_class: str,
    out_dir: Path,
    attempt: int,
) -> dict[str, Any]:
    """Spin up a sandbox, run manim, download the MP4, tear the sandbox down.

    All Modal exceptions are caught and converted into the "infra" envelope.
    A non-zero manim exit code is converted into the "render" envelope.

    This function is fully synchronous and intended to be invoked from a
    worker thread (see :func:`_run_render`).

    Args:
        source: The Manim Python source code content.
        scene_class: The name of the scene class to render.
        out_dir: The directory where the rendered video should be saved.
        attempt: The current attempt number for this render.

    Returns:
        A dictionary containing the result of the render invocation. On success,
        keys are {"ok": True, "mp4_path": str}. On failure, keys include
        {"ok": False, "kind": str, ...}.
    """
    try:
        settings = get_settings()
        hydrated_app = modal.App.lookup(settings.modal_app_name, create_if_missing=True)

        modal_sb = modal.Sandbox.create(
            "sleep",
            "infinity",
            app=hydrated_app,
            image=MANIM_IMAGE,
            timeout=settings.modal_sandbox_timeout,
            workdir="/work",
        )
    except modal.exception.Error as exc:
        return {
            "ok": False,
            "kind": "infra",
            "message": f"Modal sandbox failed to start: {exc!s}",
        }

    try:
        sandbox = ModalSandbox(sandbox=modal_sb)
        sandbox.upload_files(
            [
                ("/work/sandbox_tts.py", _read_sandbox_tts_source().encode("utf-8")),
                ("/work/scene.py", source.encode("utf-8")),
            ]
        )

        # langchain-modal's ExecuteResponse exposes a single combined `output`
        # stream plus `exit_code`; we surface that output under `stderr` so the
        # manim-coder subagent's prompt (which reads `stderr`) keeps working.
        exec_result = sandbox.execute(
            f"cd /work && TTS_SERVICE={settings.tts_service} manim -ql scene.py {scene_class}",
            timeout=_RENDER_TIMEOUT_SECONDS,
        )
        if exec_result.exit_code != 0:
            return {
                "ok": False,
                "kind": "render",
                "stderr": exec_result.output,
                "attempt": attempt,
            }

        # Locate the final MP4. Manim writes it to
        # /work/media/videos/scene/<quality>/<SceneClass>.mp4 and also leaves
        # intermediate clips under .../partial_movie_files/<SceneClass>/*.mp4.
        find = sandbox.execute("find /work/media -name '*.mp4' -type f")
        candidates = [line.strip() for line in find.output.splitlines() if line.strip()]
        remote_mp4 = _select_final_mp4(candidates, scene_class)
        if remote_mp4 is None:
            return {
                "ok": False,
                "kind": "render",
                "stderr": "Manim exited 0 but no final .mp4 file was produced.",
                "attempt": attempt,
            }

        downloads = sandbox.download_files([remote_mp4])
        content = downloads[0].content
        if content is None:
            return {
                "ok": False,
                "kind": "infra",
                "message": (
                    f"Failed to download {remote_mp4} from sandbox: {downloads[0].error!r}"
                ),
            }

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"video_{scene_class}.mp4"
        out_path.write_bytes(content)

        return {"ok": True, "mp4_path": f"/video_{scene_class}.mp4"}

    except modal.exception.Error as exc:
        return {
            "ok": False,
            "kind": "infra",
            "message": f"Modal sandbox error during render: {exc!s}",
        }
    finally:
        try:
            modal_sb.terminate()
        except Exception:  # noqa: BLE001 — teardown failure is non-fatal
            pass
