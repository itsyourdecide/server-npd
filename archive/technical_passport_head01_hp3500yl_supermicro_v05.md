# Технический паспорт — head01, HP 3500yl, кластер Supermicro

Версия: 0.5  
Дата: 2026-06-27  
Статус: черновик, обновлён — инвентаризация железа завершена, SSH/каталоги/сервисы подтверждены  
Основной узел: `head01`  
Основной коммутатор: HP 3500yl-48G `J8693A`  
Основное направление: новая инфраструктура на базе Supermicro, где `head01` — управляющий узел

> **Статус документа после архитектурной сессии 27.06.2026**  
> Этот файл фиксирует текущее состояние Ubuntu `head01` и первого HP 3500yl. Он не является целевой архитектурой. Актуальная целевая схема находится в `cluster_architecture_presentation.md`, порядок внедрения — в `cluster_implementation_plan.md`, команды выездной проверки — в `cluster_inventory_checklist.md`.

### Принятые уточнения

- Всего имеется 10 Supermicro, включая `head01`, а не 10 плюс отдельный `head01`.
- Для пилота будут одновременно доступны ровно три Supermicro.
- Цель пилота — установить Proxmox VE на все три узла и сформировать равноправный трёхузловой кластер.
- Текущая Ubuntu на `head01` является временной. Перед переустановкой нужно сохранить сетевую, IPMI, Tailscale и инвентаризационную конфигурацию.
- Три pilot-узла планируются как постоянно включённое ядро Proxmox/Ceph/HA, а не как отдельные неиспользуемые control-серверы.
- Подтверждён второй HP 3500yl с физическим доступом; его конфигурация и 10GbE-модуль пока не проверены.
- Текущий единый VLAN 10 и роль `head01` как NAT-шлюза являются временной схемой. Production требует отдельных management, IPMI, VM, DMZ и storage-сетей.
- Принято решение включить все 10 Supermicro в один Proxmox-кластер для VM/LXC и Slurm worker VM. При 10 голосах quorum равен 6, поэтому массовое регулярное выключение PVE-узлов не допускается; энергосбережение применяется к ASUS.
- Ориентир по JBOD — около 10 полок с отклонением примерно ±20%; фактическое число дисков и их состояние неизвестны.
- До инвентаризации не закупаются SSD, SAS HBA, кабели или быстрая сеть.

## 1. Назначение документа

Этот документ является техническим паспортом текущего состояния инфраструктуры.

Он фиксирует:

- подтверждённые факты по оборудованию;
- подтверждённую топологию сети;
- подтверждённую конфигурацию коммутатора;
- подтверждённую сетевую конфигурацию `head01`;
- обнаруженные старые узлы ASUS;
- текущие предположения о ролях;
- что нельзя менять без согласования;
- что пока неизвестно и должно быть инвентаризировано;
- планируемую будущую топологию.

Это не просто журнал устранения неполадок. Он задуман как базовый документ для дальнейшего развёртывания кластера.

## 2. Замысел инфраструктуры

Текущее направление:

```text
head01 becomes the main control node of the new infrastructure.
New Supermicro servers become the main compute/server platform.
Old ASUS servers remain legacy and should not be treated as the future base.
HP 3500yl is currently configured as VLAN 10 PXE/install switch.
```

Ожидаемое будущее:

```text
router / upstream network
  |
  v
switch
  |
  +-- head01 LAN1 / normal LAN / upstream access
  +-- head01 LAN2 / install or cluster network
  +-- Supermicro nodes
  +-- IPMI/BMC ports
  +-- optional ASUS legacy nodes
```

Важная поправка:

```text
The router should not be treated as permanently connected directly to head01 LAN1.
Current direct router-to-LAN1 is temporary.
Future topology should place the router/upstream behind a switch or proper network segment.
```

### Ранее принятая временная схема (зафиксирована 2026-06-27, заменена архитектурой v2)

**Топология временного стенда — Вариант B: head01 как NAT-шлюз:**

```text
Internet
   |
Router (upstream, его DHCP работает)
   |
head01 enp3s0f0 — WAN (192.168.31.x временно)
   |
  [NAT + DHCP на head01]
   |
head01 enp3s0f1 — 10.10.0.101 — LAN шлюз
   |
HP switch VLAN 10 — единый сегмент
   ├── Supermicro ноды  →  10.10.0.10–200
   ├── IPMI портов      →  10.10.0.x
   └── ASUS legacy      →  10.10.0.1
```

Обоснование выбора:

