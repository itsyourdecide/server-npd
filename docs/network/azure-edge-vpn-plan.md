# План внешнего Azure edge и WireGuard-доступа

Статус: draft
Дата создания: 2026-09-08
Последняя проверка исходного состояния: 2026-09-09
Назначение: спроектировать независимый внешний вход через `vpn-npd` и
безопасную миграцию с текущего TCP relay на routed WireGuard
Источник истины для: целевой схемы Azure edge/VPN и этапов её внедрения; не для
фактического состояния сети и не для приоритетов других работ

## Статус решения

Владелец подтвердил общее направление:

- `vpn-npd` в Azure становится единственной контролируемой внешней точкой;
- новый основной site-to-site WireGuard завершается внутри `fw01`/OPNsense;
- отдельный WireGuard-контур предоставляет административный доступ с ПК;
- публичный сайт и SSH пользователей принимаются на белом IP Azure;
- входящие порты и белый IP сети кафедры не используются;
- Tailscale и текущий WireGuard на `pve02` сохраняются только на время
  безопасной миграции и как возможный аварийный доступ.

Адреса, порты, перечень разрешённых VLAN и момент удаления старой схемы ниже
остаются предлагаемыми до явного подтверждения владельцем на соответствующем
этапе. Этот документ сам по себе не разрешает менять Azure, OPNsense или PVE.

## Зачем это нужно

Сеть кафедры предоставляет исходящий Internet, но её входящий NAT, firewall и
адресация не находятся под контролем владельца кластера. Внешний Azure server с
белым IP решает эту границу:

- внутренний endpoint сам поддерживает исходящий tunnel до Azure;
- пользователи обращаются только к контролируемому Azure IP/DNS;
- public HTTPS и SSH не зависят от port forwarding кафедры;
- внутренние адреса не публикуются напрямую;
- правила доступа остаются под контролем Azure edge и OPNsense.

Полной независимости от физического Internet кафедры быть не может: для tunnel
нужен исходящий IP connectivity и разрешённый UDP. Текущий WireGuard handshake
подтверждает, что такой исходящий путь существует. От входящих правил кафедры
целевая схема не зависит.

## Исходное состояние

Живая read-only проверка 2026-09-08 показала:

- `vpn-npd` — Ubuntu 24.04 в Azure, public IP `20.215.200.4`;
- `vpn-npd wg0` — `10.255.80.1/30`, UDP `51820`;
- `pve02 wg0` — `10.255.80.2/30`, handshake активен;
- у peers разрешены только адреса концов tunnel `/32`;
- `net.ipv4.ip_forward = 0` на `vpn-npd` и `pve02`;
- Azure TCP/10000 пересылается через `socat` на `pve02:10022`;
- `pve02:10022` пересылается на `bastion01:22`;
- текущий WireGuard является транспортом одного TCP endpoint, а не routed VPN;
- `fw01`/OPNsense остаётся gateway VLAN 10, 30, 40, 50 и 80;
- `portal-dev01` — VM 103 на `pve01`, адрес `10.10.40.107`;
- Tailscale предоставляет существующий административный fallback.

Авторитетное описание действующего пользовательского пути находится в
[user access](../services/user-access.md). Этот план не переводит перечисленные
target-компоненты в deployed state.

## Checkpoint реализации 2026-09-09

Подтверждено владельцем и live output:

- резервные копии OPNsense и legacy VPN configuration созданы вне Git;
- на `vpn-npd` создан и включён после reboot интерфейс `wg-site` с адресом
  `10.255.82.1/30` и public listen port UDP `51822`;
- Azure NSG разрешает inbound UDP `51822` от `Any`, priority `340`;
- на `fw01`/OPNsense создана instance `wg-site` с адресом
  `10.255.82.2/30`, local listen port UDP `51823` и `PersistentKeepalive = 25`;
- peers ограничены tunnel addresses `10.255.82.1/32` и
  `10.255.82.2/32`;
- handshake и двусторонние counters между Azure и OPNsense получены;
- legacy `wg0`, TCP/10000 и Tailscale не изменялись и не отключались.

Во время диагностики packets с OPNsense source/destination port `51822`
покидали `fw01` и физический `nic0` на `pve02`, но не наблюдались на Azure.
Raw UDP с `pve02` до Azure проходил. После смены local listen port OPNsense на
`51823` handshake установился; внешний NAT перевёл его в динамический source
port. Это указывает на NAT state/port handling по пути, но не доказывает,
какое именно upstream устройство выполняло проблемную обработку.

