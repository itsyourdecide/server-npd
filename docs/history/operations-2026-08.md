# Журнал операций — август 2026

- Статус: historical
- Последняя проверка структуры: 2026-09-05
- Назначение: неизменяемая хронология выполненных работ за 2026-08
- Источник истины для: факта выполнения операции на указанную дату

> Записи перенесены из исходного журнала без актуализации фактов. Открытые
> пункты из истории не являются текущим backlog; используйте
> [open issues](../project/open-issues.md).

### 2026-08-05 — pxe01 — добавлен локальный AlmaLinux repo cache для ускорения массового PXE

После возврата к работе проверено состояние первой ASUS-рельсы:

```text
asus-r1n2 -> 10.10.80.102 SSH OK, firstboot_done
asus-r1n3 -> 10.10.80.103 SSH OK, firstboot_done
asus-r1n4 -> 10.10.80.104 SSH OK, firstboot_done
asus-r1n1 -> переустановка запущена заново после исправления LAN/PXE
```

На `r1n1` подтвержден свежий PXE install:

```text
10.10.80.117 GET /install-once/20:cf:30:72:52:ae.ipxe -> 200
10.10.80.117 GET /profiles/alma9-basic-autoinstall.ipxe -> 200
10.10.80.117 GET /alma/9/BaseOS/x86_64/os/images/pxeboot/vmlinuz -> 200
10.10.80.117 GET /alma/9/BaseOS/x86_64/os/images/pxeboot/initrd.img -> 200
10.10.80.117 GET /alma/9/BaseOS/x86_64/os/images/install.img -> 200
10.10.80.117 GET /kickstart/alma9-basic.ks -> 200
```

Проблема скорости: `install.img`/kernel/initrd уже локальные, но RPM-пакеты в kickstart тянулись с `repo.almalinux.org`, из-за чего каждая новая нода могла ждать внешний интернет.

Сделано:

- rootfs `pxe01` увеличен с 16G до 60G;
- добавлен nginx proxy cache `/alma-cache/` с backend `repo.almalinux.org`;
- cache storage: `/srv/pxe/cache/nginx/alma`, лимит `40g`;
- `alma9-basic.ks`, `alma9-pxe-test.ks` и iPXE profiles переключены на:

```text
http://10.10.80.10/alma-cache/almalinux/9/BaseOS/x86_64/os
http://10.10.80.10/alma-cache/almalinux/9/AppStream/x86_64/os
```

Это не полный mirror: первый запрос конкретного RPM может скачать его через интернет, но все следующие ноды получают этот RPM локально с `pxe01`.

### 2026-08-05 — ASUS rail 1 — OS install checkpoint 4/4

После исправления физического LAN/PXE для `asus-r1n1` выполнена повторная install-once установка. Firstboot отработал:

```text
asus-r1n1.internal -> 10.10.80.101 SSH OK, firstboot_done, IPMI 10.10.30.101 ping OK
asus-r1n2.internal -> 10.10.80.102 SSH OK, firstboot_done, IPMI 10.10.30.102 ping OK
asus-r1n3.internal -> 10.10.80.103 SSH OK, firstboot_done, IPMI 10.10.30.103 ping pending
asus-r1n4.internal -> 10.10.80.104 SSH OK, firstboot_done, IPMI 10.10.30.104 ping pending
```

Итог: первая ASUS-рельса готова как base AlmaLinux fleet для Ansible и будущего HTCondor execute role. IPMI на `r1n3/r1n4` не блокирует следующий этап и отложен.

Добавлен batch-helper на `pxe01`:

```sh
/usr/local/sbin/create-install-once-batch.sh --dry-run r1
/usr/local/sbin/create-install-once-batch.sh r1
```

Он читает CSV inventory, создает install-once files для выбранной рельсы/hostname и запускает watcher один раз. Следующий практический PXE шаг: добавить inventory для `asus-r2n1` ... `asus-r2n4`, добавить их MAC в `boot.ipxe`, затем прогнать batch install на одной новой рельсе.

