from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    channel_id: int
    database_url: str
    tavily_api_key: str = ""
    timezone: str = "Europe/Moscow"
    default_cron: str = "0 9 * * *"
    testing: bool = False


def get_settings() -> Settings:
    return Settings()
