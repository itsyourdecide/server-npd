# Service account Proxmox для Portal

Статус: current
Последняя проверка: 2026-09-21
Last tested: 2026-09-21 на Proxmox VE 9.2.3
Назначение: воспроизводимо создать и проверить ограниченный API-доступ operation worker Portal
Источник истины для: процедуры настройки service account, token, pool и ACL Portal в Proxmox

## Область действия и воздействие

Runbook создаёт отдельные объекты Proxmox:

- user `portal-worker@pve`;
- API token `portal-worker@pve!portal` с `privsep=1`;
- resource pool `npd-portal`;
- custom role `NPDPortalWorker`;
- ACL на `/`, `/pool/npd-portal`, `/storage/local-zfs`, исходный template и
  конкретную SDN/VLAN path.

Ожидаемый простой отсутствует. Команды не изменяют существующие VM, storage
или сеть. Неправильный ACL способен выдать worker лишние права, поэтому после
каждого этапа обязательна проверка effective permissions.

## Prerequisites

- root shell на одном из действующих cluster members;
- подтверждённый quorum;
- резервный административный доступ через Proxmox GUI или другую root SSH
  session;
- рабочая станция Portal видит `pve01:8006` и разрешает имя `pve01`;
- на рабочей станции создан локальный `.env.worker`, исключённый из Git.

Перед началом:

```bash
LC_ALL=C pvecm status
LC_ALL=C pveum user list
LC_ALL=C pveum pool list
LC_ALL=C pveum role list
```

## Стоп-критерии

Остановить настройку и не расширять ACL, если:

- cluster не имеет quorum;
- user, token, pool или role с таким именем уже существуют, но имеют другое
  назначение;
- `local-zfs` указывает не на ожидаемое локальное ZFS-хранилище;
- resource pool содержит VM, не принадлежащие Portal;
- TLS certificate не проверяется cluster CA;
- effective permissions содержат `Administrator`, `Permissions.Modify`,
  `User.Modify`, `Sys.Modify` или другие не запланированные write privileges.

## Создание service account и token

Создать пользователя без интерактивного login:

```bash
LC_ALL=C pveum user add 'portal-worker@pve' --comment "NPD Portal operation worker"
```

Выдать backing user общий read-only доступ:

```bash
LC_ALL=C pveum acl modify / -user 'portal-worker@pve' -role PVEAuditor -propagate 1
```

Создать privilege-separated token:

```bash
LC_ALL=C pveum user token add 'portal-worker@pve' portal -privsep 1 -comment "NPD Portal API token"
```

Команда показывает token secret в поле `value` только один раз. Secret нельзя
вставлять в shell history, документацию, issue, chat или Git. Его нужно сразу
перенести в защищённый `.env.worker` на хосте приложения.

Выдать token такой же общий read-only доступ:

```bash
LC_ALL=C pveum acl modify / -token 'portal-worker@pve!portal' -role PVEAuditor -propagate 1
```

### Ротация token

`pveum user token delete` удаляет не только secret, но и ACL этого token.
После создания нового token с тем же ID нужно заново назначить **все** его
ACL из этого runbook: `/`, pool, storage, template и SDN/VLAN path. ACL
backing user при этом сохраняются. После ротации обязательно повторить
`pveum user token permissions` и API probe; одной замены secret в
`.env.worker` недостаточно.

## Создание изолированного resource pool

```bash
LC_ALL=C pveum pool add npd-portal --comment "Virtual machines managed by NPD Portal"
```

Resource pool является логической ACL-границей. Он не резервирует CPU, RAM
или storage.

## Создание VM-роли

```bash
LC_ALL=C pveum role add NPDPortalWorker --privs "Pool.Audit VM.Allocate VM.Audit VM.Clone VM.Config.CDROM VM.Config.CPU VM.Config.Cloudinit VM.Config.Disk VM.Config.HWType VM.Config.Memory VM.Config.Network VM.Config.Options VM.GuestAgent.Audit VM.PowerMgmt"
```

Назначить роль backing user и token только на pool Portal:

```bash
LC_ALL=C pveum acl modify /pool/npd-portal -user 'portal-worker@pve' -role NPDPortalWorker -propagate 1
LC_ALL=C pveum acl modify /pool/npd-portal -token 'portal-worker@pve!portal' -role NPDPortalWorker -propagate 1
```

В роли намеренно отсутствуют управление пользователями и ACL, изменение
узлов, storage administration, migration, replication и snapshots.

## Доступ к VM storage

Разрешить выделение места только на `local-zfs`:

```bash
LC_ALL=C pveum acl modify /storage/local-zfs -user 'portal-worker@pve' -role PVEDatastoreUser -propagate 1
LC_ALL=C pveum acl modify /storage/local-zfs -token 'portal-worker@pve!portal' -role PVEDatastoreUser -propagate 1
```

`PVEDatastoreUser` даёт `Datastore.AllocateSpace` и `Datastore.Audit`, но не
разрешает изменять конфигурацию самого storage. Одинаковый ID `local-zfs` на
нескольких узлах не превращает локальные ZFS pools в shared storage.

## Доступ к template и сети

После создания template `9000` выдать user и token только право чтения и
клонирования:

```bash
LC_ALL=C pveum acl modify /vms/9000 -user 'portal-worker@pve' -role PVETemplateUser -propagate 1
LC_ALL=C pveum acl modify /vms/9000 -token 'portal-worker@pve!portal' -role PVETemplateUser -propagate 1
```

Для private VM network на `pve02` разрешить использование только VLAN 40:

