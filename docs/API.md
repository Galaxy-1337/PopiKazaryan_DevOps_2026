# Описание HTTP API

Базовый адрес: `http://127.0.0.1:8000`
Версия API: `v0.1.0`
Префикс прикладных методов: `/api/v1`

Живая документация: `/docs` (Swagger UI), `/redoc` (ReDoc), `/openapi.json` (схема OpenAPI 3.1) —
служебные адреса, доступные только администратору.

**Сессия обязательна.** Без действующей сессии открыты только адреса входа (`GET`/`POST /login`,
`POST /api/v1/auth/login`), выход `GET /logout`, статика `/static/...`, `/favicon.ico` и
служебная проверка `GET /internal/health`. У каждого метода ниже указано, кому он доступен:
**обе роли**, **только администратор** или **только участник**.

---

## Общие соглашения

### Доступ и роли

В системе две роли учётной записи (`users.role`, перечисление `UserRole`): `admin`
(администратор) и `participant` (участник). Роли в реестре участников нет.

| Ситуация | Ответ |
|---|---|
| Сессии нет, запрос к `/api/*` или к `/health`, `/version`, `/openapi.json` | `401 unauthorized` |
| Сессии нет, запрос к странице браузера (`/`, `/docs`, `/redoc`, любая другая) | перенаправление на `/login` (HTTP 303) |
| Участник обращается к разделу администратора | `403 admin_only` |
| Администратор вызывает действие участника | `403 participant_only` |
| Участник обращается к объекту чужой заявки | `403 forbidden_not_owner` или `403 forbidden_foreign_*` |

### Формат данных

Запросы и ответы — `application/json; charset=utf-8`. Даты — `YYYY-MM-DD`, даты со временем —
ISO 8601 в UTC (`2026-01-15T10:00:00Z`). Денежные суммы передаются строками с двумя знаками
после запятой (`"3500.00"`).

### Единый формат ошибки

Любой ответ с кодом `>= 400` имеет вид:

```json
{
  "error": {
    "code": "section_capacity_exceeded",
    "message": "В секции «CI/CD и автоматизация релизов» нет свободных мест (3 из 3 занято)",
    "details": null
  }
}
```

| Код HTTP | `error.code` | Когда возникает |
|---|---|---|
| 400 | `invalid_conference_dates`, `section_not_in_conference`, `hotel_not_allowed_for_online` | некорректные данные, которые нельзя проверить схемой |
| 400 | `invalid_credentials` | неверный пароль или неизвестный адрес при входе (текст сообщения одинаков в обоих случаях) |
| 401 | `unauthorized` | запрос к защищённому методу или служебному адресу (`/health`, `/version`, `/openapi.json`) без действующей сессии |
| 403 | `admin_only` | раздел доступен только администратору, а вошёл участник |
| 403 | `participant_only` | действие доступно только участнику: администратор не подаёт заявки и не действует от своего имени |
| 403 | `forbidden` | у учётной записи нет права, требуемого методом |
| 403 | `user_disabled` | учётная запись отключена |
| 404 | `not_found`, `http_error` | объект или маршрут не найден |
| 409 | код правила предметной области | нарушено правило (см. таблицу ниже) |
| 422 | `validation_error` | схема запроса не прошла валидацию; поле `details` содержит список полей |
| 500 | `internal_error` | непредвиденная ошибка сервера |

Дополнительные коды `403`, связанные с принадлежностью объекта текущему пользователю:

| `error.code` | Когда возникает |
|---|---|
| `forbidden_not_owner` | запрашивается или изменяется заявка другого участника |
| `forbidden_foreign_fee` | попытка оплатить или вернуть оргвзнос по чужой заявке |
| `forbidden_foreign_thesis` | обращение к тезисам по чужой заявке |
| `forbidden_foreign_booking` | обращение к брони гостиницы по чужой заявке |
| `no_participant_profile` | у учётной записи нет связанной записи участника, а операция требует работы «от себя» |