### 2026-08-06 — pve02/pxe01 — создан PXE-профиль и VM `condor01`

Создан отдельный AlmaLinux 9 PXE/Kickstart профиль для управляющей HTCondor VM `condor01`, чтобы не использовать ASUS firstboot/IPMI-логику на серверной VM.
- VM: `condor01`, VMID `130`, host `pve02`.
- Network: `vmbr0`, VLAN80, MAC `bc:24:11:cd:01:30`.
- Target IP после firstboot: `10.10.80.20/24`, gw/DNS `10.10.80.1`, hostname `condor01.internal`.
- Resources: 4 vCPU, 8G RAM, `local-zfs` disk 64G.
- PXE files:
  - `/srv/pxe/http/profiles/alma9-condor01-autoinstall.ipxe`
  - `/srv/pxe/http/kickstart/alma9-condor01.ks`
  - `/srv/pxe/http/scripts/condor01-firstboot.sh`
  - `/srv/pxe/http/scripts/npd-condor01-firstboot.service`
- `boot.ipxe` knows MAC `bc:24:11:cd:01:30` and checks install-once before local disk.
- install-once flag was consumed manually after the first HTTP 200 to avoid reinstall loops.
- `pxe01` nginx was found failed after reboot because startup-time DNS could not resolve `repo.almalinux.org`; repo config updated to use runtime resolver for `/alma-cache/`.

Итог: `condor01` PXE install completed; host отвечает на `10.10.80.20`, hostname `condor01.internal`, firstboot marker `/var/lib/npd-condor01-firstboot.done` есть. Boot order переключен на `scsi0;net0`, install-once файл перенесен в `used/`, чтобы не было reinstall loop. Ansible `base` применен к `condor01.internal`: `ok=3`, `changed=0`, `failed=0`. Nginx runtime-resolver fix применен live на `pxe01`, `nginx -t` OK, `/alma-cache/.../repomd.xml` отвечает `200`.

Открыто: добавить HTCondor Ansible roles и проверить первый `condor_status`/test job.

### 2026-08-06 — condor01/asus-r1 — первый рабочий HTCondor pool

Через Ansible добавлены роли:
- `htcondor_common`
- `htcondor_manager`
- `htcondor_submit`
- `htcondor_execute`

`condor01.internal` настроен как central manager + submit/access point. После DNS override в OPNsense `condor01.internal` резолвится в `10.10.80.20`, поэтому `CONDOR_HOST` возвращен к имени. `NETWORK_INTERFACE` оставлен явным IP, потому что HTCondor ожидает интерфейс/IP, а не hostname.

ASUS первая рельса настроена как execute-ноды:
- `asus-r1n1.internal` / `10.10.80.101`
- `asus-r1n2.internal` / `10.10.80.102`
- `asus-r1n3.internal` / `10.10.80.103`
- `asus-r1n4.internal` / `10.10.80.104`

Проверки:
- `condor_status` на `condor01` видит 4 `Unclaimed Idle` слота.
- `condor_status -schedd` видит `condor01.internal`.
- `condor_q` работает и не падает на старый DHCP IP.
- Повторный Ansible прогон manager/execute: `changed=0`, `failed=0`.
- Smoke test: 4 jobs в cluster `1`, все завершились; log подтвердил запуск по одной job на каждой ASUS-ноде.

Итог: минимальный HTCondor pool `condor01 + 4 ASUS` работает.

Открыто: CVMFS/storage/monitoring.

### 2026-08-07 — fw01/HTCondor — DNS override для `condor01`

В OPNsense добавлен host override `condor01.internal -> 10.10.80.20`. Проверено:
- `dig @10.10.10.1 condor01.internal A` → `10.10.80.20`.
- `dig @10.10.80.1 condor01.internal A` → `10.10.80.20`.
- ASUS-ноды резолвят `condor01.internal` в `10.10.80.20`.