После проверки tunnel device был назначен отдельным OPNsense interface
`WG_SITE`. На Azure добавлен host route `10.10.40.107/32` через OPNsense, а на
`WG_SITE` — временное правило `10.255.82.1 -> 10.10.40.107`, TCP any. Ping и
TCP/22 от `vpn-npd` прошли. Правило предназначено только для bring-up и должно
быть сужено до выбранного application port; административный SSH в target
будет разрешён отдельному `wg-admin` peer.

Checkpoint не завершает V1 или V2: `wg-admin`, Azure forwarding policy для
admin traffic, production firewall policy и application flows ещё не созданы.

## Целевая схема

```text
                         Internet
                            |
                  public IP 20.215.200.4
                            |
                     Azure vpn-npd
                  +---------+----------+
                  |                    |
             public edge          wg-admin
          HTTPS / SSH proxy      Windows admin
                  |                    |
                  +---------+----------+
                            |
                         wg-site
                            |
                     fw01 / OPNsense
          +---------+---------+---------+---------+
          |         |         |         |         |
       VLAN 10   VLAN 30   VLAN 40   VLAN 50   VLAN 80
       MGMT      IPMI      private VM  DMZ      HTCondor
```

`fw01` остаётся VM на `pve02` до отдельного решения о migration/failover.
Термин «tunnel завершается на OPNsense» означает, что WireGuard настраивается
внутри этой VM. Proxmox host `pve02` продолжает размещать VM/LXC, но не является
основным production router для нового VPN.

## Два независимых WireGuard-контура

Разделение site и admin traffic упрощает routing, firewall и отзыв peers.

| Контур | Роль | Сеть | Endpoint / состояние |
|---|---|---|---|
| legacy `wg0` | действующий Azure ↔ `pve02` fallback | `10.255.80.0/30` | UDP `51820`, deployed |
| `wg-admin` | Windows/администраторы ↔ Azure | `10.255.81.0/24` | UDP `51821`, proposed |
| `wg-site` | Azure ↔ `fw01`/OPNsense | `10.255.82.0/30` | Azure UDP `51822`, handshake verified |

Предлагаемые адреса:

| Узел | Интерфейс | Адрес |
|---|---|---|
| `vpn-npd` | `wg-admin` | `10.255.81.1/24` |
| первый Windows admin | WireGuard client | `10.255.81.10/32` |
| `vpn-npd` | `wg-site` | `10.255.82.1/30` (deployed) |
| `fw01`/OPNsense | `wg-site` | `10.255.82.2/30` (deployed) |

`wg-admin` network остаётся предложением и перед внедрением повторно
проверяется в OPNsense, Azure и на client devices. `wg-site` transit network
подтверждена handshake, но не считается маршрутом во внутренние VLAN.

## Потоки трафика

### Административный доступ

```text
Windows WireGuard client
  -> vpn-npd wg-admin
  -> Azure forwarding policy
  -> vpn-npd wg-site
  -> OPNsense WireGuard interface
  -> разрешённый internal destination
```

Client использует split tunnel. Default Internet route Windows не меняется.
В `AllowedIPs` включаются только утверждённые NPD networks.

Начальный минимальный scope:

- `10.10.10.0/24` для management и GUI OPNsense;
- `10.10.40.0/24` для `portal-dev01` и private VM.

VLAN 30, 50 и 80 добавляются только когда нужен конкретный административный
доступ. Corosync VLAN 20, reserved VLAN 60/61 и WAN_TEMP VLAN 99 через
`wg-admin` не маршрутизируются.

### Публичный HTTPS

```text
Browser
  -> vpn-npd public TCP/443
  -> reverse proxy and TLS policy
  -> wg-site
  -> OPNsense rule
  -> portal upstream
```

Public DNS указывает только на Azure. Адрес портала в VLAN 40 не публикуется.
Для development upstream может быть `portal-dev01`; production deployment,
hostname, certificate и upstream port утверждаются отдельно.

### Публичный SSH

```text
SSH client
  -> vpn-npd public SSH endpoint
  -> TCP proxy through wg-site
  -> bastion01
  -> authorized internal destination
```

Обычному пользователю не нужен WireGuard client. Он проходит аутентификацию на
`bastion01`, после чего доступ ограничивается существующей identity и firewall
policy. Не создаются отдельные публичные порты для каждой VM.