```bash
LC_ALL=C pveum acl modify /sdn/zones/localnetwork/vmbr0/40 -user 'portal-worker@pve' -role PVESDNUser -propagate 1
LC_ALL=C pveum acl modify /sdn/zones/localnetwork/vmbr0/40 -token 'portal-worker@pve!portal' -role PVESDNUser -propagate 1
```

Проверенная SDN path относится к `vmbr0` на `pve02`. На `pve01` private VM
bridge называется `vmbr2`; при добавлении размещения на другом узле ACL и
node-to-bridge mapping нужно проверить отдельно, не расширяя доступ на всю
SDN zone.

## TLS и локальная конфигурация worker

Скопировать публичный cluster CA на хост приложения по доверенному SSH-каналу:

```bash
install -d -m 700 ~/.config/npd-portal
scp pve01:/etc/pve/pve-root-ca.pem ~/.config/npd-portal/pve-root-ca.pem
chmod 600 ~/.config/npd-portal/pve-root-ca.pem
```

В локальном `.env.worker`:

```dotenv
PROXMOX_API_URL=https://pve01:8006/api2/json
PROXMOX_TOKEN_ID=portal-worker@pve!portal
PROXMOX_TOKEN_SECRET=<secret from token creation; never commit>
PROXMOX_CA_FILE=/home/<portal-user>/.config/npd-portal/pve-root-ca.pem
PROXMOX_TIMEOUT_SECONDS=10
```

Нельзя заменять CA verification на `verify=False`.

## Проверка результата

Проверить объекты и эффективные права:

```bash
LC_ALL=C pveum user token list 'portal-worker@pve'
LC_ALL=C pveum pool list
LC_ALL=C pveum role list | grep NPDPortalWorker
LC_ALL=C pveum user token permissions 'portal-worker@pve' portal
```

Ожидается:

- на `/` — только privileges роли `PVEAuditor`;
- на `/pool/npd-portal` — privileges `NPDPortalWorker`;
- на `/storage/local-zfs` — `Datastore.AllocateSpace` и `Datastore.Audit`;
- на `/vms/9000` — `VM.Audit` и `VM.Clone` через `PVETemplateUser`;
- на `/sdn/zones/localnetwork/vmbr0/40` — `SDN.Audit` и `SDN.Use`;
- никаких administrative privileges для user или token.

Из каталога `portal/` проверить read-only API через реальный клиент:

```bash
.venv/bin/python - <<'PY'
import asyncio

from app.proxmox.client import ProxmoxClient
from app.workers.config import OperationWorkerSettings


async def main() -> None:
    settings = OperationWorkerSettings()
    client = ProxmoxClient(
        api_url=settings.proxmox_api_url,
        token_id=settings.proxmox_token_id,
        token_secret=settings.proxmox_token_secret.get_secret_value(),
        ca_file=str(settings.proxmox_ca_file),
        timeout_seconds=settings.proxmox_timeout_seconds,
    )
    try:
        print(await client.get_version())
        print(await client.get_nodes())
    finally:
        await client.aclose()


asyncio.run(main())
PY
```

Проверка 2026-09-21 вернула PVE `9.2.3` и узлы `pve01`, `pve02`, `pve03` со
статусом `online`.

## Rollback

Сначала остановить operation worker. Затем удалить ACL, не затрагивая другие
principals:

```bash
LC_ALL=C pveum acl delete /storage/local-zfs --users 'portal-worker@pve' --roles PVEDatastoreUser
LC_ALL=C pveum acl delete /storage/local-zfs --tokens 'portal-worker@pve!portal' --roles PVEDatastoreUser
LC_ALL=C pveum acl delete /vms/9000 --users 'portal-worker@pve' --roles PVETemplateUser
LC_ALL=C pveum acl delete /vms/9000 --tokens 'portal-worker@pve!portal' --roles PVETemplateUser
LC_ALL=C pveum acl delete /sdn/zones/localnetwork/vmbr0/40 --users 'portal-worker@pve' --roles PVESDNUser
LC_ALL=C pveum acl delete /sdn/zones/localnetwork/vmbr0/40 --tokens 'portal-worker@pve!portal' --roles PVESDNUser
LC_ALL=C pveum acl delete /pool/npd-portal --users 'portal-worker@pve' --roles NPDPortalWorker
LC_ALL=C pveum acl delete /pool/npd-portal --tokens 'portal-worker@pve!portal' --roles NPDPortalWorker
LC_ALL=C pveum acl delete / --users 'portal-worker@pve' --roles PVEAuditor
LC_ALL=C pveum acl delete / --tokens 'portal-worker@pve!portal' --roles PVEAuditor
```

Удалить token:

```bash
LC_ALL=C pveum user token delete 'portal-worker@pve' portal
```

Удалять pool можно только после проверки, что он пуст:

```bash
LC_ALL=C pveum pool list
LC_ALL=C pveum pool delete npd-portal
```

После удаления всех ACL роль и user можно удалить:

```bash
LC_ALL=C pveum role delete NPDPortalWorker
LC_ALL=C pveum user delete 'portal-worker@pve'
```

Удалить token secret из secret storage хоста приложения и перезапустить
worker только после выдачи нового token.

## Следующий этап

Реализовать `HttpProxmoxAdapter` поверх проверенного API-контракта и fixtures.
Template `9000`, storage/network ACL и полный lifecycle smoke test уже готовы.

## Связанные документы

- [Proxmox cluster](../services/proxmox.md).
- [AlmaLinux template для Portal](portal-proxmox-template.md).
- [Текущее состояние](../current-state.md).
- [Архитектура вычислительных квот и VM](../architecture/compute-quota-and-vm.md).