После перевода HTCondor с временного IP на имя обнаружено, что `NETWORK_INTERFACE = condor01.internal` невалиден: HTCondor не может определить IP по hostname для этой настройки. Исправлено:
- `CONDOR_HOST = condor01.internal`.
- `NETWORK_INTERFACE = 10.10.80.20` на `condor01`.
- `NETWORK_INTERFACE = ansible_host` на ASUS execute-нодах.
- Execute override перенесен в `99-npd-execute`, старый `00-npd-execute` удаляется Ansible.

Итог: `condor_status` снова видит 4 ASUS slots, `condor_status -schedd` видит `condor01`, повторный Ansible прогон manager/execute: `changed=0`, `failed=0`.

### 2026-08-07 — pve01 — добавлен cluster health-check

Добавлен `scripts/cluster-health.sh` — единая быстрая проверка текущего минимального стека. Скрипт запускается с `pve01` из корня репозитория:

```bash
./scripts/cluster-health.sh
```

Проверяет:
- Proxmox cluster quorum.
- `fw01`, `condor01`, `pxe01` running.
- `pxe01` nginx + `tftpd-hpa`.
- HTTP PXE endpoint `/boot.ipxe`.
- DNS `condor01.internal -> 10.10.80.20`.
- Ansible reachability до `condor01` и ASUS.
- HTCondor service/queue на `condor01`.
- `condor_status` видит 4 ASUS execute slots.
- HTCondor smoke job завершается с `Normal termination (return value 0)`.

Итог: первый прогон после фиксов: `11 checks, 0 failed`.

### 2026-08-07 — condor01/asus-r1 — CVMFS client

Добавлена Ansible role `cvmfs_client` и playbook `ansible/playbooks/cvmfs_client.yml`.

Настройки:
- Repositories: `sft.cern.ch`, `unpacked.cern.ch`.
- Proxy: `DIRECT`.
- Cache base: `/var/lib/cvmfs`.
- Quota: `8000` MB.

Применено на:
- `condor01.internal`
- `asus-r1n1.internal`
- `asus-r1n2.internal`
- `asus-r1n3.internal`
- `asus-r1n4.internal`

Проверки:
- `cvmfs_config probe sft.cern.ch` OK на всех 5 узлах.
- `cvmfs_config probe unpacked.cern.ch` OK на всех 5 узлах.
- Повторный Ansible прогон: `changed=0`, `failed=0`.
- HTCondor smoke test cluster `7`: 4 jobs ушли на все ASUS-ноды и на каждой успешно прочитали `/cvmfs/sft.cern.ch` и `/cvmfs/unpacked.cern.ch`, return value `0`.

Итог: CVMFS слой готов для первого HEP/software smoke test.

### 2026-08-07 — pve02/squid01 — Squid proxy/cache для CVMFS

Создан отдельный LXC `squid01` для локального HTTP proxy/cache CVMFS.

Параметры:
- Host: `pve02`.
- CTID: `111`.
- IP: `10.10.80.11/24`, gateway `10.10.80.1`.
- VLAN: `80`.
- OS: Debian 12 LXC.
- Resources: 1 vCPU, 1G RAM, 64G rootfs.
- Service: Squid, port `3128`.
- ACL: разрешен `10.10.80.0/24`; management/VLAN10 не имеет доступа к proxy.
- Cache: `/var/spool/squid`, `40960` MB, `maximum_object_size 1024 MB`.
- Config snapshot: `work/squid01/squid.conf`.

Исправление: CVMFS использует HTTP endpoints не только на 80, но и на `8000`, поэтому `Safe_ports` включает `80`, `443`, `8000`.

CVMFS clients переключены на:

```text
CVMFS_HTTP_PROXY="http://10.10.80.11:3128|DIRECT"
```

Проверки:
- `squid` active.
- `curl -x http://10.10.80.11:3128 .../.cvmfspublished` с `condor01` → `200 OK`.
- CVMFS probes на `condor01` и ASUS проходят.
- `scripts/cluster-health.sh`: `15 checks, 0 failed`.

Итог: CVMFS теперь ходит через локальный Squid proxy с direct fallback.

### 2026-08-07 — pve01/JBOD — preflight перед созданием `/data`

