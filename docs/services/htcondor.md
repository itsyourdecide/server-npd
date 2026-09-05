# HTCondor pool

- Статус: current snapshot
- Последняя end-to-end identity/job проверка: 2026-08-13
- Источник истины для: topology и operational policy основного scheduler

## Topology

| Role | Nodes |
|---|---|
| Central manager | `condor01.internal` (`10.10.80.20`) |
| Submit/access point | `condor01.internal` |
| Bare-metal execute | `asus-r1n1.internal`–`asus-r1n4.internal` |
| Supermicro execute VM | planned, inventory group пока пуст |

HTCondor является основным scheduler. Slurm не развёрнут и рассматривается
только для будущих многонодовых MPI-задач.

## Configuration

Ansible playbooks:

```bash
cd /root/server-npd/ansible
ansible-playbook playbooks/htcondor_manager.yml
ansible-playbook playbooks/htcondor_execute.yml --limit asus_nodes
```

Pool password хранится локально в
`ansible/inventory/group_vars/all/vault.yml` и не коммитится.

## Identity

```text
UID_DOMAIN = internal
TRUST_UID_DOMAIN = True
FILESYSTEM_DOMAIN = per-host FQDN
```

Human user должен иметь одинаковый numeric UID на `condor01` и execute nodes.
Execute-node identity не получает SSH keys. Provisioning выполняется через
`scripts/create-cluster-user.py` согласно
[user access runbook](user-access.md).

## Storage and file transfer

- Малые jobs могут использовать HTCondor file transfer и home на `condor01`.
- `/data` используется только когда NFS подтверждён online на всех нужных
  nodes.
- Per-host `FILESYSTEM_DOMAIN` сохраняется, пока shared filesystem не считается
  постоянно доступной.

## Verification

```bash
cd /root/server-npd
./scripts/cluster-health.sh --skip-storage
```

Для storage end-to-end test после подтверждения JBOD:

```bash
./scripts/storage-smoke.sh 4
```

## Known limitations

- manager и submit совмещены в одной VM;
- нет Supermicro execute VM;
- automatic power management не реализован;
- quota/fair-share policy не описана как production-ready;
- `/data` availability требует новой проверки.

## Related

- [ADR-0002](../architecture/decisions/0002-htcondor-primary-scheduler.md).
- [CVMFS](cvmfs.md).
- [Storage](storage.md).
- [Current state](../current-state.md).
