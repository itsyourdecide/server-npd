# Текущее документированное состояние кластера

Статус: current
Последняя редакция: 2026-09-05
Живая проверка при редакции: не выполнялась
Источник истины для: последнего документированного состояния компонентов и известных проблем

## Как читать статусы

- **Verified** — результат подтверждён проверкой в указанную дату.
- **Last documented** — факт зафиксирован в документации, но при подготовке
  этой страницы повторно не проверялся.
- **Planned** — целевое состояние, которое ещё не считается развёрнутым.
- **Unknown/deferred** — последнее состояние недостаточно для безопасного
  вывода или работа сознательно отложена.

Ни один статус на этой странице не следует автоматически переносить на более
позднюю дату. Для актуализации нужно выполнить соответствующий health-check и
обновить поле `Последняя проверка`.

## Общая сводка

| Компонент | Последнее документированное состояние | Статус | Последняя проверка |
|---|---|---|---|
| Proxmox | Кластер `npd`, узлы `pve01`–`pve03`, quorum 3/3 | Verified | 2026-08-13 |
| Firewall/router | `fw01`, VM 100; после migration test возвращена на `pve02` | Last documented | 2026-08-13 |
| HTCondor | `condor01` manager+submit и 4 ASUS execute-ноды | Verified | 2026-08-13 |
| PXE | `pxe01`, LXC 110 на `pve02`, HTTP/TFTP/iPXE | Verified | 2026-08-07 |
| CVMFS | `sft.cern.ch` и `unpacked.cern.ch`, Squid-first с direct fallback | Verified | 2026-08-07 |
| Monitoring | Prometheus на `monitor01`, 11/11 targets up | Verified | 2026-08-13 |
| User access | Azure/WireGuard → `pve02` → `bastion01` → `condor01` | Verified | 2026-08-28 |
| Shared storage | `npddata`/NFS прошёл smoke test, но после физических работ JBOD был отложен | Unknown/deferred | healthy 2026-08-07; unavailable documented 2026-08-11 |
| Inter-switch LACP | Работал через один линк; второй был Down | Last documented, degraded | 2026-08-11 |
| Backup | Независимая backup-система не подтверждена | Planned | — |

## Proxmox и виртуальная инфраструктура

Последняя подтверждённая конфигурация:

| Узел | Management | Corosync | Роль |
|---|---|---|---|
| `pve01` | `10.10.10.11` | `10.10.20.11` | cluster member, ZFS replication peer, первый storage head |
| `pve02` | `10.10.10.12` | `10.10.20.12` | cluster member, основное размещение инфраструктурных VM/LXC |
| `pve03` | `10.10.10.13` | `10.10.20.13` | cluster member, ZFS replication peer |

Зафиксировано:

- кластер называется `npd`;
- Corosync вынесен в VLAN 20;
- `fw01` имеет ZFS-реплики на запасных узлах;
- planned migration `fw01` с `pve02` на `pve03` и обратно выполнена
  2026-07-08;
- автоматический HA/fencing и настоящий replica failover не подтверждены;
- LAN2/bonding для трёх PVE-узлов не настроен.

`pve04` и `pve05` по состоянию на 2026-08-11 были физически подключены к
Force10 на уровне LAN/IPMI, но не были введены в Proxmox-кластер. `pve06`–
`pve10` остаются target state.

## Сеть

| VLAN | Сеть | Назначение | Gateway |
|---:|---|---|---|
| 10 | `10.10.10.0/24` | Proxmox и switch management | `10.10.10.1` |
| 20 | `10.10.20.0/24` | Corosync | отсутствует |
| 30 | `10.10.30.0/24` | IPMI/BMC | `10.10.30.1` |
| 40 | `10.10.40.0/24` | Private VM | `10.10.40.1` |
| 50 | `10.10.50.0/24` | DMZ | `10.10.50.1` |
| 60 | `10.10.60.0/24` | зарезервирован под возможный Ceph client traffic | отсутствует |
| 61 | `10.10.61.0/24` | зарезервирован под возможный Ceph replication | отсутствует |
| 80 | `10.10.80.0/24` | HTCondor/PXE/storage clients | `10.10.80.1` |
| 99 | внешний DHCP | временный WAN лабораторной схемы | внешний router |

Последнее документированное состояние коммутаторов:

- `force10-sm` обслуживает шкаф Supermicro;
- `switch1`/`hp3500` обслуживает шкаф ASUS;
- межшкафный LACP должен состоять из двух 1GbE-линков;
- 2026-08-11 Force10 `Gi 0/2` был Up, `Gi 0/1` был Down;
- фактическая VLAN summary в старой карте `switch1` содержит внутреннее
  расхождение и требует сверки с `show vlan`;
- LAN2/bonding Supermicro остаётся незавершённым.

## HTCondor, PXE и scientific software

