from pathlib import Path

import pytest

from src.config import Settings
from src.domain import ConfigurationError


def test_settings_load_and_convert_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("RETRIEVAL_COUNT", "7")
    monkeypatch.setenv("CHROMA_DIRECTORY", "custom-db")

    settings = Settings.from_env()

    assert settings.openai_api_key == "test-key"
    assert settings.openai_model == "test-model"
    assert settings.retrieval_count == 7
    assert settings.chroma_directory == Path("custom-db")


def test_settings_reject_invalid_chunk_overlap() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        chunk_size=100,
        chunk_overlap=100,
    )

    with pytest.raises(ConfigurationError, match="smaller than CHUNK_SIZE"):
        settings.validate()


def test_settings_reject_non_integer_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("RETRIEVAL_COUNT", "many")

    with pytest.raises(ConfigurationError, match="RETRIEVAL_COUNT must be an integer"):
        Settings.from_env()
