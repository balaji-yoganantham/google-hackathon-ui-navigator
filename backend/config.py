"""Application configuration from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google / Gemini
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Vertex AI (when USE_VERTEX_AI=true)
    USE_VERTEX_AI: bool = False
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"

    # Server
    BACKEND_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:5173"

    # Agent behavior
    SINGLE_MODEL_REQUEST_MODE: bool = True

    @property
    def google_api_key_set(self) -> bool:
        return bool(self.GOOGLE_API_KEY)


settings = Settings()
