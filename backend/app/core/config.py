from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration from environment variables (or a local .env file, never committed)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Daily Spend API"
    environment: str = Field(default="development", description="development | test | production")
    database_url: str = "postgresql+psycopg://dailyspend:dailyspend@localhost:5432/dailyspend"
    jwt_secret: str = Field(default="", description="Required. Long random string.")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24 * 30
    cors_origins: list[str] = []
    log_level: str = "INFO"
    sync_max_batch: int = 2000
    # OAuth client ids whose Google ID tokens are accepted (comma separated). The app's
    # *Web* client id is the audience of tokens it gets from Google Sign-In on Android.
    google_client_ids: str = ""
    # Pro by UPI: where payments go and what they cost (paise). Empty UPI id = Pro can't be bought.
    pro_upi_id: str = ""
    pro_upi_name: str = "MyExpenses"
    pro_price_monthly_minor: int = 4900
    pro_price_yearly_minor: int = 39900

    @property
    def google_audiences(self) -> list[str]:
        return [c.strip() for c in self.google_client_ids.split(",") if c.strip()]

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3(cls, v: str) -> str:
        """Hosts like Render hand out postgres:// or postgresql:// URLs; this app uses the psycopg (v3) driver."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix) :]
        return v

    def validate_for_runtime(self) -> None:
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be set to a random string of at least 32 characters.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
