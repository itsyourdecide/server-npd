#!/usr/bin/env bash
set -uo pipefail

PVE02="${PVE02:-pve02}"
BASTION_CTID="${BASTION_CTID:-102}"
CONDOR_HOST="${CONDOR_HOST:-npdadmin@10.10.80.20}"
FUNNEL_HOST="${FUNNEL_HOST:-pve02.taile43d6d.ts.net}"
FUNNEL_SSH_PORT="${FUNNEL_SSH_PORT:-10000}"
USER_TO_CHECK="${1:-}"

checks=0
failed=0

usage() {
  cat <<EOF
Usage: $0 [username]

Checks the phase-1 user access layer:
  - Tailscale Funnel SSH endpoint
  - bastion01 SSH/fail2ban/node-exporter services
  - bastion01 SSH hardening
  - condor01 SSH/HTCondor availability
  - optional username existence and authorized_keys on bastion01/condor01
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

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
  if "$@" >/tmp/npd-user-access.out 2>/tmp/npd-user-access.err; then
    ok "$label"
  else
    fail "$label"
    sed 's/^/     /' /tmp/npd-user-access.err
    sed 's/^/     /' /tmp/npd-user-access.out
  fi
}

check_funnel_ssh() {
  nc -vz -w 5 "$FUNNEL_HOST" "$FUNNEL_SSH_PORT"
}

check_bastion_services() {
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$PVE02" \
    "pct exec $BASTION_CTID -- systemctl is-active --quiet ssh &&
     pct exec $BASTION_CTID -- systemctl is-active --quiet fail2ban &&
     pct exec $BASTION_CTID -- systemctl is-active --quiet prometheus-node-exporter"
}

check_bastion_hardening() {
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$PVE02" \
    "pct exec $BASTION_CTID -- sh -lc '
      sshd -T | grep -qx \"permitrootlogin no\" &&
      sshd -T | grep -qx \"passwordauthentication no\" &&
      sshd -T | grep -qx \"kbdinteractiveauthentication no\" &&
      sshd -T | grep -qx \"pubkeyauthentication yes\" &&
      sshd -T | grep -qx \"allowtcpforwarding yes\" &&
      sshd -T | grep -qx \"allowagentforwarding no\"
    '"
}

check_condor_submit() {
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$CONDOR_HOST" \
    "systemctl is-active --quiet condor && condor_q >/dev/null"
}

check_user_bastion() {
  local user="$1"
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$PVE02" \
    "pct exec $BASTION_CTID -- sh -lc '
      id \"$user\" >/dev/null &&
      test -s \"\$(getent passwd \"$user\" | cut -d: -f6)/.ssh/authorized_keys\"
    '"
}

check_user_condor() {
  local user="$1"
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$CONDOR_HOST" \
    "id \"$user\" >/dev/null &&
     sudo -n test -s \"\$(getent passwd \"$user\" | cut -d: -f6)/.ssh/authorized_keys\""
}

echo "NPD user access health check"
date --iso-8601=seconds
echo

run_check "Tailscale Funnel SSH endpoint is open" check_funnel_ssh
run_check "bastion01 ssh, fail2ban and node exporter are active" check_bastion_services
run_check "bastion01 SSH hardening is enforced" check_bastion_hardening
run_check "condor01 SSH and HTCondor submit are available" check_condor_submit

if [ -n "$USER_TO_CHECK" ]; then
  run_check "user $USER_TO_CHECK exists on bastion01 with authorized_keys" check_user_bastion "$USER_TO_CHECK"
  run_check "user $USER_TO_CHECK exists on condor01 with authorized_keys" check_user_condor "$USER_TO_CHECK"
fi

echo
printf 'Summary: %s checks, %s failed\n' "$checks" "$failed"

if [ "$failed" -ne 0 ]; then
  exit 1
fi
