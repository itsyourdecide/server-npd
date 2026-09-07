# Roadmap кластера server-npd

Статус: current
Последняя редакция: 2026-09-07
Живая проверка при редакции: частичная; ограничения после переезда подтверждены
владельцем кластера
Источник истины для: порядка развития кластера; конкретные задачи находятся в `open-issues.md`

## Принцип

Каждый этап заканчивается проверяемым рабочим состоянием. Новая ёмкость не
добавляется раньше сети, питания, monitoring, backup и процедуры восстановления.

Статусы ниже отражают последнее документированное состояние, а не живую
проверку 2026-09-05.

## Завершённая база

### M1 — трёхузловой Proxmox pilot

Статус: documented complete

- `pve01`–`pve03` объединены в кластер `npd`;
- Corosync вынесен в VLAN 20;
- ZFS replication настроена для первых критичных VM;
- planned migration `fw01` проверена;
- VLAN routing/firewall PoC работает.

Не входит в completed scope: автоматический HA/fencing, LAN2/bonding и
независимый backup.

### M2 — PXE и первый HTCondor pool

Статус: documented complete

- `pxe01` раздаёт iPXE/Kickstart и локально кэширует AlmaLinux packages;
- четыре ASUS-ноды установлены как AlmaLinux fleet;
- `condor01` работает как central manager и submit;
- jobs выполнялись на всех четырёх ASUS;
- CVMFS работает через локальный Squid-first proxy;
- Prometheus monitoring охватывал 11 targets.

### M3 — первый пользовательский SSH-доступ

Статус: documented complete

- key-only доступ через `bastion01`;
- ProxyJump к `condor01`;
- одинаковый UID на submit и execute nodes;
- основной внешний gateway через Azure/WireGuard;
- Tailscale сохранён как fallback/admin channel.

## Текущий стабилизационный этап

### M4 — текущая ограниченная конфигурация после переезда

Статус: in progress / owner-directed

Работающее ядро сейчас ограничено тремя PVE-узлами, первой ASUS-рельсой и двумя
коммутаторами. Остальное оборудование не считается сломанным только потому,
что оно не включено или не подключено после переезда.

Зафиксированные ограничения, без назначения порядка выполнения:

- inter-switch LACP временно работает через один member link; владелец знает и
  восстановит второй отдельно;
- `pve01`–`pve03` работают без A/B power redundancy, поскольку пока не хватает
  PDU и силовых кабелей;
- JBOD намеренно выключены до покупки отдельного шкафа, направляющих и
  сопутствующей физической инфраструктуры;
- port maps и оставшиеся IPMI-проверки актуализируются при соответствующих
  физических работах.

Конкретные приоритеты, порядок и состав закупок задаёт владелец кластера. M4 не
разрешает автоматически начинать закупки, destructive storage actions,
перекоммутацию или присоединение новых PVE-узлов.

## Следующие этапы

### M5 — отказоустойчивость и восстановление

Статус: planned

- независимый backup;
- restore test;
- контролируемый `fw01` replica failover;
- решение по HA/fencing;
- LAN2/bonding после стабилизации inter-switch network;
- runbooks для отказа PVE, firewall и storage head.

### M6 — безопасное расширение compute

Статус: planned

- полная inventory `pve04`/`pve05`;
- измерение power/thermal;
- ввод PVE-узлов по одному только после quorum review;
- добавление Supermicro HTCondor execute VM;
- расширение ASUS по одной рельсе с PXE и monitoring acceptance test.

### M7 — storage productionization

Статус: deferred / blocked by physical infrastructure and procurement

- определить требуемую доступность общего `/data`;
- после решения владельца и необходимых закупок вернуть и описать
  single-shelf topology;
- выполнить SMART/burn-in и slot mapping;
- определить backup для уникальных данных;
- расширять JBOD только короткими маркированными SAS-цепочками;
- вернуться к Ceph только при выполнении условий ADR и наличии сети.

### M8 — эксплуатационная зрелость

Статус: planned

- alerts и contacts;
- централизованные логи;
- регулярные restore/failover/thermal drills;
- жизненный цикл пользователей и квоты;
- обновления и maintenance windows;
- автоматический documentation/link/staleness check.

### M9 — дополнительные возможности

Статус: deferred

- JupyterHub/Open OnDemand;
- GPU scheduling;
- HTCondor power management ASUS;
- LDAP/AD;
- DIRAC/LHCb integration;
- отдельный Slurm/MPI pool при подтверждённой потребности.

## Ограничения, которые нельзя обходить

- Не считать ZFS replication резервной копией.
- Не включать весь ASUS-парк до подтверждения электрики и охлаждения.
- Не выключать массово голосующие PVE-узлы.
- Не добавлять Ceph на случайной 1GbE-схеме.
- Не публиковать Proxmox/IPMI в интернет.
- Не выполнять storage wipe, failover или hard power-off без отдельного
  проверенного runbook и явного окна работ.

## Связанные документы

- [Текущее состояние](../current-state.md).
- [Открытые задачи](open-issues.md).
- [Основной план документации](../documentation-reorganization-plan.md).
