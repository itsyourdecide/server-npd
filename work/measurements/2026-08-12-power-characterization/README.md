# Power characterization — 2026-08-12

Goal: measure real wall power draw for each hardware class in the NPD cluster.
All watt values are external power-meter readings, not BMC voltage sensors.

## Measurement Rules

- Record `boot_peak_w` during power-on/startup.
- Record `idle_w` after the OS is fully booted and stable for about 5 minutes.
- Record both `stable_w` and `peak_w` during each workload.
- Keep tests short unless explicitly needed; this is a server-room power survey,
  not a burn-in test.
- Avoid destructive disk writes on production/system disks.
- JBOD/storage tests are separate because spinning disks change power heavily.

## Current Results

| Device | Hardware class | State / workload | Duration | Stable W | Peak W | Notes |
|---|---|---|---:|---:|---:|---|
| `pve01` | Supermicro 2U, 2x Xeon E5-2620 v4, 512GB RAM | Boot | startup | — | 180 | User power-meter reading |
| `pve01` | Supermicro 2U, 2x Xeon E5-2620 v4, 512GB RAM | Idle, Proxmox running, no intentional workload | ~5 min | 111 | 111 | User power-meter reading |
| `pve01` | Supermicro 2U, 2x Xeon E5-2620 v4, 512GB RAM | CPU-only stress, `stress-ng --cpu 0 --timeout 60s` | 60s | 226 | 226 | 32 CPU workers, no disk workload |
| `pve01` | Supermicro 2U, 2x Xeon E5-2620 v4, 512GB RAM | RAM stress, `stress-ng --vm 4 --vm-bytes 64G --vm-keep --timeout 60s` | ~61s | 203 | 213 | 64 GiB total, 16 GiB per worker |
| `pve01` | Supermicro 2U, 2x Xeon E5-2620 v4, 512GB RAM | Heavy RAM stress, `stress-ng --vm 8 --vm-bytes 256G --vm-keep --timeout 60s` | ~66s | 221 | 238 | 256 GiB total, 32 GiB per worker, no swap |
| `pve01` | Supermicro 2U, 2x Xeon E5-2620 v4, 512GB RAM | Local SSD read-only, parallel `dd if=/dev/sda` + `dd if=/dev/sdb` to `/dev/null` | 60s | 148-153 | 153 | Both local Micron SSDs, no writes, about 535-544 MB/s each |
| `pve01` | Supermicro 2U, 2x Xeon E5-2620 v4, 512GB RAM | Mixed load: 24 CPU workers + 128 GiB RAM + local SSD read-only | ~66s | 230 | 240 | Good planning point for heavy real-world node load |
| ASUS rail 1 (`asus-r1n1`-`asus-r1n4`) | 4x ASUS execute nodes | Boot, whole rail powered together | startup | — | 870 | Whole rail reading; about 217.5 W peak per node if divided by 4 |
| ASUS rail 1 (`asus-r1n1`-`asus-r1n4`) | 4x ASUS execute nodes | Idle, all 4 nodes booted | ~5 min | 320 | 320 | Whole rail reading; about 80 W idle per node |
| ASUS rail 1 (`asus-r1n1`-`asus-r1n4`) | 4x ASUS execute nodes | HTCondor CPU load, 4 jobs x 32 CPU fallback workers | ~50-60s | 1300 | — | Whole rail reading; about 325 W stable per node if divided by 4 |
| Force10 S60 | Network switch | Idle | stable | 120 | 120 | User power-meter reading |
| Force10 S60 | Network switch | Loaded / maximum observed | stable/max | 200 | 200 | User power-meter reading |
| HP 3500yl | Network switch | Idle | stable | 120 | 120 | User power-meter reading |
| HP 3500yl | Network switch | Loaded / maximum observed | stable/max | 200 | 200 | User power-meter reading |
| JBOD shelf | Disk shelf, one Promise 4U-SAS-24-12G BP | Startup | startup | — | 350 | Per-shelf user power-meter reading |
| JBOD shelf | Disk shelf, one Promise 4U-SAS-24-12G BP | Idle, disks spun up | stable | 230 | 230 | Per-shelf user power-meter reading |

## pve01 Test Context

