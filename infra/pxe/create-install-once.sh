#!/bin/sh
set -eu

mac="${1:-}"
profile="${2:-alma9-basic-autoinstall.ipxe}"
dir=/srv/pxe/http/install-once
watcher=/usr/local/sbin/install-once-watcher.sh

case "$mac" in
  [0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F])
    ;;
  *)
    echo "Usage: $0 aa:bb:cc:dd:ee:ff [profile.ipxe]" >&2
    exit 2
    ;;
esac

case "$profile" in
  *../*|*/*|"")
    echo "Invalid profile name: $profile" >&2
    exit 2
    ;;
esac

mac=$(printf "%s" "$mac" | tr 'A-F' 'a-f')
mkdir -p "$dir/used"

cat > "$dir/$mac.ipxe" <<EOF
#!ipxe
echo Reinstall authorized once for $mac
chain http://10.10.80.10/profiles/$profile
EOF

chmod 644 "$dir/$mac.ipxe"
echo "Created $dir/$mac.ipxe"

if [ -x "$watcher" ]; then
  nohup "$watcher" 3600 >/tmp/install-once-watcher.log 2>&1 &
  echo "Started install-once watcher PID $!"
else
  echo "Watcher not executable at $watcher; remove the flag manually after first 200 GET." >&2
fi
