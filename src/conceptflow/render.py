"""Custom `render_manim` tool for ConceptFlow.

Renders a Manim CE scene defined in the agent's virtual filesystem
(`/scene.py`) inside a Modal sandbox, then downloads the resulting MP4
to `./outputs/<thread_id>/video.mp4` on the local machine.

All Modal interaction is contained in this module so the rest of the
codebase can be tested without touching the network.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Annotated, Any

import modal
import modal.exception
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_modal import ModalSandbox
from langgraph.prebuilt import InjectedState

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

# Modal app namespacing all conceptflow sandboxes.
#
# We construct a local App at import time (no network, no auth required) so
# the module can be imported in hermetic test environments. The actual
# hydrated App used by `Sandbox.create` is fetched lazily inside
# `_run_render` via `modal.App.lookup(..., create_if_missing=True)`.
APP: modal.App = modal.App("conceptflow")

# Manim CE image. System packages are required for cairo/pango/ffmpeg;
# texlive-latex-extra is included so `MathTex` works when needed.
MANIM_IMAGE: modal.Image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "ffmpeg",
        "libcairo2-dev",
        "libpango1.0-dev",
        "texlive-latex-base",
        "texlive-fonts-recommended",
        "texlive-latex-extra",
    )
    .pip_install("manim==0.18.1")
)

# Hard wall-clock cap on a single render invocation.
_RENDER_TIMEOUT_SECONDS: int = 60 * 5

# Sandbox lifetime cap. Generous because the first invocation pays the
# image build cost.
_SANDBOX_TIMEOUT_SECONDS: int = 60 * 15

# Where rendered MP4s are written on the local machine.
_OUTPUTS_ROOT: Path = Path("./outputs")


@tool
async def render_manim(
    scene_class: str,
    state: Annotated[dict[str, Any], InjectedState],
    config: RunnableConfig,
) -> dict[str, Any]:
    """Render the Manim scene defined in `/scene.py` to an MP4.

    Args:
        scene_class: Name of the `Scene` subclass inside `/scene.py` to render
            (e.g. ``"PythagoreanIntro"``).

    Returns:
        A dict in one of three shapes:

        * Success::

              {"ok": True, "mp4_path": "./outputs/<thread_id>/video.mp4"}

        * Render failure (Manim subprocess exited non-zero)::

              {"ok": False, "kind": "render", "stderr": "...", "attempt": n}

        * Infrastructure failure (Modal API / sandbox spawn error)::

              {"ok": False, "kind": "infra", "message": "..."}

        * Logic failure (missing `/scene.py` in agent state)::

              {"ok": False, "kind": "logic", "message": "..."}
    """
    # 1. Pull /scene.py out of agent state.
    files = state.get("files") or {}
    file_entry = files.get("/scene.py")
    if file_entry is None:
        return {
            "ok": False,
            "kind": "logic",
            "message": (
                "/scene.py not found in the agent's virtual filesystem. "
                "Write it with write_file before calling render_manim."
            ),
        }
    source: str = file_entry["content"]

    # 2. Resolve thread_id for output namespacing.
    configurable = (config or {}).get("configurable") or {}
    thread_id: str = configurable.get("thread_id") or "default"

    # 3. Compute attempt number from prior tool messages.
    attempt: int = _count_prior_render_calls(state) + 1

    # 4. Run the render.
    return await _run_render(
        source=source,
        scene_class=scene_class,
        thread_id=thread_id,
        attempt=attempt,
    )


def _count_prior_render_calls(state: dict[str, Any]) -> int:
    """Count prior ToolMessages for `render_manim` in the message history."""
    messages = state.get("messages") or []
    return sum(
        1
        for m in messages
        if isinstance(m, ToolMessage) and getattr(m, "name", None) == "render_manim"
    )


def _select_final_mp4(candidates: list[str], scene_class: str) -> str | None:
    """Pick the final rendered MP4 from a list of `find` results.

    Manim leaves intermediate clips under ``partial_movie_files/`` in addition
    to the final ``<SceneClass>.mp4``. This selects the final render and never
    a partial.

    Args:
        candidates: Absolute MP4 paths found under the sandbox media dir.
        scene_class: The scene class name whose final render we want.

    Returns:
        The path to the final render, or ``None`` if none qualifies.
    """
    final = [c for c in candidates if "partial_movie_files" not in c.split("/")]
    if not final:
        return None
    # Prefer an exact ``<SceneClass>.mp4`` basename match; fall back to the
    # first non-partial candidate.
    target = f"{scene_class}.mp4"
    for path in final:
        if path.rsplit("/", 1)[-1] == target:
            return path
    return final[0]


async def _run_render(
    *,
    source: str,
    scene_class: str,
    thread_id: str,
    attempt: int,
) -> dict[str, Any]:
    """Run the blocking Modal render in a worker thread.

    The Modal SDK and ``langchain-modal`` expose only synchronous APIs, which
    would block the event loop if awaited inline. We offload the entire
    sandbox lifecycle to a thread via :func:`asyncio.to_thread` so the ASGI
    server stays responsive.
    """
    return await asyncio.to_thread(
        _run_render_blocking,
        source=source,
        scene_class=scene_class,
        thread_id=thread_id,
        attempt=attempt,
    )


def _run_render_blocking(
    *,
    source: str,
    scene_class: str,
    thread_id: str,
    attempt: int,
) -> dict[str, Any]:
    """Spin up a sandbox, run manim, download the MP4, tear the sandbox down.

    All Modal exceptions are caught and converted into the "infra" envelope.
    A non-zero manim exit code is converted into the "render" envelope.

    This function is fully synchronous and intended to be invoked from a
    worker thread (see :func:`_run_render`).
    """
    try:
        # Hydrate (or create) the named app on Modal's side before spawning
        # the sandbox. Done lazily here so importing this module never
        # requires Modal credentials.
        hydrated_app = modal.App.lookup("conceptflow", create_if_missing=True)
        modal_sb = modal.Sandbox.create(
            "sleep",
            "infinity",
            app=hydrated_app,
            image=MANIM_IMAGE,
            timeout=_SANDBOX_TIMEOUT_SECONDS,
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

        # Upload /scene.py into the sandbox workdir.
        sandbox.upload_files([("/work/scene.py", source.encode("utf-8"))])

        # Render. langchain-modal's ExecuteResponse exposes a single
        # combined `output` stream plus `exit_code`; we surface that output
        # under `stderr` so the manim-coder subagent's existing prompt
        # (which reads `stderr`) keeps working.
        exec_result = sandbox.execute(
            f"cd /work && manim -ql scene.py {scene_class}",
            timeout=_RENDER_TIMEOUT_SECONDS,
        )
        exit_code = exec_result.exit_code
        if exit_code != 0:
            return {
                "ok": False,
                "kind": "render",
                "stderr": exec_result.output,
                "attempt": attempt,
            }

        # Locate the produced MP4. Manim writes the final render to
        # /work/media/videos/scene/<quality>/<SceneClass>.mp4 and also leaves
        # intermediate clips under .../partial_movie_files/<SceneClass>/*.mp4.
        # We must pick the final render, never a partial.
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

        # Download.
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

        # Persist locally.
        out_dir = _OUTPUTS_ROOT / thread_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "video.mp4"
        out_path.write_bytes(content)

        return {"ok": True, "mp4_path": str(out_path)}

    except modal.exception.Error as exc:
        return {
            "ok": False,
            "kind": "infra",
            "message": f"Modal sandbox error during render: {exc!s}",
        }
    finally:
        # Best-effort teardown; ignore errors here.
        try:
            modal_sb.terminate()
        except Exception:  # noqa: BLE001 — teardown failure is non-fatal
            pass
