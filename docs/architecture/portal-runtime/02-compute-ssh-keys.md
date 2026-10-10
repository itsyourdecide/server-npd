# Поток 2. Стартовая квота и публичные SSH-ключи

[Карта всех потоков](../portal-runtime-walkthrough.md) · Код:
[`app/compute/`](../../../portal/app/compute/),
[`app/ssh_keys/`](../../../portal/app/ssh_keys/).

## Как новый пользователь получает квоту

```text
auth_callback()
  -> get_or_create_user()
     -> для новой (issuer, subject): User() + db.flush()
     -> ExternalIdentity(...)
     -> assign_starter_quota(db, user_id)
        -> SELECT ComputePlan WHERE code = 'starter'
        -> проверить plan.is_active
        -> db.add(UserQuota(user_id, plan.id, status='active'))
  -> commit общей callback-транзакции
```

`ComputePlan` — общая конфигурация лимитов, а `UserQuota` — назначение плана
конкретному человеку. `UserQuota.user_id` — первичный ключ таблицы, поэтому
в текущей схеме у пользователя **не больше одной строки квоты**, а не
«одна активная среди многих». Это не отдельный аккаунт. При обычном повторном
входе `get_or_create_user()` возвращает прежнего `User` и повторно квоту не
создаёт.

Миграция создания `compute_plans` добавила запись `starter`, а отдельная
миграция `backfill_starter_user_quotas` назначает её уже существовавшим
пользователям через `INSERT ... SELECT ... WHERE NOT EXISTS`. Поэтому
`assign_starter_quota()` занимается **новыми** пользователями, а миграция —
историческими. Текущая модель плана содержит `max_vms`, суммарные vCPU, RAM,
storage и `max_shared_storage_gb`; старый `max_running_vms` был удалён
следующей миграцией и не должен использоваться в новом коде.

Файлы: [`identity/services.py`](../../../portal/app/identity/services.py),
[`compute/services.py`](../../../portal/app/compute/services.py),
[`compute/models.py`](../../../portal/app/compute/models.py),
[`903299d0...`](../../../portal/alembic/versions/903299d0b202_create_compute_plans_table.py),
[`1b47a1...`](../../../portal/alembic/versions/1b47a1f1aaff_backfill_starter_user_quotas.py).

## Как считается использование

`get_user_compute_usage(db, user_id)` строит один SQL `SELECT` с `count()` и
`sum()` по VM данного владельца. `coalesce(sum(...), 0)` нужен потому, что
SQL `SUM` по пустому набору возвращает `NULL`, а интерфейсу и проверке квоты
нужен числовой ноль. Функция возвращает словарь:

```text
used_vms, used_vcpus, used_memory_mb, used_storage_gb
```

Учитываются VM со статусами `pending`, `pending_capacity`, `provisioning`,
`running`, `stopped`, `deleting`. Таким образом:

- постановка создания в очередь **сразу** занимает личную квоту;
- остановка VM не освобождает CPU/RAM/storage-лимит;
- удаление не освобождает лимит, пока статус не станет `deleted`;
- `failed` и `deleted` не входят в сумму.

Это учёт **выделенных пользователю конфигураций**, а не измерение текущей
физической загрузки узлов. Функция не спрашивает Proxmox о свободной ёмкости.
`pending_capacity` есть в словаре статусов, но сама по себе эта функция не
реализует планировщик глобальной ёмкости.

## `GET /compute/quota`

`get_quota()` требует `get_current_user`, загружает `UserQuota` по `user.id`,
затем `ComputePlan`, вызывает `get_user_compute_usage()` и возвращает JSON
`status`, `plan`, `limits`, `usage`, `remaining`. Остаток по каждому ресурсу
вычисляется как лимит минус использование. Если квоты или плана нет, текущий
код бросает `RuntimeError` (это 500, а не отдельный пользовательский 404):
ситуация считается нарушением инварианта регистрации.

`shared_storage_gb` в ответе пока особый случай: limit берётся из плана,
но usage принудительно равен `0`, а remaining — всему лимиту. Это
**заглушка**, а не реальный учёт JBOD/shared storage. Статус `suspended`
показывается в ответе; он не обнуляет существующее использование. Запрет на
новое создание проверяется отдельно в `create_vm()`.

## Импорт готового публичного ключа

```text
POST /compute/ssh-keys/import
  -> get_current_user() + verify_csrf()
  -> Pydantic SshPublicKeyCreate(name, public_key)
  -> import_ssh_public_key(db, user.id, request_model)
     -> parse_ssh_public_key(raw text)
     -> проверить имя у этого владельца
     -> проверить fingerprint среди всех владельцев
     -> db.add(SshPublicKey), db.flush()
  -> commit, refresh, HTTP 201 + SshPublicKeyRead
```