```text
Один кабель на ноду (без trunk).
Нет конфликта DHCP — head01 единственный DHCP-сервер в 10.10.0.x.
Минимальная конфигурация свича — VLAN 10 как есть, ничего не менять.
head01 контролирует весь трафик нод — удобно для мониторинга.
```

**Статус реализации:**

```text
ОТЛОЖЕНО — head01 сейчас на временном месте, сеть будет меняться при переезде в серверную.
Настраивать NAT/DHCP имеет смысл только в финальном расположении.
```

**Что стабильно и делается сейчас:**

```text
- Tailscale установлен — доступ к head01 не зависит от физической сети ✓
- Внутренняя сеть 10.10.0.x остаётся неизменной
- Инвентаризация head01 (раздел 22)
```

## 3. Известное оборудование — класс сервера Supermicro

Загруженное руководство Supermicro определяет класс сервера как:

```text
Supermicro SuperServer 6028R-TR / 6028R-TRT
```

Известные характеристики платформы:

```text
Chassis: SC825TQ-R740LPB class 2U chassis
Serverboard family: X10DRi / X10DRi-T
Chipset: Intel C612
CPU family: Intel Xeon E5-2600 v3/v4
Memory: DDR4 ECC RDIMM/LRDIMM, up to 1 TB depending configuration
Drive bays: 8 hot-swap SATA bays
Power supplies: redundant 740 W
Cooling: hot-plug server fans
IPMI/BMC: dedicated management controller and dedicated IPMI LAN port
```

Замечание по сети:

```text
X10DRi usually has 1GbE LAN ports.
X10DRi-T usually has 10GbE LAN ports.
```

**Подтверждено 2026-07-01** (после установки Proxmox, `dmidecode`/`lspci` на `pve01`): плата — именно **X10DRI-T**, встроены **два 10GbE Intel X540-AT2** (`nic0`/`nic1`), не 1GbE. См. `cluster_operations_log.md`, запись «pve01 — инвентаризация железа, найдено расхождение с паспортом».

Важные эксплуатационные замечания:

```text
IPMI/BMC is separate from Ubuntu network interfaces.
IPMI can work even if the OS is down, as long as standby power is present.
Do not expose IPMI directly to the public internet.
Server boot can be slow due to ECC memory, BMC/IPMI, PCIe/HBA, and POST checks.
```

## 4. Известный хост — head01

Имя хоста:

```text
head01
```

Наблюдаемое имя пользователя Linux:

```text
ultron
```

Роль:

```text
New infrastructure control node.
Potential future Ansible controller.
Potential future PXE/autoinstall server.
Potential future monitoring/logging/control node.
```

Текущее подтверждённое состояние:

```text
head01 is running Ubuntu/Linux.
head01 has at least two normal network interfaces visible to Linux:
- enp3s0f0
- enp3s0f1

head01 also has a separate IPMI/BMC interface not shown as a normal Linux NIC.
```

Известные установленные/использованные инструменты по уже выполненным командам:

```text
iproute2 tools: ip, ip route, ip neigh
ethtool
nmap
tcpdump
curl
ss
sudo
```

Неизвестно и пока не задокументировано:

```text
OS version
kernel version
disk layout
mounts
filesystems
installed packages
enabled services
SSH configuration
Tailscale status
Ansible status
important directories
netplan configuration
firewall status
users and sudoers
IPMI configuration
BIOS boot settings
```

Это должно быть инвентаризировано позже командами из раздела 21.

## 5. Текущие физические соединения

Подтверждённая текущая/временная кабельная схема:

```text
head01 LAN1 -> router / normal LAN / internet
head01 LAN2 -> HP 3500yl switch, port 25
head01 IPMI -> HP 3500yl switch, port 26  (перемещён с порта 27)
```

Важная будущая поправка:

```text
The direct router -> head01 LAN1 connection is temporary.
Future design should be router/upstream -> switch -> head01 and other infrastructure devices.
```

Наблюдаемое соответствие портов коммутатора HP:

```text
Port 1  -> old ASUS, MAC 20:cf:30:72:52:ae, IP 10.10.0.1
Port 3  -> old ASUS, MAC c8:60:00:39:1e:fb, DHCP client, no IP assigned
Port 5  -> old ASUS, MAC 20:cf:30:7c:98:f2, no IP confirmed
Port 25 -> head01 LAN2, MAC ac:1f:6b:4c:d7:43, IP 10.10.0.101
Port 26 -> head01 IPMI, MAC ac:1f:6b:4c:ce:a0, DHCP client, no IP assigned
```

## 6. Сетевые интерфейсы head01

Использованная команда:

```bash
ip a
```

