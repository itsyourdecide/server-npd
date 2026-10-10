# Proxmox cluster

Статус: current
Последняя проверка API-интеграции Portal: 2026-09-21
Последняя подтверждённая общая проверка: 2026-08-13
Назначение: описать развёрнутое состояние Proxmox и границы его эксплуатации
Источник истины для: роли Proxmox, API-доступа Portal и границ эксплуатации

## Deployed

- cluster name: `npd`;
- members: `pve01`, `pve02`, `pve03`;
- management: `10.10.10.11`–`10.10.10.13`;
- Corosync: `10.10.20.11`–`10.10.20.13`;
- local ZFS на узлах;
- ZFS replication первых критичных VM;
- основные инфраструктурные VM/LXC размещены на `pve02`.

## API-интеграция Portal

Проверенное 2026-09-21 состояние:

| Объект | Значение |
|---|---|
| API endpoint | `https://pve01:8006/api2/json` |
| Service account | `portal-worker@pve` |
| API token ID | `portal-worker@pve!portal` |
| Token privilege separation | включено (`privsep=1`) |
| Resource pool | `npd-portal` |
| VM role | `NPDPortalWorker` |
| Разрешённое хранилище | `local-zfs` через `PVEDatastoreUser` |
| Исходный template | `9000` (`npd-almalinux-9-template`) на `pve02` |
| Сеть пользовательских VM | VLAN 40 (`10.10.40.0/24`) |
| Общий доступ | read-only через `PVEAuditor` на `/` |

`NPDPortalWorker` содержит:

```text
Pool.Audit
VM.Allocate
VM.Audit
VM.Clone
VM.Config.CDROM
VM.Config.CPU
VM.Config.Cloudinit
VM.Config.Disk
VM.Config.HWType
VM.Config.Memory
VM.Config.Network
VM.Config.Options
VM.GuestAgent.Audit
VM.PowerMgmt
```

Роль назначена и backing user, и отделённому API token только на
`/pool/npd-portal`. `PVEDatastoreUser` аналогично назначена обоим principals на
`/storage/local-zfs`. Двойное назначение обязательно: при `privsep=1`
эффективные права token ограничены пересечением собственных ACL и ACL его
владельца.

Portal проверяет TLS по cluster CA, а не отключает certificate verification.
CA хранится на хосте приложения отдельно от репозитория. Token secret хранится
только в локальном `.env.worker`, который не должен попадать в Git. Проверка
через `ProxmoxClient` успешно получила PVE version `9.2.3` и список
`pve01`–`pve03`; все три узла API вернул как `online`.

Доступ к `local-zfs` разрешает выделять место, но не даёт управлять самим
storage. `local-zfs` является локальным storage каждого узла, а не shared
storage, поэтому размещение и доступность template должны учитываться для
конкретного узла.

Для клонирования user и token получили `PVETemplateUser` на `/vms/9000`.
Для подключения клона к private VM network оба principals получили
`PVESDNUser` только на `/sdn/zones/localnetwork/vmbr0/40`. Без этого ACL
изменение сетевой конфигурации завершается `403` с требованием `SDN.Use`.

### AlmaLinux template

На `pve02` развёрнут защищённый template:

| Параметр | Значение |
|---|---|
| VMID / name | `9000` / `npd-almalinux-9-template` |
| Образ | `AlmaLinux-9-GenericCloud-9.8-20260810.x86_64.qcow2` |
| SHA-256 | `6bdab6376d46d42e4203ace3733efafc7c5d37c7cb443a6cc74750097002d74b` |
| Storage | `local-zfs`, базовый диск 10 GiB |
| Machine / BIOS | `q35` / SeaBIOS |
| CPU / RAM | `x86-64-v2-AES`, 2 vCPU / 2048 MiB |
| Disk controller | `virtio-scsi-single` |
| Guest agent | включён, `fstrim_cloned_disks=1` |
| Network | `virtio`, `vmbr0`, firewall, VLAN tag 40 |
| Cloud-Init | user `almalinux`, IPv4 DHCP |
| DNS | `10.10.40.1`, search domain `internal` |
| Protection | включена |

