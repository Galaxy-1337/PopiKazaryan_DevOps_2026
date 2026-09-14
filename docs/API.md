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
| 404 | `not_found`, `http_error` | объект или маршрут не найден |
| 409 | код правила предметной области | нарушено правило (см. таблицу ниже) |
| 422 | `validation_error` | схема запроса не прошла валидацию; поле `details` содержит список полей |
| 500 | `internal_error` | непредвиденная ошибка сервера |

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

---

## Веб-интерфейс

| Адрес | Назначение |
|---|---|
| `/` | рабочая страница со вкладками (Сводка, Заявки, Оргвзносы, Приглашения, Гостиница, Тезисы) |
| `/static/css/app.css` | стили |
| `/static/js/app.js` | клиентская логика вызовов API |
