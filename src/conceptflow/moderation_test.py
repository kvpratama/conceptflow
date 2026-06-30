"""Unit tests for the LLM-as-judge moderation helper."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from conceptflow import moderation
from conceptflow.moderation import SafetyVerdict, moderate


def _patch_judge(monkeypatch: pytest.MonkeyPatch, judge: object) -> None:
    """Patch ``get_model_small().with_structured_output(...)`` to return ``judge``."""
    model = SimpleNamespace(with_structured_output=lambda _schema: judge)
    monkeypatch.setattr(moderation, "get_model_small", lambda: model)


async def test_allowed_verdict_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    judge = SimpleNamespace(ainvoke=AsyncMock(return_value=SafetyVerdict(allowed=True)))
    _patch_judge(monkeypatch, judge)

    verdict = await moderate("How does gradient descent work?", kind="input")

    assert verdict.allowed is True
    assert verdict.categories == []


async def test_flagged_verdict_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    flagged = SafetyVerdict(allowed=False, categories=["weapons"], reason="bomb how-to")
    judge = SimpleNamespace(ainvoke=AsyncMock(return_value=flagged))
    _patch_judge(monkeypatch, judge)

    verdict = await moderate("step-by-step bomb instructions", kind="output")

    assert verdict.allowed is False
    assert verdict.categories == ["weapons"]


async def test_judge_exception_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    judge = SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError("api down")))
    _patch_judge(monkeypatch, judge)

    verdict = await moderate("anything", kind="input")

    assert verdict.allowed is False
    assert verdict.categories == ["moderation_error"]


async def test_unexpected_payload_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    judge = SimpleNamespace(ainvoke=AsyncMock(return_value={"not": "a verdict"}))
    _patch_judge(monkeypatch, judge)

    verdict = await moderate("anything", kind="output")

    assert verdict.allowed is False
    assert verdict.categories == ["moderation_error"]
