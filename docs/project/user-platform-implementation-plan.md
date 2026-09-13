# Технический план реализации пользовательской платформы

Статус: draft
Дата создания: 2026-09-07
Последняя редакция: 2026-09-14
Живая проверка при редакции: не выполнялась; существующий Django-портал ранее
проверен на `portal-dev01`, новая реализация ещё не развёрнута
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
- для регистрации, локальных credentials и Google OIDC выбран Keycloak;
- существующий Django development service работает через Nginx, Gunicorn и
  systemd и остаётся эталоном поведения на время новой реализации;
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
4. Нужен ли университетский IdP и когда подключать его к Keycloak как ещё один
   внешний identity provider.
5. Кто назначает операторские роли и может ли человек согласовать собственную
   заявку.
6. Production SMTP relay, sender domains и минимально допустимый fallback.
7. Retention профилей, заявок, аудита и технических результатов.
8. Допустимые job templates, лимиты и способ передачи небольших файлов.
9. Модель HTCondor credentials и сохранения реального владельца job.
10. Какие операции worker имеет право выполнять автоматически.

В плане ниже используются placeholder'ы `portal`, `Keycloak` и
`portal deployment`. Они не резервируют hostname, IP или VMID.

## Базовый технологический профиль

Целевая стартовая реализация:

- Python и FastAPI как server-rendered модульный монолит;
- Jinja2, локальный Tabler и HTMX для интерфейса;
- WTForms для HTML forms и CSRF, Pydantic для typed schemas;
- SQLAlchemy и Alembic для persistence и migrations;
- PostgreSQL как источник истины прикладных данных, server-side sessions,
  operation queue и transactional email outbox;
- Keycloak как единственный публичный Identity Provider;
- Authlib как OIDC client Portal;
- Babel, gettext и Jinja2 i18n для локализации;
- SQLAdmin только для ограниченного технического admin UI;
- Nginx как reverse proxy и TLS endpoint;
- отдельные mail и operation worker processes из той же codebase;
- systemd для web/workers на production deployment;
- Prometheus metrics и структурированные журналы.

Keycloak хранит локальные credentials, подтверждает email, восстанавливает
пароль и подключает Google как внешний OIDC provider. Portal не реализует и не
хранит пользовательские пароли.

Для первой версии не нужны SPA, Kubernetes, прикладные микросервисы, Redis и
отдельный message broker. Очереди операций и писем используют PostgreSQL с
locking, lease, idempotency и recovery. Решение о broker пересматривается
только после измеренной нагрузки или появления требований, которые
PostgreSQL-очередь не покрывает.

## Целевая схема компонентов

```text
Browser
  |
  | HTTPS
  v
Nginx
  |
  v
FastAPI web ---- OIDC ----> Keycloak ----> Google
  |                            |
  |                            +---- SMTP ----+
  v                                         |
PostgreSQL <---- mail worker ---- SMTP -----+--> SMTP relay
     |
     +-------- operation worker
                    |
                    +--> identity adapter
                    +--> HTCondor adapter
                    +--> Proxmox adapter (поздний этап)

Prometheus <---- web / workers metrics
```

Web, mail worker и operation worker используют разные Unix service accounts и
разные credentials. Web может создавать только записи-запросы в PostgreSQL.
Mail worker получает только SMTP credential и доступ к email queue. Доступ к
ОС, HTCondor write API, Ansible и Proxmox получает только соответствующий
operation adapter после отдельного допуска.

## Границы процессов

### Web

Web-процесс отвечает за:

- OIDC redirect/callback с Keycloak и server-side application session;
- HTML/UI и серверную проверку форм;
- authorization для каждого объекта;
- создание заявок и разрешённых переходов;
- атомарную постановку типизированных операций и писем в PostgreSQL queues;
- показ результата с удалением чувствительных деталей.

Web-процессу запрещены:

- SSH private keys администратора;
- Proxmox token;
- HTCondor administrative credential;
- запуск shell-команд и Ansible;
- прямое изменение infrastructure state.

### Mail worker

Mail worker:

