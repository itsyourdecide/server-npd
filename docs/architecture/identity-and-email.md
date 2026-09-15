# Целевая архитектура Portal, идентификации и электронной почты

Статус: draft
Последняя редакция: 2026-09-14
Назначение: описать итоговое устройство Portal, регистрации, входа и почтовых
уведомлений пользовательской платформы NPD
Источник истины для: целевой схемы Portal, Keycloak, PostgreSQL, mail worker и
SMTP; не является runbook развёртывания

## Общая схема

```text
                            +--------------------+
                            | Google             |
                            | OpenID Connect     |
                            +---------+----------+
                                      |
                                      v
+---------+                  +--------------------+
| Browser |<---------------->| Keycloak           |
+----+----+                  |                    |
     |                       | local accounts     |
     |                       | Google broker      |
     |                       | email verification |
     |                       | password recovery  |
     |                       +----+-----------+---+
     |                            |           |
     |                 OIDC code  |           | SMTP
     |                            |           |
     v                            v           |
+----------------------+    +------------------------+ |
| Nginx                |--->| Portal web             | |
+----------------------+    | FastAPI + Jinja2/HTMX  | |
                            +-----------+------------+ |
                                        |              |
                                        v              |
                                  +------------+       |
                                  | PostgreSQL |       |
                                  +-----+------+       |
                                        |              |
                                        v              v
                                  +--------------------+
                                  | Mail worker        |
                                  +---------+----------+
                                            |
                                            | SMTP
                                            v
                                  +--------------------+
                                  | SMTP relay         |
                                  |                    |
                                  | Mailpit: dev       |
                                  | provider: prod     |
                                  +--------------------+
```

Keycloak и Portal используют один SMTP relay, но отвечают за разные категории
писем. В development SMTP принимает Mailpit. В production используется
университетский или внешний SMTP relay.

Архитектура является модульным монолитом с отдельными процессами. Portal web и
mail worker собираются из одного repository и одной application codebase,
используют общие прикладные модели и одну application database, но запускаются
и масштабируются независимо. Keycloak и SMTP relay являются отдельными
инфраструктурными сервисами.

## Архитектурные принципы

Portal разделён на четыре уровня:

```text
HTTP и HTML
FastAPI, Jinja2, HTMX, WTForms
        |
        v
Application services
регистрация профиля, проекты, заявки, уведомления
        |
        v
Domain rules
состояния, переходы, permissions, ограничения
        |
        v
Infrastructure adapters
PostgreSQL, Keycloak, SMTP, cluster operations
```

HTTP handlers принимают и проверяют входные данные, определяют текущего
пользователя, вызывают application service и формируют response. Бизнес-правила
не размещаются в handlers, HTML templates, ORM hooks или mail worker.

Внешние системы доступны через явные adapters. Замена OIDC provider, SMTP
relay, способа выполнения cluster operations или web framework не меняет
domain rules. Абстракции вводятся вокруг значимых внешних границ, а не вокруг
каждой используемой библиотеки.

Модули Portal находятся в одной codebase и взаимодействуют через application
services, а не через внутренние HTTP API. Каждый модуль владеет своими
операциями и не изменяет чужие таблицы напрямую.

## Ответственность компонентов

### Keycloak

Keycloak является единственным публичным Identity Provider платформы и
отвечает за:

- регистрацию по email;
- хранение и проверку пользовательских credentials;
- подтверждение email;
- восстановление пароля;
- вход через Google;
- связывание способов входа;
- MFA и защиту от перебора;
- пользовательские authentication sessions;
- выпуск подписанных OIDC tokens для Portal.

Пользователь вводит пароль только на страницах Keycloak. Portal не принимает,
не передаёт и не хранит пользовательские пароли.

### Portal

Portal доверяет identity, подтверждённой Keycloak, и отвечает за:

- локальную application session после OIDC login;
- профиль пользователя кластера;
- обязательный onboarding после первого входа;
- проекты и membership;
- заявки и переходы их состояний;
- роли `applicant`, `user`, `project_lead`, `reviewer`, `operator` и `admin`;
- связь portal user с Unix login и numeric UID;
- SSH keys и состояние доступа к кластеру;
- аудит прикладных действий;
- in-app и email-уведомления о событиях портала.

Portal является server-rendered web application. Основной runtime stack:

