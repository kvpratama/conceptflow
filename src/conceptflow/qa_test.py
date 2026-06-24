"""Unit tests for the QA schema and qa_scene tool.

External services (Modal sandbox, the vision model) are mocked — no real
sandbox is created and no live model is called.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.runnables import RunnableConfig

from conceptflow.qa import QAIssue, SceneQA


def test_scene_qa_round_trips() -> None:
    qa = SceneQA(
        scene_class="Foo",
        passed=False,
        issues=[
            QAIssue(
                category="caption_overflow",
                severity="blocking",
                frames=[0, 1],
                description="Caption runs past the right edge.",
                suggestion="Use make_caption width-fitting.",
            )
        ],
    )
    dumped = qa.model_dump()
    assert dumped["scene_class"] == "Foo"
    assert dumped["passed"] is False
    assert dumped["issues"][0]["category"] == "caption_overflow"
    assert dumped["issues"][0]["severity"] == "blocking"


def test_scene_qa_defaults_to_no_issues() -> None:
    qa = SceneQA(scene_class="Bar", passed=True, issues=[])
    assert qa.issues == []
    assert qa.passed is True


def test_qa_scene_is_a_tool() -> None:
    from conceptflow.qa import qa_scene

    assert qa_scene.name == "qa_scene"


def _write_video(outputs_root: Path, thread_id: str, scene_class: str) -> None:
    """Write a fake rendered video into the per-thread output dir."""
    d = outputs_root / thread_id
    d.mkdir(parents=True, exist_ok=True)
    (d / f"video_{scene_class}.mp4").write_bytes(b"FAKEMP4")


def _make_exec_response(*, exit_code: int, output: str) -> MagicMock:
    resp = MagicMock(spec=["exit_code", "output", "truncated"])
    resp.exit_code = exit_code
    resp.output = output
    resp.truncated = False
    return resp


def _make_download_response(*, path: str, content: bytes | None, error: str | None = None):
    resp = MagicMock(spec=["path", "content", "error"])
    resp.path = path
    resp.content = content
    resp.error = error
    return resp


def _make_fake_sandbox(*, duration: str = "12.0\n", n_frames: int = 5) -> MagicMock:
    """A MagicMock that behaves like a ModalSandbox for QA review."""
    fake = MagicMock()
    fake.upload_files.return_value = []

    def _execute(command: str, *, timeout: int | None = None):
        if command.startswith("mkdir "):
            return _make_exec_response(exit_code=0, output="")
        if command.startswith("ffprobe "):
            return _make_exec_response(exit_code=0, output=duration)
        # ffmpeg frame extraction
        return _make_exec_response(exit_code=0, output="")

    fake.execute.side_effect = _execute
    fake.download_files.return_value = [
        _make_download_response(path=f"/work/qa_Foo/frame_{i}.png", content=b"PNG" + bytes([i]))
        for i in range(n_frames)
    ]
    return fake


def _patch_qa_model(monkeypatch: pytest.MonkeyPatch, result: SceneQA) -> None:
    """Make get_qa_model().with_structured_output().ainvoke() return result."""
    from conceptflow import qa

    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=result)
    model = MagicMock()
    model.with_structured_output = MagicMock(return_value=structured)
    monkeypatch.setattr(qa, "get_qa_model", lambda: model)


async def test_qa_scene_returns_logic_error_when_video_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, qa

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    state = {"messages": []}
    config: RunnableConfig = {"configurable": {"thread_id": "t-miss"}}

    result = await qa.qa_scene.ainvoke({"scene_class": "Foo", "state": state}, config=config)

    assert result["ok"] is False
    assert result["kind"] == "logic"
    assert "video_Foo.mp4" in result["message"]


async def test_qa_scene_rejects_invalid_scene_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conceptflow import qa

    result = await qa.qa_scene.ainvoke(
        {"scene_class": "Foo; rm -rf /", "state": {"messages": []}},
        config={"configurable": {"thread_id": "t"}},
    )
    assert result["ok"] is False
    assert result["kind"] == "logic"
    assert "Invalid scene_class" in result["message"]


async def test_qa_scene_success_returns_structured_qa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, qa, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_video(tmp_path / "outputs", "t-ok", "Foo")

    # Reuse a sandbox via state id so _resolve_sandbox uses from_id (no create).
    fake_modal_sb = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "from_id", MagicMock(return_value=fake_modal_sb))
    monkeypatch.setattr(qa, "ModalSandbox", MagicMock(return_value=_make_fake_sandbox()))

    _patch_qa_model(
        monkeypatch,
        SceneQA(
            scene_class="WRONG",  # tool must overwrite this with the real scene_class
            passed=True,
            issues=[
                QAIssue(
                    category="blank_frame",
                    severity="warning",
                    frames=[0],
                    description="First frame is empty.",
                    suggestion="Add an opening title.",
                )
            ],
        ),
    )

    state = {"messages": [], "render_sandbox_id": "sb-1"}
    config: RunnableConfig = {"configurable": {"thread_id": "t-ok"}}
    result = await qa.qa_scene.ainvoke({"scene_class": "Foo", "state": state}, config=config)

    assert result["ok"] is True
    assert result["qa"]["scene_class"] == "Foo"
    # No blocking issues -> passed recomputed True.
    assert result["qa"]["passed"] is True
    assert result["qa"]["issues"][0]["category"] == "blank_frame"
    # Shared sandbox was reused, not torn down by the tool.
    fake_modal_sb.terminate.assert_not_called()


async def test_qa_scene_recomputes_passed_from_blocking_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, qa, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_video(tmp_path / "outputs", "t-block", "Foo")
    monkeypatch.setattr(render.modal.Sandbox, "from_id", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(qa, "ModalSandbox", MagicMock(return_value=_make_fake_sandbox()))

    # Model claims passed=True but reports a blocking issue; tool must override.
    _patch_qa_model(
        monkeypatch,
        SceneQA(
            scene_class="Foo",
            passed=True,
            issues=[
                QAIssue(
                    category="offscreen_mobject",
                    severity="blocking",
                    frames=[2],
                    description="Circle is off the right edge.",
                    suggestion="Shift it left within the frame.",
                )
            ],
        ),
    )

    state = {"messages": [], "render_sandbox_id": "sb-1"}
    config: RunnableConfig = {"configurable": {"thread_id": "t-block"}}
    result = await qa.qa_scene.ainvoke({"scene_class": "Foo", "state": state}, config=config)

    assert result["ok"] is True
    assert result["qa"]["passed"] is False


async def test_qa_scene_returns_infra_when_ffprobe_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, qa, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_video(tmp_path / "outputs", "t-probe", "Foo")
    monkeypatch.setattr(render.modal.Sandbox, "from_id", MagicMock(return_value=MagicMock()))

    fake = MagicMock()
    fake.upload_files.return_value = []

    def _execute(command: str, *, timeout: int | None = None):
        if command.startswith("mkdir "):
            return _make_exec_response(exit_code=0, output="")
        if command.startswith("ffprobe "):
            return _make_exec_response(exit_code=1, output="bad file")
        return _make_exec_response(exit_code=0, output="")

    fake.execute.side_effect = _execute
    monkeypatch.setattr(qa, "ModalSandbox", MagicMock(return_value=fake))

    state = {"messages": [], "render_sandbox_id": "sb-1"}
    config: RunnableConfig = {"configurable": {"thread_id": "t-probe"}}
    result = await qa.qa_scene.ainvoke({"scene_class": "Foo", "state": state}, config=config)

    assert result["ok"] is False
    assert result["kind"] == "infra"
