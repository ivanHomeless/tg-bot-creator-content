-- Создаем пользователя
CREATE USER botcreator WITH PASSWORD 'iX5IjBbxAGPGUl5zxNpM';

-- Создаем базу данных
CREATE DATABASE telegram_bot_posts OWNER botcreator;

-- Подключаемся к созданной БД и выдаем права на схему public
\c telegram_bot_posts

GRANT ALL ON SCHEMA public TO botcreator;
GRANT ALL ON ALL TABLES IN SCHEMA public TO botcreator;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO botcreator;

-- Права на будущие объекты (автоматически)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO botcreator;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO botcreator;
