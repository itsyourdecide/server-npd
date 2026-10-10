# Поток 3. Запросы на VM: браузер, сервис и транзакция

[Карта всех потоков](../portal-runtime-walkthrough.md) · Код:
[`virtual_machines/router.py`](../../../portal/app/virtual_machines/router.py),
[`virtual_machines/services.py`](../../../portal/app/virtual_machines/services.py),
[`web/router.py`](../../../portal/app/web/router.py).

## Два интерфейса, один набор правил

| Действие | JSON API | HTML-форма | Сервис |
|---|---|---|---|
| Список своих VM | `GET /compute/vms` | `GET /dashboard` | SQL SELECT с `owner_user_id` |
| Создать | `POST /compute/vms` | `POST /dashboard/vms` | `create_vm()` |
| Запустить | `POST /compute/vms/{vm_id}/start` | `POST /dashboard/vms/{vm_id}/start` | `enqueue_vm_operation(..., "vm.start")` |
| Выключить корректно | `POST /compute/vms/{vm_id}/shutdown` | пока нет | `enqueue_vm_operation(..., "vm.shutdown")` |
| Выключить принудительно | `POST /compute/vms/{vm_id}/stop` | пока нет | `enqueue_vm_operation(..., "vm.stop")` |
| Перезагрузить | `POST /compute/vms/{vm_id}/reboot` | пока нет | `enqueue_vm_operation(..., "vm.reboot")` |
| Удалить | `POST /compute/vms/{vm_id}/delete` | пока нет | `enqueue_vm_operation(..., "vm.delete")` |
| Узнать результат | `GET /compute/vms/{vm_id}/operations/{operation_id}` | последние операции в `/dashboard` | SQL JOIN с проверкой владельца |

JSON API и HTML не вызывают друг друга HTTP-запросом. Оба вызывают один
сервис Python внутри web-процесса, поэтому бизнес-правила не раздваиваются.
API получает JSON-тело и заголовки `X-CSRF-Token`, `Idempotency-Key`;
HTML получает form-urlencoded поля `csrf_token` и `idempotency_key`.
`get_current_user()` обязателен для каждого маршрута; POST также требует
`verify_csrf()`.

## Показ кабинета и список VM

`web.dashboard()` читает `UserQuota` по `user.id`, затем план и usage. Три
дальнейших SELECT получают VM, SSH-ключи и последние 10 операций. Выборка
VM/ключей фильтрует `owner_user_id == user.id`; операции соединены с VM и
фильтруются по её владельцу. В шаблон передаются только результаты этих
запросов, CSRF и ключи идемпотентности для форм.

Для каждого GET создаётся новый UUID формы создания VM и новый UUID для
кнопки start каждой остановленной VM. Повторная отправка **той же открытой
формы** несёт тот же UUID; новый осознанный визит на страницу — новый UUID.
Кнопка start показывается только при `vm.status == "stopped"`, но это лишь
удобство UI: авторитетная проверка статуса и владельца находится в сервисе.

`my_vms()` JSON API тоже фильтрует `owner_user_id` и отдаёт ORM-объекты через
`response_model=list[VirtualMachineRead]`. Схема `VirtualMachineRead` не
содержит `owner_user_id`, provider credential или внутренние ошибки worker.

## Создание VM: точная цепочка

```text
браузер / API
  -> get_current_user() + verify_csrf()
  -> VirtualMachineCreate + UUID idempotency key
  -> create_vm(db, user.id, request_model, key)
     1. SELECT SshPublicKey WHERE id = key_id AND owner_user_id = user.id
     2. SELECT UserQuota WHERE user_id = user.id FOR UPDATE
     3. _get_existing_vm_for_create_request(db, key, user.id, request_model)
     4. проверить quota.status == active
     5. проверить image allowlist и минимальный размер диска
     6. SELECT ComputePlan; get_user_compute_usage(); _validate_vm_quota()
     7. db.add(VirtualMachine(status=pending)); await db.flush()
     8. db.add(Operation(type=vm.create, status=pending, phase=clone)); flush()
  -> обработчик: await db.commit()
  -> API: HTTP 201 + VirtualMachineRead
     HTML: HTTP 303 -> /dashboard#vms
```

`VirtualMachineCreate` — Pydantic-модель для **разрешённого ввода**: vCPU,
RAM, диск больше нуля, корректный `image_id` и UUID публичного ключа. Она
не принимает выбранный browser `owner_user_id`, статус, node или Proxmox
VMID. Для JSON задано `extra="forbid"`. HTML-обработчик сам собирает словарь
из известных полей формы и вызывает `model_validate()`.

`IMAGE_MIN_STORAGE_GB` сейчас допускает `almalinux-9` с минимумом 10 ГБ.
Pydantic проверяет форму значения, а сервис — продуктовую политику образа и
минимального диска. Эти проверки не взаимозаменяемы.

`UserQuota ... FOR UPDATE` удерживает блокировку до commit/rollback HTTP-
транзакции. Два одновременных создания одного владельца не могут оба пройти
проверку одного и того же свободного остатка. `_validate_vm_quota()`
сравнивает `usage + requested` отдельно по количеству VM, суммарным vCPU,
RAM и storage. Глобальная физическая ёмкость Proxmox **не** проверяется этой
функцией.