`parse_ssh_public_key()` отдаёт ключ библиотеке `cryptography`, допускает
Ed25519 и RSA не короче 2048 бит, сериализует назад в стандартный OpenSSH
формат и вычисляет `SHA256:` fingerprint. Нормализация убирает комментарий
в конце исходной строки как идентификатор ключа: комментарий не входит в
криптографический ключ. Эта функция вызывает `ValueError` для невалидного
или неподдерживаемого ключа. Сервис преобразует это в
`InvalidSshPublicKeyError`, а роутер — в HTTP 400.

Имя HTTP-функции — `import_ssh_key()`: она не парсит криптографию сама,
а переводит результат/исключения сервиса в HTTP 201/400/409 и решает,
когда делать commit. Поэтому этот же сервис можно использовать без HTTP,
не передавая ему `Request` или `Response`.

Имя уникально **в пределах пользователя**; одинаковое имя у разных людей
разрешено. Fingerprint уникален **глобально**, поэтому один и тот же ключ
не регистрируется двум владельцам. Сервис заранее делает SELECT и сообщает
`SshPublicKeyConflictError`/409; уникальные ограничения в БД остаются
последней защитой от гонки двух параллельных запросов.

## Генерация пары ключей в Portal

```text
POST /compute/ssh-keys/generate
  -> get_current_user() + verify_csrf()
  -> SshKeyPairGenerate(name)
  -> generate_ssh_key_pair()
     -> проверить имя пользователя
     -> ed25519.Ed25519PrivateKey.generate()
     -> вывести OpenSSH public key и приватный OpenSSH PEM
     -> parse_ssh_public_key(public) для типа/fingerprint
     -> db.add(SshPublicKey), db.flush()
     -> вернуть GeneratedSshKeyPair(public row, private text)
  -> commit, refresh(public row)
  -> HTTP 201: {key: metadata, private_key: text}
```

Приватный ключ **не является колонкой** `ssh_public_keys`: в БД остаётся
только открытый ключ и его метаданные. Ответ содержит приватный ключ один
раз. Роутер ставит `Cache-Control: no-store` и `Pragma: no-cache`, чтобы
снизить риск кэширования ответа. Пользователь должен сохранить приватный
ключ безопасно; восстановить тот же приватный ключ из публичного нельзя.
Текущий код не шифрует выданный приватный ключ паролем
(`NoEncryption()`), поэтому защита скачанного файла ложится на клиента.

HTTP-функция называется `generate_ssh_key_pair_endpoint()`: она делает
commit, `refresh` публичной записи, выставляет anti-cache headers и
сериализует ответ. Сам сервис `generate_ssh_key_pair()` возвращает
`GeneratedSshKeyPair` с ORM-строкой и приватным текстом, но HTTP-коды
и заголовки ему не принадлежат.

Сервис генерации явно проверяет конфликт имени, но не делает отдельный
SELECT на глобальный fingerprint. Вероятность случайного совпадения Ed25519
пренебрежимо мала; если всё же сработает ограничение БД, текущий роутер не
переведёт эту `IntegrityError` в специализированный 409.

`get_list_keys()` на `GET /compute/ssh-keys` выбирает только строки с
`owner_user_id == user.id` и возвращает `SshPublicKeyRead`. В HTML-кабинете
сейчас есть список и выбор ключа при создании VM, но **нет** HTML-формы
импорта/генерации. Для этих действий используется JSON API.

## Как ключ попадает в будущую VM

`VirtualMachine` хранит `ssh_public_key_id`, а не приватный ключ.
`create_vm()` при приёме запроса проверяет, что указанная строка
`SshPublicKey` принадлежит текущему пользователю. Позднее worker вызывает
`_build_create_vm_request(db, vm)`: он ещё раз загружает этот ключ, проверяет
его владельца и кладёт **публичную** строку в `CreateVmRequest`.
`HttpProxmoxAdapter.configure_vm()` передаёт её как `sshkeys` в конфигурацию
Cloud-Init. Так проверка владения есть и на входе, и непосредственно перед
инфраструктурным действием.

При этом comment в конце публичного OpenSSH-ключа не управляет Unix-логином
в VM. Имя пользователя Cloud-Init приходит из настройки worker
`proxmox_cloud_init_user`, а вход подтверждается соответствием приватного
ключа сохранённому публичному.
