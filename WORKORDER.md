# Market Intel — Work Order & Build Tracker

Last updated: 2026-11-15

A living, trackable plan for building Market Intel end to end with good
engineering practice. It is written to be executed by an **AI coding agent**:
every task carries a self-contained, copy-paste **prompt** so the agent has all
the context it needs, plus **acceptance criteria** so you can tell when it is done.

> **Current status (2026-11-15).** The code is a git repo pushed to the **public
> GitHub repo `arnavxchaurasia/Insights`** (https://github.com/arnavxchaurasia/Insights).
> GitHub Actions CI runs on push to `main` and every PR and is **green**. Local
> clone: `C:\Users\arnav\dev\market-intel`.
>
> **IMPORTANT — layout:** the project is the **repo root**. `backend/` and
> `frontend/` sit at the top level; there is **no** `market-intel/` wrapper folder
> anymore. Any path in this document written as `market-intel/backend/...` means
> `backend/...` from the repo root.
>
> Done: Phase 1 (feed + SSE bell), **6.1** (out of OneDrive), **6.2** (Postgres),
> **6.3** (story de-duplication), **6.4** (CI), **7.1** (model-provider interface),
> **H1–H4** (Ruff, mypy, Alembic migrations, pinned deps — all via PRs #1–#4,
> verified 2026-11-15).
>
> **BUILD ORDER (decided 2026-11-15): build the product fully first, deploy last.**
> Deployment (6.5a/6.5b) is **DEFERRED** — do it only after Phases 2–4 are done.
> **Next task → 7.4 (Impact UI on each article).** Then work straight
> through Phase 2 → Phase 3 → Phase 4, and come back to 6.5 at the very end.
>
> Phase 2 is the AI layer but is **not blocked** on choosing or paying for a model:
> every AI task is built behind a swappable `LLMProvider` and tested with a
> `FakeProvider` (tests never hit a real model). The real model endpoint + key
> (decision C) and hosting (decision D) are both wired in later. The Progress
> tracker (section 4) is the source of truth.
>
> **Engineering hardening (NEW — section 12).** Features alone are not "end to end".
> Section 12 adds the production-grade engineering scaffolding (migrations, linting,
> typing, pinned deps, rate limiting, security headers, observability, branch
> protection, …) as trackable tasks. **Do the P1 items there interleaved with the
> feature work, not all at the end.** In particular, do **H3 (Alembic migrations)
> and H1/H2 (Ruff + mypy) BEFORE 7.2**, because 7.2/7.3/8.x each add new tables —
> adopting migrations now avoids reworking the hand-written `ALTER TABLE` hack
> later. Suggested order: H1, H2, H4, H3 → then 7.2 onward, folding in the rest of
> section 12 as you go.
>
> **More scope added (sections 14–17):** **Phase 5 (§14)** is the cross-impact
> intelligence layer — the product's core thesis — built on Phase 2 impacts (do
> after 7.3). **Phase 6 (§15)** is public-launch readiness (methodology/disclaimer
> page, SEO, a11y) — do before deploy. **§16** is a data-ops backlog and **§17** a
> small review-fix backlog; pick these up opportunistically.

---

## 0. How to use this document

1. Work **top to bottom**, one task at a time. Do not skip ahead — later tasks
   assume earlier ones are done.
2. For each task: first paste the **System preamble** (section 3) into your model,
   then paste that task's **Prompt**.
3. When the model is finished, check the **Acceptance criteria**. Only then tick
   the box `[x]` in this file and in the **Progress tracker** (section 4).
4. If a task says **STOP and ask** about something, do not let the model guess —
   bring the question to a human.
5. Keep every change small. One task = one focused change = one commit.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked.

---

## 1. Product principles (never violate)

