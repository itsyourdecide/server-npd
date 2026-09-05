# Чеклист инвентаризации кластера

- Статус: current reusable runbook
- Последняя редакция: 2026-09-05
- Источник истины для: процедуры сбора hardware facts, но не для самих фактов

Дата проверки: __________
Исполнители: __________

Цель: собрать воспроизводимые hardware facts до переустановки, закупки,
подключения storage или ввода узла в production. Не стирать существующую ОС и
данные до отдельного подтверждённого backup/erase decision.

## 1. Фотографии и маркировка

- [ ] Передняя и задняя панели трёх Supermicro.
- [ ] Серийный номер, модель шасси и материнской платы.
- [ ] Все PCIe-карты и их внешние разъёмы.
- [ ] Маркировка JBOD и SAS I/O-модулей.
- [ ] Маркировка внешних SAS-кабелей.
- [ ] Задние модули обоих HP 3500yl.
- [ ] Общий вид стоек, розеток/PDU и помещения.

Не публиковать фотографии с паролями, QR-кодами доступа или наклейками recovery key.

## 2. Supermicro — выполнить на каждом из трёх узлов

Имя узла: __________  Серийный номер: __________

```bash
sudo dmidecode -t system -t baseboard -t bios
lscpu
free -h
sudo dmidecode -t memory
lsblk -e7 -o NAME,SIZE,MODEL,SERIAL,ROTA,TYPE,FSTYPE,MOUNTPOINTS
sudo lspci -nnk
ip -br link
sudo ethtool <interface>
sudo ipmitool mc info
sudo ipmitool lan print 1
sudo ipmitool sensor list
```

- [ ] 2 CPU и ожидаемое число ядер.
- [ ] Объём RAM и ошибки ECC/IPMI SEL.
- [ ] Два SSD и их точные модели.
- [ ] Две OS NIC + отдельный BMC.
- [ ] Модель SAS HBA и режим HBA/JBOD, не hardware RAID.
- [ ] Модель быстрой NIC/InfiniBand, если есть.
- [ ] Версии BIOS и BMC.
- [ ] VT-x/VT-d включены.

Очистить старые события только после сохранения:

```bash
sudo ipmitool sel elist > ipmi-sel-<hostname>-before.txt
```

## 3. SSD/HDD health

Для каждого локального SSD:

```bash
sudo smartctl -x /dev/sdX
```

Записать:

- [ ] SMART overall health.
- [ ] Power-on hours.
- [ ] Reallocated/pending/uncorrectable sectors.
- [ ] Wear indicator для SSD.
- [ ] Ошибки интерфейса/CRC.

Диск с pending/uncorrectable sectors не использовать в production storage до
отдельной проверки.

## 4. JBOD и SAS

Проверять по одной полке на узел.

- [ ] Точная модель полки.
- [ ] Один или два I/O-модуля.
- [ ] Тип внешнего SAS-разъёма.
- [ ] Есть ли два независимых PSU.
- [ ] Все вентиляторы исправны.
- [ ] HBA видит каждый диск отдельно.
- [ ] Не включён hardware RAID.
- [ ] Serial дисков стабилен после reboot.
- [ ] Доступны enclosure/slot identifiers.
- [ ] Есть ли на IO-модуле полки отдельный порт **Mgmt** (Ethernet) для сетевого мониторинга самой полки (PSU/вентиляторы/диски) независимо от хоста — найден на первой полке (Promise 4U-SAS-24-12G), подписан `Mgmt`.
- [ ] Есть ли **serial-консольный** порт на IO-модуле (обозначается иконкой терминала, параметры `115200 8 N 1`) — найден на первой полке, аналогичен доступу к HP-свитчу через PuTTY. Стоит завести доступ так же, как к свитчу, для диагностики полки без захода через ОС узла.

Команды после подключения:

```bash
sudo dmesg -T | grep -Ei 'sas|scsi|enclos|error|reset'
lsblk -S -o NAME,HCTL,TRAN,VENDOR,MODEL,REV,SERIAL
sudo lsscsi -g
sudo sg_map -i
sudo multipath -ll
```

Если `lsscsi`, `sg3_utils` или `multipath-tools` отсутствуют — сначала только зафиксировать это, не менять конфигурацию вслепую.

