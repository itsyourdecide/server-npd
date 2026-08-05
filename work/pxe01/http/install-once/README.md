# install-once PXE flags

Files in this directory explicitly authorize destructive autoinstall for known nodes.

Example filename:

```text
20:cf:30:72:52:ae.ipxe
```

File content:

```ipxe
#!ipxe
echo Reinstall authorized once for 20:cf:30:72:52:ae
chain http://10.10.80.10/profiles/alma9-basic-autoinstall.ipxe
```

If the file is absent, known ASUS nodes boot from local disk instead of reinstalling.

Use `/usr/local/sbin/create-install-once.sh` on `pxe01` when possible:

```sh
/usr/local/sbin/create-install-once.sh 20:cf:30:72:52:ae
```

That helper starts `install-once-watcher.sh`, which watches only new nginx log
entries and moves a consumed flag into `install-once/used/` after the first
successful `GET /install-once/<mac>.ipxe` with HTTP 200.

Known ASUS nodes use this flow:

1. DHCP returns `ipxe.efi`, which is intentionally the legacy embedded
   `undionly.kpxe` payload for these old Intel Boot Agent systems.
2. Embedded iPXE chains `http://10.10.80.10/boot.ipxe`.
3. `boot.ipxe` checks for `/install-once/<mac>.ipxe`.
4. If the file exists, the node runs the destructive AlmaLinux autoinstall.
5. If the file is absent, iPXE exits to BIOS boot order.

Recommended ASUS BIOS order:

```text
1st: Network: IBA GE Slot 0200
2nd: AHCI/SATA disk
3rd: Network: IBA GE Slot 0300
```

If a node has already been installed and does not need remote reinstall, SATA
first is also acceptable. Avoid putting both network devices before the disk:
after iPXE exits, BIOS will try the second NIC and may show `PXE-E61`.

Package downloads use the local AlmaLinux cache on `pxe01`:

```text
http://10.10.80.10/alma-cache/almalinux/9/BaseOS/x86_64/os
http://10.10.80.10/alma-cache/almalinux/9/AppStream/x86_64/os
```

The cache proxies `repo.almalinux.org` and stores RPMs under
`/srv/pxe/cache/nginx/alma`. The first install that needs a package may still
download it from the internet; later installs use the local cached copy.
