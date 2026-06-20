"""Unit tests for the render_manim tool.

External services (Modal) are mocked — no real sandbox is created.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig


def test_module_exposes_render_manim_tool() -> None:
    from conceptflow.render import render_manim

    # langchain @tool produces a BaseTool — it should have a `.name` attribute.
    assert render_manim.name == "render_manim"


def test_module_exposes_modal_image_with_manim_deps() -> None:
    from conceptflow import render

    assert hasattr(render, "MANIM_IMAGE")
    # The image object isn't introspectable for installed packages, but we
    # at least confirm it's a modal.Image subclass.
    import modal

    assert isinstance(render.MANIM_IMAGE, modal.Image)


async def test_render_returns_logic_error_when_scene_py_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, render

    # Point outputs at an empty temp dir so scene.py is genuinely absent.
    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")

    state = {"files": {}, "messages": []}
    config: RunnableConfig = {"configurable": {"thread_id": "t1"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["ok"] is False
    assert result["kind"] == "logic"
    assert "scene.py" in result["message"]


async def test_render_rejects_invalid_scene_class_without_starting_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conceptflow import render

    sandbox_create = MagicMock()
    app_lookup = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(render.modal.Sandbox, "create", sandbox_create)
    monkeypatch.setattr(render.modal.App, "lookup", app_lookup)

    state = {"files": {"/scene.py": {"content": "x", "encoding": "utf-8"}}, "messages": []}
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo; rm -rf /", "state": state}, config=config
    )

    assert result["ok"] is False
    assert result["kind"] == "logic"
    assert "Invalid scene_class" in result["message"]
    sandbox_create.assert_not_called()
    app_lookup.assert_not_called()


def _write_scene(
    outputs_root: Path, thread_id: str, content: str = "from manim import *\n"
) -> None:
    """Write a scene.py into the per-thread output dir, as the agent would."""
    scene_dir = outputs_root / thread_id
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "scene.py").write_text(content, encoding="utf-8")


def _make_exec_response(*, exit_code: int, output: str) -> MagicMock:
    """Mock of langchain_modal.sandbox.ExecuteResponse (dataclass)."""
    resp = MagicMock(spec=["exit_code", "output", "truncated"])
    resp.exit_code = exit_code
    resp.output = output
    resp.truncated = False
    return resp


def _make_download_response(
    *, path: str, content: bytes | None, error: str | None = None
) -> MagicMock:
    """Mock of langchain_modal.sandbox.FileDownloadResponse (dataclass)."""
    resp = MagicMock(spec=["path", "content", "error"])
    resp.path = path
    resp.content = content
    resp.error = error
    return resp


def _make_upload_response(*, path: str, error: str | None = None) -> MagicMock:
    """Mock of langchain_modal.sandbox.FileUploadResponse (dataclass)."""
    resp = MagicMock(spec=["path", "error"])
    resp.path = path
    resp.error = error
    return resp


def _make_fake_sandbox(
    *,
    exit_code: int = 0,
    stderr: str = "",
    stdout: str = "",
    find_stdout: str = "/work/media/videos/scene/480p15/Foo.mp4\n",
    mp4_bytes: bytes = b"FAKEMP4",
):
    """Return a MagicMock that behaves like a ModalSandbox."""
    fake = MagicMock()
    fake.upload_files.return_value = []

    # Combined stdout+stderr matches the real ExecuteResponse.output field.
    combined_output = stdout + stderr

    def _execute(command: str, *, timeout: int | None = None):
        if command.startswith("mkdir "):
            return _make_exec_response(exit_code=0, output="")
        if command.startswith("find "):
            return _make_exec_response(exit_code=0, output=find_stdout)
        # The manim render call.
        return _make_exec_response(exit_code=exit_code, output=combined_output)

    fake.execute.side_effect = _execute
    fake.download_files.return_value = [
        _make_download_response(path="/work/media/videos/scene/480p15/Foo.mp4", content=mp4_bytes)
    ]
    return fake


async def test_render_success_writes_mp4_and_returns_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, render

    # Redirect outputs to a tmp dir.
    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "thread-xyz")

    # Mock modal.Sandbox.create and ModalSandbox.
    fake_modal_sb = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=fake_modal_sb))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))
    fake_sandbox = _make_fake_sandbox(mp4_bytes=b"HELLO_MP4")
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    state = {
        "files": {"/scene.py": {"content": "from manim import *\n", "encoding": "utf-8"}},
        "messages": [],
    }
    config: RunnableConfig = {"configurable": {"thread_id": "thread-xyz"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result == {
        "ok": True,
        "mp4_path": "/video_Foo.mp4",
    }
    written = (tmp_path / "outputs" / "thread-xyz" / "video_Foo.mp4").read_bytes()
    assert written == b"HELLO_MP4"

    # The manim command was invoked with -ql and the scene class.
    called_commands = [call.args[0] for call in fake_sandbox.execute.call_args_list]
    assert any("manim -ql scene.py Foo" in cmd for cmd in called_commands)

    # Sandbox was torn down.
    fake_modal_sb.terminate.assert_called_once()


async def test_render_reuses_sandbox_when_id_in_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When state carries render_sandbox_id, render reconnects and does not own it."""
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t-reuse")

    fake_modal_sb = MagicMock()
    create = MagicMock(return_value=fake_modal_sb)
    from_id = MagicMock(return_value=fake_modal_sb)
    monkeypatch.setattr(render.modal.Sandbox, "create", create)
    monkeypatch.setattr(render.modal.Sandbox, "from_id", from_id)
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=_make_fake_sandbox()))

    state = {
        "files": {"/scene.py": {"content": "x", "encoding": "utf-8"}},
        "messages": [],
        "render_sandbox_id": "sb-123",
    }
    config: RunnableConfig = {"configurable": {"thread_id": "t-reuse"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["ok"] is True
    from_id.assert_called_once_with("sb-123")
    create.assert_not_called()
    fake_modal_sb.terminate.assert_not_called()


async def test_render_isolates_work_dir_per_scene_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each render uses a per-scene_class workdir (/work/<SceneClass>/) so two
    concurrent renders of different scenes never share scene.py or media/."""
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t-iso")
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))

    fake_sandbox = _make_fake_sandbox()
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    state = {
        "files": {"/scene.py": {"content": "from manim import *\n", "encoding": "utf-8"}},
        "messages": [],
    }
    config: RunnableConfig = {"configurable": {"thread_id": "t-iso"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["ok"] is True

    # Uploads are namespaced under /work/Foo/.
    uploaded_paths = [item[0] for item in fake_sandbox.upload_files.call_args.args[0]]
    assert "/work/Foo/scene.py" in uploaded_paths
    assert "/work/Foo/sandbox_tts.py" in uploaded_paths

    # The manim render and the find both target the per-scene dir.
    commands = [call.args[0] for call in fake_sandbox.execute.call_args_list]
    assert any("cd /work/Foo &&" in cmd and "manim -ql scene.py Foo" in cmd for cmd in commands)
    assert any(cmd.startswith("find /work/Foo/media ") for cmd in commands)


async def test_render_creates_remote_work_dir_before_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-scene sandbox directory must exist before uploading files into it."""
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t-mkdir")
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))

    fake_sandbox = _make_fake_sandbox()
    events: list[str] = []

    def _execute(command: str, *, timeout: int | None = None) -> MagicMock:
        if command.startswith("mkdir "):
            events.append("mkdir")
            return _make_exec_response(exit_code=0, output="")
        if command.startswith("find "):
            return _make_exec_response(
                exit_code=0,
                output="/work/Foo/media/videos/scene/480p15/Foo.mp4\n",
            )
        return _make_exec_response(exit_code=0, output="")

    def _upload_files(files: list[tuple[str, bytes]]) -> list[MagicMock]:
        events.append("upload")
        return [_make_upload_response(path=path) for path, _ in files]

    fake_sandbox.execute.side_effect = _execute
    fake_sandbox.upload_files.side_effect = _upload_files
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    state = {"files": {}, "messages": []}
    config: RunnableConfig = {"configurable": {"thread_id": "t-mkdir"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["ok"] is True
    assert events[:2] == ["mkdir", "upload"]
    assert fake_sandbox.execute.call_args_list[0].args[0] == "mkdir -p /work/Foo"


async def test_render_returns_infra_when_upload_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upload errors should stop before the render command hides the real cause."""
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t-upload-fail")
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))

    fake_sandbox = _make_fake_sandbox()
    fake_sandbox.upload_files.return_value = [
        _make_upload_response(path="/work/Foo/sandbox_tts.py"),
        _make_upload_response(path="/work/Foo/scene.py", error="file_not_found"),
    ]
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    state = {"files": {}, "messages": []}
    config: RunnableConfig = {"configurable": {"thread_id": "t-upload-fail"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["ok"] is False
    assert result["kind"] == "infra"
    assert "Failed to upload render files" in result["message"]
    assert "/work/Foo/scene.py: file_not_found" in result["message"]
    render_commands = [
        call.args[0] for call in fake_sandbox.execute.call_args_list if "manim -ql" in call.args[0]
    ]
    assert render_commands == []


async def test_render_selects_final_mp4_not_partial_movie_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When `find` returns partial movie files alongside the final render,
    the final `<SceneClass>.mp4` (outside partial_movie_files) is chosen."""
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t-partial")
    fake_modal_sb = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=fake_modal_sb))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))

    # `find` lists a partial movie file BEFORE the final render — the old
    # `candidates[0]` logic would have picked the partial.
    fake_sandbox = _make_fake_sandbox(
        find_stdout=(
            "/work/media/videos/scene/480p15/partial_movie_files/Foo/abc123.mp4\n"
            "/work/media/videos/scene/480p15/partial_movie_files/Foo/def456.mp4\n"
            "/work/media/videos/scene/480p15/Foo.mp4\n"
        ),
    )
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    state = {
        "files": {"/scene.py": {"content": "from manim import *\n", "encoding": "utf-8"}},
        "messages": [],
    }
    config: RunnableConfig = {"configurable": {"thread_id": "t-partial"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["ok"] is True
    # The final render — not a partial movie file — was downloaded.
    downloaded = fake_sandbox.download_files.call_args.args[0]
    assert downloaded == ["/work/media/videos/scene/480p15/Foo.mp4"]


async def test_render_returns_render_error_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t-err")
    fake_modal_sb = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=fake_modal_sb))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))
    fake_sandbox = _make_fake_sandbox(
        exit_code=1,
        stderr="NameError: name 'Squarez' is not defined",
        stdout="Manim Community v0.18.1",
    )
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    state = {
        "files": {"/scene.py": {"content": "from manim import *\n", "encoding": "utf-8"}},
        "messages": [],
    }
    config: RunnableConfig = {"configurable": {"thread_id": "t-err"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["ok"] is False
    assert result["kind"] == "render"
    assert "NameError" in result["stderr"]
    assert result["attempt"] == 1
    fake_modal_sb.terminate.assert_called_once()


async def test_attempt_counter_reflects_prior_tool_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t")
    fake_modal_sb = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=fake_modal_sb))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))
    fake_sandbox = _make_fake_sandbox(exit_code=1, stderr="boom")
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "render_manim",
                "args": {"scene_class": "Foo"},
                "id": "x1",
                "type": "tool_call",
            },
            {
                "name": "render_manim",
                "args": {"scene_class": "Foo"},
                "id": "x3",
                "type": "tool_call",
            },
        ],
    )
    prior1 = ToolMessage(content="boom", name="render_manim", tool_call_id="x1")
    other = ToolMessage(content="ok", name="write_file", tool_call_id="x2")
    prior2 = ToolMessage(content="boom", name="render_manim", tool_call_id="x3")

    state = {
        "files": {"/scene.py": {"content": "x", "encoding": "utf-8"}},
        "messages": [ai_msg, prior1, other, prior2],  # 2 prior render_manim calls
    }
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["attempt"] == 3


