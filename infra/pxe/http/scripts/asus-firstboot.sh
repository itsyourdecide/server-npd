#!/bin/bash
set -euo pipefail

MAP_URL="http://10.10.80.10/asus-r1-map.csv"
MAP_FILE="/root/asus-r1-map.csv"

for i in $(seq 1 30); do
  if curl -fsS "$MAP_URL" -o "$MAP_FILE"; then
    break
  fi
  sleep 5
done

[ -s "$MAP_FILE" ] || exit 1

macs="$(ip -o link | awk '
  /link\/ether/ {
    for (i = 1; i <= NF; i++) {
      if ($i == "link/ether") {
        print tolower($(i + 1))
      }
    }
  }
')"
row=""
while IFS=, read -r hostname os_ip ipmi_ip lan_mac ipmi_mac switch_port_lan switch_port_ipmi; do
  [ "$hostname" = "hostname" ] && continue
  [[ "$hostname" =~ ^# ]] && continue
  [ -z "$hostname" ] && continue
  lan_mac="$(echo "$lan_mac" | tr 'A-F' 'a-f')"
  if echo "$macs" | grep -qx "$lan_mac"; then
    row="$hostname,$os_ip,$ipmi_ip,$lan_mac,$ipmi_mac,$switch_port_lan,$switch_port_ipmi"
    break
  fi
done < "$MAP_FILE"

[ -n "$row" ] || exit 0

IFS=, read -r hostname os_ip ipmi_ip lan_mac ipmi_mac switch_port_lan switch_port_ipmi <<< "$row"
lan_mac="$(echo "$lan_mac" | tr 'A-F' 'a-f')"
ifname="$(ip -o link | awk -v mac="$lan_mac" '
  /link\/ether/ {
    found=0
    for (i = 1; i <= NF; i++) {
      if ($i == "link/ether" && tolower($(i + 1)) == mac) {
        found=1
      }
    }
    if (found) {
      iface=$2
      sub(/:$/, "", iface)
      print iface
      exit
    }
  }
')"
[ -n "$ifname" ] || exit 1

hostnamectl set-hostname "$hostname.internal"

cat > /etc/NetworkManager/system-connections/npd-htcondor.nmconnection <<EOF
[connection]
id=npd-htcondor
type=ethernet
interface-name=${ifname}
autoconnect=true

[ipv4]
method=manual
address1=${os_ip}/24,10.10.80.1
dns=10.10.80.1;
dns-search=internal;

[ipv6]
method=disabled
EOF
chmod 600 /etc/NetworkManager/system-connections/npd-htcondor.nmconnection
nmcli connection reload || true
nmcli connection up npd-htcondor || true

if command -v ipmitool >/dev/null 2>&1; then
  modprobe ipmi_si 2>/dev/null || true
  modprobe ipmi_devintf 2>/dev/null || true
  ipmitool lan set 1 ipsrc static || true
  ipmitool lan set 1 ipaddr "$ipmi_ip" || true
  ipmitool lan set 1 netmask 255.255.255.0 || true
  ipmitool lan set 1 defgw ipaddr 10.10.30.1 || true
fi

touch /var/lib/npd-asus-firstboot.done
systemctl disable npd-asus-firstboot.service || true