| Сервис/узел | Адрес | Размещение | Последняя роль |
|---|---|---|---|
| `pxe01.internal` | `10.10.80.10` | LXC 110, `pve02` | TFTP, iPXE, Nginx, AlmaLinux cache |
| `squid01.internal` | `10.10.80.11` | LXC 111, `pve02` | CVMFS HTTP proxy/cache |
| `condor01.internal` | `10.10.80.20` | VM 130, `pve02` | HTCondor central manager и submit |
| `asus-r1n1.internal` | `10.10.80.101` | bare metal | HTCondor execute |
| `asus-r1n2.internal` | `10.10.80.102` | bare metal | HTCondor execute |
| `asus-r1n3.internal` | `10.10.80.103` | bare metal | HTCondor execute |
| `asus-r1n4.internal` | `10.10.80.104` | bare metal | HTCondor execute |

Подтверждённый milestone:

- четыре ASUS-ноды установлены через PXE/Kickstart;
- роли HTCondor применяются через Ansible;
- CVMFS probe проходил на `condor01` и ASUS;
- пользовательский job выполнялся под реальным UID, а не `nobody`;
- `UID_DOMAIN = internal`, `TRUST_UID_DOMAIN = True`;
- Supermicro execute VM пока не добавлены в inventory.

IPMI `asus-r1n1` и `asus-r1n2` отвечал на ping. Для `asus-r1n3` и
`asus-r1n4` в последней карте оставался статус `pending`.

## Monitoring

| Компонент | Значение |
|---|---|
| `monitor01` | LXC 112 на `pve02` |
| IP | `10.10.10.30` |
| Prometheus | `http://10.10.10.30:9090` |
| Последний результат | 11/11 targets up, 2026-08-13 |

Ожидаемые targets: три PVE, `monitor01`, Prometheus, `bastion01`, `condor01` и
четыре ASUS execute-ноды.

## Пользовательский доступ

Последняя проверенная схема:

```text
Internet user
  -> vpn-npd 20.215.200.4:10000
  -> WireGuard 10.255.80.1 <-> 10.255.80.2
  -> pve02 local forward :10022
  -> bastion01 10.10.50.10:22
  -> ProxyJump
  -> condor01 10.10.80.20:22
  -> HTCondor execute nodes
```

- `bastion01` — LXC 102 на `pve02`, VLAN 50;
- основной внешний вход — Azure gateway `vpn-npd`;
- Tailscale Funnel остаётся fallback/admin channel;
- пользователи входят только по SSH key и не получают sudo;
- одинаковые UID создаются на `condor01` и execute-нодах.

End-to-end `user-access-health.sh npdtest` завершился как `8 checks, 0
failed` 2026-08-28.

## Хранилище

Принятое разделение:

- диски VM: локальный ZFS + Proxmox ZFS replication;
- общие данные HTCondor: `pve01`, pool `npddata`, NFS
  `10.10.80.2:/data`;
- Ceph: deferred, не является текущим storage layer;
- `/data/projects` и `/data/results` — долговременные данные;
- `/data/scratch` — временные данные с retention 14 дней.

Storage был создан и прошёл end-to-end HTCondor smoke test 2026-08-07. В
документе по SAS topology от 2026-08-11 указано, что после физических работ
`pve01` видел только системные SSD и старый pool не был online. Поэтому storage
нельзя считать доступным без новой проверки; общий health-check следует
запускать с `--skip-storage`, пока полки намеренно выключены.

## Питание и охлаждение

Последние реальные внешние измерения 2026-08-12:

- Supermicro heavy workload: около 240 W на узел;
- ASUS rail из четырёх узлов под CPU load: около 1300 W;
- один switch: до 200 W из наблюдавшихся значений;
- одна JBOD-полка: около 350 W startup и 230 W idle;
- расчёт полного парка с инженерным запасом: примерно 26–28 kW.

Все три Supermicro ранее сообщали `PS2 Status` failed/not OK. Физическое
исправление и повторная проверка не подтверждены документацией.

## Известные проблемы

Авторитетный список находится в [open issues](project/open-issues.md). Наиболее
важные на момент создания страницы:

- восстановить второй линк межшкафного LACP;
- проверить живое состояние JBOD/NFS;
- проверить вторые PSU на `pve01`–`pve03`;
- создать независимую backup-систему и проверить восстановление;
- завершить LAN2/bonding;
- сверить фактические карты портов с конфигурацией свитчей.

## Источники последнего документированного состояния

- [История операций](history/README.md) — подтверждения на даты выполнения
  работ; не используется как текущий backlog.
- [Force10 port map](network/force10-ports.md).
- [HP 3500yl port map](network/hp3500-ports.md).
- [Ansible inventory](../ansible/inventory/hosts.yml).
- [User access](services/user-access.md).
- [Power measurements](../evidence/measurements/2026-08-12-power-characterization/README.md).
