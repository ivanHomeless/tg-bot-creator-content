# Plan: AI-Agent Telegram Bot for Content Management

## Context

Автономный Telegram-бот — контент-менеджер для канала. Принимает название товара, ищет характеристики через Tavily, генерирует экспертный пост через LLM (с защитой от галлюцинаций), предоставляет админку для редактирования, немедленной публикации или планирования. PRD: `docs/PRD_TG_Bot_Creator.md`.

## Принципы плана

1. **Docker first** — dev-окружение (PostgreSQL + бот) доступно с первого шага
2. **Тесты обязательны** — каждый шаг заканчивается зелёными тестами. Переход к следующему шагу запрещён при красных тестах
3. **Своя система ротации LLM** — интерфейс `LLMProvider` + реализации (OpenAI-compatible, Gemini) + `ProviderRouter` с приоритетами

## Ключевые решения

| Тема | Решение |
|------|---------|
| LLM-провайдеры | Стратегия ротации: модели → ключи → следующий провайдер. Конфиг в БД (JSON) |
| Gemini SDK | `google-generativeai` (официальный SDK) |
| Gemini ротация | Сначала модели (разные лимиты), потом ключи |
| OpenAI-compat ротация | Сначала ключи (лимиты per-key), потом модели |
| Конфиг провайдеров | JSON в таблице `settings` (ключ `llm_providers`), без рестарта |
| Оркестрация AI | LangGraph StateGraph, провайдерская логика поверх через ProviderRouter |
| Медиагруппы | MediaGroupMiddleware (~1.5с буфер) |
| Целевой канал | Один `CHANNEL_ID` в `.env` |
| APScheduler | 3.x (AsyncIOScheduler) |
| Группы vs ЛС | Ответ туда, откуда запрос |
| Пагинация очереди | Редактирование того же сообщения |
| Пустая очередь по крону | Тихий пропуск |
| Конкурентность | Блокировка кнопок + статус `editing` |
| Редактирование промпта | Полная замена (склейка сообщений + .txt) |
| Rate limits | FloodWait retry с backoff |
| Поиск Tavily | Сырой пользовательский ввод |
| Parse mode | HTML по умолчанию |
| Транспорт | Polling (готово к webhook) |
| Версионирование текста | Только последняя версия |
| Тестирование | pytest + pytest-asyncio, aiosqlite in-memory, моки всех внешних API |

---

## Структура проекта

```
tg-bot-creator-content/
├── bot/
│   ├── __init__.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py            # /start, main menu
│   │   ├── create_post.py      # «Создать пост» + FSM
│   │   ├── post_actions.py     # Inline callbacks (publish, schedule, edit, rewrite, delete)
│   │   ├── queue.py            # «Очередь» — пагинированный список
│   │   └── settings.py         # Настройки (промпт, крон, провайдеры)
│   ├── middlewares/
│   │   ├── __init__.py
│   │   ├── access.py           # AllowedChatsMiddleware
│   │   └── media_group.py      # MediaGroupMiddleware (альбомы)
│   ├── keyboards/
│   │   ├── __init__.py
│   │   ├── reply.py            # ReplyKeyboardMarkup (3 кнопки)
│   │   └── inline.py           # Inline keyboards (действия, навигация, настройки)
│   ├── states/
│   │   ├── __init__.py
│   │   └── fsm.py              # FSM StatesGroups
│   └── filters/
│       ├── __init__.py
│       └── chat_type.py        # Фильтр DM vs group
├── services/
│   ├── __init__.py
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── graph.py            # LangGraph StateGraph
│   │   ├── nodes.py            # search_node (Tavily), generate_node (ProviderRouter)
│   │   └── prompts.py          # Промпты и фолбэк-тексты
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py             # ABC LLMProvider
│   │   ├── openai_compat.py    # OpenAI/OpenRouter/DeepSeek
│   │   ├── gemini.py           # Google Gemini (model→key ротация)
│   │   └── router.py           # ProviderRouter (приоритетный список)
│   ├── scheduler.py            # APScheduler 3.x (AsyncIOScheduler)
│   └── publisher.py            # Публикация в канал (медиа + текст)
├── db/
│   ├── __init__.py
│   ├── models.py               # SQLAlchemy 2.0 models
│   ├── engine.py               # async engine + session factory
│   └── repo.py                 # Repository (CRUD)
├── config/
│   ├── __init__.py
│   └── settings.py             # Pydantic Settings (.env)
├── alembic/
│   ├── env.py
│   └── versions/
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Общие фикстуры
│   ├── test_config.py
│   ├── test_db/
│   │   ├── __init__.py
│   │   ├── test_models.py
│   │   └── test_repo.py
│   ├── test_services/
│   │   ├── __init__.py
│   │   ├── test_llm/
│   │   │   ├── __init__.py
│   │   │   ├── test_base.py
│   │   │   ├── test_openai_compat.py
│   │   │   ├── test_gemini.py
│   │   │   └── test_router.py
│   │   ├── test_ai_graph.py
│   │   ├── test_publisher.py
│   │   └── test_scheduler.py
│   └── test_bot/
│       ├── __init__.py
│       ├── test_middlewares.py
│       └── test_handlers.py
├── main.py
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── alembic.ini
└── pytest.ini
```

