# Схема данных

СУБД: реляционная. Локально — SQLite (`data/conference.db`), в контейнерном окружении —
PostgreSQL 16. Схема создаётся SQLAlchemy по метаданным (`make migrate`, `app/database.py`).

Одиннадцать таблиц: `conferences`, `sections`, `participants`, `applications`, `invitations`,
`fees`, `theses`, `hotel_bookings`, `audit_log`, а также `users` и `sessions` — учётные записи
для входа и сессии аутентификации.

---

## Диаграмма связей

```
                    ┌─────────────────────┐
                    │    conferences      │
                    │  id (PK)            │
                    │  title, slug (UQ)   │
                    │  starts_on, ends_on │
                    │  location           │
                    │  fee_amount         │
                    │  is_active          │
                    └──────────┬──────────┘
                               │ 1
                 ┌─────────────┴──────────────┐
                 │ N                          │ N
      ┌──────────▼──────────┐    ┌────────────▼─────────┐
      │      sections       │    │     applications     │
      │  id (PK)            │ 1  │  id (PK)             │
      │  conference_id (FK) ├───►│  conference_id (FK)  │
      │  title              │ N  │  section_id (FK)     │
      │  capacity           │    │  participant_id (FK) │
      │  is_open            │    │  topic, annotation   │
      └─────────────────────┘    │  format, status      │
                                 │  needs_hotel         │
                                 └───┬───────┬──────┬───┘
                                     │1      │1     │1
                    ┌────────────────┘       │      └──────────────┐
                    │                        │                     │
              ┌─────▼──────────┐      ┌──────▼───────┐   ┌─────────▼────────┐
              │  invitations   │      │    theses    │   │  hotel_bookings  │
              │  id (PK)       │      │  id (PK)     │   │  id (PK)         │
              │  application_id│      │  application │   │  application_id  │
              │   (FK, UQ)     │      │   _id (FK)   │   │   (FK, UQ)       │
              │  participant_id│      │  status      │   │  check_in/out    │
              │   (FK)         │      │  review_score│   │  status          │
              │  status        │      └──────────────┘   │  confirmation_   │
              │  attempts      │                         │   deadline       │
              └────────────────┘                         └──────────────────┘
                    ▲
                    │ N                       ┌──────────────┐
        ┌───────────┴──────────┐              │    fees      │
        │     participants     │              │  id (PK)     │
        │  id (PK)             │              │  application │
        │  full_name           │              │   _id (FK)   │
        │  email (UQ)          │              │  amount      │
        │  organization, city  │              │  status      │
        │  role                │              └──────▲───────┘
        └──────────┬───────────┘                     │ N
                   │ 1 (необязательная связь)        └── applications (1:N)
                   │ 1
        ┌──────────▼───────────┐
        │        users         │
        │  id (PK)             │
        │  email (UQ)          │
        │  full_name           │
        │  role                │
        │  participant_id (FK, │
        │   UQ, SET NULL)      │
        │  is_active           │
        │  last_login_at       │
        └──────────┬───────────┘
                   │ 1
                   │ N
        ┌──────────▼───────────┐
        │      sessions        │
        │  id (PK, cookie)     │
        │  user_id (FK)        │
        │  app_env             │
        │  created_at          │
        │  expires_at          │
        └──────────────────────┘
```

`applications` — центральная сущность: она связывает участника, секцию и конференцию и
является владельцем приглашения, оргвзносов, тезисов и брони гостиницы. При удалении заявки
дочерние записи удаляются каскадно.

`users` и `sessions` обслуживают вход в систему: учётная запись ссылается на запись участника
(связь «один к одному», необязательная) и владеет сессиями; при удалении пользователя его
сессии удаляются каскадно.

---

## Таблицы

### `conferences` — конференция

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | INTEGER | PK | идентификатор |
| `title` | VARCHAR(250) | NOT NULL | название |
| `slug` | VARCHAR(80) | NOT NULL, UNIQUE | код для ссылок (`devops-conf-2026`) |
| `description` | TEXT | | описание |
| `starts_on` | DATE | NOT NULL | дата начала |
| `ends_on` | DATE | NOT NULL, CHECK `ends_on >= starts_on` | дата окончания |
| `location` | VARCHAR(200) | NOT NULL | место проведения |
| `fee_amount` | NUMERIC(10,2) | NOT NULL, CHECK `>= 0` | размер оргвзноса |
| `is_active` | BOOLEAN | NOT NULL | принимаются ли заявки |
| `created_at` | TIMESTAMP | NOT NULL, UTC | время создания |

