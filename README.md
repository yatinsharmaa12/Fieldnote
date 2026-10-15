# Fieldnote

Fieldnote turns a company website into a searchable, conversational knowledge base.

Give it a public website, crawl the site, monitor the crawl as it runs, and ask questions grounded in the pages that were indexed.

![Fieldnote product workflow](docs/fieldnote-workflow.svg)

## What It Does

- Authenticates users with JWT bearer tokens.
- Keeps companies and crawl jobs isolated by owner and company.
- Crawls within the target website while enforcing SSRF, robots.txt, timeout, size, duration, and rate-limit protections.
- Processes pages into clean text, chunks, and vector embeddings.
- Re-crawls incrementally: unchanged pages skip ingestion, changed pages replace their old chunks transactionally, and unseen URLs can be deactivated.
- Runs crawls through Redis and RQ with retries, cancellation, heartbeat updates, and stale-job recovery.
- Exposes crawl statistics and duration for each execution.
- Answers company-specific questions with Gemini and returns the supporting source URLs.
 flowchart TD
    A[User registers or logs in] --> B[JWT authentication]
    B --> C[Create company with website URL]
    C --> D[Queue crawl job in Redis / RQ]
    D --> E[Fetch public HTML pages]
    E --> F[Normalize URLs and extract text]
    F --> G[Compute content hash]
    G --> H{Content changed?}
    H -->|No| I[Skip re-ingestion]
    H -->|Yes or new| J[Chunk text and create embeddings]
    J --> K[Store pages and chunks in PostgreSQL / pgvector]
    I --> L[Update crawl statistics]
    K --> L
    L --> M[User asks a question]
    M --> N[Company-scoped vector search]
    N --> O[Build source context]
    O --> P[Gemini generates answer]
    P --> Q[Validate answer and return source URLs]
## Architecture

```text
React/Vite frontend
        |
        | HTTP + JWT bearer token
        v
FastAPI API  ---- PostgreSQL + pgvector
        |
        +---- Redis/RQ ---- SimpleWorker ---- crawler + ingestion
        |
        +---- retrieval ---- Gemini answer generation
```

The repository is split into:

```text
backend/    FastAPI API, crawler, ingestion, retrieval, RAG, migrations, tests
frontend/   React + TypeScript + Vite product interface
```

## Prerequisites

- Python 3.12 or newer
- Node.js and npm
- PostgreSQL with the `vector` extension available
- Redis
- A Google Gemini API key

## Configuration