Пример ответа 422:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Запрос содержит некорректные данные",
    "details": [
      { "field": "body.email", "message": "value is not a valid email address: An email address must have an @-sign.", "type": "value_error" }
    ]
  }
}
```

### Коды нарушения правил предметной области (HTTP 409)

| `error.code` | Правило |
|---|---|
| `invalid_status_transition` | недопустимый переход статуса заявки |
| `status_already_set` | заявка уже в этом статусе |
| `conference_inactive` | приём заявок по конференции закрыт |
| `section_closed` | секция закрыта для приёма заявок |
| `section_capacity_exceeded` | в секции нет свободных мест |
| `section_capacity_below_load` | вместимость нельзя уменьшить ниже числа поданных заявок |
| `section_title_taken` | секция с таким названием уже есть |
| `conference_slug_taken` | код конференции уже занят |
| `participant_email_taken` | участник с таким e-mail уже зарегистрирован |
| `application_duplicate` | у этого участника (по почте из заявки) уже есть заявка в этой секции |
| `application_not_editable` | редактировать можно только черновик |
| `application_not_deletable` | удалить можно только черновик или отозванную заявку |
| `fee_requires_accepted_application` | оргвзнос начисляется только по принятой заявке |
| `fee_already_paid` | оргвзнос уже оплачен |
| `fee_not_payable` | нельзя оплатить отменённый или возвращённый взнос |
| `fee_not_paid` | возврат возможен только для оплаченного взноса |
| `fee_for_withdrawn_application` | оплата по отозванной заявке запрещена |
| `refund_not_allowed_for_status` | возврат только по отозванной или отклонённой заявке |
| `invitation_exists` | приглашение по заявке уже создано |
| `invitation_already_sent` | приглашение уже отправлено |
| `invitation_cancelled` | приглашение отменено |
| `thesis_requires_accepted_application` | тезисы принимаются только по принятой заявке |
| `thesis_file_too_large` | размер файла тезисов превышает предел |
| `thesis_not_reviewable` | тезисы в этом статусе не рецензируются |
| `invalid_review_score` | оценка вне диапазона 1–10 |
| `hotel_requires_accepted_application` | бронь только по принятой заявке |
| `hotel_not_allowed_for_online` | дистанционному участнику гостиница не предоставляется |
| `hotel_dates_out_of_conference` | даты проживания вне дат конференции |
| `hotel_booking_exists` | по заявке уже есть активная бронь |
| `hotel_already_confirmed` | бронь уже подтверждена |
| `hotel_not_confirmable` | бронь отменена или истекла |
| `hotel_already_cancelled` | запрос на бронь уже отклонён |
| `hotel_not_rejectable` | нельзя отклонить истёкшую бронь |
| `hotel_confirmation_expired` | истёк срок подтверждения брони |
| `integrity_error` | операция нарушает ограничения целостности данных |

### Пагинация

Методы списков принимают `limit` (1–200, по умолчанию 50) и `offset` (>= 0) и возвращают:

```json
{ "items": [ ... ], "total": 12, "limit": 50, "offset": 0 }
```

### Трассировка запросов

Каждый ответ содержит заголовок `X-Request-ID`. Если он передан клиентом, значение
сохраняется; иначе генерируется. Значение попадает в журнал приложения и в сообщения
обработчика ошибок — по нему разбирают инциденты.

---

## Служебные методы

### `GET /internal/health` — служебная проверка работоспособности

Доступ: **без сессии**. Отдаёт только признак готовности — ни версии, ни окружения, ни сведений
о базе. Используется контейнерным `HEALTHCHECK`, скриптом `scripts/container_check.py` и CI.

```bash
curl -s http://127.0.0.1:8000/internal/health
```

```json
{ "status": "ok" }
```

Если база данных недоступна, ответ — `503` и `{"status": "degraded"}`.

### `GET /health` — проверка работоспособности

Доступ: **только администратор**. Без сессии — `401 unauthorized`, вошедшему участнику —
`403 admin_only`.

```bash
curl -s -b cookies.txt http://127.0.0.1:8000/health
```

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "ok",
  "app_env": "local",
  "checked_at": "2026-01-15T10:00:00Z"
}
```

`status` равен `ok`, когда запрос `SELECT 1` к базе выполняется успешно; иначе `degraded`,
а поле `database` содержит описание ошибки.

### `GET /version` — версия приложения

Доступ: **только администратор** (без сессии — `401 unauthorized`, участнику —
`403 admin_only`).

```json
{ "version": "0.1.0", "app_env": "local" }
```

Системы мониторинга и проверки контейнера используют `/internal/health`; `/health` и `/version`
доступны только администратору.

---

## Аутентификация и разграничение доступа

**Сессия обязательна для любого запроса.** Без неё открыты только адреса входа и служебная
проверка: `GET`/`POST /login`, `GET /logout`, `POST /api/v1/auth/login`, статика `/static/...`,
`/favicon.ico` и `GET /internal/health`. Любой другой адрес требует сессии: методы API и
служебные `/health`, `/version`, `/openapi.json` отвечают `401 unauthorized`, страницы для
браузера (`/`, `/docs`, `/redoc` и другие) перенаправляются на `/login` (HTTP 303).

В API две роли: `admin` (администратор) и `participant` (участник). Роль есть только у учётной
записи (`users.role`, перечисление `UserRole`): раздел администратора для участника отвечает
`403 admin_only`, действие участника для администратора — `403 participant_only`.

Сессия создаётся при входе и передаётся в cookie `conference_session` (флаги `HttpOnly` и
`SameSite=Lax`) либо в заголовке `Authorization: Bearer <токен сессии>` — второй вариант
предназначен для программных клиентов. Токен сессии — случайная строка из 43 символов, срок
жизни сессии — 12 часов; при выходе сессия удаляется.

Учётные записи хранятся в таблице `users`, сессии — в таблице `sessions` (см. `docs/DATA_MODEL.md`).
Пароли хранятся только в виде хеша PBKDF2-HMAC-SHA256 (200 000 итераций, случайная соль 16 байт,
формат `pbkdf2_sha256$200000$соль$хеш`); открытый пароль нигде не сохраняется и не попадает
в журналы приложения.

### `POST /api/v1/auth/login` — вход

Доступ: **без сессии** — единственный прикладной метод, открытый без входа. Тело запроса:
`{"email": "...", "password": "..."}`.

```bash
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "organizer@example.com", "password": "Conference2026"}'
```

Ответ `200` (одновременно устанавливается cookie `conference_session`) — учётная запись
администратора:

```json
{
  "id": 1,
  "email": "organizer@example.com",
  "full_name": "Администратор программы",
  "role": "admin",
  "role_title": "Администратор",
  "participant_id": null,
  "is_active": true,
  "last_login_at": "2026-09-18T20:04:54Z"
}
```

Вход участника возвращает ту же структуру с `"role": "participant"` и `"participant_id": null`:
учётная запись участника **универсальная** и с записью реестра не связана — кто именно участвует
в конференции, определяется данными конкретной заявки (ФИО и почта).

```bash
curl -s -c participant.txt -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "polzovatel@example.ru", "password": "Conference2026"}'
```

Ошибки: неверный пароль или неизвестный адрес → `400 invalid_credentials` (текст сообщения
одинаков в обоих случаях, чтобы не раскрывать существующие адреса); отключённая учётная
запись → `403 user_disabled`.