Пользователь подтвердил, что данные на JBOD можно полностью стереть, и разрешил создание storage layer. Перед destructive действиями выполнен preflight на `pve01`.

Проверки:
- `lsblk` показывает только два системных Micron SSD:
  - `sda` `Micron_5200_MTFDDAK960TDD` `18031DBC5C7D` — Proxmox/LVM.
  - `sdb` `Micron_5200_MTFDDAK960TDD` `18031DBC5C7C` — `rpool`.
- Ожидаемые 24 JBOD-диска `TOSHIBA MG04ACA600E` сейчас не видны.
- `lspci` видит оба LSI/Broadcom SAS HBA:
  - `SAS3216`
  - `SAS3224`
- `mpt3sas` загружен, SCSI rescan выполнен, но новых дисков/expander/enclosure не появилось.
- `zpool status` показывает только `rpool`; `zpool import` показывает старый/importable `zroot` на `zd0`, не JBOD.

Итог: destructive storage step остановлен. Нельзя создавать ZFS pool, пока `pve01` не видит 24 JBOD-диска.

Открыто: физически проверить питание JBOD, SAS cable, правильный внешний HBA/порт, индикацию link/activity на полке и HBA.

### 2026-08-07 — pve01/JBOD — создан общий ZFS/NFS storage `/data`

После включения JBOD `pve01` увидел 24 диска `TOSHIBA MG04ACA600E` по 5.5T
(`sdc`-`sdz`). Перед созданием пула:
- `blkid /dev/sd[c-z]` не показал существующих файловых сигнатур.
- SMART health у всех 24 JBOD-дисков: `PASSED`.
- Системные Micron SSD `sda`/`sdb` не использовались.

Создан ZFS pool:
- Name: `npddata`.
- Layout: `2 x raidz2`, по 12 дисков в каждом vdev.
- Properties: `ashift=12`, `compression=lz4`, `atime=off`,
  `xattr=sa`, `acltype=posixacl`, `mountpoint=/data`.
- Доступно после создания: примерно `99.6T`.

Созданы datasets:
- `/data/projects` — persistent project data, `2775`, owner/group `1000:1000`.
- `/data/results` — persistent job outputs, sticky writable для HTCondor jobs.
- `/data/scratch` — temporary shared job data, sticky writable.

Сеть:
- На `pve01` добавлен `vmbr2.80` с адресом `10.10.80.2/24`.
- Старый маршрут `10.10.80.0/24 via 10.10.10.1` с `vmbr2.10` удален из
  `/etc/network/interfaces`, потому что VLAN80 теперь directly connected.
- Бэкап перед правкой: `/etc/network/interfaces.bak.20260807-190342`.

NFS:
- Установлен и включен `nfs-kernel-server`.
- Export: `/data 10.10.80.0/24(rw,sync,no_subtree_check,root_squash,crossmnt)`.
- `crossmnt` нужен, потому что `/data/projects`, `/data/results` и
  `/data/scratch` являются отдельными ZFS datasets под родителем `/data`.

Ansible:
- Добавлен playbook `ansible/playbooks/storage_client.yml`.
- Добавлена role `ansible/roles/storage_client`.
- Применено к `condor01.internal` и `asus-r1n1.internal`-`asus-r1n4.internal`.

Проверки:
- Все клиенты монтируют `10.10.80.2:/data` как `nfs4`.
- Все клиенты пишут в `/data/scratch`.
- HTCondor smoke job ушел на `asus-r1n3.internal` и успешно записал результат
  в `/data/results` на JBOD.

Итог: первый общий storage layer для HTCondor работает end-to-end.

### 2026-08-07 — condor01/asus-r1/JBOD — добавлен storage smoke test

Добавлен `scripts/storage-smoke.sh` — быстрый end-to-end тест общего storage:
- submit идет через `condor01.internal`;
- jobs выполняются на HTCondor execute-нодах;
- каждая job пишет результат в `/data/results/npd-storage-smoke` на JBOD.

Проверки:
- `./scripts/storage-smoke.sh 1` — OK, результат записан с
  `asus-r1n3.internal`.