---

## Тестовая инфраструктура

### Инструменты

| Компонент | Подход |
|-----------|--------|
| Тест-раннер | `pytest` + `pytest-asyncio` (asyncio_mode=auto) |
| БД | `aiosqlite` in-memory, `Base.metadata.create_all` в фикстуре |
| Telegram Bot API | `AsyncMock` для `Bot`, `Message`, `CallbackQuery` |
| Tavily | `unittest.mock.patch` на `TavilyClient.search` |
| LLM (OpenAI) | `AsyncMock` на `ChatOpenAI.ainvoke` |
| LLM (Gemini) | `AsyncMock` на `ChatGoogleGenerativeAI.ainvoke` |
| APScheduler | Мок scheduler, тест job-функций напрямую |
| FSM | `FSMContext` с `MemoryStorage` в фикстурах |

### Общие фикстуры (`tests/conftest.py`)

```python
@pytest.fixture
async def db_engine():
    """In-memory SQLite engine с созданными таблицами."""

@pytest.fixture
async def db_session(db_engine):
    """Async session с авто-rollback после каждого теста."""

@pytest.fixture
def repo(db_session):
    """Экземпляр Repository."""

@pytest.fixture
def mock_bot():
    """AsyncMock бот с send_message, send_photo, send_media_group."""

@pytest.fixture
def mock_tavily():
    """Patched TavilyClient с фиксированными результатами."""

@pytest.fixture
def mock_llm_router():
    """ProviderRouter с одним мок-провайдером."""
```

### Ожидаемое количество тестов

| Шаг | Модуль | Тестов |
|-----|--------|--------|
| 0 | Config | ~3 |
| 1 | Models | ~6 |
| 2 | Repository | ~14 |
| 3 | LLM Providers | ~18 |
| 4 | AI Pipeline | ~6 |
| 5 | Middlewares/Filters | ~4 |
| 6 | Start Handler | ~2 |
| 7 | Create Post | ~5 |
| 8 | Post Actions | ~9 |
| 9 | Publisher | ~6 |
| 10 | Queue | ~5 |
| 11 | Settings | ~7 |
| 12 | Scheduler | ~5 |
| 13 | Integration | ~2 |
| **Итого** | | **~92** |

---

## Пошаговая реализация

### Step 0: Docker + Config + Skeleton

**Цель:** Структура каталогов, зависимости, Docker-окружение, конфигурация. Dev-среда с PostgreSQL доступна сразу.

**Файлы:**

- Все `__init__.py` по структуре проекта
- `main.py` — заглушка (`if __name__ == "__main__": pass`)
- `requirements.txt`:
  ```
  aiogram>=3.10,<4
  langchain>=0.3
  langgraph>=0.2
  langchain-openai>=0.3
  langchain-google-genai>=2.0
  google-generativeai>=0.8
  tavily-python>=0.5
  sqlalchemy[asyncio]>=2.0
  asyncpg>=0.30
  alembic>=1.14
  apscheduler>=3.10,<4
  pydantic-settings>=2.0

  # Testing
  pytest>=8.0
  pytest-asyncio>=0.24
  aiosqlite>=0.20
  pytest-mock>=3.14
  ```