### HTCondor

Первый пользовательский путь остаётся через `bastion01 -> condor01`. Будущий
portal принимает HTTPS на Azure и обращается к внутренним adapters только по
заранее разрешённым flows. Сетевой план не даёт portal административных прав в
HTCondor.

## Routing без NAT

Целевая схема использует routing между `wg-admin` и `wg-site` без source NAT.
OPNsense видит настоящий адрес admin peer, например
`10.255.81.10`, и может вести точный audit/firewall log.

Для этого:

- Azure знает внутренние NPD networks через peer `wg-site`;
- OPNsense знает `10.255.81.0/24` через Azure peer;
- forwarding на Azure разрешён только между двумя WireGuard interfaces и
  только для утверждённых prefixes;
- OPNsense применяет правила на назначенном WireGuard interface;
- ответный путь проверяется отдельно до публикации сервисов.

Masquerade допустим только как временная диагностическая мера по отдельному
решению. Он не входит в target, потому что скрывает client identity.

## Firewall boundaries

### Azure NSG и host firewall

Предполагаемые public listeners:

| Protocol/port | Назначение | Состояние плана |
|---|---|---|
| UDP `51821` | `wg-admin` | открыть при создании admin tunnel |
| UDP `51822` | `wg-site` | открыть при создании site tunnel |
| TCP `443` | public portal | открыть только на этапе публикации |
| TCP user SSH port | вход на bastion | номер и cutover подтвердить отдельно |
| TCP `22` | администрирование Azure | ограничить принятой admin policy |

WireGuard authentication не отменяет host firewall. Forward policy на Azure
должна быть deny-by-default с stateful return traffic.

### OPNsense

Для нового WireGuard interface создаются отдельные aliases:

- `VPN_ADMIN_NET` — `10.255.81.0/24`;
- `AZURE_EDGE_WG` — `10.255.82.1`;
- `PORTAL_UPSTREAM` — утверждённый portal address;
- `BASTION_HOST` — `10.10.50.10`.

Первичные разрешения:

| Source | Destination | Service | Причина |
|---|---|---|---|
| первый admin peer | `fw01` management | HTTPS | управление OPNsense |
| первый admin peer | `portal-dev01` | SSH | development access |
| Azure edge | portal upstream | HTTPS/approved upstream port | reverse proxy |
| Azure edge | `bastion01` | SSH | public SSH entry |

Все остальные переходы с WireGuard interface блокируются. Доступ в IPMI VLAN
30 не следует выдавать всей client subnet; для него нужен отдельный admin peer
или точное правило. Corosync VLAN 20 не доступен через VPN.

## Identity и ключи

- `wg-site`, `wg-admin` и каждый client peer имеют отдельную key pair.
- Private keys не передаются в чат, Git, documentation или evidence.
- На Azure хранится только private key Azure interface и public keys peers.
- На OPNsense хранится только private key OPNsense и public key Azure.
- На Windows private key создаётся и остаётся на этом устройстве.
- Peer получает один адрес `/32`; адрес нельзя переиспользовать одновременно.
- Отзыв администратора выполняется удалением его public key peer на Azure.
- Конфигурационные snapshots перед публикацией очищаются от private keys.

## Этап V0 — preflight и rollback base

Воздействие: read-only и создание резервных копий, без изменения traffic.

Работы:

1. Экспортировать конфигурацию OPNsense в защищённое место вне Git.
2. Сохранить копии текущих `wg0` и systemd units Azure/`pve02` вне Git.
3. Зафиксировать Azure NSG rules, routes и public listeners.
4. Проверить console/Tailscale access к PVE и OPNsense.
5. Повторно проверить handshake legacy tunnel и public SSH.
6. Подтвердить свободные VPN subnets и UDP ports.
7. Зафиксировать выбранные DNS names и public SSH port либо оставить их
   нерешёнными до V5.

Готово, когда существующая схема может быть восстановлена без нового VPN.

## Этап V1 — параллельная основа на Azure

Воздействие: добавляются новые listeners и interfaces; legacy `wg0` не
изменяется.

Работы:

1. Создать key pairs Azure для `wg-site` и `wg-admin`.
2. Создать interfaces с отдельными config files и systemd units.
3. Открыть UDP `51821` и `51822` в Azure NSG.
4. Включить persistent IPv4 forwarding.
5. Добавить deny-by-default forwarding policy между interfaces.
6. Добавить logging/metrics без записи key material.
7. Проверить, что legacy TCP/10000 продолжает работать.