- `./scripts/storage-smoke.sh 4` — OK, результаты записаны с
  `asus-r1n1.internal`, `asus-r1n2.internal`, `asus-r1n3.internal`,
  `asus-r1n4.internal`.
- `./scripts/cluster-health.sh` теперь включает этот тест и показывает
  `20 checks, 0 failed`.

Итог: общий storage проверяется не только mount/write-командой, но и настоящей
HTCondor job.

### 2026-08-07 — pve01/JBOD — закреплена политика `/data`

Закреплена структура общего storage:
- `/data/projects/npd` — persistent datasets/configs/project inputs.
- `/data/results/npd` — persistent job outputs.
- `/data/scratch/condor` — temporary HTCondor job data.
- `/data/scratch/users` — temporary manual/user work.

Права:
- `/data/projects` и `/data/projects/npd`: `2775`, owner/group `1000:1000`.
- `/data/results`, `/data/results/npd`,
  `/data/results/npd-storage-smoke`: sticky-writable.
- `/data/scratch`, `/data/scratch/condor`, `/data/scratch/users`:
  sticky-writable.

Добавлены скрипты:
- `scripts/apply-storage-policy.sh` — применяет директории/права/ZFS properties.
- `scripts/clean-scratch.sh` — чистит только `/data/scratch`.

На `pve01` установлен systemd timer:
- `npd-scratch-clean.timer` — daily, `Persistent=true`,
  `RandomizedDelaySec=30m`.
- `npd-scratch-clean.service` запускает `/usr/local/sbin/npd-clean-scratch`.
- Retention: `14` дней.

Снимки live-конфигов:
- `work/pve01/configs/2026-08-07-npd-scratch-clean.service`.
- `work/pve01/configs/2026-08-07-npd-scratch-clean.timer`.
- `work/pve01/logs/2026-08-07-storage-policy.log`.

Итог: `/data` получил понятные зоны ответственности; автоочистка касается
только scratch и не трогает projects/results. `cluster-health.sh` расширен до
`21 checks, 0 failed`.

### 2026-08-10 — pve02/monitor01 — поднят Prometheus monitoring phase 1

Создан LXC `monitor01`:
- Host: `pve02`.
- CTID: `112`.
- IP: `10.10.10.30/24`, gateway/DNS `10.10.10.1`.
- VLAN: `10` management.
- OS: Debian 12 LXC.
- Resources: 2 vCPU, 2G RAM, 32G rootfs.
- Services: `prometheus`, `prometheus-node-exporter`.

Node exporter установлен:
- Proxmox: `pve01` `10.10.10.11:9100`, `pve02` `10.10.10.12:9100`,
  `pve03` `10.10.10.13:9100`.
- Monitoring: `monitor01` `10.10.10.30:9100`.
- Alma/HTCondor: `condor01` `10.10.80.20:9100`,
  `asus-r1n1`-`asus-r1n4` `10.10.80.101`-`10.10.80.104:9100`.

Для AlmaLinux узлов добавлена воспроизводимая Ansible role `node_exporter`.
Используется официальный `node_exporter 1.12.1 linux-amd64` с SHA256:
`b51d8a76aa2a9156a55d501aca6276fae09e262259a5e4e831d2c2222f084e63`.

Prometheus config:
- Snapshot/source: `work/monitor01/prometheus.yml`.
- Live path внутри LXC: `/etc/prometheus/prometheus.yml`.
- UI: `http://10.10.10.30:9090`.

Проверки:
- `scripts/monitoring-health.sh` видит `10/10` targets `up`.
- `cluster-health.sh` расширен monitoring-проверками.

Итог: минимальная наблюдаемость CPU/RAM/disk/network по Proxmox, monitor01,
condor01 и первой ASUS-рельсе работает.

### 2026-08-10 — pve02/bastion01 — создан SSH bastion phase 1