- `Dockerfile`:
  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  CMD ["python", "main.py"]
  ```
- `docker-compose.yml` (dev):
  ```yaml
  services:
    postgres:
      image: postgres:16-alpine
      environment:
        POSTGRES_USER: botuser
        POSTGRES_PASSWORD: botpass
        POSTGRES_DB: botdb
      ports: ["5432:5432"]
      volumes: [pgdata:/var/lib/postgresql/data]
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U botuser -d botdb"]
        interval: 5s
        retries: 5
    bot:
      build: .
      env_file: .env
      depends_on:
        postgres: { condition: service_healthy }
      volumes: [".:/app"]
      restart: unless-stopped
  volumes:
    pgdata:
  ```
- `docker-compose.prod.yml` (бот only, внешняя БД)
- `.env.example`:
  ```
  BOT_TOKEN=
  CHANNEL_ID=
  DATABASE_URL=postgresql+asyncpg://botuser:botpass@postgres:5432/botdb
  TAVILY_API_KEY=
  TIMEZONE=Europe/Moscow
  DEFAULT_CRON=0 9 * * *
  ```
- `.gitignore` (Python + .env + .idea + __pycache__)
- `pytest.ini`:
  ```ini
  [pytest]
  asyncio_mode = auto
  testpaths = tests
  ```
- `config/settings.py`:
  ```python
  from pydantic_settings import BaseSettings

  class Settings(BaseSettings):
      bot_token: str
      channel_id: int
      database_url: str
      tavily_api_key: str = ""
      timezone: str = "Europe/Moscow"
      default_cron: str = "0 9 * * *"
      testing: bool = False

      model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

  def get_settings() -> Settings:
      return Settings()
  ```

**Тесты:** `tests/test_config.py`
- `test_settings_from_env` — через `monkeypatch.setenv`, проверка всех полей
- `test_settings_defaults` — timezone и default_cron по умолчанию
- `test_settings_missing_required` — `ValidationError` без `bot_token`

**Проверка:** `pytest tests/test_config.py -v`

---

### Step 1: Database Layer (Models + Engine + Alembic)

**Цель:** SQLAlchemy 2.0 модели, async engine, session factory, Alembic.

**Файлы:**

- `db/engine.py`:
  - `build_engine(database_url)` → `create_async_engine`
  - `build_session_factory(engine)` → `async_sessionmaker`
- `db/models.py`:
  - `Base(DeclarativeBase)`
  - `PostStatus(str, Enum)`: pending, approved, published, editing, deleted
  - `AllowedChat`: id (PK), telegram_id (BigInteger, unique), description (String)
  - `Setting`: key (String, PK), value (Text)
  - `Post`: id (PK), media_ids (PortableJSON), original_text (Text), generated_text (Text), status (Enum), created_at (DateTime), published_at (DateTime, nullable)
  - `PortableJSON(TypeDecorator)` — JSONB на PostgreSQL, Text+JSON на SQLite
- `alembic.ini` + `alembic/env.py` — async migration runner
- Initial migration

**Тесты:** `tests/test_db/test_models.py`
- `test_create_allowed_chat` — insert + verify fields
- `test_allowed_chat_unique_telegram_id` — дубликат → IntegrityError
- `test_create_setting` — insert Setting, read back
- `test_create_post_default_status` — status = pending, published_at = None
- `test_post_status_enum_values` — все 5 значений валидны
- `test_post_media_ids_json` — сохранение/чтение list[dict] в media_ids

**Фикстуры:** добавить в `tests/conftest.py` — `db_engine`, `db_session`

**Проверка:** `pytest tests/test_db/test_models.py -v`

---

### Step 2: Repository (CRUD)

**Цель:** `db/repo.py` — все операции с БД за чистым async-интерфейсом.

**Файлы:**

- `db/repo.py`:
  ```python
  class Repository:
      def __init__(self, session: AsyncSession): ...

      # AllowedChat
      async def is_chat_allowed(self, telegram_id: int) -> bool
      async def add_allowed_chat(self, telegram_id: int, description: str = "") -> AllowedChat
      async def remove_allowed_chat(self, telegram_id: int) -> None

      # Settings
      async def get_setting(self, key: str) -> str | None
      async def set_setting(self, key: str, value: str) -> None

      # Posts
      async def create_post(self, original_text: str, generated_text: str,
                            media_ids: list[dict] | None = None) -> Post
      async def get_post(self, post_id: int) -> Post | None
      async def update_post_status(self, post_id: int, status: PostStatus) -> Post | None
      async def update_post_text(self, post_id: int, generated_text: str) -> Post | None
      async def delete_post(self, post_id: int) -> None
      async def get_approved_posts(self, page: int = 1, per_page: int = 5) -> list[Post]
      async def count_approved_posts(self) -> int
      async def get_oldest_approved_post(self) -> Post | None
  ```

**Тесты:** `tests/test_db/test_repo.py`
- `test_is_chat_allowed_true` / `test_is_chat_allowed_false`
- `test_add_and_remove_allowed_chat`
- `test_get_setting_returns_none_for_missing_key`
- `test_set_and_get_setting`
- `test_set_setting_overwrites`
- `test_create_post_returns_pending`
- `test_get_post_by_id`
- `test_update_post_status`
- `test_update_post_text`
- `test_delete_post`
- `test_get_approved_posts_pagination` — 7 approved, page 1 = 5, page 2 = 2
- `test_count_approved_posts` — исключает не-approved
- `test_get_oldest_approved_post` — 3 поста, возвращает старейший
- `test_get_oldest_approved_post_empty` — None

**Проверка:** `pytest tests/test_db/test_repo.py -v`

---

### Step 3: LLM Provider System

**Цель:** Система ротации провайдеров: интерфейс + реализации + роутер. Полностью автономный модуль.

**Файлы:**

#### `services/llm/base.py` — абстрактный интерфейс

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LLMResponse:
    text: str
    provider_name: str
    model: str
    tokens_used: int | None = None

class LLMProviderExhausted(Exception):
    """Все модели и ключи провайдера исчерпаны."""

class LLMProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def generate(self, messages: list[dict], temperature: float = 0.7) -> LLMResponse: ...

    @abstractmethod
    def reset(self) -> None: ...

    @property
    @abstractmethod
    def is_exhausted(self) -> bool: ...
```