### 6.1 LAN1 — текущая обычная LAN

Интерфейс:

```text
enp3s0f0
```

MAC:

```text
ac:1f:6b:4c:d7:42
```

Текущий IP:

```text
192.168.31.136/24
```

Состояние:

```text
UP, LOWER_UP
```

Текущая роль:

```text
temporary normal LAN / internet path
```

Текущий вышестоящий шлюз:

```text
192.168.31.1
```

Текущая роль маршрута:

```text
default route goes through enp3s0f0
```

### 6.2 LAN2 — коммутатор HP / VLAN 10

Интерфейс:

```text
enp3s0f1
```

MAC:

```text
ac:1f:6b:4c:d7:43
```

Текущий статический IP:

```text
10.10.0.101/24
```

Способ назначения:

```text
netplan (постоянный, переживает ребут)
```

Конфиг /etc/netplan/50-cloud-init.yaml:

```yaml
network:
  version: 2
  ethernets:
    enp3s0f0:
      dhcp4: true
    enp3s0f1:
      dhcp4: false
      addresses:
        - 10.10.0.101/24
```

Итоговое наблюдаемое состояние:

```text
UP, LOWER_UP
Link detected: yes
valid_lft forever  ← постоянный адрес
```

Текущая роль:

```text
connection from head01 to HP switch VLAN 10
future: LAN gateway for cluster nodes
```

Замечание:

```text
cloud-init отключён для сети:
/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
content: network: {config: disabled}
Без этого cloud-init перезаписал бы netplan при ребуте.
```

### 6.3 Детали линка LAN2

Использованная команда:

```bash
sudo ethtool enp3s0f1
```

Наблюдаемое:

```text
Speed: 100Mb/s
Duplex: Full
Auto-negotiation: on
Link detected: yes
```

Проблема:

```text
LAN2 currently negotiates at 100Mb/s.
For diagnostics this is acceptable.
For production this should be investigated.
```

Возможные причины:

```text
bad cable
old cable
switch port negotiation issue
server NIC negotiation issue
port forced somewhere
```

## 7. Маршрутизация head01

Использованная команда:

```bash
ip route
```

Наблюдаемое:

```text
default via 192.168.31.1 dev enp3s0f0 proto dhcp src 192.168.31.136 metric 100
10.10.0.0/24 dev enp3s0f1 proto kernel scope link src 10.10.0.101
192.168.31.0/24 dev enp3s0f0 proto kernel scope link src 192.168.31.136 metric 100
192.168.31.1 dev enp3s0f0 proto dhcp scope link src 192.168.31.136 metric 100
```

Интерпретация:

```text
Internet/default route -> enp3s0f0 -> 192.168.31.1
PXE/install network -> enp3s0f1 -> 10.10.0.0/24
```

Это состояние корректно.

Важное замечание по безопасности:

```text
Do not add a default gateway on enp3s0f1.
```

## 8. Идентификация коммутатора HP 3500yl

Способ доступа:

```text
Serial console via PuTTY
9600 8N1
No flow control
```

Устройство:

```text
HP J8693A Switch 3500yl-48G
Software revision K.15.10.0003
CLI prompt: HP-3500yl-48G#
```

## 9. Текущая конфигурация коммутатора HP

Использованная команда:

```text
show config
```

Наблюдаемое:

```text
hostname "HP-3500yl-48G"
module 1 type j86yya
module 2 type j86xxa
snmp-server community "public" unrestricted

vlan 1
   name "DEFAULT_VLAN"
   no untagged 1-48
   ip address dhcp-bootp
   exit

vlan 10
   name "PXE"
   untagged 1-48
   ip address 10.10.0.254 255.255.255.0
   exit
```

Интерпретация:

```text
All access ports 1-48 are untagged in VLAN 10.
VLAN 10 is named PXE.
The switch management IP is 10.10.0.254/24.
VLAN 1 exists but has no untagged ports.
```

Важный вывод:

```text
This switch was likely intentionally configured as a PXE/install network.
It should not be erased blindly.
```

## 10. Состояние VLAN коммутатора HP

Использованная команда:

```text
show vlan
```

Наблюдаемые VLAN:

```text
1  DEFAULT_VLAN
10 PXE
```

Management VLAN:

```text
not explicitly set
```

## 11. Состояние IP коммутатора HP

Использованная команда:

```text
show ip
```

Наблюдаемое:

```text
IP Routing: Disabled
DEFAULT_VLAN: DHCP/Bootp
PXE: Manual 10.10.0.254 255.255.255.0
```

Интерпретация:

