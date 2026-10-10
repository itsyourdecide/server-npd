# Поток 5. От worker до Proxmox API

[Карта всех потоков](../portal-runtime-walkthrough.md) · Код:
[`proxmox/contracts.py`](../../../portal/app/proxmox/contracts.py),
[`proxmox/fake.py`](../../../portal/app/proxmox/fake.py),
[`proxmox/http_adapter.py`](../../../portal/app/proxmox/http_adapter.py),
[`proxmox/client.py`](../../../portal/app/proxmox/client.py),
[`workers/adapter.py`](../../../portal/app/workers/adapter.py).

## Зачем три уровня

```text
operation_worker / operations.services
           │  типизированные действия с VM
           ▼
ProxmoxAdapter (Protocol)
    ├── FakeProxmoxAdapter: локальная имитация
    └── HttpProxmoxAdapter: политика и интерпретация Proxmox
                       │  конкретные HTTP endpoints и JSON
                       ▼
                 ProxmoxClient
                       │  HTTPS + API token + CA
                       ▼
                   Proxmox API
```

Worker не строит URL и не знает формата JSON Proxmox. Он вызывает
`adapter.clone_vm`, `adapter.start_vm` и другие действия по контракту.
`HttpProxmoxAdapter` решает, **можно ли** выполнить действие с ожидаемой VM,
и преобразует ответ в типизированный результат. `ProxmoxClient` выполняет
HTTP и проверяет минимальную форму ответа. Это позволяет запускать тот же
worker с fake без credentials и тестировать обработку стадий отдельно от
сетевого API.

## Как выбирается адаптер и где лежат credentials

`create_worker_adapter()` читает `WorkerModeSettings.worker_adapter` из
`.env.worker` (`fake` по умолчанию). В fake-режиме создаёт
`FakeProxmoxAdapter` и **не требует** токен/CA Proxmox. В режиме `proxmox`
создаёт `OperationWorkerSettings`, затем `ProxmoxClient`, передаёт его в
`HttpProxmoxAdapter` и закрывает `AsyncClient` через `aclose()` при выходе.

`OperationWorkerSettings` содержит API URL, token ID/secret, путь к CA,
timeout, target node, pool, шаблон, storage и Cloud-Init настройки. Эти
переменные предназначены отдельному worker-процессу. Web читает
`app.core.config.Settings`, где Proxmox token отсутствует. Совпадение
кодовой базы не должно означать, что web-процессу выдали credentials worker.

## Типы данных между worker и адаптером

| Тип | Содержимое и смысл |
|---|---|
| `CreateVmRequest` | Portal UUID, разрешённый image ID, vCPU/RAM/disk и **публичный** SSH-ключ. Собирается из БД функцией `_build_create_vm_request()`. |
| `ProviderPlacement` | Выбранные `node + vmid`. Сохраняются в `VirtualMachine` до clone. |
| `ProviderTask` | `task_id` (для Proxmox это UPID), `node`, `vmid`; нужен для опроса конкретной задачи. |
| `ProviderTaskStatus` | Нормализованный `running/succeeded/failed` и код ошибки. |
| `ProviderCloneResult` | `submitted` с task, `in_progress` или `succeeded` без task. |
| `ProviderDeleteResult` | Такие же три состояния для delete. |
| `ProviderVmState` | Наблюдаемое `running/stopped/missing` плюс `locked`. |

`None` из `configure_vm`, `resize_vm_disk`, `start_vm`, `shutdown_vm` или
`stop_vm` означает, что адаптер считает желаемый результат уже достигнутым
либо завершившимся без отдельной асинхронной task. Это **не** «запрос
потерялся»: операции при таком результате переходят на следующую фазу или
завершаются.

## Защита от действия над чужой VMID

