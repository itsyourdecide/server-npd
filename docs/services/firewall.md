# Firewall и routing (`fw01`)

- Статус: current snapshot
- Последняя общая health-check: 2026-08-13
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

Полный актуальный OPNsense export не найден среди активных source-controlled
конфигураций. До его появления журнал операций остаётся историческим
свидетельством, но не заменяет backup конфигурации.

## Related

- [Addressing](../network/addressing.md).
- [Network topology](../network/topology.md).
- [Failover runbook](../runbooks/fw01-failover.md).
- [Open issue HA-001](../project/open-issues.md#ha-001--провести-контролируемый-replica-failover-fw01).
