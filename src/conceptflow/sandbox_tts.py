"""Sandbox-side TTS helper for ConceptFlow Manim renders.

This module is uploaded into the Modal render sandbox alongside ``scene.py``
(see :func:`conceptflow.render._read_sandbox_tts_source`) and imported by the
generated ``scene.py`` to build a manim-voiceover ``SpeechService`` with a
gTTS-primary, pyttsx3-fallback policy.

All ``manim_voiceover`` / ``gtts`` imports are performed lazily inside
functions so this module can be imported (and its pure decision logic
unit-tested) in the host environment, where those sandbox-only packages are
not installed.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Callable

_logger = logging.getLogger(__name__)

VALID_BACKENDS = ("gtts", "pyttsx3")

# Hard wall-clock cap on the gTTS reachability probe. Kept well under the outer
# manim render timeout so a hung/unreachable gTTS endpoint falls back to
# pyttsx3 quickly instead of stalling the whole render.
_PROBE_TIMEOUT_SECONDS: float = 15.0

# Self-contained synthesis run in a short-lived subprocess so it can be killed
# on timeout (gTTS/requests offer no usable per-call cancellation in-process).
_PROBE_SCRIPT = (
    "import tempfile\n"
    "from pathlib import Path\n"
    "from gtts import gTTS\n"
    "with tempfile.TemporaryDirectory() as tmp:\n"
    "    gTTS(text='ok', lang='en').save(str(Path(tmp) / 'probe.mp3'))\n"
)


def resolve_tts_backend(requested: str, probe: Callable[[], None]) -> str:
    """Resolve the concrete TTS backend name for a single scene render.

    Args:
        requested: Configured backend name (``"gtts"`` or ``"pyttsx3"``).
        probe: Zero-arg callable that raises if gTTS is unreachable. Only
            invoked when ``requested == "gtts"``.

    Returns:
        ``"gtts"`` when gTTS is requested and the probe succeeds; ``"pyttsx3"``
        when pyttsx3 is requested, or when gTTS is requested but the probe
        fails.

    Raises:
        ValueError: If ``requested`` is not a recognised backend name.
    """
    if requested not in VALID_BACKENDS:
        raise ValueError(f"Unknown TTS backend {requested!r}. Expected one of {VALID_BACKENDS}.")
    if requested == "pyttsx3":
        return "pyttsx3"
    try:
        probe()
    except Exception as exc:
        _logger.warning("gTTS probe failed (%s); falling back to pyttsx3.", exc)
        return "pyttsx3"
    return "gtts"


def _gtts_probe(timeout: float = _PROBE_TIMEOUT_SECONDS) -> None:
    """Synthesize a tiny phrase with gTTS in a subprocess to verify reachability.

    The synthesis runs in a short-lived subprocess bounded by a hard wall-clock
    timeout, so a hung or unreachable gTTS endpoint cannot block the render
    indefinitely. On timeout the subprocess is killed and ``TimeoutError`` is
    raised; any other failure (missing dependency, network error, non-zero
    exit) propagates as ``subprocess.CalledProcessError``. Either way the caller
    falls back to pyttsx3.

    Args:
        timeout: Maximum seconds to wait for the probe subprocess.

    Raises:
        TimeoutError: If the probe does not complete within ``timeout`` seconds.
        subprocess.CalledProcessError: If the probe subprocess exits non-zero.
    """
    try:
        subprocess.run(
            [sys.executable, "-c", _PROBE_SCRIPT],
            check=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"gTTS probe exceeded {timeout:g}s timeout") from exc


def build_speech_service(requested: str | None = None) -> object:
    """Build a manim-voiceover SpeechService per the configured policy.

    The concrete backend is decided once here, so a single scene render uses
    one consistent voice. gTTS is preferred and, when unreachable, pyttsx3 is
    used instead. If pyttsx3 itself is unavailable, its constructor raises and
    the render fails loudly (surfaced through render_manim's error envelope).

    Args:
        requested: Backend name override. When ``None``, read from the
            ``TTS_SERVICE`` environment variable (default ``"gtts"``).

    Returns:
        A ``manim_voiceover.services.base.SpeechService`` instance. Typed as
        ``object`` because the concrete type lives in the sandbox-only
        ``manim_voiceover`` package, which the host cannot import.
    """
    if requested is None:
        requested = os.environ.get("TTS_SERVICE", "gtts")

    backend = resolve_tts_backend(requested, _gtts_probe)

    if backend == "pyttsx3":
        from manim_voiceover.services.pyttsx3 import (  # ty:ignore[unresolved-import]
            PyTTSX3Service,
        )

        return PyTTSX3Service()

    from manim_voiceover.services.gtts import GTTSService  # ty:ignore[unresolved-import]

    return GTTSService()
