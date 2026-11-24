"""Settings read from the environment."""

import os
from collections.abc import Mapping

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    """Keys, model choices and run limits of the web app."""

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    decompose_model: str = "claude-opus-5-5"
    decompose_effort: str = "high"
    verify_model: str = "claude-sonnet-5-5"
    verify_effort: str = "high"
    review_model: str = "gpt-6-sol"
    access_code: str | None = None
    daily_run_cap: int = 50


_ENV_NAMES = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "decompose_model": "FC_DECOMPOSE_MODEL",
    "decompose_effort": "FC_DECOMPOSE_EFFORT",
    "verify_model": "FC_VERIFY_MODEL",
    "verify_effort": "FC_VERIFY_EFFORT",
    "review_model": "FC_REVIEW_MODEL",
    "access_code": "FC_ACCESS_CODE",
    "daily_run_cap": "FC_DAILY_RUN_CAP",
}


def load_settings(env: Mapping[str, str]) -> Settings:
    """Build Settings from `env`; unset or empty names keep their defaults."""
    values = {field: env[name] for field, name in _ENV_NAMES.items() if env.get(name)}
    return Settings.model_validate(values)


def settings_from_environment() -> Settings:
    """Load `.env` if present, then build Settings from os.environ."""
    load_dotenv()
    return load_settings(os.environ)