Исходный QCOW2, подписанные checksum-файлы и публичный AlmaLinux signing key
хранятся на `pve02` в `/var/lib/vz/template/cache/npd-portal/`. Образ проверен
сначала по GPG-подписи, затем по SHA-256.

Сетевой bridge зависит от узла: `pve01` использует `vmbr2`, `pve02` и
`pve03` — `vmbr0`. Все три bridge VLAN-aware и разрешают VLAN
`10,20,30,40,50,80,99`. Adapter не должен считать имя bridge глобальной
константой без привязки к выбранному узлу.

### Проверенный lifecycle через API token

Контрольный full clone template `9000` на `pve02` подтвердил:

- clone, изменение CPU/RAM/Cloud-Init, resize, start, shutdown и delete;
- task polling: выполняющаяся задача имеет `status="running"`, успешная
  завершённая — `status="stopped"` и `exitstatus="OK"`;
- `sshkeys` в form body должен быть предварительно URL-encoded;
- resize также возвращает UPID и должен быть опрошен до завершения;
- guest agent сообщил адрес из VLAN 40, SSH через bastion прошёл;
- root XFS автоматически вырос до 30 GiB;
- явные DNS-настройки дали только `10.10.40.1` и `search internal`;
- Cloud-Init с обновлением пакетов занял около пяти минут, поэтому успешный
  `qmstart` ещё не означает готовность гостевой ОС.

Удаление нужно выполнять с `purge=1`. Комбинация с
`destroy-unreferenced-disks=1` в текущей конфигурации дала ошибку
`no such logical volume pve/data`; повторный delete только с `purge=1`
завершился `OK` и удалил все тома VM.

Обезличенные реальные ответы API находятся в
`portal/tests/fixtures/proxmox/`. Полная локальная копия документации PVE 9.2
для офлайн-разработки находится вне Git в
`~/.local/share/npd-portal/proxmox-ve-9.2-docs/`.

### Ещё не развёрнуто

- production `HttpProxmoxAdapter` для операций создания VM;
- политика выбора узла и проверки реальной ёмкости;
- start, stop, delete и reconciliation с реальным состоянием Proxmox.

VM `120` (`pxe-alma-test`) не является образом Portal: это временная
PXE/iPXE test VM без установленной ОС. Её нельзя использовать или
преобразовывать в template для Portal.

## Health check

```bash
cd /root/server-npd
./scripts/cluster-health.sh --skip-storage
```

Storage assertions включаются только когда JBOD/NFS намеренно online.

Дополнительно проверяются:

```bash
pvecm status
pvesr status
qm list
pct list
```

## HA boundary

- Наличие трёх cluster members даёт quorum, но не делает каждую VM HA.
- ZFS replication асинхронна и имеет ненулевой RPO.
- Planned migration `fw01` проверена; uncontrolled failure и fencing — нет.
- Replication не заменяет backup.
- До настройки LAN2 каждый PVE зависит от основного LAN path.

## Expansion rule

Новый PVE-узел добавляется только после hardware inventory, burn-in, проверки
обоих PSU, network, power/thermal и пересчёта quorum. Наличие кабеля в switch не
означает готовность узла к `pvecm add`.

## Related

- [ADR-0001](../architecture/decisions/0001-proxmox-on-supermicro.md).
- [Current state](../current-state.md).
- [Portal Proxmox service account runbook](../runbooks/portal-proxmox-service-account.md).
- [Portal AlmaLinux template runbook](../runbooks/portal-proxmox-template.md).
- [Архитектура вычислительных квот и VM](../architecture/compute-quota-and-vm.md).
- [fw01 failover runbook](../runbooks/fw01-failover.md).
- [Open issues](../project/open-issues.md).
