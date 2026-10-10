# Поток 4. Operation worker и стадии исполнения

[Карта всех потоков](../portal-runtime-walkthrough.md) · Код:
[`workers/operation_worker.py`](../../../portal/app/workers/operation_worker.py),
[`operations/services.py`](../../../portal/app/operations/services.py),
[`operations/models.py`](../../../portal/app/operations/models.py).

## Почему операция хранится в БД

HTTP-запрос короткий, а clone/resize/start в Proxmox асинхронны и могут
пережить перезапуск web-процесса. `Operation` сохраняет **намерение** в той
же PostgreSQL-транзакции, что и новую VM. Worker затем читает это намерение
без участия browser. Отдельный брокер сейчас не требуется: PostgreSQL
выполняет роль долговечной очереди.

`Operation.operation_type` перечисляет `vm.create`, `vm.start`,
`vm.shutdown`, `vm.stop`, `vm.reboot`, `vm.delete`. `status` ограничен
`pending`, `processing`, `succeeded`, `failed`. `phase` уточняет конкретный
шаг (например, создание состоит из четырёх). `attempts` считает отправки
команд, а не каждый проход цикла опроса. `provider_task_id` хранит известный
UPID провайдера. `last_error_code` — нормализованный код, не обязательно весь
текст ошибки. Уникальный `idempotency_key` связывает повторы HTTP-запроса с
одной operation.

## Запуск и выбор работы

`operation_worker.main()` настраивает logging, через
`create_worker_adapter()` выбирает fake либо HTTP-адаптер и вызывает
`run_worker(adapter)`. `run_worker()` бесконечно вызывает `run_once()`:
после обработанной строки ждёт 1 секунду, без работы — 2 секунды, после
исключения логирует его и ждёт 2 секунды. Это polling БД, а не
прослушивание push-уведомлений.

`run_once()` открывает `SessionLocal()` и `db.begin()`, выбирает одну
`Operation` с `status IN (pending, processing)`, сортирует по `updated_at`
и использует `FOR UPDATE SKIP LOCKED`. Блокировка даёт одному экземпляру
worker право продвигать строку; другой экземпляр пропустит заблокированную.

Не любая `processing`-строка опрашивается каждую секунду. Условия выборки
разрешают:

- все `pending`;
- `dispatch*` только после `DISPATCH_GRACE = 5 минут` — чтобы другой
  worker не объявил живой сетевой вызов потерянным;
- `reconcile*` и `poll_backoff*` после 10 секунд;
- строку с известным `provider_task_id`, когда она не в `poll_backoff`.

`needs_review_*` без UPID не подходит под автоматический опрос: это
осознанная остановка для ручного разбора неизвестного результата.
Если обработка внутри транзакции бросит исключение, `db.begin()` откатится;
внешний цикл залогирует ошибку и попробует снова позже. Это не означает,
что безопасно повторять внешний Proxmox-запрос: для него есть отдельный
протокол dispatch/reconcile.

## Почему Proxmox вызывается вне транзакции БД

Сеть может зависнуть, сервер может принять команду, а ответ — потеряться.
Если держать `FOR UPDATE` во время HTTP-вызова, блокировка длится всю сеть.
Если после timeout бездумно повторить POST, можно запустить/клонировать
ресурс дважды. Текущий основной путь делает так:

```text
Транзакция A: выбрать и заблокировать Operation
  -> сохранить status=processing, phase=dispatch_*, attempts += 1
  -> COMMIT, освободить блокировку

Без транзакции: adapter.<command>() обращается к Proxmox

Транзакция B: вновь заблокировать ту же Operation
  -> сохранить UPID или подтверждённый конечный результат
  -> COMMIT
```

Если команда выбросила исключение или транзакция B не смогла сохранить
результат, worker **не должен слепо повторять** её. Сохранённый
`dispatch_*` и отсутствие UPID приводят к чтению фактического состояния
через `reconcile_*`. Разделение «подготовить / отправить / сохранить» —
центральная причина существования нескольких похожих функций.

## `vm.create`: четыре шага

