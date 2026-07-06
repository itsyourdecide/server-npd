# Лабораторный Proof of Concept кластера

Версия: 1.0  
Дата: 01.07.2026  
Статус: план тестового стенда до переезда в серверную  
Связанные документы: `cluster_architecture_presentation.md`, `cluster_implementation_plan.md`, `cluster_inventory_checklist.md`

## 1. Цель

Собрать в лаборатории уменьшенную, но функционально полную модель будущей инфраструктуры на трёх Supermicro:

- Proxmox cluster и quorum;
- VLAN и trunk/access-порты;
- routing, firewall, NAT и DHCP;
- OPNsense как временный виртуальный router/firewall;
- изоляция Management, IPMI, VM, DMZ и compute;
- тестовый HTCondor;
- Ceph и HA после проверки SAS/10GbE;
- контролируемые испытания отказов.

Общий лабораторный router не перенастраивается. Стенд использует его только как внешний NAT/uplink.

## 2. Ограничения PoC

- OPNsense работает как VM, а не на отдельном firewall appliance.
- Присутствует двойной NAT.
- Один физический uplink в общий router остаётся точкой отказа.
- До ввода Ceph OPNsense VM хранится локально и не имеет автоматической HA.
- 1GbE допускается только для функциональных тестов, не для оценки production Ceph.
- В лаборатории одновременно доступны три из десяти Supermicro.

Эти ограничения приемлемы для PoC, но не переносятся в production без отдельного решения.

## 3. Физическая схема

```text
Internet
   |
Общий лабораторный router
   | обычный LAN, конфигурация не меняется
   |
Switch 1 port 1 — ACCESS VLAN 99
   |
   +===============================+
   | Switch 1 == tagged trunk == Switch 2
   +===============================+
          |                    |
       pve01 LAN1           pve01 LAN2
       pve02 LAN1           pve02 LAN2
       pve03 LAN1           pve03 LAN2
```

OPNsense VM работает на `pve01`, но её виртуальные NIC доступны через VLAN-aware bridge Proxmox.

## 4. VLAN лабораторного стенда

Эта таблица — **единый источник конкретных подсетей и шлюзов** для всего проекта (IP-план `10.10.<VLAN>.0/24` переносится в production как есть, кроме VLAN 99 — см. §12). Обзорные VLAN-таблицы в `cluster_architecture_presentation.md` §5.2 и `cluster_architecture_rationale.md` §10 ссылаются сюда за цифрами.

| VLAN | Сеть | Назначение | Gateway |
|---:|---|---|---|
| 10 | `10.10.10.0/24` | Proxmox/switch management | `10.10.10.1` |
| 20 | `10.10.20.0/24` | Corosync | отсутствует |
| 30 | `10.10.30.0/24` | IPMI/BMC | `10.10.30.1` |
| 40 | `10.10.40.0/24` | Private VM | `10.10.40.1` |
| 50 | `10.10.50.0/24` | DMZ | `10.10.50.1` |
| 60 | `10.10.60.0/24` | Ceph public/client, позднее | отсутствует |
| 61 | `10.10.61.0/24` | Ceph replication, позднее | отсутствует |
| 80 | `10.10.80.0/24` | HTCondor/PXE | `10.10.80.1` |
| 99 | DHCP лаборатории | Временный WAN OPNsense | общий router |

VLAN 99 существует только в лаборатории и удаляется после переноса на production WAN.

## 5. Адреса core-оборудования

```text
OPNsense Management gateway  10.10.10.1
Switch 1                     10.10.10.2
Switch 2                     10.10.10.3
pve01                        10.10.10.11
pve02                        10.10.10.12
pve03                        10.10.10.13

Corosync:
pve01                        10.10.20.11
pve02                        10.10.20.12
pve03                        10.10.20.13

IPMI:
pve01-bmc                    10.10.30.11
pve02-bmc                    10.10.30.12
pve03-bmc                    10.10.30.13
```

