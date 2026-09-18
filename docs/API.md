# Описание HTTP API

Базовый адрес: `http://127.0.0.1:8000`
Версия API: `v0.1.0`
Префикс прикладных методов: `/api/v1`

Живая документация: `/docs` (Swagger UI), `/redoc` (ReDoc), `/openapi.json` (схема OpenAPI 3.1).

---

## Общие соглашения

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
| 401 | `unauthorized` | запрос к защищённому методу без действующей сессии |
| 403 | `forbidden` | у роли нет права, требуемого методом |
| 403 | `user_disabled` | учётная запись отключена |
| 404 | `not_found`, `http_error` | объект или маршрут не найден |
| 409 | код правила предметной области | нарушено правило (см. таблицу ниже) |
| 422 | `validation_error` | схема запроса не прошла валидацию; поле `details` содержит список полей |
| 500 | `internal_error` | непредвиденная ошибка сервера |

Дополнительные коды `403`, связанные с принадлежностью объекта текущему пользователю:

| `error.code` | Когда возникает |
|---|---|
| `forbidden_not_owner` | запрашивается или изменяется объект другого пользователя (заявка) |
| `forbidden_foreign_participant` | попытка создать заявку от имени другого участника |
| `forbidden_foreign_fee` | попытка оплатить оргвзнос по чужой заявке |
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
| `application_duplicate` | у участника уже есть заявка в этой секции |
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

### `GET /health` — проверка работоспособности