```text
The switch is not routing.
The switch is L2 for traffic and has management IP on VLAN 10.
10.10.0.254 is not a real gateway unless routing is enabled.
```

## 12. Состояние STP и транков коммутатора HP

Использованные команды:

```text
show trunks
show spanning-tree
```

Наблюдаемое:

```text
No trunks configured.
STP Enabled: No.
```

Риск:

```text
Avoid physical loops.
With STP disabled, a loop can break the network.
```

## 13. Состояние портов коммутатора HP

После включения старых серверов ASUS активными портами были:

```text
Port 1  Up 1000FDx
Port 3  Up 1000FDx
Port 5  Up 100FDx
Port 25 Up 100FDx
Port 27 Up 1000FDx
```

Известное соответствие:

```text
Port 1  -> old ASUS 10.10.0.1
Port 3  -> old ASUS asking DHCP
Port 5  -> old ASUS, IP not confirmed
Port 25 -> head01 LAN2
Port 27 -> head01 IPMI when connected
```

## 14. Таблица MAC коммутатора HP

Использованная команда:

```text
show mac-address
```

Наблюдалось ранее с подключённым IPMI:

```text
ac1f6b-4ccea0 27 10
ac1f6b-4cd743 25 10
```

Наблюдалось после включения серверов ASUS и отключения IPMI:

```text
20cf30-7252ae 1  10
20cf30-7c98f2 5  10
ac1f6b-4cd743 25 10
c86000-391efb 3  10
```

Интерпретация:

```text
The HP switch sees old ASUS machines on ports 1, 3, and 5.
The HP switch sees head01 LAN2 on port 25.
When connected, the HP switch sees head01 IPMI on port 27.
```

## 15. Тесты связности

### 15.1 head01 до коммутатора HP

Команда:

```bash
ping -c 4 10.10.0.254
```

Результат:

```text
4 packets transmitted, 4 received, 0% packet loss
```

Подтверждено:

```text
head01 LAN2 can reach HP switch management IP.
```

### 15.2 Сканирование сети

Команда:

```bash
nmap -sn 10.10.0.0/24
```

С включённым ASUS наблюдалось:

```text
10.10.0.1    up
10.10.0.101  up
10.10.0.254  up
```

Интерпретация:

```text
10.10.0.1 is an old ASUS server.
10.10.0.101 is head01 LAN2.
10.10.0.254 is HP switch.
```

## 16. Старый сервер ASUS по адресу 10.10.0.1

MAC:

```text
20:cf:30:72:52:ae
```

Производитель:

```text
ASUSTek Computer
```

Порт коммутатора:

```text
1
```

IP:

```text
10.10.0.1
```

Сканирование сервисов:

```bash
nmap -sV 10.10.0.1
```

Наблюдаемое:

```text
22/tcp open ssh  OpenSSH 8.7
80/tcp open http Apache httpd 2.4.62 (AlmaLinux)
```

Полное сканирование TCP:

```bash
sudo nmap -p- --min-rate 5000 10.10.0.1
```

Наблюдаемое:

```text
22/tcp open ssh
80/tcp open http
```

Проверка HTTP:

```bash
curl -I http://10.10.0.1
curl http://10.10.0.1
```

Наблюдаемое:

```text
Apache default AlmaLinux test page
```

Интерпретация:

```text
10.10.0.1 is an AlmaLinux server.
It has SSH and Apache.
It does not expose obvious PXE content at HTTP root.
It is not currently confirmed as an active PXE server.
```

## 17. Проверки PXE/DHCP/TFTP

Команда:

```bash
sudo nmap -sU -p 67,69,4011 10.10.0.1
```

Наблюдаемое:

```text
67/udp   closed dhcps
69/udp   closed tftp
4011/udp closed altserviceboot
```

Интерпретация:

```text
10.10.0.1 is not currently listening as DHCP server.
10.10.0.1 is not currently listening as TFTP server.
10.10.0.1 is not currently listening as PXE proxyDHCP.
```

Команда на head01:

```bash
sudo ss -lunp | grep -E ':67|:69|:4011'
```

Наблюдаемое:

```text
no output
```

Интерпретация:

```text
head01 is not currently running DHCP/TFTP/PXE services.
```

## 18. Наблюдение DHCP-трафика

Команда:

```bash
sudo tcpdump -ni enp3s0f1 'port 67 or port 68 or arp'
```

Наблюдалось от IPMI узла head01:

```text
DHCP Request from ac:1f:6b:4c:ce:a0
```

Интерпретация:

```text
head01 IPMI is asking for DHCP.
No DHCP server replies.
```

