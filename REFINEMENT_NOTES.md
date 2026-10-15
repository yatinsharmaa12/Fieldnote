# Fieldnote refinement — 16 October 2026

## Result

All final verification commands passed:

- Backend: `.venv/bin/pytest -q` — 126 passed (18.17s).
- Frontend: `npm test && npm run build` — 18 passed; TypeScript and Vite build passed.
- Extension: `npm test && npm run build` — 14 passed; TypeScript and Vite build passed.
- `git diff --check` — passed.

Non-failing dependency notices remain: a Google GenAI/Pydantic deprecation and React Router v7 future-flag warnings.

## Performance and behavior

- Reuse Gemini HTTP clients, cap output at 1,024 tokens, and disable automatic SDK retries that could multiply the 30-second provider timeout.
- Cache up to 256 query embeddings in process; answers and retrieved company content are not cached.
- A local warm-model microbenchmark measured median query embedding time of 20.729 ms without cache versus 0.002 ms on cache hits (12 uncached samples, 100 cached samples). This measures only the embedding stage, not end-to-end chat latency or live Gemini performance.
- Release the authentication database connection before retrieval/model generation; add company/ownership/join indexes.
- Aggregate crawl progress in SQL, avoid repeated discovery work, and throttle only URLs actually fetched.
- Prevent overlapping polls, pause polling in hidden tabs, recover from transient failures with backoff, and abort obsolete requests.
- Give chat a 45-second client deadline to accommodate retrieval plus the provider timeout; ordinary requests retain a 12-second deadline.
- Add Stop/retry interactions, question suggestions, clearer waiting and failure states, keyboard-friendly dialogs, focus indicators, and reduced-motion styling.
- Prevent old-site responses from appearing after an extension tab switch and prevent stale logout responses from clearing a new session.
- Fix root crawl failures being reported as success, duplicate unchanged-page counts, premature URL deactivation in partial crawls, robots origin handling, and list-marker guardrail mistakes.

## Deployment

Apply the new database migration against the intended deployment database before rollout:

```sh
cd backend
.venv/bin/alembic upgrade head
```

The migration was verified against isolated fresh and preinitialized test schemas, including persistence across connections. No production database migration was applied. Restart the backend/workers and reload the built extension after deploying. A temporary browser fixture was removed; no fixture authentication or mock API code remains in the product.

## Modified and added files

Paths below are relative to the repository root.

### Backend

- `backend/alembic/env.py`: keep extension creation and migrations in the committed migration transaction; support supplied test connections.
- `backend/alembic/versions/2d5e91a8b301_bootstrap_schema_and_query_indexes.py`: bootstrap missing base tables and add query indexes without deleting existing data.
- `backend/app/api/chat.py`: release the authentication database connection before generation.
- `backend/app/api/company_crawl.py`: include attempt count in job responses.
- `backend/app/crawler/crawler.py`: SQL progress aggregation, lazy embedding, discovery deduplication, correct partial-crawl handling, root failure propagation, and throttle only actual requests.
- `backend/app/crawler/robots.py`: origin-root robots URL, matching user agent, and deny on authorization failures.
- `backend/app/crawler/url_registry.py`: maintain last-seen and active/deactivated state.
- `backend/app/domain/job_state.py`: clear previous error when a job starts running.
- `backend/app/ingestion/embedding.py`: lazy shared model and bounded, synchronized query-vector cache.
- `backend/app/models/company.py`: ownership index.
- `backend/app/models/crawl_job.py`: company index.
- `backend/app/models/page_chunk.py`: page join index.
- `backend/app/models/page_db.py`: company and URL join indexes.
- `backend/app/rag/generator.py`: shared provider client, bounded retries/output, safe transport/empty-response handling.
- `backend/app/rag/guardrails.py`: remove list markers without whitelisting unrelated numerical claims.
- `backend/app/services/crawl_service.py`: honor cancellation around completion/retry and roll back before error recovery.
- `backend/tests/test_company_crawl.py`: attempt-count response fixture.
- `backend/tests/test_guardrails.py`: unsupported numeric-claim regression.
- `backend/tests/test_incremental_crawl.py`: unchanged counts, partial-crawl preservation, root failure, and skipped-URL throttle regression.
- `backend/tests/test_robots.py`: isolated network fixture, root robots path and forbidden-response tests.
- `backend/tests/test_latency_regressions.py`: embedding cache/concurrency, provider reuse, rate-limit/timeout/empty-output tests.
- `backend/tests/test_migrations.py`: fresh and initialized schema migration integration tests.

### Frontend

- `frontend/src/App.tsx`: resilient loading, live crawl updates, keyed company views, reusable dialogs, and clearer statuses.
- `frontend/src/api.ts`: in-flight GET deduplication, cancellable requests, body-inclusive deadlines, useful validation errors, and session expiration.
- `frontend/src/auth.tsx`: immediate logout and session-expiration handling.
- `frontend/src/styles.css`: interaction, loading, focus, responsive and reduced-motion refinements.
- `frontend/src/components/ChatPanel.tsx`: cancellable chat, suggestions, progress, retries and safe source links.
- `frontend/src/components/Dialog.tsx`: focus management, focus trap, Escape close and scroll locking.
- `frontend/src/hooks/useCrawlStatus.ts`: non-overlapping visibility-aware polling, retry backoff and cleanup.
- `frontend/src/App.test.tsx`: updated polling and terminal-state assertions.
- `frontend/src/api.test.ts`: deduplication, body deadlines, cancellation, validation and expiration regressions.
- `frontend/src/components/ChatPanel.test.tsx`: stop, unmount and retry regressions.
- `frontend/src/hooks/useCrawlStatus.test.tsx`: recovery, terminal, stale-response and visibility regressions.

### Extension

- `extension/src/App.tsx`: session/site loading, keyed site isolation, cancellable chat, duplicate-action protection and terminal-state recovery.
- `extension/src/api/auth.ts`: immediate local logout with captured-token revocation.
- `extension/src/api/chat.ts`: propagate cancellation.
- `extension/src/api/client.ts`: body-inclusive timeouts, cancellation, validation errors and token-safe expiration.
- `extension/src/api/crawl.ts`: propagate polling cancellation.
- `extension/src/hooks/useAuth.ts`: loading and session-expiration state.
- `extension/src/hooks/useCrawlStatus.ts`: resilient, visibility-aware polling.
- `extension/src/hooks/useCurrentTab.ts`: ignore stale tab-query results.
- `extension/src/styles.css`: focus and reduced-motion refinements.
- `extension/src/App.test.tsx`: tab-switch cancellation and timed-out crawl recovery.
- `extension/src/api/api.test.ts`: body deadlines, pre-cancelled requests and old-token expiration.
- `extension/src/hooks/useCrawlStatus.test.tsx`: polling recovery, visibility and stale-response regressions.

### Documentation

- `REFINEMENT_NOTES.md`: this implementation inventory, measured results and deployment notes.
