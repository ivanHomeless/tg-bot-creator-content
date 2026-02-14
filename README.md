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
| Логирование | stdout + RotatingFileHandler (`logs/bot.log`) |
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

### Продакшен-деплой

Если PostgreSQL уже работает в отдельном Docker-контейнере (в сети `ai_serivices_web`):

```bash
git clone https://github.com/your-username/tg-bot-creator-content.git
cd tg-bot-creator-content
cp .env.example .env
# Заполнить .env (DATABASE_URL указать на существующий PostgreSQL)
```

```bash
# Первый запуск
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec tg_bot_creator alembic upgrade head

# Обновление
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Бот автоматически перезапускается при падении (`restart: unless-stopped`). Логи доступны в `logs/bot.log` и через `docker logs tg_bot_creator`.

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

### 5. Настроить доступ

См. раздел [Настройка бота](#-настройка-бота) ниже.

## 📖 Настройка бота

### Канал для публикаций

Бот публикует посты в один канал, указанный в `.env`:

```env
CHANNEL_ID=-1001234567890
```

ID канала — это **отрицательное число**, начинающееся с `-100`. Чтобы его узнать:

1. Добавьте бота **администратором** в канал (с правом отправки сообщений)
2. Перешлите любое сообщение из канала боту [@userinfobot](https://t.me/userinfobot) или [@getidsbot](https://t.me/getidsbot) — он покажет ID
3. Скопируйте ID (например `-1001234567890`) в `CHANNEL_ID`

### Белый список чатов (allowed_chats)

Бот отвечает **только** в чатах из таблицы `allowed_chats`. Все остальные сообщения молча игнорируются. Нужно добавить записи в БД через SQL:

```sql
-- Добавить свой личный аккаунт (ЛС с ботом)
INSERT INTO allowed_chats (telegram_id, description)
VALUES (123456789, 'Админ Иван');

-- Добавить группу для подготовки публикаций
INSERT INTO allowed_chats (telegram_id, description)
VALUES (-1001987654321, 'Рабочая группа редакции');
```

**Как узнать ID:**
- **Свой ID** — напишите [@userinfobot](https://t.me/userinfobot), он вернёт ваш числовой ID (положительное число, например `123456789`)
- **ID группы/супергруппы** — добавьте [@userinfobot](https://t.me/userinfobot) в группу, он покажет ID группы (отрицательное число с префиксом `-100`, например `-1001987654321`)

### Личные сообщения vs Группа

Бот работает в обоих режимах, но интерфейс отличается:

| | Личные сообщения | Группа |
|---|---|---|
| Меню | Нижнее меню с 3 кнопками (Создать пост, Очередь, Настройки) | Без нижнего меню |
| Взаимодействие | Полная админка через ReplyKeyboard | Только inline-кнопки под постами |
| Подходит для | Единоличное управление | Командная модерация |

**Типичный сценарий:**
1. Добавьте в `allowed_chats` свой личный ID + ID рабочей группы
2. В ЛС с ботом — создавайте посты, управляйте настройками и очередью
3. В группе — совместно модерируйте посты через inline-кнопки (одобрить, отредактировать, опубликовать)

### Подключение к PostgreSQL

Для ручного добавления `allowed_chats` подключитесь к БД:

```bash
# Через docker-compose
docker-compose exec postgres psql -U botuser -d botdb

# Или напрямую
psql postgresql://botuser:botpass@localhost:5432/botdb
```

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
├── logs/                      # Логи (gitignored)
├── Dockerfile
├── docker-compose.yml         # Dev (с локальным PostgreSQL)
├── docker-compose.prod.yml    # Prod (внешняя сеть, volume для логов)
├── requirements.txt
└── .env.example
```

## 📄 Лицензия

MIT
