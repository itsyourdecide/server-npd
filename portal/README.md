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

## Веб-интерфейс

`/` — публичная страница со ссылками на вход и регистрацию через Keycloak.
После входа браузер попадает на `/dashboard`: там показаны квота, VM,
публичные SSH-ключи и последние операции текущего пользователя. HTML-формы
создают VM и запускают остановленную VM; остальные lifecycle-действия и
импорт/генерация SSH-ключей пока доступны через JSON API. Мутирующие запросы
проверяют CSRF. Подробные связи маршрутов, сервисов, транзакций, worker и
адаптера описаны в
[карте работающего кода](../docs/architecture/portal-runtime-walkthrough.md).

## Worker виртуальных машин

`uv run python -m app.workers.operation_worker` по умолчанию использует
`FakeProxmoxAdapter`; для этого не нужны токен и сертификат Proxmox.
Переключатель `WORKER_ADAPTER` можно задать в `.env.worker`:
`fake` (по умолчанию) или `proxmox`. В режиме `proxmox` обязательны все
`PROXMOX_*` параметры из `.env.worker.example`.

Не запускайте реальный режим до проверки подключения и ожидающих операций
в БД: воркер сразу начнёт их обрабатывать.
