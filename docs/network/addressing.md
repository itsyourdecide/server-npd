# Адресация и VLAN

- Статус: current, основан на последнем документированном состоянии
- Последняя редакция: 2026-09-05
- Живая проверка при редакции: не выполнялась
- Источник истины для: VLAN ID, подсетей, gateway и зарезервированных адресов

## VLAN

| VLAN | Имя | Сеть | Gateway | Состояние |
|---:|---|---|---|---|
| 10 | MGMT | `10.10.10.0/24` | `10.10.10.1` | deployed |
| 20 | COROSYNC | `10.10.20.0/24` | отсутствует | deployed, routed access не требуется |
| 30 | IPMI | `10.10.30.0/24` | `10.10.30.1` | deployed |
| 40 | PRIVATE_VM | `10.10.40.0/24` | `10.10.40.1` | deployed |
| 50 | DMZ | `10.10.50.0/24` | `10.10.50.1` | deployed |
| 60 | CEPH_PUBLIC | `10.10.60.0/24` | отсутствует | reserved, Ceph deferred |
| 61 | CEPH_CLUSTER | `10.10.61.0/24` | отсутствует | reserved, Ceph deferred |
| 80 | HTCONDOR_PXE | `10.10.80.0/24` | `10.10.80.1` | deployed |
| 99 | WAN_TEMP | внешний DHCP | внешний router | временная лабораторная схема |

VLAN 60/61 нельзя считать действующими Ceph-сетями только потому, что номера
зарезервированы. VLAN 99 не является production WAN design.

## Core-узлы

| Имя | Management | Corosync | IPMI | Состояние |
|---|---|---|---|---|
| `pve01` | `10.10.10.11` | `10.10.20.11` | `10.10.30.11` | deployed |
| `pve02` | `10.10.10.12` | `10.10.20.12` | `10.10.30.12` | deployed |
| `pve03` | `10.10.10.13` | `10.10.20.13` | `10.10.30.13` | deployed; последний port status IPMI требовал проверки |

## Инфраструктурные сервисы

| Имя | Адрес | VLAN | Роль |
|---|---|---:|---|
| `monitor01` | `10.10.10.30` | 10 | Prometheus |
| `bastion01` | `10.10.50.10` | 50 | SSH bastion |
| `pxe01.internal` | `10.10.80.10` | 80 | PXE/iPXE HTTP/TFTP |
| `squid01.internal` | `10.10.80.11` | 80 | CVMFS proxy/cache |
| `condor01.internal` | `10.10.80.20` | 80 | HTCondor manager+submit |
| NFS export на `pve01` | `10.10.80.2` | 80 | `/data`, доступность требует проверки |

## ASUS rail 1

| Имя | OS | IPMI | Состояние последней документации |
|---|---|---|---|
| `asus-r1n1.internal` | `10.10.80.101` | `10.10.30.101` | OS и IPMI verified |
| `asus-r1n2.internal` | `10.10.80.102` | `10.10.30.102` | OS и IPMI verified |
| `asus-r1n3.internal` | `10.10.80.103` | `10.10.30.103` | OS verified, IPMI pending |
| `asus-r1n4.internal` | `10.10.80.104` | `10.10.30.104` | OS verified, IPMI pending |

## Внешний пользовательский доступ

| Компонент | Адрес |
|---|---|
| `vpn-npd` public endpoint | `20.215.200.4:10000/tcp` |
| `vpn-npd` WireGuard | `10.255.80.1/30` |
| `pve02` WireGuard | `10.255.80.2/30` |
| Tailscale fallback | `pve02.taile43d6d.ts.net:10000` |

Публичный endpoint подтверждался 2026-08-28. Его дальнейшая доступность должна
проверяться `scripts/user-access-health.sh`.

## Правила изменения

- Не назначать новый адрес только через этот файл: сначала определить
  авторитетную конфигурацию/DHCP reservation.
- После изменения обновить inventory, current state, service-документ и history.
- Corosync не получает default gateway.
- IPMI не публикуется наружу.
- Planned-адреса новых узлов хранятся отдельно от deployed-таблиц.

## Связанные документы

- [Текущее состояние](../current-state.md).
- [Сетевая топология](topology.md).
- [Force10 port map](force10-ports.md).
- [HP 3500yl port map](hp3500-ports.md).
- [Target port plan](target-port-plan.md).
