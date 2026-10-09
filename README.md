# Квитто — API платежей

Сервис, через который онлайн-школа принимает оплату курса: тарифы, создание платежа (карта, СБП, рассрочка), просмотр платежей и вебхук банка о смене статуса. Требования — [REQUIREMENTS.md](REQUIREMENTS.md).

**Стек:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic, PostgreSQL 17, pytest + httpx, uv.

## Быстрый старт

```bash
cp .env.example .env   # заполнить POSTGRES_* и согласованные с ними DATABASE_URL / TEST_DATABASE_URL
docker compose up --build
```

- API: http://localhost:8000, Swagger: http://localhost:8000/docs
- `app` стартует после healthcheck `db`, применяет миграции (`alembic upgrade head`) и идемпотентно заводит тарифы.
- Тестовая база `POSTGRES_TEST_DB` создаётся init-скриптом при **первой** инициализации volume. После смены реквизитов в `.env` пересоздать volume: `docker compose down -v`.
- Порты на хосте меняются через `POSTGRES_HOST_PORT` и `APP_HOST_PORT`.

## Локальная разработка

```bash
uv sync                        # .venv с зависимостями, включая dev
docker compose up -d db        # только Postgres
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

### Тесты и проверки

Тесты идут против настоящего PostgreSQL (`TEST_DATABASE_URL`), SQLite не используется. Схема тестовой базы пересоздаётся на каждую сессию pytest, таблицы очищаются перед каждым тестом. Юнит-тесты расчётов работают без БД.

```bash
docker compose up -d db
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy app migrations tests
```

## API

| Метод | Путь | Ответы |
|---|---|---|
| GET | `/tariffs` | 200 |
| POST | `/payments` | 201 создан · 200 ключ уже использован · 422 |
| GET | `/payments/{id}` | 200 · 404 · 422 (не UUID) |
| GET | `/payments?email=&status=` | 200 · 422 (неизвестный статус) |
| POST | `/webhooks/bank` | 200 `{"result":"ok"}` · 404 · 409 `{"error":"invalid_transition"}` · 422 |

```bash
curl -X POST localhost:8000/payments \
  -H "Content-Type: application/json" -H "Idempotency-Key: order-42" \
  -d '{"tariff_id":"standard","email":"user@example.com","method":"installment","installment_months":3,"promo_code":"kvitto10"}'

curl -X POST localhost:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -d '{"payment_id":"<id>","status":"succeeded"}'
```

Все суммы — целые копейки. Тарифы: `basic` 990000, `standard` 1990000, `premium` 2990000. Промокод `KVITTO10` даёт 10%.

## Структура

```
app/
  main.py          FastAPI, lifespan: seed тарифов
  config.py        настройки из окружения / .env
  db.py            async engine и сессии
  promo.py         справочник промокодов
  seed.py          идемпотентный upsert тарифов
  api/             роутеры: tariffs, payments, webhooks
  models/          SQLAlchemy-модели и перечисления
  schemas/         Pydantic-схемы запросов и ответов
  services/        бизнес-логика: pricing, transitions, payments, tariffs
migrations/        Alembic, одна начальная миграция
docker/            entrypoint (миграции + запуск), init-скрипт тестовой БД
tests/             pytest: юнит-тесты расчётов и API-тесты против Postgres
```

## Решения, не описанные в ТЗ

**Данные**
- Названия тарифов: «Базовый», «Стандарт», «Премиум». Seed — upsert: при старте цена и название приводятся к значениям из кода.
- Перечисления в БД — `VARCHAR` + `CHECK`, а не нативный `ENUM` Postgres. `schedule` — `bigint[]`.
- CHECK-ограничения: неотрицательные `price`, `amount`, `discount`; для `installment` — `installment_months` ∈ {3, 6, 12} и длина `schedule` равна числу месяцев, для `card`/`sbp` оба поля `NULL`. Равенство `sum(schedule) == amount` гарантирует сервис, не БД.

**Создание платежа**
- `"installment_months": null` при `card`/`sbp` равнозначно отсутствию поля, 422 только на число.
- Промокод из пустой строки или пробелов — отсутствие промокода. В БД хранится нормализованным (`KVITTO10`).
- Email валидируется `EmailStr`: домен приводится к нижнему регистру, из формы `Имя <a@b.c>` остаётся адрес.
- Лишние поля в теле игнорируются.
- Бизнес-ошибки — `422 {"detail": "Unknown tariff"}` / `{"detail": "Unknown promo code"}`.

**Идемпотентность**
- Пустой или пробельный `Idempotency-Key` — отсутствие ключа. Ключ длиннее 255 символов — 422.
- Порядок проверок: структура тела (FastAPI) → поиск по ключу → тариф и промокод. Повтор с невалидным телом получает 422, повтор с неизвестным промокодом — 200 и существующий платёж.

**Чтение**
- `created_at` в ответе — UTC с точностью до секунд: `2026-10-09T13:04:00Z`. В БД хранится с микросекундами.
- Сортировка списка — `created_at DESC, id DESC`. Пагинации нет.
- Фильтр `email` — без учёта регистра. Пустые `?email=` и `?status=` — отсутствие фильтра.
- `/tariffs/` и `/payments/` со слешем — 307 на путь без слеша (поведение FastAPI).

## Известные ограничения

- **Вебхук банка не аутентифицирован** — нет подписи, секрета или фильтра по IP. Любой, кто знает `payment_id`, может сменить статус.
- Фильтр по `email` сравнивает `lower(email)`, поэтому обычный индекс `ix_payments_email` для него не используется; при росте данных нужен функциональный индекс.
- Ошибка «`installment_months` при `card`/`sbp`» возвращается с `loc: ["body"]`, а не на поле.
