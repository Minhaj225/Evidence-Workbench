# Pinned corpus

`manifest.json` is the source of truth for URLs, SHA-256 hashes, physical page counts, and local filenames. Download with `make corpus`; existing files are reverified. Downloads are bounded, written to a temporary file, verified, and atomically moved into `data/corpus`. A checksum mismatch fails instead of changing the manifest automatically.

- NIST AI 100-1: Artificial Intelligence Risk Management Framework (AI RMF 1.0), 48 physical PDF pages.
- NIST AI 600-1: Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile, 64 physical PDF pages.

Source PDFs retain NIST publication notices. They are ignored by Git and fetched from the official publication host. Printed page labels can differ from PDF page numbers. Evaluation and citations always use physical, one-based PDF pages.
