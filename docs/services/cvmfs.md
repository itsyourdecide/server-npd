# CVMFS client and proxy

- Статус: current snapshot
- Последняя подтверждённая probe/job проверка: 2026-08-07
- Источник истины для: CVMFS client topology и proxy policy

## Deployed

- clients: `condor01` и `asus-r1n1`–`asus-r1n4`;
- repository probes: `sft.cern.ch`, `unpacked.cern.ch`;
- proxy: `squid01.internal`, `10.10.80.11:3128`;
- fallback: direct access.

```text
CVMFS_HTTP_PROXY="http://10.10.80.11:3128|DIRECT"
```

Local proxy уменьшает повторные загрузки, но его отказ не должен полностью
блокировать clients, пока direct fallback разрешён firewall policy.

## Configuration

```bash
cd /root/server-npd/ansible
ansible-playbook playbooks/cvmfs_client.yml --limit 'condor01.internal:asus_nodes'
ansible condor01.internal:asus_nodes -m shell -a 'cvmfs_config probe sft.cern.ch'
```

Авторитетная repository copy Squid находится в
[`infra/squid/squid.conf`](../../infra/squid/squid.conf). После изменения
нужно отдельно подтвердить deployment на `squid01`.

## Verification

Обычная проверка должна включать:

- `cvmfs_config probe`;
- чтение файла из нужного repository;
- небольшой HTCondor job на execute nodes;
- проверку поведения при временно недоступном Squid.

## Expansion rule

Новый repository добавляется только по реальной workload-потребности. После
изменения обновляются Ansible vars, firewall requirements и этот документ.

## Related

- [HTCondor](htcondor.md).
- [PXE](pxe.md).
- [Current state](../current-state.md).
