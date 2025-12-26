"""Application configuration using pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """OLLIE configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    openweathermap_api_key: str = ""
    newsapi_key: str = ""
    aeroapi_key: str = ""
    openrouteservice_api_key: str = ""
    spoonacular_api_key: str = ""
    anthropic_api_key: str = ""
    opensky_username: str = ""
    opensky_password: str = ""

    # Location defaults
    default_location: str = "Edgewood, WA"
    default_lat: float = 47.2540
    default_lon: float = -122.2937

    # LLM Settings
    llm_model_path: Path = Path("./models/phi-3-mini-4k-instruct-q4.gguf")
    llm_context_size: int = 2048
    llm_max_tokens: int = 256

    # For text-mode prototype, we can use a mock LLM
    use_mock_llm: bool = True


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
