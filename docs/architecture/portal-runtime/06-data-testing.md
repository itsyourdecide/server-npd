# Поток 6. PostgreSQL, миграции, конфигурация и проверка

Статус: current
Последняя проверка: 2026-10-12
Назначение: карта схемы БД, миграций, конфигурации и способов проверки
Источник истины для: не является источником истины; первичен код в portal/app/

[Карта всех потоков](../portal-runtime-walkthrough.md) · Код:
[`db/base.py`](../../../portal/app/db/base.py),
[`db/models.py`](../../../portal/app/db/models.py),
[`db/session.py`](../../../portal/app/db/session.py),
[`alembic/env.py`](../../../portal/alembic/env.py),
[`tests/`](../../../portal/tests/).

## Карта данных и владения

```text
User.id
 ├─ ExternalIdentity.user_id  (внешний issuer + subject)
 ├─ ApplicationSession.user_id (hash browser session token)
 ├─ UserQuota.user_id ───────> ComputePlan.id
 ├─ SshPublicKey.owner_user_id
 └─ VirtualMachine.owner_user_id
       ├─ VirtualMachine.ssh_public_key_id ─> SshPublicKey.id
       └─ Operation.virtual_machine_id ────> VirtualMachine.id
```

`User.id` — UUID внутреннего пользователя. Email хранится в
`ExternalIdentity` как атрибут способа входа, но не используется как FK
владения. `UserQuota.user_id` одновременно FK и primary key: одна строка
квоты на User в текущей схеме. `VirtualMachine.id` — Portal UUID;
`provider_vmid` и `provider_node` связывают его с Proxmox только после
выбора размещения. `Operation` принадлежит VM, а через неё — User.

Схема БД страхует сервисные проверки:

- `ExternalIdentity`: уникальная `(issuer, subject)`;
- `ApplicationSession`: уникальный `token_hash`;
- `ComputePlan`: уникальный `code`, неотрицательные лимиты;
- `UserQuota`: status только `active/suspended`;
- `SshPublicKey`: уникальное имя внутри владельца и глобальный fingerprint;
- `VirtualMachine`: допустимые статусы, положительные ресурсы, уникальный
  `provider_vmid`;
- `Operation`: допустимые тип/status, `attempts >= 0`, уникальный
  `idempotency_key`.

Ограничения БД — последняя защита от гонок/ошибок кода, но сами по себе они
не выбирают правильный HTTP-статус. Сервисные проверки дают понятные 403,
404 или 409 в обычных случаях. При конкурентной гонке сервисы перехватывают
`IntegrityError` от уникального индекса: после rollback'а повторная сверка
либо возвращает существующую запись как идемпотентный повтор (VM-операции),
либо поднимает специализированный конфликт 409 (SSH-ключи, чужой
idempotency-key). Callback логина в этой ситуации повторяет транзакцию
целиком, поэтому два параллельных входа одной identity завершаются двумя
обычными сессиями одного пользователя.

## Как модель оказывается в Alembic metadata

`Base` — общий `DeclarativeBase`. Каждый класс модели наследует `Base`,
поэтому его таблица регистрируется в `Base.metadata` **при импорте модуля**.
`app.db.models` импортирует все классы моделей в одном месте. Его
`__all__` задаёт публичные имена для `from app.db.models import *`, но
**не создаёт таблицы** и не управляет миграциями сам по себе.

`alembic/env.py` импортирует `Base` через `app.db.models` и выставляет
`target_metadata = Base.metadata`, а URL БД берёт из `settings.database_url`.
Поэтому `alembic revision --autogenerate` сравнивает подключённую БД с
зарегистрированными моделями. Автогенерация — **черновик изменения схемы**:
созданную миграцию следует читать до `upgrade`. Она не создаёт строки
`starter` сама, если в миграции нет явного `bulk_insert` или SQL.

В истории миграций есть важная последовательность:

1. users, external identities и application sessions;
2. compute plans и `starter`, затем user quotas;
3. backfill quotas для пользователей, созданных до появления этого правила;
4. virtual machines и operations, затем добавление phase, provider task ID,
   SSH-key FK и новых lifecycle operation types;
5. отдельная миграция удаляет прежний `max_running_vms`.

Новые миграции должны **добавляться** поверх истории, а не переписывать
применённые ревизии на общей БД. Модель описывает текущую схему; старые
ревизии могут содержать поля, которые позже были удалены.

