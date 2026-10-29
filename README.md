# Compas

## Запуск

Нужны Git и запущенный Docker Desktop (Linux containers). Python и PostgreSQL на компьютер устанавливать не нужно.

Первый запуск:

```powershell
git clone --branch compas https://github.com/DanialKonurkulzhaev/compas.git
cd compas
docker compose -f docker-compose.init.yml run --rm init
docker compose up -d --build
docker compose ps -a
```

Команда `init` создаёт `.env`; существующий файл не перезаписывается. Если остался `.env` от «Одеяла», сначала переименуйте его в `.env.old`. Настроенный `.env` Compas и его секреты сохраняйте.

Swagger: **http://localhost:8001/docs**. Миграции и каталог из 13 тестов создаются автоматически. `migrate` и `seed` завершаются с кодом 0 — это нормально; `db` и `app` должны стать healthy.

Если проект уже скачан, обновление и запуск выполняются из его папки:

```powershell
git switch compas
git pull --ff-only
docker compose -f docker-compose.init.yml run --rm init
docker compose up -d --build
```

Если запуск не удался:

```powershell
docker compose logs --tail 100 migrate seed app nginx
```

Остановка: `docker compose stop`. Данные сохраняются; для обычного обновления не используйте `down -v`.

### Подключение локального фронта

Для фронта, запущенного через `npm run dev`, в его `.env.development`:

```dotenv
NEXT_PUBLIC_SERVER_API_URL=http://localhost:8001
NEXT_PUBLIC_BFF_API_URL=http://localhost:3000/api
```

После изменения перезапустите `npm run dev`. Фронт открывается на http://localhost:3000; общая Docker-сеть для этого режима не нужна. Вход через Яндекс настраивается отдельно: [docs/yandex-login.md](docs/yandex-login.md).

Для запуска самого фронта в Docker: [docs/frontend-integration.md](docs/frontend-integration.md).

В Linux пользователь контейнера подготовки по умолчанию имеет UID/GID 1000. Если UID/GID владельца проекта другие, задайте `LOCAL_UID` и `LOCAL_GID` перед первой командой. Секреты и дампы не входят в репозиторий.

Включены:

- регистрация, вход, обновление токенов, восстановление пароля, вход через Яндекс;
- профиль, редактирование данных, аватар;
- анкета и каталог психологов, заявки, подтверждённые клиенты, доступ к их результатам;
- алерты психологу по Беку, STAI и DASS-21.

## Проверка в Swagger

1. `POST /auth/register`: email, username, gender, password, confirm_password. Пол обязателен; дата рождения, город, телефон необязательны.
2. `POST /auth/login`, затем `GET /auth/me`.
3. `GET /tests`, `GET /tests/{test_id}/questions/answers`.
4. `POST /tests/result`: `test_id`, `date`
5. `GET /tests/{test_id}/results/`: все прохождения. `GET /tests/passed/user`: одна карточка на тест.
6. Для психолога зарегистрируйте второй аккаунт; назначьте роль через административную CLI ниже. Заполните анкету `PATCH /psychologist/become`: сама анкета **не повышает роль**.
7. Клиент: `POST /applications` с `manager_id` психолога, `text`, `inquiry: []`. Психолог: `PATCH /applications/{app_id}/confirm`.
8. Психолог: `GET /client`, `GET /psychologist/clients/{client_id}/test-results`, `GET /psychologist/alerts`.


```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

Тесты используют отдельную SQLite в памяти с адаптацией PostgreSQL-массивов только в тестах. Проверяются все 13 расчётов и история, повторная загрузка каталога, профиль, заявки, доступ и границы алертов. SQLite не заменяет проверку миграции и поведения под нагрузкой на PostgreSQL.