### `sections` — секция конференции

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | INTEGER | PK | идентификатор |
| `conference_id` | INTEGER | FK → `conferences.id` ON DELETE CASCADE | конференция |
| `title` | VARCHAR(200) | NOT NULL, UQ с `conference_id` | название секции |
| `description` | TEXT | | описание |
| `capacity` | INTEGER | NOT NULL, CHECK `> 0` | вместимость (число мест) |
| `is_open` | BOOLEAN | NOT NULL | открыта ли секция для приёма |

Ограничение `uq_section_title_per_conference` запрещает две секции с одинаковым названием в
одной конференции.

### `participants` — участник

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | INTEGER | PK | идентификатор |
| `full_name` | VARCHAR(200) | NOT NULL | ФИО |
| `email` | VARCHAR(200) | NOT NULL, UNIQUE, индекс | контактный адрес (в нижнем регистре) |
| `phone` | VARCHAR(30) | | телефон |
| `organization` | VARCHAR(250) | | организация |
| `position` | VARCHAR(150) | | должность |
| `academic_degree` | VARCHAR(120) | | учёная степень |
| `city` | VARCHAR(120) | | город |
| `role` | VARCHAR(20) | NOT NULL, enum | `listener`, `speaker`, `organizer`, `reviewer` |
| `is_active` | BOOLEAN | NOT NULL | признак активности |
| `created_at` | TIMESTAMP | NOT NULL, UTC | время регистрации |

### `users` — учётная запись для входа

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | INTEGER | PK | идентификатор |
| `email` | VARCHAR(200) | NOT NULL, UNIQUE, индекс | адрес для входа (в нижнем регистре) |
| `full_name` | VARCHAR(200) | NOT NULL | ФИО пользователя |
| `role` | VARCHAR(20) | NOT NULL, индекс, enum | `organizer`, `listener`, `speaker`, `reviewer` |
| `password_hash` | VARCHAR(255) | NOT NULL | хеш пароля PBKDF2-HMAC-SHA256, формат `pbkdf2_sha256$итерации$соль$хеш` |
| `participant_id` | INTEGER | FK → `participants.id` ON DELETE SET NULL, UNIQUE | связанная запись участника (для работы «от себя») |
| `is_active` | BOOLEAN | NOT NULL | признак активности учётной записи |
| `created_at` | TIMESTAMP | NOT NULL, UTC | время создания |
| `last_login_at` | TIMESTAMP | | время последнего входа |

Пароль хранится только в виде хеша: PBKDF2-HMAC-SHA256, 200 000 итераций, случайная соль
16 байт. Открытый пароль не сохраняется в базе и не записывается в журналы.

### `sessions` — сессия входа

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | VARCHAR(64) | PK | идентификатор сессии (случайная строка, значение cookie `conference_session`) |
| `user_id` | INTEGER | FK → `users.id` ON DELETE CASCADE, индекс | пользователь |
| `app_env` | VARCHAR(20) | NOT NULL | среда (`local`, `docker`, `ci`) — для диагностики |
| `created_at` | TIMESTAMP | NOT NULL, UTC | время создания |
| `expires_at` | TIMESTAMP | NOT NULL | срок действия (по умолчанию 12 часов) |

Токен сессии — случайная строка из 43 символов; он передаётся в cookie `conference_session`
с флагами `HttpOnly` и `SameSite=Lax` либо в заголовке `Authorization: Bearer <токен>`.
Сессия удаляется при выходе пользователя и по истечении срока действия.

### `applications` — заявка на участие

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | INTEGER | PK | идентификатор |
| `conference_id` | INTEGER | FK → `conferences.id` CASCADE | конференция |
| `section_id` | INTEGER | FK → `sections.id` CASCADE | секция |
| `participant_id` | INTEGER | FK → `participants.id` CASCADE | участник |
| `topic` | VARCHAR(300) | NOT NULL | тема доклада |
| `annotation` | TEXT | | аннотация |
| `format` | VARCHAR(20) | NOT NULL, enum | `offline`, `online`, `poster` |
| `status` | VARCHAR(20) | NOT NULL, индекс, enum | `draft`, `submitted`, `accepted`, `rejected`, `withdrawn` |
| `needs_hotel` | BOOLEAN | NOT NULL | нужна ли гостиница |
| `submitted_at` | TIMESTAMP | | время подачи |
| `decided_at` | TIMESTAMP | | время решения |
| `decision_comment` | TEXT | | комментарий решения |
| `created_at` / `updated_at` | TIMESTAMP | NOT NULL, UTC | служебные отметки |

