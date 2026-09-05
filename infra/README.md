# Действующие конфигурации вне Ansible

- Статус: current repository copies
- Последняя проверка структуры: 2026-09-05
- Назначение: хранить версионируемые исходники конфигураций, не управляемых Ansible
- Источник истины для: repository copy PXE, Nginx, Squid, Prometheus и systemd units

## Состав

- `pxe/` — iPXE scripts, Kickstart, firstboot, install-once и Nginx.
- `monitoring/prometheus.yml` — конфигурация Prometheus для `monitor01`.
- `squid/squid.conf` — конфигурация Squid для CVMFS proxy.
- `systemd/pve02/` — units для Tailscale и WireGuard SSH forwarding.
- `systemd/vpn-npd/` — unit публичного SSH forwarding на gateway.

Файл здесь является авторитетной repository copy, но не доказывает, что такая
же версия применена на живом узле. После deployment нужна проверка, датированная
запись в [history](../docs/history/README.md) и обновление
[current state](../docs/current-state.md).

Сырые выгрузки и старые снимки конфигурации находятся в `evidence/`. Секреты,
private keys, Vault content и runtime state в `infra/` не добавляются.
