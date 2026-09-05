# Реестр оборудования

- Статус: current, основан на последнем документированном inventory
- Последняя редакция: 2026-09-05
- Живая проверка при редакции: не выполнялась
- Источник истины для: подтверждённых hardware facts и неизвестных параметров

## Supermicro

| Узел | Последние подтверждённые CPU/RAM | Storage/NIC/HBA | Состояние |
|---|---|---|---|
| `pve01` | 2× Xeon E5-2620 v4, около 512 GiB RAM | 2× local SSD; Intel X540-AT2; SAS9305-16i и SAS9305-16e | в кластере `npd` |
| `pve02` | 2× Xeon E5-2620 v4, около 512 GiB RAM | 2× local SSD; HBA class SAS3224/SAS3216 | в кластере `npd` |
| `pve03` | 2× Xeon E5-2620 v4, около 512 GiB RAM | 2× local SSD; HBA class SAS3224/SAS3216 | в кластере `npd` |
| future `pve04` | не завершено | LAN/IPMI физически видны на Force10 | не введён в кластер |
| future `pve05` | не завершено | LAN/IPMI физически видны на Force10 | не введён в кластер |
| `pve06`–`pve10` | unknown | unknown | target only |

Последний power/thermal baseline трёх PVE выполнялся 2026-07-10. Все три узла
сообщали `PS2 Status` failed/not OK; повторное подтверждение после физической
проверки отсутствует.

## ASUS rail 1

| Узел | OS role | OS IP | IPMI IP | Последнее состояние |
|---|---|---|---|---|
| `asus-r1n1` | AlmaLinux/HTCondor execute | `10.10.80.101` | `10.10.30.101` | OS+IPMI documented healthy |
| `asus-r1n2` | AlmaLinux/HTCondor execute | `10.10.80.102` | `10.10.30.102` | OS+IPMI documented healthy |
| `asus-r1n3` | AlmaLinux/HTCondor execute | `10.10.80.103` | `10.10.30.103` | OS healthy, IPMI pending |
| `asus-r1n4` | AlmaLinux/HTCondor execute | `10.10.80.104` | `10.10.30.104` | OS healthy, IPMI pending |

Подтверждено для первой партии:

- шасси семейства ASUS R21A, четыре узла в рельсе;
- dedicated IPMI используется вместо Shared LAN/NC-SI;
- legacy PXE boot требует специального iPXE flow;
- BMC family AST/IPMI 2.0, в исходной проверке firmware 2.13;
- whole-rail CPU load измерялся около 1300 W.

Не подтверждено для полного парка:

- точное число шасси и исправных узлов;
- распределение RS720QA/RS724QA;
- InfiniBand adapters, switch и кабели;
- PSU/BMC/boot status каждой следующей рельсы.

## JBOD

Последнее подтверждённое оборудование первой полки:

- Promise `4U-SAS-24-12G BP`;
- 24 disk slots;
- 24× Toshiba `MG04ACA600E`, около 6 TB nominal;
- management Ethernet и serial console;
- enclosure id `0x50001555fe256000`;
- подключение через внешний SAS9305-16e `pve01`.

Точное число полок оценивается как 8–12, но не подтверждено полным inventory.
Online-состояние pool не является hardware fact и ведётся в
[current state](../current-state.md).

## Network equipment

| Устройство | Роль | Последнее известное состояние |
|---|---|---|
| Dell Force10 S60 (`force10-sm`) | шкаф Supermicro | 44 copper 1GbE, 4 SFP 1GbE, 2 SFP+ 10GbE; deployed |
| HP 3500yl-48G (`switch1`/`hp3500`) | шкаф ASUS | 48×1GbE; deployed |
| отдельный IPMI switch | разгрузка production ports | planned |

Фактические подключения находятся в [network](../network/topology.md), а не в
этом inventory.

## Power measurements

| Класс | Последнее измерение |
|---|---:|
| Supermicro heavy | около 240 W/узел |
| ASUS rail, 4 nodes CPU load | около 1300 W |
| Force10/HP switch max observed | около 200 W/устройство |
| JBOD startup | около 350 W/полка |
| JBOD idle | около 230 W/полка |

Полные результаты: [power characterization](../../evidence/measurements/2026-08-12-power-characterization/README.md).

## Как обновлять

Использовать [hardware inventory runbook](../runbooks/hardware-inventory.md).
Непроверенные предположения заносить как `unknown`, а не копировать параметры
с похожего узла.
