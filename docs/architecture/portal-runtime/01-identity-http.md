# Поток 1. HTTP, вход, сессия, CSRF и выход

Статус: current
Последняя проверка: 2026-10-10
Назначение: карта кода входа через OIDC, application-сессий, CSRF и выхода
Источник истины для: не является источником истины; первичен код в portal/app/

[Карта всех потоков](../portal-runtime-walkthrough.md) · Код:
[`app/main.py`](../../../portal/app/main.py),
[`app/identity/`](../../../portal/app/identity/),
[`app/web/router.py`](../../../portal/app/web/router.py).

## Что создаётся при запуске web-процесса

`app.main.create_app()` создаёт `FastAPI`, подключает `SessionMiddleware`,
статику `/static` и роутеры web, identity, system, compute, VM и SSH-ключей.
`SessionMiddleware` нужен Authlib для временного OIDC `state`: cookie
`npd_oidc_state`, срок 600 секунд, `SameSite=Lax`. Это **не** cookie входа в
Portal. Постоянная application session создаётся позднее в callback и
называется `npd_session`.

`app.core.config.Settings` читает `.env`: URL БД, адрес issuer и credentials
OIDC, секрет подписи временного OIDC state, время жизни application session,
секрет CSRF и флаг Secure для cookies. `SecretStr` скрывает значение секрета
при обычном выводе объекта настроек; это не шифрование данных в `.env`.

`app.identity.oidc.oauth.register(name="keycloak", ...)` создаёт OIDC-клиент.
Его `server_metadata_url` указывает на discovery-документ realm Keycloak,
scope запрашивает `openid profile email`. Portal использует Keycloak как
поставщика идентичности; пароли и Google OIDC, если он настроен в Keycloak,
не обрабатываются кодом Portal.

## Цепочка входа

```text
GET /auth/login или /auth/register
  -> login()/register()
  -> oauth.keycloak.authorize_redirect(request, callback URL)
  -> браузер уходит в Keycloak
  -> Keycloak возвращает браузер на /auth/callback
  -> auth_callback()
  -> authorize_access_token() и token["userinfo"]
  -> get_or_create_user()
  -> create_application_session()
  -> commit транзакции
  -> 303 /dashboard + Set-Cookie: npd_session
```

`register()` отличается от `login()` параметром `prompt="create"`: он
просит Keycloak показать регистрацию, но не создаёт отдельного Portal-аккаунта
своими силами. Оба пути возвращаются в один callback.

В `auth_callback()` Authlib обрабатывает OIDC-ответ и отдаёт `userinfo`. Код
Portal затем отдельно требует непустой `email` и **ровно**
`email_verified is True`; иначе 403. Далее `_login_and_create_session()`
оборачивает всю последовательность в одну транзакцию `db.begin()`. Внутри
неё:

1. `get_or_create_user(db, issuer=userinfo["iss"],
   subject=userinfo["sub"], email=email)` ищет `ExternalIdentity` по паре
   `(issuer, subject)`. Эта пара идентифицирует **способ входа**, а не email.
2. При найденной identity обновляются её email и `email_verified`, затем
   загружается связанный `User`. Если `User` отсутствует, это ошибка
   целостности данных, а не повод создать другого пользователя.
3. При новой identity добавляется `User`; `flush()` даёт его UUID в той же
   транзакции. Затем добавляется `ExternalIdentity` и через
   `assign_starter_quota()` — `UserQuota` с планом `starter`. Если план не
   найден или неактивен, транзакция откатывается: половинчатый аккаунт не
   фиксируется.
4. Callback отклоняет `User.is_active is False` и вызывает
   `create_application_session()`. Тот генерирует случайный
   `secrets.token_urlsafe(32)`, сохраняет SHA-256 hash токена и `expires_at`
   в `ApplicationSession`, а исходный токен возвращает только обработчику.
5. Выход из `db.begin()` фиксирует вместе User/identity/quota/session либо
   откатывает всё. После commit браузер получает `303` на `/dashboard` и
   `npd_session` со свойствами `HttpOnly`, `SameSite=Lax`, `path=/`, `max_age`
   из настроек; `Secure` зависит от `oidc_cookie_secure` (локальный HTTP
   использует `False`, production HTTPS должен использовать `True`).

Если два параллельных входа одной identity одновременно проходят путь
создания, проигравший ловит `IntegrityError` на
`uq_external_identities_issuer_subject` при commit. Callback откатывает
транзакцию и повторяет её целиком один раз: повтор уже видит
закоммиченную identity победителя и завершается обычным входом. Каждый
запрос получает собственную `ApplicationSession` — двойной логин того же
пользователя не конфликт, а два нормальных входа.

Почему `User.id` отдельный: email может измениться, а Keycloak может
подключить иной способ входа. Владение квотой, ключами и VM не должно
меняться вслед за адресом почты. Текущий код автоматически **не связывает**
разные `(issuer, subject)` по совпавшему email — это отдельная задача
безопасного account linking.

## Что происходит на каждом защищённом запросе

```text
FastAPI Depends(get_current_user)
  -> Cookie(alias="npd_session")
  -> get_user_by_session_token(db, token)
  -> SHA-256(token) -> SELECT ApplicationSession по token_hash
  -> SELECT User по session.user_id
  -> проверки revoked_at, expires_at, user.is_active
  -> валидная сессия: обновить last_seen_at не чаще раза в 5 минут
  -> вернуть User в обработчик или HTTP 401
```