Типичная проверка локальной development-БД из `portal/`:

```bash
.venv/bin/alembic current
.venv/bin/alembic revision --autogenerate -m "describe schema change"
# сначала прочитать созданный файл в alembic/versions/
.venv/bin/alembic upgrade head
```

`current` сообщает реально применённую ревизию, `upgrade head` меняет
схему БД. Не запускай его против другой БД, не проверив `DATABASE_URL`.

## Где открывается и заканчивается транзакция

`db/session.py` создаёт `engine` и `SessionLocal = async_sessionmaker(...)`.
Зависимость `get_db()` делает `async with SessionLocal() as db: yield db`.
FastAPI даёт обработчику эту `AsyncSession` и закрывает её после запроса.

Сравнение трёх операций SQLAlchemy:

| Вызов | Что происходит | Можно ли ещё откатить? |
|---|---|---|
| `db.add(obj)` | Python-объект начинает отслеживаться сессией. | Да. |
| `await db.flush()` | SQL INSERT/UPDATE отправляется в **текущую транзакцию**; появляются ID. | Да. |
| `await db.commit()` | Транзакция завершается, изменения становятся видны другим транзакциям. | Нет, нужен новый компенсирующий шаг. |

Поэтому `create_vm()` может после первого `flush` получить `vm.id` и
создать связанную `Operation`, не делая преждевременный commit. HTTP-роутер
делает commit после успеха всей сервисной функции. `db.rollback()` в
обработчике освобождает транзакцию после ожидаемой ошибки. OIDC callback и
logout используют `async with db.begin()` — он автоматически фиксирует
успешный блок или откатывает исключение. Worker не получает HTTP-сессию;
каждый его проход открывает собственный `SessionLocal`/`db.begin()`.

`SELECT ... FOR UPDATE` в `create_vm()` блокирует UserQuota для сериализации
параллельных созданий одного пользователя. В `enqueue_vm_operation()`
блокируется конкретная VM для сериализации её lifecycle-действий.
`FOR UPDATE SKIP LOCKED` в worker — другое применение: взять следующую
операцию очереди, не ожидая строку, которую уже взял другой worker.

Почему в коде разные способы чтения SQLAlchemy:

| Вызов | Когда подходит | Результат |
|---|---|---|
| `await db.get(Model, primary_key)` | Знаем первичный ключ таблицы. | Один ORM-объект или `None`. |
| `await db.scalar(select(Model).where(...))` | Нужны произвольные условия, например `owner_user_id`. | Первая колонка первой строки или `None`. |
| `await db.scalars(select(Model).where(...))` | Нужны многие ORM-объекты. | `ScalarResult`; `.all()` превращает его в список. |
| `(await db.execute(select(...))).one()` | Нужна строка из нескольких агрегатов/колонок и ожидается ровно одна. | `Row`; ноль или несколько строк — исключение. |

Поэтому `db.get(UserQuota, user.id)` корректен: `user_id` — primary key.
А `db.get(ComputePlan, code == "starter")` некорректен: `code` не primary
key, нужен `select(...).where(ComputePlan.code == "starter")`.

## Конфигурация процессов

| Процесс | Файл/класс | Что использует |
|---|---|---|
| FastAPI web | `app.core.config.Settings`, `.env` | PostgreSQL URL, OIDC client/issuer/secrets, cookie/CSRF settings. |
| Worker в fake-режиме | `WorkerModeSettings`, `.env.worker` | `WORKER_ADAPTER=fake`; Proxmox secret не нужен. |
| Worker в real-режиме | `OperationWorkerSettings`, `.env.worker` | Proxmox API URL, token, CA, timeout, pool/node/template/storage/Cloud-Init. |

В одном репозитории есть два набора настроек, но credentials Proxmox не
должны попадать в окружение web-процесса. `WORKER_ADAPTER` по умолчанию
`fake`. При выборе `proxmox` обязательные параметры валидируются при старте
worker. Реальный worker после запуска **немедленно** начнёт подбирать
имеющиеся pending operations; перед переключением режима нужно понять,
какие строки уже лежат в БД и куда он сможет воздействовать.

## Что именно проверяют тесты

Из каталога `portal/`:

```bash
.venv/bin/python -m pytest -q
```

