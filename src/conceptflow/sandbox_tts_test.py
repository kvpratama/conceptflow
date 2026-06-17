"""Tests for the sandbox-side TTS helper.

The pure decision logic (resolve_tts_backend) runs in the host. The
manim-voiceover binding (build_speech_service / _gtts_probe with the real
GTTSService / PyTTSX3Service) is sandbox-only and covered by an integration
test that is skipped by default.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from conceptflow.sandbox_tts import resolve_tts_backend


def test_resolve_returns_gtts_when_probe_succeeds() -> None:
    calls: list[str] = []

    def probe() -> None:
        calls.append("probed")

    assert resolve_tts_backend("gtts", probe) == "gtts"
    assert calls == ["probed"]


def test_resolve_falls_back_to_pyttsx3_when_probe_fails() -> None:
    def probe() -> None:
        raise RuntimeError("network down")

    assert resolve_tts_backend("gtts", probe) == "pyttsx3"


def test_resolve_pyttsx3_does_not_probe() -> None:
    def probe() -> None:
        raise AssertionError("probe must not be called for pyttsx3")

    assert resolve_tts_backend("pyttsx3", probe) == "pyttsx3"


def test_resolve_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unknown TTS backend"):
        resolve_tts_backend("elevenlabs", lambda: None)


def test_build_speech_service_defaults_to_env_and_returns_gtts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With TTS_SERVICE unset, build_speech_service requests gtts and returns it."""
    from conceptflow import sandbox_tts

    captured: dict[str, str] = {}

    def fake_resolve(requested: str, probe: object) -> str:
        captured["requested"] = requested
        return "gtts"

    monkeypatch.setattr(sandbox_tts, "resolve_tts_backend", fake_resolve)

    sentinel = object()
    gtts_mod: Any = types.ModuleType("manim_voiceover.services.gtts")
    gtts_mod.GTTSService = lambda: sentinel
    monkeypatch.setitem(sys.modules, "manim_voiceover", types.ModuleType("manim_voiceover"))
    monkeypatch.setitem(
        sys.modules, "manim_voiceover.services", types.ModuleType("manim_voiceover.services")
    )
    monkeypatch.setitem(sys.modules, "manim_voiceover.services.gtts", gtts_mod)

    monkeypatch.delenv("TTS_SERVICE", raising=False)
    result = sandbox_tts.build_speech_service()

    assert captured["requested"] == "gtts"
    assert result is sentinel


def test_build_speech_service_returns_pyttsx3_when_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When resolution picks pyttsx3, the pyttsx3 service is constructed."""
    from conceptflow import sandbox_tts

    monkeypatch.setattr(sandbox_tts, "resolve_tts_backend", lambda requested, probe: "pyttsx3")

    sentinel = object()
    pyttsx3_mod: Any = types.ModuleType("manim_voiceover.services.pyttsx3")
    pyttsx3_mod.PyTTSX3Service = lambda: sentinel
    monkeypatch.setitem(sys.modules, "manim_voiceover", types.ModuleType("manim_voiceover"))
    monkeypatch.setitem(
        sys.modules, "manim_voiceover.services", types.ModuleType("manim_voiceover.services")
    )
    monkeypatch.setitem(sys.modules, "manim_voiceover.services.pyttsx3", pyttsx3_mod)

    monkeypatch.setenv("TTS_SERVICE", "pyttsx3")
    result = sandbox_tts.build_speech_service()

    assert result is sentinel


@pytest.mark.integration
def test_build_speech_service_pyttsx3_real() -> None:
    """Integration: build a real PyTTSX3Service (needs manim-voiceover + espeak)."""
    pytest.importorskip("manim_voiceover")
    from conceptflow.sandbox_tts import build_speech_service

    service = build_speech_service("pyttsx3")
    assert service.__class__.__name__ == "PyTTSX3Service"
