from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    bot_token: str
    database_url: str = "sqlite+aiosqlite:///./hogar.db"
    scheduler_db_url: str = "sqlite:///./jobs.sqlite"
    timezone: str = "America/Mexico_City"
    authorized_user_ids: List[int] = []

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
