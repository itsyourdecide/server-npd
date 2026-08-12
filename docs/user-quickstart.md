# NPD Cluster Quickstart

This is the short instruction to send to a first test user.

## 1. Send Your SSH Public Key

On your computer:

```bash
ssh-keygen -t ed25519 -C "<your-name>@npd"
cat ~/.ssh/id_ed25519.pub
```

Send the single public key line to the cluster administrator. Do not send
`id_ed25519`; that is the private key.

## 2. Configure SSH

After the administrator creates your account, add this to `~/.ssh/config`.
Replace `<username>` with your cluster login.

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

Connect:

```bash
ssh npd-condor
```

## 3. Submit A Test Job

On `npd-condor`:

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

After it finishes:

```bash
cat hello.*.out
cat hello.*.err
```

## Current Limits

- Login is SSH-key only.
- No sudo access.
- Large shared `/data` storage may be offline during the first test phase.
- Keep first tests small until the administrator confirms storage and quotas.
