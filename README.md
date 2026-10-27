# Compas

Включены:

- регистрация, вход, обновление токенов, восстановление пароля, вход через Яндекс;
- профиль, редактирование данных, аватар;
- анкета и каталог психологов, заявки, подтверждённые клиенты, доступ к их результатам;
- алерты психологу по Беку, STAI и DASS-21.

## Проверка в Swagger

1. `POST /auth/register`: email, username, gender, password, confirm_password. Пол обязателен; дата рождения, город, телефон необязательны.
2. `POST /auth/login`, затем `GET /auth/me`. Авторизация работает через собственные cookie `compas_access_token` и `compas_refresh_token`; они не перезаписывают вход в «Одеяло» на том же компьютере. Используйте один адрес хоста (`127.0.0.1` либо `localhost`) последовательно.
3. `GET /tests`, `GET /tests/{test_id}/questions/answers`.
4. `POST /tests/result`: `test_id`, `date` в ISO-формате и `results` со значениями **score** из вариантов каждого вопроса, в порядке `number`. Сохраняется фактическое время прохождения. Число и значения ответов проверяются.
5. `GET /tests/{test_id}/results/`: все прохождения. `GET /tests/passed/user`: одна карточка на тест.
6. Для психолога зарегистрируйте второй аккаунт; назначьте роль через административную CLI ниже. Заполните анкету `PATCH /psychologist/become`: сама анкета **не повышает роль**.
7. Клиент: `POST /applications` с `manager_id` психолога, `text`, `inquiry: []`. Психолог: `PATCH /applications/{app_id}/confirm`.
8. Психолог: `GET /client`, `GET /psychologist/clients/{client_id}/test-results`, `GET /psychologist/alerts`.


```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

Тесты используют отдельную SQLite в памяти с адаптацией PostgreSQL-массивов только в тестах. Проверяются все 13 расчётов и история, повторная загрузка каталога, профиль, заявки, доступ и границы алертов. SQLite не заменяет проверку миграции и поведения под нагрузкой на PostgreSQL.