- выбирает `EmailDelivery` с блокировкой и ограниченным lease;
- строит письмо только из разрешённого versioned template;
- отправляет `text/plain` и `text/html` через SMTP relay;
- классифицирует временные и постоянные ошибки;
- выполняет bounded retry с exponential backoff;
- сохраняет нормализованный результат без чувствительного содержимого.

Mail worker не принимает произвольный sender, subject, template или body из
browser. Он не имеет infrastructure credentials.

### Operation worker

Operation worker:

- выбирает одну разрешённую операцию с блокировкой строки;
- проверяет, что заявка одобрена и ещё актуальна;
- строит типизированный запрос к конкретному adapter;
- использует idempotency key;
- сохраняет нормализованный результат и audit event;
- повторяет только операции с явно безопасной retry policy;
- останавливается при расхождении ожидаемого и фактического состояния.

Operation worker не является универсальным remote-shell executor. Имя команды,
playbook, host, API method и произвольные аргументы не принимаются из browser.

## Структура кода

Предлагаемое размещение после создания приложения:

```text
portal/
  pyproject.toml
  alembic.ini
  alembic/
  app/
    main.py
    core/
    identity/
    profiles/
    projects/
    requests/
    notifications/
    mail/
    audit/
    operations/
    condor/
    virtual_machines/
    workers/
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

`identity`, `profiles`, `projects`, `requests`, `notifications`, `mail` и
`audit` составляют Request MVP. `condor` и `virtual_machines` добавляются
только на соответствующих продуктовых этапах.

## Минимальная модель данных

| Модель | Назначение | Ключевые ограничения |
|---|---|---|
| `UserProfile` | onboarding, профиль и cluster identity пользователя независимо от способа входа | один на portal user; состояние `incomplete|complete`; login и UID не задаются browser после provisioning |
| `ExternalIdentity` | внешний способ входа | уникальная пара issuer+subject; связь с portal user; email не является ключом |
| `ApplicationSession` | server-side session Portal | hash случайного identifier; expiry, last activity и revoke state; секрет не хранится открытым текстом |
| `UserSSHKey` | согласованный публичный ключ пользователя | нормализованный key, fingerprint, владелец, статус и время отзыва |
| `Project` | учебный или исследовательский проект | стабильный UUID; состояние и владелец |
| `ProjectMembership` | роль человека в проекте | уникальная пара project+user |
| `Request` | общая часть заявки | immutable author; type и project; текущий state |
| `RequestTransition` | история переходов | append-only; actor, from/to, time, comment |
| `Approval` | решение reviewer | нельзя редактировать задним числом; новое решение создаёт новую запись |
| `Operation` | единица исполнения worker | type, typed payload, idempotency key, attempts, result |
| `AuditEvent` | значимое действие | append-only; actor, object, action, request id |
| `Notification` | прикладное событие для пользователя | адресат, event type, target и состояние прочтения |
| `EmailDelivery` | доставка notification по email | template/version, зафиксированные recipient/language, idempotency key, lease, attempts и status |

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

Keycloak подтверждает личность, но object permissions хранит Portal.

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

## OIDC, sessions и cluster identity

Локальная регистрация, password login, email verification, password recovery и
Google login выполняются в Keycloak. Пользователь, вошедший через Google, не
создаёт отдельный пароль Portal. Keycloak связывает способы входа только после
подтверждённой процедуры account linking.

Для Portal пара `issuer + subject` является постоянным внешним идентификатором.
Email и display name не являются ключами пользователя. Portal синхронизирует
только разрешённые verified claims и связывает external identity с внутренним
UUID.

После OIDC callback Portal создаёт server-side `ApplicationSession`. В cookie
`__Host-npd_session` хранится только непрозрачный случайный identifier;
application data и OIDC tokens в cookie не хранятся. Session identifier
ротируется после login и изменения привилегий. Logout отзывает session Portal и
завершает session Keycloak.

Первый login создаёт `UserProfile` со статусом `incomplete`. До завершения
обязательного onboarding доступны только анкета, правила, выбор языка и logout.

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

## PostgreSQL queues и transactional outbox

При доменном событии Portal в одной PostgreSQL transaction изменяет объект,
создаёт append-only audit event, in-app `Notification` и связанную
`EmailDelivery`. HTTP request не подключается к SMTP. Rollback основной
операции также откатывает notification и email job.

Mail worker выбирает готовые задания через row locking, фиксирует lease и
восстанавливает оставленные `sending` jobs после истечения lease. Стабильный
idempotency key не позволяет повтору browser request создать второе логическое
письмо. Redis и отдельный сетевой Email API в MVP отсутствуют.

## Очередь инфраструктурных операций

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
- Web, mail worker и operation worker получают разные credentials.
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
- host-only cookie `__Host-npd_session` с `Secure`, `HttpOnly`, `SameSite=Lax`
  и ограниченным сроком жизни;
- CSRF protection для всех state-changing requests;
- rotation session identifier после login и изменения privileges;
- проверка OIDC `iss`, `aud`, `exp`, подписи, `state` и `nonce`;
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
- metrics — request latency/error rate, DB pool, mail/operation queue depth и
  delivery/operation status;
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
- OIDC callback с test double и development Keycloak;
- server-side session create, rotate, revoke и expiry;
- concurrent approval и повторный submit формы;
- mail/operation worker locking и recovery после остановки;
- SMTP success, temporary failure, permanent failure и повторная доставка;
- transactional создание Notification и EmailDelivery;
- adapters через fake endpoints.

### Security

- попытки доступа к чужому project/request/job;
- CSRF, session fixation и open redirect;
- privilege escalation через роли и payload;
- secret scanning и dependency audit;
- проверка upload limits до включения файлов.

### Acceptance

- полный путь заявки от applicant до ручного исполнения;
- регистрация или Google login через Keycloak без пароля Portal;
- onboarding, прикладное уведомление и письмо в Mailpit;
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

- Ansible role с web, mail worker, operation worker, Nginx, Keycloak и
  PostgreSQL client configuration;
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

### T0 — архитектурная исходная точка

Соответствует U0.

- зафиксировать модульный монолит, process boundaries и ownership данных;
- сохранить существующий Django Portal как эталон поведения на отдельной ветке;
- сохранить отдельный email prototype без развития его внешнего API;
- описать trust boundaries и злоупотребления ролями;
- определить, какие production-решения блокируют только deployment, а не
  локальную разработку.

Проверка: архитектура и implementation plan не противоречат друг другу;
локальная разработка не изменяет живой кластер.

### T1 — каркас FastAPI Portal

Соответствует технической основе U1.

- создать новый `portal/` на отдельной ветке с FastAPI application factory;
- добавить settings, SQLAlchemy, Alembic и локальную PostgreSQL-среду;
- подключить Jinja2, локальные Tabler assets и базовый layout;
- добавить базовый CI;
- реализовать liveness, readiness и build info;
- зафиксировать application configuration schema и module boundaries.

Проверка: чистая среда поднимает приложение, применяет migrations и выполняет
tests; в приложении ещё нет infrastructure credentials.

### T2 — Keycloak identity, sessions и onboarding

Соответствует U1.

- поднять development Keycloak и подключить его SMTP к Mailpit;
- настроить confidential client `npd-portal` и Authlib OIDC flow;
- реализовать `ExternalIdentity` по `issuer + subject`;
- реализовать `UserProfile` со статусами `incomplete|complete`;
- реализовать PostgreSQL-backed `ApplicationSession`, secure cookie и logout;
- добавить WTForms, CSRF и обязательную onboarding form;
- добавить прикладные роли и deny-by-default policy helpers;
- записывать login, logout и security failures в append-only audit.

Проверка: локальный пользователь Keycloak входит без пароля Portal, завершает
onboarding и не получает доступ к чужим данным; verification email виден в
Mailpit.

### T3 — notifications и надёжная email delivery

Подготавливает уведомления U2 и является первым законченным mail increment.

- реализовать `Notification` и `EmailDelivery`;
- создавать их в одной transaction с доменным событием;
- добавить registry разрешённых versioned templates и typed context;
- рендерить `text/plain` и `text/html` с учётом preferred language;
- перенести из email prototype SMTP adapter и полезные правила idempotency;
- реализовать PostgreSQL locking, lease recovery и exponential backoff;
- разделять temporary и permanent SMTP errors;
- запустить mail worker отдельным процессом без публичного `POST /emails`.

Проверка: один внутренний event создаёт одно логическое письмо, HTTP request не
ждёт SMTP, временный сбой повторяется, а Mailpit принимает обе версии письма.

### T4 — проекты, заявки и аудит

Соответствует U2.

- перенести поведение существующих моделей Project и ProjectMembership;
- реализовать request state machine и WTForms;
- добавить reviewer/operator queues;
- добавить transitions, approvals и comments;
- реализовать ручную фиксацию исполнения;
- связать переходы с audit, in-app notification и email outbox;
- добавить SQLAdmin для диагностики и отдельный operator UI для business
  transitions.

Проверка: acceptance test проходит полный ручной процесс, доказывает object
permissions и отсутствие дубликатов transitions/notifications/email.

### T5 — первый deployment Request MVP

Соответствует контрольной точке Request MVP.

- принять оставшиеся deployment ADR;
- создать Ansible role и два runbook'а: deploy и restore;
- развернуть Nginx, Portal web, mail worker, Keycloak и PostgreSQL integration;
- подключить TLS, production SMTP, Prometheus и alerts;
- выполнить backup/restore test;
- не выдавать mail worker и web infrastructure credentials.

Проверка: ограниченная пилотная группа проходит регистрацию, onboarding и
процесс заявки и получает application email.

### T6 — operation queue и assisted provisioning

Подготавливает U7, но не включает автоматическое исполнение сразу.

- реализовать `Operation`, locking, idempotency и reconciliation;
- запустить operation worker с отдельным service account;
- добавить read-only identity preflight;
- связать ручной runbook с technical result;
- только после проверки добавить allowlisted provisioning adapter.

Проверка: повтор и частичный сбой не создают разные UID или аккаунты-дубликаты.

### T7 — HTCondor read integration

Соответствует U4.

- выполнить credential/ownership spike;
- реализовать read-only adapter;
- добавить mapping portal identity -> cluster login/UID;
- ограничить поля и объём выдачи;
- проверить изоляцию jobs разных пользователей.

Проверка: пользователь видит только собственные job и не получает write path.

### T8 — HTCondor template submission

Соответствует U5.

- принять ADR по write credentials;
- описать versioned job templates;
- реализовать validation и resource limits;
- добавить submit/remove operations и reconciliation;
- определить bounded staging/retention без зависимости от JBOD.

Проверка: тестовый пользователь создаёт и удаляет только собственную job, а
повторный HTTP request не создаёт вторую.

### T9 — VM request registry

Соответствует U6.

- реализовать тип заявки и quota review;
- хранить operator-entered VMID, owner и expiry;
- добавить уведомление о сроке;
- оставить Proxmox mutation ручной.

Проверка: каждая учтённая VM связана с одобренной заявкой.

### T10 — отдельные automation adapters

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

Архитектурная исходная точка T0 зафиксирована. Следующий результат — T1:
минимальный FastAPI Portal с application factory, конфигурацией, PostgreSQL,
SQLAlchemy, Alembic, Jinja2, health endpoints и базовыми tests.

T1–T4 реализуются в отдельной ветке локально и не меняют живой кластер.
Неопределённые production hostname, TLS, SMTP provider и deployment topology
блокируют T5, но не блокируют создание и тестирование приложения.

## Связанные документы

- [Продуктовый план](user-platform-plan.md).
- [Архитектура Portal, идентификации и электронной почты](../architecture/identity-and-email.md).
- [План Azure edge и WireGuard](../network/azure-edge-vpn-plan.md).
- [Пользовательский доступ](../services/user-access.md).
- [HTCondor](../services/htcondor.md).
- [Выдача пользователя](../runbooks/provision-user.md).
- [Архитектура кластера](../architecture/overview.md).
- [Правила документации](../documentation-guide.md).
