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
import tempfile
from collections.abc import Callable
from pathlib import Path

_logger = logging.getLogger(__name__)

VALID_BACKENDS = ("gtts", "pyttsx3")


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


def _gtts_probe() -> None:
    """Synthesize a tiny phrase with gTTS to verify reachability.

    Raises:
        Exception: Propagates any gTTS/network error so the caller can fall
            back to pyttsx3.
    """
    from gtts import gTTS  # ty:ignore[unresolved-import]

    with tempfile.TemporaryDirectory() as tmp:
        gTTS(text="ok", lang="en").save(str(Path(tmp) / "probe.mp3"))


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
