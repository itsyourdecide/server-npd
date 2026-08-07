# NPD Ansible

PXE/Kickstart installs only a small AlmaLinux base with SSH and the
`npdadmin` sudo user. Everything role-specific is applied from here.

Initial flow:

1. Install a node with the `alma9-basic` PXE profile.
2. Add the node IP or DNS name to `inventory/hosts.yml`.
3. Run the base playbook:

```bash
cd /root/server-npd/ansible
ansible-playbook playbooks/base.yml
```

Later roles:

- `htcondor_execute` for ASUS bare-metal workers and Supermicro execute VMs.
- `cvmfs_client` for CERN/HEP software access.
- `monitoring` after the first HTCondor smoke test.

Current checkpoint:

- `asus-r1n1.internal` through `asus-r1n4.internal` are installed with the
  base AlmaLinux PXE profile and reachable over SSH.
- `condor01.internal` is planned as the first HTCondor central manager and
  submit node on `pve02`, IP `10.10.80.20`.
- Run base checks with:

```bash
cd /root/server-npd/ansible
ansible asus_nodes -m ping
ansible-playbook playbooks/base.yml --limit asus_nodes
ansible-playbook playbooks/base.yml --limit condor01.internal
```

HTCondor first pool:

```bash
cd /root/server-npd/ansible
ansible-playbook playbooks/htcondor_manager.yml
ansible-playbook playbooks/htcondor_execute.yml --limit asus_nodes
ansible condor01.internal -m shell -a 'condor_status; condor_q'
```

CVMFS client:

```bash
cd /root/server-npd/ansible
ansible-playbook playbooks/cvmfs_client.yml --limit 'condor01.internal:asus_nodes'
ansible condor01.internal:asus_nodes -m shell -a 'cvmfs_config probe sft.cern.ch'
```

CVMFS uses the local Squid proxy first, with direct fallback:

```text
CVMFS_HTTP_PROXY="http://10.10.80.11:3128|DIRECT"
```

Shared JBOD storage:

- pve01 exports the JBOD ZFS pool as NFS at `10.10.80.2:/data`.
- Pool name: `npddata`.
- Datasets: `/data/projects` for persistent project data, `/data/results`
  for job outputs, and `/data/scratch` for temporary shared job data.
- `/data/results` and `/data/scratch` are sticky-writable so HTCondor runtime
  users can write files there.

Mount it on Condor and execute nodes:

```bash
cd /root/server-npd/ansible
ansible-playbook playbooks/storage_client.yml --limit 'condor01.internal:asus_nodes'
ansible condor01.internal:asus_nodes -m shell -a 'findmnt /data && touch /data/scratch/ansible-write-test && rm -f /data/scratch/ansible-write-test'
```

Run an end-to-end storage smoke test through HTCondor:

```bash
cd /root/server-npd
./scripts/storage-smoke.sh
```

The optional first argument is the number of jobs, for example
`./scripts/storage-smoke.sh 8`.

Cluster health check:

```bash
cd /root/server-npd
./scripts/cluster-health.sh
```

Local secret:

- Create `inventory/group_vars/all/vault.yml` locally before HTCondor playbooks.
- It must define `htcondor_pool_password`.
- This file is ignored by git.
