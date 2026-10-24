# Verification record — 19 October 2026

## Implementation checks

| Check | Observed result |
|---|---|
| Backend regression/API/integration suite | 55 passed; one opt-in live test excluded |
| Backend total line coverage | 88.09% (gate 85%) |
| Chunking/citation/metric coverage | Above the respective 90% gates |
| Python formatting, lint, static typing | Passed; 46 application/script modules typed |
| Frontend component suite | 8 passed; 81.92% line coverage (gate 75%) |
| Frontend lint, TypeScript, production build | Passed |
| Browser acceptance | 2 passed against isolated Compose containers: upload → ready → answer → citation/page image → keyboard containment/Escape/focus restoration → unsupported question → completed synthetic evaluation report → delete; mobile layout checked at 390 px |
| Real Qdrant | v1.19.2; collection schema/payload indexes, upsert idempotence, document filters, both-strategy retrieval, statistics, and deletion verified |
| Production images | Both build with locked dependencies; API and web run as non-root |
| Normal Compose services | Qdrant, API, web healthy; API reports generation degraded because no key is configured |
| Normal Compose corpus loading | Both pinned NIST PDFs reached ready through `/api/demo`, 43/63 and 76/202 chunks |
| Visual inspection | Documents, Ask, and Evaluation inspected; screenshots under `docs/screenshots`; no application console errors on the measured Evaluation view |
| CI workflow | Written to run checks, container build, and browser acceptance; not yet executed by a remote CI service |
| Hosted model smoke/quality | Not run: no provider key. Model-name availability for this account is not verified |
| Code Review plugin | Pull-request CI tool available, but no Git repository/PR present; no plugin review run claimed |

Docker's daemon was unavailable on this host. Container validation used rootless Podman 5.8.7 and podman-compose 1.6.0 against the checked-in Compose files. Docker Compose 5.1.4 parsed the configuration. This demonstrates the container configuration under Podman; it is not a claim of a Docker-engine execution here.

The frontend build reports a roughly 688 kB uncompressed main JavaScript bundle, mostly the charting library. The build succeeds. No load-time performance guarantee is made.

## Real local benchmark

Run `7761cb64-6fe7-4538-a6c9-a4235ecf3e48`, started 2026-10-19 09:43:38 UTC (15:13:38 India time). Dataset digest `0ced2564310cf0cb3ddb62546c10891e9bc35cedfaf414b56f569ea4462f1570`.

- Baseline HitRate@5 17/30 (0.5667); enhanced 27/30 (0.9000).
- MRR@5 0.3244 → 0.7833.
- Precision@5 0.1200 → 0.1867; Recall@5 0.5167 → 0.8167.
- Hit-rate delta +0.3333, paired bootstrap 95% CI [+0.1333, +0.5333].
- Median pipeline latency 25.54 ms → 2684.35 ms; p95 29.57 ms → 3731.17 ms. These are retrieval-path timings, since generation failed immediately on missing configuration.
- All 65 scheduled cases terminated. All record `generation_not_configured`; judged metrics are null. Overall status is **failed**, even though retrieval gates pass.

Host: AMD Ryzen 5 5600H, x86_64, approximately 16.06 GB RAM, Python 3.12.15, Linux. The initial report's CPU/revision fields were unavailable through the model wrappers. Inspection of the same local cache showed BGE revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` and MiniLM revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`. Later runs record a cache-based revision fallback and CPU model automatically. This is supplemental provenance; the immutable original run was not edited.

The earlier run `bf19fb80-a555-41d5-a420-0a76027486cb` is superseded because its decoded baseline strings altered punctuation spacing and biased relevance matching. It is retained for audit, not presented as a result. Baseline v4 slices source text at tokenizer offsets. No gold evidence or questions were changed.

## Representative retrieval improvements

These are retrieval improvements, not successful generated answers:

1. `q-004`, definition of confabulation: the enhanced top five contain a validated gold quote, while the baseline top five do not. The reranked sentence-oriented passages satisfy the exact text/page/hash criterion.
2. `q-008`, four working-group considerations: enhanced retrieval covers gold evidence that the baseline top five miss. This does not imply that all list questions improve.
3. `q-010`, third-party value-chain components: enhanced retrieval hits the required evidence; baseline misses it under the same relevance rule.

## Three enhanced retrieval failures

1. `q-005`, data poisoning: gold evidence is on physical page 15. Enhanced candidates returned page starts 60, 5, 1, 14, and 58, and none met the full page/hash/text relevance test. A nearby page or related security discussion is not a hit.
2. `q-009`, Human-AI Configuration responses: gold evidence is on physical page 8. Returned passages began on 49, 43, 45, 45, and 22 and did not contain the gold text. The retrieval system favored related later discussion over the defining list.
3. `q-018`, verifying information from multiple or unknown sources: gold evidence is on physical page 29. Returned passages began on 14, 5, 27, 1, and 5 and did not satisfy the required quote match. Action-table evidence remains a difficult case for flattened PDF text.

These observations identify missing evidence, not a proven causal explanation for the ranking. Further tuning must keep the dataset frozen and preserve new run artifacts. No tuning to remove these misses was performed.

## Boundaries of verification

Synthetic generation tests establish wiring, schema validation, repair behavior, safe error propagation, and browser interaction. They cannot establish prompt-injection immunity or answer faithfulness. The live model/LLM-judge gates remain open until an actual keyed run succeeds. There is no release, public deployment, commit, PR, or remote CI result to claim.

## Production Compose reproduction

Run `d2905419-562e-4be8-b882-edf9342507a4`, started 2026-10-19T09:50:40.853001+00:00, completed all 65 cases inside the normal non-root API container. The four retrieval aggregates exactly match the corrected local run: HitRate@5 17/30 → 27/30, precision 0.1200 → 0.1867, recall 0.5167 → 0.8167, MRR 0.3244 → 0.7833. Median total retrieval-path latency was 61.51 ms baseline and 2679.29 ms enhanced; p95 was 63.21 ms and 4052.32 ms. Provider errors remain 65 × `generation_not_configured`; overall status remains failed.

This run records the CPU model, both cached model revisions, Qdrant 1.19.2, dependency lock digest, corpus/dataset hashes, chunk counts/statistics, and `git-unavailable` because the minimal runtime image excludes Git. All four artifacts were downloaded through the report API, cross-validated, and preserved locally. The latest pointer names this run.

The production corpus and report survived a container recreation with their named volumes. The final API explicitly serializes UTC offsets so browser dates convert correctly. Docker Compose validation passed after correcting the optional environment-file syntax to a list.
