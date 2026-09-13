# Технический план реализации пользовательской платформы

Статус: draft
Дата создания: 2026-09-07
Последняя редакция: 2026-09-11
Живая проверка при подготовке: development-портал проверен на `portal-dev01`
Назначение: разложить реализацию портала на технические пакеты работ и задать
безопасные границы интеграций
Источник истины для: предлагаемой структуры реализации; не является runbook и
не разрешает deployment или изменение инфраструктуры

## Связь с продуктовым планом

[Продуктовый план](user-platform-plan.md) определяет пользовательский результат
и критерии этапов U0–U7. Этот документ отвечает на вопросы «из каких
компонентов это собрать», «какие контракты нужны» и «как проверять каждый
инкремент».

Команды развёртывания, миграции production-базы и выдачи credentials должны
появляться в отдельных runbook'ах после выбора deployment topology. До этого
документ используется только для проектирования и разработки.

## Техническая исходная точка

Уже существует:

- Python-скрипт `scripts/create-cluster-user.py` для создания согласованной
  Unix identity;
- runbook выдачи пользователя;
- `condor01` как HTCondor manager и submit point;
- Ansible inventory и роли для execute nodes;
- Prometheus и node exporter;
- внешний SSH-путь через WireGuard и `bastion01`;
- PostgreSQL 16 работает локально на development VM `portal-dev01`;
- для первого входа выбраны локальные учётные записи портала и Google OIDC;
- development web service работает через Nginx, Gunicorn и systemd;
- пользовательские страницы используют единый адаптивный интерфейс на Tabler;
  frontend-assets хранятся локально и не зависят от CDN; интерфейс доступен
  английской и украинской языковыми версиями;
- реализованы профили, внешние identity, системные роли, проекты и membership;
- события входа, ошибки входа и выхода записываются в append-only `AuditEvent`;
- реализованы заявки, append-only transitions и approvals, reviewer/operator
  queues и ручная фиксация результата исполнения;
- изменения состояния заявки создают дедуплицированные in-app уведомления;
- production HTTP endpoint для портала ещё не выбран и не считается
  развёрнутым.

JBOD/NFS намеренно выключены. Реализация до этапа шаблонной отправки jobs не
должна зависеть от `/data`; восстановление storage не входит в этот план.

## Решения, которые нужно принять до production deployment

Для каждого пункта нужен ADR или явное решение владельца:

1. Размещение: VM или LXC, узел, имя, адрес и ресурсные лимиты.
2. Контур доступа: внутренний pilot, VPN или публичный HTTPS endpoint.
3. DNS-имя, источник TLS-сертификата и процедура продления.
4. Нужен ли после Google университетский IdP и будет ли он подключаться
   напрямую или через identity broker.
5. Кто назначает операторские роли и может ли человек согласовать собственную
   заявку.
6. Канал уведомлений и минимально допустимый fallback.
7. Retention профилей, заявок, аудита и технических результатов.
8. Допустимые job templates, лимиты и способ передачи небольших файлов.
9. Модель HTCondor credentials и сохранения реального владельца job.
10. Какие операции worker имеет право выполнять автоматически.

В плане ниже используются placeholder'ы `portal`, `Google OIDC` и
`portal deployment`. Они не резервируют hostname, IP или VMID.

## Базовый технологический профиль

Предлагаемая стартовая реализация:

- Python и Django как единое server-side приложение;
- Django templates, Tabler и HTMX для интерактивных фрагментов;
- PostgreSQL как источник истины заявок и операций;
- локальная Django-аутентификация и Google OIDC authorization-code flow;
- Nginx как reverse proxy и TLS endpoint;
- отдельный worker-процесс, использующий ту же кодовую базу;
- systemd для web/worker на production deployment;
- Prometheus metrics и структурированные журналы.

Google является первым внешним OIDC-провайдером. Keycloak или другой broker
не требуется для этого этапа и рассматривается только при подключении
нескольких внешних провайдеров или появлении дополнительных требований к SSO.

Для первой версии не нужны SPA, Kubernetes, микросервисы и отдельный message
broker. При низком потоке заявок очередь операций можно хранить в PostgreSQL,
а worker запускать как отдельную Django management command. Решение о broker
пересматривается только после появления измеренной нагрузки или требований,
которые PostgreSQL-очередь не покрывает.

## Целевая схема компонентов

```text
Browser
  |
  | HTTPS
  v
Nginx
  |
  v
Django web --------------------> OIDC provider
  |
  +----> PostgreSQL <---- Django worker
                            |
                            +--> identity adapter
                            +--> HTCondor adapter
                            +--> Proxmox adapter (поздний этап)

Prometheus <---- web / worker metrics
```

