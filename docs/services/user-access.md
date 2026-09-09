# Пользовательский доступ

- Статус: current snapshot
- Последняя end-to-end проверка: 2026-08-28
- Источник истины для: topology, security boundary и identity policy пользовательского доступа

Пошаговая выдача аккаунта находится в
[runbook provisioning](../runbooks/provision-user.md), а инструкция для самого
пользователя — в [quickstart](../users/quickstart.md).

## Текущая схема

```text
Internet user
  -> vpn-npd 20.215.200.4:10000
  -> WireGuard 10.255.80.1 <-> 10.255.80.2
  -> pve02 tcp/10022
  -> bastion01 10.10.50.10:22
  -> ProxyJump to condor01 10.10.80.20:22
  -> HTCondor submit
  -> ASUS execute nodes
```

| Компонент | Роль | Адрес / ID |
|---|---|---|
| `vpn-npd` | основной публичный SSH gateway | `20.215.200.4`, WG `10.255.80.1` |
| `pve02` | WireGuard peer и локальный TCP forward | WG `10.255.80.2` |
| `bastion01` | изолированный SSH bastion | `10.10.50.10`, CTID 102 |
| `condor01` | HTCondor manager + submit | `10.10.80.20`, VMID 130 |
| `asus-r1n1`–`asus-r1n4` | первый execute pool | `10.10.80.101`–`104` |

Основная пользовательская точка входа:

```text
ssh -p 10000 <username>@20.215.200.4
```

Tailscale endpoint `pve02.taile43d6d.ts.net:10000` оставлен как
административный fallback и не требуется обычному пользователю.

## Параллельный tunnel в разработке

Проверка 2026-09-09 подтвердила handshake отдельного `wg-site` между
`vpn-npd` (`10.255.82.1`) и `fw01` (`10.255.82.2`). Он пока переносит только
служебный traffic tunnel endpoints и не заменяет описанный выше public
TCP/10000 path.

Через новый tunnel ещё не опубликованы `bastion01`, `portal-dev01` или другие
внутренние endpoints. `wg-admin`, routing во VLAN и правила OPNsense остаются
следующими этапами [плана Azure edge](../network/azure-edge-vpn-plan.md).

## Security boundary

- Нет shared password, anonymous login и публичного Proxmox.
- На `bastion01` запрещены root/password/keyboard-interactive login, agent и
  X11 forwarding; разрешены public key и TCP forwarding для ProxyJump.
- Пользователь не получает sudo.
- OPNsense разрешает только `bastion01` (`10.10.50.10`) → `condor01`
  (`10.10.80.20`) TCP/22 отдельным правилом выше `Block DMZ to HTCONDOR`.
- Execute-node аккаунты не получают SSH keys; они нужны только для запуска
  HTCondor job под одинаковым числовым UID.
- Человеческие UID выделяются из диапазона `20000-29999`.

## HTCondor identity policy

```text
UID_DOMAIN = internal
TRUST_UID_DOMAIN = True
FILESYSTEM_DOMAIN = each host's own FQDN
```

Одинаковый числовой UID должен существовать на `condor01` и execute nodes.
`FILESYSTEM_DOMAIN` остаётся локальным до постоянного подтверждения `/data` на
всех узлах; HTCondor не должен считать локальные home directories общими.

## Storage boundary

Намеренно отключённые JBOD/NFS не блокируют маленькие тестовые job из home
directory. В этом режиме provisioning не создаёт каталоги `/data`, а
health-check явно запускается с `--skip-storage`. После решения владельца о
возврате storage применяется режим `--storage-only` из provisioning runbook.

## Repository configuration

- [`infra/systemd/vpn-npd/`](../../infra/systemd/vpn-npd/) — public gateway
  forwarding unit;
- [`infra/systemd/pve02/`](../../infra/systemd/pve02/) — WireGuard/Tailscale
  forwarding units;
- `scripts/create-cluster-user.py` — account provisioning;
- `scripts/user-access-health.sh` — end-to-end validation.

Repository copy не доказывает deployment; live-состояние подтверждается
проверкой.

## Проверка и история

```bash
./scripts/user-access-health.sh <username>
./scripts/cluster-health.sh --skip-storage
```

Последние документированные проверки:

- 2026-08-12 — ProxyJump и первый job временного пользователя;
- 2026-08-13 — запуск job под реальным UID на ASUS execute node;
- 2026-08-28 — публичный Azure/WireGuard gateway.
- 2026-09-09 — handshake параллельного Azure ↔ OPNsense `wg-site`; без
  service cutover.

Подробности сохранены в [истории за август](../history/operations-2026-08.md) и
[истории за сентябрь](../history/operations-2026-09.md). Проверка нового
tunnel не продлевает автоматически статус старого пользовательского пути.

## Связанные документы

- [Целевой план Azure edge и WireGuard](../network/azure-edge-vpn-plan.md).
- [Current state](../current-state.md).
- [Firewall](firewall.md).
- [HTCondor](htcondor.md).
- [Provision user](../runbooks/provision-user.md).
- [User quickstart](../users/quickstart.md).
