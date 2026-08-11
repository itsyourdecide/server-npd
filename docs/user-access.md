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

## Public Entry

The lab is behind university NAT, so the current public entry is Tailscale
Funnel on `pve02`, not router port forwarding.

Public endpoints:

```text
https://pve02.taile43d6d.ts.net
ssh -p 10000 <username>@pve02.taile43d6d.ts.net
```

Funnel runs on `pve02` and forwards SSH to `bastion01`:

```text
pve02.taile43d6d.ts.net:10000
  -> 127.0.0.1:10022 on pve02
  -> bastion01 10.10.50.10:22
```

The local services that keep this alive after boot:

```text
nginx.service
npd-bastion-ssh-forward.service
npd-tailscale-funnel.service
```

Users are still manually provisioned by an administrator. No shared password or
anonymous account is used.

## Create A User

Ask the user for their SSH public key, for example `id_ed25519.pub`.

From `pve01`:

```bash
cd /root/server-npd
./scripts/create-cluster-user.py <username> /path/to/id_ed25519.pub
```

The script creates the same key-only account on:

- `bastion01`
- `condor01`

It also creates shared storage directories:

```text
/data/projects/users/<username>
/data/results/users/<username>
/data/scratch/users/<username>
```

User IDs are allocated from `20000-29999` so NFS ownership is consistent
between `bastion01`, `condor01`, and `/data`.

Password login remains disabled. The user gets no sudo privileges.

## Example SSH Config

After a user's SSH key is installed:

```sshconfig
Host bastion01
  HostName pve02.taile43d6d.ts.net
  Port 10000
  User <username>
  IdentityFile ~/.ssh/<key>

Host condor01
  HostName 10.10.80.20
  User <username>
  ProxyJump bastion01
```

Quick login test:

```bash
ssh -p 10000 <username>@pve02.taile43d6d.ts.net
ssh condor01
condor_q
```

## Minimal HTCondor Job

On `condor01`:

```bash
mkdir -p ~/condor-tests/hello
cd ~/condor-tests/hello

cat > hello.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "hello from $(hostname)"
date
mkdir -p "/data/results/users/$USER"
printf 'finished on %s\n' "$(hostname)" > "/data/results/users/$USER/hello-result.txt"
EOF
chmod +x hello.sh

cat > hello.sub <<'EOF'
executable = hello.sh
output = hello.$(ClusterId).$(ProcId).out
error = hello.$(ClusterId).$(ProcId).err
log = hello.log
request_cpus = 1
request_memory = 512MB
queue 1
EOF

condor_submit hello.sub
condor_q
```