Ограничение `uq_application_unique (conference_id, section_id, participant_id)` реализует
правило «один участник — одна заявка в секции данной конференции».

### `invitations` — приглашение (очередь рассылки)

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | INTEGER | PK | идентификатор |
| `application_id` | INTEGER | FK → `applications.id` CASCADE, UNIQUE | заявка (одно приглашение на заявку) |
| `participant_id` | INTEGER | FK → `participants.id` CASCADE, индекс | получатель |
| `subject` | VARCHAR(250) | NOT NULL | тема письма |
| `body` | TEXT | NOT NULL | текст письма |
| `status` | VARCHAR(20) | NOT NULL, индекс, enum | `queued`, `sent`, `delivered`, `failed`, `cancelled` |
| `attempts` | INTEGER | NOT NULL | число попыток отправки |
| `last_error` | TEXT | | текст последней ошибки |
| `queued_at` | TIMESTAMP | NOT NULL, UTC | время постановки в очередь |
| `sent_at` | TIMESTAMP | | время отправки |

### `fees` — оргвзнос

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | INTEGER | PK | идентификатор |
| `application_id` | INTEGER | FK → `applications.id` CASCADE, индекс | заявка |
| `amount` | NUMERIC(10,2) | NOT NULL, CHECK `>= 0` | сумма |
| `currency` | VARCHAR(3) | NOT NULL (`RUB`) | валюта |
| `status` | VARCHAR(20) | NOT NULL, индекс, enum | `pending`, `paid`, `refunded`, `cancelled` |
| `payment_reference` | VARCHAR(100) | UNIQUE | идентификатор платежа |
| `paid_at` / `refunded_at` | TIMESTAMP | | время оплаты и возврата |
| `comment` | TEXT | | комментарий |
| `created_at` | TIMESTAMP | NOT NULL, UTC | время начисления |

### `theses` — тезисы доклада

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | INTEGER | PK | идентификатор |
| `application_id` | INTEGER | FK → `applications.id` CASCADE, индекс | заявка |
| `title` | VARCHAR(300) | NOT NULL | название |
| `abstract` | TEXT | NOT NULL | текст тезисов |
| `keywords` | VARCHAR(400) | | ключевые слова |
| `file_name` | VARCHAR(255) | | имя файла |
| `file_size_kb` | INTEGER | | размер файла, КБ |
| `status` | VARCHAR(20) | NOT NULL, индекс, enum | `draft`, `submitted`, `under_review`, `accepted`, `revision`, `rejected` |
| `reviewer_name` | VARCHAR(200) | | рецензент |
| `review_score` | INTEGER | CHECK `1..10` | оценка |
| `review_comment` | TEXT | | комментарий рецензента |
| `submitted_at` / `reviewed_at` | TIMESTAMP | | даты подачи и рецензии |
| `created_at` | TIMESTAMP | NOT NULL, UTC | служебная отметка |

### `hotel_bookings` — потребность в гостинице

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | INTEGER | PK | идентификатор |
| `application_id` | INTEGER | FK → `applications.id` CASCADE, UNIQUE | заявка (одна бронь на заявку) |
| `hotel_name` | VARCHAR(200) | NOT NULL | гостиница |
| `room_type` | VARCHAR(80) | NOT NULL (`standard`) | тип номера |
| `guests_count` | INTEGER | NOT NULL, CHECK `> 0` | число гостей |
| `check_in` | DATE | NOT NULL | дата заезда |
| `check_out` | DATE | NOT NULL, CHECK `check_out > check_in` | дата выезда |
| `status` | VARCHAR(20) | NOT NULL, индекс, enum | `requested`, `confirmed`, `checked_in`, `cancelled`, `expired` |
| `confirmation_deadline` | TIMESTAMP | NOT NULL, UTC | срок подтверждения |
| `confirmed_at` | TIMESTAMP | | время подтверждения |
| `comment` | TEXT | | комментарий |
| `created_at` | TIMESTAMP | NOT NULL, UTC | время создания |

Вычисляемое свойство `nights` = `check_out − check_in` в ночах.