Web и worker используют разные Unix service accounts и разные credentials.
Web может создавать только записи-запросы в PostgreSQL. Доступ к ОС,
HTCondor write API, Ansible и Proxmox получает только соответствующий adapter
worker'а после отдельного допуска.

## Границы процессов

### Web

Web-процесс отвечает за:

- локальный login, Google OIDC login и локальную session;
- HTML/UI и серверную проверку форм;
- authorization для каждого объекта;
- создание заявок и разрешённых переходов;
- постановку типизированной операции в очередь;
- показ результата с удалением чувствительных деталей.

Web-процессу запрещены:

- SSH private keys администратора;
- Proxmox token;
- HTCondor administrative credential;
- запуск shell-команд и Ansible;
- прямое изменение infrastructure state.

### Worker

Worker:

- выбирает одну разрешённую операцию с блокировкой строки;
- проверяет, что заявка одобрена и ещё актуальна;
- строит типизированный запрос к конкретному adapter;
- использует idempotency key;
- сохраняет нормализованный результат и audit event;
- повторяет только операции с явно безопасной retry policy;
- останавливается при расхождении ожидаемого и фактического состояния.

Worker не является универсальным remote-shell executor. Имя команды, playbook,
host, API method и произвольные аргументы не принимаются из браузера.

## Структура кода

Предлагаемое размещение после создания приложения:

```text
portal/
  manage.py
  pyproject.toml
  config/
    settings/
      base.py
      development.py
      test.py
      production.py
    urls.py
  apps/
    accounts/
    projects/
    requests/
    audit/
    operations/
    condor/
    virtual_machines/
  templates/
  static/
  tests/
ansible/
  roles/
    portal/
docs/
  runbooks/
    portal-deploy.md          # создаётся перед первым deployment
    portal-restore.md         # создаётся до production acceptance
```

`accounts`, `projects`, `requests` и `audit` составляют MVP. `condor` и
`virtual_machines` добавляются только на соответствующих продуктовых этапах.

## Минимальная модель данных

| Модель | Назначение | Ключевые ограничения |
|---|---|---|
| `UserProfile` | профиль и cluster identity пользователя независимо от способа входа | один на portal user; login и UID не задаются браузером после provisioning |
| `ExternalIdentity` | внешний способ входа | уникальная пара issuer+subject; связь с portal user; email не является ключом |
| `UserSSHKey` | согласованный публичный ключ пользователя | нормализованный key, fingerprint, владелец, статус и время отзыва |
| `Project` | учебный или исследовательский проект | стабильный UUID; состояние и владелец |
| `ProjectMembership` | роль человека в проекте | уникальная пара project+user |
| `Request` | общая часть заявки | immutable author; type и project; текущий state |
| `RequestTransition` | история переходов | append-only; actor, from/to, time, comment |
| `Approval` | решение reviewer | нельзя редактировать задним числом; новое решение создаёт новую запись |
| `Operation` | единица исполнения worker | type, typed payload, idempotency key, attempts, result |
| `AuditEvent` | значимое действие | append-only; actor, object, action, request id |
| `Notification` | состояние доставки | канал, адресат, событие, attempts |

Позднее добавляются `Job`, `JobAction`, `VMRequest` и `VMInstance`. Raw secret,
SSH private key и полный stdout административных инструментов в PostgreSQL не
хранятся.

Публичные идентификаторы — UUID. Внутренние numeric primary key не должны быть
единственным authorization boundary.

## Состояния и конкурентный доступ

Переходы заявки реализуются одним доменным сервисом, а не произвольным
присваиванием поля `status` из view или admin.

Минимальные правила:

- `draft -> submitted` выполняет автор;
- `submitted -> under_review` выполняет reviewer;
- `under_review -> approved|rejected` требует reviewer и комментарий;
- `approved -> executing` создаёт ровно одну `Operation`;
- `executing -> active|failed` выполняет worker или оператор;
- отмена после начала исполнения зависит от типа операции;
- requestor не согласовывает собственную заявку, если владелец явно не принял
  другую политику.

Изменение состояния выполняется в transaction с блокировкой заявки. Формы
используют одноразовый idempotency token, а `Operation.idempotency_key` имеет
unique constraint.

## Авторизация

Локальный login или OIDC подтверждают личность, но object permissions хранит
портал.

