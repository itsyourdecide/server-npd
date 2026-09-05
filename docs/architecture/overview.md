# Архитектура кластера server-npd

Статус: current
Последняя редакция: 2026-09-05
Живая проверка при редакции: не выполнялась
Источник истины для: архитектурных границ и разделения deployed/target state

## Назначение

Кластер предоставляет:

- виртуальные машины и контейнеры на Proxmox;
- выполнение независимых научных задач через HTCondor;
- PXE-установку bare-metal compute-узлов;
- CVMFS-доступ к HEP/CERN software;
- общее файловое пространство для проектов и результатов;
- контролируемый SSH-доступ пользователей;
- monitoring инфраструктуры и compute-узлов.

Конкретное последнее состояние компонентов находится в
[current state](../current-state.md), а будущие работы — в
[roadmap](../project/roadmap.md). Этот документ не заменяет их.

## Развёрнутое состояние

```text
Internet user
    |
    | TCP/10000
    v
vpn-npd (Azure public gateway)
    |
    | WireGuard
    v
pve02 -> bastion01 (DMZ/VLAN50)
             |
             | SSH ProxyJump
             v
       condor01 (VLAN80)
             |
             | HTCondor
             v
   asus-r1n1 ... asus-r1n4
```

```text
                      Proxmox cluster "npd"
                +-----------+-----------+-----------+
                |   pve01   |   pve02   |   pve03   |
                +-----------+-----------+-----------+
                     VLAN20 Corosync / quorum

  pve01: ZFS/NFS storage head      pve02: fw01, pxe01, squid01,
  and replication peer                    monitor01, bastion01, condor01
```

### Виртуализация

- `pve01`–`pve03` образуют действующий Proxmox-кластер `npd`.
- Каждый узел является равноправным участником quorum.
- Corosync изолирован в VLAN 20.
- Диски первых критичных VM реплицируются средствами Proxmox/ZFS.
- Полный автоматический HA/fencing и независимый backup пока не считаются
  подтверждёнными.

### Compute

- HTCondor является основным scheduler.
- `condor01` совмещает central manager и submit/access point.
- Первая ASUS-рельса содержит четыре bare-metal execute-ноды AlmaLinux 9.
- PXE/Kickstart создаёт минимальную ОС; роли HTCondor, CVMFS, monitoring и
  storage применяются через Ansible.
- Slurm не развёрнут и рассматривается только как возможный отдельный слой для
  многонодовых MPI-задач.

### Хранилище

Используются два разных механизма:

1. Локальный ZFS и Proxmox ZFS replication для дисков VM.
2. `npddata` на `pve01` с NFS export `10.10.80.2:/data` для общих данных
   HTCondor.

ZFS replication не является shared storage и не является backup. NFS на одном
storage head имеет собственную точку отказа. Ceph отложен до появления
достаточной сети, failure domains и доказанной потребности.

Доступность JBOD/NFS должна проверяться отдельно: последняя документация
содержит как успешный smoke test, так и более позднюю запись об отключённой
полке.

### Сеть

Основная сегментация:

| VLAN | Назначение |
|---:|---|
| 10 | Proxmox и switch management |
| 20 | Corosync |
| 30 | IPMI/BMC |
| 40 | Private VM |
| 50 | DMZ |
| 60/61 | зарезервированы под возможный Ceph |
| 80 | HTCondor, PXE и storage clients |
| 99 | временный внешний WAN лабораторной схемы |

Межсетевой доступ контролирует `fw01`/OPNsense. Compute и пользовательские
сегменты не должны получать прямой доступ к Proxmox и BMC.

Force10 обслуживает шкаф Supermicro, HP 3500yl — шкаф ASUS. Между ними
предусмотрен двухлинковый LACP. LAN2/bonding Supermicro остаётся целевым, а не
развёрнутым состоянием.

### Пользовательский доступ

- основной публичный вход — Azure gateway `vpn-npd`;
- WireGuard доставляет соединение на `pve02`;
- `bastion01` находится в DMZ и принимает только key-based SSH;
- пользователь подключается к `condor01` через `ProxyJump`;
- пользователи не получают sudo;
- одинаковые numeric UID поддерживаются на submit и execute-нодах.

### Monitoring

Prometheus на `monitor01` собирает node exporter metrics с PVE,
инфраструктурных и compute-узлов. Текущая реализация является phase 1: наличие
targets проверяется, но полноценные alerts, central logs и дежурная процедура
ещё входят в roadmap.

## Целевое состояние

Цель развития, а не описание уже работающей системы:

- до десяти проверенных Supermicro в Proxmox-кластере;
- расширение ASUS по одной рельсе после power/thermal и PXE acceptance tests;
- резервные LAN1/LAN2 для PVE;
- независимый backup с регулярным restore test;
- понятная доступность общего storage и recovery procedure;
- alerts, central logs и регулярные failover/thermal drills;
- Supermicro HTCondor execute VM при наличии безопасного запаса ресурсов;
- LDAP/AD, web UI, GPU и Slurm/MPI только по подтверждённой потребности.

## Архитектурные границы

- Proxmox host OS не используется как обычная compute-нода.
- ASUS не входят в quorum и не размещают критичные VM.
- HTCondor power management не имеет права выключать PVE/storage hosts.
- IPMI не публикуется в интернет.
- Ceph не добавляется только потому, что появились свободные диски или два
  10GbE-порта.
- ZFS replication не заменяет backup.
- Исторические PoC-схемы не являются production architecture.

## Принятые решения

- [ADR-0001: Proxmox для Supermicro](decisions/0001-proxmox-on-supermicro.md).
- [ADR-0002: HTCondor как основной scheduler](decisions/0002-htcondor-primary-scheduler.md).
- [ADR-0003: ZFS replication вместо Ceph на текущем этапе](decisions/0003-zfs-instead-of-ceph.md).

## Открытые вопросы

Архитектурные вопросы ведутся как задачи, а не дописываются в этот документ:
[open issues](../project/open-issues.md).
