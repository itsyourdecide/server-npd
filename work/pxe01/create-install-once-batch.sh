#!/bin/sh
set -eu

map_file="${MAP_FILE:-/srv/pxe/http/asus-r1-map.csv}"
profile="alma9-basic-autoinstall.ipxe"
dry_run=0
ttl=3600

usage() {
  cat >&2 <<'EOF'
Usage: create-install-once-batch.sh [--dry-run] [--profile profile.ipxe] [--ttl seconds] selector...

Selectors:
  all           every non-comment row in the ASUS CSV inventory
  r1            every node whose hostname starts with asus-r1n
  asus-r1       same as r1
  asus-r1n2     one exact hostname

Environment:
  MAP_FILE      CSV inventory path, default /srv/pxe/http/asus-r1-map.csv

The script creates /srv/pxe/http/install-once/<lan_mac>.ipxe for matching rows
and starts one install-once watcher.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --profile)
      [ "$#" -ge 2 ] || {
        usage
        exit 2
      }
      profile="$2"
      shift 2
      ;;
    --ttl)
      [ "$#" -ge 2 ] || {
        usage
        exit 2
      }
      ttl="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

[ "$#" -gt 0 ] || {
  usage
  exit 2
}

case "$profile" in
  *../*|*/*|"")
    echo "Invalid profile name: $profile" >&2
    exit 2
    ;;
esac

case "$ttl" in
  *[!0-9]*|"")
    echo "Invalid ttl: $ttl" >&2
    exit 2
    ;;
esac

[ -r "$map_file" ] || {
  echo "Cannot read map file: $map_file" >&2
  exit 1
}

dir=/srv/pxe/http/install-once
watcher=/usr/local/sbin/install-once-watcher.sh
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

matches_selector() {
  hostname="$1"
  selector="$2"

  case "$selector" in
    all)
      return 0
      ;;
    r[0-9]*)
      case "$hostname" in
        asus-"$selector"n*) return 0 ;;
      esac
      ;;
    asus-r[0-9]*)
      case "$selector" in
        *n[0-9]*)
          [ "$hostname" = "$selector" ] && return 0
          ;;
        *)
          case "$hostname" in
            "$selector"n*) return 0 ;;
          esac
          ;;
      esac
      ;;
    *)
      [ "$hostname" = "$selector" ] && return 0
      ;;
  esac

  return 1
}

while IFS=, read -r hostname os_ip ipmi_ip lan_mac ipmi_mac switch_port_lan switch_port_ipmi; do
  [ "$hostname" = "hostname" ] && continue
  case "$hostname" in ""|\#*) continue;; esac

  for selector in "$@"; do
    if matches_selector "$hostname" "$selector"; then
      lan_mac=$(printf "%s" "$lan_mac" | tr 'A-F' 'a-f')
      printf '%s,%s,%s,%s,%s\n' "$hostname" "$os_ip" "$lan_mac" "$switch_port_lan" "$switch_port_ipmi" >> "$tmp"
      break
    fi
  done
done < "$map_file"

if [ ! -s "$tmp" ]; then
  echo "No matching nodes found in $map_file" >&2
  exit 1
fi

sort -u "$tmp" | while IFS=, read -r hostname os_ip lan_mac switch_port_lan switch_port_ipmi; do
  echo "$hostname os=$os_ip lan_mac=$lan_mac ports=$switch_port_lan/$switch_port_ipmi profile=$profile"

  if [ "$dry_run" -eq 0 ]; then
    mkdir -p "$dir/used"
    cat > "$dir/$lan_mac.ipxe" <<EOF
#!ipxe
echo Reinstall authorized once for $lan_mac
chain http://10.10.80.10/profiles/$profile
EOF
    chmod 644 "$dir/$lan_mac.ipxe"
  fi
done

if [ "$dry_run" -eq 1 ]; then
  echo "Dry run only; no install-once files created."
  exit 0
fi

if [ -x "$watcher" ]; then
  nohup "$watcher" "$ttl" >/tmp/install-once-watcher.log 2>&1 &
  echo "Started install-once watcher PID $! for ${ttl}s"
else
  echo "Watcher not executable at $watcher; remove flags manually after first 200 GET." >&2
fi
