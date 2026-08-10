#!/usr/bin/env bash
set -euo pipefail

PROMETHEUS_URL="${PROMETHEUS_URL:-http://10.10.10.30:9090}"
EXPECTED_TARGETS="${EXPECTED_TARGETS:-10}"

payload="$(curl -fsS "$PROMETHEUS_URL/api/v1/targets")"

total="$(jq '.data.activeTargets | length' <<<"$payload")"
down="$(jq '[.data.activeTargets[] | select(.health != "up")] | length' <<<"$payload")"

jq -r '.data.activeTargets[] | [.labels.job, .labels.instance, (.labels.role // "-"), .health] | @tsv' <<<"$payload" | sort

if [ "$total" -ne "$EXPECTED_TARGETS" ]; then
  echo "expected $EXPECTED_TARGETS targets, found $total" >&2
  exit 1
fi

if [ "$down" -ne 0 ]; then
  echo "$down targets are down" >&2
  exit 1
fi

echo "Monitoring targets healthy: $total/$EXPECTED_TARGETS up"