#### `services/llm/openai_compat.py` — OpenAI/OpenRouter/DeepSeek

```python
class OpenAICompatibleProvider(LLMProvider):
    """
    Конфиг из БД:
    {
        "name": "openai",
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o"],
        "api_keys": ["sk-key1", "sk-key2"],
        "temperature": 0.7
    }

    Ротация: key[0]+model[0] → key[1]+model[0] → key[0]+model[1] → key[1]+model[1] → exhausted
    (Ключи первыми, т.к. rate limits per-key)
    """
```

- Использует `langchain_openai.ChatOpenAI` внутри
- `_current_model_idx`, `_current_key_idx`
- Ловит `openai.RateLimitError`, `openai.APIError`, `openai.APITimeoutError`

#### `services/llm/gemini.py` — Google Gemini

```python
class GeminiProvider(LLMProvider):
    """
    Конфиг из БД:
    {
        "name": "gemini",
        "type": "gemini",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro"],
        "api_keys": ["AIza-key1", "AIza-key2"],
        "temperature": 0.7
    }

    Ротация: model[0]+key[0] → model[1]+key[0] → model[0]+key[1] → model[1]+key[1] → exhausted
    (Модели первыми, т.к. у Google разные лимиты на модели)
    """
```

- Использует `langchain_google_genai.ChatGoogleGenerativeAI` внутри
- Ловит `google.api_core.exceptions.ResourceExhausted`, `GoogleAPIError`

#### `services/llm/router.py` — ProviderRouter

```python
class AllProvidersExhausted(Exception):
    """Все провайдеры в списке исчерпаны."""

class ProviderRouter:
    def __init__(self, providers: list[LLMProvider]): ...

    async def generate(self, messages: list[dict], temperature: float = 0.7) -> LLMResponse:
        """Пробует провайдеры по приоритету. Raises AllProvidersExhausted."""

    def reset_all(self) -> None:
        """Сброс состояния ротации всех провайдеров."""

    @classmethod
    def from_config(cls, config: list[dict]) -> "ProviderRouter":
        """Создание из JSON-конфига из БД."""
```

#### JSON-схема конфига (`settings.llm_providers`):

