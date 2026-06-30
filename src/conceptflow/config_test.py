"""Tests for the Settings object and model builders."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.language_models import BaseChatModel
from pydantic import ValidationError

from conceptflow.config import (
    Settings,
    get_model,
    get_model_small,
    load_environment,
)


def test_default_modal_settings() -> None:
    """modal_app_name and modal_sandbox_timeout have sensible defaults."""
    s = Settings(_env_file=None)  # type: ignore
    assert s.modal_app_name == "conceptflow"
    assert s.modal_sandbox_timeout == 60 * 30


def test_modal_settings_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both settings can be overridden via environment variables."""
    monkeypatch.setenv("MODAL_APP_NAME", "custom-app")
    monkeypatch.setenv("MODAL_SANDBOX_TIMEOUT", "120")
    s = Settings(_env_file=None)  # type: ignore
    assert s.modal_app_name == "custom-app"
    assert s.modal_sandbox_timeout == 120


def test_default_max_render_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_render_attempts defaults to 3 (the historical advisory cap)."""
    monkeypatch.delenv("MAX_RENDER_ATTEMPTS", raising=False)
    s = Settings(_env_file=None)  # type: ignore
    assert s.max_render_attempts == 3


def test_max_render_attempts_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_render_attempts can be overridden via the MAX_RENDER_ATTEMPTS env var."""
    monkeypatch.setenv("MAX_RENDER_ATTEMPTS", "5")
    s = Settings(_env_file=None)  # type: ignore
    assert s.max_render_attempts == 5


def test_max_render_attempts_invalid_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 0 is rejected for Settings.max_render_attempts.

    Like test_default_max_render_attempts and
    test_max_render_attempts_overridable_via_env, this tests validation constraints
    on Settings.max_render_attempts.
    """
    monkeypatch.setenv("MAX_RENDER_ATTEMPTS", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore


def test_max_render_attempts_invalid_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a negative value is rejected for Settings.max_render_attempts.

    Like test_default_max_render_attempts and
    test_max_render_attempts_overridable_via_env, this tests validation constraints
    on Settings.max_render_attempts.
    """
    monkeypatch.setenv("MAX_RENDER_ATTEMPTS", "-1")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore


