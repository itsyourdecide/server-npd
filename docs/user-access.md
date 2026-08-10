# User Access Layer

## Recommendation

Use two layers:

1. `bastion01` for SSH access and `ProxyJump`.
2. JupyterHub later for browser-based interactive work and notebooks.

Open OnDemand remains a candidate for a future HPC portal, but it is not the
first choice for the current HTCondor-only phase. It is strongest when the site
already has a traditional HPC scheduler workflow and web apps to expose.

## Bastion

- Hostname: `bastion01`.
- CTID: `102`.
- Proxmox host: `pve02`.
- VLAN: `50` DMZ.
- IP: `10.10.50.10/24`.
- Gateway/DNS: `10.10.50.1`.
- OS: Debian 12 LXC.
- Resources: 1 vCPU, 1G RAM, 16G rootfs.

SSH hardening:

- Root SSH login disabled.
- Password and keyboard-interactive login disabled.
- Public key auth enabled.
- Agent forwarding disabled.
- TCP forwarding enabled for SSH `ProxyJump`.
- X11 forwarding disabled.
- `fail2ban` enabled for `sshd`.

Monitoring:

- `prometheus-node-exporter` listens on `10.10.50.10:9100`.
- `monitor01` scrapes it as role `bastion`.

## Not Exposed Yet

No WAN/NAT/port-forward rule has been created yet.

Before exposing SSH to users, decide:

- Public entry method: university public IP, router port forward, VPN/Tailscale,
  or reverse tunnel/VPS.
- User list and SSH public keys.
- Which internal hosts users may reach through `ProxyJump`.
- Whether users get direct shell access on `bastion01`, or only jump access.

## Example SSH Config

After a user's SSH key is installed and external access is published:

```sshconfig
Host bastion01
  HostName <public-host-or-ip>
  User <username>
  IdentityFile ~/.ssh/<key>

Host condor01
  HostName 10.10.80.20
  User <username>
  ProxyJump bastion01
```