async def test_render_refuses_once_attempt_cap_exceeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When prior render attempts hit the cap, the tool short-circuits.

    No sandbox is created and an 'exhausted' stop envelope is returned so
    the cap is enforced in code, not merely advised in the prompt.
    """
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t")
    sandbox_create = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", sandbox_create)
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "render_manim",
                "args": {"scene_class": "Foo"},
                "id": "x1",
                "type": "tool_call",
            },
            {
                "name": "render_manim",
                "args": {"scene_class": "Foo"},
                "id": "x2",
                "type": "tool_call",
            },
            {
                "name": "render_manim",
                "args": {"scene_class": "Foo"},
                "id": "x3",
                "type": "tool_call",
            },
        ],
    )
    prior1 = ToolMessage(content="boom", name="render_manim", tool_call_id="x1")
    prior2 = ToolMessage(content="boom", name="render_manim", tool_call_id="x2")
    prior3 = ToolMessage(content="boom", name="render_manim", tool_call_id="x3")
    state = {
        "files": {"/scene.py": {"content": "x", "encoding": "utf-8"}},
        "messages": [ai_msg, prior1, prior2, prior3],  # 3 prior render_manim calls (cap=3)
    }
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["ok"] is False
    assert result["kind"] == "exhausted"
    assert result["attempt"] == 4
    # The cap is enforced before any Modal interaction.
    sandbox_create.assert_not_called()


async def test_render_returns_infra_error_when_sandbox_fails_to_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t")

    def _explode(*_args, **_kwargs):
        raise render.modal.exception.AuthError("missing token")

    monkeypatch.setattr(render.modal.App, "lookup", _explode)

    state = {"files": {}, "messages": []}
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["ok"] is False
    assert result["kind"] == "infra"
    assert "missing token" in result["message"]


async def test_thread_id_defaults_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "default")
    fake_modal_sb = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=fake_modal_sb))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=_make_fake_sandbox()))

    state = {
        "files": {"/scene.py": {"content": "x", "encoding": "utf-8"}},
        "messages": [],
    }
    # No thread_id in config.
    empty_config: RunnableConfig = {}
    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=empty_config
    )

    assert result["ok"] is True
    assert result["mp4_path"] == "/video_Foo.mp4"
    assert (tmp_path / "outputs" / "default" / "video_Foo.mp4").is_file()


async def test_render_uses_custom_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow import paths, render

    monkeypatch.setenv("MODAL_APP_NAME", "custom-app-name")
    monkeypatch.setenv("MODAL_SANDBOX_TIMEOUT", "123")
    render.get_settings.cache_clear()

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t")
    mock_lookup = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(render.modal.App, "lookup", mock_lookup)
    mock_create = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(render.modal.Sandbox, "create", mock_create)
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=_make_fake_sandbox()))

    state = {
        "files": {"/scene.py": {"content": "x", "encoding": "utf-8"}},
        "messages": [],
    }
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}
    await render.render_manim.ainvoke({"scene_class": "Foo", "state": state}, config=config)

    mock_lookup.assert_called_once_with("custom-app-name", create_if_missing=True)
    assert mock_create.call_args.kwargs["timeout"] == 123


async def test_stitch_videos_empty_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow.render import stitch_videos

    config: RunnableConfig = {"configurable": {"thread_id": "t"}}
    result = await stitch_videos.ainvoke(
        {"mp4_paths": [], "state": {"messages": []}}, config=config
    )

    assert result["ok"] is False
    assert result["kind"] == "logic"
    assert "mp4_paths is empty" in result["message"]


async def test_stitch_videos_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conceptflow import paths
    from conceptflow.render import stitch_videos

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    # The file does not exist on disk
    result = await stitch_videos.ainvoke(
        {"mp4_paths": ["/video_Foo.mp4"], "state": {"messages": []}}, config=config
    )

    assert result["ok"] is False
    assert result["kind"] == "logic"
    assert "File not found" in result["message"]


async def test_stitch_videos_single_scene_shortcut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths
    from conceptflow.render import stitch_videos

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    # Write a dummy input video file
    t_dir = tmp_path / "outputs" / "t"
    t_dir.mkdir(parents=True, exist_ok=True)
    (t_dir / "video_Foo.mp4").write_bytes(b"SINGLE_SCENE")

    # Call stitch with 1 scene -> should copy file directly
    result = await stitch_videos.ainvoke(
        {"mp4_paths": ["/video_Foo.mp4"], "state": {"messages": []}}, config=config
    )

    assert result == {"ok": True, "mp4_path": "/video.mp4"}
    # Verify the file was copied
    assert (t_dir / "video.mp4").read_bytes() == b"SINGLE_SCENE"


async def test_stitch_videos_multiple_scenes_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    # Write input video files
    t_dir = tmp_path / "outputs" / "t"
    t_dir.mkdir(parents=True, exist_ok=True)
    (t_dir / "video_Foo.mp4").write_bytes(b"SCENE1")
    (t_dir / "video_Bar.mp4").write_bytes(b"SCENE2")

    fake_modal_sb = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=fake_modal_sb))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))

    fake_sandbox = MagicMock()
    fake_sandbox.upload_files.return_value = []
    fake_sandbox.execute.return_value = _make_exec_response(exit_code=0, output="ffmpeg ok")
    fake_sandbox.download_files.return_value = [
        _make_download_response(path="/work/output.mp4", content=b"STITCHED_OK")
    ]
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    result = await render.stitch_videos.ainvoke(
        {"mp4_paths": ["/video_Foo.mp4", "/video_Bar.mp4"], "state": {"messages": []}},
        config=config,
    )

    assert result == {"ok": True, "mp4_path": "/video.mp4"}
    assert (t_dir / "video.mp4").read_bytes() == b"STITCHED_OK"

    # Verify sandbox interactions
    fake_modal_sb.terminate.assert_called_once()
    uploaded = fake_sandbox.upload_files.call_args[0][0]
    # Expect: [('/work/concat_list.txt', ...), ...]
    assert uploaded[0][0] == "/work/concat_list.txt"
    assert b"file '/work/video_Foo.mp4'" in uploaded[0][1]
    assert b"file '/work/video_Bar.mp4'" in uploaded[0][1]


async def test_stitch_reuses_sandbox_when_id_in_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-scene stitch reconnects to the shared sandbox and does not own it."""
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    t_dir = tmp_path / "outputs" / "t"
    t_dir.mkdir(parents=True, exist_ok=True)
    (t_dir / "video_Foo.mp4").write_bytes(b"S1")
    (t_dir / "video_Bar.mp4").write_bytes(b"S2")

    fake_modal_sb = MagicMock()
    create = MagicMock(return_value=fake_modal_sb)
    from_id = MagicMock(return_value=fake_modal_sb)
    monkeypatch.setattr(render.modal.Sandbox, "create", create)
    monkeypatch.setattr(render.modal.Sandbox, "from_id", from_id)
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))

    fake_sandbox = MagicMock()
    fake_sandbox.upload_files.return_value = []
    fake_sandbox.execute.return_value = _make_exec_response(exit_code=0, output="ok")
    fake_sandbox.download_files.return_value = [
        _make_download_response(path="/work/output.mp4", content=b"OUT")
    ]
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    state = {"messages": [], "render_sandbox_id": "sb-xyz"}
    result = await render.stitch_videos.ainvoke(
        {"mp4_paths": ["/video_Foo.mp4", "/video_Bar.mp4"], "state": state},
        config=config,
    )

    assert result == {"ok": True, "mp4_path": "/video.mp4"}
    from_id.assert_called_once_with("sb-xyz")
    create.assert_not_called()
    fake_modal_sb.terminate.assert_not_called()