Создан LXC `bastion01`:
- Host: `pve02`.
- CTID: `102`.
- IP: `10.10.50.10/24`, gateway/DNS `10.10.50.1`.
- VLAN: `50` DMZ.
- OS: Debian 12 LXC.
- Resources: 1 vCPU, 1G RAM, 16G rootfs.
- Services: `ssh`, `fail2ban`, `prometheus-node-exporter`.

SSH hardening:
- `PermitRootLogin no`.
- `PasswordAuthentication no`.
- `KbdInteractiveAuthentication no`.
- `PubkeyAuthentication yes`.
- `AllowAgentForwarding no`.
- `AllowTcpForwarding yes` для будущего `ProxyJump`.
- `X11Forwarding no`.
- `fail2ban` jail `sshd` включен через `backend = systemd`.

Monitoring:
- `bastion01` добавлен в Prometheus target list как role `bastion`.
- `scripts/monitoring-health.sh` теперь ожидает `11` targets.

Снимки live-конфигов:
- `work/bastion01/configs/2026-08-10-pct-config`.
- `work/bastion01/configs/2026-08-10-sshd-npd-bastion.conf`.
- `work/bastion01/configs/2026-08-10-fail2ban-sshd.local`.
- `work/bastion01/logs/2026-08-10-bastion-health.log`.
- `work/monitor01/configs/2026-08-10-prometheus-with-bastion.yml`.

Важно: WAN/NAT/port-forward для bastion **не создан**. Bastion пока поднят и
защищен внутри DMZ, но не опубликован наружу до отдельного решения по способу
публичного входа и списку SSH-ключей пользователей.

Итог: пользовательский SSH entrypoint подготовлен. `cluster-health.sh` расширен
до `27 checks, 0 failed`.

Сводка: `pve01` введён в строй (Proxmox на бывшем `head01`), собрана первая рабочая связка OPNsense-роутер + тестовая VM за NAT. Этапы 1–6 плана `today_plan` (в `archive/`) выполнены, этап 7 (свитч) — частично. `pve02/pve03` не трогались, Ceph/JBOD не подключались.

### 2026-08-11 — Force10 / Supermicro rack — сверка портов после подключения новых нод

Пользователь физически поправил trunk `pve01` и подключил две новые Supermicro
ноды в шкаф Supermicro. Проверка с `pve01`:

```text
pve01 nic1 -> Up, 1000Mb/s Full
cluster-health --skip-storage -> 21 checks, 0 failed, 6 skipped
```

JBOD сознательно отложен, поэтому storage-проверки пропущены через новый режим
`./scripts/cluster-health.sh --skip-storage`.

По выводу Force10:

```text
Gi 0/6  Up 1000 Full trunk VLAN 10,20,30,40,50,80,99
        MAC VLAN10 ac:1f:6b:4c:d7:ca  -> future pve04 LAN1
Gi 0/7  Up 1000 Full trunk VLAN 10,20,30,40,50,80,99
        MAC VLAN10 ac:1f:6b:4c:d7:c8  -> future pve05 LAN1
Gi 0/16 Up 1000 Full VLAN30
        MAC ac:1f:6b:4c:ce:80        -> future pve04 IPMI
Gi 0/17 Up 1000 Full VLAN30
        MAC ac:1f:6b:4c:ce:7f        -> future pve05 IPMI
```

Вывод: физическое подключение будущих `pve04`/`pve05` на уровне Force10
выглядит корректно. Ноды пока не введены в Proxmox-кластер и не отвечают на
ожидаемые management IP.

Найденная текущая проблема:

```text
Force10 Gi 0/1 -> Down
Force10 Gi 0/2 -> Up, member of Po1
```

То есть межшкафный LACP Force10 <-> switch1 временно деградировал до одного
линка. Нужно проверить кабель `Force10 Gi 0/1` ↔ `switch1 port 2`.

Документация обновлена:

- добавлен `force10_port_map.md` как фактическая карта портов Force10;
- `production_port_plan.md` очищен от устаревшего пункта про перенос `pve01`;
- README теперь указывает оба port-map документа: Force10 и switch1.

### 2026-08-12 — bastion/HTCondor — end-to-end user access validation

