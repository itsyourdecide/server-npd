# User Access Workflow

Status: phase 1, SSH-only user access. Users are created manually by the
administrator. No shared password, anonymous login, VPN requirement, or public
Proxmox access.

## Current Shape

```text
Internet user
  -> Tailscale Funnel on pve02, tcp/10000
  -> pve02 localhost tcp/10022
  -> bastion01 10.10.50.10:22
  -> ProxyJump to condor01 10.10.80.20:22
  -> HTCondor submit from condor01
  -> ASUS execute nodes
```

Roles:

| Host | Role | Address |
|---|---|---|
| `pve02` | public Funnel endpoint and local TCP forward | `pve02.taile43d6d.ts.net` |
| `bastion01` | SSH bastion only | `10.10.50.10`, CTID `102` on `pve02` |
| `condor01` | HTCondor central manager + submit node | `10.10.80.20` |
| `asus-r1n1`-`asus-r1n4` | first execute nodes | `10.10.80.101`-`10.10.80.104` |

Public endpoints:

```text
https://pve02.taile43d6d.ts.net
ssh -p 10000 <username>@pve02.taile43d6d.ts.net
```

The SSH endpoint is the important one. The web endpoint is only a lightweight
landing/check page for now.

## Security Model

Network/firewall requirement:

- OPNsense `DMZ` rules must include a narrow pass rule above `Block DMZ to
  HTCONDOR`:
  - source: `10.10.50.10` (`bastion01`);
  - destination: `10.10.80.20` (`condor01`);
  - protocol/port: TCP/22.
- ICMP from `bastion01` to `condor01` can stay blocked. The user workflow only
  needs SSH forwarding to TCP/22.

`bastion01` SSH hardening:

- root SSH login disabled;
- password and keyboard-interactive login disabled;
- public key authentication enabled;
- agent forwarding disabled;
- TCP forwarding enabled for `ProxyJump`;
- X11 forwarding disabled;
- `fail2ban` enabled for `sshd`;
- node exporter enabled for monitoring.

Users:

- get a normal Linux account on `bastion01` and `condor01`;
- authenticate only with their SSH public key;
- get no sudo privileges;
- use UID range `20000-29999`, reserved for human cluster users;
- submit HTCondor jobs from `condor01`.

Important: users should normally connect directly to `condor01` through
`ProxyJump`, not log into `bastion01` first and then SSH onward. Agent
forwarding is intentionally disabled on `bastion01`, so direct second-hop SSH
from inside bastion is not the default path.

## Admin Workflow

Ask the user for:

- desired lowercase login name, for example `denis`;
- SSH public key, usually `id_ed25519.pub`;
- short purpose / expected workload.

Store the public key temporarily on `pve01`, then run:

```bash
cd /root/server-npd
./scripts/create-cluster-user.py <username> /path/to/id_ed25519.pub
```

The script:

- validates the login name and OpenSSH public key;
- allocates the first free UID in `20000-29999`, unless `--uid` is given;
- creates the same locked-password, key-only account on `bastion01`;
- creates the same account on `condor01`;
- creates `/data` user directories only when `/data` is mounted and accessible.

Current storage note: JBOD/NFS storage may be intentionally offline. In that
case the script skips `/data/projects/users/<user>`,
`/data/results/users/<user>`, and `/data/scratch/users/<user>`. This is OK for
phase 1: basic HTCondor jobs can still run from the user's home directory on
`condor01`. After JBOD is online, re-run:

```bash
cd /root/server-npd
./scripts/create-cluster-user.py <username> /path/to/id_ed25519.pub --storage-only
```

Use `--accounts-only` when you explicitly do not want to touch `/data`.

## Admin Verification

Replace `<username>` before running.

```bash
# Account exists on bastion01.
ssh pve02 'pct exec 102 -- id <username>'

# Account exists on condor01.
ssh npdadmin@10.10.80.20 'id <username>'

# Public entry is open.
nc -vz -w 5 pve02.taile43d6d.ts.net 10000

# Bastion can reach the Condor submit host over SSH.
ssh pve02 'pct exec 102 -- nc -vz -w 5 10.10.80.20 22'

# Cluster user can reach condor01 through the bastion.
ssh -J <username>@pve02.taile43d6d.ts.net:10000 <username>@10.10.80.20 'hostname; condor_q'
```

Run the full health check after user provisioning:

```bash
cd /root/server-npd
./scripts/cluster-health.sh --skip-storage
```

## User SSH Config

Recommended `~/.ssh/config` for the user:

```sshconfig
Host npd-bastion
  HostName pve02.taile43d6d.ts.net
  Port 10000
  User <username>
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes

Host npd-condor
  HostName 10.10.80.20
  User <username>
  ProxyJump npd-bastion
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
```

Login:

```bash
ssh npd-condor
```

One-shot command:

```bash
ssh npd-condor 'hostname; condor_q'
```

## Minimal HTCondor Job

Run this on `condor01` as the user:

```bash
mkdir -p ~/condor-tests/hello
cd ~/condor-tests/hello

cat > hello.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "hello from $(hostname)"
date
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

When the job finishes:

```bash
cat hello.*.out
cat hello.*.err
condor_history -limit 5
```

## What Changes After JBOD Storage

When `/data` is permanently online:

- user project input lives in `/data/projects/users/<username>`;
- job results live in `/data/results/users/<username>`;
- temporary shared data lives in `/data/scratch/users/<username>`;
- storage checks in `cluster-health.sh` should run without `--skip-storage`.

Until then, keep first user tests small and home-directory based.

## Validation Notes

2026-08-12 end-to-end validation:

- temporary user `npdtest` was created with UID `20000`;
- public login to `bastion01` through Tailscale Funnel worked;
- ProxyJump from `bastion01` to `condor01` worked after the OPNsense DMZ rule
  above was added;
- a minimal HTCondor job submitted by `npdtest` completed on
  `asus-r1n1.internal` with exit code 0;
- `npdtest` had no sudo access on `condor01`.

## Future UI Layer

Phase 1 is intentionally SSH-only. Later options:

- JupyterHub for browser notebooks and interactive Python work;
- Open OnDemand if the workflow becomes a more traditional HPC portal;
- a small custom landing page with examples, status, and request form.