`HttpProxmoxAdapter._vm_name(portal_vm_id)` формирует `npd-<Portal UUID>`.
Перед мутацией `_find_owned_vm_resource(portal_vm_id, node, vmid)` вызывает
`ProxmoxClient.find_vm_resource(vmid)` и проверяет четыре свойства найденного
ресурса: `type == "qemu"`, имя равно ожидаемому, pool равен выделенному
порталу и node равен сохранённому. Несовпадение вызывает
`ProviderResourceConflictError`, а не попытку «исправить» чужую VM.
При отсутствии ресурса возвращается `None`, и вызывающий метод решает,
создать ли его, считать удалённым или сообщить ошибку.

Эта проверка — защита от ошибки VMID/перемещения/чужого ресурса. Она не
заменяет Proxmox ACL token и не сверяет все возможные свойства VM. Именно
поэтому отдельный service account, ограниченный pool/storage, остаётся
важным даже при проверках в коде.

## Создание в HTTP-адаптере по шагам

1. `choose_clone_target(request)` вызывает
   `client.get_next_vmid()` (`GET cluster/nextid`) и выбирает настроенный
   `target_node`. Worker сначала сохраняет эту пару в Portal DB.
2. `clone_vm(request, node, vmid)` проверяет node и `image_id` против
   конфигурации шаблона. Если ресурс с ожидаемыми именем/pool/node уже есть:
   lock `clone` даёт `in_progress`, отсутствие lock — `succeeded`, иной lock
   — конфликт. Если ресурса нет, `client.clone_vm()` вызывает API шаблона с
   `newid`, `name=npd-UUID`, `full=1`, storage, pool и target. Возвращённый
   UPID становится `ProviderTask`, результат — `submitted`.
3. `configure_vm()` требует существующий **свой** ресурс без lock. Через
   `client.configure_vm()` задаёт cores, memory, `ciuser`, сетевые/DNS
   параметры Cloud-Init, публичный `sshkeys`, protection и tags
   `npd-portal;npd-UUID`. Если Proxmox возвращает UPID, worker ждёт task;
   если `None` — переходит дальше.
4. `resize_vm_disk()` снова проверяет ресурс и lock, затем читает текущий
   `maxdisk` из `status/current`. Если диск уже нужного размера — `None`;
   если больше запрошенного — ошибка, потому что уменьшение не выполняется;
   если меньше — `PUT .../resize` для `scsi0` и ожидание UPID.
5. `start_vm()` читает фактическое power state: `running` → `None`, `stopped`
   без lock → `POST .../status/start` и task, missing/lock/иной статус →
   ошибка. После подтверждения worker сохраняет `VirtualMachine.running`.

`full=1` в clone — полная копия диска, не linked clone. Это часть запроса
`ProxmoxClient.clone_vm()`, а не самостоятельная настройка browser.

## Lifecycle в HTTP-адаптере

`get_vm_power_state()` проверяет target node и принадлежность ресурса,
затем читает `status/current`; возвращает `missing`, `running` или `stopped`
и признак lock из resource/status. Эта **read-only** функция важна для
reconciliation после потерянного ответа.

`_get_owned_vm_status()` строже: missing и lock считаются ошибкой. Его
используют `shutdown_vm()` и `stop_vm()`; если VM уже stopped, возвращается
`None`, иначе вызывается соответствующий Proxmox endpoint. Shutdown —
штатное завершение с timeout и `forceStop=0`; stop — принудительное.

`delete_vm()` проверяет node, принадлежность и фактический `stopped`.
Missing даёт `ProviderDeleteResult(succeeded)` — повтор после успешного
удаления не должен падать. Lock даёт `in_progress`, чтобы не отправлять
второй DELETE вслепую. Иначе `client.delete_vm()` выполняет DELETE с
`purge=1`, возвращает task. Worker помечает VM `deleted` только после
подтверждения результата.

У `ProxmoxClient` есть метод `reboot_vm()` с Proxmox endpoint, но текущий
`ProxmoxAdapter` и worker **его не используют**: Portal выполняет reboot
как две подтверждаемые фазы shutdown → start.