async def test_stitch_videos_ffmpeg_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    t_dir = tmp_path / "outputs" / "t"
    t_dir.mkdir(parents=True, exist_ok=True)
    (t_dir / "video_Foo.mp4").write_bytes(b"SCENE1")
    (t_dir / "video_Bar.mp4").write_bytes(b"SCENE2")

    fake_modal_sb = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=fake_modal_sb))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))

    fake_sandbox = MagicMock()
    fake_sandbox.upload_files.return_value = []
    fake_sandbox.execute.return_value = _make_exec_response(exit_code=1, output="ffmpeg crashed")
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    result = await render.stitch_videos.ainvoke(
        {"mp4_paths": ["/video_Foo.mp4", "/video_Bar.mp4"], "state": {"messages": []}},
        config=config,
    )

    assert result["ok"] is False
    assert result["kind"] == "infra"
    assert "ffmpeg concat failed" in result["message"]
    assert "ffmpeg crashed" in result["message"]
    fake_modal_sb.terminate.assert_called_once()


async def test_stitch_videos_download_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    t_dir = tmp_path / "outputs" / "t"
    t_dir.mkdir(parents=True, exist_ok=True)
    (t_dir / "video_Foo.mp4").write_bytes(b"SCENE1")
    (t_dir / "video_Bar.mp4").write_bytes(b"SCENE2")

    fake_modal_sb = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=fake_modal_sb))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))

    fake_sandbox = MagicMock()
    fake_sandbox.upload_files.return_value = []
    fake_sandbox.execute.return_value = _make_exec_response(exit_code=0, output="ffmpeg ok")
    fake_sandbox.download_files.return_value = [
        _make_download_response(path="/work/output.mp4", content=None, error="download timeout")
    ]
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    result = await render.stitch_videos.ainvoke(
        {"mp4_paths": ["/video_Foo.mp4", "/video_Bar.mp4"], "state": {"messages": []}},
        config=config,
    )

    assert result["ok"] is False
    assert result["kind"] == "infra"
    assert "Failed to download stitched video" in result["message"]
    fake_modal_sb.terminate.assert_called_once()


