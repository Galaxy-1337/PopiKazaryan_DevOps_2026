# Git-процесс: от задачи до тега версии

Пошаговое руководство, полностью воспроизводящее требования лабораторной работы №1
(«Сквозной проект и Git-процесс»). Все команды выполняются из папки проекта.

```
git add .   →   git commit   →   git push
```

Три команды выше — минимальный ежедневный цикл. Полный процесс включает задачу, ветку,
запрос на слияние, проверку CI, моделирование конфликта и тег версии — об этом ниже.

---

## 0. Подготовка рабочего места (один раз)

```powershell
# Проверить, что Git знает, кто вы
git config --global user.name  "Попиков Иван"
git config --global user.email "your-mail@example.com"

# Перейти в папку проекта
cd "C:\Users\Иван\Desktop\ПЕРВЫЙ проект\DevOps"

# Убедиться, что удалённый репозиторий настроен
git remote -v
```

Ожидаемый вывод:

```
origin  https://github.com/Galaxy-1337/PopiKazaryan_DevOps_2026.git (fetch)
origin  https://github.com/Galaxy-1337/PopiKazaryan_DevOps_2026.git (push)
```

Если `origin` не настроен:

```powershell
git remote add origin https://github.com/Galaxy-1337/PopiKazaryan_DevOps_2026.git
```

Проверить, что секреты не попадут в репозиторий:

```powershell
git check-ignore -v .env
```

Ожидаемый вывод — строка с `.gitignore` и правилом `.env`, например:

```
.gitignore:2:.env    .env
```

Если команда ничего не вывела — **остановитесь**: файл `.env` не игнорируется, коммитить
нельзя.

---

## Шаг 1. Задача

Каждое изменение начинается с задачи (issue) в GitHub:

1. Открыть репозиторий → **Issues** → **New issue**.
2. Заголовок: результат, который нужен. Например: «Учёт потребности в гостинице».
3. Описание: зачем нужно, что считается готовым результатом, как проверять.
4. Назначить исполнителя, поставить метку `feature`.
5. Запомнить номер задачи (например `#4`) — он понадобится в названии ветки, в коммитах и
   в описании PR.

Пример задачи для демонстрации на защите:

```markdown
## Задача
Нужно учитывать потребность участников в гостинице: кто, с какого по какое число,
сколько гостей, и подтверждена ли бронь.

## Критерии готовности
- [ ] бронь создаётся только по принятой заявке
- [ ] дистанционному участнику бронь недоступна
- [ ] даты проживания укладываются в даты конференции
- [ ] есть срок подтверждения; просроченная бронь не подтверждается
- [ ] покрыто тестами, `make verify` зелёный

## Как проверять
`make run` → вкладка «Гостиница» → подтвердить бронь
```

---

## Шаг 2. Ветка под задачу

```powershell
# Актуализировать основную ветку
git switch main
git pull --ff-only

# Создать ветку под задачу (номер задачи в названии)
git switch -c feature/4-hotel-booking

# Убедиться, что вы в нужной ветке
git branch --show-current
```

Соглашение об именах ветвей: `feature/<номер>-<кратко>`, `fix/<номер>-<кратко>`,
`docs/<номер>-<кратко>`, `chore/<номер>-<кратко>`.

---

## Шаг 3. Разработка и локальные проверки

Работать в Visual Studio Code (см. раздел «Работа в VS Code» в конце документа).
Перед каждым коммитом:

```powershell
.\scripts\dev.ps1 verify
```

или, если установлен GNU make:

```bash
make verify
```

Команда выполняет `ruff format --check`, `ruff check`, `pytest` (58 тестов) и дымовую проверку
приложения. **Пока проверка не зелёная — коммитить нельзя.**

### Ручная проверка в браузере

```powershell
.\scripts\dev.ps1 run
```

Открыть <http://127.0.0.1:8000> и убедиться, что новая функция работает, а старая не сломалась.
Остановить сервер — `Ctrl+C`.

---

## Шаг 4. Осмысленные коммиты

Несколько небольших коммитов лучше одного большого. История должна читаться как рассказ о
работе:

```powershell
git add app/models.py app/schemas.py
git commit -m "feat(hotel): добавить сущность брони гостиницы"

git add app/services.py
git commit -m "feat(hotel): реализовать правило срока подтверждения брони"

git add tests/test_workflow.py
git commit -m "test(hotel): покрыть подтверждение и истечение брони"

git add docs/API.md README.md
git commit -m "docs(hotel): описать методы API гостиницы"
```

Проверить историю:

```powershell
git log --oneline --graph --decorate -10
```

Ожидаемый вид:

```
* 9f2c1ab (HEAD -> feature/4-hotel-booking) docs(hotel): описать методы API гостиницы
* 4d81e30 test(hotel): покрыть подтверждение и истечение брони
* 1c05f77 feat(hotel): реализовать правило срока подтверждения брони
* 77ab204 feat(hotel): добавить сущность брони гостиницы
* 3e91d55 (main) chore: создать каркас проекта
```

Проверить, что в коммит не попали лишние файлы:

```powershell
git status --short
git show --stat HEAD
```

Если файл попал в индекс по ошибке:

```powershell
git restore --staged <файл>
```

---

## Шаг 5. Отправка ветки в удалённый репозиторий

```powershell
git push -u origin feature/4-hotel-booking
```

---

## Шаг 6. Запрос на слияние (Pull Request)

> **Внимание.** Создать запрос на слияние можно только из веб-интерфейса GitHub — в Git нет
> команды для создания PR. Если ветка уже отправлена (`git push -u origin <ветка>`), GitHub
> показывает на странице репозитория кнопку **Compare & pull request**. Откройте
> `https://github.com/Galaxy-1337/PopiKazaryan_DevOps_2026/pulls` и нажмите
> **New pull request**, если подсказка не появилась.

1. Открыть репозиторий на GitHub — появится подсказка **Compare & pull request**.
2. Base: `main`, compare: `feature/4-hotel-booking`.
3. Заголовок: `feat(hotel): учёт потребности в гостинице (#4)`.
4. Описание заполнить по шаблону из [`CONTRIBUTING.md`](../CONTRIBUTING.md), обязательно
   указать `Closes #4` и раздел «Как проверить».
5. Вкладка **Checks** — дождаться зелёного CI (две группы: «Локальные проверки и тесты» и
   «Сборка и проверка контейнера»).
6. Вкладка **Files changed** — просмотреть дифф, убедиться, что нет `.env`, `data/`,
   `backups/` и посторонних файлов.
7. **Merge pull request** → **Confirm merge**. Для демонстрации истории лучше выбрать
   `Create a merge commit`, чтобы в истории был виден факт слияния ветки.
8. Удалить ветку на GitHub (**Delete branch**) и локально:

```powershell
git switch main
git pull --ff-only
git branch -d feature/4-hotel-booking
```

Проверить результат:

```powershell
git log --oneline --graph --decorate -12
```

---

## Шаг 7. Моделирование и разрешение конфликта слияния

Конфликт создаётся намеренно: две ветки добавляют разные строки **в одно и то же место одного
файла**. Ниже приведён тот сценарий, который уже выполнен в этом репозитории: ветки
`feature/2-teams-section` и `feature/3-section-capacity` правили константы в
`app/services.py`.

### 7.1 Создать конфликт

```powershell
# Ветка A: значение по умолчанию 4 и верхняя граница
git switch main
git switch -c feature/2-teams-section
# в app/services.py добавляем после ACTIVE_SECTION_STATUSES:
#   DEFAULT_SECTION_CAPACITY = 4
#   MAX_SECTION_CAPACITY = 100
git add app/services.py
git commit -m "feat(sections): задать вместимость секции по умолчанию и предел вместимости"
git push -u origin feature/2-teams-section
```

Не сливая ветку A, создать ветку B от `main`, которая правит **то же место** иначе:

```powershell
git switch main
git switch -c feature/3-section-capacity
# в app/services.py добавляем после ACTIVE_SECTION_STATUSES:
#   DEFAULT_SECTION_CAPACITY = 5
#   MIN_SECTION_CAPACITY = 1
git add app/services.py
git commit -m "feat(sections): поднять вместимость секции по умолчанию и задать минимум"
git push -u origin feature/3-section-capacity
```