```text
FastAPI                  HTTP routing и middleware
Jinja2 + Tabler + HTMX   server-rendered UI
WTForms                  HTML forms и CSRF
Pydantic                 входные и внутренние typed schemas
SQLAlchemy               persistence mapping
Alembic                  database migrations
Authlib                  OIDC client
Babel + gettext          локализация
SQLAdmin                 ограниченный технический admin UI
pytest                   automated tests
```

Этот набор не образует отдельные сетевые сервисы. Библиотеки используются
внутри одного приложения и могут заменяться независимо при сохранении границ
application services и infrastructure adapters.

Регистрация в Keycloak создаёт возможность войти в Portal, но не выдаёт SSH,
Unix account, UID, HTCondor access или инфраструктурные полномочия. Доступ к
кластеру появляется только после отдельной заявки и утверждённого процесса
исполнения.

### Mail worker

Mail worker является отдельным процессом той же application codebase. Он:

- читает задания из PostgreSQL;
- блокирует одно задание на время обработки;
- строит письмо только из разрешённого шаблона;
- отправляет сообщение через SMTP relay;
- фиксирует результат попытки;
- повторяет временные ошибки с задержкой;
- переводит постоянные или исчерпавшие попытки ошибки в `failed`;
- восстанавливает задания после остановки worker по ограниченному lease.

Worker не принимает произвольные SMTP credentials, sender, recipient, subject
или тело письма из браузера.

## Модули Portal

Целевая codebase содержит как минимум следующие прикладные модули:

```text
identity       связь Portal user с Keycloak identity
profiles       onboarding и данные пользователя
projects       проекты и membership
requests       заявки и их state machine
access         Unix account, UID, SSH keys и cluster access
notifications in-app notifications
mail           постановка и доставка application email
audit          append-only audit events
```

Модуль `mail` предоставляет внутреннюю операцию постановки типизированного
письма в очередь. Остальные модули не подключаются к SMTP и не создают
произвольные email bodies.

## Границы развертывания

Текущая система не разделяется на прикладные микросервисы. Portal web и mail
worker развёртываются как отдельные процессы, но остаются частями одного
модульного приложения. Между прикладными модулями нет внутренних HTTP-вызовов,
service-to-service tokens и отдельных копий одних и тех же данных.

Такое устройство сохраняется, пока модули имеют одного владельца, выпускаются
вместе и требуют согласованных PostgreSQL transactions. Отдельный модуль
выделяется в самостоятельный сервис только при появлении измеримой причины:

- нескольких независимых приложений-потребителей;
- отдельного владельца или цикла выпуска;
- необходимости независимого масштабирования;
- требования изолировать secrets, данные или сбои;
- устойчивого внешнего контракта и готовности поддерживать его версии.

Mail worker масштабируется независимо без превращения модуля `mail` в сетевой
сервис. Если почтовая подсистема позднее будет выделена, внутренний mail adapter
заменяется публикацией события или вызовом API. Новый сервис получает
собственное хранилище и не изменяет таблицы Portal напрямую.

## Модель идентичности

Постоянная внешняя identity определяется парой:

```text
issuer + subject
```

Пример:

```text
issuer  = https://<auth-host>/realms/npd
subject = 3df991bc-7eb4-4e0d-91ec-8b6d7ac52ec4
```

Keycloak выдаёт один `subject` для связанной учётной записи независимо от
того, вошёл пользователь по паролю или через Google. Portal хранит эту пару в
`ExternalIdentity` и связывает её с внутренним UUID пользователя.

Email является обязательным подтверждённым контактным атрибутом и может
использоваться как имя входа. Проекты, заявки, роли, аудит и ресурсы связаны с
внутренним UUID пользователя, а не со строкой email.

Portal принимает адрес для уведомлений только при
`email_verified = true`. При каждом OIDC login Portal синхронизирует разрешённые
profile claims из Keycloak:

```text
sub
email
email_verified
given_name
family_name
```

Изменение email выполняется через Keycloak Account Console. Новый адрес
становится активным после подтверждения. Совершенно другой Google account не
получает доступ к существующему portal profile без явного связывания identity.

## Onboarding и профиль пользователя

Первый успешный вход создаёт в Portal минимальный `UserProfile` со статусом
`incomplete`. После создания application session пользователь перенаправляется
на обязательную анкету:

