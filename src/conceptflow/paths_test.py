"""Unit tests for the workspace-path helpers in `conceptflow.paths`."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig


def test_sanitize_thread_id_defaults_when_empty() -> None:
    from conceptflow.paths import sanitize_thread_id

    assert sanitize_thread_id(None) == "default"
    assert sanitize_thread_id("") == "default"


def test_sanitize_thread_id_strips_path_traversal() -> None:
    from conceptflow.paths import sanitize_thread_id

    # Path(...).name collapses to the basename, blocking ../ escapes.
    assert sanitize_thread_id("../../etc/passwd") == "passwd"
    # A pure traversal has an empty basename -> falls back to "default".
    assert sanitize_thread_id("../../") == "default"


def test_sanitize_thread_id_replaces_disallowed_chars_and_caps_length() -> None:
    from conceptflow.paths import sanitize_thread_id

    assert sanitize_thread_id("a b/c!d") == "c_d"
    assert len(sanitize_thread_id("x" * 500)) == 128


def test_output_dir_joins_outputs_root_and_sanitizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    assert paths.output_dir("../evil") == tmp_path / "outputs" / "evil"
    assert paths.output_dir(None) == tmp_path / "outputs" / "default"


def test_out_dir_from_config_uses_thread_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    config: RunnableConfig = {"configurable": {"thread_id": "abc"}}
    assert paths.out_dir_from_config(config) == tmp_path / "outputs" / "abc"


def test_out_dir_from_config_defaults_when_config_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    assert paths.out_dir_from_config(None) == tmp_path / "outputs" / "default"


def test_out_dir_from_config_defaults_when_thread_id_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    assert paths.out_dir_from_config({}) == tmp_path / "outputs" / "default"
    assert paths.out_dir_from_config({"configurable": {}}) == tmp_path / "outputs" / "default"


def test_out_dir_from_config_sanitizes_traversal_in_thread_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conceptflow import paths

    monkeypatch.setattr(paths, "_OUTPUTS_ROOT", tmp_path / "outputs")
    config: RunnableConfig = {"configurable": {"thread_id": "../../etc/passwd"}}
    # The path traversal is stripped to its basename; the helper does not
    # allow escape from _OUTPUTS_ROOT.
    result: Path = paths.out_dir_from_config(config)
    assert result == tmp_path / "outputs" / "passwd"
    assert tmp_path / "outputs" in result.parents
