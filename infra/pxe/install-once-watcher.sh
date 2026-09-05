#!/bin/sh
set -eu

usage() {
  echo "Usage: $0 [ttl_seconds]" >&2
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

ttl="${1:-3600}"
case "$ttl" in
  *[!0-9]*|"")
    usage
    exit 2
    ;;
esac

end=$(( $(date +%s) + ttl ))
log=/var/log/nginx/access.log
used_dir=/srv/pxe/http/install-once/used
mkdir -p "$used_dir"

# Only watch log entries appended after this process starts. This avoids
# consuming a freshly-created flag because of an older matching 200 response.
offset=0
[ -f "$log" ] && offset=$(wc -c < "$log")

while [ "$(date +%s)" -lt "$end" ]; do
  [ -f "$log" ] || {
    sleep 1
    continue
  }

  size=$(wc -c < "$log")
  if [ "$size" -lt "$offset" ]; then
    offset=0
  fi

  dd if="$log" bs=1 skip="$offset" 2>/dev/null | grep "GET /install-once/" | grep " 200 " | while read -r line; do
    file=$(printf "%s\n" "$line" | sed -n 's#.*GET /install-once/\([^ ?]*\.ipxe\).*#\1#p')
    [ -n "$file" ] || continue
    case "$file" in *../*|*/*|"") continue;; esac

    if [ -f "/srv/pxe/http/install-once/$file" ]; then
      mv "/srv/pxe/http/install-once/$file" "$used_dir/$(date +%Y%m%d-%H%M%S)-$file"
      echo "$(date -Is) consumed $file" >> /var/log/install-once-watcher.log
    fi
  done

  offset="$size"
  sleep 1
done
