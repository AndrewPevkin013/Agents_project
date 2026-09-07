# Auth Service

Готовый отдельный сервис авторизации для мультиагентной системы.

## Реализовано

- FastAPI
- PostgreSQL
- SQLAlchemy 2 async + asyncpg
- Alembic migrations
- Argon2id password hashing
- JWT access token
- refresh token rotation
- в БД хранится только SHA-256 hash refresh token
- logout/revocation refresh token
- роли пользователей
- Docker Compose

## API

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /health`

## Быстрый запуск через Docker

1. Скопировать `.env.example` в `.env`.
2. Сгенерировать JWT secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

3. Вставить его в `JWT_SECRET_KEY`.
4. Запустить:

```bash
docker compose up --build
```

Swagger:

```text
http://127.0.0.1:8080/docs
```

## Локальный запуск без Docker для Python

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

## Register

```json
{
  "username": "andrew",
  "email": "andrew@example.com",
  "password": "VeryStrongPassword123!"
}
```

## Login

```json
{
  "login": "andrew",
  "password": "VeryStrongPassword123!"
}
```

Login принимает username или email.

## /auth/me

Передать header:

```text
Authorization: Bearer <access_token>
```

## Важно

Пароли не шифруются обратимо. Они хэшируются Argon2id.

Access token живёт недолго и не хранится в БД.
Refresh token генерируется случайно; в БД хранится только его SHA-256 hash.
После `/auth/refresh` старый refresh token становится revoked.

Для production позже лучше перейти с HS256 на асимметричную подпись (RS256 или EdDSA), чтобы Agent Service хранил только public key и мог проверять токены, но не выпускать их.
