# Network snapshot: 2026-07-10 after server-room move

Purpose: preserve the working network and Tailscale state of the three Proxmox nodes after the move to the server room and the router/WAN fix.

Important: this snapshot intentionally does not include `/var/lib/tailscale/tailscaled.state`, because that file contains device secrets.

## Nodes

| Node | MGMT | Corosync | Tailscale IPv4 | Default route |
| --- | --- | --- | --- | --- |
| `pve01` | `10.10.10.11/24`, plus direct `192.168.31.50/24` | `10.10.20.11/24` | `100.110.23.10` | `192.168.31.1` via `vmbr0` |
| `pve02` | `10.10.10.12/24` | `10.10.20.12/24` | `100.100.173.60` | `10.10.10.1` via `vmbr0.10` |
| `pve03` | `10.10.10.13/24` | `10.10.20.13/24` | `100.86.225.123` | `10.10.10.1` via `vmbr0.10` |

## Captured Per Node

- `/etc/network/interfaces`
- `/etc/network/interfaces.d/`
- `/etc/hosts`
- `/etc/resolv.conf`
- `ip -br addr`
- `ip addr show`
- `ip route show table all`
- `ip rule show`
- `ip -d link show`
- `bridge link show`
- `bridge vlan show`
- `pvecm status`
- `systemctl status tailscaled`
- `tailscale status`
- `tailscale status --json`
- `tailscale ip`
- `tailscale debug prefs`
- `tailscale netcheck`

## Current WAN Note

After the router move, `fw01` WAN was renewed to `192.168.31.90/24` with gateway/DNS via `192.168.31.1`. Post-fix checks confirmed:

- `pve02 -> 1.1.1.1`: OK
- `pxe01 -> 1.1.1.1`: OK
- `pxe01 DNS via 10.10.80.1`: OK
- AlmaLinux repo HTTP from `pxe01`: OK
