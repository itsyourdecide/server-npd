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