def test_default_model_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Primary and small model identifiers have sensible defaults."""
    monkeypatch.delenv("MODEL", raising=False)
    monkeypatch.delenv("MODEL_SMALL", raising=False)
    s = Settings(_env_file=None)  # type: ignore
    assert s.model == "anthropic:claude-sonnet-4-5-20250929"
    assert s.model_small == "anthropic:claude-3-5-sonnet-20241022"


def test_model_small_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """model_small can be overridden via the MODEL_SMALL env var."""
    monkeypatch.setenv("MODEL_SMALL", "anthropic:claude-3-haiku-20240307")
    s = Settings(_env_file=None)  # type: ignore
    assert s.model_small == "anthropic:claude-3-haiku-20240307"


def test_default_retry_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """ModelRetryMiddleware tuning knobs have sensible defaults."""
    monkeypatch.delenv("RETRY_MAX_RETRIES", raising=False)
    monkeypatch.delenv("RETRY_BACKOFF_FACTOR", raising=False)
    monkeypatch.delenv("RETRY_INITIAL_DELAY", raising=False)
    s = Settings(_env_file=None)  # type: ignore
    assert s.retry_max_retries == 5
    assert s.retry_backoff_factor == 2.0
    assert s.retry_initial_delay == 5.0


def test_retry_settings_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """All three retry settings can be overridden via environment variables."""
    monkeypatch.setenv("RETRY_MAX_RETRIES", "10")
    monkeypatch.setenv("RETRY_BACKOFF_FACTOR", "3.5")
    monkeypatch.setenv("RETRY_INITIAL_DELAY", "1.25")
    s = Settings(_env_file=None)  # type: ignore
    assert s.retry_max_retries == 10
    assert s.retry_backoff_factor == 3.5
    assert s.retry_initial_delay == 1.25


def test_get_model_uses_primary_model_id() -> None:
    """get_model() forwards the Settings.model id to init_chat_model."""
    s = Settings(_env_file=None, model="anthropic:test-primary")  # type: ignore
    with patch("conceptflow.config.init_chat_model") as mock_init:
        mock_init.return_value = object()
        get_model(s)
    assert mock_init.call_args.kwargs["model"] == "anthropic:test-primary"


def test_get_model_small_uses_small_model_id() -> None:
    """get_model_small() forwards the Settings.model_small id to init_chat_model."""
    s = Settings(_env_file=None, model_small="anthropic:test-small")  # type: ignore
    with patch("conceptflow.config.init_chat_model") as mock_init:
        mock_init.return_value = object()
        get_model_small(s)
    assert mock_init.call_args.kwargs["model"] == "anthropic:test-small"


def test_get_model_falls_back_to_get_settings_when_none() -> None:
    """When called with no arg, get_model() resolves Settings via get_settings()."""
    fake = Settings(_env_file=None, model="anthropic:from-cache")  # type: ignore
    with (
        patch("conceptflow.config.get_settings", return_value=fake) as mock_get_settings,
        patch("conceptflow.config.init_chat_model") as mock_init,
    ):
        mock_init.return_value = object()
        get_model()
    mock_get_settings.assert_called_once()
    assert mock_init.call_args.kwargs["model"] == "anthropic:from-cache"


def test_get_model_small_falls_back_to_get_settings_when_none() -> None:
    """When called with no arg, get_model_small() resolves Settings via get_settings()."""
    fake = Settings(_env_file=None, model_small="anthropic:small-from-cache")  # type: ignore
    with (
        patch("conceptflow.config.get_settings", return_value=fake) as mock_get_settings,
        patch("conceptflow.config.init_chat_model") as mock_init,
    ):
        mock_init.return_value = object()
        get_model_small()
    mock_get_settings.assert_called_once()
    assert mock_init.call_args.kwargs["model"] == "anthropic:small-from-cache"


def test_get_model_returns_base_chat_model_subclass() -> None:
    """The factory returns the object init_chat_model produced."""
    s = Settings(_env_file=None)  # type: ignore
    sentinel = type("FakeModel", (BaseChatModel,), {})
    with patch("conceptflow.config.init_chat_model", return_value=sentinel):
        assert get_model(s) is sentinel


def test_load_environment_os_env_beats_local_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """OS env wins over ./.env."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-os")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-local\n")
    monkeypatch.setattr("conceptflow.config._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "no-home"))

    load_environment()

    assert os.environ["ANTHROPIC_API_KEY"] == "from-os"


def test_load_environment_local_dotenv_beats_user_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """./.env wins over ~/.config/conceptflow/config.env when OS env is unset."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-local\n")
    home = tmp_path / "home"
    user_cfg = home / ".config" / "conceptflow"
    user_cfg.mkdir(parents=True)
    (user_cfg / "config.env").write_text("ANTHROPIC_API_KEY=from-user\n")
    monkeypatch.setattr("conceptflow.config._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    load_environment()

    assert os.environ["ANTHROPIC_API_KEY"] == "from-local"


def test_load_environment_user_config_fills_when_no_local_or_os(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """~/.config/conceptflow/config.env is consulted when nothing else sets the key."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    home = tmp_path / "home"
    user_cfg = home / ".config" / "conceptflow"
    user_cfg.mkdir(parents=True)
    (user_cfg / "config.env").write_text("OPENAI_API_KEY=from-user\n")
    monkeypatch.setattr("conceptflow.config._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    load_environment()

    assert os.environ["OPENAI_API_KEY"] == "from-user"


def test_load_environment_tolerates_missing_user_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No user-config file is fine; no error raised."""
    monkeypatch.setattr("conceptflow.config._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "no-home"))

    load_environment()  # must not raise


def test_default_tts_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """tts_service defaults to gtts."""
    monkeypatch.delenv("TTS_SERVICE", raising=False)
    s = Settings(_env_file=None)  # type: ignore
    assert s.tts_service == "gtts"


def test_tts_service_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """tts_service can be set to pyttsx3 via the TTS_SERVICE env var."""
    monkeypatch.setenv("TTS_SERVICE", "pyttsx3")
    s = Settings(_env_file=None)  # type: ignore
    assert s.tts_service == "pyttsx3"


def test_tts_service_rejects_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unrecognised TTS_SERVICE value is rejected."""
    monkeypatch.setenv("TTS_SERVICE", "elevenlabs")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore


def test_default_max_qa_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_qa_rounds defaults to 2."""
    monkeypatch.delenv("MAX_QA_ROUNDS", raising=False)
    s = Settings(_env_file=None)  # type: ignore
    assert s.max_qa_rounds == 2


def test_max_qa_rounds_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_qa_rounds can be overridden via the MAX_QA_ROUNDS env var."""
    monkeypatch.setenv("MAX_QA_ROUNDS", "4")
    s = Settings(_env_file=None)  # type: ignore
    assert s.max_qa_rounds == 4


def test_max_qa_rounds_rejects_non_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_qa_rounds must be > 0."""
    monkeypatch.setenv("MAX_QA_ROUNDS", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore


def test_qa_model_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """qa_model is unset by default (falls back to the main model)."""
    monkeypatch.delenv("QA_MODEL", raising=False)
    s = Settings(_env_file=None)  # type: ignore
    assert s.qa_model is None


def test_get_qa_model_falls_back_to_main_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """When qa_model is unset, get_qa_model builds the main model id."""
    from conceptflow import config

    captured: dict[str, str] = {}

    def fake_build(settings: Settings, model_id: str) -> object:
        captured["model_id"] = model_id
        return object()

    monkeypatch.setattr(config, "_build_model", fake_build)
    s = Settings(_env_file=None, model="anthropic:main", qa_model=None)  # type: ignore
    config.get_qa_model(s)
    assert captured["model_id"] == "anthropic:main"


def test_get_qa_model_uses_override_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """When qa_model is set, get_qa_model builds that id instead."""
    from conceptflow import config

    captured: dict[str, str] = {}

    def fake_build(settings: Settings, model_id: str) -> object:
        captured["model_id"] = model_id
        return object()

    monkeypatch.setattr(config, "_build_model", fake_build)
    s = Settings(_env_file=None, model="anthropic:main", qa_model="openai:vision")  # type: ignore
    config.get_qa_model(s)
    assert captured["model_id"] == "openai:vision"


def test_default_max_research_searches(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_research_searches defaults to 5."""
    monkeypatch.delenv("MAX_RESEARCH_SEARCHES", raising=False)
    s = Settings(_env_file=None)  # type: ignore
    assert s.max_research_searches == 5


def test_max_research_searches_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_research_searches can be overridden via the env var."""
    monkeypatch.setenv("MAX_RESEARCH_SEARCHES", "8")
    s = Settings(_env_file=None)  # type: ignore
    assert s.max_research_searches == 8


def test_max_research_searches_rejects_non_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_research_searches must be > 0."""
    monkeypatch.setenv("MAX_RESEARCH_SEARCHES", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore


def test_default_wikipedia_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """wikipedia_user_agent defaults to an impersonal app/version identifier."""
    from importlib.metadata import version

    monkeypatch.delenv("WIKIPEDIA_USER_AGENT", raising=False)
    s = Settings(_env_file=None)  # type: ignore
    assert s.wikipedia_user_agent == f"ConceptFlow/{version('conceptflow')}"


def test_wikipedia_user_agent_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """wikipedia_user_agent can be overridden via the env var."""
    monkeypatch.setenv("WIKIPEDIA_USER_AGENT", "MyApp/2.0 (me@example.com)")
    s = Settings(_env_file=None)  # type: ignore
    assert s.wikipedia_user_agent == "MyApp/2.0 (me@example.com)"


def test_research_model_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """research_model is unset by default (falls back to the main model)."""
    monkeypatch.delenv("RESEARCH_MODEL", raising=False)
    s = Settings(_env_file=None)  # type: ignore
    assert s.research_model is None


def test_get_research_model_falls_back_to_main_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """When research_model is unset, get_research_model builds the main model id."""
    from conceptflow import config

    captured: dict[str, str] = {}

    def fake_build(settings: Settings, model_id: str) -> object:
        captured["model_id"] = model_id
        return object()

    monkeypatch.setattr(config, "_build_model", fake_build)
    s = Settings(_env_file=None, model="anthropic:main", research_model=None)  # type: ignore
    config.get_research_model(s)
    assert captured["model_id"] == "anthropic:main"


def test_get_research_model_uses_override_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """When research_model is set, get_research_model builds that id instead."""
    from conceptflow import config

    captured: dict[str, str] = {}

    def fake_build(settings: Settings, model_id: str) -> object:
        captured["model_id"] = model_id
        return object()

    monkeypatch.setattr(config, "_build_model", fake_build)
    s = Settings(_env_file=None, model="anthropic:main", research_model="openai:cheap")  # type: ignore
    config.get_research_model(s)
    assert captured["model_id"] == "openai:cheap"