Общая инфраструктура (`tests/conftest.py`): тесты работают с отдельной базой
`portal_test` (не с development-базой), схема накатывается миграциями один раз
за прогон, после каждого теста тестовые данные очищаются `TRUNCATE`, но
посевные данные миграций (план `starter`) сохраняются. `DATABASE_URL`
переопределяется в `conftest` до импортов приложения, поэтому web, worker и
HTTP-тесты прозрачным образом попадают в тестовую базу. Сидинг для worker- и
HTTP-тестов обязан делать `commit` — приложение читает собственными
сессиями; проверка состояния после чужих коммитов идёт через свежую сессию,
а не через объекты из identity map текущей.

| Тесты | Что доказывают | Чего не доказывают |
|---|---|---|
| `tests/identity/` (31) | CSRF, хранение хэша вместо токена, все 401-ветки, троттлинг `last_seen_at`, cookie-флаги, logout без `id_token_hint` (ID-002), retry callback при гонке. Мок только Keycloak. | Поведение живого Keycloak. |
| `tests/virtual_machines/` (16) | Квоты starter-плана, идемпотентные replay, детерминированные и реальные конкурентные гонки на констрейнтах Postgres. | Поведение Proxmox: адаптер — `FakeProxmoxAdapter`. |
| `tests/ssh_keys/` (11) | Парсинг ключей; конфликты имени/отпечатка, включая одновременный импорт двумя сессиями. | Реальную регистрацию ключей в гостевых ОС. |
| `tests/operations/` (40) | Recovery-матрицу фаз на быстрых фейках сессии. | Реальные транзакции; кандидаты на миграцию по образцу `test_start_recovery_database.py`. |
| `tests/workers/` (7) | Выбор fake/real адаптера; start-recovery целиком на реальной БД: `FOR UPDATE SKIP LOCKED`, маркер до провайдера, `RECONCILE_DELAY`-гейт без sleep. | Физический старт гостевой ОС. |
| `tests/web/test_dashboard.py` (11) | Формы create/start и dashboard на реальном приложении и реальной БД: коды ответов, экранирование, владение ресурсами. | — |

Каждая критичная ветка подтверждена мутационной проверкой: изменение
порядка проверок, удаление троттлинга, подмена статусов, потеря UPID,
снятие фильтра владельца и другие мутации ловятся соответствующим тестом.

Дополнительно `tests/fixtures/proxmox/` содержит сохранённые примеры
ответов API. Подменённый адаптер и fixture-ответ — не замена безопасному
интеграционному тесту на кластере.

Для ручной проверки полного **локального** пути нужны отдельно запущенные
PostgreSQL, web и operation worker в fake-режиме: создать VM, увидеть
`Operation.pending`, затем после проходов worker увидеть
`Operation.succeeded`/`VirtualMachine.running`. Для повторной отправки
нужно использовать **тот же** `idempotency_key`; для новой VM — новый.
Локальные тесты не должны включать real-режим worker случайно.

## Открытые ограничения, которые не стоит скрывать

- HTML-формы при ошибке пока показывают стандартный JSON FastAPI, а не
  понятное сообщение прямо в кабинете.
- HTML умеет создать и запустить VM; shutdown/stop/reboot/delete доступны
  только через JSON API. Удаление требует отдельного UI-подтверждения.
- Импорт/генерация SSH-ключа доступны через API, но не как HTML-форма.
- `GET /dashboard` содержит CSRF в HTML и пока не выставляет `no-store`;
  перед production следует завершить cache hardening.
- `oidc_cookie_secure` по умолчанию `False` для локальной разработки;
  production через HTTPS требует осознанной конфигурации.
- `ApplicationSession.last_seen_at` обновляется не чаще одного раза в пять
  минут и только у валидных сессий; срок жизни при этом фиксированный,
  а не скользящий.
- `shared_storage_gb` в quota API не измеряется; глобальная свободная
  ёмкость Proxmox не проверяется `create_vm()`.
- При `vm.create` провал может оставить частичный ресурс в Proxmox, тогда
  как `get_user_compute_usage()` не учитывает VM со статусом `failed`.
  Это требует сверки и политики cleanup до широкого доступа пользователей.
- Отдельные operator UI, аудит действий, retention и production-наблюдаемость
  не становятся готовыми от наличия таблицы `Operation` и логов worker.
- Плановые документы о Django/mail/HTCondor описывают будущие или прежние
  этапы; эта карта фиксирует только текущую FastAPI-реализацию.
