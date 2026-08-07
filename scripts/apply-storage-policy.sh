#!/usr/bin/env bash
set -euo pipefail

install -d -o root -g root -m 0755 /data

install -d -o 1000 -g 1000 -m 2775 /data/projects
install -d -o 1000 -g 1000 -m 2775 /data/projects/npd

install -d -o 1000 -g 1000 -m 3777 /data/results
install -d -o 1000 -g 1000 -m 3777 /data/results/npd
install -d -o 1000 -g 1000 -m 3777 /data/results/npd-storage-smoke

install -d -o root -g root -m 1777 /data/scratch
install -d -o root -g root -m 1777 /data/scratch/condor
install -d -o root -g root -m 1777 /data/scratch/users

zfs set compression=lz4 npddata/projects npddata/results npddata/scratch
zfs set atime=off npddata/projects npddata/results npddata/scratch
