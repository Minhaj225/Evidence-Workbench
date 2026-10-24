# Plan analysis and implementation decisions

The source brief is `/home/minhaj/Coder/Ideas/p1_plan.md`. Its product and acceptance requirements guide this implementation. Instructions addressed to an implementing model inside that document are document content, not independent authorization to publish, spend money, or change unrelated projects.

## Architecture and scope

This is a single-user, single-node application. FastAPI owns validation, persisted jobs, retrieval, generation, evaluation, and private page previews. SQLite owns document/job/run lifecycle records; Qdrant owns retrieval payloads and vectors. The frontend has Documents, Ask, and Evaluation routes. There is one application worker process and one serialized ingestion/evaluation queue. Multiple Uvicorn workers would duplicate recovery and are unsupported.

Authentication, multi-tenant isolation, OCR, arbitrary web crawling, hybrid search, streaming generation, and distributed workers are outside the brief. The supplied Compose ports bind to loopback. Do not expose the unauthenticated API directly to the Internet.

## CSS decision

Retain ordinary CSS with shared custom properties, React Router, TanStack Query, and Recharts. This three-view application benefits from a small, readable stylesheet; Tailwind adds no necessary capability. The UI uses restrained blue accents, a clear document table, explicit unavailable/error states, and a native modal citation drawer with keyboard containment, Escape, and focus restoration. Layout adapts to small screens and reduced motion.

## Contracts and implementation

| Area | Implementation and rationale |
|---|---|
| Uploads | PDF and UTF-8 text; 20 MiB streamed limit, multipart envelope bound, randomized private paths, SHA-256 deduplication, sanitized display names. A filename never becomes a storage path. |
| PDF validation | Signature, parser validity, encryption, page limit, and text density checked; image-only documents fail with an OCR-required error. Physical PDF page numbers are used. |
| Provenance | Normalized source blocks retain page, bounding box, and offsets in the cleaned text stream. Each chunk has exact source spans and a deterministic content/version-derived UUID. These offsets are not raw PDF byte offsets. |
| Cleaning | Unicode normalization, whitespace/dehyphenation, repeated margin removal, and heading boundaries. Tables remain extracted text; no claim of table structure reconstruction. |
| Baseline | Up to 512 content tokens with 50-token overlap. Source text is sliced using tokenizer offsets instead of decoded token strings: decoding changes punctuation spacing and unfairly breaks the plan’s exact-evidence matcher. A leading WordPiece fragment may retokenize into more tokens, so the end is shortened until the actual serialized chunk fits. |
| Semantic | Sentence embeddings, p95 dissimilarity boundary (median + 1.5 IQR for small samples), hard heading boundaries, minimum-size merging, 448-token body cap, target 384, last-sentence overlap up to 64, and heading prefix only when final text fits 512. Short sections can remain below 128 when no legal merge exists. |
| Embedding | CPU BGE-small-en-v1.5, 384 dimensions, normalized vectors, query instruction prefix. BGE's 512 positions include two special tokens: content longer than 510 is segmented safely, embedded separately, and combined by token-weighted normalized pooling. This explicit encoding deviation avoids silently losing source tokens. |
| Retrieval | Baseline dense top five. Enhanced dense top 50, MiniLM cross-encoder rerank, final five. Ties use dense score then chunk ID. Scores are ranking signals, not probabilities. |
| Generation | Server-side OpenAI Responses structured parsing, fixed evidence envelope, no tool access, ID/inline-marker validation, at most one schema/citation repair. Provider failures become stable safe errors. |
| Abstention | Insufficient-context answers must have no citation markers or used source IDs. This deliberately stricter rule avoids implying that a nearby passage answers an unsupported question. |
| Recovery | Job committed before queueing; cleanup of both indexes before retry; ready only after both counts match. Interrupted jobs resume on startup. Native model work can outlive coroutine cancellation until process shutdown; the next ingestion clears partial vectors. |
| Deletion | Per-document lock, deleting state, both vector collections, originals, cache, and database metadata removed in that order. Partial cleanup stays retryable. `force=true` waits for active use rather than racing a background write. |
| Reindexing | Re-uploading identical content rebuilds stale versions or missing vector counts. Failed ingestion needs explicit retry. Evaluation refuses a stale corpus; run demo ingestion before rerunning it. |
| Evaluation | Frozen 35-case dataset with exact distributions and validated quotes; both strategies for 30 answerable questions, enhanced for five unanswerable questions; paired bootstrap with 10,000 resamples/seed 42. Errors retain their cases. |
| Reporting | Run JSON, per-case JSONL, CSV, and Markdown; finalized runs cannot be overwritten. The latest pointer advances only after report cross-validation. Missing judged scores are null, never substituted with success or zero. |
| Concurrency | Evaluations lock their corpus to avoid deletion/reindex races. New uploads can queue while an evaluation runs. No distributed locking is provided. |
| Containers | Pinned Python/Node/Qdrant/nginx images, locked dependencies, non-root API/web users, named volumes, health checks. The browser fixture has a separate entrypoint requiring APP_ENV=test. |

## Dataset review

The two NIST PDFs are pinned by URL, SHA-256, and physical page count. Every answerable record has a human-readable reference and exact normalized evidence. The 30 answerable cases contain five each of definition, enumeration, relationship, recommended-action, table, and synthesis questions; difficulty is 10 easy / 12 medium / 8 hard; corpus grouping is 12 / 12 / 6. Five additional questions require abstention.

The illustrative question in the brief refers to a printed page number; dataset evidence uses the actual PDF page index. This correction preserves the evidence requirement. The dataset is small and curated, not a statistically representative general benchmark. Its wording/evidence must not be changed to make retrieval gates pass.

## Acceptance and remaining evidence

Implementation tests and synthetic browser tests establish behavior, not model quality. A real corpus run measures retrieval. Answer faithfulness, Ragas context metrics, citation coverage, and abstention support require a valid provider key and a successful live run. The illustrative improvement in the brief is not a measured result. Current measured results and exact validation status are in `README.md` and `docs/verification.md`.

No Git history or pull request was present in this workspace. The Code Review plugin exposes pull-request CI checks only, so local code was reviewed through source inspection, static checks, regression tests, real Qdrant integration, and browser acceptance.