```text
Keycloak authentication
        |
        v
Portal application session
        |
        v
UserProfile: incomplete
        |
        v
Onboarding form
        |
        v
UserProfile: complete
        |
        v
Cluster access request
```

Пока профиль не заполнен, пользователю доступны только:

- onboarding form;
- просмотр правил и политики обработки данных;
- изменение языка;
- выход из аккаунта.

Создание заявок, просмотр внутренних разделов и получение доступа к кластеру
становятся доступны после заполнения обязательных полей.

### Данные анкеты

Анкета содержит:

- имя и фамилию, предварительно заполненные из подтверждённой identity;
- университет или организацию;
- факультет;
- кафедру;
- академический статус;
- курс обучения;
- научного руководителя;
- направление исследования или работы;
- цель использования кластера;
- предпочитаемый язык;
- подтверждение согласия с действующей версией правил и политики обработки
  данных.

Академический статус выбирается из серверного списка:

```text
student
postgraduate
teacher
staff
external_researcher
```

`course` обязателен только для `student`. Факультет и кафедра выбираются из
справочников Portal, когда подходящее значение существует. Для внешнего
исследователя организация и подразделение могут вводиться отдельно.

Минимальные служебные поля профиля:

```text
onboarding_status
onboarding_completed_at
academic_status
organization
faculty
department
course
supervisor
research_area
cluster_usage_purpose
preferred_language
policy_version
policy_accepted_at
```

Значения анкеты являются заявленными пользователем данными. Они помогают
reviewer рассмотреть заявку, но сами по себе не назначают роли, квоты, Unix
account или доступ к ресурсам.

Пользователь может обновлять разрешённые поля анкеты через Portal. Значимые для
действующей заявки изменения получают audit event. Подтверждение личности,
email и способов входа остаётся ответственностью Keycloak.

## Регистрация по email и паролю

```text
Browser -> Portal -> Keycloak registration
Keycloak -> SMTP relay -> verification email
User -> verification link -> Keycloak
Keycloak -> OIDC authorization code -> Portal
Portal -> create/find ExternalIdentity and UserProfile
```

Последовательность:

1. Portal перенаправляет неаутентифицированного пользователя в Keycloak.
2. Пользователь открывает регистрацию и вводит email.
3. Keycloak создаёт неподтверждённую учётную запись.
4. Keycloak отправляет одноразовую verification link через SMTP.
5. Пользователь подтверждает владение адресом и устанавливает пароль.
6. Keycloak завершает Authorization Code Flow.
7. Portal проверяет token и создаёт профиль с минимальной ролью `applicant`.
8. Portal направляет пользователя на обязательную onboarding form.
9. После заполнения анкеты пользователь может создать заявку на доступ.

## Вход через Google

```text
Browser -> Portal -> Keycloak -> Google
Google -> Keycloak -> Portal
```

Последовательность:

1. Пользователь выбирает Google на странице Keycloak.
2. Keycloak перенаправляет browser в Google.
3. Google аутентифицирует пользователя и возвращает подтверждённую identity.
4. Keycloak находит связанную учётную запись или создаёт новую.
5. Keycloak возвращает Portal собственный OIDC authorization code.
6. Portal создаёт application session.
7. При первом входе Portal направляет пользователя на обязательную onboarding
   form.

Пользователь, впервые вошедший через Google, не создаёт и не вводит отдельный
пароль платформы.

Если в Keycloak уже существует учётная запись с тем же email, связывание
подтверждается одноразовой ссылкой на подтверждённый адрес. После первого
связывания вход через Google выполняется без дополнительных шагов.

## OIDC-клиент Portal

В Keycloak существует отдельный confidential client `npd-portal` со
следующими свойствами:

- Authorization Code Flow;
- PKCE;
- точные allowlisted redirect URI;
- HTTPS для всех production redirect URI;
- отключённый Implicit Flow;
- отключённый Direct Access Grant;
- короткоживущие tokens;
- проверка `iss`, `aud`, `exp`, подписи, `state` и `nonce`;
- client credential хранится вне Git.

OIDC flow выполняется через Authlib. После callback Portal создаёт server-side
application session в PostgreSQL. В browser cookie хранится только случайный
непрозрачный session identifier; профиль, роли и OIDC tokens в cookie не
хранятся и frontend-коду не передаются.

Logout отзывает application session и перенаправляет пользователя на OIDC
logout Keycloak, после чего browser возвращается на публичную страницу Portal.

