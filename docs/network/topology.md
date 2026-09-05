# Сетевая топология

- Статус: current/target split
- Последняя редакция: 2026-09-05
- Живая проверка при редакции: не выполнялась
- Источник истины для: логической связи сетевых компонентов

## Последняя документированная схема

```text
                 external/lab router
                   |             |
             WAN_TEMP 99    WAN_TEMP 99
                   |             |
             HP 3500yl ===== Force10 S60
             ASUS rack       Supermicro rack
                  2 x 1GbE LACP
                   (1 link degraded on 2026-08-11)

HP 3500yl                         Force10 S60
  ASUS LAN/IPMI                     pve01-pve05 LAN1/IPMI
  reserved PVE LAN2                 reserved pve06-pve10
  VLAN 10/20/30/40/50/80            VLAN 10/20/30/40/50/80/99
```

`fw01`/OPNsense маршрутизирует VLAN 10, 30, 40, 50 и 80. Corosync VLAN 20 не
маршрутизируется как пользовательская сеть. VLAN 60/61 зарезервированы, но Ceph
не развёрнут.

## Deployed и reserved

### Deployed

- `pve01`–`pve03` LAN1 на Force10;
- IPMI `pve01`/`pve02`; статус `pve03` требует новой проверки;
- четыре ASUS LAN на HP 3500yl;
- четыре ASUS IPMI физически подключены, две последние BMC-проверки pending;
- inter-switch LACP, но последнее состояние degraded;
- `fw01` как VLAN router/firewall.

### Reserved/target

- LAN1/IPMI `pve04`/`pve05` физически видны, но узлы не введены в кластер;
- LAN2 `pve01`–`pve10` зарезервирован на HP, bonding не настроен;
- порты для остальных ASUS и Supermicro;
- отдельные IPMI switches;
- Ceph VLAN 60/61 и 10GbE topology;
- production WAN без зависимости от временного VLAN 99.

## Failure boundaries

- Отказ ASUS-порта уменьшает compute capacity, но не должен ломать control plane.
- Отказ одного inter-switch member должен переживаться LACP; этот сценарий нужно
  повторно испытать после ремонта NET-001.
- До настройки LAN2 отказ Force10 или LAN1 может отрезать PVE-узел.
- `fw01` остаётся критичной точкой routing; planned migration проверена, полный
  replica failover — нет.
- IPMI VLAN предоставляет аппаратный контроль и должен быть доступен только
  администраторам.

## Источники физического состояния

- [Force10](force10-ports.md).
- [HP 3500yl](hp3500-ports.md).
- [Целевая раскладка](target-port-plan.md).
- [Адресация](addressing.md).

Перед физическими работами port maps нужно сверить с живыми `show`-командами.
Этот diagram сам по себе не является разрешением на переподключение.
