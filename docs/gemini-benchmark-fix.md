# Gemini benchmark diagnosis and fixes

Verified on 24 October 2026 against the Docker application and the current checkout.

## Cause of the screenshot

Docker run `190c38d1-624e-4786-bd9a-33971ddf6feb`, created at 17:16:23 IST, had the Gemini key loaded and both hosted model settings set to `gemini-3.5-flash-lite`. This was not a missing-key failure.

| Saved failure | Cases |
|---|---:|
| Gemini quota/rate limit | 35 |
| Invalid citations after a repair attempt | 4 |
| Unclassified evaluation failure during judging | 1 |

The run retained local retrieval results: baseline HitRate@5 was 56.7%, enhanced 90.0%. Generation and judging require hosted API requests in addition to retrieval. Some judged results were recorded: 3 of 30 baseline answerable cases and 20 of 30 enhanced answerable cases had faithfulness scores. The summary deliberately requires every answerable case to have a score before calculating a judged aggregate. Therefore enhanced faithfulness was unavailable, and the overall benchmark failed. “65/65 processed” means terminal results were saved for every case, including errors.

The old report discarded the exception details for its unclassified judge failure; its precise cause cannot be recovered. A subsequent tiny request from Docker succeeded, confirming the key/model could work. That does not establish the project's exact minute, token, or daily quota.

## Repository review

Reviewed the configuration, containers and frontend routing; ingestion/storage/worker recovery; chunking and local model adapters; retrieval; generation and citation validation; Ragas judging, benchmark persistence, metrics and reporting; API/frontend result handling; and the associated scripts and tests.

The failure path had no requests-per-minute budget shared by generation and the judge. Serial answer generation alone does not limit the many requests made by Ragas. Its default provider retry policy could also add requests. The UI exposed a generic gate failure without summarizing the provider errors or score coverage. Local development also defaulted to a hardcoded remote API instead of the local backend.

## Changes

- Shared pacing across interactive answers, answer repairs, Ragas calls/repairs, and citation judging. Default `GEMINI_REQUESTS_PER_MINUTE=5` spaces requests at least 12 seconds apart within the single API process.
- One transport attempt per request for the native SDK and Ragas wrapper. Ragas' existing bounded malformed-output repairs remain paced.
- Safe error classification for quota, daily exhaustion, timeouts, rejected credentials (including structured invalid-key HTTP 400), and unavailable models. Daily/auth/model failures suppress remaining hosted calls while retaining local retrieval measurements, including after a worker restart.
- Per-case safe messages and failure stages, structured diagnostic logs, and per-metric score counts. The frontend explains failures and derives coverage for preserved older reports too.
- Local development defaults to `http://127.0.0.1:8000`; an explicit `API_URL` still overrides it. Docker applies `.env` updates by recreating the API container.

Retrieval parameters, gold evidence, acceptance thresholds, citation validation, stored documents, and previous reports were preserved. No new dependency was added.

## Validation

- Backend suite with real local Qdrant: 83 passed; 89.62% application coverage and all critical-module coverage gates passed.
- Frontend: 10 tests passed; lint, type checks and production build passed. Python lint, formatting and type checks passed.
- Hosted synthetic launch-year test: generation and actual Ragas faithfulness, context precision, context recall, and citation coverage passed at the default pacing. No user documents were sent by this test.
- Docker API/web rebuilt; runtime key presence and five-request-per-minute setting verified without exposing the key. All production components reported healthy, and both documents and the saved benchmark remained present.

- Browser acceptance: both existing tests passed against an isolated Docker fixture stack (upload/ingest/answer/citations/abstention/evaluation/delete and mobile layout).
- Production browser check: the rebuilt application showed the actual 35 quota failures, 4 citation failures, and 20/30 enhanced judge coverage with no page errors. [Screenshot](../artifacts/verification/evaluation-quota-diagnostics.png).
- Local development routing self-check passed for both the local default and an explicit `API_URL` override. An installed Chromium executable was selected with `CHROME_PATH` because the browser revision expected by the updated Playwright package was absent.

## Remaining limits

The entire 65-case hosted benchmark has not been rerun. At the default rate it can take over an hour and may exceed a project's daily or token quota. Pacing cannot guarantee Google quota availability or a model's answer quality. Invalid model citations still fail validation. A new benchmark is required to establish full-corpus faithfulness and whether every quality gate passes; the old failed report stays unchanged.

The existing Ragas integration emits deprecation warnings, and the frontend build reports a large bundle warning. These do not fail the checks above. This review does not establish compatibility with the separate Vercel/PostgreSQL deployment guide: the current worker, document storage and database setup are designed for the persistent Docker/SQLite deployment.