### 7.2 Слить первую ветку

Создать и слить PR из `feature/2-teams-section` в `main` (шаг 6). После слияния:

```powershell
git switch main
git pull --ff-only
```

Если PR создавать не хочется (например, чтобы просто получить конфликт), ветку можно слить
локально:

```powershell
git merge --no-ff -m "merge: влить feature/2-teams-section (вместимость секции по умолчанию)" feature/2-teams-section
```

### 7.3 Получить конфликт

Слить вторую ветку в `main` — Git сообщит о конфликте:

```powershell
git merge --no-ff feature/3-section-capacity
```

Ожидаемый вывод:

```
Auto-merging app/services.py
CONFLICT (content): Merge conflict in app/services.py
Automatic merge failed; fix conflicts and then commit the result.
```

Посмотреть состояние:

```powershell
git status
```

```
Unmerged paths:
  (use "git add <file>..." to mark resolution)
        both modified:   app/services.py
```

### 7.4 Разрешить конфликт

Открыть файл в VS Code. Git вставил маркеры прямо в то место, куда обе ветки добавляли строки:

```text
ACTIVE_SECTION_STATUSES = (ApplicationStatus.SUBMITTED, ApplicationStatus.ACCEPTED)

# Вместимость секции по умолчанию, если значение не задано в конференции.
<<<<<<< HEAD
DEFAULT_SECTION_CAPACITY = 4
# Максимальная вместимость секции, которую допускает интерфейс организатора.
MAX_SECTION_CAPACITY = 100
=======
DEFAULT_SECTION_CAPACITY = 5
# Минимальная вместимость секции: меньше одного места она иметь не может.
MIN_SECTION_CAPACITY = 1
>>>>>>> feature/3-section-capacity
```

Порядок разрешения:

1. Понять, какое значение верное. Для значения по умолчанию принимается `5` из ветки
   `feature/3-section-capacity`, но **изменения обеих веток должны сохраниться**: ограничения
   `MIN_SECTION_CAPACITY = 1` и `MAX_SECTION_CAPACITY = 100` не конфликтуют между собой.
2. Удалить маркеры `<<<<<<<`, `=======`, `>>>>>>>` и оставить согласованный вариант:

```text
# Вместимость секции по умолчанию, если значение не задано в конференции.
DEFAULT_SECTION_CAPACITY = 5
# Минимальная вместимость секции: меньше одного места она иметь не может.
MIN_SECTION_CAPACITY = 1
# Максимальная вместимость секции, которую допускает интерфейс организатора.
MAX_SECTION_CAPACITY = 100
```

3. Проверить, что не потерялись изменения обеих сторон.
4. Проверить, что конфликтов не осталось:

```powershell
git diff --check
Select-String -Path . -Pattern '^(<<<<<<<|=======|>>>>>>>)' -Recurse -ErrorAction SilentlyContinue
```

5. Прогнать проверки — **обязательно**, потому что слияние могло сломать код:

```powershell
.\scripts\dev.ps1 verify
```

6. Зафиксировать результат слияния:

```powershell
git add app/services.py
git commit -m "merge: разрешить конфликт вместимости секции (оставлено 5 мест)"
git push
```

### 7.5 Альтернатива: разрешение в VS Code

VS Code показывает конфликтные файлы в панели **Source Control**. Для каждой группы маркеров
доступны действия **Accept Current Change**, **Accept Incoming Change**, **Accept Both
Changes**, **Compare Changes**. Для этого конфликта удобнее всего **Accept Both Changes**, а
затем поправить значение по умолчанию вручную.

### 7.6 Альтернатива: полностью отказаться от слияния

```powershell
git merge --abort
```

Вернуться к состоянию до слияния — тоже допустимый способ разрешения, если изменение не нужно.

---

## Шаг 8. Тег первой версии `v0.1.0`

```powershell
# Убедиться, что main актуален и проверки зелёные
git switch main
git pull --ff-only
.\scripts\dev.ps1 verify

# Создать аннотированный тег
git tag -a v0.1.0 -m "Первая версия: участники, заявки, оргвзносы, тезисы, гостиница, приглашения, отчёты"

# Отправить тег в репозиторий
git push origin v0.1.0

# Проверить
git tag -n
git show v0.1.0 --stat
```

