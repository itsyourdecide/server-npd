# HTCondor + PXE architecture plan

Дата: 2026-08-06
Статус: draft v0.5, первый HTCondor pool работает: `condor01` + 4 ASUS execute-ноды

## Цель

Построить управляемую вычислительную площадку для кафедры физики высоких энергий:

- Supermicro-ноды остаются Proxmox-гипервизорами и могут гибко отдавать свободные CPU/RAM в HTCondor через execute-VM.
- ASUS-ноды используются как bare-metal HTCondor execute-ноды.
- Пользователи сначала заходят через bastion/login frontend и отправляют jobs в HTCondor.
- Научный software stack делается ближе к HEP/CERN-подходу: HTCondor + CVMFS + контейнеры/окружения, а не ручная установка Geant4 на каждую ноду.
- PXE/Kickstart ставит только базовую AlmaLinux с SSH/admin user; HTCondor, CVMFS, scientific stack и tuning применяются после установки через Ansible.
- Массовый PXE запускается только после успешного теста на 1 ASUS bare-metal и 1 Supermicro execute-VM.

## Уже готовая база

- VLAN80 `HTCONDOR_PXE`: `10.10.80.0/24`.
- Gateway/DNS: `fw01` / OPNsense, `10.10.80.1`.
- PXE-сервер: `pxe01`, `10.10.80.10`.
- DHCP/PXE boot через OPNsense Dnsmasq:
  - boot server: `10.10.80.10`
  - boot file: `ipxe.efi`
- `/srv/tftp/ipxe.efi` — custom embedded legacy iPXE (`undionly.kpxe` payload), который после DHCP сам цепляет `http://10.10.80.10/boot.ipxe`. Имя оставлено `ipxe.efi`, потому что так уже настроен DHCP в OPNsense, но содержимое legacy-compatible для старого Intel Boot Agent на ASUS.
- HTTP/TFTP на `pxe01` проверены из VLAN80.
- `boot.ipxe` содержит MAC-based список известных ASUS. Для них destructive install запускается только если есть файл `/srv/pxe/http/install-once/<mac>.ipxe`; если файла нет, iPXE выходит в BIOS boot order.
- Для ASUS с legacy BIOS нельзя полагаться на `sanboot --drive 0x80`: на этих нодах он зависал на `Booting from SAN device 0x80`. Используем `exit` из iPXE и правильный BIOS boot order.
- AlmaLinux packages идут через локальный nginx cache на `pxe01`: `http://10.10.80.10/alma-cache/almalinux/9/...`. Первый запрос к RPM может сходить во внешний интернет, повторные установки берут пакет локально.

## Согласованная архитектура

### Управляющие сервисы

| Hostname | IP | Где живет | Роль |
| --- | --- | --- | --- |
| `pxe01.internal` | `10.10.80.10` | LXC на `pve02` | TFTP/HTTP для PXE/iPXE |
| `condor01.internal` | `10.10.80.20` | VM на `pve02` | HTCondor central manager + submit |
| `bastion01.internal` | `10.10.80.21` | VM, стартово можно на `pve02` | SSH-вход пользователей, сначала также submit/frontend |

На первом этапе `bastion01` может совмещать bastion/login/submit-функции. В плане оставляем возможность позже разделить `bastion01`, `login01` и `submit01`.

### Supermicro

Supermicro-ноды используются как Proxmox-гипервизоры. HTCondor запускается не на Proxmox host напрямую, а внутри одной большой execute-VM на каждой Supermicro-ноде, когда есть свободные ресурсы.

Стартовый размер execute-VM:

- OS: AlmaLinux 9
- vCPU: 16
- RAM: 128 GB
- роль: HTCondor execute
- CVMFS: да
- local scratch: `/scratch`

Планируемые имена/IP:

| Hostname | IP | Роль |
| --- | --- | --- |
| `condor-sm01.internal` | `10.10.80.31` | Supermicro execute-VM |
| `condor-sm02.internal` | `10.10.80.32` | Supermicro execute-VM |

Дальнейшие `condor-smXX` добавляются по мере включения Supermicro-нод.

### ASUS

ASUS-ноды ставятся с чистого листа, без сохранения CERN legacy OS/config/data. PXE-профиль должен считать диск расходным и выполнять clean install.

Базовый профиль:

- OS: AlmaLinux 9
- установка: unattended clean install после успешного первого теста
- роль: HTCondor execute
- CVMFS: да
- local scratch: `/scratch`
- monitoring: добавить после базового HTCondor milestone