Готово, когда оба новых interfaces подняты, но не имеют доступа во внутренние
VLAN и не повлияли на старый вход.

## Этап V2 — site-to-site Azure ↔ OPNsense

Воздействие: в `fw01` появляется новый WireGuard interface и ограниченные
firewall rules. Планового отключения текущего Internet routing быть не должно.

Работы:

1. Создать OPNsense WireGuard instance и Azure peer.
2. Настроить OPNsense как endpoint, который поддерживает session к белому IP
   Azure через существующий WAN/NAT.
3. Назначить WireGuard interface и применить default-deny rules.
4. Настроить Azure routes/AllowedIPs только для выбранных internal networks.
5. Настроить обратный route к `wg-admin` через Azure peer.
6. Проверить handshake, counters, MTU и bidirectional routing.
7. Проверить, что VLAN 20/60/61/99 недоступны.

Готово, когда Azure по новому tunnel достигает только разрешённых test targets,
а legacy access остаётся рабочим.

## Этап V3 — административный WireGuard для Windows

Воздействие: один client peer получает минимальный внутренний доступ.

Работы:

1. Создать key pair в WireGuard client на Windows.
2. Добавить public key и `/32` peer на Azure.
3. Настроить split-tunnel `AllowedIPs` для VLAN 10 и 40.
4. Добавить точные OPNsense rules для admin peer.
5. Проверить GUI OPNsense, SSH `portal-dev01` и отсутствие доступа в остальные
   VLAN.
6. Проверить, что обычный Internet Windows не идёт через Azure.
7. Проверить reconnect после смены сети Windows и restart interfaces.

Готово, когда владелец включает WireGuard одной кнопкой и напрямую использует
`https://10.10.10.1` и `ssh dev01@10.10.40.107` без Tailscale/ProxyJump.

## Этап V4 — public HTTPS через Azure

Воздействие: появляется первый публичный web endpoint.

Работы:

1. Подтвердить DNS name и certificate ownership.
2. Развернуть reverse proxy на Azure из воспроизводимой конфигурации.
3. Направить test hostname на portal upstream через `wg-site`.
4. Передавать корректные proxy headers и ограничить trusted proxies portal.
5. Настроить TLS, renewal, rate limits, request size и access logs.
6. Не публиковать Django development server как production service.
7. Проверить отсутствие прямого доступа к internal address извне.

Готово, когда test HTTPS endpoint переживает restart Azure proxy и tunnel, а
portal видит ожидаемый client/proxy context без доверия произвольным headers.

## Этап V5 — public SSH через новый site tunnel

Воздействие: готовится замена текущей цепочки `vpn-npd -> pve02 -> bastion01`.

Работы:

1. Выбрать и зафиксировать public SSH port.
2. Поднять параллельный test listener на Azure.
3. Направить его через `wg-site` непосредственно на `bastion01:22`.
4. Проверить key-only login, fail2ban, ProxyJump и HTCondor path.
5. Проверить limits, logs и поведение при недоступном upstream.
6. Сохранить старый TCP/10000 до завершения acceptance window.

Готово, когда test user проходит end-to-end путь к `condor01`, а новый listener
не предоставляет доступ к другим internal services.

## Этап V6 — cutover

Воздействие: public production traffic переводится на новую схему.

Работы:

1. Выполнить совместную проверку admin VPN, HTTPS и SSH.
2. Перевести public DNS/port на новые listeners.
3. Наблюдать handshake, error rate и access logs в согласованном окне.
4. Проверить portal, bastion, HTCondor и административный доступ.
5. Не отключать legacy tunnel до отдельного подтверждения владельца.

Готово, когда новая схема отработала согласованное окно без обращения к
Tailscale или legacy TCP relay.

## Этап V7 — cleanup

Воздействие: удаление старых компонентов; выполняется только после явного
решения владельца.

Кандидаты на отключение:

- Azure `npd-public-bastion-ssh-forward.service`;
- `pve02` `npd-vpn-bastion-ssh-forward.service`;
- legacy `wg0` на `pve02` и соответствующий peer Azure;
- старые public NSG rules;
- Tailscale как постоянная зависимость.