- **Public product → informational only.** Describe impact ("this affects sector
  X"). Never give buy/sell calls on specific stocks (SEBI research-analyst rules).
- **Store light.** Only headline + short snippet + link back to the publisher.
- **No bot-spoofing.** Do not disguise the reader as a browser to beat a site that
  blocks bots. Find a permitted source, license a feed, or STOP and ask.
- **AI output always carries its sources and a confidence level.** Never show a
  bare inference.
- **No invented data.** No made-up prices, dates, or figures. Always show "as of".

---

## 2. Architecture & tech stack

```
RSS / data sources ──▶ Ingestion (Python) ──▶ Postgres ──▶ FastAPI ──▶ Next.js UI
                                                   ▲
                                   AI enrichment (hosted open-source model)
```

- **Backend:** Python 3.14, FastAPI, SQLAlchemy 2.x, APScheduler, httpx, feedparser.
- **Database:** SQLite for local dev, Postgres in production (one env var switch).
- **Frontend:** Next.js (App Router, TypeScript), Tailwind CSS.
- **Real-time:** Server-Sent Events (SSE) from FastAPI → a React hook in the UI.
- **AI:** one hosted open-source model behind a single swappable interface.

---

## 3. System preamble (paste this into the model FIRST, every session)

> You are working on "Market Intel", a FastAPI + Next.js app that aggregates
> Indian market/economy/policy news and will add AI impact-analysis. Follow these
> rules exactly:
>
> **Conventions**
> - The project is the **repo root** (`arnavxchaurasia/Insights`). Backend code
>   lives in `backend/app/`, tests in `backend/tests/`. Frontend in `frontend/app/`.
>   There is no `market-intel/` wrapper folder.
> - Python: type-hint everything. Keep functions small and pure where possible.
>   Datetimes are stored naive-UTC. Settings go in `app/config.py` (env prefix
>   `MI_`), never hard-coded. Use SQLAlchemy 2.0 style (`select()`, `Mapped`).
> - Every backend behaviour change gets a pytest in `tests/`. Tests must pass with
>   `.venv\Scripts\python -m pytest` and must not hit the network (use a SQLite
>   in-memory DB and fake data).
> - TypeScript: no `any`. Client components start with `"use client"`. Wrap all
>   `localStorage`/`EventSource`/`fetch` in try/catch; the page must render if the
>   backend is down. Reuse the API base from `app/lib.ts`.
> - Accessibility & theming: every view must work in light and dark mode (use the
>   existing Tailwind `dark:` classes) and at phone width.
> - Do not add a dependency without saying why. Do not spoof browser User-Agents.
> - After changes, run the SAME checks CI runs (`.github/workflows/ci.yml`):
>   from `backend/` → `python -m pytest`; from `frontend/` → `npm run lint`,
>   then `npx next typegen`, then `npx tsc --noEmit`. **`next typegen` is required
>   before `tsc`** — Next emits its `LayoutProps`/`PageProps` ambient types into
>   `.next/types`, so a standalone `tsc` fails without it. Report what you ran.
> - Git & CI: **a task is NOT done until its code is committed AND on `main` with CI
>   green.** We build directly into `main` ("everything in main; we're only building
>   it"), so finish every task by committing and merging/pushing it to `main` — do
>   NOT leave work uncommitted or stranded on an unmerged branch (this happened with
>   7.2 and made it look done when it wasn't). A PR that merges to `main` is fine; a
>   dangling branch is not. Run the full CI-equivalent locally first (ruff check +
>   `ruff format --check`, mypy, `alembic upgrade head`, pytest; frontend lint +
>   `next typegen` + tsc). Any schema change ships an Alembic migration. NEVER commit
>   secrets, `.env`, `*.db`, `.venv/`, `node_modules/`, or `.next/` (all git-ignored).
>   One focused change per commit.
>
> **Hard limits** — if a task needs a data source that blocks bots, or a secret/API
> key, or a product decision, STOP and ask instead of guessing or scraping.
>
> Acknowledge these rules, then wait for the task.

---

## 4. Progress tracker

| Phase | Task | Status |
|---|---|---|
| 1 | RSS ingestion + feed UI | [x] |
| 1 | Real-time notification bell (SSE) | [x] |
| 1.5 | Move repo out of OneDrive | [x] |
| 1.5 | Switch to Postgres | [x] |
| 1.5 | Story de-duplication (clustering) | [x] |
| 1.5 | CI (tests + lint on push) | [x] |
| 1.5 | Containerise (Dockerfiles + compose) | [ ] DEFERRED — after Phase 4 |
| 1.5 | Provision & go live (needs host decision) | [ ] DEFERRED — after Phase 4 |
| 2 | Model-provider interface (swappable) | [x] |
| 2 | Article tagging (sector / event type) | [x] |
| 2 | Impact records (first/second-order) | [x] |
| 2 | Impact UI on each article | [ ] |
| 3 | Economic calendar | [ ] |
| 3 | FII/DII flows panel | [ ] |
| 3 | Commodity prices panel | [ ] |
| 3 | Seasonality reference calendar | [ ] |
| 4 | User accounts | [ ] |
| 4 | Watchlists | [ ] |
| 4 | Alerts (push to the bell) | [ ] |
| Eng | Engineering hardening — P1/P2/P3 tasks (see §12) | [~] interleave with features |
| 5 | Cross-impact: taxonomy, aggregation, graph, explorer, digest (§14) | [ ] |
| 6 | Public readiness: methodology, SEO, a11y, analytics, UI states (§15) | [ ] |
| Ops | Data ops: backfill, seed curation, govt source, cluster quality (§16) | [ ] |
| Fix | Review-fix backlog (§17) | [ ] |

---

## 5. Phase 1 — Feed & notifications ✅ DONE

- [x] **RSS ingestion + feed UI.** 12 feeds, 15-min scheduler, dedup by URL,
  `/api/articles` + `/api/sources`, Next.js feed with filter/search/paging.
- [x] **Real-time notification bell (SSE).** Backend `/api/stream` (SSE) and
  `/api/notifications`; frontend `useNotifications` hook + `NotificationBell`
  with unread badge and dropdown panel. Verified: a newly ingested article
  appears in the bell live, no refresh.

---

## 6. Phase 1.5 — Harden for production

### [x] 6.1 Move the repo out of OneDrive  — done 2026-11-14
**Why:** OneDrive syncs `node_modules`, slowing the dev server and risking
corruption. **Done:** repo moved to `C:\Users\arnav\dev\market-intel`. The venv
was deleted and rebuilt at the new path (Python hard-codes absolute paths in
`.venv`), and `frontend/.next` was deleted and regenerated. `.claude/launch.json`
lives inside the repo and already points at the new path. **Verified at new path:**
backend `pytest` 4 passed; imports OK; SQLite DB travelled intact (753 articles,
18 sources); frontend `npm run lint` clean; `next build` + TypeScript pass.
The stale `agent/.claude/launch.json` is left behind, harmless.

### [x] 6.2 Switch to Postgres  — done 2026-11-14
**Done:** `psycopg[binary]>=3.2` added to `requirements.txt`. The SQLite
directory-creation guard in `app/db.py` was pulled into a testable
`prepare_sqlite_dir()` (no-op for Postgres), and engine creation moved into
`make_engine()`, which enables `pool_pre_ping` for non-SQLite backends. README
documents `MI_DATABASE_URL=postgresql+psycopg://...` and warns never to commit a
real connection string (`.env` is git-ignored; none present). **Verified:** 9
pytest pass, including a new `tests/test_db.py` that exercises the Postgres branch
**offline** (engine + dialect load, no connection). **Not yet verified:** a live
connection to a real Postgres server — do this once a DB is provisioned (decision
D / 6.5 hosting).
**Original prompt:**
> Add Postgres support. (1) Add `psycopg[binary]` to `backend/requirements.txt`.
> (2) Document setting `MI_DATABASE_URL=postgresql+psycopg://user:pass@host/db` in
> the README. (3) Confirm `app/db.py` already reads that env var and that the
> SQLite-only directory-creation code is skipped for Postgres (it is guarded on
> the sqlite backend — verify and add a test). (4) Do NOT commit any real
> connection string. Run the test suite.
**Acceptance:** app starts against both SQLite (default) and a Postgres URL; no
secret committed; tests pass.

### [x] 6.3 Story de-duplication (clustering)  — done 2026-11-15
**Why:** the same story runs across ET/Mint/BusinessLine.
**Done:**
1. Added nullable `cluster_id` (indexed `VARCHAR(64)`) to `Article` in `backend/app/models.py`. Added migration guard in `backend/app/db.py:init_db` so existing databases safely gain the column.
2. Created pure function module `backend/app/cluster.py`:
   - `normalize_title_tokens(title)`: strips punctuation, preserves numeric values and percentages (e.g. `6.5%`, `24000`), normalizes units (e.g. `800 pts` → `800pts`), removes financial/headline stop words.
   - `token_set_similarity(tokens_a, tokens_b)`: combines Sørensen-Dice coefficient with subset containment. Threshold justified at 0.50 (cross-publisher rewrites score >= 0.50 while unrelated market stories score < 0.25).
   - `assign_cluster_id(title, recent_articles, threshold)`: matches against recent articles within 3 days or generates a new cluster ID.
3. Ingestion integration in `backend/app/ingest.py:store_entries`: incoming articles are clustered against existing articles from the past 3 days and within the current ingestion batch.
4. API in `backend/app/main.py`: `/api/articles` supports `?group=true`. When `group=true`, computes representative row per cluster with `also_covered_by = N - 1`. Default `group=false` behavior is completely unchanged (`also_covered_by = 0`).
5. Frontend in `frontend/app/page.tsx`: added "Group" filter toggle, pagination preserved, and renders `+N more source(s)` badge when `also_covered_by > 0`.
**Verified:**
- `backend`: 16 pytest passed (`pytest tests/test_cluster.py tests/test_db.py tests/test_ingest.py`). Unit tests verify cross-publisher headlines cluster together, distinct stories separate, and API grouped vs ungrouped behaviors.
- `frontend`: `npm run lint` clean (0 warnings, 0 errors) and `npx tsc --noEmit` clean (0 errors).
**Original prompt:**
> Add near-duplicate clustering so the feed shows one item per story. (1) Add a
> `cluster_id` column to `articles` (nullable). (2) In `app/` add a module that,
> for each new article, assigns it to an existing cluster if its normalised title
> is highly similar (use token-set similarity; threshold you justify) to a recent
> article (last 3 days), else starts a new cluster. Pure function, unit-tested with
> fixtures. (3) `/api/articles` gains `?group=true` returning one row per cluster
> with an `also_covered_by` count. (4) Frontend: when grouped, show "+N more
> sources". Keep it simple; no ML model, no new heavy dependency. Run tests + lint.
**Acceptance:** two headlines of the same story land in one cluster in a unit test;
grouped feed shows the "+N more" badge; ungrouped behaviour unchanged.

### [x] 6.4 CI (tests + lint on push)  — done 2026-11-15
**Done:** repo initialised with git and pushed to GitHub
`arnavxchaurasia/Insights` (public). Added `.github/workflows/ci.yml` with two
jobs on push-to-main / any PR: **backend** (Python 3.14, cached pip, `pytest`
with `MI_RUN_SCHEDULER=false`) and **frontend** (Node 24, cached npm, `npm ci`
→ `npm run lint` → `npx next typegen` → `npx tsc --noEmit`). The `next typegen`
step is required: Next emits its ambient `LayoutProps`/`PageProps` types into
`.next/types` at build time, so a standalone `tsc` fails without it (the first CI
run caught exactly this). Paths were adapted to the repo-root
layout (`backend/`, `frontend/`) since the project is now the repo root, not
`market-intel/`. `.gitignore` extended to exclude `*.db` and `.claude/`; no DB,
venv, node_modules, or secrets are tracked.
**Original prompt:**
> Add a GitHub Actions workflow `.github/workflows/market-intel-ci.yml` that, on
> push/PR touching `market-intel/**`, sets up Python 3.14 + Node 24, installs
> backend deps and runs `pytest`, installs frontend deps and runs `npm run lint`
> and `npx tsc --noEmit`. Cache pip and npm. No deploy step. Keep it under ~50 lines.
**Acceptance:** workflow is valid YAML; jobs run the three checks; fails if any fails.

> **⏸ DEFERRED (2026-11-15): do Section 6.5 LAST, after Phases 2–4.** The user
> chose to build the product fully before hosting. Skip 6.5 for now; the next task
> is **7.1**. Come back here only once Phase 4 is done.

### [ ] 6.5a Containerise (host-agnostic — build when you reach deploy)
**Why:** containers make the app runnable anywhere and are the unit every host
below consumes. Needs no hosting decision, so it is the first deploy step.
**Prompt:**
> Containerise the app for production. Create:
> - `backend/Dockerfile` — install `backend/requirements.txt`, run
>   `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2`. Use a slim
>   Python 3.14 base. Add a `backend/.dockerignore` (exclude `.venv`, `data`,
>   `__pycache__`, `*.db`).
> - `frontend/Dockerfile` — multi-stage: `npm ci` + `npm run build`, then a slim
>   runtime running `npm run start` on port 3000. Pass `NEXT_PUBLIC_API_URL` as a
>   build arg (Next inlines `NEXT_PUBLIC_*` at build time). Add `frontend/.dockerignore`
>   (exclude `node_modules`, `.next`).
> - `docker-compose.yml` at the repo root wiring three services: `db` (postgres:17,
>   named volume for data, healthcheck), `backend` (depends_on db healthy; env
>   `MI_DATABASE_URL=postgresql+psycopg://...`, `MI_CORS_ORIGINS` = the frontend
>   origin), `frontend` (build arg `NEXT_PUBLIC_API_URL` = the backend's public URL).
>   All real values come from an `.env` file that compose reads — commit a
>   `.env.example` with placeholder keys ONLY, never real secrets.
> - A "Deploy" section in the README documenting `docker compose up --build` and the
>   env vars.
> Run `npx next typegen && npx tsc --noEmit` and `python -m pytest` still pass. Open a PR.
**Acceptance:** `docker compose up --build` brings up all three locally; the feed
loads and the notification bell shows "Live"; `.env.example` has placeholders only,
no real secret is committed; CI green.

### [!] 6.5b Provision & go live (STOP and ask — human decision + credentials)
**Blocked on a human.** Pick ONE host and provide its credentials; Antigravity must
not guess or create paid accounts. Options, simplest first:
- **Single VPS + Docker Compose** (cheapest, most control) — a small cloud VM; point
  a domain at it, run the compose file, put Caddy/Traefik in front for HTTPS.
- **Managed PaaS** (e.g. Render / Railway / Fly.io) — managed Postgres + two services
  from the Dockerfiles; least ops.
- **Split**: frontend on Vercel, backend + Postgres on a PaaS.
**When the human has chosen and supplied access**, the prompt is:
> For the chosen host, add the deploy config (e.g. a `render.yaml` / `fly.toml`, or
> the VPS reverse-proxy + systemd/compose setup), wire the production env vars
> (`MI_DATABASE_URL`, `MI_CORS_ORIGINS`, `NEXT_PUBLIC_API_URL`) as host secrets —
> never in git — run the DB once so tables are created, and document the exact deploy
> steps in the README. Confirm the public URL serves the feed and a live bell.
**Acceptance:** a public URL serves the feed and the live SSE bell; all secrets live
in the host, not the repo. **Decision D (hosting) must be recorded in section 10.**

---

## 7. Phase 2 — Structure & AI inference (the differentiator)

### [x] 7.1 Model-provider interface (swappable)  — done 2026-11-15
**Done:**
- Created `app/ai/provider.py` defining abstract `LLMProvider` interface with `complete(system: str, user: str) -> str`.
- Implemented `OpenAICompatibleProvider(LLMProvider)`: calls `{base_url}/chat/completions` using `httpx`, strictly checks for `api_key` (raises clear `ValueError` if missing or whitespace), passes `model` and `temperature=0.0`, handles HTTP errors and response payload extraction.
- Implemented `FakeProvider(LLMProvider)`: returns canned JSON and tracks calls `(system, user)` for offline deterministic testing without hitting real models or incurring cost.
- Implemented `get_llm_provider(settings_obj)` factory: picks `FakeProvider` when configured with `"fake"` (the default in `Settings`), or `OpenAICompatibleProvider` when `"real"` / `"openai"` is configured.
- Added settings `llm_provider`, `llm_base_url`, `llm_model`, `llm_api_key`, and `llm_timeout_seconds` with `MI_LLM_*` env prefix in `app/config.py`.
- **Verified:** 9 unit tests in `tests/test_ai_provider.py` covering factory, FakeProvider, OpenAICompatibleProvider completion, missing key validation, error handling, and malformed responses. All 25 backend pytest tests pass offline; frontend lint and typegen/tsc pass clean.
**Original prompt:**
> Create `app/ai/provider.py` defining a small interface `LLMProvider` with one
> method `complete(system: str, user: str) -> str`. Implement two classes: a real
> one calling a hosted OpenAI-compatible endpoint (base URL, model name, and API
> key all from `app/config.py` env vars `MI_LLM_*`), and a `FakeProvider` returning
> canned JSON for tests. A factory picks the provider from settings. No API key in
> code; if the key is missing, the real provider raises a clear error. Unit-test the
> factory and the fake. Use `httpx`. Run tests.
**Acceptance:** factory returns the fake when configured; real provider reads config;
no secret committed; tests pass.

### [x] 7.2 Article tagging (sector / event type / entities)  — done 2026-11-16
**Done:** `ArticleTag` model (one row per article, unique FK + CASCADE) +
Alembic migration `57012fa04baa`. `app/ai/tagger.py` builds a strict JSON prompt,
validates with a Pydantic `TagResult` (unknown `event_type` → `other`, lists
sanitized), strips markdown fences, and `tag_article()` never crashes ingestion
(degrades to `other` on any error). `store_entries` tags each new article via the
configured `LLMProvider` (defaults to offline `FakeProvider`). `/api/articles`
gained `?event_type=` and `?sector=` filters; `ArticleOut` exposes `event_type` +
`sectors` (joinedload, no N+1). **Verified:** ruff + mypy clean; 37 pytest pass
(11 new); real 753-row `app.db` migrated to head with no data loss. Committed to
`main` (build-direct per user; no PR this time).
**Original prompt:**
> Add a tagging step that, for a new article, calls the `LLMProvider` with a strict
> prompt asking ONLY for JSON: `{sector: string[], event_type: one of
> [policy, govt_capex, commodity, flows, earnings, corporate_action, macro, other],
> companies: string[]}`. Store it in a new `article_tags` table (one row per
> article). Validate the JSON against a Pydantic model; on invalid output, store
> `event_type=other` and log it — never crash ingestion. Add a `?event_type=` and
> `?sector=` filter to `/api/articles`. Unit-test parsing with the `FakeProvider`.
> Do NOT call a real model in tests. Run tests + lint.
**Acceptance:** a fake-tagged article is filterable by sector and event type;
malformed model output degrades gracefully; tests pass.

### [x] 7.3 Impact records (first / second-order) — done 2026-11-16
**Prompt:**
> Add an impact-inference step: for an article tagged as policy/govt_capex/
> commodity/flows, call the model for JSON only:
> `{first_order: [{sector, direction: up|down|mixed, why}], second_order:
> [{sector, direction, why}], horizon: immediate|1-4q|multi-year, confidence:
> 0..1, evidence: string}`. Store in an `impacts` table linked to the article.
> Validate strictly; drop and log invalid output. Expose `GET /api/impacts?
> article_id=`. The `why`/`evidence` must reference the article; confidence is
> required. Unit-test with `FakeProvider`. Run tests + lint.
**Acceptance:** an impact record is produced and retrievable for a fixture article;
records without confidence or sources are rejected; tests pass.

### [ ] 7.4 Impact UI on each article
**Prompt:**
> On the feed, under an article that has an impact record, show a compact,
> collapsible "Impact" block: first-order sectors (with up/down arrows),
> second-order sectors, horizon, and a confidence bar. Always show the "as of"
> date and a note that this is model-generated, with the source link. Client
> component; must render nothing (not error) when there is no impact. Light/dark,
> phone width. Run lint + tsc.
**Acceptance:** an article with an impact shows the block; one without shows the
plain article; the block is clearly labelled model-generated with a source.

---

## 8. Phase 3 — Calendars & panels

### [ ] 8.1 Economic calendar
**Prompt:**
> Add an economic calendar of fixed-date official events (RBI policy, CPI/WPI,
> GDP, IIP). Create a seed JSON `backend/economic_calendar.json` (a human curates
> dates; do not scrape). Model + table `economic_events` (title, category, date,
> source_url). `GET /api/economic-events?from=&to=`. A `/calendar` page lists
> upcoming events grouped by date. Mark clearly that dates can change; link the
> official source. Tests for the API. Run tests + lint.
**Acceptance:** upcoming events render grouped by date from the seed file; each
links to an official source.

### [ ] 8.2 FII/DII flows panel
**Decision first (STOP and ask):** source for daily FII/DII figures (NSE publishes
them but blocks bots). Options: a permitted download, a licensed feed, or manual
seed. Once decided, build table + `/api/flows` + a small panel. **Acceptance:**
panel shows recent net FII/DII buy/sell with the source and date; no bot-spoofing.

### [ ] 8.3 Commodity prices panel
**Decision first (STOP and ask):** choose a permitted price source/API. Then table
+ `/api/commodities` + panel (crude, gold, key inputs). **Acceptance:** recent
prices with source and timestamp.

### [ ] 8.4 Seasonality reference calendar
**Prompt:**
> Add a static, curated seasonality reference: which sectors tend to be active in
> which months (e.g. jewellery around Diwali, ACs in summer), from a seed JSON.
> Show it as a month grid. Label it clearly as a historical tendency, NOT a
> forecast or a recommendation. Pure UI + seed; no model call. Run lint + tsc.
**Acceptance:** month grid renders from seed; disclaimer visible.

---

## 9. Phase 4 — Personalisation

### [ ] 9.1 User accounts
**Decision first (STOP and ask):** auth approach (a managed auth provider is
simplest and avoids us handling passwords). **Acceptance:** sign in/out; no
passwords stored by us.

### [ ] 9.2 Watchlists
**Prompt:** (after accounts) per-user saved sectors/companies; table keyed to user;
CRUD API; a watchlist page. Tests for the API. **Acceptance:** a user's watchlist
persists and is private to them.

### [ ] 9.3 Alerts → the bell
**Prompt:** when a new article/impact matches a user's watchlist, surface it as a
notification for that user via the existing SSE bell (filter the stream by the
user's watchlist). **Acceptance:** a watched-sector article pushes a live bell
notification; unrelated ones do not.

---

## 10. Data-source decisions log

| # | Decision | Status |
|---|---|---|
| A | Dividend / corporate-actions data | ✅ **Skip for now** (2026-11-14) — no clean source; revisit with a licensed feed. |
| B | Replacement for blocked govt (PIB) source | [ ] open |
| C | AI model provider + endpoint | [ ] open (needed for Phase 2) |
| D | Hosting | [ ] open (needed for 6.5) |
| E | FII/DII source | [ ] open (needed for 8.2) |
| F | Commodity price source | [ ] open (needed for 8.3) |
| G | Auth provider | [ ] open (needed for 9.1) |
| H | Open-source LICENSE | ✅ **Apache-2.0** (decided 2026-11-15); `LICENSE` file added to repo root. |
| I | PR-based flow on `main` | ✅ **Decided 2026-11-15** — every task is a PR; `main` gets branch protection (H12). 7.1 slipped in via direct push; don't repeat. |
| J | Weekly-digest delivery (on-site vs email) | [ ] open (needed for 14.5; default on-site page) |
| K | Analytics tool (privacy-friendly vs none) | [ ] open (needed for 15.4; default none) |

---

## 11. Risks

- **Data access** — the most useful data (corporate actions, govt, flows) sits
  behind bot-hostile sites. Budget for a licensed feed or keep those features
  manual-seed until then.
- **Hallucinated inferences** — mitigated by always attaching sources + confidence
  and validating model JSON strictly.
- **Regulatory** — stay informational; never public buy/sell calls.
- **Low-tier model quality** — keep every AI prompt strict ("JSON only"), validate
  output, and degrade gracefully. The provider is swappable, so a better model is
  a one-line config change.
- **Multi-worker scheduler** — `APScheduler` runs in-process. Under
  `uvicorn --workers N` (as the deferred Dockerfile specifies) every worker starts
  its own scheduler, so ingestion runs N times and races. Must be fixed before
  deploy — see **H10**.
- **Schema drift without migrations** — new tables land each feature task; the
  current hand-written `ALTER TABLE` in `init_db` does not scale and risks dev/prod
  drift. Adopt Alembic early — see **H3**.
- **Recommendation creep** — the Phase 5 aggregation, graph and explorer make the
  product feel predictive; it must stay strictly descriptive ("this news suggests X
  for sector Y"), always with sources + confidence + disclaimers, and never a
  buy/sell call (SEBI). Enforce the disclaimer in every Phase 5/6 view.

---

## 12. Engineering hardening (cross-cutting, industry practice)

These make the repo genuinely end-to-end, not just feature-complete. Each is a
normal task (branch → PR → green CI). **Priority tiers:** do **P1** interleaved
with features (several are prerequisites — see the banner), then P2, then P3.
Tick the box here when done.

### P1 — correctness, architecture & security baseline

#### [x] H1 Python lint + format (Ruff)  — done 2026-11-15
**Done:**
- Added `backend/pyproject.toml` targeting Python 3.14, line length 100, lint rules `["E", "F", "I", "UP", "B"]`.
- Added `backend/requirements-dev.txt` with `ruff>=0.17.0`, `mypy>=2.4.0`, `pytest-cov>=7.0.0`.
- Formatted and linted backend files (`ruff format`, `ruff check --fix`); fixed long lines and added `strict=True` to `zip()`.
- Updated `.github/workflows/ci.yml` backend job to install `requirements-dev.txt` and run `ruff check .` and `ruff format --check .`.
- **Verified:** `ruff check .` and `ruff format --check .` clean (0 warnings, 0 errors); 25 pytest tests pass; frontend lint/typegen/tsc clean.
**Original prompt:**
> Add Ruff as the backend linter+formatter. Put config in `backend/pyproject.toml`
> (target py3.14, line length 100, rules E,F,I,UP,B). Add a dev-deps file
> (`backend/requirements-dev.txt`) with `ruff`, `mypy`, `pytest-cov`. Add CI steps
> `ruff check .` and `ruff format --check .` in the backend job. Fix all existing
> violations.
**Acceptance:** `ruff check` and `ruff format --check` pass in CI; no behaviour change.

#### [x] H2 Python static typing (mypy)  — done 2026-11-15
**Done:**
- Added mypy configuration to `backend/pyproject.toml` (`disallow_untyped_defs = true`, `warn_unused_ignores = true`, `no_implicit_optional = true`, `check_untyped_defs = true`, `warn_redundant_casts = true`).
- Added third-party untyped library overrides for `feedparser` and `apscheduler.*`.
- Added missing type annotations in `backend/app/ingest.py` (`parse_published`) and `backend/app/main.py` (`lifespan`, `event_generator`).
- Added `mypy app` step to `.github/workflows/ci.yml`.
- **Verified:** `mypy app` clean (0 errors in 9 source files); 25 pytest tests pass; ruff format and lint pass.
**Original prompt:**
> Add mypy for `backend/app` (reasonably strict: `disallow_untyped_defs`,
> `warn_unused_ignores`, `no_implicit_optional`). Config in `pyproject.toml`. Add a
> CI step `mypy app`. Fix real type errors; justify any `# type: ignore`.
**Acceptance:** `mypy app` is clean in CI.

#### [x] H3 Database migrations (Alembic)  — done 2026-11-15
**Done:**
- Initialized Alembic under `backend/alembic/` with `alembic.ini`.
- Configured `alembic/env.py` to target `Base.metadata`, read `settings.database_url`, and enable `render_as_batch=True` on SQLite.
- Autogenerated baseline migration `65b6f5261d25_initial_schema_sources_articles.py` covering `sources` and `articles` (with `cluster_id` and all indexes).
- Replaced hand-written DDL / `create_all` in `app/db.py` and `app/main.py` with `run_migrations()` running `upgrade head` on startup (with graceful auto-stamping if baseline tables exist).
- Documented `alembic upgrade head` and `alembic revision --autogenerate` in `README.md`.
- Added CI step `alembic upgrade head` on temp DB before `pytest` in `.github/workflows/ci.yml`.
- Added unit test in `tests/test_db.py` verifying a fresh DB is built completely by migrations.
- **Verified:** All 26 pytests pass; `alembic upgrade head` runs cleanly; `ruff` and `mypy` clean.
**Original prompt:**
> Replace the hand-written `ALTER TABLE` in `app/db.py` with Alembic. Init
> `backend/alembic/`, wire `env.py` to read `settings.database_url` and target
> `Base.metadata`, autogenerate the initial migration (sources, articles incl.
> `cluster_id`), and make startup run `alembic upgrade head` (or document it as a
> deploy step) instead of `create_all`+DDL. Tests/CI run `alembic upgrade head`
> against a temp SQLite DB before `pytest`. Document `alembic revision --autogenerate`
> and `upgrade head` in the README.
**Acceptance:** a fresh DB is built entirely by migrations; no manual DDL remains in
app code; CI migrates then tests; every later schema change ships as a migration.

#### [x] H4 Pinned, reproducible dependencies  — done 2026-11-15
**Done:**
- Created `backend/requirements.in` keeping abstract dependency specifications.
- Created `backend/requirements-dev.in` for dev/CI tools (`ruff`, `mypy`, `pytest-cov`, `pip-tools`).
- Compiled fully-pinned, reproducible `backend/requirements.txt` and `backend/requirements-dev.txt` using `pip-tools`.
- Confirmed GitHub Actions CI installs from the pinned lockfiles, and frontend uses `npm ci` with `package-lock.json`.
- **Verified:** All 25 pytests pass, `ruff` checks pass, `mypy` checks pass.
**Original prompt:**
> Pin backend deps: keep intent in `backend/requirements.in`, compile a fully
> pinned `backend/requirements.txt` (uv or pip-tools). CI installs from the pinned
> file. (Frontend already has `package-lock.json`; ensure CI uses `npm ci`.)
**Acceptance:** installs are reproducible from the lockfiles; CI uses them.

#### [ ] H10 Scheduler safe under multiple workers  ← fixes a real bug
> Ensure ingestion runs exactly once regardless of web-worker count. Move the
> scheduler out of the request workers: add a dedicated entrypoint
> (`python -m app.worker`) that runs APScheduler, and have the web app start its
> in-process scheduler ONLY when `settings.run_scheduler` is true AND a single
> worker is used. In the (deferred) compose/deploy, run the worker as its own
> service. Document the two run modes.
**Acceptance:** with >1 web worker, ingestion does not duplicate; a single scheduler
owns the interval; documented.

#### [ ] H6 API rate limiting
> Add per-IP rate limiting (e.g. `slowapi`) to the public REST endpoints, limits in
> settings (default ~60/min), returning 429 + `Retry-After`. Give SSE its own
> sensible policy (or exempt it). Unit-test the limiter.
**Acceptance:** exceeding the limit returns 429; limits are configurable; tested.

#### [ ] H7 Security headers + strict CORS
> Add a backend middleware setting `X-Content-Type-Options: nosniff`,
> `Referrer-Policy`, `X-Frame-Options: DENY`, and a minimal `Permissions-Policy`.
> Add security headers in `frontend/next.config.ts`. Confirm CORS origins come only
> from `settings.cors_origins` (no `*`).
**Acceptance:** headers present on responses; CORS limited to configured origins; test.

#### [ ] H12 Branch protection + PR flow  ← fixes the 7.1 process issue
> **DEFERRED by the user (2026-11-15): leave branch protection off for now.** The PR
> flow is already being followed voluntarily (H1–H4 all went through PRs #1–#4), so
> this is low-urgency. Revisit before/at deploy. When enabling:
> **Context:** Task 7.1 was pushed straight to `main`; the work order requires a PR
> per task. Protect `main` on GitHub: require a PR, require the CI check to pass,
> block direct pushes and force-pushes (require 1 review if feasible). Delete the
> stale `task-7.1-model-provider` branch (already gone locally) and the merged
> `task-h1..h4` branches. **Admin rights needed — if the agent cannot set this via
> `gh api`, STOP and ask the human to toggle it in GitHub settings.**
**Acceptance:** direct pushes to `main` are rejected; CI is a required check; stale
branches removed.

### P2 — quality, tests & observability

#### [ ] H5 Coverage + endpoint tests
> Add `pytest-cov`; CI prints coverage and fails under a threshold (start 70%,
> raise over time). Add API tests for `/api/articles` (category/source/q/paging/
> group), `/api/sources`, `/api/notifications`, and health endpoints.
**Acceptance:** coverage enforced in CI; the listed endpoints have tests.

#### [ ] H8 Structured logging + request logging
> Replace `logging.basicConfig` with structured (JSON) logging, level from env. Add
> middleware logging each request once (method, path, status, duration_ms) with a
> generated request id echoed in an `X-Request-ID` response header.
**Acceptance:** logs are structured; each request logged once with an id.

#### [ ] H9 Liveness & readiness endpoints
> Add `/api/health/live` (process up) and `/api/health/ready` (cheap DB check,
> returns 503 when the DB is unreachable); keep `/api/health`.
**Acceptance:** readiness returns 503 when the DB is down; both documented.

#### [ ] H11 Dependabot + secret scanning
> Add `.github/dependabot.yml` (pip, npm, github-actions; weekly). Add a `gitleaks`
> CI job on PRs. Verify it fails on a planted dummy secret, then remove the dummy.
**Acceptance:** dependabot config valid; gitleaks runs in CI and catches a secret.

#### [ ] H14 Frontend format + component tests
> Add Prettier (+ `prettier --check` in CI). Add Vitest + React Testing Library with
> a few tests (NotificationBell render/badge, a feed item, grouped "+N more" badge).
**Acceptance:** `prettier --check` passes in CI; component tests run in CI.

### P3 — polish & ops niceties

#### [ ] H13 Repo hygiene
> `LICENSE` is already added (**Apache-2.0**, decision H). Add the rest:
> `CONTRIBUTING.md` (run/test/PR steps), `.editorconfig`, a PR template + issue
> templates under `.github/`, and `.pre-commit-config.yaml` (ruff for backend,
> eslint+prettier for frontend). Add a short `NOTICE` file (project name + year) to
> accompany the Apache licence.
**Acceptance:** files present; `pre-commit run --all-files` works locally.

#### [ ] H15 Error tracking (Sentry), opt-in
> Integrate Sentry in backend and frontend, enabled only when `MI_SENTRY_DSN` /
> `NEXT_PUBLIC_SENTRY_DSN` is set; a no-op (and zero overhead) otherwise. No DSN in git.
**Acceptance:** no DSN → nothing sent; with a DSN → an error is captured; no secret committed.

#### [ ] H16 Caching / conditional requests on read APIs
> Add short-TTL `Cache-Control` and `ETag` to `/api/articles` and `/api/sources`
> (SSE stays uncached); return `304` on a matching `If-None-Match`.
**Acceptance:** read responses carry `Cache-Control`/`ETag`; a matching ETag yields 304.

---

## 13. Review log

Verifications done by the reviewing agent (this is a record, not a to-do):

- **2026-11-15 — Task 7.1 (model-provider interface): PASS.** Read all code; 25
  backend tests pass; CI green on `main`. Config defaults are safe (`llm_provider=fake`,
  no key). **Finding:** committed directly to `main` instead of via a PR → tracked as
  **H12** (branch protection). Provider is correct but not yet consumed (expected; 7.2
  wires it in).

- **2026-11-15 — Tasks H1–H4 (Ruff, mypy, Alembic, pinned deps): PASS.** All four
  landed via proper PRs (#1–#4), each with CI green — the 7.1 direct-push issue is
  fixed. Verified locally: `ruff check` + `ruff format --check` clean (15 files);
  `mypy app` clean (9 files); `alembic upgrade head` builds a fresh DB
  (`sources`, `articles`, `alembic_version`); **26** pytest pass. **Migration
  adoption confirmed on real data:** running `run_migrations()` against the existing
  753-row `app.db` stamped it at baseline `65b6f5261d25` and preserved all 753 rows
  and `cluster_id` — no data loss. The manual `ALTER TABLE` is gone; `main.py` calls
  `run_migrations()` on startup. Frontend lint/typegen/tsc still green. No bugs.
  **Open:** H12 branch protection not yet enabled (see note on H12); the
  Starlette/httpx test deprecation warning persists (tracked as **17.2**).

- **2026-11-16 — Task 7.2 (article tagging): COMPLETED by the reviewer.** Antigravity
  had left 7.2 ~40% done and uncommitted (tagger + ArticleTag model only), failing
  ruff and missing the migration, ingestion wiring, API filters and tests. The
  reviewer finished it: fixed ruff E501, added migration `57012fa04baa`, wired
  tagging into `store_entries`, added `?event_type`/`?sector` filters + tag fields in
  `ArticleOut`, and wrote 11 tests. Verified ruff + mypy clean, 37 pytest pass, real
  753-row DB migrates with no data loss. Committed straight to `main` per the user
  ("everything in main; we're only building it").

- **2026-11-16 — Task 7.3 (impact records): COMPLETED.** Built `impact.py` with strict Pydantic
  schema (`ImpactResult`, `SectorImpact`), validation rejecting invalid confidence, missing sources,
  or non-standard directions/horizons, and markdown-fence stripping. Added `ArticleImpact` model
  and Alembic migration `276a9725bc9b` creating `impacts` table. Wired into `store_entries`: policy,
  govt_capex, commodity, and flows articles trigger impact inference; invalid model outputs are
  dropped/logged without crashing ingestion. Added `GET /api/impacts?article_id=` endpoint (404 on
  missing) and `has_impact` on `ArticleOut` (with joinedload). Added 14 new tests (51 total passed).
  Ruff and mypy clean; frontend lint, next typegen, and tsc pass; real 753-row DB migrated cleanly.

---

## 14. Phase 5 — Cross-impact intelligence (the core thesis)

This is the product's reason to exist: *"distant, related events have deep impact on
each other."* Phase 2 produces a per-article impact record; Phase 5 connects those
records across articles into sector-level signals and a relationship graph. **Build
after Phase 2 (needs 7.2 tags + 7.3 impacts); can interleave with Phase 3.**
Everything here is **descriptive and informational** — it reports observed/model-
inferred links from the news, with sources + confidence, and **never** a buy/sell
call. All numbers carry their supporting article links and an "as of" window; no
invented data.

### [ ] 14.1 Canonical sector/entity taxonomy
> Create a curated taxonomy so tags and impacts stay consistent: a seed
> `backend/taxonomy.json` of sectors (+ optional sub-sectors) and an alias→canonical
> map. Add a pure `normalize_sector(name) -> str | None` used by tagging (7.2) and
> impacts (7.3) so "IT"/"Information Technology"/"Tech" collapse to one sector.
> Unit-test the map. No model call.
**Acceptance:** alias variants resolve to one canonical sector; tagging/impacts use it.

### [ ] 14.2 Impact aggregation API
> Add `GET /api/impact-summary?from=&to=&sector=` that aggregates stored impact
> records (7.3) into cross-sector signals: per sector, counts of first/second-order
> up/down/mixed, the dominant horizon, average confidence, and up to N supporting
> article links. Pure SQL/Python over existing rows — **no model calls**. Every value
> carries its source articles and the "as of" window. Tests with fixtures.
**Acceptance:** returns sector signals with counts, confidence and source links; adds
no inference beyond what is stored; tested.

### [ ] 14.3 Sector relationship graph
> Derive the cross-impact graph from stored impacts: directed edges
> first-order sector → second-order sector, weighted by frequency and confidence.
> Expose `GET /api/impact-graph?from=&to=` returning nodes (sectors) and edges (with
> supporting article links + confidence). It DESCRIBES links observed in the news; it
> is not advice. Pure aggregation; tested with fixtures.
**Acceptance:** returns nodes + edges each backed by source articles and confidence;
no buy/sell framing.

### [ ] 14.4 Impact explorer UI
> A `/impact` page: choose a sector and see what is affecting it now — first- and
> second-order drivers with direction arrows, horizon, confidence bars and source
> links, plus a simple visual of the relationship graph (14.3). Clearly labelled
> "model-generated, informational only, not investment advice" with "as of" dates.
> Renders gracefully with no data. Light/dark, phone width.
**Acceptance:** the page shows a sector's drivers + the graph from the APIs;
disclaimers visible; empty state handled.

### [ ] 14.5 Weekly digest  (Decision J — delivery channel)
> **Decision first (STOP and ask): on-site page only, or email too?** Build a `/digest`
> page first (no email needed): the week's top cross-sector signals from 14.2 with
> source links and disclaimers. If email is later chosen, send via a provider behind
> config — no addresses or keys in git.
**Acceptance:** `/digest` summarizes the week's top signals with sources; email is
deferred behind decision J.

---

## 15. Phase 6 — Public-product readiness

Polish needed before a public launch. **Do before deploy (section 6.5).**

### [ ] 15.1 Methodology & disclaimer page
> Add an `/about` (methodology) page: what Market Intel is, the data sources, how AI
> impact inference works, what confidence means, update cadence, and a clear
> disclaimer — informational only, not investment advice, no buy/sell calls (SEBI).
> Link it in the header/footer.
**Acceptance:** page explains sources + method + disclaimer and is linked site-wide.

### [ ] 15.2 SEO & social metadata
> Per-page metadata (unique title/description), Open Graph + Twitter cards, plus
> `sitemap.xml` and `robots.txt` via Next metadata routes, and a site name/favicon.
> No PII in URLs.
**Acceptance:** pages have unique titles/descriptions + OG tags; sitemap and robots served.

### [ ] 15.3 Accessibility pass
> Audit a11y: semantic landmarks, visible focus states, keyboard nav for the bell and
> menus, light/dark contrast, aria labels, reduced-motion. Fix issues and add
> `eslint-plugin-jsx-a11y` to the frontend lint in CI.
**Acceptance:** no critical a11y issues; a11y lint runs in CI.

### [ ] 15.4 Privacy-friendly analytics  (Decision K — tool)
> **Decision first (STOP and ask): which tool (self-hosted Plausible/Umami) or none.**
> If chosen, add behind config — no cookies/PII, site-id/DSN from env not git, default
> off.
**Acceptance:** analytics active only when configured; no PII; nothing committed.

### [ ] 15.5 Resilient UI states & performance
> Polish empty/loading/error states across pages; add a global error boundary; confirm
> the feed paginates well at scale; add DB indexes for the new filterable columns
> (`event_type`, `sector`, `cluster_id`) and confirm the grouped query stays fast
> (no N+1).
**Acceptance:** every page has graceful states; indexes exist for filterable columns;
no obvious N+1.

---

## 16. Data operations backlog

### [ ] 16.1 Backfill clustering for existing articles
> One-off idempotent `python -m app.backfill_clusters` that assigns `cluster_id` to
> the pre-existing NULL-cluster rows using the ingestion logic, in time order, so
> historical duplicates group too. Include a `--dry-run`. Test on a fixture.
**Acceptance:** historical duplicate headlines share a cluster afterwards; re-running
is a no-op.

### [ ] 16.2 Seed-data curation workflow
> The calendar, FII/DII, commodity, seasonality and taxonomy data are human-curated
> JSON seeds. Add a JSON schema per seed, a `python -m app.validate_seeds` check wired
> into CI, and README notes on how to edit them.
**Acceptance:** a malformed seed fails CI; the edit process is documented.

### [ ] 16.3 Replacement for blocked govt source  (Decision B)
> Find a permitted, machine-readable govt/policy source to replace PIB (blocks bots).
> **Do not spoof user agents.** If nothing free exists, STOP and ask about a licensed
> feed or a manual seed.
**Acceptance:** a permitted source is ingested, or the decision is escalated with options.

### [ ] 16.4 Clustering quality improvements
> From review feedback: guard against over-clustering very short headlines — the
> `max(dice, containment)` score can hit 1.0 when one headline's tokens are a subset
> of another's. Require a minimum informative-token count and/or `dice >= t` in
> addition to containment. Fix the stale "Jaccard" comment in `cluster.py`. Add
> regression tests for the short-headline case.
**Acceptance:** a short generic headline no longer absorbs a longer unrelated story;
tests cover it.

---

## 17. Review-fix backlog (small, from code review)

### [ ] 17.1 README config accuracy
> The frontend reads `NEXT_PUBLIC_API_URL` (`frontend/app/lib.ts`), but the README
> "Configuration" section says `API_URL`. Correct the README.
**Acceptance:** README names the actual env var.

### [ ] 17.2 Clean up the test deprecation warning
> `pytest` prints a Starlette/httpx `TestClient` deprecation warning. Resolve it
> (pin/adjust the test client or dependency) so CI output stays clean; keep tests green.
**Acceptance:** suite passes with no deprecation warning.

### [ ] 17.3 Fix cluster.py docstring metric name
> `cluster.py` calls its metric "Jaccard" but implements Dice + containment. Correct
> the comment (also covered by 16.4; do whichever lands first).
**Acceptance:** comment matches the implementation.