| Действие | Applicant/User | Project lead | Reviewer | Operator | Admin |
|---|---:|---:|---:|---:|---:|
| Читать собственный профиль | да | да | да | да | да |
| Читать закрытый проект | только участник | свой проект | по политике | по политике | да |
| Создать заявку | да | да | да | да | да |
| Согласовать заявку | нет | только разрешённые типы | да | по политике | да |
| Исполнить инфраструктурную операцию | нет | нет | нет | да | да |
| Назначить системную роль | нет | нет | нет | нет | да |

Каждый queryset фильтруется по доступным объектам. Скрытие кнопки в UI не
считается проверкой прав. На критические действия добавляется повторное
подтверждение; CSRF и secure session cookies обязательны.

## OIDC и cluster identity

Локальная учётная запись использует username и пароль портала. Для внешнего
входа `issuer + subject` является неизменяемым идентификатором. Email и display
name не используются для автоматического поиска или объединения пользователей.
Даже при одинаковом email локальная и внешняя identity остаются разными, пока
пользователь явно не подтвердит связывание обоих способов входа.

Связь с кластером хранит:

- `cluster_login` в принятом lowercase формате;
- numeric UID из диапазона `20000–29999`;
- состояние provisioning;
- время и идентификатор одобренной заявки;
- результат последней сверки.

До автоматизации оператор выполняет
[действующий runbook](../runbooks/provision-user.md) вручную и вносит UID и
результат. Существующий `scripts/create-cluster-user.py` является отправной
точкой, но не вызывается web-процессом.

Перед подключением к worker скрипт или его замена должны получить:

- machine-readable preflight и result;
- однозначные exit codes;
- отсутствие пользовательских shell fragments;
- проверенный повтор без изменения уже правильного состояния;
- отдельную операцию disable/revoke;
- интеграционные тесты на конфликт login/UID;
- runbook частичного сбоя между узлами.

## Очередь операций

Для MVP используется таблица `Operation` и PostgreSQL locking. Состояния:

```text
pending -> running -> succeeded
                  +-> retryable
                  +-> failed
                  +-> needs_operator
```

Payload хранится в versioned typed schema. Например, операция создания
identity содержит только request UUID, утверждённый login, UID и ID
согласованной записи `UserSSHKey`. Она не содержит готовую shell-команду или
переданный браузером путь к файлу.

Retry допускается только если adapter документирует идемпотентность. После
неоднозначного remote timeout операция получает `needs_operator`, пока
read-only reconciliation не подтвердит результат.

## Adapter пользовательской identity

Порядок введения:

1. Портал только фиксирует одобрение; operator работает по runbook.
2. Worker выполняет read-only preflight и показывает расхождения.
3. Operator подтверждает конкретную подготовленную операцию.
4. Worker вызывает один allowlisted provisioning entrypoint.
5. Worker выполняет read-only verification на `bastion01`, `condor01` и
   выбранных execute nodes.

Private SSH key пользователя никогда не попадает в портал. Публичный ключ
валидируется, нормализуется и хранится отдельным объектом с fingerprint и
состоянием отзыва. Worker получает только ключ, указанный в одобренной заявке.

## HTCondor adapter

Интеграция делится на read и write credentials.

### Read-only

- искать jobs только по авторитетно связанному owner;
- возвращать allowlisted атрибуты, а не произвольный ClassAd;
- нормализовать состояния и hold reason;
- ограничивать объём истории и частоту запросов;
- не отдавать пути и environment, содержащие чувствительные данные.

### Submit и управление

До реализации нужен отдельный spike/ADR по модели credentials. Нужно сравнить
per-user HTCondor credentials и ограниченный helper с privilege separation на
`condor01`. Независимо от варианта:

- HTCondor `Owner` должен соответствовать реальной cluster identity;
- template строится сервером из allowlisted полей;
- CPU, RAM, disk, runtime и count имеют верхние границы;
- submit получает idempotency key и сохраняет `ClusterId.ProcId`;
- remove разрешён только владельцу job или operator;
- service credential не выдаётся web-процессу;
- arbitrary ClassAd и произвольные scheduler commands запрещены.

Пока JBOD выключены, первая версия использует только ограниченный HTCondor file
transfer. Максимальный размер, staging directory и retention должны быть
приняты до включения uploads. Без этого портал может разрешать только шаблоны,
которым не нужна загрузка пользовательских файлов.

## Proxmox adapter

До этапа U6 портал хранит только заявку и введённый оператором VMID. Создание
VM остаётся ручным.

Для последующей автоматизации обязательны:

- отдельный API token без `root@pam`;
- доступ только к выделенному resource pool и утверждённым templates;
- allowlist VLAN и границы CPU/RAM/disk;
- deterministic correlation между request UUID и VM;
- preflight на quota и конфликт VMID/name;
- безопасный повтор create/clone;
- отдельное подтверждение удаления;
- backup/restore policy до автоматического удаления.

Browser не передаёт raw Proxmox API path, privilege, node или arbitrary
cloud-init fragment.

## Секреты и конфигурация

- Секреты не коммитятся в Git и не хранятся открытым текстом в PostgreSQL.
- Development secrets отделены от production.
- Web и worker получают разные credentials.
- Runtime secret доступен только нужному Unix service account.
- OIDC client secret, database password и adapter credentials ротируются
  независимо.
- В audit сохраняются идентификатор credential/version и результат, но не
  секретное значение.
- Конфигурация deployment после принятия хранится в Ansible role; фактический
  snapshot — в evidence, а не в Markdown.

Конкретный secret backend выбирается на U0. Ansible Vault может доставлять
начальные значения, но не должен превращаться в API для web-процесса.

## HTTP и безопасность приложения

Минимальный baseline:

- HTTPS, HSTS после подтверждения endpoint и certificate renewal;
- secure, HTTP-only, SameSite session cookie;
- CSRF protection для всех state-changing requests;
- короткая operator/admin session и повторная аутентификация для критических
  действий;
- rate limit для login callback, заявок и uploads;
- строгая проверка размера и типа входных данных;
- security headers и запрет framing;
- generic error пользователю и correlation ID для оператора;
- отсутствие секретов, ключей и персональных данных в обычных логах.

Первый релиз не предоставляет публичный REST API. Он добавляется только после
отдельной модели scopes, versioning и rate limits.

## Наблюдаемость и аудит

Нужны отдельные endpoints:

- liveness — процесс отвечает;
- readiness — доступны обязательные локальные зависимости;
- metrics — request latency/error rate, DB pool, queue depth, operation status;
- build info — версия приложения и миграции без секретов.

Потеря HTCondor или Proxmox не должна делать login и просмотр заявок unready.
Состояние внешних adapters публикуется отдельными метриками.

Audit event содержит actor, effective role, action, object, request/correlation
ID, время, outcome и минимальный технический контекст. Обычный admin UI не
редактирует audit events.

## Тестирование

### Unit

- переходы state machine;
- object-level authorization;
- quota и validation;
- idempotency;
- редактирование/маскирование технических результатов.

### Integration

- PostgreSQL constraints и migrations;
- OIDC callback с тестовым provider;
- concurrent approval и повторный submit формы;
- worker locking и recovery после остановки;
- adapters через fake endpoints.

### Security

- попытки доступа к чужому project/request/job;
- CSRF, session fixation и open redirect;
- privilege escalation через роли и payload;
- secret scanning и dependency audit;
- проверка upload limits до включения файлов.

### Acceptance

- полный путь заявки от applicant до ручного исполнения;
- backup и restore PostgreSQL;
- отказ OIDC, worker и внешнего adapter;
- одна тестовая HTCondor job реального тестового пользователя перед U5;
- контролируемый повтор операции после network timeout.

Тесты, меняющие кластер, выполняются только в отдельном согласованном окне и по
runbook. Обычный CI использует fake adapters.

## CI

Минимальный pipeline:

1. format/lint Python и templates;
2. type checks для доменных сервисов и adapters;
3. unit tests;
4. PostgreSQL integration tests;
5. проверка отсутствующих migrations;
6. dependency и secret scan;
7. сборка неизменяемого release artifact;
8. публикация результата без автоматического production deployment.

Конкретные инструменты и версии фиксируются при создании `pyproject.toml` и
обновляются отдельно. План не закрепляет версии библиотек без реализации.

## Deployment и rollback

До первого production deployment должны существовать:

- Ansible role с web, worker, Nginx и PostgreSQL client configuration;
- root-owned runtime configuration;
- отдельные service accounts и filesystem permissions;
- миграция БД как отдельный контролируемый шаг;
- backup перед необратимой migration;
- health-check после deployment;
- rollback приложения на предыдущий artifact;
- правило backward-compatible migrations;
- проверенный restore PostgreSQL.

Автоматический deployment с merge в `main` в первую версию не входит.

## Технические пакеты работ

### T0 — решения и threat model

Соответствует U0.

