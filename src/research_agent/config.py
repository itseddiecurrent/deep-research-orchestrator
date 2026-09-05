"""Secret-safe environment configuration for live research adapters."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional

from dotenv import dotenv_values
from pydantic import SecretStr

from research_agent.models import NonEmptyStr, StrictModel


DEFAULT_OPENAI_MODEL = "gpt-5-mini"


class ConfigurationError(ValueError):
    pass


class AppConfig(StrictModel):
    openai_api_key: SecretStr
    tavily_api_key: SecretStr
    openai_model: NonEmptyStr = DEFAULT_OPENAI_MODEL

    @classmethod
    def from_environment(
        cls,
        environ: Optional[Mapping[str, str]] = None,
        *,
        dotenv_path: Optional[Path] = Path(".env"),
    ) -> "AppConfig":
        values: dict[str, str] = {}
        if dotenv_path is not None and dotenv_path.is_file():
            values.update(
                {
                    key: value
                    for key, value in dotenv_values(dotenv_path).items()
                    if isinstance(value, str)
                }
            )
        values.update(dict(os.environ if environ is None else environ))

        required = ("OPENAI_API_KEY", "TAVILY_API_KEY")
        missing = [name for name in required if not values.get(name, "").strip()]
        if missing:
            raise ConfigurationError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        model = values.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip()
        if not model:
            raise ConfigurationError("OPENAI_MODEL cannot be blank")
        return cls(
            openai_api_key=SecretStr(values["OPENAI_API_KEY"].strip()),
            tavily_api_key=SecretStr(values["TAVILY_API_KEY"].strip()),
            openai_model=model,
        )
