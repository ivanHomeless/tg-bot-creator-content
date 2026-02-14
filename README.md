# TG Bot Creator Content

AI-агент Telegram-бот для создания контента. Принимает название товара, ищет информацию в интернете через Tavily, генерирует экспертный пост с помощью LLM (с защитой от галлюцинаций) и предоставляет админку для редактирования, публикации и планирования постов в Telegram-канал.

## ✨ Возможности

- **AI-генерация постов** — LangGraph пайплайн: веб-поиск (Tavily) → генерация текста (LLM)
- **Система ротации LLM** — приоритетные провайдеры с автоматическим фолбэком (OpenAI-совместимые + Gemini)
- **Медиа-поддержка** — фото, видео, документы, альбомы (MediaGroupMiddleware)
- **Модерация** — inline-кнопки: публикация, одобрение, редактирование, рерайт, удаление
- **Очередь постов** — пагинация, просмотр, управление
- **Автопубликация** — APScheduler с cron-расписанием, настраиваемым через бота
- **Настройки** — системный промпт, расписание, конфиг LLM-провайдеров — всё через бота без рестарта
- **Контроль доступа** — белый список чатов в БД

## 🛠 Технический стек

| Компонент | Технология |
|-----------|-----------|
| Язык | Python 3.11+ |
| Бот-фреймворк | aiogram 3.x |
| AI-оркестрация | LangGraph + LangChain |
| LLM | ProviderRouter (OpenAI/OpenRouter/DeepSeek + Gemini) |
| Веб-поиск | Tavily |
| База данных | PostgreSQL + SQLAlchemy 2.0 (asyncpg) + Alembic |
| Планировщик | APScheduler 3.x |
| Конфигурация | Pydantic Settings + `.env` |
| Инфраструктура | Docker + docker-compose |

## 🚀 Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/your-username/tg-bot-creator-content.git
cd tg-bot-creator-content
```

### 2. Настроить окружение

```bash
cp .env.example .env
```

Заполнить `.env`:

```env
BOT_TOKEN=123456:ABC-DEF...          # токен от @BotFather
CHANNEL_ID=-100123456789             # ID канала для публикации
DATABASE_URL=postgresql+asyncpg://botuser:botpass@postgres:5432/botdb
TAVILY_API_KEY=tvly-...              # ключ Tavily API (опционально)
TIMEZONE=Europe/Moscow
DEFAULT_CRON=0 9 * * *              # расписание автопубликации
```

### 3. Запустить через Docker

```bash
docker-compose up -d
```

Это поднимет PostgreSQL и бота. БД создастся автоматически, дефолтные настройки засеются при первом запуске.

### 4. Настроить LLM-провайдеры

LLM-провайдеры настраиваются через бота (Настройки → LLM-провайдеры). Загрузите `.json` файл:

```json
[
  {
    "name": "gemini",
    "type": "gemini",
    "models": ["gemini-2.0-flash", "gemini-1.5-pro"],
    "api_keys": ["AIza-key1"],
    "temperature": 0.7
  },
  {
    "name": "openrouter",
    "type": "openai_compatible",
    "base_url": "https://openrouter.ai/api/v1",
    "models": ["deepseek/deepseek-chat"],
    "api_keys": ["sk-or-key1"],
    "temperature": 0.7
  }
]
```

Порядок в массиве = приоритет. Первый провайдер используется по умолчанию, остальные — фолбэки.

### 5. Добавить чат в белый список

Добавьте запись в таблицу `allowed_chats` в БД с вашим Telegram ID (или ID группы). Бот будет отвечать только в разрешённых чатах.

## ‍💻 Разработка

### Локальный запуск (без Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# PostgreSQL должен быть запущен
# Обновить DATABASE_URL в .env

python main.py
```

### Тесты

```bash
pip install -r requirements.txt
pytest -v
```

Тесты используют `aiosqlite` (in-memory SQLite), внешние API мокаются. PostgreSQL не нужен.

### Миграции БД

```bash
alembic upgrade head          # применить миграции
alembic revision --autogenerate -m "описание"  # создать миграцию
```

## 📁 Структура проекта

```
├── main.py                    # Точка входа
├── config/
│   └── settings.py            # Pydantic Settings
├── db/
│   ├── models.py              # SQLAlchemy модели
│   ├── repo.py                # Repository (CRUD)
│   └── engine.py              # Async engine + session factory
├── services/
│   ├── ai/
│   │   ├── graph.py           # LangGraph пайплайн
│   │   ├── nodes.py           # Search + Generate ноды
│   │   └── prompts.py         # Системный промпт, фолбэки
│   ├── llm/
│   │   ├── base.py            # ABC LLMProvider
│   │   ├── openai_compat.py   # OpenAI/OpenRouter/DeepSeek
│   │   ├── gemini.py          # Google Gemini
│   │   └── router.py          # ProviderRouter
│   ├── publisher.py           # Публикация в канал
│   └── scheduler.py           # APScheduler cron-job
├── bot/
│   ├── handlers/
│   │   ├── start.py           # /start
│   │   ├── create_post.py     # Создание поста
│   │   ├── post_actions.py    # Inline-действия
│   │   ├── queue.py           # Очередь постов
│   │   └── settings.py        # Настройки
│   ├── middlewares/
│   │   ├── access.py          # Белый список чатов
│   │   └── media_group.py     # Сбор альбомов
│   ├── keyboards/
│   │   ├── reply.py           # Главное меню
│   │   └── inline.py          # Inline-кнопки
│   ├── filters/
│   │   └── chat_type.py       # Фильтр приватных чатов
│   └── states/
│       └── fsm.py             # FSM-состояния
├── tests/                     # 103 теста
├── docs/
│   ├── PRD_TG_Bot_Creator.md
│   └── IMPLEMENTATION_PLAN.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## 📄 Лицензия

MIT