### Что делает idempotency при создании

`_get_existing_vm_for_create_request()` ищет `Operation` по глобальному
`idempotency_key`. Если записи нет, создание продолжается. Если найдена:

- operation должна иметь тип `vm.create`;
- её VM должна существовать и принадлежать тому же `User.id`;
- vCPU, RAM, disk, image и SSH-key ID должны совпадать с повтором.

При совпадении возвращается существующая VM: вторая запись не создаётся.
Несовпадение означает конфликт 409, а не новую VM. Новую одинаковую по
размеру VM создать можно, но **с новым ключом** и при достаточной квоте.
Уникальный индекс `Operation.idempotency_key` в БД защищает от дублирования
даже при гонке запросов; сервисная проверка даёт осмысленное поведение для
обычного повтора.

`db.flush()` здесь отправляет INSERT в открытую транзакцию, чтобы VM
получила ID для `Operation.virtual_machine_id`. Только `db.commit()` в
обработчике фиксирует обе строки. Если между ними ошибка — rollback убирает
обе. Worker увидит operation после commit, не после одного `flush`.

## Управление существующей VM: точная цепочка

Все lifecycle-маршруты зовут
`enqueue_vm_operation(db, user_id, vm_id, operation_type, key)`.
Он выполняет следующие проверки **в указанном порядке**:

1. Тип операции есть в `allowed_statuses`.
2. `SELECT VirtualMachine WHERE id == vm_id AND owner_user_id == user_id
   FOR UPDATE`. Не найдено — `LookupError`. Для чужой VM ответ такой же,
   как для несуществующей: клиент не получает информацию о чужом объекте.
3. `SELECT Operation WHERE idempotency_key == key`. При повторе того же
   `vm_id + operation_type` возвращается прежняя операция. Попытка применить
   тот же ключ к другому действию или VM — `ValueError`.
4. Нет другой операции этой VM со статусом `pending` или `processing`.
5. Текущий статус VM входит в разрешённый набор.
6. Добавляется `Operation(status="pending")`; `phase="shutdown"` сразу
   задаётся для `vm.reboot`, у остальных phase изначально `NULL`.
7. `flush()` создаёт ID операции; HTTP-обработчик делает commit.

Текущая таблица допустимости:

| Операция | Допустимый `VirtualMachine.status` при постановке | Конечный замысел |
|---|---|---|
| `vm.start` | `stopped` | `running` |
| `vm.shutdown` | `running` | `stopped`, штатное завершение |
| `vm.stop` | `running` | `stopped`, принудительное выключение |
| `vm.reboot` | `running` | `running` после shutdown → start |
| `vm.delete` | `stopped` | `deleted` после подтверждения удаления |

Эти правила проверяются при **постановке**, не HTML-кнопкой. После commit
операция только ожидает worker. `VirtualMachine.status` может не измениться
сразу: например, после start он останется `stopped` до подтверждения worker,
а активная pending operation блокирует второе действие.

## Разница HTTP-обработчиков

`virtual_machines.router._enqueue_lifecycle_operation()` — общий помощник
JSON-маршрутов. Он вызывает сервис, делает commit, преобразует `LookupError`
в 404, `ValueError` в 409, откатывает транзакцию при ошибках, затем refresh
ORM operation и отдаёт `OperationRead` со статусом 202. API-методы
`start_vm`, `shutdown_vm`, `stop_vm`, `reboot_vm`, `delete_vm` передают в этот
помощник только разный `operation_type`.

`web.vm_start()` делает то же для обычной HTML-формы, но сначала проверяет,
что `idempotency_key` является UUID (неверный формат — 422), и после commit
отвечает 303 на кабинет. Он не делает отдельный SELECT VM: это уже делает
сервис с проверкой владельца и блокировкой строки.

`web.dashboard_vms()` вызывает `create_vm()` и после commit отвечает 303.
Его `PermissionError` от приостановленной квоты становится 403, `ValueError`
политики/квоты/idempotency — 409, невалидная Pydantic-форма — 422.
JSON API создания использует те же сервисные ошибки, но успешный ответ —
201 с `VirtualMachineRead`.

## Чтение результата и границы авторизации

`operation_status(vm_id, operation_id, current_user, db)` делает SELECT
`Operation JOIN VirtualMachine` с тремя условиями: указанный `vm_id`,
указанный `operation_id` и `owner_user_id == current_user.id`. Если строка
не найдена, 404. URL с чужими ID не даёт обойти проверку владельца.
`OperationRead` показывает тип, status, phase, timestamps и нормализованный
`last_error_code`; `provider_task_id` наружу не отдаётся.

Список операций на HTML-странице тоже проходит через JOIN с VM и фильтр
владельца, но ограничен последними десятью записями. Это не полная
постраничная история и не автоматическое обновление в реальном времени.

## Важное разделение состояний

Одна VM может иметь `status="stopped"` и одновременно новую
`Operation(status="pending", operation_type="vm.start")`: ресурс ещё
остановлен, но команда уже заказана. `operation_type` отвечает на вопрос
«что сделать», `status` — «работа ожидает/идёт/завершена», `phase` — «на
каком внутреннем шаге». Их нельзя заменить одним общим полем. Следующая
глава разбирает, как worker меняет эти поля.