Имена и адреса фиксируются до создания Proxmox cluster и впоследствии не меняются без отдельного migration plan.

## 6. Порты коммутаторов для PoC

### Switch 1

| Порты | Устройство | Untagged | Tagged |
|---|---|---:|---|
| 1 | Общий лабораторный router | 99 | — |
| 2–3 | LACP `Trk1` к Switch 2 | — | 10, 20, 30, 40, 50, 80, 99 |
| 4 | `pve01 LAN1` | 10 | 20, 30, 40, 50, 80, 99 |
| 5 | `pve02 LAN1` | 10 | 20, 30, 40, 50, 80, 99 |
| 6 | `pve03 LAN1` | 10 | 20, 30, 40, 50, 80, 99 |
| 7 | `pve01 IPMI` | 30 | — |
| 8 | `pve03 IPMI` | 30 | — |

### Switch 2

| Порты | Устройство | Untagged | Tagged |
|---|---|---:|---|
| 1–2 | LACP `Trk1` к Switch 1 | — | 10, 20, 30, 40, 50, 80, 99 |
| 3 | `pve01 LAN2` | 10 | 20, 30, 40, 50, 80, 99 |
| 4 | `pve02 LAN2` | 10 | 20, 30, 40, 50, 80, 99 |
| 5 | `pve03 LAN2` | 10 | 20, 30, 40, 50, 80, 99 |
| 6 | `pve02 IPMI` | 30 | — |

Неиспользуемые порты выключаются. VLAN 60/61 не добавляются в 1GbE PoC до отдельного теста Ceph.

## 7. OPNsense VM

Начальные ресурсы:

```text
2–4 vCPU
4 GB RAM
20–32 GB disk
QEMU Guest Agent
Autostart enabled
```

Виртуальные NIC:

| OPNsense NIC | Proxmox VLAN tag | Роль |
|---|---:|---|
| `vtnet0` | 99 | WAN, DHCP от общего router |
| `vtnet1` | без тега | Management/native VLAN 10 |
| `vtnet2` | 30 | IPMI |
| `vtnet3` | 40 | Private VM |
| `vtnet4` | 50 | DMZ |
| `vtnet5` | 80 | HTCondor/PXE |

Corosync VLAN 20 и Ceph VLAN 60/61 к OPNsense не подключаются.

## 8. DHCP и DNS

- VLAN 10: статические адреса для инфраструктуры; DHCP не обязателен.
- VLAN 30: только статические/reserved BMC addresses.
- VLAN 40: DHCP, например `10.10.40.100–199`.
- VLAN 50: статические адреса публичных сервисов.
- VLAN 80: DHCP/PXE, например `10.10.80.100–220`.
- VLAN 99: WAN получает DHCP от общего router.

Локальные DNS-имена должны разрешаться одинаково на всех PVE до создания cluster.

## 9. Начальная firewall policy

Принцип: deny by default между VLAN, затем минимальные разрешения.

| Источник | Разрешено |
|---|---|
| Management VLAN 10 | Управление внутренними VLAN и исходящий интернет |
| IPMI VLAN 30 | Ответы администраторам; самостоятельный интернет запрещён |
| Private VM VLAN 40 | DNS, NTP, исходящий интернет; Management/IPMI запрещены |
| DMZ VLAN 50 | Исходящий интернет; доступ во внутренние сети только по явным правилам |
| HTCondor VLAN 80 | DNS, NTP, package repositories и необходимые scheduler/storage endpoints |
| WAN VLAN 99 | Все входящие запрещены, кроме явных port forwards |

Тестовые port forwards после создания сервисов:

```text
WAN:2222 -> bastion01:22
WAN:443  -> reverse-proxy01:443
```

Proxmox, Ceph и IPMI напрямую через WAN не публикуются.

## 10. Порядок сборки