## Что делает низкоуровневый `ProxmoxClient`

Конструктор создаёт `httpx2.AsyncClient` с базовым URL, заголовком
`Authorization: PVEAPIToken=...`, TLS-проверкой через указанный CA-файл,
timeout, `follow_redirects=False` и `trust_env=False`. Даже в локальной
сети TLS защищает token и ответ API от перехвата/подмены; CA позволяет
проверить, что worker разговаривает с нужным Proxmox endpoint.

`_request_data(method, path, data=None, params=None)` — общая нижняя
функция. Она делает запрос, вызывает `raise_for_status()`, разбирает JSON,
требует объект с полем `data` и возвращает **значение этого поля**. Поэтому
методы выше не повторяют HTTP/JSON-обвязку. `data` используется для form
параметров POST/PUT, `params` — для query string, например `type=vm` или
`purge=1`. `path` всегда относителен к API base URL.

| Метод клиента | Proxmox API path и назначение |
|---|---|
| `get_next_vmid()` | `GET cluster/nextid`, ожидает строку с положительным VMID. |
| `list_vm_resources()` / `find_vm_resource()` | `GET cluster/resources?type=vm`, ищет ровно один ресурс с VMID. |
| `clone_vm()` | `POST nodes/{source}/qemu/{template}/clone`, ожидает UPID. |
| `configure_vm()` | `POST nodes/{node}/qemu/{vmid}/config`, допускает UPID либо `None`. |
| `resize_vm_disk()` | `PUT nodes/{node}/qemu/{vmid}/resize`, ожидает UPID. |
| `start_vm()`, `shutdown_vm()`, `stop_vm()` | `POST .../status/{action}`, ожидают UPID. |
| `delete_vm()` | `DELETE nodes/{node}/qemu/{vmid}?purge=1`, ожидает UPID. |
| `get_task_status()` | `GET nodes/{node}/tasks/{encoded UPID}/status`. |
| `get_vm_current_status()` | `GET nodes/{node}/qemu/{vmid}/status/current`, сверяет VMID ответа. |

`get_version()` и `get_nodes()` — диагностические read-only методы клиента.
Основной цикл `operation_worker.run_once()` их сейчас не вызывает.
`app.proxmox.test_fake.main()` — ручная локальная проба fake-адаптера, не
часть web или бесконечного worker loop.

`HttpProxmoxAdapter.get_task_status()` дополнительно проверяет, что ответ
относится к ожидаемому UPID. Proxmox `status="running"` остаётся running;
`status="stopped"` с `exitstatus="OK"` становится succeeded, иной
exitstatus — failed с `proxmox_task_failed`. Таким образом HTTP/Proxmox-
специфичные слова не расползаются по worker.

## Fake для локальной разработки

`FakeProxmoxAdapter` хранит VM, power state и задачи в памяти одного
процесса. `_vmid_for_vm_id()` детерминированно выводит числовой fake VMID
из Portal UUID; `choose_clone_target()` всегда возвращает `fake-node`.
`clone_vm()` добавляет VM в словарь, task сразу имеет `succeeded`;
`configure_vm()` завершается без task; resize/start/shutdown/stop/delete
создают fake task с предсказуемым ID. Методы проверяют, что node и VMID
соответствуют ожидаемым. `get_task_status()` может распознать ранее
сформированный fake task ID даже если словарь task пуст, но вся fake VM/
power-state модель не является долговечным Proxmox.

Fake показывает, что web → DB → worker → adapter связаны правильно. Он **не
проверяет** Proxmox ACL, TLS, реальную ёмкость, Cloud-Init, сеть гостевой VM
или сохранность ресурсов после рестарта fake-процесса. Для настоящего
адаптера есть отдельные fixture-тесты HTTP-ответов и затем необходима
контролируемая проверка на кластере.
