"""Application configuration.

All runtime config is loaded from environment variables via pydantic-settings.
Never read os.environ directly elsewhere — go through `settings`.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, cast

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class LogFormat(StrEnum):
    JSON = "json"
    CONSOLE = "console"


class Settings(BaseSettings):
    """Top-level settings. Sub-namespaces are flattened for env-var simplicity."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Runtime ---------------------------------------------------------
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON

    # ---- API -------------------------------------------------------------
    api_host: str = "0.0.0.0"  # noqa: S104 — intentional in container
    api_port: int = 8000
    api_workers: int = 4
    api_cors_origins: list[AnyHttpUrl] | list[str] = Field(default_factory=list)
    api_secret_key: SecretStr = SecretStr("change-me")
    api_access_token_ttl_minutes: int = 60
    api_refresh_token_ttl_days: int = 14

    # ---- Database --------------------------------------------------------
    database_url: PostgresDsn
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    # ---- Redis / Celery --------------------------------------------------
    redis_url: RedisDsn
    celery_broker_url: RedisDsn
    celery_result_backend: RedisDsn

    # ---- Object storage --------------------------------------------------
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key: SecretStr
    s3_secret_key: SecretStr
    s3_bucket_uploads: str = "tcvn-uploads"
    s3_bucket_reports: str = "tcvn-reports"

    # ---- LLM (OSS, OpenAI-compatible) -----------------------------------
    # Defaults: Ollama on localhost serving Qwen 2.5. For production swap to
    # vLLM / SGLang on a GPU node and point `llm_base_url` at the gateway.
    llm_base_url: AnyHttpUrl = cast(AnyHttpUrl, "http://localhost:11434/v1")
    llm_api_key: SecretStr | None = None
    # 7b is the CPU/laptop dev default; production GPU should override to
    # qwen2.5:32b-instruct via the LLM_REASONING_MODEL env var.
    llm_reasoning_model: str = "qwen2.5:7b-instruct"
    llm_extraction_model: str = "qwen2.5:7b-instruct"
    llm_max_output_tokens: int = 8192
    llm_request_timeout_seconds: float = 120.0

    # ---- RAG -------------------------------------------------------------
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    rag_top_k: int = 8
    rag_rerank_top_n: int = 20
    rag_chunk_size_tokens: int = 512
    rag_chunk_overlap_tokens: int = 64

    # ---- OCR -------------------------------------------------------------
    tesseract_lang: str = "vie+eng"
    ocr_dpi: int = 300

    # ---- Observability ---------------------------------------------------
    sentry_dsn: str | None = None
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "tcvn-copilot-api"
    prometheus_metrics_enabled: bool = True

    # ---- Retention -------------------------------------------------------
    upload_retention_days: int = 30
    report_retention_days: int = 365

    # ---- Corpus location -------------------------------------------------
    standards_corpus_path: str = "/app/standards-corpus"

    # ---- Validators ------------------------------------------------------
    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def is_test(self) -> bool:
        return self.environment is Environment.TEST


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton.

    Tests override this via FastAPI's dependency overrides, *not* by clearing
    the cache directly — that way config behaves predictably across imports.
    """
    return Settings()  # all fields read from env


SettingsDep = Annotated[Settings, "settings"]