- оформить ADR из списка открытых решений;
- описать trust boundaries и злоупотребления ролями;
- утвердить MVP data model и retention;
- определить deployment target без создания ресурса.

Проверка: владелец явно принял решения, необходимые для T1.

### T1 — каркас приложения

Соответствует U1.

- создать `portal/`, settings и локальную PostgreSQL-среду;
- добавить базовый CI;
- реализовать liveness/readiness/build info;
- добавить OIDC test double и production interface;
- зафиксировать application configuration schema.

Проверка: чистая среда поднимает приложение и выполняет tests/migrations.

### T2 — identity и authorization

Соответствует U1.

- реализовать `UserProfile`, локальный login и отдельную `ExternalIdentity` для
  связи issuer+subject;
- добавить роли и object-permission helpers;
- покрыть deny-by-default тестами;
- реализовать session security и audit login events.

Проверка: тесты доказывают изоляцию пользователей и проектов.

### T3 — проекты, заявки и аудит

Соответствует U2.

- реализовать модели, state machine и forms;
- добавить reviewer/operator queues;
- добавить transitions, approvals и comments;
- реализовать ручную фиксацию исполнения;
- добавить минимальные уведомления.

Проверка: acceptance test полного ручного процесса и отсутствия дубликатов.

### T4 — первый deployment MVP

Соответствует контрольной точке Request MVP.

- создать Ansible role и два runbook'а: deploy и restore;
- развернуть портал в утверждённом контуре;
- подключить OIDC и TLS;
- подключить Prometheus и alerts;
- выполнить backup/restore test;
- не выдавать worker инфраструктурные credentials.

Проверка: ограниченная пилотная группа проходит процесс заявки.

### T5 — operation queue и assisted provisioning

Подготавливает U7, но не включает автоматическое исполнение сразу.

- реализовать `Operation`, locking, idempotency и reconciliation;
- добавить read-only identity preflight;
- связать ручной runbook с technical result;
- только после проверки добавить allowlisted provisioning adapter.

Проверка: повтор и частичный сбой не создают разные UID или аккаунты-дубликаты.

### T6 — HTCondor read integration

Соответствует U4.

- выполнить credential/ownership spike;
- реализовать read-only adapter;
- добавить mapping portal identity -> cluster login/UID;
- ограничить поля и объём выдачи;
- проверить изоляцию jobs разных пользователей.

Проверка: пользователь видит только собственные job и не получает write path.

### T7 — HTCondor template submission

Соответствует U5.

- принять ADR по write credentials;
- описать versioned job templates;
- реализовать validation и resource limits;
- добавить submit/remove operations и reconciliation;
- определить bounded staging/retention без зависимости от JBOD.

Проверка: тестовый пользователь создаёт и удаляет только собственную job, а
повторный HTTP request не создаёт вторую.

### T8 — VM request registry

Соответствует U6.

- реализовать тип заявки и quota review;
- хранить operator-entered VMID, owner и expiry;
- добавить уведомление о сроке;
- оставить Proxmox mutation ручной.

Проверка: каждая учтённая VM связана с одобренной заявкой.

### T9 — отдельные automation adapters

Соответствует выбранным операциям U7.

- выдавать один минимальный credential на один adapter;
- добавлять операции по одной;
- для каждой операции создать preflight, execute, verify и operator recovery;
- автоматизацию удаления вводить последней и только с backup policy.

Проверка: владелец принимает каждую автоматизированную операцию отдельно.

## Условия остановки

Разработка или rollout останавливаются, если:

- не определён авторитетный owner объекта;
- web-процессу требуется административный credential;
- операция не имеет idempotency/reconciliation;
- портал может показать объект другого пользователя;
- backup базы не восстанавливается;
- интеграция требует вернуть JBOD без отдельного решения;
- deployment меняет сеть, VM или доступы вне утверждённого scope;
- технический этап начинает назначать приоритеты остальной инфраструктуре.

## Ближайший технический результат

До написания production-кода результатом T0 должен стать короткий набор ADR и
утверждённая карточка Request MVP. После этого T1–T3 можно реализовать локально
с fake OIDC и fake infrastructure adapters, не меняя живой кластер.

## Связанные документы

- [Продуктовый план](user-platform-plan.md).
- [План Azure edge и WireGuard](../network/azure-edge-vpn-plan.md).
- [Пользовательский доступ](../services/user-access.md).
- [HTCondor](../services/htcondor.md).
- [Выдача пользователя](../runbooks/provision-user.md).
- [Архитектура кластера](../architecture/overview.md).
- [Правила документации](../documentation-guide.md).