Проверен полный пользовательский путь SSH-only доступа:

```text
Internet/Tailscale Funnel :10000
  -> bastion01 10.10.50.10:22
  -> ProxyJump
  -> condor01 10.10.80.20:22
  -> HTCondor submit
  -> ASUS execute node
```

Создан временный тестовый пользователь `npdtest` (UID `20000`) на `bastion01`
и `condor01` через штатный `scripts/create-cluster-user.py --accounts-only`.
Пользователь key-only, без sudo. Временный private key после проверки удалён с
`/tmp`.

Найден и исправлен недостающий firewall-проход: на OPNsense в правилах `DMZ`
добавлено narrow pass rule выше `Block DMZ to HTCONDOR`:

```text
source:      10.10.50.10   # bastion01
destination: 10.10.80.20   # condor01
protocol:    TCP/22
```

ICMP из DMZ в HTCONDOR остаётся заблокирован, но SSH `bastion01 -> condor01:22`
открыт, чего достаточно для ProxyJump.

Результат пользовательского smoke job:

```text
npdtest -> condor01 -> HTCondor cluster 35
execute host: asus-r1n1.internal
exit code: 0
output: hello from asus-r1n1.internal
```

Замечание: job на execute-ноде выполнилась как `nobody` (UID 65534), потому что
`npdtest` пока создан только на `bastion01`/`condor01`, не на ASUS execute
нодах. Для простых file-transfer job это работает. Для production `/data` и
нормальных POSIX-прав нужно решить модель идентичности: создавать пользователей
на execute-нодах через Ansible либо изменить HTCondor identity policy.

### 2026-08-12/13 — power characterization — первые реальные замеры потребления

Создан файл замеров:

```text
work/measurements/2026-08-12-power-characterization/README.md
```

Ключевые измеренные значения:

```text
pve01 Supermicro idle:                 111 W
pve01 Supermicro boot peak:            180 W
pve01 Supermicro CPU-only:             226 W
pve01 Supermicro heavy RAM 256 GiB:    221 W stable / 238 W peak
pve01 Supermicro mixed heavy:          230 W stable / 240 W peak

ASUS rail 1 idle, 4 nodes:             320 W
ASUS rail 1 boot peak, 4 nodes:        870 W
ASUS rail 1 CPU load, 4 nodes:        1300 W stable

Force10 S60 idle/max observed:         120 W / 200 W
HP 3500yl idle/max observed:           120 W / 200 W

JBOD shelf startup/idle:               350 W / 230 W
Expected JBOD estate:                  roughly 8-12 shelves in docs,
                                       current planning range 8-10 shelves
```

Планировочный вывод:

```text
10 Supermicro heavy:                  ~2.4 kW
48 ASUS heavy:                       ~15.6 kW
2 switches max:                       ~0.4 kW
8-10 JBOD idle:                       ~1.8-2.3 kW
Full measured heavy + JBOD idle:      ~20.2-20.7 kW
With 30% reserve:                     ~26.3-26.9 kW
```

Итог: ASUS-парк является главным потребителем. До подтверждения PDU/линий и
охлаждения нельзя включать/нагружать все ASUS-рельсы одновременно.

### 2026-08-13 — monitoring — повторная проверка `pve03:9100`

После вчерашней ASUS CPU-нагрузки один health-check показал
`pve03:9100 down`. Повторная проверка 2026-08-13:

```text
pve03 prometheus-node-exporter: active, listening on *:9100
monitoring-health.sh: 11/11 up
cluster-health.sh --skip-storage: 21 checks, 0 failed, 6 skipped
```

Итог: постоянной поломки monitoring не найдено; вероятно, кратковременный
scrape/down во время перезапуска или нагрузки. Текущий минимальный стек снова
зелёный.

### 2026-08-13 — user access — HTCondor запускает jobs под реальным UID

Закрыта проблема из предыдущего smoke test, где пользовательский job доходил до
ASUS execute-ноды, но выполнялся как `nobody` / UID `65534`.

Что изменено:

```text
scripts/create-cluster-user.py
  --execute-nodes  создать locked POSIX identity на ASUS вместе с новым user
  --execute-only   досинхронизировать identity для уже существующего user

HTCondor config on condor01 + ASUS:
  UID_DOMAIN = internal
  TRUST_UID_DOMAIN = True
  FILESYSTEM_DOMAIN = per-host FQDN, пока /data не считается постоянным
```

Для `npdtest` UID `20000` создан на `condor01` и `asus-r1n1`-`asus-r1n4`.
На execute-нодах SSH-ключи не ставятся: эти аккаунты нужны только для
POSIX/HTCondor identity, вход пользователей остаётся через
`bastion01 -> condor01`.

Проверка:

```text
HTCondor cluster 42
execute host: asus-r1n3.internal
whoami: npdtest
id -u: 20000
exit code: 0

Final smoke check:
HTCondor cluster 45
JobStatus: 4 completed
ExitCode: 0
whoami/id: npdtest / 20000
```

Также исправлен `scripts/user-access-health.sh`: проверка
`authorized_keys` на `condor01` теперь идёт через `sudo -n test`, потому что
домашние каталоги пользователей закрыты правами `700`.

### 2026-08-13 — pve02 — Funnel автоподъём после ребута

После ребута `npd-tailscale-funnel.service` мог падать, если `tailscaled` ещё
не успел выйти из `NoState`. На `pve02` добавлен systemd drop-in:

```text
/etc/systemd/system/npd-tailscale-funnel.service.d/retry.conf
```

Локальная копия сохранена в репозитории:

```text
work/pve02/npd-tailscale-funnel-retry.conf
```

Проверенное текущее состояние:

```text
npd-tailscale-funnel.service      active
npd-bastion-ssh-forward.service   active
tailscaled.service                active

tcp://pve02.taile43d6d.ts.net:10000 -> 127.0.0.1:10022
https://pve02.taile43d6d.ts.net     -> 127.0.0.1:18080
```

Быстрые проверки после фикса:

```text
user-access-health.sh npdtest:        6 checks, 0 failed
cluster-health.sh --skip-storage:    21 checks, 0 failed, 6 skipped
```

### 2026-08-28 — vpn-npd — primary public gateway через Azure + WireGuard

Создан отдельный внешний gateway `vpn-npd`, чтобы пользовательский доступ не
зависел от Tailscale как единственной публичной двери.

Текущая схема:

```text
Internet user
  -> 20.215.200.4:10000
  -> vpn-npd wg0 10.255.80.1
  -> WireGuard UDP/51820
  -> pve02 wg0 10.255.80.2:10022
  -> bastion01 10.10.50.10:22
  -> ProxyJump to condor01 10.10.80.20
```

Хосты и сервисы:

```text
vpn-npd:
  OS: Ubuntu 24.04.4 LTS
  public IP: 20.215.200.4
  wg0: 10.255.80.1/30
  services:
    wg-quick@wg0
    npd-public-bastion-ssh-forward.service

pve02:
  wg0: 10.255.80.2/30
  services:
    wg-quick@wg0
    npd-vpn-bastion-ssh-forward.service
```

Azure NSG inbound rules:

```text
UDP 51820  allow-wireguard-51820
TCP 10000  allow-npd-bastion-10000
```

Проверка после открытия правил:

```text
20.215.200.4:10000 open
20.215.200.4:51820 udp reachable
pve02 -> 10.255.80.1 ping: 0% loss, ~31 ms
vpn-npd -> 10.255.80.2 ping: 0% loss, ~31 ms
WireGuard latest handshake: present
20.215.200.4:10000 banner: SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u10
user-access-health.sh npdtest: 8 checks, 0 failed
```

Локальные service snapshots сохранены без приватных WireGuard ключей:

```text
work/vpn-npd/npd-public-bastion-ssh-forward.service
work/pve02/npd-vpn-bastion-ssh-forward.service
```

Tailscale Funnel остаётся как admin/fallback channel, но primary user-facing
endpoint теперь `ssh -p 10000 <username>@20.215.200.4`.
