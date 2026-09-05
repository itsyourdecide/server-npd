# Реестр сервисов

- Статус: current snapshot
- Последняя редакция: 2026-09-05
- Живая проверка при редакции: не выполнялась
- Источник истины для: имени, роли, размещения и идентификатора сервисов

| Сервис | Размещение | ID | Адрес | Назначение | Последняя проверка |
|---|---|---:|---|---|---|
| `fw01` | VM на `pve02` | 100 | gateways `.1` VLAN 10/30/40/50/80 | OPNsense routing/firewall | 2026-08-13 |
| `bastion01` | LXC на `pve02` | 102 | `10.10.50.10` | SSH bastion | 2026-08-28 |
| `pxe01` | LXC на `pve02` | 110 | `10.10.80.10` | TFTP/iPXE/Nginx/Alma cache | 2026-08-07 |
| `squid01` | LXC на `pve02` | 111 | `10.10.80.11` | CVMFS proxy/cache | 2026-08-07 |
| `monitor01` | LXC на `pve02` | 112 | `10.10.10.30` | Prometheus | 2026-08-13 |
| `condor01` | VM на `pve02` | 130 | `10.10.80.20` | HTCondor manager+submit | 2026-08-13 |
| `vpn-npd` | Azure VM | — | public `20.215.200.4`, WG `10.255.80.1` | public SSH gateway | 2026-08-28 |

`pve02` в таблице — последнее документированное размещение. Оно не является
HA-гарантией и должно обновляться после миграции.

## Dependencies

```text
vpn-npd -> WireGuard/pve02 -> bastion01 -> condor01 -> HTCondor workers

fw01 -> VLAN routing/DNS/DHCP
pxe01 -> fw01 DHCP/DNS + external AlmaLinux repository
squid01 -> external CVMFS repositories
monitor01 -> network reachability to scrape targets
condor01 -> DNS + execute nodes + optional /data
```

## Planned services

- independent backup/PBS;
- central logging;
- alert routing;
- reverse proxy/web services;
- LDAP/AD integration;
- optional user portal.

Planned services не получают IP/ID в deployed-таблице до создания.

## Связанные документы

- [Current state](../current-state.md).
- [Addressing](../network/addressing.md).
- [Architecture](../architecture/overview.md).
