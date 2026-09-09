# Firewall и routing (`fw01`)

- Статус: current snapshot
- Последняя общая health-check: 2026-08-13; `wg-site` handshake отдельно
  проверен 2026-09-09
- Источник истины для: роли `fw01` и границ межсетевого доступа

## Role

`fw01` — OPNsense VM 100, последнее документированное размещение `pve02`.
Она предоставляет gateway, routing, DHCP/DNS и firewall policy для внутренних
VLAN.

| VLAN | Gateway | Основная политика |
|---:|---|---|
| 10 | `10.10.10.1` | административный management |
| 30 | `10.10.30.1` | BMC без самостоятельного публичного доступа |
| 40 | `10.10.40.1` | private VM с outbound access |
| 50 | `10.10.50.1` | DMZ, deny внутрь кроме явных правил |
| 80 | `10.10.80.1` | HTCondor/PXE package и service access |

Corosync VLAN 20 и зарезервированные Ceph VLAN 60/61 не должны зависеть от
обычной пользовательской маршрутизации.

## Parallel Azure site tunnel

На `fw01` 2026-09-09 создана и проверена WireGuard instance `wg-site`:

| Параметр | Значение |
|---|---|
| Tunnel address | `10.255.82.2/30` |
| Local listen port | UDP `51823` |
| Azure peer | `20.215.200.4:51822` |
| Azure tunnel address | `10.255.82.1/32` |
| Persistent keepalive | `25` секунд |

Handshake и двусторонние WireGuard counters подтверждены. Local port OPNsense
был отделён от destination port Azure после диагностики прохождения через
внешний NAT. Точный upstream NAT/router, который не пропускал исходный поток
`51822 -> 51822`, не идентифицирован.

Этот checkpoint подтверждает только encrypted transfer network. WireGuard
device ещё не считается разрешённой административной зоной: rules/routes во
VLAN, доступ к GUI/VM, `wg-admin` и public service flows не настроены.

## User access exception

Для ProxyJump требуется узкое правило:

```text
source:      10.10.50.10 (bastion01)
destination: 10.10.80.20 (condor01)
protocol:    TCP/22
```

Оно располагается выше общего запрета DMZ → HTCONDOR. Разрешение ICMP или всей
VLAN50 во VLAN80 для этого не требуется.

## Recovery boundary

- Planned live migration `fw01` проверена 2026-07-08.
- Replica failover с переносом ownership не испытан.
- Ошибка `fw01` может остановить routing, DNS/DHCP и outbound access, но не
  должна разрушать Corosync.
- Перед failover обязателен локальный/консольный fallback.

## Configuration source

Владелец подтвердил создание актуального OPNsense backup 2026-09-09 вне Git.
Export не добавляется в repository, поскольку может содержать key material и
другие secrets. Журнал операций остаётся только историческим свидетельством и
не заменяет защищённый backup.

## Related

- [Addressing](../network/addressing.md).
- [Network topology](../network/topology.md).
- [Azure edge и WireGuard plan](../network/azure-edge-vpn-plan.md).
- [Failover runbook](../runbooks/fw01-failover.md).
- [Open issue HA-001](../project/open-issues.md#ha-001--провести-контролируемый-replica-failover-fw01).
