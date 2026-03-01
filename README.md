# Ded Moroz Bot: геймифицированные ежедневные задания в Telegram

`Ded Moroz` - это Telegram-бот на Python 3.11 (`aiogram 3.x`) для ежедневных челленджей с проверкой пользовательского текста через LLM (OpenRouter) и выдачей награды по дням.

Изначально проект задуман как адвент-календарь со стихами, но архитектура подходит для любых последовательных кампаний, где нужно:
1. Получать текстовый ответ от пользователя каждый день.
2. Проверять ответ автоматически по правилам.
3. Выдавать контент-награду.
4. Напоминать тем, кто пропустил день.

## Для каких задач подходит бот
Бот можно использовать не только для новогоднего формата:
1. Адвент/марафон в сообществе с ежедневными заданиями.
2. Корпоративный onboarding на 7/14/30 дней.
3. Обучающий микрокурс с ежедневной сдачей мини-ответа.
4. Писательский челлендж с выдачей новых материалов по дням.
5. Языковой тренажер (ежедневная фраза/мини-эссе).
6. Wellness/habit трекер с простыми ежедневными отчетами.
7. Промо-кампания, где доступ к бонусам открывается по расписанию.

## Когда бот может не подойти
1. Если требуется сложная ручная модерация каждого ответа.
2. Если у вас нет Telegram как основного канала.
3. Если нужен heavy-load real-time сценарий на сотни тысяч событий в минуту.

## Что умеет проект
1. Подключение пользователя через `/start`, управление статусом `/pause`, `/resume`, `/stop`, `/status`.
2. Прием текстов и LLM-проверка через `OpenRouter /chat/completions` с `response_format: json_schema`.
3. Решения по ответу: `ACCEPT`, `RETRY`, `REJECT`.
4. Лимит попыток в день и уникальная фиксация успешной сдачи на день.
5. Подарки разных типов: `text`, `url`, `photo`, `video`, `audio`, `payload`.
6. Планировщик напоминаний и уведомлений о пропуске (`APScheduler`).
7. Идемпотентность отправок через `notifications_log`.
8. Админ-инструменты для диагностики (`/admin_stats`, `/admin_errors`, `/admin_health` и другие).
9. Логи ошибок + heartbeat сервисов для мониторинга.

## Архитектура (кратко)
1. `bot` - Telegram polling и пользовательские/админ-команды.
2. `scheduler` - периодические задачи напоминаний и служебные проверки.
3. `db` - PostgreSQL для пользователей, сабмишенов, попыток, подарков, логов.
4. `migrate` - запуск Alembic миграций перед стартом `bot` и `scheduler`.

## Быстрый старт за 10-15 минут (Docker)