```text
CPU: 2 sockets x 8 cores x 2 threads = 32 logical CPUs
Model: Intel Xeon E5-2620 v4 @ 2.10GHz
CPU stress command: stress-ng --cpu 0 --timeout 60s --metrics-brief
CPU stress result: passed 32 cpu workers, 60s
RAM stress command: stress-ng --vm 4 --vm-bytes 64G --vm-keep --timeout 60s --metrics-brief
RAM stress result: passed 4 vm workers, 64 GiB total, about 61s
Heavy RAM stress command: stress-ng --vm 8 --vm-bytes 256G --vm-keep --timeout 60s --metrics-brief
Heavy RAM stress result: passed 8 vm workers, 256 GiB total, about 66s, swap remained 0
Local SSD read command: parallel timeout 60s dd if=/dev/sda and /dev/sdb of=/dev/null bs=64M iflag=direct
Local SSD read result: about 535-544 MB/s per SSD, read-only
Mixed load command: stress-ng --cpu 24 --vm 4 --vm-bytes 128G --vm-keep --timeout 60s, plus parallel read-only dd from /dev/sda and /dev/sdb
Mixed load result: passed 24 cpu + 4 vm workers, no swap
Observed idle sensors after test:
  CPU1 Temp: 33 C
  CPU2 Temp: 32 C
  Peripheral Temp: 45 C
  MB_10G Temp: 60 C
  FAN1/FAN2/FANA: about 3500-3700 RPM
```

## Planned Measurement Matrix

| Hardware / scenario | Idle | Boot peak | CPU load | Memory load | Disk read | Network | Real workload |
|---|---:|---:|---:|---:|---:|---:|---:|
| Supermicro `pve01` | done | done | done | done | done | pending | done |
| Supermicro `pve02`/`pve03` representative | pending | pending | pending | pending | pending | pending | pending |
| ASUS rail 1, 4 execute nodes | done | done | done | pending | pending | pending | done |
| Force10 S60 | done | n/a | n/a | n/a | n/a | done | n/a |
| HP 3500yl | done | n/a | n/a | n/a | n/a | done | n/a |
| JBOD shelf, disks spun up | done | done | n/a | n/a | pending | n/a | pending |
| JBOD shelf, idle disks | done | done | n/a | n/a | n/a | n/a | n/a |

## Useful Conversions

For cooling estimates:

```text
1 W = 3.412 BTU/h
1000 W = 1 kW = 3412 BTU/h
```

For a 230 V circuit, approximate current:

```text
amps = watts / 230
```

## Fleet Power Planning Snapshot

Assumptions from current documentation:

- Supermicro fleet: 10 nodes.
- ASUS fleet: 48 nodes = 12 rails of 4 nodes.
- Network switches measured here: 2 switches.
- JBOD expected estate: documentation says roughly 8-12 shelves; current
  working planning range is 8-10 shelves.

Per-unit planning values from measurements:

```text
Supermicro heavy planning: 240 W/node
Supermicro idle:           111 W/node
ASUS rail heavy:          1300 W/rail
ASUS rail idle:            320 W/rail
Switch loaded/max:         200 W/switch
Switch idle:               120 W/switch
JBOD startup:              350 W/shelf
JBOD idle:                 230 W/shelf
```

Estimated fleet totals:

| Scenario | JBOD shelves | Total W | Approx A @ 230V | Cooling BTU/h |
|---|---:|---:|---:|---:|
| Idle, 10 Supermicro + 48 ASUS + 2 switches + JBOD | 8 | 7030 | 30.6 | 23986 |
| Idle, 10 Supermicro + 48 ASUS + 2 switches + JBOD | 10 | 7490 | 32.6 | 25556 |
| Idle, 10 Supermicro + 48 ASUS + 2 switches + JBOD | 12 | 7950 | 34.6 | 27125 |
| Heavy compute, JBOD idle | 8 | 20240 | 88.0 | 69059 |
| Heavy compute, JBOD idle | 10 | 20700 | 90.0 | 70628 |
| Heavy compute, JBOD idle | 12 | 21160 | 92.0 | 72198 |
| Heavy compute + 30% reserve, JBOD idle | 8 | 26312 | 114.4 | 89776 |
| Heavy compute + 30% reserve, JBOD idle | 10 | 26910 | 117.0 | 91817 |
| Heavy compute + 30% reserve, JBOD idle | 12 | 27508 | 119.6 | 93858 |

Interpretation:

- The ASUS fleet dominates total power draw.
- Full 48-node ASUS CPU load plus 10 Supermicro under heavy load is already
  about 20-21 kW before reserve.
- With normal engineering reserve, the full fleet points toward roughly
  26-28 kW electrical/cooling capacity, depending on actual JBOD count.
- Boot/staggering matters: do not power on all ASUS rails and all JBOD shelves
  at the same instant until PDU/circuit limits are confirmed.
