#!/bin/bash
set -euo pipefail

hostnamectl set-hostname condor01.internal

ifname="$(ip -o link | awk -F': ' '$2 != "lo" { print $2; exit }')"
[ -n "$ifname" ] || exit 1

cat > /etc/NetworkManager/system-connections/npd-htcondor.nmconnection <<EOF
[connection]
id=npd-htcondor
type=ethernet
interface-name=${ifname}
autoconnect=true

[ipv4]
method=manual
address1=10.10.80.20/24,10.10.80.1
dns=10.10.80.1;
dns-search=internal;

[ipv6]
method=disabled
EOF

chmod 600 /etc/NetworkManager/system-connections/npd-htcondor.nmconnection
nmcli connection reload || true
nmcli connection up npd-htcondor || true

touch /var/lib/npd-condor01-firstboot.done
systemctl disable npd-condor01-firstboot.service || true
