# AlmaLinux template для NPD Portal

Статус: current
Последняя проверка: 2026-09-21
Last tested: Proxmox VE 9.2.3, AlmaLinux 9.8 Generic Cloud
Назначение: воспроизводимо пересоздать исходный VM template Portal и проверить первый clone
Источник истины для: VMID 9000, параметров образа, Cloud-Init и smoke test

## Проверенное состояние

- node: `pve02`;
- VMID: `9000`;
- name: `npd-almalinux-9-template`;
- storage: `local-zfs`;
- image: `AlmaLinux-9-GenericCloud-9.8-20260810.x86_64.qcow2`;
- SHA-256:
  `6bdab6376d46d42e4203ace3733efafc7c5d37c7cb443a6cc74750097002d74b`;
- image cache: `/var/lib/vz/template/cache/npd-portal/`;
- Portal network: bridge `vmbr0`, VLAN 40;
- DNS: `10.10.40.1`, search domain `internal`.

Не пересоздавать template, если VMID `9000` уже принадлежит другому объекту,
`local-zfs` не active или bridge/VLAN mapping изменился.

## Проверка образа

В каталоге image cache должны находиться QCOW2, `CHECKSUM`, `CHECKSUM.asc` и
официальный публичный AlmaLinux key. Проверить сначала подпись checksum-файла,
затем сам файл:

```bash
gpg --import RPM-GPG-KEY-AlmaLinux-9
gpg --verify CHECKSUM.asc CHECKSUM
sha256sum AlmaLinux-9-GenericCloud-9.8-20260810.x86_64.qcow2
```

Ожидаемый fingerprint signing key:
`BF18 AC28 7617 8908 D6E7 1267 D36C B86C B86B 3716`.

## Создание template

Команды выполняются на `pve02` после проверки, что VMID свободен:

```bash
qm create 9000 \
  --name npd-almalinux-9-template \
  --machine q35 \
  --bios seabios \
  --ostype l26 \
  --cpu x86-64-v2-AES \
  --cores 2 \
  --memory 2048 \
  --balloon 0 \
  --scsihw virtio-scsi-single \
  --agent enabled=1,fstrim_cloned_disks=1 \
  --serial0 socket \
  --vga serial0 \
  --net0 virtio,bridge=vmbr0,firewall=1,tag=40

qm importdisk 9000 \
  /var/lib/vz/template/cache/npd-portal/AlmaLinux-9-GenericCloud-9.8-20260810.x86_64.qcow2 \
  local-zfs

qm set 9000 --scsi0 local-zfs:vm-9000-disk-0,discard=on,iothread=1,ssd=1
qm set 9000 --ide2 local-zfs:cloudinit
qm set 9000 --boot order=scsi0
qm set 9000 --ciuser almalinux --ipconfig0 ip=dhcp
qm set 9000 --nameserver 10.10.40.1 --searchdomain internal
qm set 9000 --tags 'template;almalinux'
qm template 9000
qm set 9000 --protection 1
```

Если имя импортированного volume отличается, взять его из вывода
`qm importdisk`, а не угадывать.

## ACL

Назначить `PVETemplateUser` на `/vms/9000` и `PVESDNUser` на
`/sdn/zones/localnetwork/vmbr0/40` как описано в
[service account runbook](portal-proxmox-service-account.md).

## Smoke test

Проверенный порядок через API token:

1. Получить свободный VMID через `GET /cluster/nextid`.
2. Сделать full clone `POST /nodes/pve02/qemu/9000/clone` в pool
   `npd-portal` и опросить clone UPID.
3. До первого старта задать CPU, RAM, Cloud-Init user, DHCP, DNS,
   search domain и URL-encoded SSH public key.
4. Снять у клона наследованные `protection`/template tags и задать metadata
   Portal.
5. Увеличить `scsi0` через resize API и опросить возвращённый UPID.
6. Запустить VM, опросить start UPID, затем дождаться guest agent.
7. Проверить SSH, `/etc/resolv.conf`, root filesystem и
   `cloud-init status --wait --long`.
8. Выполнить shutdown с polling.
9. Удалить clone с `purge=1`, проверить пустой pool и отсутствие его volumes.

Не использовать `destroy-unreferenced-disks=1`: проверка 2026-09-21 дала
`no such logical volume pve/data`. Не считать VM готовой сразу после
успешного `qmstart`: Cloud-Init с `ciupgrade=1` занимал около пяти минут.

## Rollback

Template защищён. Для намеренного удаления сначала остановить worker, удалить
его template ACL, затем явно снять protection:

```bash
qm set 9000 --protection 0
qm destroy 9000 --purge 1
```

Перед удалением отдельно убедиться, что `9000` — именно
`npd-almalinux-9-template`; операция удаляет template и его диски.

## Связанные документы

- [Proxmox cluster](../services/proxmox.md).
- [Service account Proxmox для Portal](portal-proxmox-service-account.md).
- [Текущее состояние](../current-state.md).