async def test_stitch_videos_sandbox_creation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    t_dir = tmp_path / "outputs" / "t"
    t_dir.mkdir(parents=True, exist_ok=True)
    (t_dir / "video_Foo.mp4").write_bytes(b"SCENE1")
    (t_dir / "video_Bar.mp4").write_bytes(b"SCENE2")

    def _explode(*_args, **_kwargs):
        raise render.modal.exception.AuthError("bad token")

    monkeypatch.setattr(render.modal.App, "lookup", _explode)

    result = await render.stitch_videos.ainvoke(
        {"mp4_paths": ["/video_Foo.mp4", "/video_Bar.mp4"], "state": {"messages": []}},
        config=config,
    )

    assert result["ok"] is False
    assert result["kind"] == "infra"
    assert "Modal sandbox failed to start" in result["message"]


async def test_stitch_videos_rejects_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths
    from conceptflow.render import stitch_videos

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    # Create outputs root and thread subdirs
    t_dir = tmp_path / "outputs" / "t"
    t_dir.mkdir(parents=True, exist_ok=True)

    # Rejects path traversal and non-absolute logical paths
    test_cases = [
        "/../secret.txt",
        "/a/../../b",
        "../x",
        "/video_Foo.mp4/../bar",
        "/",
        "/..",
        "video_Foo.mp4",
        "/video_Foo.mp4/abc",
    ]

    for bad_path in test_cases:
        result = await stitch_videos.ainvoke(
            {"mp4_paths": [bad_path], "state": {"messages": []}}, config=config
        )
        assert result["ok"] is False, f"Path '{bad_path}' should have been rejected."
        assert result["kind"] == "logic"
        assert "Invalid path" in result["message"]


