import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from db.repo import Repository
from main import _seed_defaults, _build_llm_router, build_app


class TestSeedDefaults:
    async def test_seeds_when_empty(self):
        """Seeds all 3 default settings when none exist."""
        repo = AsyncMock()
        repo.get_setting.return_value = None

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.return_value = session

        with patch("main.Repository", return_value=repo):
            await _seed_defaults(factory)

        assert repo.set_setting.call_count == 3
        keys_set = [call[0][0] for call in repo.set_setting.call_args_list]
        assert "system_prompt" in keys_set
        assert "cron_schedule" in keys_set
        assert "llm_providers" in keys_set

    async def test_does_not_overwrite_existing(self):
        """Does not overwrite settings that already exist."""
        repo = AsyncMock()
        repo.get_setting.return_value = "existing_value"

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.return_value = session

        with patch("main.Repository", return_value=repo):
            await _seed_defaults(factory)

        repo.set_setting.assert_not_called()


class TestBuildLLMRouter:
    def test_empty_config_returns_none(self):
        assert _build_llm_router("[]") is None

    def test_invalid_json_returns_none(self):
        assert _build_llm_router("not json") is None

    def test_valid_config_returns_router(self):
        import json
        config = json.dumps([
            {
                "name": "gemini",
                "type": "gemini",
                "models": ["gemini-2.0-flash"],
                "api_keys": ["AIza-key1"],
            }
        ])
        router = _build_llm_router(config)
        assert router is not None
        assert len(router.providers) == 1


class TestBuildApp:
    @patch("main.create_scheduler")
    @patch("main.Bot")
    @patch("main._seed_defaults")
    @patch("main.build_session_factory")
    @patch("main.build_engine")
    async def test_startup_sequence(
        self, mock_engine_fn, mock_sf_fn, mock_seed, mock_bot_cls, mock_sched_fn
    ):
        """build_app creates all components in correct order."""
        # Mock engine
        mock_engine = MagicMock()
        mock_engine_fn.return_value = mock_engine

        # Mock session factory
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        mock_sf = MagicMock()
        mock_sf.return_value = session
        mock_sf_fn.return_value = mock_sf

        # Mock repo inside build_app's DB read
        repo = AsyncMock()
        repo.get_setting.return_value = None

        # Mock scheduler
        mock_scheduler = MagicMock()
        mock_sched_fn.return_value = mock_scheduler

        # Mock bot
        mock_bot = MagicMock()
        mock_bot_cls.return_value = mock_bot

        cfg = MagicMock()
        cfg.bot_token = "test:token"
        cfg.channel_id = -100123
        cfg.database_url = "sqlite+aiosqlite:///:memory:"
        cfg.tavily_api_key = "tvly-test"
        cfg.default_cron = "0 9 * * *"

        with patch("main.Repository", return_value=repo):
            dp, bot, scheduler, engine = await build_app(cfg)

        # Verify order
        mock_engine_fn.assert_called_once_with(cfg.database_url)
        mock_sf_fn.assert_called_once_with(mock_engine)
        mock_seed.assert_called_once()
        mock_sched_fn.assert_called_once()
        assert scheduler == mock_scheduler
        assert engine == mock_engine

    async def test_smoke_seed_defaults_in_memory(self):
        """Smoke test: _seed_defaults with real in-memory SQLite writes correct keys."""
        from db.models import Base
        from db.engine import build_engine, build_session_factory

        engine = build_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = build_session_factory(engine)
        await _seed_defaults(session_factory)

        # Verify all defaults are written
        async with session_factory() as session:
            repo = Repository(session)
            assert await repo.get_setting("system_prompt") is not None
            assert await repo.get_setting("cron_schedule") == "0 9 * * *"
            assert await repo.get_setting("llm_providers") == "[]"

        await engine.dispose()