Перед удалением нужно решить, оставлять ли legacy `wg0` или отдельный новый
tunnel к PVE host как emergency out-of-band path при отказе `fw01`. Tailscale
не удаляется, пока не проверен независимый recovery access.

Готово, когда неиспользуемые listeners закрыты, configs архивированы безопасно,
а current state, diagrams, runbooks и health-check отражают новую схему.

## Проверки приёмки

### Routing

- Windows достигает только утверждённых prefixes.
- Default route Windows не меняется.
- Azure достигает portal/bastion только по разрешённым ports.
- Ответный traffic возвращается через тот же tunnel.
- VLAN 20/60/61/99 недоступны.

### Security

- public scan Azure показывает только утверждённые listeners;
- без WireGuard key internal addresses недоступны;
- один admin peer нельзя использовать как другой peer;
- OPNsense log содержит исходный address admin peer;
- private keys отсутствуют в Git, logs и evidence;
- Proxmox, OPNsense и IPMI не публикуются через public reverse proxy.

### Reliability

- OPNsense восстанавливает tunnel после reboot;
- Azure interfaces и proxy восстанавливаются после reboot;
- смена внешней сети Windows не требует изменения server config;
- временный обрыв site tunnel не ломает локальный routing кластера;
- public proxy fail-closed при недоступном upstream;
- rollback возвращает legacy SSH path.

### Application paths

- admin открывает OPNsense GUI через `wg-admin`;
- admin подключается к `portal-dev01` через `wg-admin`;
- public browser открывает portal через Azure HTTPS;
- user входит на `bastion01` через Azure SSH;
- user проходит с bastion на разрешённую VM или `condor01`;
- test HTCondor job выполняется от правильной identity.

## Стоп-критерии

Работа останавливается, если:

- отсутствует console/fallback access к OPNsense или PVE;
- изменение требует перезаписать legacy `wg0` до проверки нового tunnel;
- неясен обратный route;
- OPNsense rule временно разрешает `any -> any` между VPN и VLAN;
- public listener открывает Proxmox, OPNsense или IPMI;
- private key попал в terminal capture, repository или evidence;
- изменение routing затрагивает Corosync VLAN 20;
- после изменения перестал работать текущий public SSH.

## Rollback

До V6 основной rollback — отключить новые listeners/interfaces и продолжить
использовать legacy TCP/10000 и Tailscale. Старые units и peer не изменяются в
V1–V5.

Rollback отдельного этапа:

- Azure: закрыть новый NSG rule, остановить новый interface/proxy;
- OPNsense: disable новые pass rules, затем WireGuard interface/instance;
- Windows: deactivate/remove новый tunnel profile;
- public web: вернуть test DNS или удалить test record;
- public SSH: вернуть клиентам старый TCP/10000.

Удаление key material и старых configs не является частью аварийного rollback;
оно выполняется отдельно после восстановления и подтверждения владельца.

## Артефакты реализации

После принятия и выполнения этапов должны появиться:

- ADR о внешнем Azure edge и termination site tunnel на OPNsense;
- очищенные templates WireGuard без private keys;
- воспроизводимая конфигурация Azure host firewall/reverse proxy;
- OPNsense backup вне Git и очищенный summary правил в evidence;
- runbook создания/отзыва admin peer;
- runbook public HTTPS и SSH cutover/rollback;
- health-check site/admin handshakes и public endpoints;
- monitoring handshake age, proxy health и certificate expiry;
- обновлённые current state, user access, topology и history.

## Решения перед реализацией

Владелец должен подтвердить перед соответствующим этапом:

1. Адресные сети и UDP ports из предлагаемой таблицы.
2. Какие VLAN доступны первому admin peer.
3. Public DNS name портала.
4. Public SSH port и сохранение совместимости TCP/10000.
5. Reverse proxy software и место TLS termination.
6. Остаётся ли отдельный emergency tunnel к PVE после V7.
7. Через какое acceptance window отключаются Tailscale и legacy relay.

Эти пункты не блокируют разработку Request MVP внутри `portal-dev01`, но
блокируют публикацию портала и удаление существующего доступа.

## Связанные документы

- [Текущая топология](topology.md).
- [Адресация](addressing.md).
- [Пользовательский доступ](../services/user-access.md).
- [Firewall и routing](../services/firewall.md).
- [План пользовательской платформы](../project/user-platform-plan.md).
- [Технический план платформы](../project/user-platform-implementation-plan.md).