Для пилота выбрать 3–4 заведомо исправных HDD на каждую полку и сохранить таблицу:

| Host | Enclosure | Slot | Device | Serial | Size | SMART | Hours |
|---|---|---:|---|---|---:|---|---:|
| | | | | | | | |

## 5. HP 3500yl — оба коммутатора

Сохранить вывод в отдельные текстовые файлы:

```text
show system
show version
show modules
show interfaces brief
show interfaces transceiver
show trunks
show lacp
show vlan
show spanning-tree
show config
show logging
```

Проверить:

- [ ] Модель каждого 10GbE-модуля.
- [ ] Тип портов: X2, CX4 или SFP+.
- [ ] Наличие совместимых кабелей/трансиверов.
- [ ] Все используемые 1GbE-порты согласуются на 1000FDx.
- [ ] Все неожиданные согласования на 100Mb/s объяснены и устранены до
      production.
- [ ] Версия firmware.
- [ ] SNMP community `public unrestricted` будет удалена перед production.
- [ ] STP/RSTP будет включён до соединения коммутаторов несколькими линками.

Не выполнять `erase startup-config` и не удалять текущий VLAN 10 до сохранения конфигурации.

## 6. ASUS

Для каждого шасси записать:

| Chassis | Model | Nodes | RS720/RS724 | IB QDR | BMC | PSU status |
|---|---|---:|---|---|---|---|
| | | | | | | |

Проверить хотя бы один узел каждого типа:

```bash
lscpu
free -h
lspci -nnk
ip -br link
sudo ipmitool mc info
sudo ipmitool sensor list
```

- [ ] Количество RS724QA со встроенным QDR.
- [ ] Количество RS720QA без QDR.
- [ ] Наличие InfiniBand-коммутатора и QSFP-кабелей.
- [ ] Возможность PXE boot.
- [ ] Время полного POST/boot.
- [ ] Потребление одного шасси idle/load.
- [ ] Поддержка Shared LAN/NC-SI в BIOS/BMC или обязательный dedicated-порт.
- [ ] Если Shared LAN поддерживается — умеет ли BMC тегировать VLAN.
- [ ] Повторить проверку на нескольких узлах, чтобы исключить единичную
  аппаратную особенность.

## 7. Склад

Посчитать и сфотографировать:

- [ ] InfiniBand-коммутаторы.
- [ ] QSFP/CX4/SFP+/X2 кабели и оптика.
- [ ] 10/25/40GbE NIC.
- [ ] SAS HBA.
- [ ] Внешние SAS-кабели.
- [ ] Запасные SSD/HDD.
- [ ] PDU/UPS.
- [ ] Сетевые датчики температуры.
- [ ] Запасные PSU и вентиляторы.

## 8. Помещение и uplink

- [ ] Размеры помещения.
- [ ] Возможность внешнего блока/вывода тепла.
- [ ] Существующая вентиляция.
- [ ] Электрический ввод, фазы, автоматы и заземление.
- [ ] Модель и число PDU/UPS.
- [ ] Uplink: тип, скорость, VLAN.
- [ ] Публичный IPv4/IPv6, NAT или необходимость VPS-туннеля.
- [ ] Возможность получить университетский DNS-поддомен.
- [ ] Возможность LDAP/AD интеграции.
- [ ] Наличие отдельного backup-хранилища.

## 9. Измерения питания

Измерить реальным PDU/ваттметром:

| Оборудование | Off/standby | Idle | Full load | Примечание |
|---|---:|---:|---:|---|
| Supermicro | | | | |
| JBOD без дисков | | | | |
| JBOD с дисками | | | | |
| ASUS chassis | | | | |
| HP 3500yl | | | | |

Не выбирать кондиционер только по мощности блоков питания.

## 10. Результат инвентаризации

После выезда должны быть известны:

- можно ли собрать три PVE с ZFS mirror;
- можно ли подключить три независимые JBOD;
- доступна ли сеть для выбранной storage architecture;
- сколько исправных дисков можно безопасно использовать;
- какие закупки действительно обязательны;
- безопасная мощность первого этапа.

Результаты заносятся в `docs/inventory/hardware.md`; сырые выводы и фотографии
без секретов — в датированный каталог `evidence/` после его создания.