```json
[
  {
    "name": "gemini",
    "type": "gemini",
    "models": ["gemini-2.0-flash", "gemini-1.5-pro"],
    "api_keys": ["AIza-key1", "AIza-key2"],
    "temperature": 0.7
  },
  {
    "name": "openrouter",
    "type": "openai_compatible",
    "base_url": "https://openrouter.ai/api/v1",
    "models": ["deepseek/deepseek-chat", "meta-llama/llama-3-70b"],
    "api_keys": ["sk-or-key1"],
    "temperature": 0.7
  }
]
```

Порядок в массиве = приоритет (Gemini первый, OpenRouter второй).

**Тесты:**

`tests/test_services/test_llm/test_base.py`:
- `test_llm_response_dataclass` — проверка полей
- `test_provider_interface_cannot_instantiate` — ABC нельзя инстанцировать

`tests/test_services/test_llm/test_openai_compat.py` (мок `ChatOpenAI`):
- `test_generate_success` — 1 модель, 1 ключ → LLMResponse
- `test_key_rotation_on_rate_limit` — 2 ключа, первый RateLimitError → второй
- `test_model_rotation_after_keys_exhausted` — ключи кончились → следующая модель
- `test_provider_exhausted` — всё кончилось → LLMProviderExhausted
- `test_reset_clears_indices`
- `test_is_exhausted_property`

`tests/test_services/test_llm/test_gemini.py` (мок `ChatGoogleGenerativeAI`):
- `test_generate_success`
- `test_model_rotation_first` — 2 модели, 1 ключ → ротация моделей
- `test_key_rotation_after_all_models` — модели кончились → следующий ключ + model[0]
- `test_provider_exhausted`
- `test_reset`

`tests/test_services/test_llm/test_router.py` (мок LLMProvider):
- `test_router_uses_first_provider` — первый успешен, второй не трогает
- `test_router_falls_through_to_second` — первый exhausted → второй
- `test_router_all_exhausted` → AllProvidersExhausted
- `test_router_from_config` — из JSON, проверка типов
- `test_router_reset_all`
- `test_router_sticks_with_working_provider`
- `test_router_logs_rotation` — через `caplog`

**Проверка:** `pytest tests/test_services/test_llm/ -v`

---

### Step 4: AI Pipeline (LangGraph + Tavily + LLM)

**Цель:** LangGraph `StateGraph` с `search_node` (Tavily) и `generate_node` (ProviderRouter).

**Файлы:**

- `services/ai/prompts.py`:
  - `DEFAULT_SYSTEM_PROMPT` — экспертный промпт на русском
  - `SEARCH_FALLBACK_TEXT` — «❌ У меня нет доступа к веб-поиску...»

- `services/ai/graph.py`:
  ```python
  class PostState(TypedDict):
      product_query: str
      search_results: str
      system_prompt: str
      generated_text: str
      error: Optional[str]

  def build_graph(search_fn, generate_fn) -> CompiledGraph:
      # START → search_node → (error? END : generate_node) → END
  ```

- `services/ai/nodes.py`:
  - `make_search_node(tavily_api_key)` — Tavily search, при ошибке/пусто → fallback text
  - `make_generate_node(router: ProviderRouter)` — вызов router.generate(), при AllProvidersExhausted → error text

**Тесты:** `tests/test_services/test_ai_graph.py` (Tavily и router замоканы)
- `test_full_pipeline_success` — search → generate → generated_text заполнен
- `test_search_failure_returns_fallback` — Tavily exception → SEARCH_FALLBACK_TEXT, generate не вызван
- `test_search_empty_returns_fallback` — пустые результаты
- `test_generate_failure_returns_error` — AllProvidersExhausted → error text
- `test_search_results_passed_to_generate` — текст Tavily в сообщениях для LLM
- `test_system_prompt_used_in_generate` — кастомный промпт в messages

**Проверка:** `pytest tests/test_services/test_ai_graph.py -v`

---

### Step 5: Bot Foundation (Middlewares, FSM, Keyboards, Filters)

**Цель:** Базовые компоненты бота: dispatcher, middlewares, FSM states, keyboards, filters.

**Файлы:**

