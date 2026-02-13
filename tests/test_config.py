import pytest
from pydantic import ValidationError

from config.settings import Settings


class TestSettings:
    def test_settings_from_env(self, monkeypatch):
        monkeypatch.setenv("BOT_TOKEN", "123:ABC")
        monkeypatch.setenv("CHANNEL_ID", "-1001234567890")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-xxx")

        s = Settings(_env_file=None)

        assert s.bot_token == "123:ABC"
        assert s.channel_id == -1001234567890
        assert s.database_url == "postgresql+asyncpg://u:p@localhost/db"
        assert s.tavily_api_key == "tvly-xxx"

    def test_settings_defaults(self, monkeypatch):
        monkeypatch.setenv("BOT_TOKEN", "123:ABC")
        monkeypatch.setenv("CHANNEL_ID", "-100123")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")

        s = Settings(_env_file=None)

        assert s.timezone == "Europe/Moscow"
        assert s.default_cron == "0 9 * * *"
        assert s.tavily_api_key == ""
        assert s.testing is False

    def test_settings_missing_required(self, monkeypatch):
        monkeypatch.delenv("BOT_TOKEN", raising=False)
        monkeypatch.delenv("CHANNEL_ID", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        with pytest.raises(ValidationError):
            Settings(_env_file=None)