Основной путь `run_once()` начинается с
`Operation(status=pending, phase=clone)` и VM без provider placement.

| Шаг | Функции в порядке вызова | Что сохраняется |
|---|---|---|
| Выбор места | `process_create_vm_operation()` → `start_create_vm_operation()` → `_build_create_vm_request()` → `adapter.choose_clone_target()` | `vm.provider_node` и `vm.provider_vmid`; clone ещё **не** отправлен. |
| Clone | `prepare_create_vm_dispatch()` → `adapter.clone_vm()` → `finish_create_vm_dispatch()` | Маркер `dispatch_create_clone`, затем UPID/ожидание либо переход к `configure`. |
| Configure | `prepare_create_vm_dispatch()` → `adapter.configure_vm()` → `finish_create_vm_dispatch()` | CPU, RAM, Cloud-Init, SSH public key, tags; затем `resize`. |
| Resize | `prepare_create_vm_dispatch()` → `adapter.resize_vm_disk()` → `finish_create_vm_dispatch()` | Размер системного диска; затем `start`. |
| Initial start | `prepare_create_vm_dispatch()` → `adapter.start_vm()` → `finish_create_vm_dispatch()` | После подтверждения: operation `succeeded/complete`, VM `running`. |

`_build_create_vm_request()` поднимает связанные данные из БД: ID и
параметры VM плюс **публичный** SSH-ключ. Он проверяет, что ключ существует
и принадлежит тому же владельцу. Адаптер получает типизированный
`CreateVmRequest`, а не произвольный JSON от browser.

Первый проход clone специально **только фиксирует** node+VMID: если worker
упадёт между выбором нового VMID и клонированием, следующий проход
использует тот же сохранённый target. При `prepare_create_vm_dispatch()`
операция переходит в `processing/dispatch_create_<phase>` и `attempts`
увеличивается. После сетевого вызова `finish_create_vm_dispatch()` сверяет,
что результат относится к сохранённым node+VMID. Если адаптер вернул
`ProviderTask`, его UPID сохраняется, а phase становится обычным именем
шага. Если `None` означает синхронное завершение configure/resize/start,
функция сразу переводит операцию к следующему шагу.

Когда UPID есть, следующий `run_once()` зовёт
`process_create_vm_operation()` → `refresh_create_vm_operation()` →
`adapter.get_task_status()`. `running` оставляет шаг в обработке,
`succeeded` передвигает `clone → configure → resize → start → complete`,
`failed` ставит operation и VM в `failed`. После успеха последней фазы
VM становится `running`.

При потере результата clone или start
`reconcile_create_vm_operation()` читает фактическое power state VM.
Подтверждённый законченный clone (VM stopped и без lock) ведёт к configure;
подтверждённый start (VM running и без lock) завершает операцию. Для
configure/resize одного power state недостаточно, чтобы доказать применённые
параметры, поэтому код переводит phase в `needs_review_*` и не отправляет
команду повторно вслепую.

В `operations/services.py` есть также `start_configure_vm_operation()`,
`start_resize_vm_operation()` и `start_initial_vm_operation()` — ветки
прямого `process_create_vm_operation()` для `pending`. В текущем
`operation_worker.run_once()` после выбора placement pending-фазы
configure/resize/start направляются через **prepare/dispatch/finish**, а
эти прямые функции остаются частью сервисного кода и тестовых сценариев.
Это важно при чтении файла: наличие функции не означает, что основной
worker вызывает её на каждом шаге.

## `vm.start` для уже существующей VM

```text
run_once() берёт pending vm.start
  -> prepare_start_vm_dispatch()
     -> _get_lifecycle_vm(): VM существует и имеет node+VMID
     -> processing / dispatching, attempts += 1
  -> COMMIT
  -> adapter.start_vm() вне транзакции
  -> finish_start_vm_dispatch() в новой транзакции
     -> task есть: provider_task_id и phase=await_task
     -> task=None: сразу succeeded/complete, VM=running
  -> при известном task: process_start_vm_operation()
     -> get_task_status() -> running / succeeded / failed
```

