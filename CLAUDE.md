# Call Analyzer — Architecture Notes

AI-платформа анализа аудиозвонков. По умолчанию — фрод-детекция, с профилями — произвольный анализ через Gemini API.

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy 2.0 (async), asyncpg, PostgreSQL 17
- **AI**: Gemini API (через httpx proxy), модель gemini-2.5-flash
- **Frontend**: Jinja2 + Tailwind CSS + HTMX (CDN)
- **CLI**: Typer
- **Migrations**: Alembic (async)
- **Packaging**: uv, pyproject.toml
- **Deploy**: Docker Compose (db + migrate + app)

## Development Commands

```bash
docker compose up -d --build          # Запуск всего стека
uv run alembic upgrade head           # Миграции
uv run ca serve                      # Локальный запуск (без Docker)
uv run pytest                         # Тесты
```

## Project Structure

```
src/call_analyzer/
├── app.py              # FastAPI factory, lifespan (запуск worker), static mount
├── api.py              # REST API: /api/v1 (calls, profiles, stats, webhook)
├── web.py              # Web UI: Jinja2 routes (upload, calls, profiles)
├── models.py           # ORM: Profile, Call, AnalysisResult, ProfileResult
├── database.py         # async engine + sessionmaker
├── config.py           # Pydantic Settings
├── analyzer.py         # build_prompt(), analyze_call(), analyze_file(), analyze_bytes()
├── worker.py           # worker_loop() — фоновая обработка с семафором
├── gemini_client.py    # generate_content() — HTTP-клиент Gemini API
├── audio.py            # detect_format(), encode_base64()
├── cli.py              # Typer: analyze, list, stats, serve, profile subgroup
├── notifications.py    # Email-оповещения о фроде
├── external_storage.py # ABC ExternalStorageClient (заглушка)
└── watcher.py          # Watchdog: мониторинг директории
templates/              # Jinja2: base, index, calls, call_detail, profiles, profile_form, partials/
static/                 # CSS/JS
alembic/versions/       # 001-005 миграции
```

## Key Architectural Decisions

### Dual Result Model
- **AnalysisResult** — фрод-детекция (без профиля): `is_fraud`, `fraud_score`, `fraud_categories`, `reasons`, `transcript`
- **ProfileResult** — произвольный анализ (с профилем): `data` (JSONB), `transcript`
- У Call может быть либо `analysis`, либо `profile_result`, зависит от наличия `profile_id`

### Three Prompt Scenarios (analyzer.py → build_prompt)
1. **Нет профиля** → `ANALYSIS_PROMPT` (встроенный фрод-промпт)
2. **custom mode** → `profile.custom_prompt` + trigger words
3. **template mode** → собирается из `expert`, `main_task`, `fields_for_json` + trigger words

### Async Worker (worker.py)
- Поллит БД каждые 1 сек, берёт pending calls (FIFO by created_at)
- `asyncio.Semaphore(worker_concurrency)` ограничивает параллелизм (default=5)
- При старте: сбрасывает зависшие `processing` → `pending`

### HTMX Polling
- После загрузки: `hx-trigger="every 3s"` поллит `/calls/{id}/status`
- Автозамена через `hx-swap="outerHTML"`

### ExternalStorageClient
- Абстракция (`external_storage.py`) для будущей интеграции с S3/GCS
- Текущая реализация: `StubStorageClient` (raises NotImplementedError)

## DB Models — Key Constraints

- `Profile.name` — UNIQUE
- `ProfileResult.call_id` — UNIQUE (one-to-one с Call)
- `Call.profile_id` → FK profiles.id, **ondelete=SET NULL**
- `AnalysisResult.call_id` → FK calls.id, **ondelete=CASCADE**
- `ProfileResult.call_id` → FK calls.id, **ondelete=CASCADE**
- Call relationships: `cascade="all, delete-orphan"` на analysis и profile_result

## Environment Variables

Key `.env` settings:
- `DATABASE_URL` — PostgreSQL async connection string
- `GEMINI_PROXY_URL` — Gemini API proxy endpoint
- `GEMINI_PROJECT_ID`, `GEMINI_MODEL`, `GEMINI_LOCATION`
- `UPLOAD_DIR`, `WATCH_DIR`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO`
