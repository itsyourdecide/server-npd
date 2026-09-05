# Roadmap кластера server-npd

Статус: current
Последняя редакция: 2026-09-05
Живая проверка при редакции: не выполнялась
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

### M4 — подтвердить физическую и эксплуатационную базу

Статус: next

Порядок:

1. Восстановить и испытать оба линка inter-switch LACP.
2. Проверить вторые PSU `pve01`–`pve03`.
3. Уточнить online/offline состояние JBOD и NFS.
4. Сверить фактические port maps с живой конфигурацией.
5. Завершить IPMI-проверку первой ASUS-рельсы.
6. Зафиксировать актуальные health-check результаты в current state.

Работы M4 не должны автоматически включать destructive storage actions или
присоединение новых PVE-узлов.

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

Статус: planned / partially blocked

- определить требуемую доступность общего `/data`;
- восстановить и описать single-shelf topology;
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
