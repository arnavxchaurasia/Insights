# Market Intel

Indian market, economy and policy news in one place. Phase 1: RSS ingestion and a news feed.

## Layout

- `backend/` — FastAPI service. Ingests the feeds in `feeds.json` every 15 minutes, de-duplicates by normalised URL, and serves `/api/articles` and `/api/sources`.
- `frontend/` — Next.js app that renders the feed (category filter, headline search, pagination).

## Run locally

Backend (from `backend/`):

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Frontend (from `frontend/`):

```
npm install
npm run dev
```

Tests: `.venv\Scripts\python -m pytest` from `backend/`.

## Configuration

Backend settings are environment variables prefixed `MI_` (or a `backend/.env` file), defined in `backend/app/config.py`. The frontend reads `API_URL` (default `http://127.0.0.1:8000`).

### Database

`MI_DATABASE_URL` selects the database. It defaults to a local SQLite file (`backend/data/app.db`), which needs no setup — the directory is created automatically on first run.

For deployment, point it at Postgres:

```
MI_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

This uses the `psycopg` (v3) driver, which is in `requirements.txt`. On a non-SQLite backend the engine enables `pool_pre_ping`, so a connection dropped by the server or a pooler is detected and replaced rather than failing the next request.

**Never commit a real connection string.** Keep credentials in the deployment environment (or an uncommitted `backend/.env`); `.env` is git-ignored.

### Database Migrations (Alembic)

Database schema is managed with Alembic:

- Apply pending migrations to head:
  ```bash
  alembic upgrade head
  ```
- Generate a new migration after changing models in `app/models.py`:
  ```bash
  alembic revision --autogenerate -m "describe_change"
  ```
The app runs `alembic upgrade head` automatically on startup.

## Feeds

Add or disable sources in `backend/feeds.json`; changes apply on the next backend start. Only the headline, a short snippet and the link are stored. Moneycontrol, Business Standard and PIB are disabled because they reject automated readers (HTTP 403).
