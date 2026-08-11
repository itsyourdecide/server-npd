# Shared Storage Policy

The shared JBOD storage lives on `pve01`.

- ZFS pool: `npddata`.
- NFS export: `10.10.80.2:/data`.
- Clients: `condor01.internal`, ASUS execute nodes, future Supermicro execute VMs.

Directory policy:

- `/data/projects/npd` is for persistent project data, datasets, configs and
  long-lived inputs.
- `/data/results/npd` is for job outputs that should be kept.
- `/data/scratch/condor` is for temporary HTCondor job data.
- `/data/scratch/users` is for temporary manual/user work.

Cleanup policy:

- Only `/data/scratch` is auto-cleaned.
- Files and empty directories older than 14 days are removed.
- `/data/projects` and `/data/results` are never cleaned by the scratch timer.

Useful commands:

```bash
cd /root/server-npd
./scripts/apply-storage-policy.sh
./scripts/clean-scratch.sh dry-run
./scripts/storage-smoke.sh 4
./scripts/cluster-health.sh
```

When JBOD shelves are intentionally powered off or physically deferred, run the
general health check without storage assertions:

```bash
./scripts/cluster-health.sh --skip-storage
```