- `bot/states/fsm.py`:
  ```python
  class CreatePost(StatesGroup): waiting_for_input = State()
  class EditPost(StatesGroup): waiting_for_text = State()
  class RewritePost(StatesGroup): waiting_for_prompt = State()
  class EditPrompt(StatesGroup): collecting_parts = State()
  class EditSchedule(StatesGroup): waiting_for_cron = State()
  ```

- `bot/filters/chat_type.py`:
  ```python
  class IsPrivateChat(BaseFilter):
      async def __call__(self, message: Message) -> bool:
          return message.chat.type == "private"
  ```

- `bot/middlewares/access.py`:
  - `AllowedChatsMiddleware(BaseMiddleware)` — проверка по таблице `allowed_chats`, drop если не allowed

- `bot/middlewares/media_group.py`:
  - Собирает сообщения с одинаковым `media_group_id` через `asyncio.sleep(1.5)` буфер
  - После буфера передаёт список в handler

- `bot/keyboards/reply.py`:
  - `main_menu_keyboard()` → ReplyKeyboardMarkup: «📝 Создать пост», «🗂 Очередь постов», «⚙️ Настройки»

- `bot/keyboards/inline.py`:
  - `post_actions_keyboard(post_id)` — 5 кнопок (publish, approve, edit, rewrite, delete)
  - `queue_keyboard(posts, page, total_pages)` — номера + навигация
  - `settings_keyboard()` — промпт, расписание, провайдеры
  - Callback data: `post:{post_id}:{action}`, `queue:page:{n}`, `queue:post:{id}`, `settings:{action}`

**Тесты:** `tests/test_bot/test_middlewares.py`
- `test_allowed_chat_passes_through` — mock repo.is_chat_allowed → True, handler вызван
- `test_disallowed_chat_blocked` — mock → False, handler НЕ вызван
- `test_media_group_collects_album` — 3 сообщения с media_group_id → handler получает список из 3
- `test_media_group_single_message` — без media_group_id → проходит сразу

**Проверка:** `pytest tests/test_bot/test_middlewares.py -v`

---

### Step 6: Handler — /start и Main Menu

**Цель:** Команда `/start` показывает главное меню в ЛС.

**Файлы:**

- `bot/handlers/start.py`:
  - Router с `CommandStart`
  - В private: welcome + `main_menu_keyboard()`
  - В group: краткое сообщение без ReplyKeyboard

**Тесты:** `tests/test_bot/test_handlers.py`
- `test_start_private_sends_menu` — /start в private → ReplyKeyboardMarkup
- `test_start_group_no_reply_keyboard` — /start в group → без ReplyKeyboardMarkup

**Проверка:** `pytest tests/test_bot/test_handlers.py -v`

---

### Step 7: Handler — Create Post

**Цель:** Полный флоу создания поста: приём товара + медиа, AI pipeline, сохранение, превью с кнопками.

**Файлы:**

- `bot/handlers/create_post.py`:
  1. «Создать пост» → `state.clear()`, `CreatePost.waiting_for_input`, «Отправьте название товара...»
  2. На сообщение в FSM:
     - Извлечь `file_id` из фото/видео/документов (медиагруппа через middleware)
     - Отправить «⏳ Собираю данные...»
     - Загрузить `system_prompt` и `llm_providers` из БД
     - Запустить LangGraph pipeline
     - Сохранить пост (status=pending)
     - Отправить превью + inline кнопки
     - Очистить FSM

**Тесты:** (добавить в `tests/test_bot/test_handlers.py`)
- `test_create_post_button_sets_fsm_state`
- `test_create_post_success` — мок pipeline → пост в БД со status=pending
- `test_create_post_with_media` — media_ids сохранены
- `test_create_post_search_failure` — fallback text сохранён
- `test_create_post_shows_inline_buttons` — ответ содержит InlineKeyboard

**Проверка:** `pytest tests/test_bot/test_handlers.py -v`

---

### Step 8: Handler — Post Actions (Inline Callbacks)

**Цель:** 5 inline-кнопок: publish, approve, edit, rewrite, delete.

**Файлы:**

- `bot/handlers/post_actions.py`:
  1. Parse callback_data → post_id + action
  2. Проверка статуса в БД (не editing → иначе reject)
  3. Действия:
     - **publish**: status=published → publisher.publish() → update published_at → убрать кнопки
     - **approve**: status=approved → подтверждение → убрать кнопки
     - **edit**: status=editing → FSM `EditPost.waiting_for_text` → disable кнопки. На новый текст: update generated_text, status=pending, новое превью
     - **rewrite**: status=editing → FSM `RewritePost.waiting_for_prompt` → disable кнопки. На промпт: router.generate() → update text, status=pending, превью
     - **delete**: hard delete → edit message «Удалён»

