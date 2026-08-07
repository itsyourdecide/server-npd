#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANSIBLE_DIR="$ROOT_DIR/ansible"
JOBS="${1:-4}"

cd "$ANSIBLE_DIR"

ansible condor01.internal -m shell -a "
set -euo pipefail
jobs='$JOBS'
case \"\$jobs\" in
  ''|*[!0-9]*) echo 'job count must be a positive integer' >&2; exit 2 ;;
esac
if [ \"\$jobs\" -lt 1 ]; then
  echo 'job count must be a positive integer' >&2
  exit 2
fi

workdir=/home/npdadmin/condor-tests/storage-smoke
resultdir=/data/results/npd-storage-smoke
rm -rf \"\$workdir\"
mkdir -p \"\$workdir\" \"\$resultdir\"

cat > \"\$workdir/storage-smoke.sh\" <<'EOF'
#!/bin/bash
set -euo pipefail
cluster=\"\$1\"
process=\"\$2\"
resultdir=/data/results/npd-storage-smoke
outfile=\"\$resultdir/\${cluster}.\${process}.\${HOSTNAME}.txt\"
{
  echo \"host=\${HOSTNAME}\"
  echo \"cluster=\${cluster}\"
  echo \"process=\${process}\"
  date -Is
} > \"\$outfile\"
test -s \"\$outfile\"
EOF
chmod 755 \"\$workdir/storage-smoke.sh\"

cat > \"\$workdir/storage-smoke.sub\" <<'EOF'
executable = storage-smoke.sh
arguments = \$(Cluster) \$(Process)
output = storage-smoke.\$(Cluster).\$(Process).out
error = storage-smoke.\$(Cluster).\$(Process).err
log = storage-smoke.\$(Cluster).log
request_cpus = 1
request_memory = 256MB
queue JOB_COUNT
EOF
sed -i \"s/JOB_COUNT/\$jobs/\" \"\$workdir/storage-smoke.sub\"
chown -R npdadmin:npdadmin \"\$workdir\"

cd \"\$workdir\"
sudo -u npdadmin condor_submit storage-smoke.sub >/tmp/npd-storage-smoke-submit.out
cluster=\"\$(awk '/submitted to cluster/ { print \$NF }' /tmp/npd-storage-smoke-submit.out | tr -d '.')\"

for _ in \$(seq 1 90); do
  done_count=\"\$(grep -c 'Normal termination (return value 0)' \"storage-smoke.\${cluster}.log\" 2>/dev/null || true)\"
  [ \"\$done_count\" = \"\$jobs\" ] && break
  sleep 1
done

done_count=\"\$(grep -c 'Normal termination (return value 0)' \"storage-smoke.\${cluster}.log\" 2>/dev/null || true)\"
if [ \"\$done_count\" != \"\$jobs\" ]; then
  condor_q \"\$cluster\" || true
  sed -n '1,220p' \"storage-smoke.\${cluster}.log\" || true
  exit 1
fi

if find . -name 'storage-smoke.*.err' -type f -size +0c | grep -q .; then
  find . -name 'storage-smoke.*.err' -type f -size +0c -print -exec sed -n '1,120p' {} ';'
  exit 1
fi

result_count=\"\$(find \"\$resultdir\" -maxdepth 1 -type f -name \"\${cluster}.*.txt\" | wc -l)\"
if [ \"\$result_count\" != \"\$jobs\" ]; then
  echo \"expected \$jobs result files, found \$result_count\" >&2
  find \"\$resultdir\" -maxdepth 1 -type f -name \"\${cluster}.*.txt\" -print >&2
  exit 1
fi

echo \"storage smoke cluster=\$cluster jobs=\$jobs\"
find \"\$resultdir\" -maxdepth 1 -type f -name \"\${cluster}.*.txt\" -print -exec sed -n '1,4p' {} ';'
"
