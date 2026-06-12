"""Workspace-path helpers for ConceptFlow.

The orchestrator (the compiled root graph in `agent.py`) and the render
tool (in `render.py`) both need to resolve the same per-thread output
directory: ``./outputs/<sanitized thread_id>/``. Keeping these helpers
here — rather than in either downstream module — avoids a layering
inversion where the orchestrator imports a layout helper from a tool
module, and removes the duplicated
``configurable.get("thread_id")`` extraction that would otherwise live
in both call sites.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Where rendered MP4s and intermediate artifacts are written on the local
# machine. Tests monkeypatch this to redirect to a tmp dir.
_OUTPUTS_ROOT: Path = Path(__file__).resolve().parents[2] / "outputs"


def sanitize_thread_id(thread_id: str | None) -> str:
    """Return a filesystem-safe directory name derived from a thread id.

    Collapses the value to its basename (blocking ``../`` escapes), replaces
    any character outside ``[A-Za-z0-9_.-]`` with ``_``, strips leading dots,
    caps the result at 128 characters, and falls back to ``"default"`` when the
    input is empty or sanitizes away to nothing.

    Args:
        thread_id: Raw thread id from the run config, or ``None``.

    Returns:
        A safe directory-name string.
    """
    raw = thread_id or "default"
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(raw).name).lstrip(".")[:128]
    return cleaned or "default"


def output_dir(thread_id: str | None) -> Path:
    """Return the per-thread output directory under the outputs root.

    Args:
        thread_id: Raw thread id from the run config, or ``None``.

    Returns:
        ``<_OUTPUTS_ROOT>/<sanitized thread id>`` as a ``Path``.
    """
    return _OUTPUTS_ROOT / sanitize_thread_id(thread_id)


def out_dir_from_config(config: Mapping[str, Any] | None) -> Path:
    """Resolve the per-thread output directory from a LangChain run config.

    Extracts ``configurable.thread_id`` and returns the same
    ``<_OUTPUTS_ROOT>/<sanitized thread_id>`` path that
    :func:`output_dir` produces, defaulting to ``"default"`` when the
    config or thread id is absent. This is the single entry point used by
    both the orchestrator (to root the ``FilesystemBackend``) and the
    render tool (to locate ``scene.py`` and write ``video.mp4``).

    Args:
        config: A ``RunnableConfig``-shaped mapping, or ``None``. Any
            mapping supporting ``.get`` is accepted so callers can pass
            a ``RunnableConfig`` (a TypedDict) or a plain dict.

    Returns:
        The per-thread output directory as a ``Path``.
    """
    configurable = (config or {}).get("configurable") or {}
    return output_dir(configurable.get("thread_id"))
