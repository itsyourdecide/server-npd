# Shared Storage Policy

- Статус: current policy; JBOD intentionally offline
- Последний healthy test: 2026-08-07
- Текущее физическое состояние: 2026-09-07 владелец подтвердил, что JBOD
  намеренно выключены до подготовки отдельного шкафа, направляющих и закупок
- Источник истины для: назначения каталогов `/data` и retention policy

Принятая схема размещает shared JBOD storage на `pve01`. Сейчас полки намеренно
выключены и `/data` не входит в работающую конфигурацию. Политика каталогов
остаётся целевой политикой на момент, когда владелец решит вернуть storage.

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

Команды ниже применимы только после отдельного решения владельца о возврате
JBOD и проверки физического подключения:

```bash
cd /root/server-npd
./scripts/apply-storage-policy.sh
./scripts/clean-scratch.sh dry-run
./scripts/storage-smoke.sh 4
./scripts/cluster-health.sh
```

В текущем режиме запускать общую проверку только без storage assertions:

```bash
./scripts/cluster-health.sh --skip-storage
```

## Availability boundary

Этот документ описывает policy, а не требует немедленно возвращать storage.
Пока полки намеренно выключены, отсутствие `npddata` ожидаемо и не является
инцидентом. Не подключать полки и не выполнять `zpool create`, wipe или import
без отдельного решения владельца и готовой физической инфраструктуры.

Связанные документы:

- [Storage topology](storage-topology.md).
- [ADR-0003](../architecture/decisions/0003-zfs-instead-of-ceph.md).
- [Current state](../current-state.md).
- [STO-001](../project/open-issues.md#sto-001--вернуть-jbodnfs-после-подготовки-физической-инфраструктуры).
