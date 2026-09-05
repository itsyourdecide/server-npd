# Monitoring

- Статус: current snapshot
- Последняя проверка: 2026-08-13
- Источник истины для: состава phase 1 monitoring и процедуры проверки

Phase 1 monitoring использует Prometheus и node exporter. Указанный ниже список
targets подтверждался как 11/11 `up` 2026-08-13 и не является автоматической
гарантией более позднего состояния.

## Services

- `monitor01` LXC on `pve02`.
- CTID: `112`.
- IP: `10.10.10.30/24`.
- Prometheus UI: `http://10.10.10.30:9090`.
- Node exporter: `http://10.10.10.30:9100/metrics`.

## Scrape Targets

Prometheus scrapes:

- Proxmox nodes:
  - `pve01` `10.10.10.11:9100`
  - `pve02` `10.10.10.12:9100`
  - `pve03` `10.10.10.13:9100`
- Monitoring:
  - `monitor01` `10.10.10.30:9100`
  - Prometheus itself `10.10.10.30:9090`
- Bastion:
  - `bastion01` `10.10.50.10:9100`
- HTCondor:
  - `condor01` `10.10.80.20:9100`
  - `asus-r1n1` `10.10.80.101:9100`
  - `asus-r1n2` `10.10.80.102:9100`
  - `asus-r1n3` `10.10.80.103:9100`
  - `asus-r1n4` `10.10.80.104:9100`

## Checks

```bash
cd /root/server-npd
./scripts/monitoring-health.sh
./scripts/cluster-health.sh
```

`monitoring-health.sh` expects all 11 Prometheus targets to be `up`.

## Extending

For new AlmaLinux execute nodes:

```bash
cd /root/server-npd/ansible
ansible-playbook playbooks/node_exporter.yml --limit asus_nodes
```

Authoritative repository copy находится в
[`infra/monitoring/prometheus.yml`](../../infra/monitoring/prometheus.yml).
Добавить node туда, проверить конфигурацию,
доставить её как `/etc/prometheus/prometheus.yml`, перезапустить Prometheus и
обновить current state/history.

## Known limitations

- target count `11` зафиксирован в health-check и требует обновления при
  расширении;
- alerts и notification routing не документированы как действующие;
- central logs и дежурная процедура входят в roadmap.

Связанные документы: [current state](../current-state.md),
[open issues](../project/open-issues.md).