### `POST /api/v1/auth/logout` — выход

Доступ: **обе роли** (нужна активная сессия; без неё — `401 unauthorized`).
Удаляет сессию и очищает cookie.

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/logout
```

```json
{ "status": "logged_out" }
```

### `GET /api/v1/auth/me` — текущий пользователь

Доступ: **обе роли** (нужна активная сессия; без неё — `401 unauthorized`).

```bash
curl -s -b cookies.txt http://127.0.0.1:8000/api/v1/auth/me
```

Возвращает те же поля, что и вход. Без действующей сессии → `401 unauthorized`.

### `GET /api/v1/auth/roles` — роли и их права

Доступ: **только администратор**. Без сессии — `401 unauthorized`, вошедшему участнику —
`403 admin_only`. Возвращает ровно две роли с перечнем доступных им действий:

```json
[
  {
    "role": "admin",
    "title": "Администратор",
    "permissions": ["application:decide", "application:read_all", "conference:manage", "..."]
  },
  {
    "role": "participant",
    "title": "Участник",
    "permissions": ["application:create", "application:read_own", "catalog:read", "..."]
  }
]
```

Полный состав прав по ролям (`app/auth.py`, словарь `PERMISSIONS`):

| Роль | Права |
|---|---|
| `admin` | `application:decide`, `application:read_all`, `conference:manage`, `fee:manage`, `fee:read_all`, `hotel:manage`, `hotel:read_all`, `invitation:manage`, `participant:read`, `report:read`, `section:manage`, `service:read`, `thesis:read_all`, `thesis:review`, `user:manage` |
| `participant` | `application:create`, `application:read_own`, `application:withdraw_own`, `catalog:read`, `fee:pay_own`, `fee:read_own`, `fee:refund_own`, `hotel:read_own`, `hotel:request_own`, `thesis:read_own`, `thesis:submit_own` |

| Право | Назначение |
|---|---|
| `application:create` | создание своей заявки (участник) |
| `application:read_all` / `application:read_own` | просмотр всех заявок / только своих |
| `application:decide` | решения по заявкам: принятие и отклонение (администратор) |
| `application:withdraw_own` | отзыв своей заявки (участник) |
| `catalog:read` | просмотр справочников конференций и секций (участник) |
| `conference:manage` | создание и изменение конференций (администратор) |
| `section:manage` | управление секциями и их вместимостью (администратор) |
| `participant:read` | просмотр реестра участников (администратор) |
| `invitation:manage` | рассылка приглашений (администратор) |
| `fee:manage`, `fee:read_all` | начисление, возврат и просмотр всех оргвзносов (администратор) |
| `fee:read_own`, `fee:pay_own`, `fee:refund_own` | просмотр, оплата и возврат своих оргвзносов (участник) |
| `hotel:manage`, `hotel:read_all` | подтверждение, отклонение и просмотр всех броней (администратор) |
| `hotel:read_own`, `hotel:request_own` | просмотр своих броней и оформление запроса (участник) |
| `thesis:review`, `thesis:read_all` | рецензирование и просмотр всех тезисов (администратор) |
| `thesis:read_own`, `thesis:submit_own` | просмотр своих тезисов и подача тезисов (участник) |
| `report:read` | просмотр сводных отчётов (администратор) |
| `service:read` | служебные страницы `/docs`, `/redoc`, `/openapi.json`, `/health` (администратор) |
| `user:manage` | управление учётными записями (администратор) |

Права вида `*_own` означают работу только со своими данными: сервер фильтрует выборки по
участнику, связанному с учётной записью. У администратора таких прав нет — он видит все данные,
но не действует «от себя»: не подаёт заявки и не пишет тезисы.

### Защита маршрутов

| Маршрут | Доступ |
|---|---|
| `GET`/`POST /login`, `GET /logout`, `POST /api/v1/auth/login` | без сессии |
| `GET /internal/health` | без сессии (только признак готовности) |
| `/static/...`, `/favicon.ico` | без сессии (нужны странице входа) |
| `GET /api/v1/auth/me`, `GET /api/v1/conferences`, `GET /api/v1/sections`, `GET /api/v1/applications`, `GET /api/v1/fees`, `GET /api/v1/theses`, `GET /api/v1/hotel-bookings` | обе роли (участник видит только свои данные) |
| `GET /api/v1/auth/roles`, `POST`/`PATCH`/`DELETE` конференций и секций, весь `/api/v1/participants`, весь `/api/v1/invitations`, весь `/api/v1/reports`, `POST /api/v1/fees`, `POST /api/v1/applications/{id}/decision`, `POST /api/v1/theses/{id}/review`, `POST /api/v1/hotel-bookings/{id}/confirm`, `POST /api/v1/hotel-bookings/{id}/reject`, `POST /api/v1/hotel-bookings/expire-stale`, `GET /docs`, `GET /redoc`, `GET /openapi.json`, `GET /health`, `GET /version` | только администратор |
| `POST /api/v1/applications`, `PATCH`/`DELETE /api/v1/applications/{id}`, `POST /api/v1/applications/{id}/submit`, `POST /api/v1/applications/{id}/withdraw`, `POST /api/v1/applications/{id}/theses`, `POST /api/v1/hotel-bookings` | только участник |
| остальные методы `/api/v1/*` | только с действующей сессией, иначе `401 unauthorized` |
| веб-страницы `/`, `/docs`, `/redoc` и другие | без сессии перенаправляют на `/login` (HTTP 303) |

Коды отказа:

* `401 unauthorized` — сессии нет (API и служебные `/health`, `/version`, `/openapi.json`);
* `403 admin_only` — участник обратился к разделу администратора; в сообщении указывается
  название его роли, например: `Адрес «/health» доступен только администратору (вы вошли как «Участник»)`;
* `403 participant_only` — администратор вызвал действие участника;
* `403 forbidden` — у учётной записи нет требуемого права, например: `Учётная запись
  «user@example.com» не имеет права на действие «conference:manage»`;
* `403 forbidden_not_owner` и родственные `forbidden_foreign_*` — объект принадлежит другому
  участнику.

### Доступ к данным

- **Конференции и секции.** Чтение (`GET`) доступно обеим ролям — справочники нужны форме заявки;
  создание, изменение и удаление требуют прав `conference:manage` / `section:manage`
  (только администратор).
- **Реестр участников** (`/api/v1/participants`). Только администратор (право `participant:read`):
  участнику раздел закрыт целиком — и список, и запись по id отвечают `403 admin_only`.
- **Заявки.** Администратор видит все заявки и принимает решения (`application:decide`).
  Участник видит и изменяет только свои — выборка фильтруется по участнику, связанному с учётной
  записью. Создание, изменение, удаление, подача и отзыв доступны только участнику; чужой
  объект → `403 forbidden_not_owner`; отсутствие связанного участника →
  `403 no_participant_profile`. Администратору создание заявки запрещено: `403 participant_only`.
- **Оргвзносы.** Администратор видит все взносы и может начислить (`POST /api/v1/fees`), оплатить
  и вернуть любой из них. Участник видит только взносы по своим заявкам, оплачивает и возвращает
  свой взнос; чужой → `403 forbidden_foreign_fee`. Возврат по-прежнему возможен только для
  оплаченного взноса, заявка по которому отозвана или отклонена.
- **Приглашения.** Раздел только администратора (право `invitation:manage`); участник получает
  `403 admin_only`.
- **Тезисы.** Участник подаёт тезисы по своей заявке (`thesis:submit_own`) и видит только свои;
  оценивает тезисы администратор (`thesis:review`, `thesis:read_all`). Чужие тезисы →
  `403 forbidden_foreign_thesis`.
- **Гостиница.** Участник видит только свои брони и оформляет запрос по своей заявке
  (`hotel:read_own`, `hotel:request_own`); подтверждает, отклоняет и помечает просроченные брони
  администратор (`hotel:manage`, `hotel:read_all`). Чужая бронь → `403 forbidden_foreign_booking`.
- **Отчёты** (`/api/v1/reports/*`). Только администратор (право `report:read`).

### Учётные записи

| Адрес | Роль | Пароль | Профиль участника |
|---|---|---|---|
| `organizer@example.com` (`ADMIN_EMAIL`) | `admin` | `ADMIN_PASSWORD`, иначе `DEMO_PASSWORD` (по умолчанию `Conference2026`) | нет: администратор создаётся без записи в реестре участников |
| `polzovatel@example.ru` (`PARTICIPANT_EMAIL`) | `participant` | `PARTICIPANT_PASSWORD`, иначе `DEMO_PASSWORD` (по умолчанию `Conference2026`) | нет: учётная запись универсальная, ни к какому человеку не привязана. Участник каждой заявки определяется её данными (ФИО и почта) |

Обе учётные записи создаются при старте приложения; учётные записи с другими адресами при этом
удаляются. Категорий участников (слушатель, докладчик, рецензент, организатор) в реестре больше
нет: роль есть только у учётной записи, и её значений ровно два — `admin` и `participant`.
Администратор не подаёт заявки и не пишет тезисы; эти действия доступны только участнику.

### Примеры работы с сессией

```bash
# вход и сохранение cookie сессии
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "organizer@example.com", "password": "Conference2026"}'

# запрос с сохранённой сессией
curl -s -b cookies.txt http://127.0.0.1:8000/api/v1/applications

# выход
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/logout
```

Тот же токен можно взять из cookie-файла и передать в заголовке `Authorization`:

```bash
# вход: токен возвращается в заголовке Set-Cookie (cookie conference_session)
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "organizer@example.com", "password": "Conference2026"}'

# значение cookie — это и есть токен сессии
TOKEN=$(awk '$6 == "conference_session" { print $7 }' cookies.txt)
curl -s http://127.0.0.1:8000/api/v1/reports/sections-load/1 -H "Authorization: Bearer $TOKEN"
```

Вход участника и проверка разграничения доступа:

```bash
# вход участника: та же форма, другой адрес (универсальная учётная запись)
curl -s -c participant.txt -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "polzovatel@example.ru", "password": "Conference2026"}'

# участнику закрыты разделы администратора: 403 admin_only
curl -s -b participant.txt -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/v1/participants

# без сессии служебные адреса отвечают 401: сначала /health, затем /internal/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/internal/health
```

---

## Конференции

### `GET /api/v1/conferences`

Доступ: **обе роли** (справочник нужен форме заявки).

Параметры: `limit`, `offset`, `only_active` (bool).

```bash
curl -s -b cookies.txt "http://127.0.0.1:8000/api/v1/conferences?only_active=true"
```

### `POST /api/v1/conferences`

Доступ: **только администратор** (право `conference:manage`); участнику — `403 forbidden`, без
сессии — `401 unauthorized`.

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/conferences \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Методология и практики DevOps",
    "slug": "devops-conf-2026",
    "description": "Ежегодная конференция",
    "starts_on": "2026-06-01",
    "ends_on": "2026-06-03",
    "location": "Москва",
    "fee_amount": "3500.00",
    "is_active": true
  }'
```

Ответ `201`:

```json
{
  "id": 1,
  "title": "Методология и практики DevOps",
  "slug": "devops-conf-2026",
  "description": "Ежегодная конференция",
  "starts_on": "2026-06-01",
  "ends_on": "2026-06-03",
  "location": "Москва",
  "fee_amount": "3500.00",
  "is_active": true
}
```

Правила: `slug` уникален и состоит из строчных латинских букв, цифр и дефисов; `ends_on`
не может быть раньше `starts_on`; `fee_amount >= 0`.

### `GET /api/v1/conferences/{id}`, `PATCH /api/v1/conferences/{id}`, `DELETE /api/v1/conferences/{id}`

Доступ: `GET` — **обе роли**; `PATCH` и `DELETE` — **только администратор**.

`PATCH` принимает любое подмножество полей. `DELETE` возвращает `204` и каскадно удаляет
секции и заявки конференции.

```bash
curl -s -b cookies.txt -X PATCH http://127.0.0.1:8000/api/v1/conferences/1 \
  -H "Content-Type: application/json" -d '{"is_active": false}'
```

---

## Секции

### `GET /api/v1/sections?conference_id=1`

Доступ: **обе роли**.

Дополнительно к полям таблицы возвращаются вычисляемые значения:

```json
{
  "id": 1,
  "conference_id": 1,
  "title": "CI/CD и автоматизация релизов",
  "description": "Пайплайны сборки, тестирования и доставки изменений.",
  "capacity": 3,
  "is_open": true,
  "taken_seats": 2,
  "free_seats": 1
}
```

`taken_seats` — число заявок в статусах `submitted` и `accepted`; `free_seats` — остаток мест.

### `POST /api/v1/sections`

Доступ: **только администратор** (право `section:manage`).

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/sections \
  -H "Content-Type: application/json" \
  -d '{"conference_id": 1, "title": "Наблюдаемость и надёжность", "capacity": 3}'
```

### `GET|PATCH|DELETE /api/v1/sections/{id}`

Доступ: `GET` — **обе роли**; `PATCH` и `DELETE` — **только администратор**.

Уменьшение `capacity` ниже числа уже поданных заявок отклоняется (`section_capacity_below_load`).

---

## Участники

Раздел целиком доступен **только администратору** (право `participant:read`). Участнику и
закрыт и список, и запись по id: `403 admin_only`; без сессии — `401 unauthorized`.
Поля `role` в схемах участника нет: роль есть только у учётной записи, фильтр `?role=` удалён.

### `GET /api/v1/participants`

Параметры: `search` (по ФИО или e-mail, без учёта регистра), `limit`, `offset`.

```bash
curl -s -b cookies.txt "http://127.0.0.1:8000/api/v1/participants?search=ivanov"
```

### `POST /api/v1/participants`

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/participants \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Иванов Иван Иванович",
    "email": "ivanov@example.com",
    "organization": "Московский Политех",
    "position": "Студент",
    "city": "Москва"
  }'
```

E-mail проверяется схемой и приводится к нижнему регистру. Повторный e-mail отклоняется
(`participant_email_taken`).

Ответ `201`:

```json
{
  "id": 1,
  "full_name": "Иванов Иван Иванович",
  "email": "ivanov@example.com",
  "phone": null,
  "organization": "Московский Политех",
  "position": "Студент",
  "academic_degree": null,
  "city": "Москва",
  "is_active": true,
  "created_at": "2026-01-15T10:00:00Z"
}
```

### `GET|PATCH|DELETE /api/v1/participants/{id}`

Все три метода — **только администратор**.

---

## Заявки

### `GET /api/v1/applications`

Доступ: **обе роли**. Администратор видит все заявки; участник — только свои: выборка
фильтруется по участнику, связанному с его учётной записью, и параметрами запроса чужие заявки
получить нельзя.

Фильтры: `conference_id`, `section_id`, `participant_id` (только администратор), `status`
(`draft`, `submitted`, `accepted`, `rejected`, `withdrawn`), `limit`, `offset`.

```bash
curl -s -b cookies.txt "http://127.0.0.1:8000/api/v1/applications?conference_id=1&status=submitted"
```

### `GET /api/v1/applications/{id}` — заявка по id

Доступ: **обе роли**. Администратору — любая заявка, участнику — только своя; чужой объект →
`403 forbidden_not_owner`.

### `POST /api/v1/applications` — создать черновик

Доступ: **только участник** (право `application:create`). Администратору метод недоступен —
`403 participant_only`.

Участник заявки определяется **её данными**: `full_name` и `email` обязательны. По почте
система находит запись в реестре участников или создаёт новую (с указанными ФИО, организацией
и городом), поэтому из одной универсальной учётной записи можно подать заявки на разных людей.
Поля `participant_id` в теле нет, а лишние поля запрещены схемой (`extra="forbid"`) — попытка
передать `participant_id` приводит к `422 validation_error`.

Правило «один человек — одна заявка в секции» сравнивает найденного участника: повторная
заявка того же человека (та же почта) в ту же секцию → `409 application_duplicate`; заявка на
другого человека (другая почта) проходит. «Своими» для участника считаются заявки, поданные из
его учётной записи (`applications.created_by_user_id`).

```bash
curl -s -b participant.txt -X POST http://127.0.0.1:8000/api/v1/applications \
  -H "Content-Type: application/json" \
  -d '{
    "conference_id": 1,
    "section_id": 1,
    "topic": "Автоматизация релизов: от ручных выкладок к GitOps",
    "annotation": "Опыт перехода к декларативному описанию инфраструктуры.",
    "format": "offline",
    "needs_hotel": true,
    "full_name": "Петрова Анна Сергеевна",
    "email": "petrova@example.com",
    "organization": "Московский Политех",
    "city": "Москва"
  }'
```

Профиль участника заполняется из необязательных полей `full_name`, `email`, `organization`,
`city`: участник указывает свои ФИО и почту сам, а не выбирает из готового списка. Значения
сохраняются в его профиле как контактные данные. **Логин учётной записи не меняется:** почта в
заявке — это контактный адрес, а `users.email` (логин) остаётся прежним, поэтому вход под
исходным адресом продолжает работать. ФИО при этом обновляется и в шапке интерфейса.

Проверки: конференция и секция существуют; секция принадлежит конференции; нет дубликата заявки
в этой секции; дистанционный формат не может требовать гостиницу; чужой e-mail для профиля
отклоняется (`participant_email_taken`).

### `POST /api/v1/applications/{id}/submit` — подать заявку

Доступ: **только участник** (автор заявки). Проверяет правила приёма: конференция активна,
секция открыта, есть свободные места.

```bash
curl -s -b participant.txt -X POST http://127.0.0.1:8000/api/v1/applications/1/submit
```

### `POST /api/v1/applications/{id}/decision` — решение по заявке

Доступ: **только администратор** (право `application:decide`); участнику — `403 admin_only`.

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/applications/1/decision \
  -H "Content-Type: application/json" \
  -d '{"accept": true, "comment": "Доклад соответствует тематике секции"}'
```

При `accept: true` система начисляет оргвзнос в размере `fee_amount` конференции и ставит
приглашение в очередь рассылки (статус `queued`).

### `POST /api/v1/applications/{id}/withdraw` — отозвать заявку

Доступ: **только участник** (автор заявки). Активная бронь гостиницы переходит в статус
`cancelled`, неоплаченный оргвзнос — в `cancelled`.

### `PATCH /api/v1/applications/{id}`, `DELETE /api/v1/applications/{id}`

Доступ: **только участник** (автор заявки). Доступны только для черновика (удаление — также для
отозванной заявки).

---

## Приглашения

Раздел целиком доступен **только администратору** (право `invitation:manage`). Участнику
приглашения не видны: `403 admin_only` на любой метод раздела.

### `GET /api/v1/invitations`

Фильтры: `status` (`queued`, `sent`, `delivered`, `failed`, `cancelled`), `participant_id`.

### `POST /api/v1/invitations` — поставить в очередь вручную

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/invitations \
  -H "Content-Type: application/json" -d '{"application_id": 1}'
```

### `POST /api/v1/invitations/{id}/send` — отправить

Параметры запроса: `success` (по умолчанию `true`), `error` (текст ошибки при `success=false`).
Учебная имитация отправки: фиксируется факт, число попыток и текст последней ошибки.

```bash
curl -s -b cookies.txt -X POST "http://127.0.0.1:8000/api/v1/invitations/1/send?success=false&error=SMTP%20timeout"
curl -s -b cookies.txt -X POST "http://127.0.0.1:8000/api/v1/invitations/1/send?success=true"
```

Пример ответа:

```json
{
  "id": 1,
  "application_id": 1,
  "participant_id": 1,
  "subject": "Приглашение на конференцию «Методология и практики DevOps»",
  "body": "Уважаемый(ая) Иванов Иван Иванович!\n\n...",
  "status": "sent",
  "attempts": 2,
  "last_error": null,
  "queued_at": "2026-01-15T10:00:00Z",
  "sent_at": "2026-01-15T10:05:00Z"
}
```

---

## Оргвзносы

### `GET /api/v1/fees`

Доступ: **обе роли**. Администратор видит все начисления; участник — только взносы по своим
заявкам.

Фильтры: `status` (`pending`, `paid`, `refunded`, `cancelled`), `application_id`.

В ответе каждого взноса есть поле `application_status` — статус связанной заявки. Интерфейс
использует его, чтобы предлагать возврат только по отозванной или отклонённой заявке:

```json
{
  "id": 1,
  "application_id": 1,
  "amount": "3500.00",
  "currency": "RUB",
  "status": "paid",
  "application_status": "withdrawn",
  "payment_reference": "PAY-2026-0001",
  "paid_at": "2026-01-16T10:00:00Z",
  "refunded_at": null,
  "comment": null
}
```

### `POST /api/v1/fees` — начислить вручную

Доступ: **только администратор** (право `fee:manage`); участнику — `403 admin_only`.

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/fees \
  -H "Content-Type: application/json" \
  -d '{"application_id": 1, "amount": "3500.00", "comment": "Льготный взнос"}'
```

Поле `amount` необязательно: без него берётся взнос конференции. Начисление возможно только
по принятой заявке; повторное начисление обновляет существующий незакрытый взнос.

### `POST /api/v1/fees/{id}/pay` — оплатить

Доступ: **обе роли** — администратор отмечает оплату любого взноса, участник — только взнос по
своей заявке. Чужой взнос → `403 forbidden_foreign_fee`.

```bash
curl -s -b participant.txt -X POST http://127.0.0.1:8000/api/v1/fees/1/pay \
  -H "Content-Type: application/json" -d '{"payment_reference": "PAY-2026-0001"}'
```

### `POST /api/v1/fees/{id}/refund` — вернуть

Доступ: **обе роли** — администратор возвращает любой взнос, участник — только свой
(чужой → `403 forbidden_foreign_fee`).

```bash
curl -s -b participant.txt -X POST http://127.0.0.1:8000/api/v1/fees/1/refund \
  -H "Content-Type: application/json" -d '{"reason": "Участник отказался от участия"}'
```

Возврат возможен только для оплаченного взноса и только по отозванной или отклонённой заявке.

---

## Тезисы

### `GET /api/v1/theses`

Доступ: **обе роли**. Администратор видит все тезисы, участник — только свои.

Фильтры: `status` (`draft`, `submitted`, `under_review`, `accepted`, `revision`, `rejected`),
`application_id`.

### `POST /api/v1/applications/{id}/theses` — добавить тезисы

Доступ: **только участник** — автор заявки (право `thesis:submit_own`); администратору —
`403 participant_only`, чужой заявке — `403 forbidden_not_owner`.

```bash
curl -s -b participant.txt -X POST http://127.0.0.1:8000/api/v1/applications/1/theses \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Автоматизация релизов: от ручных выкладок к GitOps",
    "abstract": "В работе описан переход команды от ручных выкладок к декларативному описанию инфраструктуры и непрерывной доставке изменений.",
    "keywords": "DevOps, GitOps, CI/CD",
    "file_name": "thesis_ivanov.pdf",
    "file_size_kb": 180
  }'
```

Тезисы принимаются только по принятой заявке; `file_size_kb` не должен превышать
`ABSTRACT_MAX_SIZE_KB` (по умолчанию 512). При создании статус — `submitted`.

### `GET /api/v1/theses/{id}`

Доступ: **обе роли**. Администратору — любой тезис, участнику — только свой; чужой →
`403 forbidden_foreign_thesis`.

### `POST /api/v1/theses/{id}/review` — рецензия

Доступ: **только администратор** (право `thesis:review`); участнику — `403 admin_only`.

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/theses/1/review \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_name": "Кузнецова Ольга Дмитриевна",
    "score": 8,
    "accepted": true,
    "comment": "Тезисы соответствуют требованиям"
  }'
```

Порог принятия — **6 баллов из 10**: при `score >= 6` и `accepted: true` тезисы получают
статус `accepted`, иначе `rejected`. Оценка вне диапазона 1–10 отклоняется схемой (422).

---

## Гостиница

### `GET /api/v1/hotel-bookings`

Доступ: **обе роли**. Администратор видит все брони, участник — только брони по своим заявкам.

Фильтры: `status` (`requested`, `confirmed`, `checked_in`, `cancelled`, `expired`).

```json
{
  "id": 1,
  "application_id": 1,
  "hotel_name": "Гостиница «Семёновская»",
  "room_type": "standard",
  "guests_count": 1,
  "check_in": "2026-06-01",
  "check_out": "2026-06-03",
  "nights": 2,
  "status": "requested",
  "confirmation_deadline": "2026-01-17T10:00:00Z",
  "confirmed_at": null,
  "comment": null
}
```

### `GET /api/v1/hotel-bookings/{id}` — бронь по id

Доступ: **обе роли**. Администратору — любая бронь, участнику — только по своей заявке; чужой
объект → `403 forbidden_foreign_booking`.

### `POST /api/v1/hotel-bookings` — оформить потребность в гостинице

Доступ: **только участник** (право `hotel:request_own`) и только по своей заявке;
администратору — `403 participant_only`.

```bash
curl -s -b participant.txt -X POST http://127.0.0.1:8000/api/v1/hotel-bookings \
  -H "Content-Type: application/json" \
  -d '{
    "application_id": 1,
    "hotel_name": "Гостиница «Семёновская»",
    "room_type": "standard",
    "guests_count": 1,
    "check_in": "2026-06-01",
    "check_out": "2026-06-03"
  }'
```

Правила: заявка должна быть принята (`hotel_requires_accepted_application`), формат участия —
не дистанционный (`hotel_not_allowed_for_online`), даты проживания — в пределах дат конференции
(`hotel_dates_out_of_conference`), активной брони по заявке ещё нет (`hotel_booking_exists`).
Срок подтверждения — `confirmation_deadline = сейчас + HOTEL_CONFIRMATION_HOURS`.

### `POST /api/v1/hotel-bookings/{id}/confirm` — подтвердить бронь

Доступ: **только администратор** (право `hotel:manage`); участнику — `403 admin_only`.
Просроченная бронь переводится в статус `expired` и подтверждена быть не может
(`hotel_confirmation_expired`); уже подтверждённая — `hotel_already_confirmed`; отменённая или
истёкшая — `hotel_not_confirmable`.

### `POST /api/v1/hotel-bookings/{id}/reject` — отклонить запрос на бронь

Доступ: **только администратор** (право `hotel:manage`). Тело запроса — объект
`{"reason": "..."}` (схема `HotelReject`); поле `reason` необязательно (до 1000 символов), но сам
JSON-объект нужно передать: подходит и пустой `{}`, а запрос без тела отвечает
`422 validation_error`.

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/hotel-bookings/1/reject \
  -H "Content-Type: application/json" -d '{"reason": "Нет свободных номеров"}'
```

Бронь переходит в статус `cancelled`, причина дописывается в поле `comment`. Уже отклонённый
запрос → `hotel_already_cancelled`, подтверждённая бронь → `hotel_already_confirmed`,
истёкшая → `hotel_not_rejectable`.

### `POST /api/v1/hotel-bookings/expire-stale` — пометить просроченные брони

Доступ: **только администратор** (право `hotel:manage`).

```json
{ "expired": 2 }
```

---

## Отчёты

Раздел целиком доступен **только администратору** (право `report:read`): отчёты содержат
сводные данные по всем участникам. Участнику любой метод раздела отвечает `403 forbidden`
(у него нет права), без сессии — `401 unauthorized`.

### `GET /api/v1/reports/conference/{id}` — сводный отчёт

```bash
curl -s -b cookies.txt http://127.0.0.1:8000/api/v1/reports/conference/1
```

```json
{
  "conference_id": 1,
  "conference_title": "Методология и практики DevOps",
  "applications_total": 3,
  "applications_by_status": { "accepted": 2, "submitted": 1 },
  "participants_total": 3,
  "fees_total_amount": "7000.00",
  "fees_paid_amount": "0.00",
  "fees_by_status": { "pending": 2 },
  "theses_total": 1,
  "theses_by_status": { "submitted": 1 },
  "invitations_by_status": { "queued": 2 },
  "hotel_bookings_total": 1,
  "hotel_guests_total": 1,
  "hotel_by_status": { "requested": 1 },
  "generated_at": "2026-01-15T10:00:00Z"
}
```

### `GET /api/v1/reports/invitations-queue` — очередь рассылки
Параметр `limit` (по умолчанию 100). Возвращает неотправленные приглашения (`queued` и
`failed`) — готовый список для рассылки:

```json
{
  "items": [
    {
      "invitation_id": 1,
      "status": "queued",
      "attempts": 0,
      "email": "ivanov@example.com",
      "full_name": "Иванов Иван Иванович",
      "subject": "Приглашение на конференцию «Методология и практики DevOps»"
    }
  ],
  "total": 1
}
```

### `GET /api/v1/reports/mailing-list/{conference_id}` — список рассылки по организациям

Возвращает участников **принятых** заявок, сгруппированных по организациям. Отчёт нужен для
централизованной рассылки: оргкомитет направляет письмо в организацию, а не каждому участнику
отдельно.

```bash
curl -s -b cookies.txt http://127.0.0.1:8000/api/v1/reports/mailing-list/1
```

```json
{
  "conference_id": 1,
  "organizations_total": 2,
  "recipients_total": 3,
  "items": [
    {
      "organization": "Московский Политех",
      "participants": 2,
      "emails": ["ivanov@example.com", "petrova@example.com"]
    },
    {
      "organization": "НИУ ВШЭ",
      "participants": 1,
      "emails": ["sidorov@example.com"]
    }
  ]
}
```

Правила формирования: учитываются только заявки в статусе `accepted` по указанной
конференции; неактивные участники исключаются; для участников без организации используется
группа «Организация не указана».

### `GET /api/v1/reports/sections-load/{conference_id}` — заполненность секций

Показывает по каждой секции вместимость, число занятых мест и остаток. Отчёт нужен
программному комитету для планирования: видно, какие секции заполнены, где есть свободные
места и не переполнена ли секция после изменения вместимости.

```bash
curl -s -b cookies.txt http://127.0.0.1:8000/api/v1/reports/sections-load/1
```

```json
{
  "conference_id": 1,
  "sections_total": 2,
  "capacity_total": 13,
  "taken_total": 6,
  "free_total": 7,
  "items": [
    {
      "section_id": 1,
      "title": "CI/CD и автоматизация релизов",
      "is_open": true,
      "capacity": 5,
      "submitted": 2,
      "accepted": 3,
      "taken": 5,
      "free_seats": 0,
      "load_percent": 100.0,
      "is_full": true
    },
    {
      "section_id": 2,
      "title": "Наблюдаемость и мониторинг",
      "is_open": true,
      "capacity": 8,
      "submitted": 1,
      "accepted": 0,
      "taken": 1,
      "free_seats": 7,
      "load_percent": 12.5,
      "is_full": false
    }
  ]
}
```

Правила формирования:

* место занимают заявки в статусах `submitted` и `accepted` — ровно те же статусы, что
  использует правило вместимости секции (`ACTIVE_SECTION_STATUSES` в `app/services.py`)
  при приёме новой заявки; поэтому отчёт и правило всегда согласованы;
* отклонённые (`rejected`) и отозванные (`withdrawn`) заявки места не занимают;
* переполнение секции через API недостижимо: изменение вместимости ниже числа занятых мест
  отклоняется правилом `section_capacity_below_load`. Поэтому `free_seats` не бывает
  отрицательным, а `is_full` принимает значение `true`, когда занято не меньше вместимости;
* если у конференции нет секций, отчёт возвращается с нулевыми итогами и пустым списком
  `items`.

Чем отличается от `GET /api/v1/sections`: список секций отдаёт заполненность по одной секции и
выполняет отдельный запрос на каждую секцию, а отчёт даёт сводку по конференции целиком —
итоги по вместимости, занятым и свободным местам, процент заполненности — за два запроса к
базе. Кроме того, список секций доступен любому вошедшему пользователю, а отчёт — только
учётной записи с правом `report:read`.

---

## Веб-интерфейс

| Адрес | Назначение |
|---|---|
| `/login` | страница входа (доступна без сессии; при активной сессии перенаправляет на `/`) |
| `/logout` | выход из системы: удаляет сессию и очищает cookie, доступен без сессии |
| `/` | рабочая страница со вкладками (состав зависит от роли); без сессии перенаправляет на `/login` (HTTP 303) |
| `/docs`, `/redoc` | Swagger UI и ReDoc; только администратору, участнику — пояснительная страница отказа |
| `/health`, `/version`, `/openapi.json` | служебные адреса; только администратору |
| `/static/css/app.css` | стили |
| `/static/js/app.js` | клиентская логика вызовов API |

Состав вкладок определяется ролью учётной записи: недоступные разделы не отображаются, а
серверные методы всё равно проверяют права при каждом запросе.

| Роль | Вкладки |
|---|---|
| администратор | Сводка, Заявки, Оргвзносы, Приглашения, Гостиница, Тезисы, Участники (семь) |
| участник | Мои заявки, Мои оргвзносы, Моя гостиница, Мои тезисы (четыре) |

У участника нет вкладок «Сводка», «Приглашения» и «Участники», а служебные страницы (`/docs`,
`/redoc`, `/health`, `/openapi.json`) закрыты для его роли.