**Тесты:** (добавить в `tests/test_bot/test_handlers.py`)
- `test_publish_now_calls_publisher` — мок publisher
- `test_publish_now_updates_status` → published
- `test_approve_sets_status` → approved
- `test_edit_enters_fsm_state` → EditPost.waiting_for_text
- `test_edit_sets_editing_status` → editing
- `test_edit_submit_new_text` → generated_text обновлён, status=pending
- `test_rewrite_calls_llm` — мок router
- `test_delete_removes_from_db`
- `test_action_on_editing_post_blocked` — reject message

**Проверка:** `pytest tests/test_bot/test_handlers.py -v`

---

### Step 9: Publisher Service

**Цель:** Публикация постов в канал с обработкой медиа и FloodWait.

**Файлы:**

- `services/publisher.py`:
  - `publish_post(bot, post, channel_id)`:
    - Без медиа → `send_message(text)`
    - Медиа + текст ≤ 1024 → `send_media_group`/single с caption
    - Медиа + текст > 1024 → медиа без caption, затем reply с текстом
  - FloodWait retry: `TelegramRetryAfter` → `asyncio.sleep(retry_after)` + retry (max 3)

**Тесты:** `tests/test_services/test_publisher.py`
- `test_publish_text_only` → send_message
- `test_publish_short_text_with_media` → caption
- `test_publish_long_text_with_media` → медиа + reply
- `test_publish_media_group` → send_media_group
- `test_flood_wait_retry` → первый TelegramRetryAfter, второй успех
- `test_flood_wait_max_retries_exceeded` → exception propagated

**Проверка:** `pytest tests/test_services/test_publisher.py -v`

---

### Step 10: Handler — Queue (Approved Posts)

**Цель:** Пагинированный список approved постов с навигацией и действиями.

**Файлы:**

- `bot/handlers/queue.py`:
  - «Очередь постов» → page 1: нумерованный список + [← Назад] [Вперёд →]
  - Клик по номеру → превью поста + кнопки (publish/edit/delete/back)
  - Навигация: `message.edit_text` / `message.edit_reply_markup`

**Тесты:** (добавить в `tests/test_bot/test_handlers.py`)
- `test_queue_empty` — «Очередь пуста»
- `test_queue_shows_posts` — 3 поста отображены
- `test_queue_pagination` — 7 постов, page 1 = 5, page 2 = 2
- `test_queue_post_detail` — клик → превью
- `test_queue_back_to_list` — возврат к списку

**Проверка:** `pytest tests/test_bot/test_handlers.py -v`

---

### Step 11: Handler — Settings (Prompt + Schedule + Providers)

**Цель:** Настройки: редактирование промпта, крон-расписания, конфига LLM-провайдеров.

**Файлы:**

- `bot/handlers/settings.py`:
  - «Настройки» → inline-подменю: [🧠 Промпт] [🕒 Расписание] [🤖 Провайдеры]

  - **Edit Prompt**: FSM `EditPrompt.collecting_parts`
    - Приём нескольких сообщений + `.txt` файлов
    - Кнопка «✅ Я закончил отправку» → конкатенация → save `system_prompt`

  - **Edit Schedule**: FSM `EditSchedule.waiting_for_cron`
    - Валидация `CronTrigger.from_crontab(user_input)`
    - Ошибка → переспрос. Успех → update DB + reschedule

  - **Edit Providers**:
    - Бот сразу отправляет текущий JSON-конфиг провайдеров (аналогично показу текущего промпта)
    - Просит загрузить новый `.json` файл
    - Валидация структуры JSON перед сохранением
    - Успех → сохранить `llm_providers`, подтверждение
    - Ошибка валидации → сообщение об ошибке, повторный запрос файла