Наблюдалось от ASUS на порту 3:

```text
DHCP Request from c8:60:00:39:1e:fb
```

Интерпретация:

```text
ASUS on port 3 is asking for DHCP.
No DHCP server replies.
```

Главный вывод:

```text
There is no active DHCP server in VLAN 10 at the moment.
```

## 19. Текущие технические выводы

Подтверждённые факты:

```text
head01 is connected to two networks:
- enp3s0f0 -> temporary normal LAN / router / internet (192.168.31.136/24)
- enp3s0f1 -> HP switch VLAN 10 / 10.10.0.0/24 (10.10.0.101)

HP 3500yl is configured as VLAN 10 PXE switch.
All ports 1-48 are currently untagged VLAN 10.
The switch management IP is 10.10.0.254.
Old ASUS 10.10.0.1 is alive, runs AlmaLinux, SSH, Apache.
No active DHCP/TFTP/PXE server was found.
ASUS on port 3 and head01 IPMI ask for DHCP but receive no reply.

Tailscale installed and running — head01 reachable via 100.93.200.94 regardless of physical network.
head01 IPMI moved from port 27 to port 26.
```

Операционный вывод:

```text
The old PXE infrastructure is incomplete or inactive.
The new infrastructure should be built around head01.
Remote access via Tailscale is confirmed and stable.
NAT/DHCP setup deferred until head01 moves to final server room location.
```

## 20. Будущая планируемая топология

Пользователь не планирует оставлять роутер напрямую подключённым к LAN1 узла head01.

Предпочтительная будущая топология:

```text
router / upstream
  |
  v
main switch or network switch layer
  |
  +-- head01 LAN1
  +-- Supermicro nodes normal LAN
  +-- user/admin access network
  +-- optional internet/uplink network

HP 3500yl or another managed switch
  |
  +-- install/PXE VLAN
  +-- IPMI VLAN
  +-- cluster VLAN
```

Возможный план VLAN:

```text
VLAN 10 - install/PXE network
VLAN 20 - cluster LAN / compute / SSH / Proxmox or Slurm
VLAN 30 - IPMI/BMC management
VLAN 40 - user/services network, if needed
```

Текущая временная топология:

```text
router -> head01 LAN1
HP switch VLAN 10 -> head01 LAN2
```

Будущая топология должна заменить это на:

```text
router -> switch -> head01 and other infrastructure
```

## 21. Что пока нельзя менять

Не запускать на коммутаторе HP:

```text
erase startup-config
reload
```

Не удалять вслепую:

```text
vlan 10
```

Не запускать DHCP на:

```text
enp3s0f0
```

Не запускать DHCP глобально на всех интерфейсах.

Если DHCP/PXE развёртывается на head01, он должен привязываться только к:

```text
enp3s0f1
```

пока не согласован финальный дизайн VLAN.

## 22. Недостающая инвентаризация head01

Следующие факты ещё не собраны и должны быть добавлены, чтобы сделать это полноценным паспортом.

### 22.1 ОС и ядро

Статус: **подтверждено**

```text
OS:               Ubuntu 24.04.4 LTS (Noble Numbat)
Kernel:           Linux 6.8.0-124-generic (May 2026)
Architecture:     x86-64
Hostname:         head01
Chassis:          server
Machine ID:       6121f6527daa48cc8f150ed332fb8125
Hardware Vendor:  Supermicro
Hardware Model:   X10DRI-T  ← исправлено 2026-07-01, см. примечание ниже (10GbE, не 1GbE)
Firmware:         3.0a (2018-02-06, возраст ~8 лет)
```

Замечание по прошивке:

```text
BIOS 2018 года — устаревший.
Обновление BIOS на Supermicro выполняется через IPMI (web или ipmitool).
Не критично для работы, но стоит обновить при удобном случае.
```

### 22.2 CPU, память, плата

Статус: **подтверждено**

CPU:

```text
Model:            Intel Xeon E5-2620 v4 @ 2.10GHz
Сокеты:           2 (dual socket)
Ядер на сокет:    8
Потоков на ядро:  2 (HyperThreading)
Итого CPU:        32 логических
NUMA node0:       CPU 0-7, 16-23  (Socket 1)
NUMA node1:       CPU 8-15, 24-31 (Socket 2)
```

Память:

```text
Итого:            512 GB DDR4 ECC
Планок:           16 × 32 GB
Слоты:            все заняты (P1: DIMMA1-DIMMD2, P2: DIMME1-DIMMH2)
Rated speed:      2667 MT/s
Configured speed: 2133 MT/s  ← E5-2620 v4 максимум, норма
ECC:              Multi-bit ECC  ✓
```

