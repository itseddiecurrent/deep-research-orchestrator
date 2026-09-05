from __future__ import annotations

from pathlib import Path

import pytest

from research_agent.config import AppConfig, ConfigurationError, DEFAULT_OPENAI_MODEL


def test_config_requires_named_nonblank_credentials_without_exposing_values() -> None:
    with pytest.raises(ConfigurationError) as error:
        AppConfig.from_environment(
            {"OPENAI_API_KEY": "  ", "TAVILY_API_KEY": "sensitive-value"},
            dotenv_path=None,
        )

    message = str(error.value)
    assert "OPENAI_API_KEY" in message
    assert "TAVILY_API_KEY" not in message
    assert "sensitive-value" not in message


def test_config_masks_secrets_and_uses_default_model() -> None:
    config = AppConfig.from_environment(
        {
            "OPENAI_API_KEY": "openai-secret",
            "TAVILY_API_KEY": "tavily-secret",
        },
        dotenv_path=None,
    )

    assert config.openai_model == DEFAULT_OPENAI_MODEL
    assert config.openai_api_key.get_secret_value() == "openai-secret"
    rendered = repr(config)
    assert "openai-secret" not in rendered
    assert "tavily-secret" not in rendered
    assert "**********" in rendered


def test_config_loads_dotenv_and_environment_overrides_model(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "OPENAI_API_KEY=dotenv-openai\n"
        "TAVILY_API_KEY=dotenv-tavily\n"
        "OPENAI_MODEL=dotenv-model\n",
        encoding="utf-8",
    )

    config = AppConfig.from_environment(
        {"OPENAI_MODEL": "environment-model"}, dotenv_path=dotenv_path
    )

    assert config.openai_api_key.get_secret_value() == "dotenv-openai"
    assert config.tavily_api_key.get_secret_value() == "dotenv-tavily"
    assert config.openai_model == "environment-model"


def test_config_rejects_blank_model_override() -> None:
    with pytest.raises(ConfigurationError, match="OPENAI_MODEL"):
        AppConfig.from_environment(
            {
                "OPENAI_API_KEY": "openai-secret",
                "TAVILY_API_KEY": "tavily-secret",
                "OPENAI_MODEL": "  ",
            },
            dotenv_path=None,
        )
