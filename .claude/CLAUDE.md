# TG Bot Creator Content

## Project Overview
AI-agent Telegram bot for content management. Accepts product names, searches the web via Tavily, generates expert posts with LLM (hallucination-protected), provides admin panel for editing/publishing/scheduling to a Telegram channel.

## Tech Stack
- **Language**: Python 3.11+
- **Bot framework**: aiogram 3.x (async, polling transport)
- **AI orchestration**: LangGraph StateGraph + LangChain
- **LLM**: Custom provider rotation system (OpenAI-compatible + Gemini) via `ProviderRouter`
  - `langchain-openai` — for OpenAI/OpenRouter/DeepSeek
  - `langchain-google-genai` + `google-generativeai` — for Google Gemini
- **Web search**: tavily-python
- **Database**: PostgreSQL + SQLAlchemy 2.0 (asyncpg) + Alembic
- **Scheduler**: APScheduler 3.x (AsyncIOScheduler)
- **Config**: Pydantic Settings from `.env`, LLM providers config in DB (JSON)
- **Infrastructure**: Docker + docker-compose

## Key File Paths
- `main.py` — entry point (bot init, polling, scheduler start)
- `config/settings.py` — all env vars via Pydantic BaseSettings
- `db/models.py` — SQLAlchemy models: AllowedChat, Setting, Post
- `db/repo.py` — Repository pattern (all DB CRUD)
- `db/engine.py` — async engine + session factory
- `services/ai/graph.py` — LangGraph pipeline (search → generate)
- `services/ai/nodes.py` — Tavily search node + LLM generate node (uses ProviderRouter)
- `services/ai/prompts.py` — default system prompt + fallback text
- `services/llm/base.py` — ABC `LLMProvider` interface (generate, reset, is_exhausted)
- `services/llm/openai_compat.py` — OpenAI/OpenRouter/DeepSeek provider (key→model rotation)
- `services/llm/gemini.py` — Gemini provider (model→key rotation)
- `services/llm/router.py` — `ProviderRouter` (priority-based provider selection + fallback)
- `services/publisher.py` — publish logic (media split, FloodWait retry)
- `services/scheduler.py` — APScheduler 3.x auto-publish cron job (AsyncIOScheduler)
- `bot/handlers/` — all aiogram routers (start, create_post, post_actions, queue, settings)
- `bot/middlewares/access.py` — AllowedChatsMiddleware (whitelist filter)
- `bot/middlewares/media_group.py` — album collection with 1.5s buffer
- `bot/keyboards/` — reply (main menu) + inline (post actions, queue nav, settings)
- `bot/states/fsm.py` — FSM states (CreatePost, EditPost, RewritePost, EditPrompt, EditSchedule)

## LLM Provider System

Custom rotation system with priority-based fallback:

- **Abstract interface** (`LLMProvider` ABC): `generate()`, `reset()`, `is_exhausted`
- **OpenAICompatibleProvider**: handles OpenAI, OpenRouter, DeepSeek. Rotation: keys first, then models (rate limits are per-key)
- **GeminiProvider**: handles Google Gemini via `google-generativeai`. Rotation: models first, then keys (Google rate-limits differently per model)
- **ProviderRouter**: manages priority-ordered list of providers. Tries next provider when current exhausted. Built from JSON config in DB via `from_config()`

**Config stored in DB** (`settings` table, key `llm_providers`) as JSON array:
```json
[
  {"name": "gemini", "type": "gemini", "models": [...], "api_keys": [...], "temperature": 0.7},
  {"name": "openrouter", "type": "openai_compatible", "base_url": "...", "models": [...], "api_keys": [...]}
]
```
Array order = priority. Can be changed via bot without restart.

## Conventions
- **Language**: Code in English, UI strings in Russian
- **Parse mode**: HTML by default
- **Post lifecycle**: pending → approved/published/editing/deleted
- **Concurrency control**: set status to `editing` + disable inline buttons before any modification
- **Text versioning**: overwrite only (no history)
- **Queue auto-publish**: silent skip when queue is empty
- **Error handling**: Tavily failure → hardcoded fallback text; LLM failure → rotate providers, then error text

## Architecture Decisions
- Layered package structure: `bot/`, `services/`, `db/`, `config/`
- Repository pattern for DB access (no raw queries in handlers)
- LangGraph for deterministic AI pipeline (search_node → generate_node)
- ProviderRouter for LLM calls inside generate_node (not langchain `with_fallbacks`)
- Single channel ID in `.env` (no multi-channel)
- Polling transport (webhook-ready architecture)
- Docker first — dev environment available from Step 0

## External Libraries — Context7

**При работе с внешними библиотеками ВСЕГДА используй context7 MCP-сервер** для получения актуальной документации и примеров кода. Перед написанием кода с использованием библиотеки:
1. Вызови `resolve-library-id` для нахождения ID библиотеки
2. Вызови `query-docs` с конкретным вопросом по API

Это обязательно для: `aiogram`, `langgraph`, `langchain`, `sqlalchemy`, `apscheduler`, `tavily-python`, `pydantic-settings`, `alembic`, `pytest-asyncio`, `langchain-google-genai`, `google-generativeai` и любых других внешних зависимостей.

## Testing
- Тестовая стратегия описана в `IMPLEMENTATION_PLAN.md` (секция «Тестовая инфраструктура»)
- Тест-раннер: `pytest` + `pytest-asyncio` (asyncio_mode=auto)
- БД в тестах: `aiosqlite` (in-memory SQLite, без PostgreSQL)
- Все внешние API (Tavily, LLM, Telegram) мокаются через `unittest.mock` / `pytest-mock`
- Общие фикстуры: `tests/conftest.py` (db_engine, db_session, repo, mock_bot, mock_tavily, mock_llm_router)
- **ВСЕ тесты должны быть зелёными (passing) — это обязательное требование**
- **Тесты обязательны после каждого шага реализации. Переход к следующему шагу запрещён при красных тестах**
- ~92 теста суммарно по всем модулям

## Documentation
- `docs/PRD_TG_Bot_Creator.md` — product requirements document
- `docs/IMPLEMENTATION_PLAN.md` — step-by-step implementation plan with decisions, tests per step, dependency graph