1. Сохранить `show config` и inventory обоих HP.
2. Проверить три Supermicro, SSD, NIC, HBA, IPMI и firmware.
3. Сохранить конфигурацию Ubuntu `head01`.
4. Настроить VLAN и management IP коммутаторов через serial console.
5. Соединить switches двумя LACP links и проверить `show trunks`/`show lacp`.
6. Установить одинаковую версию Proxmox VE на три узла.
7. Настроить LAN1/LAN2, VLAN-aware bridge и постоянные адреса.
8. Проверить VLAN 10 и Corosync VLAN 20 до создания cluster.
9. Создать трёхузловой Proxmox cluster.
10. Создать VLAN 99 и подключить общий router к Switch 1 port 1.
11. Установить OPNsense VM и назначить интерфейсы.
12. Настроить gateways, DHCP, NAT и firewall.
13. Создать тестовые VM в VLAN 40, 50 и 80.
14. Проверить изоляцию и доступ в интернет.
15. Развернуть минимальный HTCondor PoC.
16. После проверки SAS и 10GbE добавить Ceph и HA tests.

## 11. Acceptance tests

### VLAN и firewall

- [ ] VM VLAN 40 получает интернет.
- [ ] VM VLAN 40 не видит Proxmox VLAN 10.
- [ ] VM VLAN 40 не видит IPMI VLAN 30.
- [ ] Administrator VLAN 10 видит IPMI VLAN 30.
- [ ] DMZ VLAN 50 не инициирует соединения в Management/IPMI.
- [ ] WAN открывает только явно опубликованные порты.
- [ ] Подмена IP внутри access VLAN не позволяет перейти в другой VLAN.

### Switch и PVE network

- [ ] Все production links согласованы на 1000FDx.
- [ ] Отключение одного member link `Trk1` не рвёт связь switches.
- [ ] Отключение активного PVE LAN вызывает переход на резервный link.
- [ ] После failover Management и Corosync остаются доступны.
- [ ] STP/MSTP включён, случайная петля не вызывает broadcast storm.

### Proxmox

- [ ] `pvecm status` показывает quorum 3/3.
- [ ] Выключение одного узла оставляет quorum 2/3.
- [ ] Вход в GUI возможен через каждый оставшийся узел.
- [ ] Test VM переносится между узлами.

### OPNsense

- [ ] WAN получает адрес лабораторной сети.
- [ ] Outbound NAT работает для VLAN 40/50/80.
- [ ] Остановка OPNsense ожидаемо прекращает routing, но не Corosync.
- [ ] Конфигурация OPNsense экспортируется и восстанавливается.

### HTCondor

- [ ] Submit node принимает тестовую задачу.
- [ ] Worker VM и bare-metal test worker видны в одном pool.
- [ ] Job не получает доступ к Management/IPMI.
- [ ] Проверены передача файлов, retry и fair-share basics.

### Ceph/HA — поздний этап

- [ ] Ceph public и replication не используют Corosync network.
- [ ] Replicated pool имеет `size=3`, `min_size=2`, failure domain `host`.
- [ ] Отказ одного OSD не теряет данные.
- [ ] Отказ одного PVE приводит к HA restart тестовой VM.
- [ ] Recovery не разрушает quorum и измерен по времени/нагрузке.

## 12. Что переносится в production

Переносятся:

- VLAN IDs и IP plan;
- PVE hostnames;
- Proxmox cluster;
- OPNsense firewall policy через export/import;
- VM/LXC templates;
- HTCondor configuration;
- monitoring и Ansible inventory.

Не переносится напрямую:

- VLAN 99;
- лабораторный WAN DHCP;
- двойной NAT;
- зависимость production gateway от одной локальной VM без HA;
- 1GbE Ceph test network.

## 13. Условие завершения PoC

PoC считается успешным только после документированного прохождения acceptance tests. Наличие работающего GUI или одного ping не считается проверкой архитектуры.
