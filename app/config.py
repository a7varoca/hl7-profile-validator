from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_title: str = "HL7 v2.x Profile Editor"
    profiles_dir: Path = Path("profiles")

    model_config = {"env_file": ".env"}

    def model_post_init(self, __context):
        self.profiles_dir.mkdir(exist_ok=True)


settings = Settings()