Именование ASUS по рельсам:

Физическая нумерация узлов внутри рельсы задаётся **со стороны задней панели, где сетевые порты**:

```text
rear / ports side

+-----------+-----------+
|    n2     |    n4     |
+-----------+-----------+
|    n1     |    n3     |
+-----------+-----------+
```

То есть `n1` — нижний левый узел, `n2` — верхний левый, `n3` — нижний правый, `n4` — верхний правый.

| Hostname | IP | Роль |
| --- | --- | --- |
| `asus-r1n1.internal` | `10.10.80.101` | bare-metal execute |
| `asus-r1n2.internal` | `10.10.80.102` | bare-metal execute |
| `asus-r1n3.internal` | `10.10.80.103` | bare-metal execute |
| `asus-r1n4.internal` | `10.10.80.104` | bare-metal execute |

Следующие рельсы: `asus-r2n1` ... `asus-r2n4`, и так далее.

Текущая первая рельса, switch1:

| Hostname | LAN MAC | OS IP | IPMI MAC | IPMI IP | LAN port | IPMI port |
| --- | --- | --- | --- | --- | ---: | ---: |
| `asus-r1n1.internal` | `20:cf:30:72:52:ae` | `10.10.80.101` | `54:04:a6:f4:21:0a` | `10.10.30.101` | 14 | 41 |
| `asus-r1n2.internal` | `c8:60:00:31:8c:13` | `10.10.80.102` | `c8:60:00:8b:d5:8b` | `10.10.30.102` | 15 | 42 |
| `asus-r1n3.internal` | `20:cf:30:7c:98:f2` | `10.10.80.103` | `c8:60:00:ea:3b:9e` | `10.10.30.103` | 16 | 43 |
| `asus-r1n4.internal` | `c8:60:00:39:1e:fb` | `10.10.80.104` | `c8:60:00:ea:3b:a6` | `10.10.30.104` | 17 | 44 |

Состояние на 2026-08-05:

| Hostname | OS/SSH | firstboot | IPMI ping | Notes |
| --- | --- | --- | --- | --- |
| `asus-r1n1.internal` | OK | OK | OK | LAN/PXE fixed, reinstalled successfully |
| `asus-r1n2.internal` | OK | OK | OK | ready for Ansible |
| `asus-r1n3.internal` | OK | OK | pending | OS ready, IPMI later |
| `asus-r1n4.internal` | OK | OK | pending | OS ready, IPMI later |

BIOS boot order для массовой установки с возможностью последующих reinstall:

```text
1st Boot Device: Network: IBA GE Slot 0200
2nd Boot Device: AHCI/SATA disk
3rd Boot Device: Network: IBA GE Slot 0300
```

Если ОС уже установлена и reinstall не нужен, можно оставить SATA первым. Главное правило: не ставить обе сетевые карты перед SATA, иначе после `exit` из iPXE BIOS уйдет во второй PXE и покажет `PXE-E61`.

## Сеть и DNS

Рабочий домен оставляем `internal`, потому что он уже используется в OPNsense/DHCP и подходит для приватной лабораторной инфраструктуры.

VLAN80 одновременно используется для:

- PXE boot;
- HTCondor control/data traffic на первом этапе;
- доступа execute-нод к `condor01`, `pxe01`, CVMFS/HTTP(S) через `fw01`.

Интернет для compute-нод идет через `fw01`. На старте можно оставить обычный outbound-доступ для тестов. Позже правила стоит сузить до нужного:

- DNS/NTP;
- HTTP/HTTPS для package repos, CVMFS, контейнеров;
- HTCondor-порты между `condor01`, submit/frontend и execute-нодами;
- SSH/admin-доступ только с management/bastion.

## Пользователи

На тестовом этапе можно завести 1-2 admin/test users, но не строить систему вокруг shared root/shared user.

Базовое решение для PXE-installed nodes:

- создать admin user `npdadmin`;
- дать sudo;
- добавить SSH-ключ администратора;
- root SSH позже можно закрыть или ограничить.

Нормальная multi-user модель, квоты, политики и учет студентов откладываются до успешного технического milestone, но архитектурно учитываются заранее.

## Storage

JBOD планируется использовать для datasets/results, но не включается в первый HTCondor/PXE milestone.

Первый этап:

- маленькие тестовые jobs;
- локальный scratch на execute-нодах;
- результаты можно временно возвращать на submit/frontend.

Следующий этап:

- storage VM или storage role на базе JBOD/ZFS;
- NFS export, например `/data`;
- подключение `/data` к `bastion01`/`condor01` и execute-нодам;
- позже добавить quota/backup/retention policy.

Важно: не смешивать первый PXE+HTCondor тест с вводом JBOD, чтобы легче отлаживать ошибки.

## CVMFS и scientific software

Предпочтительный HEP-подход: не ставить Geant4 и весь scientific stack руками на каждую ноду, а сделать базовую compute-ноду с:

- HTCondor;
- CVMFS client;
- контейнерным runtime при необходимости, предпочтительно Apptainer/Singularity-style для HPC/HEP;
- локальным cache/scratch.

Потенциально нужные CVMFS repositories:

- `sft.cern.ch` для CERN/LCG software stack;
- `lhcb.cern.ch`, если нужна LHCb-специфика;
- `grid.cern.ch`, если понадобится grid middleware;
- `unpacked.cern.ch`, если используем контейнерные образы через CVMFS.

Точный список репозиториев надо подтвердить после первого CVMFS smoke test и понимания, какие workflows нужны кафедре.

Справочные источники:

- CVMFS client: https://cvmfs.readthedocs.io/en/stable/cpt-quickstart.html
- CVMFS configuration: https://cvmfs.readthedocs.io/en/stable/cpt-configure.html
- CVMFS containers: https://cvmfs.readthedocs.io/en/stable/cpt-containers.html
- HTCondor roles/get_htcondor: https://htcondor.readthedocs.io/en/latest/man-pages/get_htcondor.html
- Geant4 installation guide: https://geant4.web.cern.ch/documentation/dev/ig_html/InstallationGuide/

## PXE and Ansible split

PXE/Kickstart должен оставаться маленьким и предсказуемым:

- clean AlmaLinux install;
- DHCP networking;
- `npdadmin` with sudo and SSH key;
- `sshd`, `chronyd`, NetworkManager;
- Python and small admin tools required for Ansible.

Everything role-specific is configured later with Ansible:

- HTCondor execute node;
- CVMFS client and repository list;
- Geant4/ROOT/LCG software access;
- monitoring;
- JBOD/NFS mounts;
- kernel/sysctl/tuning;
- users and policy.

This lets the first 4-8 ASUS nodes be installed quickly as a base fleet, then iterated on without reinstalling the OS.

## HTCondor milestone 1

Состояние на 2026-08-06:

- `condor01.internal` установлен как central manager + submit/access point.
- `CONDOR_HOST` задан как `condor01.internal`; DNS override в OPNsense указывает `condor01.internal -> 10.10.80.20`.
- `NETWORK_INTERFACE` задается явно: `10.10.80.20` на `condor01`, `ansible_host` на execute-нодах, чтобы HTCondor не рекламировал `127.0.0.1`.
- `asus-r1n1.internal` ... `asus-r1n4.internal` установлены как execute nodes.
- `condor_status` на `condor01` видит 4 idle execute slots.
- Smoke test `cluster 1` отправил 4 jobs; job log подтвердил запуск на всех четырех ASUS:
  - `10.10.80.101` / `asus-r1n1.internal`
  - `10.10.80.102` / `asus-r1n2.internal`
  - `10.10.80.103` / `asus-r1n3.internal`
  - `10.10.80.104` / `asus-r1n4.internal`

Открыто:

- CVMFS/client role добавлена; `sft.cern.ch` и `unpacked.cern.ch` проходят probe на `condor01` и первой ASUS-рельсе.
- Добавить storage/JBOD mount design.
- Добавить monitoring и power/thermal benchmarks.

## PXE profiles to implement

Планируемая структура на `pxe01`:

```text
/srv/pxe/http/boot.ipxe
/srv/pxe/http/menu.ipxe
/srv/pxe/http/profiles/alma9-basic-autoinstall.ipxe
/srv/pxe/http/profiles/alma9-asus-execute.ipxe
/srv/pxe/http/profiles/alma9-condor-sm-execute.ipxe
/srv/pxe/http/profiles/alma9-bastion-submit.ipxe
/srv/pxe/http/kickstart/alma9-basic.ks
/srv/pxe/http/kickstart/alma9-condor-sm-execute.ks
/srv/pxe/http/kickstart/alma9-bastion-submit.ks
/srv/pxe/http/scripts/postinstall-common.sh
/srv/pxe/http/scripts/postinstall-condor-execute.sh
/srv/pxe/http/scripts/postinstall-cvmfs.sh
```

Первый режим может быть ручным меню:

- unattended test install only for VMID 120 MAC `bc:24:11:fb:09:b8`;
- AlmaLinux 9 BASIC autoinstall, destructive, selected manually from menu;
- install `bastion01`;
- manual ASUS installer fallback;
- manual Supermicro execute-VM installer fallback;
- local boot;
- iPXE shell.

`condor01` создается отдельно как обычная VM на `pve02`, а не как обязательный PXE-профиль. Это снижает риск случайной переустановки управляющей VM через PXE.

Текущий `condor01`:

| Field | Value |
| --- | --- |
| Proxmox node | `pve02` |
| VMID | `130` |
| MAC | `bc:24:11:cd:01:30` |
| VLAN | `80` |
| OS IP | `10.10.80.20` |
| Disk | `local-zfs`, 64G |
| vCPU/RAM | 4 vCPU / 8G RAM |
| PXE profile | `alma9-condor01-autoinstall.ipxe` |

После первого успешного цикла можно перейти к MAC-based inventory:

```text
MAC -> hostname -> static IP -> profile -> disk policy
```

Для ASUS это уже сделано через:

- `/srv/pxe/http/asus-r1-map.csv` — MAC/IP/hostname/ports inventory первой рельсы;
- `/srv/pxe/http/scripts/asus-firstboot.sh` — первый boot ОС выставляет hostname, статический OS IP и IPMI IP;
- `/srv/pxe/http/install-once/<mac>.ipxe` — одноразовый destructive reinstall-флаг;
- `/usr/local/sbin/create-install-once.sh <mac>` — безопасное создание флага с watcher;
- `/usr/local/sbin/create-install-once-batch.sh r1` — batch-создание install-once flags по CSV inventory;
- `/usr/local/sbin/install-once-watcher.sh` — удаляет флаг только после нового HTTP 200 GET.

Важно: install-once watcher должен смотреть только новые строки nginx access log с момента запуска. Старый вариант, который grep-ал весь лог, мог удалить свежий флаг из-за старого `200` события.

Перед следующей рельсой:

1. Добавить строки `asus-r2n1` ... `asus-r2n4` в CSV inventory с LAN MAC, IPMI MAC, OS/IPMI IP и портами.
2. Добавить MAC в `boot.ipxe` как known ASUS nodes.
3. Синхронизировать CSV/boot script на `pxe01`.
4. Проверить dry-run:

```sh
/usr/local/sbin/create-install-once-batch.sh --dry-run r2
```

5. Создать flags и включить ноды:

```sh
/usr/local/sbin/create-install-once-batch.sh r2
```

## Первый milestone

Цель: доказать весь путь от PXE до рабочей HTCondor job.

1. Создать `condor01` VM на `pve02`.
2. Установить AlmaLinux 9.
3. Настроить HTCondor central manager + submit.
4. Создать `bastion01` или временно использовать `condor01` как submit/frontend.
5. Создать `condor-sm01` VM на `pve02`:
   - AlmaLinux 9 basic install;
   - 16 vCPU;
   - 128 GB RAM;
   - HTCondor execute role applied by Ansible.
6. Установить один ASUS bare-metal, стартово `asus-r1n1`:
   - clean install;
   - AlmaLinux 9 basic install;
   - HTCondor execute role applied by Ansible.
7. Проверить:
   - `condor_status` видит `condor-sm01` и `asus-r1n1`;
   - simple job успешно выполняется;
   - output возвращается на submit node.
8. Добавить CVMFS smoke test:
   - client installed;
   - нужные repos монтируются;
   - простой доступ к `/cvmfs/...`.
9. Только после этого включать массовый PXE для остальных ASUS.

## Что специально откладываем

- Массовая установка всех ASUS до первого milestone.
- JBOD/NFS production storage.
- Полная user/quota model.
- Web/Jupyter frontend.
- GPU/Tesla T4 scheduling в HTCondor.
- Сложная автоматизация по MAC/inventory до первого успешного ручного профиля.
- LHCbDIRAC/DIRAC integration. Сначала локальный HTCondor pool.

## Открытые вопросы

- Где в итоге будет жить `bastion01`: в VLAN80 или отдельной management/private зоне.
- Нужно ли разделять `condor01` и submit/frontend сразу после PoC.
- Точный список CVMFS repositories.
- Политика outbound firewall для execute-нод.
- Storage design для JBOD: storage VM/NFS vs host ZFS export.
- Final naming/IP для всех Supermicro execute-VM после инвентаризации всех нод.