**Тесты:** (добавить в `tests/test_bot/test_handlers.py`)
- `test_edit_prompt_single_message` → DB updated
- `test_edit_prompt_multi_message` → concatenated
- `test_edit_prompt_txt_file` → content extracted
- `test_edit_schedule_valid_cron` → DB updated
- `test_edit_schedule_invalid_cron` → error + re-prompt
- `test_edit_providers_shows_current_config` → бот отправляет текущий JSON
- `test_edit_providers_valid_json_file` → .json файл загружен и сохранён
- `test_edit_providers_invalid_json_file` → невалидный .json → rejection + повторный запрос

**Проверка:** `pytest tests/test_bot/test_handlers.py -v`

---

### Step 12: APScheduler Integration

**Цель:** Крон-автопубликация approved постов.

**Файлы:**

- `services/scheduler.py`:
  - `create_scheduler(session_factory, bot, channel_id, cron_expr)`:
    - `AsyncIOScheduler` (APScheduler 3.x)
    - `publish_job`: oldest approved → publish → status=published. Пусто → silent skip
    - `add_job(publish_job, CronTrigger.from_crontab(cron), id="auto_publish", replace_existing=True)`
  - `reschedule(scheduler, new_cron)`: `scheduler.reschedule_job("auto_publish", trigger=CronTrigger.from_crontab(new_cron))`

**Тесты:** `tests/test_services/test_scheduler.py`
- `test_publish_job_publishes_oldest` — 2 approved, job → oldest published
- `test_publish_job_empty_queue_no_error` — silent
- `test_publish_job_skips_editing` — editing пост не публикуется
- `test_reschedule_updates_trigger` — mock scheduler
- `test_cron_trigger_validation` — valid/invalid строки

**Проверка:** `pytest tests/test_services/test_scheduler.py -v`

---

### Step 13: Entry Point + Final Integration

**Цель:** Собрать всё в `main.py`, seed дефолтные настройки, Docker-верификация.

**Файлы:**

- `main.py`:
  ```python
  async def main():
      cfg = get_settings()
      engine = build_engine(cfg.database_url)
      session_factory = build_session_factory(engine)

      bot = Bot(token=cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
      dp = Dispatcher(storage=MemoryStorage())

      # Middlewares
      dp.update.middleware(AllowedChatsMiddleware())

      # Routers
      dp.include_router(start.router)
      dp.include_router(create_post.router)
      dp.include_router(post_actions.router)
      dp.include_router(queue.router)
      dp.include_router(settings.router)

      # Data injection
      dp["session_factory"] = session_factory
      dp["channel_id"] = cfg.channel_id

      # Scheduler
      async with session_factory() as session:
          repo = Repository(session)
          cron = await repo.get_setting("schedule_cron") or cfg.default_cron

      scheduler = create_scheduler(session_factory, bot, cfg.channel_id, cron)
      dp["scheduler"] = scheduler

      # Start
      scheduler.start()
      try:
          await dp.start_polling(bot)
      finally:
          scheduler.shutdown()
  ```

- Seed defaults (через Alembic data migration или startup):
  - `settings(key='system_prompt', value=DEFAULT_SYSTEM_PROMPT)`
  - `settings(key='schedule_cron', value='0 9 * * *')`
  - `settings(key='llm_providers', value='[]')`

**Тесты:**
- `test_main_startup_sequence` — мок всех зависимостей, проверка порядка init
- Integration smoke test — in-memory SQLite + мок bot token → без exceptions

**Проверка:**
```bash
pytest tests/ -v                     # все ~92 теста зелёные
docker-compose up --build            # бот стартует, подключается к postgres
```

---

## Граф зависимостей

```
Step 0: Docker + Config + Skeleton
  └── Step 1: DB Models + Engine + Alembic
       └── Step 2: Repository (CRUD)
            ├── Step 3: LLM Provider System
            │    └── Step 4: AI Pipeline (LangGraph)
            │         └── Step 7: Create Post Handler
            │              └── Step 8: Post Actions Handler
            ├── Step 5: Bot Foundation (Middlewares, FSM, Keyboards)
            │    └── Step 6: /start Handler
            ├── Step 9: Publisher Service
            ├── Step 10: Queue Handler
            ├── Step 11: Settings Handler
            └── Step 12: Scheduler
                 └── Step 13: Entry Point + Integration
```

Параллельно после Step 2: Steps 3, 5, 9.
Параллельно после Step 5: Steps 6, 10, 11.
