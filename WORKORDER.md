# Market Intel — Work Order & Build Tracker

Last updated: 2026-11-15

A living, trackable plan for building Market Intel end to end with good
engineering practice. It is written to be executed by an **AI coding agent**:
every task carries a self-contained, copy-paste **prompt** so the agent has all
the context it needs, plus **acceptance criteria** so you can tell when it is done.

> **Current status (2026-11-15).** Repo lives at `C:\Users\arnav\dev\market-intel`
> (it is NOT a git repo yet — `git init` before the CI task 6.4). Done so far:
> Phase 1 (feed + SSE notification bell), **6.1** (moved out of OneDrive), **6.2**
> (Postgres support), **6.3** (story de-duplication). **Next task → 6.4 (CI: tests + lint on push).**
> Work top to bottom from there; the Progress tracker (section 4) is the source of truth.

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
> - Backend code lives in `market-intel/backend/app/`, tests in
>   `market-intel/backend/tests/`. Frontend in `market-intel/frontend/app/`.
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
> - After changes, run: backend `python -m pytest` + `npm run lint` +
>   `npx tsc --noEmit` in the frontend. Report what you ran and the result.
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
| 1.5 | Deploy (backend + frontend + db) | [ ] |
| 2 | Model-provider interface (swappable) | [ ] |
| 2 | Article tagging (sector / event type) | [ ] |
| 2 | Impact records (first/second-order) | [ ] |
| 2 | Impact UI on each article | [ ] |
| 3 | Economic calendar | [ ] |
| 3 | FII/DII flows panel | [ ] |
| 3 | Commodity prices panel | [ ] |
| 3 | Seasonality reference calendar | [ ] |
| 4 | User accounts | [ ] |
| 4 | Watchlists | [ ] |
| 4 | Alerts (push to the bell) | [ ] |

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
→ `npm run lint` → `npx tsc --noEmit`). Paths were adapted to the repo-root
layout (`backend/`, `frontend/`) since the project is now the repo root, not
`market-intel/`. `.gitignore` extended to exclude `*.db` and `.claude/`; no DB,
venv, node_modules, or secrets are tracked.
**Original prompt:**
> Add a GitHub Actions workflow `.github/workflows/market-intel-ci.yml` that, on
> push/PR touching `market-intel/**`, sets up Python 3.14 + Node 24, installs
> backend deps and runs `pytest`, installs frontend deps and runs `npm run lint`
> and `npx tsc --noEmit`. Cache pip and npm. No deploy step. Keep it under ~50 lines.
**Acceptance:** workflow is valid YAML; jobs run the three checks; fails if any fails.

### [ ] 6.5 Deploy
**Decision first (STOP and ask):** where does it run? (A single VPS with Docker
Compose is the simplest for a Python+Next+Postgres trio.) Once decided:
**Prompt:**
> For the chosen host, write a `docker-compose.yml` (postgres + backend + frontend)
> and a Dockerfile for each service, production-mode (`next build && next start`,
> `uvicorn` with `--workers`). Put real config in env vars, not the compose file.
> Document the deploy in the README. Do not include secrets.
**Acceptance:** `docker compose up` runs all three locally; the public URL serves
the feed and the live bell.

---

## 7. Phase 2 — Structure & AI inference (the differentiator)

### [ ] 7.1 Model-provider interface (swappable)
**Prompt:**
> Create `app/ai/provider.py` defining a small interface `LLMProvider` with one
> method `complete(system: str, user: str) -> str`. Implement two classes: a real
> one calling a hosted OpenAI-compatible endpoint (base URL, model name, and API
> key all from `app/config.py` env vars `MI_LLM_*`), and a `FakeProvider` returning
> canned JSON for tests. A factory picks the provider from settings. No API key in
> code; if the key is missing, the real provider raises a clear error. Unit-test the
> factory and the fake. Use `httpx`. Run tests.
**Acceptance:** factory returns the fake when configured; real provider reads config;
no secret committed; tests pass.

### [ ] 7.2 Article tagging (sector / event type / entities)
**Prompt:**
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

### [ ] 7.3 Impact records (first / second-order)
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
