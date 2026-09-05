# Карта портов Force10 S60

- Статус: current snapshot, требует повторной живой проверки
- Последняя проверка: 2026-08-11
- Источник истины для: последнего документированного назначения портов Force10

Карта построена по `show interfaces status`, `show mac-address-table` и
`show vlan` с `force10-sm`. Целевая раскладка находится отдельно:
[target-port-plan.md](target-port-plan.md).

Документ не подтверждает состояние позднее 2026-08-11. После изменения кабелей
или VLAN его нужно обновить вместе с current state и исторической записью.

## Management

- Device: Dell Force10 S60.
- Hostname: `force10-sm`.
- Management Ethernet: `192.168.31.60/24`.
- SSH: enabled, user `admin`, пароль хранится вне репозитория.
- Особенность SSH FTOS: нужен совместимый клиент/профиль с legacy algorithms
  (`diffie-hellman-group14-sha1`, `ssh-rsa`, `3des-cbc`).

## Текущее назначение портов

| Порт | Устройство | Untagged/native | Tagged | Статус 2026-08-11 |
|---:|---|---:|---|---|
| `Gi 0/0` | Аплинк к роутеру | 99 | — | Up, 1000 Full |
| `Gi 0/1` | LACP-транк к switch1 / `Po1` | — | 10,20,30,40,50,80 | **Down**, требует проверки кабеля |
| `Gi 0/2` | LACP-транк к switch1 / `Po1` | — | 10,20,30,40,50,80 | Up, 1000 Full |
| `Gi 0/3` | `pve01` LAN1 trunk, MAC `ac:1f:6b:4c:d7:43` | 10 | 20,30,40,50,80,99 | Up, 1000 Full |
| `Gi 0/4` | `pve02` LAN1 trunk, MAC `ac:1f:6b:41:93:a4` | 10 | 20,30,40,50,80,99 | Up, 1000 Full |
| `Gi 0/5` | `pve03` LAN1 trunk, MAC `ac:1f:6b:41:92:86` | 10 | 20,30,40,50,80,99 | Up, 1000 Full |
| `Gi 0/6` | future `pve04` LAN1 trunk, MAC `ac:1f:6b:4c:d7:ca` | 10 | 20,30,40,50,80,99 | Up, 1000 Full |
| `Gi 0/7` | future `pve05` LAN1 trunk, MAC `ac:1f:6b:4c:d7:c8` | 10 | 20,30,40,50,80,99 | Up, 1000 Full |
| `Gi 0/8-12` | Supermicro LAN1 reserve, future `pve06-pve10` | 10 | 20,30,40,50,80,99 | Down |
| `Gi 0/13` | `pve01` IPMI, MAC `ac:1f:6b:4c:ce:a0` | 30 | — | Up, 1000 Full |
| `Gi 0/14` | `pve02` IPMI, MAC `ac:1f:6b:4c:9f:e6` | 30 | — | Up, 1000 Full |
| `Gi 0/15` | `pve03` IPMI | 30 | — | **Down**, проверить при необходимости |
| `Gi 0/16` | future `pve04` IPMI, MAC `ac:1f:6b:4c:ce:80` | 30 | — | Up, 1000 Full |
| `Gi 0/17` | future `pve05` IPMI, MAC `ac:1f:6b:4c:ce:7f` | 30 | — | Up, 1000 Full |
| `Gi 0/18-22` | Supermicro IPMI reserve, future `pve06-pve10` | 30 | — | Down |
| `Gi 0/23-43` | ASUS LAN reserve, part 1 | 80 | — | Down |
| `Gi 0/44-47` | SFP 1GbE reserve, not RJ45 copper | — | — | Down |
| `Te 0/48-49` | 10GbE SFP+ reserve, future storage/Ceph discussion | — | — | Down |

## VLAN Summary

| VLAN | Purpose | Untagged | Tagged |
|---:|---|---|---|
| 1 | Default VLAN | `Po1(Gi 0/2)` currently still appears here | — |
| 10 | MGMT | `Gi 0/3-12` | `Po1(Gi 0/2)` |
| 20 | Corosync | — | `Gi 0/3-12`, `Po1(Gi 0/2)` |
| 30 | IPMI | `Gi 0/13-22` | `Gi 0/3-12`, `Po1(Gi 0/2)` |
| 40 | Private VM | — | `Gi 0/3-12`, `Po1(Gi 0/2)` |
| 50 | DMZ | — | `Gi 0/3-12`, `Po1(Gi 0/2)` |
| 80 | HTCondor/PXE | `Gi 0/23-43` | `Gi 0/3-12`, `Po1(Gi 0/2)` |
| 99 | WAN_TEMP | `Gi 0/0` | `Gi 0/3-12` |

## Current Findings

- `pve04`/`pve05` physical LAN and IPMI cabling looks correct at switch level.
- Inter-switch LACP is degraded: `Po1` is up only through `Gi 0/2`;
  `Gi 0/1` is down. Expected state is both `Gi 0/1` and `Gi 0/2` up.
- Existing cluster health without JBOD passed after `pve01 nic1` was restored:
  `21 checks, 0 failed, 6 skipped`.

## Quick Verification Commands

On `force10-sm`:

```text
show interfaces status
show mac-address-table
show vlan
show interfaces port-channel 1
show running-config interface gigabitethernet 0/6
show running-config interface gigabitethernet 0/7
show running-config interface gigabitethernet 0/16
show running-config interface gigabitethernet 0/17
```