`reconcile_start_vm_operation()` используется, если нет известного UPID
после возможной отправки команды. Он спрашивает фактическое состояние VM;
только `running` без lock подтверждает успех. Иначе остаётся
`processing/reconcile` с `provider_outcome_unknown`, без второго start POST.

Конкретный пример неоднозначного ответа:

```text
БД: vm.start / pending
worker: prepare_start_vm_dispatch -> processing / dispatching -> COMMIT
Proxmox: команду принял и запустил VM
сеть: ответ с UPID потерян, вызов выбросил timeout
worker: записал reconcile, UPID неизвестен
следующий проход: get_vm_power_state -> running, lock=False
worker: succeeded / complete, VM=running
```

Если бы worker повторил `POST start` сразу после timeout, он не знал бы,
не была ли первая команда уже принята. Маркер `dispatching` делает этот
неизвестный исход видимым и направляет следующий шаг на чтение состояния.

## `vm.shutdown`, `vm.stop`, `vm.reboot`, `vm.delete`

Для этих типов `run_once()` использует общую пару
`prepare_lifecycle_dispatch()` и `finish_lifecycle_dispatch()`.
Первая проверяет operation, получает VM с node+VMID, ставит
`processing/dispatch_*`, увеличивает attempts и фиксирует этот маркер.
При delete VM дополнительно получает `status=deleting`. После commit worker
вызывает нужный метод адаптера; результат обрабатывает в новой транзакции.

| Тип | Отправка | После подтверждённого успеха |
|---|---|---|
| `vm.shutdown` | `adapter.shutdown_vm()` | operation `succeeded`, VM `stopped` |
| `vm.stop` | `adapter.stop_vm()` | operation `succeeded`, VM `stopped` |
| `vm.reboot` | `adapter.shutdown_vm()`, затем отдельной фазой `adapter.start_vm()` | operation `succeeded`, VM `running` |
| `vm.delete` | `adapter.delete_vm()` | operation `succeeded`, VM `deleted` |

У `vm.reboot` **нет одного вызова** `adapter.reboot_vm()`: фазы `shutdown`
и `start` сохраняются в БД между итерациями. После подтверждённого shutdown
operation снова `pending/phase=start`, VM `stopped`. Это позволяет пережить
перезапуск worker между выключением и запуском.

Для известного UPID `process_power_off_vm_operation()`,
`process_reboot_vm_operation()` и `process_delete_vm_operation()` опрашивают
task. Их ветки `pending` умеют отправить команду напрямую, но основной
`run_once()` для pending lifecycle использует защищённый
`prepare_lifecycle_dispatch()` и отправку **после commit**. При task failure
operation становится `failed`; для failed delete VM остаётся `deleting`,
чтобы не освобождать квоту до доказанного удаления.

Если ответ команды потерян, `reconcile_lifecycle_operation()` читает
`adapter.get_vm_power_state()`: stopped подтверждает shutdown/stop либо
первую фазу reboot, running подтверждает вторую фазу reboot, missing
подтверждает delete. Если цель не доказана, остаётся `reconcile_*` без
повторной отправки. При обычном delete статус `deleted` также освобождает
учёт квоты, потому что `get_user_compute_usage()` не суммирует deleted VM.

## Как читать ошибки и зависшие операции

- `pending` — команда ещё не отправлена; worker должен подобрать её.
- `processing` + UPID — есть известная task; worker опрашивает её.
- `processing/dispatch_*` без UPID — команда могла быть отправлена, но
  результат ещё не сохранён; после grace нужна сверка, не повтор POST.
- `processing/reconcile_*` — фактический результат ещё не доказан;
  повторяется read-only проверка состояния.
- `needs_review_*` — автоматическая проверка недостаточна; требуется
  операторский разбор. Текущий код не даёт отдельного UI для него.
- `failed` — провайдер сообщил ошибку задачи; это не универсальное
  доказательство, что в Proxmox не осталось частичных ресурсов.

Сам worker логирует ход работы, но ещё не является полноценной системой
наблюдаемости/операторских уведомлений. Нельзя считать `Operation.status`
или `VirtualMachine.status` мгновенным отражением Proxmox без сверки.