Замечание по памяти:

```text
Планки 2667 MT/s работают на 2133 MT/s — не баг.
E5-2620 v4 поддерживает максимум 2133 MT/s.
Планки быстрее процессора, работают на его максимуме.
```

Плата:

```text
Model:     Supermicro X10DRI-T  ← исправлено 2026-07-01 (было ошибочно записано как X10DRi)
NIC:       2× 10GbE Intel X540-AT2 встроены (nic0/nic1), подтверждено dmidecode+lspci
Chipset:   Intel C612
```

**Статус 2026-07-01:** запись ниже про «1GbE встроенный, нужна отдельная PCIe-карта под 10GbE» была ошибочной — при установке Proxmox на `pve01` подтверждены штатные встроенные 10GbE. Отдельная PCIe-карта под 10GbE не нужна (актуально и для потенциального возврата к Ceph, см. `storage_decision_zfs_replication.md`).

### 22.3 Диски и файловые системы

Статус: **подтверждено**

Физические диски:

```text
sda   894.3 GB   Micron 5200 MTFD   ← enterprise SATA SSD, power loss protection
sdb   894.3 GB   Micron 5200 MTFD   ← enterprise SATA SSD, power loss protection
```

Разметка sda (OS):

```text
sda1    1 GB   vfat   /boot/efi
sda2    2 GB   ext4   /boot
sda3  891 GB   LVM    ubuntu-vg → ubuntu-lv → /
```

Разметка sdb (данные):

```text
sdb1  894 GB   ext4   /data   ← пустой, owned ultron, готов к использованию
```

Точки монтирования:

```text
/          877 GB   ext4 LVM   (12 GB занято, 829 GB свободно)
/data      880 GB   ext4       (пустой, 835 GB свободно)
/boot        2 GB   ext4       (105 MB занято)
/boot/efi    1 GB   vfat       (6 MB занято)
```

Замечание:

```text
/data пустой и принадлежит ultron — подготовлен под данные кластера.
Рекомендуется использовать /data для хранилища кластера (/data/cluster).
smartmontools запущен — мониторинг здоровья дисков активен.
```

### 22.4 Детали сети

Выполнить:

```bash
ip -br a
ip route
resolvectl status
networkctl status
ls /etc/netplan
sudo cat /etc/netplan/*.yaml
```

### 22.5 Установленные пакеты и сервисы

Статус: **подтверждено**

Запущенные сервисы:

```text
ssh.service                ✓  OpenSSH 9.6p1
tailscaled.service         ✓  Tailscale 1.98.4
smartmontools.service      ✓  мониторинг дисков
rsyslog.service            ✓  системные логи
cron.service               ✓
systemd-networkd.service   ✓  сетевое управление
unattended-upgrades        ✓  автообновления
```

Отключено в ходе настройки:

```text
ModemManager.service  ← отключён (не нужен на сервере)
                        sudo systemctl disable --now ModemManager
```

Установлены нужные инструменты:

```text
tailscale    1.98.4   ✓
ipmitool     1.8.19   ✓
openssh      9.6p1    ✓
nmap         7.94     ✓
tcpdump      4.99.4   ✓
python3      3.12.3   ✓
smartmontools          ✓
```

Не установлено — понадобится:

```text
ansible   ← управление нодами
dnsmasq   ← DHCP/PXE после переезда в серверную
docker    ← если понадобится
```

Интересное — уже установлено:

```text
python3-boto3   ← AWS SDK, сервер использовался с AWS/S3 ранее
```

### 22.6 SSH и удалённый доступ

Статус: **подтверждено**

```text
Port:                   22 (default)
PermitRootLogin:        prohibit-password (default) ← root только по ключу
PasswordAuthentication: yes (default)  ← ВНИМАНИЕ: риск при выходе наружу
PubkeyAuthentication:   yes (default)
```

Замечание по безопасности:

```text
PasswordAuthentication yes — Ubuntu 24.04 default.
При выходе сервера в публичную сеть стоит выключить:
  PasswordAuthentication no  в /etc/ssh/sshd_config
Предварительно убедиться что SSH-ключ добавлен в ~/.ssh/authorized_keys.
Пока сервер за NAT/Tailscale — не критично.
```

Доступ:

```text
Локально:         ssh ultron@10.10.0.101  (через VLAN 10)
Через Tailscale:  ssh ultron@100.93.200.94  (из любой сети)
```

IPMI web-доступ через SSH tunnel:

```bash
# С десктопа — поднять туннель
ssh -L 8443:10.10.0.2:443 ultron@100.93.200.94 -N

# Открыть в браузере
https://localhost:8443
# Логин: ultron / пароль IPMI
```

SSH config на десктопе (~/.ssh/config):

```text
Host head01
    HostName 100.93.200.94
    User ultron
    LocalForward 8443 10.10.0.2:443
```

### 22.7 Tailscale

Статус: **подтверждено, установлено и работает**

```text
Статус:           installed, active (running), enabled
Tailscale IP:     100.93.200.94
Аккаунт:          itsyourdecide@
Tailnet:          личный (не университетский knu.ua)
Автозапуск:       systemd enabled — поднимается после ребута
Режим:            DERP relay (прямой P2P пока не установлен — NAT на временном роутере)
```

Устройства в tailnet:

```text
head01            100.93.200.94   linux    online
desktop-4md6f5p   100.105.80.15   windows  online
```

Замечание:

```text
Ранее head01 был авторизован под vinnikivan@knu.ua (корпоративный tailnet КНУ).
Там у пользователя не было прав администратора — управлял IT КНУ.
Выполнен tailscale logout и повторная авторизация под личным аккаунтом itsyourdecide@.
Теперь пользователь — полный admin своего tailnet.
```

Важное замечание по UFW:

```text
UFW по умолчанию блокировал входящий UDP 41641 на enp3s0f0.
Это порт WireGuard/Tailscale — без него Tailscale не устанавливает соединение.
Tailscale-пакеты приходят на физический интерфейс enp3s0f0, а не на tailscale0.
Правило на tailscale0 alone недостаточно.
Решение: sudo ufw allow 41641/udp
```

Доступ к admin-панели:

```text
https://login.tailscale.com/admin  под itsyourdecide@
```

SSH через Tailscale (независимо от физической сети):

```bash
ssh ultron@100.93.200.94
```

### 22.8 Фаервол

Статус: **подтверждено**

```text
UFW status:   active
Logging:      on (low)
Default:      deny (incoming), allow (outgoing), disabled (routed)
```

Открытые правила:

```text
22/tcp        ALLOW IN  Anywhere       ← SSH
41641/udp     ALLOW IN  Anywhere       ← Tailscale/WireGuard (критично!)
tailscale0    ALLOW IN  Anywhere       ← весь трафик внутри Tailscale
```

Важное замечание:

```text
41641/udp — обязательное правило.
Без него Tailscale не устанавливает соединение даже если tailscale0 разрешён.
WireGuard-пакеты приходят на enp3s0f0 до декапсуляции в tailscale0.
```

Выполнить для проверки:

```bash
sudo ufw status verbose
```

### 22.9 IPMI из ОС

Статус: **подтверждено, настроено**

```text
IPMI channel:     1
IPMI IP:          10.10.0.2 (static)
IPMI Subnet:      255.255.255.0
IPMI Gateway:     10.10.0.101 (head01 LAN2)
IPMI MAC:         ac:1f:6b:4c:ce:a0
HP switch port:   26
```

Пользователи IPMI:

```text
ID 1   (anonymous)  —              Callin only, без IPMI доступа
ID 2   aACWFE       ADMINISTRATOR  пароль рандомизирован, войти не может
ID 3   ultron       ADMINISTRATOR  активен, основной пользователь  ✓
ID 4-9 (разные)     NO ACCESS      неактивны
ID 10  sysrescue    NO ACCESS      пароль рандомизирован, заблокирован
```

Замечание:

```text
Сервер использовался ранее — нестандартные пользователи (aACWFE, sysrescue и др.).
ipmitool user disable не сработал на этом BMC (известный баг Supermicro).
Решение: пароли рандомизированы через openssl rand -hex 16.
aACWFE технически ADMINISTRATOR но войти не может — пароль неизвестен никому.
```

Проверка доступа:

```bash
sudo ipmitool -I lanplus -H 10.10.0.2 -U ultron -P ПАРОЛЬ chassis status
```

Результат:

```text
System Power         : on
Power Overload       : false
Drive Fault          : false
Cooling/Fan Fault    : false
```

Инструмент:

```bash
sudo apt install ipmitool
```

### 22.10 Важные каталоги

Статус: **подтверждено**

```text
/srv        пустой  (root:root)      ← под структуру кластера
/data       пустой  (ultron:ultron)  ← 880 GB, под данные кластера
/home/ultron  стандартный home, .ssh/ существует
```

Замечание по /data:

