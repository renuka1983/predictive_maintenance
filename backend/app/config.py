"""Application settings loaded from the environment."""

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Values come from environment variables (or a local ``.env`` file) so the
    same image can run against local Docker Postgres and a managed cloud
    database without code changes.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Application -----------------------------------------------------
    app_name: str = "Manufacturing AI SaaS"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    debug: bool = True

    # --- Database --------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/manufacturing_ai"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800
    db_echo: bool = False

    # --- Security --------------------------------------------------------
    secret_key: str = "change-me-in-production"
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # --- Maturity thresholds --------------------------------------------
    # Minimum record counts required before a data domain is considered
    # "established" for the purposes of maturity scoring.
    min_maintenance_records: int = 50
    min_production_batches: int = 50
    min_sensor_readings: int = 500
    min_sensor_machine_coverage: float = 0.5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        """Allow CORS origins to be supplied as a comma separated string."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()


settings = get_settings()
