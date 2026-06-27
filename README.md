# Feature Store API

A production-style feature store that computes, stores, and serves ML features for a User entity — built with FastAPI, Redis (online store), SQLite/SQLModel (offline store), and Alembic for migrations.

---

## How It Works

```
POST /features/{entity_id}          →  store pre-computed features → write to BOTH stores
POST /features/{entity_id}/compute  →  compute features from raw data → write to BOTH stores
GET  /features/{entity_id}          →  fast lookup from Redis (online store)
GET  /features/{entity_id}/history  →  full historical record from SQLite (offline store)
GET  /health                        →  health check
```

---

## Table of Contents

- [Why Two Stores?](#why-two-stores)
- [Feature Schema](#feature-schema)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Database Migrations](#database-migrations)
- [Running Tests](#running-tests)
- [API Endpoints](#api-endpoints)
- [Request & Response Schemas](#request--response-schemas)
- [Example Usage](#example-usage)
- [Docker](#docker)

---

## Why Two Stores?

Real-time ML inference needs feature values in milliseconds — a model can't wait on a database query while a live prediction is happening. Training a model, on the other hand, needs the **full history** of how a feature's value changed over time.

This API mirrors that real-world split:

```
Online store (Redis)    → only the LATEST value per entity, millisecond lookups
Offline store (SQLite)  → every historical snapshot ever computed, used for training
```

Every write updates both — overwriting the "current" value in Redis while appending a permanent new row to SQLite. This is the same pattern production feature stores like Feast and Tecton are built around.

---

## Feature Schema

Tracking a **User** entity:

| Feature | Type | Description |
|---|---|---|
| `total_purchases` | `int` | Total number of purchases ever made |
| `total_spend` | `float` | Total amount spent across all purchases |
| `avg_order_value` | `float` | Average amount per order |
| `num_logins_7d` | `int` | Logins in the last 7 days |
| `num_logins_30d` | `int` | Logins in the last 30 days |
| `days_since_last_login` | `int` | Days since most recent login (`-1` if never) |
| `days_since_last_purchase` | `int` | Days since most recent purchase (`-1` if never) |
| `account_age_days` | `int` | Days since account creation |
| `computed_at` | `datetime` | When this snapshot was computed (offline store only adds new rows; online store overwrites) |

---

## Project Structure

```
feature-store-api/
├── .github/
│   └── workflows/
│       └── ci.yml                — GitHub Actions CI pipeline
├── app/
│   ├── __init__.py
│   ├── main.py                   — FastAPI app and route handlers
│   ├── database.py               — SQLite engine, session, get_db
│   ├── model.py                  — FeatureSnapshot (offline store table)
│   ├── schema.py                 — Request/response schemas
│   ├── store.py                  — Redis online store (save/get latest features)
│   ├── crud.py                   — Offline store operations (save snapshot, get history)
│   └── services/
│       ├── __init__.py
│       └── features.py           — compute_features (raw data → derived features)
├── app/test/
│   ├── __init__.py
│   └── test_app.py                — Full test suite
├── migrations/                    — Alembic migration scripts
├── .dockerignore
├── .env                           — Environment variables
├── .gitignore
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── feature_store.db               — SQLite database file (local dev)
├── README.md
├── requirements.txt
└── start.sh                       — Runs migrations, then starts uvicorn
```

---

## Requirements

- Python 3.12+
- Docker and Docker Compose
- Redis (handled by Docker Compose, or run standalone for local dev)

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/HonourJAH/feature-store-api.git
cd feature-store-api
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
```

```
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=sqlite:///./feature_store.db
```

### 5. Start Redis

```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### 6. Run database migrations

```bash
alembic upgrade head
```

### 7. Start the API server

```bash
uvicorn app.main:app --reload
```

API available at `http://localhost:8000`
Interactive docs at `http://localhost:8000/docs`

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL for the online store |
| `DATABASE_URL` | `sqlite:///./feature_store.db` | SQLite connection URL for the offline store |

> **Important:** Alembic reads `DATABASE_URL` from the environment (via `migrations/env.py`) so migrations always target the exact same database the app connects to. Keep this variable consistent across `.env`, `docker-compose.yml`, and any deployment environment — a mismatch here means migrations create tables in one file while the app reads from another.

---

## Database Migrations

This project uses Alembic, with table creation owned **entirely** by migrations — the app itself never calls `create_all()`.

**Apply all pending migrations:**

```bash
alembic upgrade head
```

**Create a new migration after changing `model.py`:**

```bash
alembic revision --autogenerate -m "describe your change"
```

**Always inspect the generated file before applying it** — `--autogenerate` only detects the difference between your models and whatever database `alembic.ini`/`DATABASE_URL` currently points to. If that database already matches your models (e.g. it was created manually outside of Alembic), the generated migration's `upgrade()` will be empty, silently failing to create anything in a fresh environment.

**Roll back the last migration:**

```bash
alembic downgrade -1
```

---

## Running Tests

Redis is mocked with `fakeredis` and SQLite runs in-memory — no real infrastructure required.

```bash
pytest -v
```

Run with coverage:

```bash
pytest -v --cov=app --cov-report=term-missing
```

---

## API Endpoints

| Method | Endpoint | Description | Status Code |
|---|---|---|---|
| `POST` | `/features/{entity_id}` | Store pre-computed feature values | `201 Created` |
| `POST` | `/features/{entity_id}/compute` | Compute features from raw data, then store | `201 Created` |
| `GET` | `/features/{entity_id}` | Fast lookup of current features (Redis) | `200 OK` |
| `GET` | `/features/{entity_id}/history` | Full historical record (SQLite) | `200 OK` |
| `GET` | `/health` | Health check | `200 OK` |

---

## Request & Response Schemas

### `POST /features/{entity_id}`

**Request body:**

```json
{
  "total_purchases": 5,
  "total_spend": 250.0,
  "avg_order_value": 50.0,
  "num_logins_7d": 3,
  "num_logins_30d": 12,
  "days_since_last_login": 1,
  "days_since_last_purchase": 4,
  "account_age_days": 90
}
```

**Response:**

```json
{
  "entity_id": "user_123",
  "total_purchases": 5,
  "total_spend": 250.0,
  "avg_order_value": 50.0,
  "num_logins_7d": 3,
  "num_logins_30d": 12,
  "days_since_last_login": 1,
  "days_since_last_purchase": 4,
  "account_age_days": 90,
  "computed_at": "2026-06-25T20:02:13.670311Z"
}
```

---

### `POST /features/{entity_id}/compute`

**Request body** — simulates raw event data pulled from an orders/logins database:

```json
{
  "purchases": [
    { "amount": 49.99, "date": "2026-01-15" },
    { "amount": 89.50, "date": "2026-03-02" }
  ],
  "logins": ["2026-06-20", "2026-06-24", "2026-06-25"],
  "account_created_at": "2026-01-01"
}
```

The API derives `total_purchases`, `total_spend`, `avg_order_value`, login counts, and recency features from this raw data, then writes the result to both stores — same response shape as above.

---

### `GET /features/{entity_id}`

Returns the **current** snapshot from Redis. Returns `404` if no features have ever been computed for this entity.

---

### `GET /features/{entity_id}/history`

```json
{
  "entity_id": "user_123",
  "result": 2,
  "history": [
    { "entity_id": "user_123", "total_purchases": 5, "...": "...", "computed_at": "2026-06-25T19:56:01" },
    { "entity_id": "user_123", "total_purchases": 7, "...": "...", "computed_at": "2026-06-25T20:02:13" }
  ]
}
```

Every `POST` call appends a new row here — this list only ever grows, never overwrites.

---

### `GET /health`

```json
{ "status": "healthy" }
```

---

## Example Usage

### Store pre-computed features

```bash
curl -X POST http://localhost:8000/features/user_123 \
  -H "Content-Type: application/json" \
  -d '{
    "total_purchases": 5,
    "total_spend": 250.0,
    "avg_order_value": 50.0,
    "num_logins_7d": 3,
    "num_logins_30d": 12,
    "days_since_last_login": 1,
    "days_since_last_purchase": 4,
    "account_age_days": 90
  }'
```

### Compute features from raw data

```bash
curl -X POST http://localhost:8000/features/user_456/compute \
  -H "Content-Type: application/json" \
  -d '{
    "purchases": [
      {"amount": 49.99, "date": "2026-01-15"},
      {"amount": 89.50, "date": "2026-03-02"}
    ],
    "logins": ["2026-06-20", "2026-06-24", "2026-06-25"],
    "account_created_at": "2026-01-01"
  }'
```

### Fast lookup (online store)

```bash
curl http://localhost:8000/features/user_123
```

### Full history (offline store)

```bash
curl -s http://localhost:8000/features/user_123/history | python3 -m json.tool
```

---

## Docker

### Run with Docker Compose

Starts Redis and the API together. `start.sh` runs `alembic upgrade head` before launching uvicorn, so the database schema is always in place before the API accepts requests.

```bash
docker compose up --build
```

### Stop everything

```bash
docker compose down -v
```

### Services

| Service | Port | Description |
|---|---|---|
| `api` | `8000` | FastAPI server |
| `redis` | `6379` | Online feature store |

### Persistence

Both Redis data and the SQLite database file are mounted as named volumes (`redis_data`, `feature_store_data`), so feature history survives container restarts. Use `docker compose down -v` only when you intentionally want a clean slate — it deletes both volumes.

### Build the image only

```bash
docker build -t feature-store-api .
```
