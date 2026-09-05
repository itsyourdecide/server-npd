# Proxmox cluster

- Статус: current snapshot
- Последняя подтверждённая общая проверка: 2026-08-13
- Источник истины для: роли Proxmox и границ его эксплуатации

## Deployed

- cluster name: `npd`;
- members: `pve01`, `pve02`, `pve03`;
- management: `10.10.10.11`–`10.10.10.13`;
- Corosync: `10.10.20.11`–`10.10.20.13`;
- local ZFS на узлах;
- ZFS replication первых критичных VM;
- основные инфраструктурные VM/LXC размещены на `pve02`.

## Health check

```bash
cd /root/server-npd
./scripts/cluster-health.sh --skip-storage
```

Storage assertions включаются только когда JBOD/NFS намеренно online.

Дополнительно проверяются:

```bash
pvecm status
pvesr status
qm list
pct list
```

## HA boundary

- Наличие трёх cluster members даёт quorum, но не делает каждую VM HA.
- ZFS replication асинхронна и имеет ненулевой RPO.
- Planned migration `fw01` проверена; uncontrolled failure и fencing — нет.
- Replication не заменяет backup.
- До настройки LAN2 каждый PVE зависит от основного LAN path.

## Expansion rule

Новый PVE-узел добавляется только после hardware inventory, burn-in, проверки
обоих PSU, network, power/thermal и пересчёта quorum. Наличие кабеля в switch не
означает готовность узла к `pvecm add`.

## Related

- [ADR-0001](../architecture/decisions/0001-proxmox-on-supermicro.md).
- [Current state](../current-state.md).
- [fw01 failover runbook](../runbooks/fw01-failover.md).
- [Open issues](../project/open-issues.md).
