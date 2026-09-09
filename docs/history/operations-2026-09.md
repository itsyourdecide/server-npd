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