Create `backend/.env` with values for the local environment:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/fieldnote
TEST_DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/fieldnote_test
REDIS_URL=redis://localhost:6379/0
GEMINI_API_KEY=your-gemini-api-key
JWT_SECRET_KEY=replace-with-a-long-random-secret
```

Optional crawler settings:

```dotenv
MAX_RESPONSE_SIZE_BYTES=5000000
REQUEST_CONNECT_TIMEOUT=10
REQUEST_READ_TIMEOUT=10
REQUEST_WRITE_TIMEOUT=10
REQUEST_POOL_TIMEOUT=10
MAX_CRAWL_DURATION_SECONDS=1800
DOMAIN_MIN_DELAY_SECONDS=1
```

Never commit `.env`, API keys, JWT secrets, or database credentials.

## Backend Setup

From the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Apply database migrations:

```bash
alembic upgrade head
```

Start the API:

```bash
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`.

Health check:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Crawl Worker

Run the worker in a second terminal while the API is running:

```bash
cd backend
source .venv/bin/activate
python -m app.workers.crawl_worker
```

The API enqueues crawl jobs in the `crawl` RQ queue. The worker executes them and handles the existing retry and failure callbacks.

## Frontend Setup

In a third terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

During development, Vite proxies `/api/*` to `http://localhost:8000/*`. To use another API origin, set `VITE_API_URL` in `frontend/.env.local`:

```dotenv
VITE_API_URL=http://localhost:8000
```

The frontend stores the JWT in session storage for the current browser session and sends it as an `Authorization: Bearer` header.

## First Use

The backend exposes registration, while the current frontend focuses on login and the product workflow. Create a user once:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"change-me"}'
```

Then sign in through the frontend.

Typical flow:

1. Sign in.
2. Add a company and its public website URL.
3. Open the company and start a crawl.
4. Monitor the queued/running job and its statistics.
5. Open crawl history for completed or failed runs.
6. Ask questions in company chat and follow the returned sources.

## API Surface

All routes except registration, login, token, and health require a JWT bearer token.

### Authentication

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/auth/register` | Create a user with `{email, password}` |
| `POST` | `/auth/login` | Return a JWT from JSON credentials |
| `POST` | `/auth/token` | OAuth2 form-compatible token endpoint |

### Companies

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/companies` | Create `{name, website_url}` |
| `GET` | `/companies` | List companies owned by the current user |
| `GET` | `/companies/{company_id}` | Read an owned company |
| `PUT` | `/companies/{company_id}` | Update an owned company |
| `DELETE` | `/companies/{company_id}` | Delete an owned company |

### Crawls

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/companies/{company_id}/crawl` | Queue a crawl with `max_pages` and `max_depth` |
| `GET` | `/companies/{company_id}/crawl-jobs` | List company crawl history |
| `GET` | `/companies/{company_id}/crawl-jobs/{job_id}` | Read one company-scoped crawl job |
| `POST` | `/companies/{company_id}/crawl-jobs/{job_id}/cancel` | Cancel a queued or running job |

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

Successful responses keep this shape:

```json
{
  "answer": "...",
  "sources": [
    {
      "title": "FastAPI",
      "url": "https://fastapi.tiangolo.com/"
    }
  ]
}
```

## Crawl Observability

Crawl job responses include the current execution's counters:

- `pages_discovered`: active URLs known during the crawl.
- `pages_crawled`: URLs successfully fetched and processed.
- `pages_indexed`: URLs whose content is indexed.
- `pages_failed`: URLs whose fetch or processing failed.
- `pages_new`: pages created and successfully ingested for the first time.
- `pages_changed`: existing pages whose content changed and whose chunks were successfully replaced.
- `pages_unchanged`: existing pages whose content hash matched and whose ingestion was skipped.
- `pages_deactivated`: previously active URLs not seen during the current crawl.
- `attempt_count`: number of job execution attempts, including retries.
- `duration_seconds`: derived from `started_at` and `completed_at`, or current elapsed time for a running job.

When a completed job is rerun, per-execution counters and execution timestamps are reset before the new run starts. Existing page and chunk data is not duplicated.

## RAG Flow

The chat path is intentionally small:

```text
question
  -> company-scoped vector search
  -> cosine-distance filtering and nearest-first ordering
  -> grouped, duplicate-free source context
  -> website-specific Gemini prompt
  -> answer + ordered, URL-deduplicated sources
```

The assistant is instructed to answer directly, synthesize related website facts, avoid unsupported claims, and clearly say when the website does not contain enough information. Navigation, header, footer, script, and style elements are removed during page parsing.

Gemini server failures are translated into a safe `502 Bad Gateway` response. Retrieval failures remain separate from provider failures.

## Security Boundaries

- JWT authentication protects private routes.
- Company and crawl-job queries are scoped to the authenticated user's company ownership.
- Crawl requests enforce SSRF protections and same-site crawling rules.
- Robots.txt, response-size, timeout, duration, and per-domain rate limits are enforced by the crawler.
- Provider error responses do not expose SDK tracebacks, prompts, API keys, or authorization headers.
- Keep secrets in environment variables and use a strong, private `JWT_SECRET_KEY` outside local development.

## Testing

Backend tests use the configured `TEST_DATABASE_URL`:

```bash
cd backend
source .venv/bin/activate
pytest -q
```

Frontend tests:

```bash
cd frontend
npm test
```

Frontend production build:

```bash
npm run build
```

The test suite covers authentication, ownership isolation, crawl lifecycle, retries, cancellation, recovery, security protections, incremental ingestion, statistics, RAG retrieval, provider failures, and frontend API/UI behavior.

## Troubleshooting

### `KeyError: 'JWT_SECRET_KEY'`

Confirm `backend/.env` exists and contains `JWT_SECRET_KEY`, then start Uvicorn from the `backend` directory.

### Frontend stays on “Signing in…”

Confirm both services are running:

```bash
curl http://localhost:8000/health
```

If the API is unreachable, the frontend reports a connection error after its request timeout.

### Crawls remain queued

Redis and the RQ worker must both be running. Verify that `REDIS_URL` points to the same Redis instance used by the API and worker.

### Chat returns a provider error

This indicates that Gemini was unavailable or timed out. Retry the request and check the backend logs for the provider error type and status code. The API intentionally returns a safe upstream error instead of a fabricated answer.

## Project Status

The current product includes the working backend crawl/RAG system and the React frontend workflow for login, companies, crawl monitoring, crawl history, statistics, and company chat. WebSockets and external observability infrastructure are intentionally not part of the current implementation; crawl updates use polling.