`get_user_by_session_token()` только **ищет** пару `(User,
ApplicationSession)`. Проверку срока, отзыва и активности делает
`get_current_user()`, так что все защищённые маршруты используют одно и то
же правило. При отсутствии cookie, неизвестном hash, отозванной или
просроченной сессии клиент получает 401. Если сессия ссылается на
несуществующий `User`, возникает `RuntimeError`: это сигнал повреждения
инварианта БД. `last_seen_at` обновляется только после успешных проверок и
не чаще одного раза в `LAST_SEEN_UPDATE_INTERVAL` (5 минут): Core-UPDATE с
отдельным commit'ом выполняется в `get_current_user()`. Троттлинг не
превращает обычный визит в запись на каждый HTTP-запрос; скользящий срок
при этом не реализован — `expires_at` остаётся фиксированным от входа.

`Depends(get_current_user)` — инструкция FastAPI вызвать эту функцию до
обработчика и подставить результат в параметр `user`. Так же
`Depends(get_db)` подставляет `AsyncSession`; `Cookie(alias="npd_session")`
читает значение из HTTP cookie. Обработчик не вызывает эти функции вручную
и не получает `User` из поля формы, которое browser мог бы подделать.

FastAPI кэширует результат одинаковой зависимости в пределах запроса.
Поэтому и обработчик, и его вложенная зависимость `get_current_user` могут
получать один экземпляр `AsyncSession` через `get_db`, а не две независимые
транзакции. `get_db()` открывает `SessionLocal()` и закрывает сессию после
запроса; commit для мутирующих HTTP-маршрутов делают сами обработчики.

## CSRF — отдельная проверка POST

Browser автоматически прикрепляет `npd_session` к запросам своего origin.
Без CSRF-защиты страница другого сайта могла бы вынудить browser отправить
POST с этой cookie. `SameSite=Lax` уменьшает риск, но текущие POST явно
проверяют дополнительный токен.

`make_csrf_token(session_token)` вычисляет HMAC-SHA256 от строки
`"csrf-v1:" + session_token` с отдельным `settings.csrf_secret`. Токен
детерминирован для данной application session; отдельной таблицы CSRF нет.
`verify_csrf()` получает cookie `npd_session`, затем ищет токен:

1. сначала в заголовке `X-CSRF-Token` для JSON API;
2. если заголовка нет и `Content-Type` равен
   `application/x-www-form-urlencoded`, в поле формы `csrf_token`.

При отсутствии cookie — 401, токена — 403, неверном HMAC — 403. Сравнение
идёт через `hmac.compare_digest`. Это доказывает, что отправитель видел
токен, рассчитанный для данной сессии; **авторизацию пользователя** всё равно
делает `get_current_user()`. `verify_csrf` подключён через
`dependencies=[Depends(verify_csrf)]` к мутирующим маршрутам.

`GET /auth/csrf` сначала требует `get_current_user()`, затем возвращает
токен в JSON с `Cache-Control: no-store`. HTML-кабинет вычисляет тот же токен
на сервере при `GET /dashboard` и вставляет в скрытые поля форм.
`templates/base.html` делает это для выхода; `templates/dashboard.html` —
для создания/запуска VM. Сам `GET /dashboard` сейчас не выставляет
`Cache-Control: no-store`; это отдельный пункт для hardening.

## Выход

```text
POST /auth/logout
  -> verify_csrf()
  -> logout()
  -> revoke_user_session(db, cookie) внутри db.begin()
  -> Keycloak discovery: end_session_endpoint
  -> 303 на URL Keycloak с client_id и post_logout_redirect_uri
  -> Delete-Cookie: npd_session
  -> Keycloak возвращает на /auth/logged-out -> 303 /
```

`revoke_user_session()` хеширует cookie и выставляет `revoked_at` у найденной
записи. Повторный выход безопасен: отсутствующая или уже отозванная запись
ничего не меняет. Удаление browser cookie не заменяет server-side revoke:
похищенный старый токен после отзыва также перестаёт проходить
`get_current_user()`.

Logout отправляет Keycloak `end_session` **без** `id_token_hint`. Portal
намеренно не хранит `id_token` пользователя: это OIDC-артефакт с PII и
правом завершать SSO-сессию, а ещё один bearer-подобный секрет в БД
противоречит политике минимального хранения (по тому же принципу Portal
хранит только SHA-256 hash сессионного токена). Побочный эффект — Keycloak
показывает страницу подтверждения перед выходом. Это принято как цена
решения, а не недоделка; способ вернуться к silent logout, если UX станет
проблемой, — [ID-002](../../project/open-issues.md).

## Другие HTTP-маршруты этого слоя

| Маршрут | Функция | Смысл |
|---|---|---|
| `GET /` | `web.home` | Публичная HTML-страница; не требует входа. |
| `GET /dashboard` | `web.dashboard` | Требует пользователя; показывает данные только его объектов. |
| `GET /auth/me` | `identity.me` | Проверяет session dependency и возвращает `user_id`. |
| `GET /health` | `system.health` | Проверяет, что web-процесс отвечает; БД не проверяет. |
| `GET /health/ready` | `system.readiness` | Выполняет `SELECT 1`; при SQLAlchemy-ошибке возвращает 503. |

`web.router` создаётся с `include_in_schema=False`: HTML-маршруты не
засоряют OpenAPI `/docs`. JSON API-маршруты остаются видимыми там.

## Чего эта цепочка не делает

- Portal не хранит и не проверяет пользовательские пароли.
- Совпавший email не склеивает автоматически две внешние identity.
- CSRF-токен не даёт доступ без валидной application session.
- `GET /auth/me` не обновляет `last_seen_at` и не продлевает срок сессии.
- `GET /health` не доказывает доступность PostgreSQL; для этого есть ready.
