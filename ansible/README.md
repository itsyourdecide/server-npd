# NPD Ansible

PXE/Kickstart installs only a small AlmaLinux base with SSH and the
`npdadmin` sudo user. Everything role-specific is applied from here.

Initial flow:

1. Install a node with the `alma9-basic` PXE profile.
2. Add the node IP or DNS name to `inventory/hosts.yml`.
3. Run the base playbook:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/base.yml
```

Later roles:

- `htcondor_execute` for ASUS bare-metal workers and Supermicro execute VMs.
- `cvmfs_client` for CERN/HEP software access.
- `monitoring` after the first HTCondor smoke test.
