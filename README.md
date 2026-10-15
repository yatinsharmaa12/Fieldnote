# Fieldnote

Turn any public company website into a searchable, conversational knowledge base.

Give Fieldnote a website URL → it crawls the site, indexes clean page content as vector embeddings, and answers questions grounded in the pages it indexed — with source URLs for every answer.

![Python](https://img.shields.io/badge/python-3.12+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688)
![React](https://img.shields.io/badge/React-18-61dafb)
![PostgreSQL + pgvector](https://img.shields.io/badge/PostgreSQL-pgvector-336791)
![Redis + RQ](https://img.shields.io/badge/Redis-RQ-DC382D)
![Gemini](https://img.shields.io/badge/Gemini-API-4285F4)

## Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Repository structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Quickstart](#quickstart)
  - [1. Backend API](#1-backend-api)
  - [2. Crawl worker](#2-crawl-worker)
  - [3. Frontend app](#3-frontend-app)
  - [4. Chrome extension (optional)](#4-chrome-extension-optional)
  - [5. First use](#5-first-use)
- [API reference](#api-reference)
- [Crawl observability](#crawl-observability)
- [RAG / chat flow](#rag--chat-flow)
- [Security boundaries](#security-boundaries)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Project status and limitations](#project-status-and-limitations)

## Features

**Auth & multi-tenancy**

- JWT bearer auth (register, JSON login, OAuth2 form-compatible token endpoint).
- Companies and crawl jobs strictly isolated by owner (`user → company → job → pages`).

**Crawler**

- Same-site crawling with `max_pages` / `max_depth` controls.
- SSRF protection, `robots.txt` enforcement, response-size caps, connect/read/write timeouts, max crawl duration, and per-domain rate limiting.
- Incremental re-crawls: unchanged pages skip ingestion, changed pages replace chunks transactionally, unseen URLs are deactivated (no duplicates).

**Background jobs**

- Redis + RQ queue (`crawl` queue) with retries, cancellation, heartbeats, attempt counting, and stale-job recovery.
- Per-execution counters, `started_at` / `completed_at`, and derived `duration_seconds` on every run.

**RAG chat**

- Company-scoped pgvector search with cosine-distance filtering and nearest-first ordering.
- Grouped, duplicate-free context fed to Gemini with a website-grounded prompt.
- Ordered, URL-deduplicated `answer + sources[]` responses; model says "not enough information" instead of hallucinating.

**Product UI**

- React + TypeScript frontend: login, companies, live crawl monitoring (polling), crawl history + statistics, company chat with suggestions, stop/retry, and safe source links.
- Chrome side-panel extension (Manifest V3): detects the site in the current tab, shows crawl status, and chats against that site's index.
- Resilient UX: non-overlapping visibility-aware polling, request cancellation/dedup, backoff on transient failures, keyboard-accessible dialogs, focus indicators, reduced-motion support.

## How it works

Typical flow:

1. Sign in.
2. Add a company (`name` + public `website_url`).
3. Start a crawl (`max_pages`, `max_depth`).
4. Watch queued → running → completed/failed with live counters.
5. Browse crawl history and per-run statistics.
6. Ask questions in company chat and follow the cited sources.

```mermaid
flowchart TD
    A["React Frontend / Chrome Extension"] --> B["FastAPI REST API"]
    B --> C[("PostgreSQL + pgvector")]
    B --> D["Redis / RQ Queue"]
    D --> E["RQ Crawl Worker"]
    E --> F["Fetch and parse HTML"]
    F --> G["Clean and chunk content"]
    G --> H["Generate embeddings"]
    H --> C

    A --> I["Ask a question"]
    I --> B
    B --> J["Company-scoped vector search"]
    J --> C
    J --> K["Build grounded context"]
    K --> L["Gemini"]
    L --> M["Validate answer"]
    M --> N["Return answer and source URLs"]
```

## Tech stack

| Layer | Technology |
| --- | --- |
| API | FastAPI, SQLAlchemy, Alembic, Pydantic, PyJWT |
| Crawl & ingestion | httpx/requests, BeautifulSoup, tiktoken, sentence-transformers, torch |
| Retrieval & generation | pgvector (`vector` extension), Google Gemini (`google-genai`) |
| Jobs | Redis, RQ |
| Web app | React 18, TypeScript, Vite, React Router, lucide-react, Vitest |
| Extension | React 18, TypeScript, Vite, Chrome Manifest V3 side panel, Vitest |
| Data | PostgreSQL 14+ with `pgvector`, Redis 6+ |

## Repository structure

```text
backend/
  app/
    api/          auth, companies, company_crawl, chat routes
    crawler/      crawler, robots.txt, URL registry, fetching/parsing
    ingestion/    cleaning, chunking, embeddings
    retrieval/    company-scoped vector search
    rag/          Gemini prompt, generation, guardrails/validation
    services/     crawl enqueue/cancel/retry orchestration
    queue/        Redis/RQ connection + queue definitions
    workers/      RQ crawl worker entrypoint
    models/       User, Company, CrawlJob, Page, PageChunk
    db/           session/engine
    core/         env config (timeouts, limits, JWT, CORS)
  alembic/        migrations (incl. pgvector + query indexes)
  tests/          auth, ownership, crawl lifecycle, retries,
                  incremental ingestion, RAG, security, migrations
frontend/
  src/
    api.ts auth.tsx        HTTP client, session handling
    components/ChatPanel.tsx, Dialog.tsx
    hooks/useCrawlStatus.ts visibility-aware polling
    App.tsx               login, companies, crawl monitor, history, chat
extension/
  src/
    api/                  client, auth, chat, crawl
    hooks/                useAuth, useCrawlStatus, useCurrentTab
    App.tsx               side-panel: current-site detection + chat
  public/manifest.json    Manifest V3 (sidePanel, storage/tabs)
```

> `autotype/` and `docs/` are currently empty placeholders and contain no runtime code.

## Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- PostgreSQL with the `vector` (pgvector) extension available
- Redis (local or remote)
- A Google Gemini API key

| Service | Default |
| --- | --- |
| API | `http://localhost:8000` |
| Frontend (Vite) | `http://localhost:5173` |
| Redis | `redis://localhost:6379/0` |
| Postgres | `postgresql://USER:PASSWORD@localhost:5432/fieldnote` |

## Configuration

Create `backend/.env` (never commit it):

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/fieldnote
TEST_DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/fieldnote_test
REDIS_URL=redis://localhost:6379/0
GEMINI_API_KEY=your-gemini-api-key
JWT_SECRET_KEY=replace-with-a-long-random-secret
```

Optional tuning (defaults shown):

```dotenv
MAX_RESPONSE_SIZE_BYTES=5000000
REQUEST_CONNECT_TIMEOUT=10
REQUEST_READ_TIMEOUT=10
REQUEST_WRITE_TIMEOUT=10
REQUEST_POOL_TIMEOUT=10
MAX_CRAWL_DURATION_SECONDS=1800
DOMAIN_MIN_DELAY_SECONDS=1
ACCESS_TOKEN_EXPIRE_MINUTES=60
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` / `TEST_DATABASE_URL` | App and test databases |
| `REDIS_URL` | Shared by API and worker; must match on both sides |
| `GEMINI_API_KEY` | Answer generation (retrieval works without it; chat does not) |
| `JWT_SECRET_KEY` | Required; HS256 signing key — use a long random value outside local dev |
| `CORS_ALLOW_ORIGINS` | Comma-separated web origins; set to your production origin when deploying |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime (default 60) |
| `MAX_*` / `REQUEST_*` / `DOMAIN_*` | Crawler safety and politeness limits |

## Quickstart

You need three terminals for the full loop: API, worker, frontend. The extension is optional.

### 1. Backend API

From the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Verify:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

> `KeyError: 'JWT_SECRET_KEY'` means `backend/.env` is missing or Uvicorn wasn't started from `backend/`.

### 2. Crawl worker

In a second terminal (API must be running):

```bash
cd backend
source .venv/bin/activate
python -m app.workers.crawl_worker
```

The API enqueues jobs on the `crawl` RQ queue; the worker executes them with retry/failure callbacks. If crawls sit in `queued` forever, Redis or the worker isn't running, or `REDIS_URL` differs between API and worker.

### 3. Frontend app

In a third terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

During development Vite proxies `/api/*` → `http://localhost:8000/*`. To point at another API directly, create `frontend/.env.local`:

```dotenv
VITE_API_URL=http://localhost:8000
```

The web app keeps the JWT in session storage and sends `Authorization: Bearer <token>` on private routes.

### 4. Chrome extension (optional)

```bash
cd extension
npm install
npm run build
```

Then in Chrome: `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select `extension/dist`. Open the Fieldnote side panel on any site; the extension detects the current tab's site and chats against that company's index using the same backend API.

### 5. First use

The backend exposes registration; the frontend focuses on login + product workflow. Create a user once:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"change-me"}'
```

Then in the UI: sign in → **Add company** (`name` + public `website_url`) → open it → **Start crawl** → monitor progress → open **history** → ask questions in **chat** and follow the returned sources.

## API reference

All routes except registration, login, token, and health require `Authorization: Bearer <token>`.

### Authentication

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/auth/register` | Create user with `{email, password}` |
| `POST` | `/auth/login` | JSON login → `{access_token, token_type}` |
| `POST` | `/auth/token` | OAuth2 password-form login (docs / form clients) |
| `GET` | `/health` | Public liveness probe → `{"status":"ok"}` |

### Companies

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/companies` | Create `{name, website_url}` |
| `GET` | `/companies` | List companies owned by current user |
| `GET` | `/companies/{company_id}` | Read one owned company |
| `PUT` | `/companies/{company_id}` | Update an owned company |
| `DELETE` | `/companies/{company_id}` | Delete an owned company |

### Crawls

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/companies/{company_id}/crawl` | Queue crawl with `{max_pages, max_depth}` |
| `GET` | `/companies/{company_id}/crawl-jobs` | List crawl history (latest first) |
| `GET` | `/companies/{company_id}/crawl-jobs/{job_id}` | Read one company-scoped job + counters |
| `POST` | `/companies/{company_id}/crawl-jobs/{job_id}/cancel` | Cancel a queued/running job |

### Chat

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "company_id": 16,
  "question": "What is FastAPI?"
}
```

Success shape:

```json
{
  "answer": "...",
  "sources": [
    { "title": "FastAPI", "url": "https://fastapi.tiangolo.com/" }
  ]
}
```

Provider (Gemini) outages return a safe `502 Bad Gateway` — no fabricated answer. Retrieval failures are reported separately from provider failures.

## Crawl observability

Every job response carries per-execution counters:

| Field | Meaning |
| --- | --- |
| `pages_discovered` | Active URLs known during this crawl |
| `pages_crawled` | URLs successfully fetched + processed |
| `pages_indexed` | URLs whose content is indexed |
| `pages_failed` | URLs whose fetch/processing failed |
| `pages_new` | First-time pages ingested |
| `pages_changed` | Known pages whose hash changed and chunks were replaced |
| `pages_unchanged` | Known pages whose hash matched (ingestion skipped) |
| `pages_deactivated` | Previously active URLs not seen in this crawl |
| `attempt_count` | Execution attempts including retries |
| `duration_seconds` | `completed_at - started_at`, or live elapsed time while running |

Re-running a completed job resets per-execution counters and timestamps before the new run; existing page/chunk data is reused, not duplicated. The UI polls job status (no WebSockets) and stops polling in terminal states.

## RAG / chat flow

```text
question
  -> company-scoped vector search
  -> cosine-distance filtering, nearest-first
  -> grouped, duplicate-free source context
  -> website-specific Gemini prompt (bounded output)
  -> guardrail validation
  -> answer + ordered, URL-deduplicated sources
```

- Query embeddings are cached in-process (bounded LRU); answers and retrieved content are never cached.
- Navigation/header/footer/script/style elements are stripped before chunking.
- The model is instructed to synthesize only website-supported facts and to say when the site lacks the information.
- Provider SDK errors never leak prompts, keys, headers, or tracebacks to clients.

## Security boundaries

- JWT auth on all private routes; company/job queries scoped to the caller's ownership.
- SSRF + same-site enforcement on every fetched URL; `robots.txt` honored (deny on auth failures).
- Response-size, timeout, duration, and per-domain delay caps enforced by the crawler.
- CORS uses an explicit allowlist (no `*`); `Authorization` + `Content-Type` only, no cookie/credentials mode.
- Security headers on all responses: `nosniff`, `DENY` framing, `no-referrer`, restrictive CSP, HSTS (effective behind HTTPS).
- Secrets stay in environment variables; use a strong private `JWT_SECRET_KEY` in any shared environment.

## Testing

Backend (uses `TEST_DATABASE_URL` — never your dev database):

```bash
cd backend
source .venv/bin/activate
pytest -q
```

Frontend:

```bash
cd frontend
npm test      # Vitest
npm run build # tsc + Vite production build
```

Extension:

```bash
cd extension
npm test
npm run build
```

Coverage includes: auth, ownership isolation, crawl lifecycle, retries/cancellation/recovery, SSRF/robots/timeout guards, incremental ingestion + statistics, vector retrieval, Gemini failure mapping, and frontend/extension API + UI behavior (polling, cancellation, stale-response handling).

Check for unintended changes with `git diff --check` before committing.

## Troubleshooting

**`KeyError: 'JWT_SECRET_KEY'`**
`backend/.env` is missing `JWT_SECRET_KEY`, or Uvicorn wasn't launched from `backend/`.

**Frontend stuck on "Signing in…"**
Check the API is reachable: `curl http://localhost:8000/health`. If unreachable, the UI surfaces a connection error after its request timeout (12s normal, 45s for chat).

**Crawls stay queued**
Redis and `python -m app.workers.crawl_worker` must both be running with the same `REDIS_URL` as the API.

**Chat returns 502 / provider error**
Gemini was unavailable or timed out. Retry and inspect backend logs for provider error type/status. This is intentional — the API won't invent an answer.

**Migration / pgvector errors**
Ensure the `vector` extension is installed and run `alembic upgrade head` from `backend/` against the intended database before starting the API/workers.

**CORS errors in production**
Set `CORS_ALLOW_ORIGINS` in `backend/.env` to the exact web origin(s) (e.g. `https://app.example.com`), restart the API.

**Extension can't reach the API**
`host_permissions` defaults to `http://localhost:8000/*`. For a remote backend, update `extension/public/manifest.json`, rebuild, and reload the unpacked extension.

## Project status and limitations

Working today: backend crawl + incremental ingestion + RAG, React web workflow (login, companies, live crawl monitor, history/statistics, chat), and Chrome side-panel extension.

Deliberately out of scope for now: WebSockets / server-push (UIs poll), external observability infrastructure, and multi-user shared workspaces (data is per-owner).

Good next steps: hosted deployment guide (Postgres + Redis + worker supervision), background re-crawl schedules, sitemap-aware discovery, per-page freshness indicators, and evaluation harness for answer groundedness.
