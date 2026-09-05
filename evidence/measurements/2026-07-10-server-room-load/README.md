# 2026-07-10 server-room power and thermal measurements

## Scope

Measurements were taken after moving the current 3-node Proxmox cluster into the server room.

Nodes:
- `pve01` - Supermicro, Proxmox, JBOD disks visible
- `pve02` - Supermicro, Proxmox, runs `fw01` and `pxe01`
- `pve03` - Supermicro, Proxmox

Baseline inventory and idle IPMI data:
- `/root/server-npd/work/measurements/2026-07-10-server-room-baseline/`

Load-test raw logs:
- `/root/server-npd/work/measurements/2026-07-10-server-room-load/`

## Baseline summary

Each node has:
- 2 x Intel Xeon E5-2620 v4
- 8 cores per socket, Hyper-Threading enabled
- 32 logical CPUs total
- about 503 GiB RAM

Idle IPMI power before load tests:

| Node | Instantaneous | IPMI average | IPMI recorded max |
| --- | ---: | ---: | ---: |
| `pve01` | 132 W | 108 W | 186 W |
| `pve02` | 140 W | 127 W | 181 W |
| `pve03` | 122 W | 105 W | 171 W |
| Total | ~394 W | ~340 W | n/a |

Idle temperatures:

| Node | CPU1 | CPU2 | System | Peripheral | MB_10G |
| --- | ---: | ---: | ---: | ---: | ---: |
| `pve01` | 28 C | 28 C | 26 C | 43 C | 57 C |
| `pve02` | 29 C | 30 C | 24 C | 40 C | 56 C |
| `pve03` | 28 C | 28 C | 26 C | 39 C | 54 C |

## CPU load tests

Tool:

```bash
stress-ng --cpu 32 --cpu-method matrixprod --timeout 300s --metrics-brief
```

Sequential 5-minute tests, one node at a time:

| Node | Max instantaneous power | Max CPU1 | Max CPU2 | Max System | Max Peripheral | Max MB_10G | stress-ng status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `pve01` | 236 W | 43 C | 43 C | 29 C | 45 C | 61 C | passed |
| `pve02` | 228 W | 42 C | 42 C | 26 C | 41 C | 59 C | passed |
| `pve03` | 228 W | 42 C | 42 C | 28 C | 41 C | 59 C | passed |

Simultaneous 3-minute CPU test on all three nodes:

| Node | Max instantaneous power | Max CPU1 | Max CPU2 | Max System | Max Peripheral | Max MB_10G | stress-ng status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `pve01` | 236 W | 43 C | 42 C | 29 C | 44 C | 59 C | passed |
| `pve02` | 228 W | 42 C | 42 C | 26 C | 42 C | 59 C | passed |
| `pve03` | 228 W | 41 C | 41 C | 28 C | 40 C | 57 C | passed |
| Total estimated node peak | ~692 W | n/a | n/a | n/a | n/a | n/a | n/a |

The simultaneous test did not produce a higher per-node peak than the sequential tests. Temperatures stayed low for a CPU-only workload.

## Important hardware warning

All three Supermicro nodes report `PS2 Status` as failed/not OK in IPMI:

| Node | PS1 | PS2 |
| --- | --- | --- |
| `pve01` | `0x1` | `0xb` |
| `pve02` | `0x1` | `0xb` |
| `pve03` | `0x1` | `0xb` |

Interpretation: likely the second PSU is not connected to power, is switched off upstream, or is actually failed. This must be checked physically before relying on PSU redundancy.

Recommended physical check:
- Confirm both PSU modules are fully seated in every Supermicro.
- Confirm both power cords are connected.
- If using A/B power feeds or two PDUs, confirm both feeds are live.
- After fixing cabling, re-run:

```bash
ipmitool sensor list | egrep 'PS[12] Status'
ipmitool sel elist | tail -30
```

## Physical readings to record while near the rack

Fill these in manually if possible:

| Reading | Idle | During all-node CPU load | Notes |
| --- | ---: | ---: | --- |
| PDU/UPS total W |  |  | wall-side value, not IPMI |
| PDU/UPS total A |  |  | note voltage too |
| Circuit voltage |  |  | e.g. 230 V |
| Front rack inlet temp, bottom |  |  | thermometer |
| Front rack inlet temp, middle |  |  | thermometer |
| Front rack inlet temp, top |  |  | thermometer |
| Rear/hot-air temp |  |  | thermometer |
| Room ambient temp |  |  | away from rack |
| AC setpoint |  |  | if available |
| UPS model/rating |  |  | photo is enough |
| PDU model/rating |  |  | photo is enough |
| Breaker rating |  |  | photo is enough |

Useful photos to take:
- Full rack front and back.
- Power cabling for every server.
- PDU/UPS screens with W/A values.
- Breaker panel labels.
- Server labels and switch port labels.
- Airflow path: rack front, rack rear, AC position.

## Practical planning numbers

For the current 3 Supermicro nodes:
- Idle from IPMI: about `340-394 W`.
- CPU-only peak from IPMI: about `692 W` total.
- Add margin for PSU inefficiency, disks, fans, boot spikes, and measurement error.

Planning recommendation:
- Treat these 3 nodes as at least `800-1000 W` for electrical/cooling planning.
- If the JBOD disks on `pve01` are later stressed heavily, repeat with disk IO load because CPU-only tests do not fully represent disk shelf heat/power.
- Do not plan redundancy until `PS2 Status` is fixed and verified.

## Files captured after tests

Post-test cluster status:
- `post-pvecm-status.txt`
- `post-qm-list.txt`
- `post-pct-list.txt`

Raw stress logs:
- `pve01/stress-pve01-20260710-145909/`
- `pve02/stress-pve02-20260710-150514/`
- `pve03/stress-pve03-20260710-145308/`
- `all-nodes-3min/stress-pve01-allnodes-20260710-151159/`
- `all-nodes-3min/stress-pve02-allnodes-20260710-151159/`
- `all-nodes-3min/stress-pve03-allnodes-20260710-151159/`