### `audit_log` — журнал значимых действий

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | INTEGER | PK | идентификатор |
| `entity` | VARCHAR(60) | NOT NULL, индекс | сущность (`application`, `fee`, `thesis`, `hotel`, `invitation`) |
| `entity_id` | INTEGER | | идентификатор записи |
| `action` | VARCHAR(60) | NOT NULL | действие (`submit`, `accept`, `pay`, `refund`, `review`, `confirm`, `expire`, ...) |
| `details` | TEXT | | подробности |
| `created_at` | TIMESTAMP | NOT NULL, UTC | время события |

Журнал используется при разборе инцидентов и для контроля хода обработки заявок.

---

## Ограничения целостности

**Уникальность**

| Ограничение | Таблица | Смысл |
|---|---|---|
| `slug` | `conferences` | уникальный код конференции |
| `uq_section_title_per_conference` | `sections` | одна секция с таким названием в конференции |
| `email` | `participants` | один участник на адрес |
| `email` | `users` | одна учётная запись на адрес входа |
| `participant_id` | `users` | одна учётная запись на запись участника (связь «один к одному») |
| `uq_application_unique` | `applications` | одна заявка участника в секции конференции |
| `application_id` | `invitations` | одно приглашение на заявку |
| `application_id` | `hotel_bookings` | одна бронь на заявку |
| `payment_reference` | `fees` | уникальный идентификатор платежа |

**Проверки (`CHECK`)**

| Ограничение | Условие |
|---|---|
| `ck_conference_dates` | `ends_on >= starts_on` |
| `ck_conference_fee_non_negative` | `fee_amount >= 0` |
| `ck_section_capacity_positive` | `capacity > 0` |
| `ck_fee_amount_non_negative` | `amount >= 0` |
| `ck_thesis_review_score_range` | `review_score BETWEEN 1 AND 10` (или `NULL`) |
| `ck_hotel_dates` | `check_out > check_in` |
| `ck_hotel_guests_positive` | `guests_count > 0` |

**Ссылочная целостность**

Внешние ключи предметных таблиц объявлены с `ON DELETE CASCADE`: удаление конференции удаляет
её секции и заявки, удаление заявки — приглашение, оргвзносы, тезисы и бронь. Для SQLite
контроль внешних ключей включается параметром `PRAGMA foreign_keys=ON` при каждом соединении
(`app/database.py`).

Ключи аутентификации ведут себя иначе:

| Связь | Правило удаления | Смысл |
|---|---|---|
| `sessions.user_id` → `users.id` | `ON DELETE CASCADE` | удаление учётной записи удаляет все её сессии |
| `users.participant_id` → `participants.id` | `ON DELETE SET NULL` | при удалении участника ссылка обнуляется, учётная запись сохраняется |

`users.participant_id` дополнительно объявлен как `UNIQUE`: у одной записи участника может быть
не более одной учётной записи (связь «один к одному»). Поле допускает `NULL` — учётная запись
без связанного участника (например, организатор, не подающий заявки) допустима.

## Требования к хранению данных

- Все отметки времени хранятся в UTC; для SQLite «наивные» значения нормализуются функцией
  `as_aware()` перед сравнением.
- Денежные суммы хранятся в `NUMERIC(10,2)` (в SQLite — как `NUMERIC`), что исключает
  накопление ошибок округления.
- Секреты (пароль администратора, строка подключения к БД) задаются только переменными
  окружения; файл `.env` исключён из репозитория.
- Резервное копирование: `make backup` (копия файла SQLite или `pg_dump`), восстановление —
  `make restore`. Каталог `backups/` исключён из репозитория.
- Персональные данные участников (ФИО, e-mail, телефон, организация) обрабатываются в объёме,
  необходимом для организации конференции; при внешней эксплуатации требуется соблюдение
  требований 152-ФЗ (см. раздел 4.5 технического задания).

**Безопасность учётных данных.** Пароли пользователей хранятся только в виде хеша
(PBKDF2-HMAC-SHA256, 200 000 итераций, случайная соль 16 байт на запись); открытый пароль
не сохраняется в базе, не возвращается в ответах API и не записывается в журналы приложения.
Сессии имеют ограниченный срок жизни (12 часов) и удаляются при выходе пользователя. Cookie
сессии `conference_session` передаётся с флагами `HttpOnly` (недоступна клиентским сценариям)
и `SameSite=Lax` (ограничивает межсайтовую отправку). Для программных клиентов тот же токен
принимается в заголовке `Authorization: Bearer`. Проверка прав выполняется на сервере для
каждого запроса — сокрытие элементов интерфейса не заменяет серверную проверку.
