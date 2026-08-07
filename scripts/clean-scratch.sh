#!/usr/bin/env bash
set -euo pipefail

SCRATCH_DIR="${SCRATCH_DIR:-/data/scratch}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
MODE="${1:-run}"

if [ ! -d "$SCRATCH_DIR" ]; then
  echo "scratch directory does not exist: $SCRATCH_DIR" >&2
  exit 1
fi

case "$RETENTION_DAYS" in
  ''|*[!0-9]*) echo "RETENTION_DAYS must be a positive integer" >&2; exit 2 ;;
esac

if [ "$RETENTION_DAYS" -lt 1 ]; then
  echo "RETENTION_DAYS must be at least 1" >&2
  exit 2
fi

if [ "$MODE" = "dry-run" ]; then
  find "$SCRATCH_DIR" -xdev -mindepth 1 -mtime "+$RETENTION_DAYS" -print
  exit 0
fi

if [ "$MODE" != "run" ]; then
  echo "usage: $0 [run|dry-run]" >&2
  exit 2
fi

find "$SCRATCH_DIR" -xdev -mindepth 1 -type f -mtime "+$RETENTION_DAYS" -delete
find "$SCRATCH_DIR" -xdev -mindepth 1 -type d -empty -mtime "+$RETENTION_DAYS" -delete
