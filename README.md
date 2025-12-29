# Ded Moroz: адвент‑подарки

Telegram‑бот на Python 3.11 + aiogram 3.x для адвент‑кампании: пользователи присылают стихи, бот проверяет их через OpenRouter (Structured Outputs) и выдаёт подарки дня. Отдельный планировщик на APScheduler рассылает напоминания и уведомления о пропущенных днях.

## Возможности
- Opt‑in через `/start`, статусы `/pause`, `/resume`, `/stop`, `/status`.
- Проверка стихов через OpenRouter `/chat/completions` с `response_format: json_schema`.
- Логирование попыток и сабмишенов (уникально по пользователю и дню), лимит попыток в день.
- Два задания планировщика: `send_daily_reminders`, `send_missed_notifications`, идемпотентность через `notifications_log`.
- Админ‑команды: `/admin_stats`, `/admin_user`, `/set_gift`, `/get_gift`, `/admin_errors`, `/admin_error`, `/admin_health`.
- Лог ошибок в `error_logs` и авто‑уведомления админам, heartbeat в `service_heartbeats`.
- Деплой через docker-compose: bot + scheduler + postgres.
- Alembic миграции и минимальные тесты.

## Быстрый старт (docker-compose)
1. Скопируйте `.env.example` в `.env` и задайте переменные (ключи, даты кампании, ID админов).
2. Запустите:
   ```bash
   docker-compose up --build
   ```
   Поднимутся контейнеры `db`, `bot`, `scheduler`. Alembic миграции применяются при старте контейнеров.
3. В Telegram нажмите `/start` у бота.

## Локальный запуск
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[test]
cp .env.example .env  # заполните значения
alembic upgrade head
python -m ded_moroz.bot  # бот (polling)
python -m ded_moroz.scheduler  # отдельный процесс планировщика
```

## Конфигурация
Ключевые переменные `.env`:
- `BOT_TOKEN` — токен Telegram бота.
- `DATABASE_URL` — async URL PostgreSQL (или SQLite для локальных тестов).
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL` — настройки OpenRouter.
- `CAMPAIGN_START_DATE` (YYYY-MM-DD), `CAMPAIGN_DAYS`, `CAMPAIGN_REMINDER_DEADLINE_HOUR`, `CAMPAIGN_MISSED_DEADLINE_HOUR`, `CAMPAIGN_QUIET_HOURS_START`, `CAMPAIGN_QUIET_HOURS_END`, `CAMPAIGN_MAX_ATTEMPTS_PER_DAY`, `CAMPAIGN_TZ` (по умолчанию `Europe/Moscow`, quiet-часы 23–06, напоминания не раньше 12:00).
- `ADMIN_TG_IDS` — ID админов через запятую (поддерживаются алиасы `ADMIN_IDS`, `ADMINS__IDS`).
- `WELCOME_IMAGE_URL` — (опционально) ссылка/file_id на картинку в приветственном сообщении `/start`.

### Подарки
- Текст без указания типа: `/set_gift 1 Мой текстовый подарок` (не обрезается).
- Ссылки: `/set_gift 2 url https://example.com/bonus`.
- Медиа: `/set_gift 3 photo https://example.com/pic.jpg Подпись к картинке` (поддерживаются `photo|video|audio`, caption необязательный).

## Тесты
```bash
pip install -r requirements-test.txt
pytest
```

Покрыты сценарии: уникальность сабмишенов, идемпотентные уведомления, валидация JSON от LLM.
