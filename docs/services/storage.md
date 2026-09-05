# Shared Storage Policy

- Статус: current policy; фактическая доступность требует проверки
- Последний healthy test: 2026-08-07
- Последний caveat: 2026-08-11 JBOD/pool не был online после физических работ
- Источник истины для: назначения каталогов `/data` и retention policy

Принятая схема размещает shared JBOD storage на `pve01`. Политика каталогов
остаётся действующей даже когда полки намеренно выключены.

- ZFS pool: `npddata`.
- NFS export: `10.10.80.2:/data`.
- Clients: `condor01.internal`, ASUS execute nodes, future Supermicro execute VMs.

Directory policy:

- `/data/projects/npd` is for persistent project data, datasets, configs and
  long-lived inputs.
- `/data/results/npd` is for job outputs that should be kept.
- `/data/scratch/condor` is for temporary HTCondor job data.
- `/data/scratch/users` is for temporary manual/user work.

Cleanup policy:

- Only `/data/scratch` is auto-cleaned.
- Files and empty directories older than 14 days are removed.
- `/data/projects` and `/data/results` are never cleaned by the scratch timer.

Useful commands:

```bash
cd /root/server-npd
./scripts/apply-storage-policy.sh
./scripts/clean-scratch.sh dry-run
./scripts/storage-smoke.sh 4
./scripts/cluster-health.sh
```

When JBOD shelves are intentionally powered off or physically deferred, run the
general health check without storage assertions:

```bash
./scripts/cluster-health.sh --skip-storage
```

## Availability boundary

Этот документ описывает policy, а не доказывает доступность. Перед операциями с
данными выполнить read-only проверки HBA, `zpool status`, NFS export и mount на
клиентах. Не выполнять `zpool create`, wipe или import с force только для того,
чтобы health-check стал зелёным.

Связанные документы:

- [Storage topology](storage-topology.md).
- [ADR-0003](../architecture/decisions/0003-zfs-instead-of-ceph.md).
- [Current state](../current-state.md).
- [STO-001](../project/open-issues.md#sto-001--определить-фактическое-состояние-jbodnfs).
