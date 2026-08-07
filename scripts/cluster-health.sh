#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANSIBLE_DIR="$ROOT_DIR/ansible"
PVE02="10.10.20.12"
PXE_CTID="110"
SQUID_CTID="111"
FW_VMID="100"
CONDOR_VMID="130"
EXPECTED_ASUS_SLOTS="4"

checks=0
failed=0

ok() {
  checks=$((checks + 1))
  printf 'OK   %s\n' "$1"
}

fail() {
  checks=$((checks + 1))
  failed=$((failed + 1))
  printf 'FAIL %s\n' "$1"
}

run_check() {
  local label="$1"
  shift
  if "$@" >/tmp/npd-health.out 2>/tmp/npd-health.err; then
    ok "$label"
  else
    fail "$label"
    sed 's/^/     /' /tmp/npd-health.err
    sed 's/^/     /' /tmp/npd-health.out
  fi
}

check_proxmox_quorum() {
  pvecm status | grep -q 'Quorate:.*Yes'
}

check_cluster_vm() {
  local name="$1"
  pvesh get /cluster/resources --type vm --output-format json | grep -q "\"name\":\"$name\".*\"status\":\"running\""
}

check_pxe_services() {
  ssh -o BatchMode=yes -o ConnectTimeout=5 "root@$PVE02" \
    "pct exec $PXE_CTID -- systemctl is-active --quiet nginx && pct exec $PXE_CTID -- systemctl is-active --quiet tftpd-hpa"
}

check_pxe_http() {
  curl -fsSI --connect-timeout 5 "http://10.10.80.10/boot.ipxe" >/dev/null
}

check_squid_service() {
  ssh -o BatchMode=yes -o ConnectTimeout=5 "root@$PVE02" \
    "pct exec $SQUID_CTID -- systemctl is-active --quiet squid"
}

check_squid_cvmfs_proxy() {
  cd "$ANSIBLE_DIR" || return 1
  ansible condor01.internal -m shell -a 'curl -fsSI --connect-timeout 5 -x http://10.10.80.11:3128 http://cvmfs-stratum-one.cern.ch/cvmfs/sft.cern.ch/.cvmfspublished >/dev/null' >/dev/null
}

check_dns() {
  if command -v dig >/dev/null 2>&1; then
    dig +short @10.10.10.1 condor01.internal A | grep -qx '10.10.80.20'
  else
    getent hosts condor01.internal | awk '{ print $1 }' | grep -qx '10.10.80.20'
  fi
}

check_ansible_ping() {
  cd "$ANSIBLE_DIR" || return 1
  ansible condor01.internal:asus_nodes -m ping >/dev/null
}

check_condor_services() {
  cd "$ANSIBLE_DIR" || return 1
  ansible condor01.internal -m shell -a 'systemctl is-active --quiet condor && condor_q >/dev/null' >/dev/null
}

check_condor_slots() {
  cd "$ANSIBLE_DIR" || return 1
  local slots
  slots="$(ansible condor01.internal -m shell -a "condor_status -af Name | grep -c '^slot'" 2>/dev/null | awk '/^[0-9]+$/ { print $1; exit }')"
  [ "$slots" = "$EXPECTED_ASUS_SLOTS" ]
}

check_condor_smoke_job() {
  cd "$ANSIBLE_DIR" || return 1
  ansible condor01.internal -m shell -a '
set -euo pipefail
workdir=/home/npdadmin/condor-tests/health
rm -rf "$workdir"
mkdir -p "$workdir"
chown -R npdadmin:npdadmin /home/npdadmin/condor-tests
cat > "$workdir/health.sh" <<'"'"'EOF'"'"'
#!/bin/bash
set -e
hostname
EOF
chmod 755 "$workdir/health.sh"
cat > "$workdir/health.sub" <<'"'"'EOF'"'"'
executable = health.sh
output = health.$(Cluster).$(Process).out
error = health.$(Cluster).$(Process).err
log = health.$(Cluster).log
request_cpus = 1
request_memory = 256MB
queue 1
EOF
chown -R npdadmin:npdadmin "$workdir"
cd "$workdir"
sudo -u npdadmin condor_submit health.sub >/tmp/npd-health-submit.out
cluster="$(awk "/submitted to cluster/ { print \$NF }" /tmp/npd-health-submit.out | tr -d ".")"
for i in $(seq 1 60); do
  if grep -q "Normal termination (return value 0)" "health.${cluster}.log" 2>/dev/null; then
    break
  fi
  sleep 1
done
grep -q "Normal termination (return value 0)" "health.${cluster}.log"
test ! -s health."$cluster".0.err
' >/dev/null
}

check_cvmfs_probe() {
  cd "$ANSIBLE_DIR" || return 1
  ansible condor01.internal:asus_nodes -m shell -a 'cvmfs_config probe sft.cern.ch >/dev/null && cvmfs_config probe unpacked.cern.ch >/dev/null' >/dev/null
}

check_storage_pool() {
  zpool status npddata | grep -q 'state: ONLINE'
}

check_storage_export() {
  exportfs -v | grep -q '/data.*10.10.80.0/24'
}

check_storage_clients() {
  cd "$ANSIBLE_DIR" || return 1
  ansible condor01.internal:asus_nodes -m shell -a 'findmnt -rn /data | grep -q "10.10.80.2:/data"' >/dev/null
}

check_storage_write() {
  cd "$ANSIBLE_DIR" || return 1
  ansible condor01.internal -m shell -a '
set -euo pipefail
testfile=/data/scratch/npd-health-$(hostname)-$(date +%s)
echo ok > "$testfile"
grep -qx ok "$testfile"
rm -f "$testfile"
' >/dev/null
}

check_condor_storage_job() {
  "$ROOT_DIR/scripts/storage-smoke.sh" 1 >/dev/null
}

printf 'NPD cluster health check\n'
printf 'Date: %s\n\n' "$(date -Is)"

run_check 'Proxmox cluster is quorate' check_proxmox_quorum
run_check 'fw01 VM is running' check_cluster_vm fw01
run_check 'condor01 VM is running' check_cluster_vm condor01
run_check 'pxe01 LXC is running' check_cluster_vm pxe01
run_check 'squid01 LXC is running' check_cluster_vm squid01
run_check 'pxe01 nginx and tftpd-hpa are active' check_pxe_services
run_check 'PXE HTTP boot.ipxe is reachable' check_pxe_http
run_check 'squid01 squid service is active' check_squid_service
run_check 'squid01 proxies CVMFS HTTP traffic' check_squid_cvmfs_proxy
run_check 'condor01.internal resolves to 10.10.80.20' check_dns
run_check 'Ansible can reach condor01 and ASUS nodes' check_ansible_ping
run_check 'HTCondor service and queue are healthy on condor01' check_condor_services
run_check "HTCondor sees $EXPECTED_ASUS_SLOTS ASUS execute slots" check_condor_slots
run_check 'HTCondor smoke job completes' check_condor_smoke_job
run_check 'CVMFS probes sft.cern.ch and unpacked.cern.ch' check_cvmfs_probe
run_check 'JBOD ZFS pool npddata is online' check_storage_pool
run_check 'pve01 exports /data over NFS to VLAN80' check_storage_export
run_check 'Condor and ASUS nodes have /data mounted' check_storage_clients
run_check 'Shared /data/scratch is writable from condor01' check_storage_write
run_check 'HTCondor job writes to shared /data/results' check_condor_storage_job

printf '\nSummary: %s checks, %s failed\n' "$checks" "$failed"

if [ "$failed" -ne 0 ]; then
  exit 1
fi
