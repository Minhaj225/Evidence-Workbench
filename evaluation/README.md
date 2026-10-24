# Evaluation dataset

`dataset.jsonl` contains 35 fixed cases. Do not change questions or evidence to obtain a passing retrieval result. Changes to corpus editions require a separately reviewed dataset version and a new digest.

The 30 answerable cases have five each of definition, enumeration, relationship, recommended-action, table, and synthesis questions. Difficulty is 10 easy / 12 medium / 8 hard; publication groups are 12 from AI 100-1, 12 from AI 600-1, and six using combined evidence. Five further cases require abstention.

Each quote is validated against the exact PDF hash, physical page, and normalized extracted block text. Normalization handles NFC, whitespace, and line-end dehyphenation. Source references are curated evidence; they do not establish that the reference answer is a universal account of the topic.

A relevant retrieval must match the document hash and page and contain the normalized evidence (or be contained in it with the stipulated shorter-text token overlap). HitRate is any relevant passage; precision divides relevant returned passages by actual returned count, capped at five; recall counts distinct gold spans covered; MRR uses the first relevant rank. Duplicate overlapping passages cannot increase recall for one gold span. Empty retrieval scores zero.

Ragas and a structured citation judge score generation only when configured. Failed rows stay in the denominator and missing judged metrics remain null. Paired bootstrap resamples aligned cases, 10,000 times with seed 42. This is a small curated benchmark; its confidence intervals describe these cases, not general corpus performance.

Artifacts are stored per immutable run. The synthetic report in `backend/tests/fixtures/report.py` tests UI behavior and is never evidence of retrieval or generation quality.
