# NPD Portal

Новая реализация пользовательского портала вычислительного кластера NPD на
FastAPI.

## Структура

```text
app/        код приложения
tests/      автоматические тесты
templates/  HTML-шаблоны
static/     CSS, JavaScript и локальные frontend assets
```

Существующая Django-реализация временно сохранена в соседнем каталоге
`../portal-django/` как эталон поведения.

## Локальный запуск

```bash
cp .env.example .env
sudo docker compose up -d
uv sync
uv run uvicorn app.main:app --reload
```

После запуска:

- health check: <http://127.0.0.1:8000/health>;
- readiness check: <http://127.0.0.1:8000/health/ready>;
- OpenAPI: <http://127.0.0.1:8000/docs>.