```bash
curl -s http://127.0.0.1:8000/health
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

```json
{ "version": "0.1.0", "app_env": "local" }
```

Методы `/health` и `/version` доступны без входа и используются системами мониторинга.

---

## Аутентификация и разграничение доступа

Все прикладные методы `/api/v1/*`, кроме перечисленных ниже, требуют действующей сессии.
Сессия создаётся при входе и передаётся в cookie `conference_session` (флаги `HttpOnly` и
`SameSite=Lax`) либо в заголовке `Authorization: Bearer <токен сессии>` — второй вариант
предназначен для программных клиентов. Токен сессии — случайная строка из 43 символов, срок
жизни сессии — 12 часов; при выходе сессия удаляется.

Учётные записи хранятся в таблице `users`, сессии — в таблице `sessions` (см. `docs/DATA_MODEL.md`).
Пароли хранятся только в виде хеша PBKDF2-HMAC-SHA256 (200 000 итераций, случайная соль 16 байт,
формат `pbkdf2_sha256$200000$соль$хеш`); открытый пароль нигде не сохраняется и не попадает
в журналы приложения.

### `POST /api/v1/auth/login` — вход

Тело запроса: `{"email": "...", "password": "..."}`. Доступен без входа.

```bash
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "organizer@example.com", "password": "Conference2026"}'
```

Ответ `200` (одновременно устанавливается cookie `conference_session`):

```json
{
  "id": 1,
  "email": "organizer@example.com",
  "full_name": "Администратор программы",
  "role": "organizer",
  "role_title": "Организатор",
  "participant_id": 1,
  "is_active": true,
  "last_login_at": "2026-09-18T20:04:54Z"
}
```

Ошибки: неверный пароль или неизвестный адрес → `400 invalid_credentials` (текст сообщения
одинаков в обоих случаях, чтобы не раскрывать существующие адреса); отключённая учётная
запись → `403 user_disabled`.

### `POST /api/v1/auth/logout` — выход

Удаляет сессию и очищает cookie.

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/logout
```

```json
{ "status": "logged_out" }
```

### `GET /api/v1/auth/me` — текущий пользователь

```bash
curl -s -b cookies.txt http://127.0.0.1:8000/api/v1/auth/me
```

Возвращает те же поля, что и вход. Без действующей сессии → `401 unauthorized`.

### `GET /api/v1/auth/roles` — справочник ролей и прав

Доступен без входа. Возвращает массив ролей с перечнем прав:

```json
[
  {
    "role": "organizer",
    "title": "Организатор",
    "permissions": ["application:create", "application:decide", "conference:manage", "..."]
  },
  { "role": "listener", "title": "Участник (слушатель)", "permissions": ["..."] },
  { "role": "speaker", "title": "Докладчик", "permissions": ["..."] },
  { "role": "reviewer", "title": "Рецензент", "permissions": ["..."] }
]
```

### Права ролей

| Право | Организатор | Участник (слушатель) | Докладчик | Рецензент |
|---|---|---|---|---|
| `application:create` | да | да | да | — |
| `application:decide` | да | — | — | — |
| `application:read_all` | да | — | — | да |
| `application:read_own` | да | да | да | — |
| `conference:manage` | да | — | — | — |
| `fee:manage` | да | — | — | — |
| `fee:pay_own` | да | да | да | — |
| `fee:read_own` | да | да | да | — |
| `hotel:manage` | да | — | — | — |
| `hotel:request_own` | да | да | да | — |
| `invitation:manage` | да | — | — | — |
| `invitation:read_own` | да | да | да | да |
| `participant:manage` | да | — | — | — |
| `report:read` | да | — | — | — |
| `section:manage` | да | — | — | — |
| `thesis:read_all` | да | — | — | да |
| `thesis:review` | да | — | — | да |
| `thesis:submit_own` | да | — | да | — |
| `user:manage` | да | — | — | — |

### Защита маршрутов

| Маршрут | Доступ |
|---|---|
| `GET /health`, `GET /version` | без входа |
| `POST /api/v1/auth/login` | без входа |
| `GET /api/v1/auth/roles` | без входа |
| страница `/login` и форма входа | без входа |
| остальные методы `/api/v1/*` | только с действующей сессией, иначе `401 unauthorized` |
| веб-страница `/` | без сессии перенаправляет на `/login` (HTTP 303) |

Недостаток прав → `403 forbidden`; в сообщении указываются роль и требуемое право, например:
`Роль «Участник (слушатель)» не имеет права на действие «conference:manage»`.

### Доступ к данным по ролям

- **Конференции, секции, реестр участников.** Чтение доступно любой вошедшей роли (нужно для
  выбора участника и просмотра списков); изменение — только организатору.
- **Заявки.** Организатор видит и изменяет все заявки и принимает по ним решения. Участник и
  докладчик видят только свои заявки, могут подавать их, изменять черновик и отзывать.
  Рецензент видит список заявок для контекста, но не изменяет их. Обращение к чужой заявке →
  `403 forbidden_not_owner`; попытка создать заявку от имени другого участника →
  `403 forbidden_foreign_participant`. Если у учётной записи нет связанного участника, операция
  отклоняется с `403 no_participant_profile`.
- **Оргвзносы.** Организатор видит все взносы, начисляет и возвращает их. Участник и докладчик
  видят только взносы по своим заявкам и могут оплачивать только их; чужой взнос →
  `403 forbidden_foreign_fee`.
- **Приглашения.** Организатор управляет очередью рассылки; участник, докладчик и рецензент
  видят только адресованные им приглашения.
- **Тезисы.** Докладчик подаёт тезисы только по своей заявке (организатор — по любой);
  рецензент и организатор видят все тезисы; оценку выставляет только рецензент (право
  `thesis:review`); докладчик видит только свои тезисы, обращение к чужим →
  `403 forbidden_foreign_thesis`.
- **Гостиница.** Организатор управляет всеми бронями и подтверждает их; участник и докладчик
  оформляют потребность только по своим заявкам и видят только свои; чужая бронь →
  `403 forbidden_foreign_booking`.
- **Отчёты** (`/api/v1/reports/*`). Требуется право `report:read`; доступно только организатору.

### Демонстрационные учётные записи

| Адрес | Роль | Пароль |
|---|---|---|
| `organizer@example.com` | организатор | `ADMIN_PASSWORD` / `DEMO_PASSWORD`, по умолчанию `Conference2026` |
| `listener@example.com` | участник (слушатель) | `Conference2026` |
| `speaker@example.com` | докладчик | `Conference2026` |
| `reviewer@example.com` | рецензент | `Conference2026` |

Учётные записи создаются при старте приложения, если включено наполнение демонстрационными
данными (`SEED_DEMO_DATA=true`). Пароль демонстрационных учётных записей задаётся переменной
`DEMO_PASSWORD`.

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
  -d '{"email": "reviewer@example.com", "password": "Conference2026"}'

# значение cookie — это и есть токен сессии
TOKEN=$(awk '$6 == "conference_session" { print $7 }' cookies.txt)
curl -s http://127.0.0.1:8000/api/v1/theses -H "Authorization: Bearer $TOKEN"
```

---

## Конференции

### `GET /api/v1/conferences`

Параметры: `limit`, `offset`, `only_active` (bool).

```bash
curl -s "http://127.0.0.1:8000/api/v1/conferences?only_active=true"
```

### `POST /api/v1/conferences`

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/conferences \
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

`PATCH` принимает любое подмножество полей. `DELETE` возвращает `204` и каскадно удаляет
секции и заявки конференции.

```bash
curl -s -X PATCH http://127.0.0.1:8000/api/v1/conferences/1 \
  -H "Content-Type: application/json" -d '{"is_active": false}'
```

---

## Секции

### `GET /api/v1/sections?conference_id=1`

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

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/sections \
  -H "Content-Type: application/json" \
  -d '{"conference_id": 1, "title": "Наблюдаемость и надёжность", "capacity": 3}'
```

### `PATCH /api/v1/sections/{id}`

Уменьшение `capacity` ниже числа уже поданных заявок отклоняется (`section_capacity_below_load`).

---

## Участники

### `GET /api/v1/participants`

Параметры: `search` (по ФИО или e-mail, без учёта регистра), `role`
(`listener`, `speaker`, `organizer`, `reviewer`), `limit`, `offset`.

```bash
curl -s "http://127.0.0.1:8000/api/v1/participants?search=ivanov&role=speaker"
```

### `POST /api/v1/participants`

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/participants \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Иванов Иван Иванович",
    "email": "ivanov@example.com",
    "organization": "Московский Политех",
    "position": "Студент",
    "city": "Москва",
    "role": "speaker"
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
  "role": "speaker",
  "is_active": true,
  "created_at": "2026-01-15T10:00:00Z"
}
```

### `GET|PATCH|DELETE /api/v1/participants/{id}`

---

## Заявки

### `GET /api/v1/applications`

Фильтры: `conference_id`, `section_id`, `participant_id`, `status`
(`draft`, `submitted`, `accepted`, `rejected`, `withdrawn`), `limit`, `offset`.

```bash
curl -s "http://127.0.0.1:8000/api/v1/applications?conference_id=1&status=submitted"
```

### `POST /api/v1/applications` — создать черновик

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/applications \
  -H "Content-Type: application/json" \
  -d '{
    "conference_id": 1,
    "section_id": 1,
    "participant_id": 1,
    "topic": "Автоматизация релизов: от ручных выкладок к GitOps",
    "annotation": "Опыт перехода к декларативному описанию инфраструктуры.",
    "format": "offline",
    "needs_hotel": true
  }'
```

Проверки: конференция, секция и участник существуют; секция принадлежит конференции; нет
дубликата заявки; дистанционный формат не может требовать гостиницу.

### `POST /api/v1/applications/{id}/submit` — подать заявку

Проверяет правила приёма: конференция активна, секция открыта, есть свободные места.

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/applications/1/submit
```

### `POST /api/v1/applications/{id}/decision` — решение по заявке

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/applications/1/decision \
  -H "Content-Type: application/json" \
  -d '{"accept": true, "comment": "Доклад соответствует тематике секции"}'
```

При `accept: true` система начисляет оргвзнос в размере `fee_amount` конференции и ставит
приглашение в очередь рассылки (статус `queued`).

### `POST /api/v1/applications/{id}/withdraw` — отозвать заявку

Активная бронь гостиницы переходит в статус `cancelled`, неоплаченный оргвзнос — в `cancelled`.

### `PATCH /api/v1/applications/{id}`, `DELETE /api/v1/applications/{id}`

Доступны только для черновика (удаление — также для отозванной заявки).

---

## Приглашения

### `GET /api/v1/invitations`

Фильтры: `status` (`queued`, `sent`, `delivered`, `failed`, `cancelled`), `participant_id`.

### `POST /api/v1/invitations` — поставить в очередь вручную

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/invitations \
  -H "Content-Type: application/json" -d '{"application_id": 1}'
```

### `POST /api/v1/invitations/{id}/send` — отправить

Параметры запроса: `success` (по умолчанию `true`), `error` (текст ошибки при `success=false`).
Учебная имитация отправки: фиксируется факт, число попыток и текст последней ошибки.

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/invitations/1/send?success=false&error=SMTP%20timeout"
curl -s -X POST "http://127.0.0.1:8000/api/v1/invitations/1/send?success=true"
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

Фильтры: `status` (`pending`, `paid`, `refunded`, `cancelled`), `application_id`.

### `POST /api/v1/fees` — начислить вручную

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/fees \
  -H "Content-Type: application/json" \
  -d '{"application_id": 1, "amount": "3500.00", "comment": "Льготный взнос"}'
```

Поле `amount` необязательно: без него берётся взнос конференции. Начисление возможно только
по принятой заявке; повторное начисление обновляет существующий незакрытый взнос.

### `POST /api/v1/fees/{id}/pay` — оплатить

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/fees/1/pay \
  -H "Content-Type: application/json" -d '{"payment_reference": "PAY-2026-0001"}'
```

### `POST /api/v1/fees/{id}/refund` — вернуть

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/fees/1/refund \
  -H "Content-Type: application/json" -d '{"reason": "Участник отказался от участия"}'
```

Возврат возможен только для оплаченного взноса и только по отозванной или отклонённой заявке.

---

## Тезисы

### `GET /api/v1/theses`

Фильтры: `status` (`draft`, `submitted`, `under_review`, `accepted`, `revision`, `rejected`),
`application_id`.

### `POST /api/v1/applications/{id}/theses` — добавить тезисы

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/applications/1/theses \
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

### `POST /api/v1/theses/{id}/review` — рецензия

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/theses/1/review \
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

### `POST /api/v1/hotel-bookings` — оформить потребность в гостинице

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/hotel-bookings \
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

Срок подтверждения — `confirmation_deadline = сейчас + HOTEL_CONFIRMATION_HOURS`.

### `POST /api/v1/hotel-bookings/{id}/confirm` — подтвердить бронь

Просроченная бронь переводится в статус `expired` и подтверждена быть не может.

### `POST /api/v1/hotel-bookings/expire-stale` — пометить просроченные брони

```json
{ "expired": 2 }
```

---

## Отчёты

### `GET /api/v1/reports/conference/{id}` — сводный отчёт

```bash
curl -s http://127.0.0.1:8000/api/v1/reports/conference/1
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
curl -s http://127.0.0.1:8000/api/v1/reports/mailing-list/1
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

---

## Веб-интерфейс

| Адрес | Назначение |
|---|---|
| `/login` | страница входа (доступна без сессии) |
| `/` | рабочая страница со вкладками (Сводка, Заявки, Оргвзносы, Приглашения, Гостиница, Тезисы); без сессии перенаправляет на `/login` (HTTP 303) |
| `/static/css/app.css` | стили |
| `/static/js/app.js` | клиентская логика вызовов API |

Состав вкладок зависит от роли: разделы, на которые у роли нет права, не отображаются, а
серверные методы всё равно проверяют право при каждом запросе.
