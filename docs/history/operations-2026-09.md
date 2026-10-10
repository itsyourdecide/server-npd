# Журнал операций — сентябрь 2026

- Статус: historical
- Последняя проверка структуры: 2026-09-09
- Назначение: неизменяемая хронология выполненных работ за 2026-09
- Источник истины для: факта выполнения операции на указанную дату

### 2026-09-09 — vpn-npd/fw01 — поднят параллельный WireGuard site tunnel

Причина: начать безопасную миграцию внешнего Azure edge с legacy TCP relay на
routed tunnel, не отключая действующий пользовательский и fallback access.

Изменено:

- владелец создал резервные копии OPNsense и legacy VPN configuration вне Git;
- на Azure `vpn-npd` создан enabled interface `wg-site`:
  `10.255.82.1/30`, UDP `51822`;
- в Azure NSG добавлен inbound allow UDP `51822` от `Any`, priority `340`;
- на `fw01`/OPNsense создана WireGuard instance `wg-site`:
  `10.255.82.2/30`, local UDP `51823`;
- OPNsense peer направлен на `20.215.200.4:51822` и использует
  `PersistentKeepalive = 25`;
- `AllowedIPs` пока содержат только адреса tunnel endpoints `/32`;
- private keys и полный OPNsense export не добавлялись в repository.

Диагностика:

- raw UDP test с Windows и `pve02` достигал Azure UDP `51822`;
- первоначальные WireGuard packets `192.168.31.90:51822 ->
  20.215.200.4:51822` были видны на WAN OPNsense, `tap100i7` и physical
  `nic0` узла `pve02`, но не наблюдались на Azure;
- после смены local listen port OPNsense на UDP `51823` tunnel установился;
- наблюдение указывает на NAT state/port handling upstream, но не определяет
  конкретный router или firewall как причину.

Проверка:

- Azure `wg show wg-site` показал learned endpoint OPNsense;
- `latest handshake` присутствовал;
- двусторонние counters: `1.23 KiB received`, `368 B sent` в момент проверки;
- legacy `wg0`, TCP/10000 и Tailscale продолжили работать без cutover.

Результат: encrypted transfer network Azure ↔ OPNsense работает. Routing во
внутренние VLAN, assigned firewall interface/rules, `wg-admin`, public HTTPS и
перевод SSH на новый tunnel ещё не выполнялись.

Evidence: live CLI output и GUI screenshots предоставлены владельцем в ходе
операции; raw artifacts с network identifiers и key configuration в Git не
сохранялись.

### 2026-09-09 — vpn-npd/fw01 — проверен routed TCP path до portal-dev01

Причина: до развёртывания reverse proxy проверить data plane через `wg-site`
на одном destination, не открывая всю VLAN40.

Изменено:

- WireGuard device назначен отдельным OPNsense interface `WG_SITE`;
- в Azure peer `AllowedIPs` добавлен `10.10.40.107/32`;
- Linux route на `vpn-npd` направляет `10.10.40.107` через `wg-site` с source
  `10.255.82.1`;
- на `WG_SITE` добавлено временное pass rule от `10.255.82.1` к
  `10.10.40.107` для TCP с любым destination port.

Проверка:

- ping `10.255.82.2 -> 10.255.82.1`: 14/14 packets, 0% loss, average около
  31 ms;
- route lookup на Azure: `10.10.40.107 dev wg-site src 10.255.82.1`;
- WireGuard handshake оставался активным;
- ping и TCP/22 `vpn-npd -> portal-dev01` прошли end-to-end.

Результат: Azure достигает одной private VM через OPNsense; public reverse
proxy ещё не развёрнут. Временное `any TCP` rule должно быть заменено точными
application и admin rules после определения upstream port и создания
`wg-admin`.

Evidence: live CLI results подтверждены владельцем; private keys и raw configs
в Git не добавлялись.

### 2026-09-21 — Proxmox/Portal — создан ограниченный API service account

Причина: подготовить operation worker Portal к управлению пользовательскими
VM без использования root credentials или глобальной administrative role.

Изменено:

- создан `portal-worker@pve`;
- создан token `portal-worker@pve!portal` с `privsep=1`;
- создан resource pool `npd-portal`;
- создана ограниченная роль `NPDPortalWorker`;
- user и token получили эту роль только на `/pool/npd-portal`;
- user и token получили `PVEDatastoreUser` только на
  `/storage/local-zfs`;
- на `/` оставлен только общий read-only доступ `PVEAuditor`;
- Portal настроен на HTTPS API `pve01:8006` с проверкой cluster CA;
- token secret сохранён вне Git в локальном `.env.worker` и в документацию не
  добавлялся.

Проверка:

- effective permissions token содержат `NPDPortalWorker` на pool и только
  `Datastore.AllocateSpace`/`Datastore.Audit` на `local-zfs`;
- `ProxmoxClient` получил version `9.2.3`;
- API вернул `pve01`, `pve02`, `pve03` со статусом `online`;
- TLS verification выполнена через `/etc/pve/pve-root-ca.pem`, скопированный
  по доверенному SSH-каналу;
- существующие VM не изменялись.

Результат: authentication, TLS и read-only API path подтверждены; write scope
ограничен pool Portal и выделением места на `local-zfs`. Реальное создание VM
ещё не включено: AlmaLinux cloud template и ACL исходного template не готовы.

Evidence: live `pveum` output и read-only API response проверены во время
операции; token secret и raw credential artifacts в Git не сохранялись.

### 2026-09-21 — Proxmox/Portal — создан template и проверен полный API lifecycle

Причина: собрать и проверить всё сервер-зависимое до разработки production
`HttpProxmoxAdapter` без постоянного доступа к кластеру.

Изменено:

- официальный AlmaLinux 9.8 Generic Cloud image проверен по GPG и SHA-256;
- на `pve02` создан защищённый template `9000`
  (`npd-almalinux-9-template`) на `local-zfs`;
- template настроен на Cloud-Init, qemu guest agent, VLAN 40 и явный DNS
  `10.10.40.1`/`internal`;
- user и token получили `PVETemplateUser` на `/vms/9000`;
- user и token получили `PVESDNUser` только на
  `/sdn/zones/localnetwork/vmbr0/40`;
- вне Git сохранены offline-документация PVE 9.2 и исходный подписанный образ;
- в Git добавлены обезличенные реальные API fixtures.

Проверка:

- token выполнил full clone, config update, disk resize, start и shutdown;
- UPID polling различил `running` и успешный `stopped`/`OK`;
- guest agent вернул адрес VLAN 40, SSH по Cloud-Init key прошёл;
- root XFS вырос до 30 GiB, интернет и DNS работали;
- чистый первый boot использовал только `10.10.40.1` и `search internal`;
- Cloud-Init выполнил обновление пакетов примерно за пять минут;
- delete с `purge=1` удалил VM и все её тома, pool снова стал пустым.

Выявлено:

- без точечного `SDN.Use` изменение tagged NIC возвращает `403`;
- `sshkeys` требует предварительного URL encoding в form body;
- resize возвращает отдельный UPID и требует polling;
- `qmstart` подтверждает запуск QEMU, но не готовность гостевой ОС;
- `destroy-unreferenced-disks=1` дал `no such logical volume pve/data`, поэтому
  в проверенном delete path используется только `purge=1`.

Результат: серверная сторона для первой версии `HttpProxmoxAdapter` проверена;
в resource pool не оставлено временных VM.

После завершения проверки API token был ротирован из-за появления прежнего
secret в локальном диагностическом выводе. Новый secret записан только в
игнорируемый `.env.worker`; все token ACL назначены заново и effective
permissions повторно проверены.