async def test_render_uploads_sandbox_tts_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sandbox-side TTS helper is uploaded alongside scene.py."""
    from conceptflow import paths, render

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t-tts")
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))
    fake_sandbox = _make_fake_sandbox()
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    state = {
        "files": {"/scene.py": {"content": "x", "encoding": "utf-8"}},
        "messages": [],
    }
    config: RunnableConfig = {"configurable": {"thread_id": "t-tts"}}
    await render.render_manim.ainvoke({"scene_class": "Foo", "state": state}, config=config)

    uploaded = fake_sandbox.upload_files.call_args[0][0]
    uploaded_paths = [entry[0] for entry in uploaded]
    assert "/work/Foo/sandbox_tts.py" in uploaded_paths
    assert "/work/Foo/scene.py" in uploaded_paths


async def test_render_command_passes_tts_service_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The configured tts_service is exported into the manim render command."""
    from conceptflow import paths, render

    monkeypatch.setenv("TTS_SERVICE", "pyttsx3")
    render.get_settings.cache_clear()

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t-env")
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))
    fake_sandbox = _make_fake_sandbox()
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    state = {
        "files": {"/scene.py": {"content": "x", "encoding": "utf-8"}},
        "messages": [],
    }
    config: RunnableConfig = {"configurable": {"thread_id": "t-env"}}
    await render.render_manim.ainvoke({"scene_class": "Foo", "state": state}, config=config)

    render.get_settings.cache_clear()
    commands = [call.args[0] for call in fake_sandbox.execute.call_args_list]
    assert any("TTS_SERVICE=pyttsx3 manim -ql scene.py Foo" in cmd for cmd in commands)