```text
/data уже принадлежит ultron и примонтирован — кто-то подготовил под данные.
Рекомендуется использовать /data/cluster вместо /srv/cluster
из-за размера: /data 880 GB vs / 877 GB.
```

Предлагаемая структура:

```text
/srv/cluster/           ← symlink или основная точка
/data/cluster/
  docs/
  inventory/
  ansible/
  pxe/
  autoinstall/
  scripts/
  backups/
```

Создать после переезда в серверную:

```bash
sudo mkdir -p /data/cluster/{docs,inventory,ansible,pxe,autoinstall,scripts,backups}
sudo chown -R ultron:ultron /data/cluster
```

## 23. Предлагаемая структура ролей head01

Рекомендуемые будущие роли:

```text
head01
- control node
- documentation source
- Ansible controller
- PXE/autoinstall server
- optional DHCP server for install network only
- optional monitoring node
- optional Tailscale entry point
```

Не рекомендуется:

```text
Do not make old ASUS the main control node.
Do not mix old ASUS legacy setup with new Supermicro production without documenting it.
```

## 24. Следующий рекомендуемый технический шаг

**Выполнено:**

```text
✓  Tailscale установлен, работает, автозапуск
✓  UFW настроен (SSH + 41641/udp)
✓  IPMI настроен: 10.10.0.2, пользователь ultron
✓  enp3s0f1 закреплён в netplan: 10.10.0.101
✓  cloud-init отключён для сети
✓  ModemManager отключён
✓  Инвентаризация OS, CPU, RAM, дисков, сервисов, каталогов завершена
✓  IPMI web-доступ через SSH tunnel задокументирован
```

**Ещё не проверено:**

```text
□  SSH authorized_keys — есть ли ключ, отключить PasswordAuthentication
□  /data/cluster структура — создать после переезда
```

**После переезда в серверную:**

```text
1. Обновить netplan под новую сеть (enp3s0f0)
2. Включить ip_forward
3. Настроить iptables MASQUERADE
4. Установить dnsmasq (DHCP только на enp3s0f1)
5. Установить ansible
6. Создать /data/cluster структуру
7. PXE / autoinstall для нод
```

Правило безопасности:

```text
Any DHCP service must be explicitly bound to enp3s0f1 only.
```

## 25. Краткая фактическая сводка

Текущая фактическая сводка:

```text
ЖЕЛЕЗО:
  Board:   Supermicro X10DRI-T (2× 10GbE Intel X540-AT2 встроены, исправлено 2026-07-01)
  CPU:     2× Intel Xeon E5-2620 v4, итого 32 логических CPU
  RAM:     512 GB DDR4 ECC (16 × 32 GB, все слоты заняты)
  Disk0:   894 GB Micron 5200 SSD → OS (LVM, / 877 GB)
  Disk1:   894 GB Micron 5200 SSD → /data (880 GB, пустой)
  BIOS:    3.0a (2018-02-06)

ОС:
  Ubuntu 24.04.4 LTS, kernel 6.8.0-124-generic
  Пользователь: ultron

СЕТЬ:
  enp3s0f0   192.168.31.136   DHCP  (временный, сменится при переезде)
  enp3s0f1   10.10.0.101      static netplan  ✓ постоянный
  IPMI       10.10.0.2        static BMC      ✓ постоянный
  Tailscale  100.93.200.94    personal tailnet ✓ постоянный навсегда

ДОСТУП:
  SSH:   ssh ultron@100.93.200.94
  IPMI:  ssh -L 8443:10.10.0.2:443 ultron@100.93.200.94 -N → https://localhost:8443
  UFW:   active, 22/tcp + 41641/udp открыты

КОММУТАТОР:
  HP 3500yl-48G, все порты VLAN 10 (PXE), IP 10.10.0.254
  STP отключён — избегать физических петель
  ASUS 10.10.0.1 — жив, AlmaLinux, SSH+Apache
  Нет активного DHCP/PXE сервера в VLAN 10

АРХИТЕКТУРНОЕ РЕШЕНИЕ:
  head01 = NAT-шлюз для нод (Вариант B)
  Один кабель на ноду, без trunk
  NAT/DHCP настраивается после переезда в серверную
```

Стабильные IP (не изменятся при переезде):

```text
enp3s0f1   10.10.0.101    ✓  netplan static
IPMI       10.10.0.2      ✓  BMC static
Tailscale  100.93.200.94  ✓  permanent
```

Временные IP (изменятся при переезде в серверную):

```text
enp3s0f0   192.168.31.136   DHCP от текущего роутера
```

---

*Паспорт обновлён до v0.5 — инвентаризация head01 завершена.*
