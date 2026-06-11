"""Unit tests for the render_manim tool.

External services (Modal) are mocked — no real sandbox is created.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig


def test_module_exposes_render_manim_tool():
    from conceptflow.render import render_manim

    # langchain @tool produces a BaseTool — it should have a `.name` attribute.
    assert render_manim.name == "render_manim"


def test_module_exposes_modal_image_with_manim_deps():
    from conceptflow import render

    assert hasattr(render, "MANIM_IMAGE")
    # The image object isn't introspectable for installed packages, but we
    # at least confirm it's a modal.Image subclass.
    import modal

    assert isinstance(render.MANIM_IMAGE, modal.Image)


async def test_render_returns_logic_error_when_scene_py_missing(tmp_path, monkeypatch):
    from conceptflow import render

    # Point outputs at an empty temp dir so scene.py is genuinely absent.
    monkeypatch.setattr(render, "_OUTPUTS_ROOT", tmp_path / "outputs")

    state = {"files": {}, "messages": []}
    config: RunnableConfig = {"configurable": {"thread_id": "t1"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["ok"] is False
    assert result["kind"] == "logic"
    assert "scene.py" in result["message"]


async def test_render_rejects_invalid_scene_class_without_starting_sandbox(monkeypatch):
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
        if command.startswith("find "):
            return _make_exec_response(exit_code=0, output=find_stdout)
        # The manim render call.
        return _make_exec_response(exit_code=exit_code, output=combined_output)

    fake.execute.side_effect = _execute
    fake.download_files.return_value = [
        _make_download_response(path="/work/media/videos/scene/480p15/Foo.mp4", content=mp4_bytes)
    ]
    return fake


async def test_render_success_writes_mp4_and_returns_path(tmp_path, monkeypatch):
    from conceptflow import render

    # Redirect outputs to a tmp dir.
    monkeypatch.setattr(render, "_OUTPUTS_ROOT", tmp_path / "outputs")
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
        "mp4_path": str(tmp_path / "outputs" / "thread-xyz" / "video.mp4"),
    }
    written = (tmp_path / "outputs" / "thread-xyz" / "video.mp4").read_bytes()
    assert written == b"HELLO_MP4"

    # The manim command was invoked with -ql and the scene class.
    called_commands = [call.args[0] for call in fake_sandbox.execute.call_args_list]
    assert any("manim -ql scene.py Foo" in cmd for cmd in called_commands)

    # Sandbox was torn down.
    fake_modal_sb.terminate.assert_called_once()


async def test_render_selects_final_mp4_not_partial_movie_file(tmp_path, monkeypatch):
    """When `find` returns partial movie files alongside the final render,
    the final `<SceneClass>.mp4` (outside partial_movie_files) is chosen."""
    from conceptflow import render

    monkeypatch.setattr(render, "_OUTPUTS_ROOT", tmp_path / "outputs")
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


async def test_render_returns_render_error_on_nonzero_exit(tmp_path, monkeypatch):
    from conceptflow import render

    monkeypatch.setattr(render, "_OUTPUTS_ROOT", tmp_path / "outputs")
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


async def test_attempt_counter_reflects_prior_tool_calls(tmp_path, monkeypatch):
    from conceptflow import render

    monkeypatch.setattr(render, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t")
    fake_modal_sb = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", MagicMock(return_value=fake_modal_sb))
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))
    fake_sandbox = _make_fake_sandbox(exit_code=1, stderr="boom")
    monkeypatch.setattr(render, "ModalSandbox", MagicMock(return_value=fake_sandbox))

    prior = ToolMessage(content="boom", name="render_manim", tool_call_id="x1")
    other = ToolMessage(content="ok", name="write_file", tool_call_id="x2")

    state = {
        "files": {"/scene.py": {"content": "x", "encoding": "utf-8"}},
        "messages": [prior, other, prior],  # 2 prior render_manim calls
    }
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}

    result = await render.render_manim.ainvoke(
        {"scene_class": "Foo", "state": state}, config=config
    )

    assert result["attempt"] == 3


async def test_render_refuses_once_attempt_cap_exceeded(tmp_path, monkeypatch):
    """When prior render attempts hit the cap, the tool short-circuits.

    No sandbox is created and an 'exhausted' stop envelope is returned so
    the cap is enforced in code, not merely advised in the prompt.
    """
    from conceptflow import render

    monkeypatch.setattr(render, "_OUTPUTS_ROOT", tmp_path / "outputs")
    _write_scene(tmp_path / "outputs", "t")
    sandbox_create = MagicMock()
    monkeypatch.setattr(render.modal.Sandbox, "create", sandbox_create)
    monkeypatch.setattr(render.modal.App, "lookup", MagicMock(return_value=MagicMock()))

    prior = ToolMessage(content="boom", name="render_manim", tool_call_id="x")
    state = {
        "files": {"/scene.py": {"content": "x", "encoding": "utf-8"}},
        "messages": [prior, prior, prior],  # 3 prior render_manim calls (cap=3)
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


async def test_render_returns_infra_error_when_sandbox_fails_to_start(tmp_path, monkeypatch):
    from conceptflow import render

    monkeypatch.setattr(render, "_OUTPUTS_ROOT", tmp_path / "outputs")
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


async def test_thread_id_defaults_when_absent(tmp_path, monkeypatch):
    from conceptflow import render

    monkeypatch.setattr(render, "_OUTPUTS_ROOT", tmp_path / "outputs")
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
    assert "/default/" in result["mp4_path"]


async def test_render_uses_custom_settings(tmp_path, monkeypatch):
    from conceptflow import render

    monkeypatch.setenv("MODAL_APP_NAME", "custom-app-name")
    monkeypatch.setenv("MODAL_SANDBOX_TIMEOUT", "123")
    render.get_settings.cache_clear()

    monkeypatch.setattr(render, "_OUTPUTS_ROOT", tmp_path / "outputs")
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


def test_sanitize_thread_id_defaults_when_empty():
    from conceptflow.render import sanitize_thread_id

    assert sanitize_thread_id(None) == "default"
    assert sanitize_thread_id("") == "default"


def test_sanitize_thread_id_strips_path_traversal():
    from conceptflow.render import sanitize_thread_id

    # Path(...).name collapses to the basename, blocking ../ escapes.
    assert sanitize_thread_id("../../etc/passwd") == "passwd"
    # A pure traversal has an empty basename -> falls back to "default".
    assert sanitize_thread_id("../../") == "default"


def test_sanitize_thread_id_replaces_disallowed_chars_and_caps_length():
    from conceptflow.render import sanitize_thread_id

    assert sanitize_thread_id("a b/c!d") == "c_d"
    assert len(sanitize_thread_id("x" * 500)) == 128


def test_output_dir_joins_outputs_root_and_sanitizes(tmp_path, monkeypatch):
    from conceptflow import render

    monkeypatch.setattr(render, "_OUTPUTS_ROOT", tmp_path / "outputs")
    assert render.output_dir("../evil") == tmp_path / "outputs" / "evil"
    assert render.output_dir(None) == tmp_path / "outputs" / "default"
