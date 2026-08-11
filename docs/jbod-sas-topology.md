# JBOD SAS Topology Plan

Status: draft, based on current inventory.

## Terms

- **JBOD shelf**: disk shelf. It contains disks, power supplies, fans, and SAS
  I/O modules, but it is not a server by itself.
- **SAS**: the disk cable fabric between a server and a JBOD shelf. Treat it as
  "PCIe/network for disks", not Ethernet.
- **HBA**: the SAS card inside a server. It lets Linux/ZFS see every disk
  directly. For ZFS this must behave as plain HBA/JBOD mode, not hardware RAID.
- **External HBA**: the SAS card with ports on the rear of the server for
  connecting external JBOD shelves.
- **IOM / I/O module**: the SAS module in the rear of a JBOD shelf. A shelf can
  have one or two IOMs.
- **Daisy chain**: one server HBA port goes to shelf 1, shelf 1 links onward to
  shelf 2, and so on.
- **Dual path**: two independent SAS paths to the same shelf/disks, usually via
  IOM A and IOM B. This can improve resilience, but Linux then needs multipath
  configured so the same disk is not treated as two different disks.
- **Enclosure**: the Linux view of a JBOD shelf. It lets us map physical disk
  slots to device names/serials.

## Known Hardware

From the existing inventory and logs:

- Expected estate: roughly 8-12 JBOD shelves.
- Confirmed shelf model: `Promise 4U-SAS-24-12G BP`.
- Confirmed shelf size: 24 disk slots.
- Confirmed shelf generation: 12G SAS backplane.
- Confirmed first shelf enclosure id: `0x50001555fe256000`.
- Confirmed disks in first shelf: 24 x `TOSHIBA MG04ACA600E`, about 5.5T each.
- Shelf has a rear `Mgmt` Ethernet port.
- Shelf has a serial console port, likely `115200 8N1`.
- `pve01` has:
  - external HBA: `LSI/Broadcom SAS9305-16e`, chip `SAS3216`, firmware `16.00.01.00`;
  - internal HBA: `LSI/Broadcom SAS9305-16i`, chip `SAS3224`, firmware `16.00.01.00`.
- `pve02` and `pve03` have the same HBA class (`SAS3224` + `SAS3216`) in the
  inventory notes.

Current caveat: after the latest physical changes `pve01` currently sees only
its system SSDs. The old `npddata` JBOD pool is not online at the time of this
draft. Before changing storage topology, confirm shelf power and SAS cabling.

## Design Rules

1. Do not connect one ZFS pool to multiple servers at the same time.
   One JBOD shelf or daisy chain belongs to one storage head unless a real
   clustered storage design is explicitly built.
2. Do not build one huge 10-12 shelf chain.
   It is harder to debug and too much capacity depends on one cable path.
3. Prefer short, labelled chains.
   A practical chain length is 2-3 shelves.
4. Start single-path, then add dual-path only after multipath is tested.
   Single-path is simpler and safer for the first expansion.
5. Keep SAS cabling local to the Supermicro/JBOD rack.
   Do not run SAS across the ASUS rack unless there is no alternative.
6. Label both ends of every cable before scaling.

## Recommended First Production Layout

Use `pve01` as the first storage head because the current `/data` design already
expects:

```text
pve01
  ZFS pool: npddata
  NFS export: 10.10.80.2:/data
```

First reconnect only one shelf:

```text
pve01 external HBA port 1 -> jbod01 IOM A input
```

Then verify:

```bash
lsblk -S -o NAME,HCTL,TRAN,VENDOR,MODEL,REV,SERIAL,SIZE
dmesg -T | grep -Ei 'sas|scsi|enclos|error|reset'
zpool import
zpool status
```

Only after the first shelf is stable, add shelves in short chains:

```text
pve01 HBA external port 1 -> jbod01 -> jbod02 -> jbod03
pve01 HBA external port 2 -> jbod04 -> jbod05 -> jbod06
```

If the HBA has four external ports/cables available, use four smaller chains:

```text
pve01 HBA external port 1 -> jbod01 -> jbod02 -> jbod03
pve01 HBA external port 2 -> jbod04 -> jbod05 -> jbod06
pve01 HBA external port 3 -> jbod07 -> jbod08 -> jbod09
pve01 HBA external port 4 -> jbod10 -> jbod11 -> jbod12
```

This is easier to service than one long chain.

## Later Dual-Path Layout

Only after `multipath-tools`, `lsscsi`, and `sg3_utils` are installed and tested:

```text
pve01 HBA port A1 -> jbod01 IOM A -> jbod02 IOM A -> jbod03 IOM A
pve01 HBA port B1 -> jbod01 IOM B -> jbod02 IOM B -> jbod03 IOM B
```

The goal of dual-path is not "more disks"; it is a second route to the same
disks if one cable/IOM path fails. Without multipath, dual-path can be dangerous
because Linux may show the same physical disk twice.

## Cable Labels

Use labels like this:

```text
pve01-hba-e1 -> jbod01-iomA-in
jbod01-iomA-out -> jbod02-iomA-in
pve01-hba-e2 -> jbod04-iomA-in
```

For future dual-path:

```text
pve01-hba-e1 -> jbod01-iomA-in
pve01-hba-e2 -> jbod01-iomB-in
```

Also label shelf management:

```text
jbod01-mgmt
jbod01-serial
```

## Need To Confirm Physically

Before connecting all shelves:

- exact count of shelves: 10 or 12;
- exact rear IOM layout for each shelf;
- number and type of external SAS ports/cables;
- which ports are input/output on the Promise IOM;
- whether all shelves have two IOMs or only one;
- whether all shelves are the same `Promise 4U-SAS-24-12G BP` model;
- whether all shelf management ports can be cabled to a management switch;
- enclosure/slot mapping with `lsscsi` and `sg_ses`.

## My Current Recommendation

Do not scale JBOD cabling yet. First restore and document the single-shelf
connection that used to provide `npddata`, then expand in short chains.

The preferred growth path is:

```text
phase 1: pve01 -> jbod01
phase 2: pve01 -> two chains, 2-3 shelves each
phase 3: decide whether pve02/pve03 get independent shelves
phase 4: only then consider dual-path/multipath
```

For now, the safest operational model remains:

```text
one storage head owns one ZFS pool
ZFS exports /data by NFS
HTCondor nodes consume /data over network
```