## Сессии, cookies и CSRF

Application session имеет ограниченный срок жизни, время последней активности,
состояние отзыва и связь с внутренним UUID пользователя. Session identifier
создаётся криптографически стойким генератором; в PostgreSQL хранится его hash.
Identifier меняется после успешного login, изменения уровня доступа и других
security-sensitive transitions.

Session cookie называется `__Host-npd_session` и имеет следующие свойства:

```text
Secure
HttpOnly
SameSite=Lax
Path=/
без Domain
ограниченный Max-Age
```

Production Portal доступен только через HTTPS. Portal доверяет forwarded
headers только от известного reverse proxy. Logout удаляет cookie и отзывает
серверную session; истёкшие и отозванные sessions периодически удаляются.

Все browser requests, изменяющие состояние и использующие cookie session,
защищаются CSRF token. WTForms создаёт и проверяет token для HTML forms. HTMX
requests передают тот же token. `SameSite` является дополнительной защитой, а
не заменой CSRF validation.

## Формы и проверка данных

WTForms отвечает за HTML fields, преобразование значений, сообщения об ошибках
и CSRF. Pydantic schemas описывают typed input для application services и
интеграционных границ. Domain services повторно проверяют бизнес-инварианты,
которые нельзя доверять состоянию формы.

Ошибки формы отображаются рядом с соответствующими полями. Справочники,
условная обязательность полей и допустимые переходы состояний всегда
проверяются на сервере независимо от browser validation.

## Авторизация и permissions

Keycloak подтверждает identity, но прикладные роли и доступ к объектам
определяет Portal. Проверка permissions выполняется внутри application service
до чтения чувствительных данных или изменения состояния, а не только в router
или интерфейсе.

Базовые правила реализуются явными policy-функциями и используют:

- роль пользователя;
- membership в проекте;
- владельца или автора объекта;
- текущее состояние заявки;
- статус профиля и cluster access;
- запрет конфликта интересов, включая обработку собственной заявки.

По умолчанию доступ запрещён. Все значимые разрешения и запреты покрываются
автоматическими тестами. Внешний policy engine вводится только если количество
ролей, организаций и наследуемых правил сделает явные policies недостаточными.

## Admin и operator UI

SQLAdmin предоставляет ограниченный технический интерфейс для диагностики и
безопасного CRUD справочных данных. Доступ к нему разрешён только выделенной
роли `admin` и дополнительно ограничивается на инфраструктурном уровне.

Изменение состояния заявок, выдача cluster access, повтор операций, управление
ролями и повторная отправка писем выполняются через отдельный operator UI и
application services. Generic admin не используется для обхода state machine,
permissions или audit. Append-only audit events нельзя редактировать или
удалять через admin UI.

## Категории писем

### Authentication emails

Keycloak формирует и отправляет:

- подтверждение email;
- восстановление пароля;
- подтверждение смены email;
- подтверждение связывания identity;
- security notifications и required actions.

Ссылки и одноразовые токены этих писем создаёт только Keycloak. Portal и mail
worker не формируют authentication links.

### Application emails

Portal формирует и отправляет:

- изменение состояния заявки;
- отправку заявки на рассмотрение;
- одобрение или отклонение;
- начало и завершение исполнения;
- результат выдачи доступа;
- ошибки операций, требующие действий пользователя или оператора;
- напоминания об окончании доступа или ресурса.

Application email содержит минимальный безопасный контекст и ссылку на Portal.
Комментарии reviewer, технический stdout, внутренние адреса, credentials и
другие чувствительные сведения в письмо не включаются.

## Создание application email

При доменном событии Portal в одной PostgreSQL transaction:

1. изменяет состояние объекта;
2. создаёт append-only audit event;
3. создаёт in-app `Notification`;
4. создаёт связанную `EmailDelivery` в состоянии `pending`;
5. фиксирует transaction.

Пользовательский HTTP request не подключается к SMTP и не ждёт завершения
отправки. Если transaction откатывается, notification и email job также не
создаются.

Одна доменная операция имеет стабильный idempotency key. Повтор browser
request или повторная обработка события не создаёт второе логическое письмо.

## Модель доставки

`Notification` описывает прикладное событие и его отображение внутри Portal.
`EmailDelivery` описывает доставку этого события по email.

Минимальные поля `EmailDelivery`:

