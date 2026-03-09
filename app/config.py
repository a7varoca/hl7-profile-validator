from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_title: str = "HL7 v2.x Profile Editor"
    # Legacy paths — used only for one-time migration into SQLite on first startup
    profiles_dir: Path = Path("profiles")
    hl7standard_cache_dir: Path = Path("hl7standard_cache")

    model_config = {"env_file": ".env"}


settings = Settings()
