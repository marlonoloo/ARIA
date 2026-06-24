"""Centralised configuration loaded from environment variables.

Keeping every tunable in one place makes the Lambdas easy to configure per
environment (dev / demo) and keeps magic strings out of the handlers.
"""
from __future__ import annotations

import os


class ConfigError(RuntimeError):
    """Raised when a required environment variable is missing."""


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"Required environment variable '{name}' is not set. "
            "Check the Lambda configuration."
        )
    return value


def _optional(name: str, default: str) -> str:
    return os.environ.get(name, default)


class Config:
    """Lazily-read configuration.

    Values are read on access (not at import time) so unit tests can patch
    the environment per-case without re-importing the module.
    """

    # --- Aurora (via RDS Data API) ---
    @property
    def db_cluster_arn(self) -> str:
        return _required("DB_CLUSTER_ARN")

    @property
    def db_secret_arn(self) -> str:
        return _required("DB_SECRET_ARN")

    @property
    def db_name(self) -> str:
        return _optional("DB_NAME", "aria")

    # --- Bedrock ---
    @property
    def knowledge_base_id(self) -> str:
        return _required("KB_ID")

    @property
    def model_id(self) -> str:
        # Claude 3 Sonnet by default (per the team brief). Override per env.
        return _optional("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")

    @property
    def kb_num_results(self) -> int:
        return int(_optional("KB_NUM_RESULTS", "5"))

    @property
    def max_tokens(self) -> int:
        return int(_optional("BEDROCK_MAX_TOKENS", "2000"))

    @property
    def temperature(self) -> float:
        # Low temperature: clinical content must be stable and conservative.
        return float(_optional("BEDROCK_TEMPERATURE", "0.2"))

    @property
    def region(self) -> str:
        # AWS_REGION is injected by the Lambda runtime.
        return _optional("AWS_REGION", "us-east-1")


config = Config()