На GitHub тег появится в разделе **Releases** → **Tags**. При желании там же оформляется
Release с описанием изменений.

---

## Шаг 9. Доказательство, что секреты и локальные файлы не попадают в репозиторий

Это отдельный пункт проверки на защите. Готовые команды:

```powershell
# 1. Какие файлы игнорируются и каким правилом
git check-ignore -v .env data/conference.db backups/

# 2. Полный список игнорируемых файлов
git status --ignored --short

# 3. Что реально отслеживается Git (в списке не должно быть .env, *.db, backups/)
git ls-files

# 4. Поиск случайно закоммиченных секретов в истории
git log --all --full-history -- .env
git log --all -p -- .env.example
```

Если `.env` всё же попал в коммит:

```powershell
git rm --cached .env
git commit -m "chore: убрать .env из репозитория"
```

> Важно: удаление файла коммитом не убирает его из истории. Если в репозиторий попал реальный
> пароль или токен — его необходимо **сменить**, потому что он считается скомпрометированным.

---

## Шпаргалка по командам

| Задача | Команда |
|---|---|
| Посмотреть состояние | `git status` |
| Посмотреть историю | `git log --oneline --graph --decorate -15` |
| Создать ветку | `git switch -c feature/4-hotel-booking` |
| Переключиться | `git switch main` |
| Добавить изменения | `git add .` |
| Зафиксировать | `git commit -m "feat(hotel): ..."` |
| Отправить ветку | `git push -u origin feature/4-hotel-booking` |
| Обновить main | `git pull --ff-only` |
| Слить ветку локально | `git merge feature/4-hotel-booking` |
| Отменить слияние | `git merge --abort` |
| Посмотреть теги | `git tag -n` |
| Создать тег | `git tag -a v0.1.0 -m "..."` |
| Отправить тег | `git push origin v0.1.0` |
| Удалить локальную ветку | `git branch -d feature/4-hotel-booking` |
| Удалить ветку на сервере | `git push origin --delete feature/4-hotel-booking` |
| Отменить последний коммит (без потери кода) | `git reset --soft HEAD~1` |
| Убрать файл из индекса | `git restore --staged <файл>` |
| Отменить правки в файле | `git restore <файл>` |

---

## Работа в VS Code

### Открытие проекта

```powershell
cd "C:\Users\Иван\Desktop\ПЕРВЫЙ проект\DevOps"
code .
```

Если `code` не найден: в VS Code `Ctrl+Shift+P` → **Shell Command: Install 'code' command in
PATH**.

### Полезные расширения

- **Python** (ms-python.python) — запуск, отладка, интерпретатор;
- **Ruff** (charliermarsh.ruff) — подсветка замечаний и форматирование по `pyproject.toml`;
- **GitLens** — история строк, авторство;
- **GitHub Pull Requests** — создание и просмотр PR без выхода из редактора;
- **Docker** — управление контейнерами;
- **Even Better TOML**, **YAML** — подсветка конфигураций.

### Запуск и отладка

1. `Ctrl+Shift+P` → **Python: Select Interpreter** → выбрать `.\.venv\Scripts\python.exe`.
2. Терминал (`Ctrl+`` ` ``) → `.\scripts\dev.ps1 verify` для проверок.
3. Панель **Run and Debug** → создать `launch.json` для FastAPI:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI: app.main",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
      "jinja": true,
      "justMyCode": false
    }
  ]
}
```

4. Панель **Testing** (иконка колбы) — запуск отдельных тестов и отладка падающих.

### Работа с Git внутри VS Code

1. Панель **Source Control** (`Ctrl+Shift+G`) — список изменённых файлов.
2. Ввести сообщение коммита в поле сверху → `Ctrl+Enter` — коммит.
3. Кнопка **Sync Changes** — `git pull` + `git push` одной кнопкой.
4. Панель **Source Control Graph** (расширение GitLens) — визуальная история веток и слияний.

> Перед коммитом из VS Code всё равно выполняется `.\scripts\dev.ps1 verify` в терминале —
> проверка не отменяется удобной кнопкой.