### 1) Подготовьте входные данные
Нужно заранее получить:
1. `BOT_TOKEN` от [@BotFather](https://t.me/BotFather).
2. `OPENROUTER_API_KEY` из вашего аккаунта OpenRouter.
3. Telegram ID администратора (например, через [@userinfobot](https://t.me/userinfobot)).

### 2) Склонируйте репозиторий
```bash
git clone https://github.com/aglyamodinar/DedMoroz.git
cd DedMoroz
```

### 3) Создайте `.env`
```bash
cp .env.example .env
```

### 4) Заполните `.env` минимумом обязательных значений
Минимальный рабочий набор:
```dotenv
BOT_TOKEN=123456:telegram-token
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/dedmoroz
OPENROUTER_API_KEY=sk-or-xxxx
OPENROUTER_MODEL=openai/gpt-4o-mini-2024-07-18
CAMPAIGN_START_DATE=2026-12-01
CAMPAIGN_DAYS=24
CAMPAIGN_REMINDER_DEADLINE_HOUR=12
CAMPAIGN_MISSED_DEADLINE_HOUR=23
CAMPAIGN_QUIET_HOURS_START=23
CAMPAIGN_QUIET_HOURS_END=6
CAMPAIGN_TZ=Europe/Moscow
CAMPAIGN_MAX_ATTEMPTS_PER_DAY=3
ADMIN_TG_IDS=123456789
ENV=local
```

### 5) Запустите сервисы
```bash
docker compose up --build
```
Если у вас старая версия Docker Compose:
```bash
docker-compose up --build
```

### 6) Убедитесь, что все поднялось
Ожидаемо работают контейнеры: `db`, `migrate`, `bot`, `scheduler`.
Проверка:
```bash
docker compose ps
```

### 7) Пройдите smoke-test в Telegram
1. Откройте чат с ботом и отправьте `/start`.
2. Нажмите кнопку "Сдать стих за сегодня" или отправьте `/gift`.
3. Отправьте тестовый текст.
4. Убедитесь, что бот отвечает и при `ACCEPT` выдает подарок.

## Суперподробный runbook для AI-ассистента
Этот раздел можно давать AI-ассистенту как "протокол развертывания".

### Шаг 1. Собери параметры у пользователя
Ассистент должен запросить и подтвердить:
1. `BOT_TOKEN`.
2. `OPENROUTER_API_KEY`.
3. `ADMIN_TG_IDS`.
4. Дату старта кампании (`CAMPAIGN_START_DATE`, формат `YYYY-MM-DD`).
5. Часовой пояс (`CAMPAIGN_TZ`, например `Europe/Moscow`).
6. Число дней (`CAMPAIGN_DAYS`).
7. Лимит попыток (`CAMPAIGN_MAX_ATTEMPTS_PER_DAY`).

### Шаг 2. Подготовь окружение
Команды:
```bash
cp .env.example .env
```
Критерий успеха: файл `.env` создан.

### Шаг 3. Заполни `.env` и проверь обязательные поля
Ассистент обязан проверить, что в `.env` не осталось заглушек:
1. `BOT_TOKEN` не равен `your-telegram-bot-token`.
2. `OPENROUTER_API_KEY` начинается с `sk-or-`.
3. `ADMIN_TG_IDS` содержит хотя бы один числовой ID.
4. `CAMPAIGN_START_DATE` валидна в формате `YYYY-MM-DD`.
5. `DATABASE_URL` указывает на `db:5432` для Docker-режима.

### Шаг 4. Запусти контейнеры
Команда:
```bash
docker compose up --build -d
```
Критерий успеха: `docker compose ps` показывает `bot` и `scheduler` в состоянии `running`.

### Шаг 5. Проверь миграции и логи
Команды:
```bash
docker compose logs migrate --tail=100
docker compose logs bot --tail=100
docker compose logs scheduler --tail=100
```
Критерий успеха:
1. Для `migrate` нет ошибок применения миграций.
2. Для `bot` нет фатальных ошибок инициализации.
3. Для `scheduler` есть признак запуска (`Scheduler started`).

### Шаг 6. Проведи функциональную проверку
Ассистент должен попросить пользователя выполнить в Telegram:
1. `/start`.
2. `/status`.
3. `/gift` или кнопку "Сдать стих за сегодня".
4. Отправить текст и проверить, что бот дал валидный ответ.

### Шаг 7. Настрой контент (подарки)
Ассистент должен подсказать админу:
1. `/set_gift 1 Добро пожаловать в челлендж!`
2. `/set_gift 2 url https://example.com/bonus`
3. `/set_gift 3 photo https://example.com/pic.jpg Подпись`
4. `/admin_gifts` для проверки заполнения.

### Шаг 8. Проверь мониторинг для администратора
Команды в боте:
1. `/admin_stats`
2. `/admin_errors`
3. `/admin_health`
Критерий успеха: бот возвращает статистику и состояние сервисов без ошибок доступа.

### Шаг 9. Финальный отчет ассистента
Ассистент завершает развертывание отчетом:
1. Какие значения были настроены (без секретов в явном виде).
2. Какие проверки пройдены.
3. Что осталось сделать вручную (если есть).
4. Где смотреть логи и как перезапустить сервисы.

## Команды бота

### Пользовательские
1. `/start` - старт/возврат в кампанию.
2. `/gift` - запросить сдачу текста за текущий день.
3. `/status` - показать текущий статус.
4. `/pause` - пауза участия.
5. `/resume` - продолжить участие.
6. `/stop` - остановить участие.

### Админские
1. `/set_gift <day> <content>` - установить подарок.
2. `/setgift <day>` - пошаговая FSM-настройка подарка.
3. `/get_gift <day>` - получить конфиг подарка на день.
4. `/admin_gifts` - аудит заполненности подарков.
5. `/admin_stats` - агрегированная статистика.
6. `/admin_user <telegram_id>` - данные пользователя.
7. `/admin_errors` и `/admin_error <id>` - ошибки.
8. `/admin_health` - heartbeat сервисов.
9. `/campaign_start [YYYY-MM-DD]` - посмотреть/изменить дату старта.
10. `/campaign_reset_dates` - сбросить даты для тестов.
11. `/set_welcome_image <url_or_file_id>` - обновить приветственное медиа.

## Форматы подарков
1. Текст: `/set_gift 1 Мой текстовый подарок`.
2. Ссылка: `/set_gift 2 url https://example.com/bonus`.
3. Фото: `/set_gift 3 photo https://example.com/pic.jpg Подпись`.
4. Видео: `/set_gift 4 video https://example.com/video.mp4 Описание`.
5. Аудио: `/set_gift 5 audio https://example.com/track.mp3 Описание`.
6. JSON payload: `/set_gift 6 payload {"coupon":"XMAS-25"}`.

## Конфигурация `.env`

### Обязательные
1. `BOT_TOKEN` - токен Telegram бота.
2. `DATABASE_URL` - async URL БД.
3. `OPENROUTER_API_KEY` - ключ OpenRouter.
4. `CAMPAIGN_START_DATE` - дата старта (`YYYY-MM-DD`).
5. `ADMIN_TG_IDS` - Telegram ID админов через запятую.

### Важные опциональные
1. `OPENROUTER_MODEL` - модель OpenRouter.
2. `OPENROUTER_BASE_URL` - базовый URL OpenRouter API.
3. `CAMPAIGN_DAYS` - длительность кампании.
4. `CAMPAIGN_REMINDER_DEADLINE_HOUR` - час, после которого отправляются напоминания.
5. `CAMPAIGN_MISSED_DEADLINE_HOUR` - час дедлайна дня и уведомлений о пропуске.
6. `CAMPAIGN_QUIET_HOURS_START` и `CAMPAIGN_QUIET_HOURS_END` - тихие часы.
7. `CAMPAIGN_TZ` - таймзона кампании.
8. `CAMPAIGN_MAX_ATTEMPTS_PER_DAY` - лимит попыток.
9. `WELCOME_IMAGE_URL` - ссылка или `file_id` приветственного медиа.
10. `BATCH_CHUNK_SIZE` - размер батча для рассылок.

## Локальный запуск без Docker
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[test]
cp .env.example .env
alembic upgrade head
python -m ded_moroz.bot
python -m ded_moroz.scheduler
```

## Тесты
```bash
pip install -r requirements-test.txt
pytest
```
Покрыты базовые сценарии: уникальность сабмишенов, идемпотентность уведомлений, валидация JSON от LLM.

## Частые проблемы и быстрые решения
1. Бот не отвечает на `/start`: проверьте `BOT_TOKEN` и логи `bot`.
2. Ошибка БД при старте: проверьте `DATABASE_URL` и что контейнер `db` здоров.
3. Ошибка LLM-проверки: проверьте `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, доступность OpenRouter.
4. Нет напоминаний: проверьте `scheduler`, `CAMPAIGN_*_HOUR`, таймзону и quiet hours.
5. Админ-команды не работают: проверьте `ADMIN_TG_IDS`.