```text
id
notification_id
idempotency_key
recipient_email
template_key
template_version
language
status
attempts
next_attempt_at
locked_at
lease_expires_at
last_error_code
message_id
created_at
sent_at
```

Адрес, язык и версия шаблона фиксируются в момент постановки задания в очередь.
SMTP password, OIDC tokens и полные исключения с чувствительными данными в
таблице не хранятся.

Состояния доставки:

```text
pending -> sending -> sent
                    +-> retryable -> sending
                    +-> failed
```

Временные ошибки получают exponential backoff и ограниченное количество
попыток. Ошибки адреса или отклонение сообщения по постоянной причине сразу
переходят в `failed`.

SMTP обеспечивает как минимум однократную попытку доставки, но не гарантирует
абсолютный exactly-once после неоднозначного network timeout. Worker использует
стабильный `Message-ID`, idempotency key и lease recovery. Прикладные письма
проектируются так, чтобы редкий повтор не выполнял действие сам по себе.

## Шаблоны и локализация

Интерфейс Portal локализуется через Babel, gettext catalogs и Jinja2 i18n.
Поддерживаемые языки задаются серверной конфигурацией. Предпочтение
аутентифицированного пользователя хранится в `UserProfile.preferred_language`;
до входа язык выбирается из безопасного cookie или заголовка browser с
fallback на язык Portal по умолчанию.

Текст интерфейса, form labels, validation messages и письма используют
translation keys. Пользовательские значения, identifiers, имена ролей в базе и
audit payloads не используются как переводимый текст.

Keycloak и Portal имеют независимые наборы UI и email templates и независимые
translation catalogs.

Keycloak templates:

```text
verify-email
reset-password
update-email
link-identity
security-event
```

Portal templates:

```text
request-submitted
request-state-changed
request-approved
request-rejected
request-execution-finished
operation-failed
access-expiring
```

Каждое письмо Portal имеет `text/plain` и `text/html` версии. Subject, sender и
структура сообщения определяются серверным template registry. Данные события
проходят отдельную typed validation до рендеринга.

Язык email берётся из `UserProfile.preferred_language`. Поддерживаемые значения
совпадают с языками Portal. Изменение языка влияет на новые письма и не меняет
уже поставленные задания.

## Development

В development Keycloak и Portal worker отправляют SMTP на Mailpit:

```text
SMTP host: mailpit
SMTP port: 1025
TLS: disabled внутри изолированной development-сети
Authentication: disabled
```

Mailpit перехватывает все письма и не отправляет их в Internet. Через Mailpit
UI проверяются обе версии письма, заголовки, ссылки и повторные попытки.

Development использует тестовые hostname и callback URI. Production secrets,
Google client secret и настоящие адреса пользователей в development не
используются.

## Production

В production Keycloak и Portal worker подключаются к утверждённому SMTP relay
через TLS и отдельные credentials. Рекомендуемое разделение отправителей:

```text
accounts@<mail-domain>       authentication emails Keycloak
notifications@<mail-domain> application emails Portal
```

Для mail domain настраиваются SPF, DKIM и DMARC. SMTP credentials хранятся вне
Git и доступны только соответствующему процессу.

Keycloak, Portal web и Portal mail worker запускаются как отдельные процессы.
Keycloak хранит identity data в собственной database/schema. Portal и mail
worker используют общую application database, но разные service accounts и
минимально необходимые permissions.

## Наблюдаемость

Для почтовой подсистемы публикуются:

- количество `pending`, `retryable` и `failed` deliveries;
- возраст самого старого `pending` задания;
- количество отправок и ошибок по безопасной категории;
- длительность SMTP attempt;
- состояние mail worker;
- результат тестового SMTP probe без отправки пользователю.

Логи содержат delivery UUID, event type, attempt number и безопасную категорию
ошибки. Полное тело письма, password, token, SMTP credential и чувствительные
данные заявки в логи не записываются.

Статус `sent` означает, что SMTP relay принял сообщение. Фактическая доставка
в mailbox, bounce и complaint являются отдельными событиями и учитываются при
наличии соответствующего интерфейса у production-провайдера.

## Связанные документы

- [Архитектура кластера](overview.md).
- [План пользовательской платформы](../project/user-platform-plan.md).
- [Технический план пользовательской платформы](../project/user-platform-implementation-plan.md).
- [Development deployment Portal](../runbooks/portal-dev-deploy.md).
