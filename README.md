# Compas

## Запуск

Нужен Docker Desktop с Linux-контейнерами. Локальные Python и PostgreSQL не требуются.

Из корня проекта:

```powershell
docker compose -f docker-compose.init.yml run --rm init
docker compose up -d --build
docker compose ps -a
```

Первая команда создаёт `.env` с новыми ключами. Существующий файл не перезаписывается. `.env` от «Одеяла» не подходит: перед первым запуском сохраните его под другим именем. Не заменяйте секреты уже используемой базы.

Swagger: http://localhost:8001/docs. Миграции и загрузка недостающих записей каталога выполняются автоматически. `migrate` и `seed` должны завершиться с кодом 0, `db` и `app` — перейти в healthy. При ошибке: `docker compose logs --tail 100 migrate seed app`.

Для запуска совместно с фронтом: [docs/frontend-integration.md](docs/frontend-integration.md).

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
