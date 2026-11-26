# MeenMitra — Engineering Notes

> Consolidated engineering work log from Day 1 through 24 November 2026.
>
> This document separates completed implementation work from verified command output and items that still need confirmation. Test results and deployment results are recorded only where evidence was retained.

## Project overview

MeenMitra is a fisheries information backend intended to help fishers in Tamil Nadu find useful information about fishing-ban periods, fishing gear regulations, fish species, and welfare schemes. It aims to connect local Tamil fish names with scientific names and relevant fisheries information.

**Technology stack**

- Python 3.12
- `uv` for Python project and dependency management
- FastAPI
- PostgreSQL
- SQLAlchemy and Alembic
- Docker and Docker Compose
- Redis
- pytest and pytest-cov
- Poe the Poet
- Ruff and pre-commit
- GitHub Actions
- GitHub Container Registry (GHCR)
- Render
- Neon PostgreSQL

**Repository**

`madhumithra0705-ops/prince28-agr03-meenmitra`

**Live backend**

- API: https://meenmitra.onrender.com
- API documentation: https://meenmitra.onrender.com/docs

---

## D01 · Project foundation

### Goal

Establish the Python project foundation and a maintainable structure for the MeenMitra backend.

### Project setup

- Python project managed with `uv`.
- Application package: `src/meenmitra/`.
- Configuration managed through environment-based settings.
- Project dependencies and task commands declared in `pyproject.toml`.
- Local configuration kept outside source control.
- `.env.example` documents the expected environment variables.

### Application configuration

The application settings include:

- `app_name`
- `app_env` (`local`, `ci`, or `production`)
- `log_level`
- `data_file`

`APP_ENV` is intentionally required rather than silently defaulted. Invalid values are rejected during settings validation.

### Repository conventions

- Application code lives under `src/meenmitra/`.
- Tests live under `tests/`.
- Data fixtures live under `data/`.
- Ruff is used for linting and formatting.
- Poe tasks provide repeatable project commands.

**Evidence note:** The repository foundation is documented, but an exact Day 1 terminal transcript and Day 1 test count were not retained. No unverified command output is claimed.

---

## D02 · FastAPI service foundation

### Goal

Build a FastAPI service with clear boundaries between configuration, request handling, data access, errors, and logging.

### Application structure

The service foundation includes:

- `config.py` — validated application settings.
- `logging_setup.py` — structured JSON logging and request-ID context.
- `store.py` — initial in-memory record store loaded from `data/sample_records.json`.
- `api/main.py` — application factory and lifespan setup.
- `api/deps.py` — FastAPI dependency injection.
- `api/middleware.py` — request IDs, request timing, and unexpected-error handling.
- `api/errors.py` — consistent RFC 9457-style problem responses.
- `api/routes/health.py` — `/health` and `/ready`.
- `api/routes/documents.py` — document listing, search, pagination, and lookup.

### API behaviour

- `GET /health` is the liveness endpoint. It reports whether the process is running and does not depend on the database.
- `GET /ready` reports whether the service is ready to serve traffic.
- `GET /v1/documents` supports search and pagination.
- `GET /v1/documents/{doc_id}` returns a document or a structured 404 response.
- Invalid request parameters are handled as validation errors.
- Responses carry an `X-Request-ID`. A supplied request ID is reused; otherwise, one is generated.
- Unexpected request failures are logged and converted into a controlled HTTP 500 response.

### Initial data-store design

The first `RecordStore` loads JSON records and requires each record to have an `id`. It supports readiness, search, and lookup.

Keeping the store behind the API dependency layer allowed the backing store to be replaced with PostgreSQL later without changing the endpoint contract.

**Evidence note:** The FastAPI skeleton and implementation details are documented. Exact Day 2 test totals and complete terminal transcripts were not retained.

---

## D03 · PostgreSQL, migrations, and data loading

### Database integration

The in-memory store was replaced by PostgreSQL-backed persistence. The backend uses SQLAlchemy models and sessions, with Alembic managing schema changes.

Key database work:

- PostgreSQL database and session configuration.
- SQLAlchemy document and page models.
- Alembic migration history.
- JSONB metadata storage and a GIN index.
- SHA-256 document fingerprints.
- Document descriptive fields and timestamps.
- Repository-layer database operations.
- A repeatable data loader.

### Migration verification

An earlier migration downgrade and upgrade check produced:

```powershell
uv run alembic downgrade -1
uv run alembic current
uv run alembic upgrade head
```

Recorded results:

```text
Successfully downgraded from c32d6f697003 to a009a85f761c.

Current revision:
a009a85f761c

Successfully upgraded from a009a85f761c to c32d6f697003.
```

Later migrations extended the schema with `source_url`, SHA-256, and descriptive/timestamp fields.

The migration run recorded during the Docker Compose build applied:

```text
Running upgrade  -> a009a85f761c, create documents and pages
Running upgrade a009a85f761c -> c32d6f697003, add gin index on metadata
Running upgrade c32d6f697003 -> 924078ec9bae, add source_url to documents
Running upgrade 924078ec9bae -> 4e9ce3848267, add sha256 to documents
Running upgrade 4e9ce3848267 -> ee3b0a666077, add document descriptive and timestamp fields
```

### Loader idempotency

The loader was run repeatedly against the same dataset.

**Run 1 — initial load**

```text
records=20 inserted=20 updated=0 unchanged=0
```

**Run 2 — same data loaded again**

```text
records=20 inserted=0 updated=0 unchanged=20
```

**Run 3 — after editing one record**

```text
records=20 inserted=0 updated=1 unchanged=19
```

The loader uses SHA-256 fingerprints to identify changed records. Unchanged records are skipped; changed records are updated.

### JSONB query-plan inspection

Command:

```powershell
uv run python scripts/explain.py sha256 6070e0c336534abd3c0d6275d196072e663a473549432698f84b2d8327bc2f78
```

**Normal planner**

```text
Seq Scan on documents
Rows Removed by Filter: 19
Execution Time: 0.523 ms
```

**With sequential scan disabled**

```text
Bitmap Heap Scan on documents
  -> Bitmap Index Scan on ix_documents_metadata_gin
Execution Time: 1.933 ms
```

**Interpretation:** The table had only 20 records, so PostgreSQL estimated a sequential scan to be cheaper than an index lookup. For a larger table and a selective JSONB filter, the planner may choose the GIN index when its estimated cost is lower.

### SHA-256 support

- The database migration adds a SHA-256 field to documents.
- The API returns the `sha256` field.
- The API supports filtering documents by SHA-256.

Migration command:

```powershell
uv run alembic upgrade head
```

---

## D04 · Docker, Compose, tests, and delivery

### Docker image

The Dockerfile uses a multi-stage build and runs the application as the non-root `app` user. `.dockerignore` keeps unnecessary files out of the build context.

Recorded image evidence:

```text
IMAGE           ID             DISK USAGE   CONTENT SIZE
meenmitra:dev   8e469890d750   300MB        70MB
```

The image was below the 400 MB target.

### Non-root verification

Command:

```powershell
docker run --rm meenmitra:dev id
```

Output:

```text
uid=999(app) gid=999(app) groups=999(app)
```

### Build-cache verification

- Initial build time: 19.2 seconds.
- Cache-test rebuild time: 15.3 seconds.
- The dependency-install step `uv sync --locked --no-install-project --no-dev` was reported as `CACHED`.
- The temporary `/health` docstring change used for the cache check was reverted.

### Docker Compose stack

The Compose stack contains:

- `db` — PostgreSQL with pgvector.
- `redis` — Redis.
- `migrate` — one-shot Alembic migration service.
- `api` — FastAPI application.

Recorded stack status:

```text
meenmitra-api-1       meenmitra-api             api       Up (healthy)
meenmitra-db-1        pgvector/pgvector:pg17    db        Up (healthy)
meenmitra-migrate-1   meenmitra-migrate        migrate   Exited (0)
meenmitra-redis-1     redis:7-alpine            redis     Up (healthy)
```

### Clean-clone verification

A clean clone was created in a separate directory. The stack was built and started from that clone:

```powershell
docker compose up --build -d
```

The API, database, and Redis reached healthy/running states, and the migration service exited successfully.

The clean-clone stack was taken down and the temporary clone removed. The original project stack was also restarted successfully.

### Migration repeatability after restart

After `docker compose down` without `-v` and `docker compose up -d`, the migration logs ended with:

```text
records=20 inserted=0 updated=0 unchanged=20
```

This confirms that existing records were not duplicated or unnecessarily updated on restart.

### Liveness and readiness verification

When PostgreSQL was stopped, `/health` continued to respond:

```text
{"status":"ok","app":"meenmitra","env":"local"}
```

The readiness response was:

```text
HTTP/1.1 503 Service Unavailable
{"status":"not_ready","checks":{"database":false}}
```

After restarting PostgreSQL:

```powershell
docker compose start db
curl.exe -i localhost:8000/ready
```

Recorded response:

```text
HTTP/1.1 200 OK
{"status":"ready","checks":{"database":true}}
```

### Tests and coverage

**Unit tests**

```powershell
uv run poe test
```

Recorded results:

```text
18 passed in 0.81s
```

An earlier run recorded 18 passed in 1.04 seconds.

**Integration tests**

```powershell
uv run poe test-integration
```

Recorded result:

```text
7 passed in 6.71s
```

**Coverage**

- Unit-only coverage: 81%.
- Combined unit and integration coverage: 95%.

Recorded combined run:

```text
TOTAL                               262     10     28      4    95%
12 files skipped due to complete coverage.
25 passed in 5.65s
```

Two meaningful uncovered error-handling paths were identified:

- `src/meenmitra/api/deps.py` — database connection failure handling used by readiness checks.
- `src/meenmitra/api/middleware.py` — unexpected request-error handling that returns a controlled HTTP 500 response.

The manual readiness check verified database failure and recovery, but it does not count as pytest coverage.

### Tooling and documentation

- `Makefile` added for convenient project commands.
- Poe tasks include development, lint, unit tests, coverage, migrations, seeding, and integration tests.
- README includes a one-command local startup using `docker compose up --build`.
- `.gitignore` includes coverage output paths.

### Pre-commit and GitHub delivery

All recorded hooks passed on the feature branch:

```text
trim trailing whitespace       Passed
fix end of files               Passed
check yaml                     Passed
check toml                     Passed
check for added large files    Passed
detect private key             Passed
ruff check                     Passed
ruff format                    Passed
Detect secrets                 Passed
```

Feature branch:

```text
feat/day-04-docker-tests
```

Commit:

```text
29d4dc1 docs: run locally in one command, task runner, day 4 notes
```

Pull request title:

```text
feat: docker, compose stack and unit/integration tests
```

The pull request was merged into `main`, the remote feature branch was deleted, and the local branch was updated with:

```powershell
git switch main
git pull
```

---

## D05 · CI/CD and going live

### Deployment

Live URL:

https://meenmitra.onrender.com

API documentation:

https://meenmitra.onrender.com/docs

### CI and CD runs

- CI run for PR #5: https://github.com/madhumithra0705-ops/prince28-agr03-meenmitra/actions/runs/44701211052
- First successful automatic deployment (CD #2): https://github.com/madhumithra0705-ops/prince28-agr03-meenmitra/actions/runs/44716701716
- Recorded CD workflow duration: 50 seconds.

Exact merge-click and smoke-test completion timestamps were not retained, so merge-to-live lead time is not recorded.

### Smoke test

Recorded output from the first successful automatic CD run:

```text
ok   /health -> 200, version 2ced9003b6a2bdaad30294e094bc0dba2d5b4b98
ok   /ready -> 200 {'status': 'ready', 'checks': {'database': True}}
ok   /v1/documents?limit=1 -> 200
Smoke test passed
```

### Rollback and roll-forward drill

**Rollback**

- Rolled back to SHA `6f358e162533bb6c19a2388420372e543508639f`.
- Approximate elapsed time: 3 minutes.
- CD run: https://github.com/madhumithra0705-ops/prince28-agr03-meenmitra/actions/runs/44733280814

**Roll-forward**

- Rolled forward to SHA `4450cf04b26da7ec0603166faf13a39b7cbab781`.
- Approximate elapsed time: 3 minutes.
- CD run: https://github.com/madhumithra0705-ops/prince28-agr03-meenmitra/actions/runs/44733769105

The rollback workflow skips migrations and changes only the deployed application image. The newer database schema was backward-compatible with the older application version for this rollback.

### Secrets

- Neon connection string: GitHub Secret `DATABASE_URL` and Render environment.
- Render deploy hook: GitHub Secret `RENDER_DEPLOY_HOOK`.
- Secrets are not stored in the project source code or Docker image.

### Monitoring

- UptimeRobot checks `/health` every 5 minutes.
- Email alerts are configured.
- The free Render instance may have a cold-start delay on its first request. An always-on hosting instance would avoid that delay.

---

## D06 · Corpus collection and downloader reliability

### Goal

Build a fisheries document corpus from identified sources, download source files, and make the collection process resumable.

### Source collection

- The corpus work covered 12 sources.
- The initial download run downloaded 9 files and recorded 3 failures.
- The resume run and the third run reported 0 newly downloaded, 9 skipped, and 3 failed.
- Three Tamil Nadu Fisheries URLs returned HTTP 404.

The 404 results are recorded as source availability failures; they should not be described as successful downloads.

### Downloader resume and interruption test

An isolated temporary test was run using 20 CMFRI URLs.

Test procedure and recorded results:

1. The test was interrupted after 3 downloads.
2. No `.part` files remained after interruption.
3. The resume run downloaded the remaining 17 files.
4. The 3 already downloaded files were skipped.
5. No blocked or failed URLs were recorded in the resume test.
6. All 20 files were completed.
7. The original project corpus was unchanged by this isolated test.

The isolated test verified that interrupted downloads can resume without downloading completed files again.

### Corpus and delivery documentation

The corpus work included tracking source information and download results for project data.

Delivery requirements being tracked included:

- Every `data/sources.csv` row should have a licence value.
- `data/manifest.jsonl` should be committed.
- `DATASET.md` should contain licence and known-gaps tables.
- `CAPACITY` documentation should include the relevant corpus metrics.
- Raw downloaded files should not be committed to Git.
- Source collection should respect robots and access restrictions.

### Tests and Git status

- A recorded test run reported 40 tests passed.
- At the latest retrieved checkpoint, the latest three-file changes had not yet been confirmed as merged.
- The complete delivery checklist should not be marked finished until the files, licence coverage, manifest, documentation, and Git status are checked on `main`.

---

## D07 · Document parsing and database storage

### Goal

Parse the collected PDF, HTML, and text documents into structured document and page records, preserving useful headings and tables.

### Parser implementation

Main parser module:

`src/meenmitra/ingest/parse.py`

The parser supports:

- PDF parsing with PyMuPDF.
- Alternative PDF parsing with pypdf.
- HTML extraction with Trafilatura.
- Plain text and structured text formats.
- Markdown-style heading detection.
- Page splitting.
- Repeated header and footer removal.
- Text cleaning.
- Heading-path tracking.
- Structured parse errors for unsupported, corrupt, encrypted, empty, or scanned files.

The PyMuPDF parser detects larger-font headings and converts ruled tables into Markdown tables. PDFs without a usable text layer are reported as requiring OCR rather than being treated as successfully parsed.

HTML parsing uses Trafilatura to extract the main article and reduce navigation, footer, script, and other page noise.

### Parser storage

Main storage module:

`src/meenmitra/ingest/store.py`

The storage layer:

- Creates a document ID from the SHA-256 fingerprint.
- Saves document metadata and parsed pages.
- Records parser name, page count, table count, and character count.
- Stores parse failures separately.
- Updates an existing failure record rather than creating duplicate failure rows.
- Clears an earlier failure when a later parse succeeds.
- Commits each document separately so an interrupted run does not leave a partially saved document.

### Database integration fixes

During integration testing, the following model attribute mismatches were corrected:

- `doc.metadata_` was changed to the actual model attribute `doc.document_metadata`.
- `Page.page_no` was changed to the actual model attribute `Page.page_number`.

These fixes aligned the parser storage code with the SQLAlchemy model definitions.

### Parser tests

The parser unit tests cover:

- PDF page numbering.
- Heading detection and heading paths.
- Markdown table extraction.
- Scanned PDFs with no text layer.
- Corrupt PDFs.
- Password-protected PDFs.
- Repeated headers and footers.
- Agreement between PDF parser page counts.
- Text cleaning.
- Tamil text preservation.
- Markdown, reStructuredText, and AsciiDoc headings.
- HTML article extraction and navigation removal.
- Empty and unsupported files.
- Page splitting.
- Comments inside code blocks not being mistaken for headings.

Recorded test history:

- The parser unit suite had 17 passing tests before two PDF title tests were added.
- The two additional PDF title tests passed individually (2 passed).
- The parser-store integration tests passed 3/3 after the model attribute corrections.
- A full current test-suite result after all later parser changes was not confirmed in the retrieved evidence.

### HTML extraction improvement

The Tamil Nadu Fisheries page extraction was adjusted after the earlier article selectors did not capture the expected content.

The selector fallback includes:

- `.ep_summary_content_main`
- `.ep_tm_page_content`
- `section.sidemenu section.faq`
- A body fallback

Regression test:

`test_tn_fisheries_page_keeps_article_and_drops_navigation`

The regression test passed. The purpose was to preserve article content while avoiding unrelated navigation content.

### PDF title extraction

PDF title extraction was improved to avoid generic metadata titles and to find report titles after blank pages.

Tests added:

- `test_pdf_title_ignores_generic_powerpoint_metadata`
- `test_pdf_title_finds_report_title_after_blank_pages`

Both tests passed individually.

Recorded title checks:

- PMMSY FAQ: `Pradhan Mantri Matsya Sampada Yojana Frequently Asked Questionaries (FAQs)`
- FIMSUL document: `FISHERIES MANAGEMENT OPTIONS FOR TAMIL NADU & PUDUCHERRY`
- Gazette PDF: `CHAPTER I`

The Gazette title result is not necessarily the desired document-level title. Its heading extraction also showed limitations, so that case should not be treated as fully resolved.

### Full-corpus parsing

The corpus parser was run against the test database branch `meenmitra-test`.

Recorded result:

```text
files=344
parsed=344
pages=1302
failures=0
```

Elapsed time:

```text
429.6 seconds
```

A second run verified idempotency:

```text
files=344
already_parsed=344
pages=0
seconds=2.0
```

The second run did not parse or insert duplicate pages for already parsed files.

**Database scope:** These results were recorded against the test database, not the production database.

---

## D07 · Parser comparison: ten difficult files

### Goal

Compare the extraction quality of the available PDF and HTML parsers using ten of the largest source files.

Script:

`scripts/compare_parsers.py`

The script selects the ten largest PDF/HTML/HTM files when run without arguments.

Comparison methods:

- PDF: PyMuPDF versus pypdf.
- HTML: Trafilatura versus BeautifulSoup tag stripping.

The comparison records extracted character counts, page counts where applicable, and text previews. It also writes the comparison table to `NOTES.md` between:

```text
<!-- BEGIN PARSER COMPARISON -->
<!-- END PARSER COMPARISON -->
```

### Recorded comparison results



| File | Parser results | Quality observation |
|---|---|---|
| CMFRI training manual | PyMuPDF 496,288 chars / 248 pages; pypdf 472,740 / 248 | **PyMuPDF** — extracted more text; previews were comparable. |
| NITI report `gss1155a000607` | PyMuPDF 134,138 / 174; pypdf 126,259 / 174 | **PyMuPDF** — more extracted text and clearer heading structure. |
| CMFRI marine fish landings | PyMuPDF 29,317 / 16; pypdf 41,884 / 16 | **PyMuPDF** — more readable on inspected pages; pypdf had embedded-font encoding problems. |
| CMFRI marine fish stock status | PyMuPDF 34,724 / 28; pypdf 33,765 / 28 | **PyMuPDF** — slightly more text and clearer heading formatting. |
| PMMSY guidelines | PyMuPDF 807,379 / 237; pypdf 327,646 / 237 | **PyMuPDF** — preserved substantial table content that pypdf missed. |
| FIMSUL `33-6f8ab05da6` | PyMuPDF 262,947 / 76; pypdf 259,850 / 76 | **PyMuPDF** — slightly more extracted text; quality difference was modest. |
| FIMSUL `35-a68c60fc70` | PyMuPDF 83,681 / 36; pypdf 76,680 / 36 | **PyMuPDF** — more extracted text and clearer title formatting. |
| Tamil Nadu Gazette | PyMuPDF 212,121 / 129; pypdf 195,760 / 129 | **Neither clearly better** — manual inspection showed garbled Tamil characters and unreliable headings in the extracted output. |
| PMMSY farmer FAQ | PyMuPDF 9,793 / 9; pypdf 9,275 / 9 | **PyMuPDF** — preserved the beneficiary funding table as a readable Markdown grid with correct percentages and readable FAQ content. |
| Tamil Nadu Fisheries HTML page | Trafilatura 1,967 chars; BeautifulSoup 7,046 chars | **Trafilatura** — extracted the actual article and removed navigation menus; BeautifulSoup retained irrelevant navigation content. |


### D07 · Parsing my corpus

- Files in the manifest: 347 · parsed: 344 · failed: 3 · pages in Postgres: 1,302
- Parsing coverage: 99.1% of all manifest files (344 of 347). All 344 successfully downloaded files were parsed.

### Failures by reason

| Reason | Files | What I did |
|---|---:|---|
| HTTP 404 (download failure) | 3 | Confirmed the source URLs were unavailable. Kept these separate from parsing failures. |

- The one I fixed: file `src/meenmitra/ingest/parse.py`, reason: the HTML extraction needed reliable article-content selection, fix: added fallback selectors for `.ep_summary_content_main`, `.ep_tm_page_content`, and `section.sidemenu section.faq`.

### What I saw when I read my parsed pages

- A page where the heading path is right: AMENDMENT TO THE TAMIL NADU MARINE FISHING REGULATION RULES, 1983, page 2, path: `CHAPTER I > PRELIMINARY`.
- Something that came out wrong: Tamil Nadu Gazette, page 129, Tamil text extraction was garbled and headings were unreliable.
- A table: Markdown grid, in AMENDMENT TO THE TAMIL NADU MARINE FISHING REGULATION RULES, 1983, page 22. Some headings appeared as generic labels such as `Col2` and `Col4`.

### My parser choice

- For PDFs I use PyMuPDF because the PMMSY Guidelines produced 807,379 characters compared with pypdf's 327,646 across 237 pages. The PMMSY Farmer FAQ also produced 9,793 characters with PyMuPDF versus 9,275 with pypdf across 9 pages.
- The Tamil Nadu Gazette is a document type that neither parser handles well; the Tamil text is garbled and heading extraction is unreliable.

### One thing that went wrong today, and how I fixed it

- During parser-store integration, the storage code used model attribute names that did not exist. I corrected `doc.metadata_` to `doc.document_metadata` and `Page.page_no` to `Page.page_number` in `src/meenmitra/ingest/store.py`.

### Inspection notes

The parser comparison was followed by manual inspection of selected document pages.

**CMFRI Marine Fish Landings**

- pypdf reported an embedded-font encoding issue involving a CFF Type1 font.
- On inspected pages, PyMuPDF produced more readable text.
- Some pypdf pages were readable, but others contained substantial encoding problems.

**PMMSY Guidelines**

- PyMuPDF preserved large amounts of table content.
- On inspected pages, pypdf extracted far less text and missed substantial table content.

**Tamil Nadu Gazette**

- Heading extraction was not consistently reliable.
- The first page had no detected headings despite containing the Gazette masthead and title.
- Some later heading results did not match the surrounding text.
- Tamil text had character-encoding limitations.

### Parser selection conclusion

- PyMuPDF is the preferred PDF parser based on the inspected extraction quality, especially where tables matter.
- Trafilatura is preferred for HTML article extraction because it removes navigation noise.
- pypdf is useful as an alternative comparison parser, but faster execution alone does not make it the better extraction choice.
- BeautifulSoup tag stripping can retain more raw text, but may include navigation and other irrelevant page content.

---

## Parser speed — full-corpus benchmark

A one-pass benchmark was run to compare parser execution time across the local PDF and HTML corpus.

Recorded terminal excerpt:

```text
pypdf: 38.56 seconds (0 errors)
Trafilatura: 7.24 seconds (0 errors)
BeautifulSoup: 5.58 seconds (0 errors)

PDF comparison: pypdf was faster.
Time difference: 92.65 seconds

HTML comparison: BeautifulSoup was faster.
Time difference: 1.66 seconds
```

The current notes draft records the following PyMuPDF timing:

```text
PyMuPDF: 131.21 seconds
```

**Verification note:** The pasted terminal excerpt showed the 92.65-second PDF time difference but did not include the direct PyMuPDF timing line. The 131.21-second figure is consistent with the recorded difference, but the original timing line should be checked before treating it as independently verified.

### Speed conclusion

- pypdf was faster for PDFs in the recorded benchmark.
- BeautifulSoup was slightly faster for HTML.
- Extraction quality remains important: PyMuPDF preserved important table content in inspected PDFs that pypdf missed.
- The benchmark was a single run; timings may vary between runs.

---

## Current verified outcomes

### Backend and deployment

- FastAPI backend foundation implemented.
- PostgreSQL persistence and Alembic migrations implemented.
- Repeatable data loader verified.
- JSONB/GIN query-plan behaviour inspected.
- Docker image verified below the 400 MB target.
- Container runs as non-root `app`.
- Docker Compose stack and clean-clone startup verified.
- Readiness behaviour verified during database failure and recovery.
- Unit tests: 18 passed in the recorded Day 4 run.
- Integration tests: 7 passed in the recorded Day 4 run.
- Combined coverage: 95% in the recorded Day 4 run.
- Live deployment smoke test passed.
- Rollback and roll-forward drill completed.
- Uptime monitoring configured.

### Corpus and parsing

- Downloader interruption/resume behaviour tested in an isolated temporary directory.
- Parser implementation supports PDF, HTML, and text formats.
- Parser-store integration tests passed 3/3 after model attribute corrections.
- Two additional PDF title tests passed individually.
- Full-corpus parse against the test database: 344 files, 1,302 pages, 0 failures.
- Second parse run confirmed idempotency: 344 already parsed, 0 new pages.
- Ten difficult files compared across PDF and HTML parser options.
- Parser speed comparison recorded, with the direct PyMuPDF timing line still requiring confirmation.

---

## Remaining verification checklist

These items should only be marked complete after checking the current repository and GitHub state.

- [ ] Confirm the accidental extra parser recommendation was removed from the D06 bullet in `NOTES.md`.
- [ ] Confirm the direct PyMuPDF benchmark output line before retaining `131.21 seconds` as verified.
- [ ] Confirm the total number of PDF and HTML files included in the full-corpus benchmark.
- [ ] Confirm every row in `data/sources.csv` has a licence value.
- [ ] Confirm `data/manifest.jsonl` is committed.
- [ ] Confirm `DATASET.md` contains licence and known-gaps tables.
- [ ] Confirm `CAPACITY` documentation contains the relevant corpus metrics.
- [ ] Confirm raw downloaded files are not committed to Git.
- [ ] Confirm source collection did not violate robots or access restrictions.
- [ ] Confirm the latest three-file changes are merged into `main`.
- [ ] Confirm CI is green on the final `main` commit.
- [ ] Run the complete current test suite after the latest parser changes.
- [ ] Run the current lint command after the latest parser changes.

**Important:** The test database parsing results do not establish that production was parsed or modified. Production database status should be checked separately before making any production-completion claim.

---

## Project status as of 24 November 2026

MeenMitra has progressed from a basic FastAPI backend into a deployed fisheries information service with PostgreSQL persistence, Docker-based development, CI/CD, source-document collection, and a document parsing pipeline.

The latest verified parser run processed 344 files and 1,302 pages in the test database with zero recorded failures. A second run confirmed that the parsing workflow skips already processed files.

The remaining work is primarily verification and delivery housekeeping: confirm the latest documentation corrections, check the final Git/CI state, and rerun the full test and lint checks after the latest parser changes.

**PMMSY Farmer FAQ — PyMuPDF is better.** It preserves the beneficiary funding table as a readable Markdown grid, including the correct 40%/60% values, and extracts the FAQ headings and questions in order. pypdf extracts less complete table content.

**Tamil Nadu Fisheries — Trafilatura is better.** It extracts the main article and removes navigation menus. BeautifulSoup retains excessive navigation links and unrelated page text, even though it extracts more characters.

**Tamil Nadu Gazette — Neither parser is clearly better.** The original page contains a readable Tamil form, but extracted Tamil characters and headings are garbled. Both PyMuPDF and pypdf have Tamil encoding limitations.

### English vs Tamil Token Comparison
- Hi (baseline): 221 tokens
- English sentence: 229 tokens
- Tamil sentence: 237 tokens
- English message tokens: 8
- Tamil message tokens: 16
- Tamil requires 2x the English message tokens.

### Ask What It Can't Know

- Question 6: "Will there be good catch near Dhanushkodi tomorrow?"
- Result: MeenMitra said it was not sure about tomorrow's catch. It did not invent a prediction.
- Off-topic question: "Who won the 2011 cricket world cup?"
- Result: MeenMitra declined in one sentence: "I’m sorry, but that question is outside the scope of MeenMitra."
- Provider: Groq fallback was used for the off-topic question.

###Day 8 testing section:
1.Document-based question: “What is the scientific name of Indian mackerel?”

Expected from data/sample_records.json: Rastrelliger kanagurta

MeenMitra answered: Scomberomorus guttatus

Result: Incorrect scientific name stated confidently. Evidence that answers must be grounded in retrieved documents.
2.Document-based question: “What are the Tamil local names listed for Indian mackerel in the dataset?”

Expected from data/sample_records.json, record 004: Kumla / Kanangeluthi.

MeenMitra answered: Kanankahthai (கானாங்களுத்தி).

Result: The answer did not match the dataset. The model supplied a local name without retrieving or verifying the record.


### D08 · LLM gateway

- Primary configured in `.env`: `gemini-3.5-flash-lite` (Gemini) · fallback: `openai/gpt-oss-20b` (Groq).
- Intended/default primary `gemini-3.8-flash` encountered HTTP 503 and ReadTimeout errors.
- A successful Gemini response without fallback was verified locally.
- Production `POST /v1/chat` with `stream: true` returned HTTP 200 and streamed Server-Sent Events.
- Production test question: "What is the scientific name of Indian mackerel?"
- Production response used Groq fallback: `openai/gpt-oss-20b`.
- Production latency: 1,527 ms.
- Production tokens: 292 input / 255 output.
- Production estimated cost: Rs 0.009348.
- Production fallback metadata: `fallback_used: true`, `attempts: 1`.
- Laptop first-token and total-response timings: not recorded in the available evidence.
- Day 1 target: under 1.5 seconds.

### Tokens: English against Tamil

| Message | tokens |
|---|---:|
| "Hi" (baseline, mostly system prompt) | 221 |
| English sentence | 229 |
| Same sentence in Tamil | 237 |
| English message only | 8 |
| Tamil message only | 16 |

- Tamil message requires 2x the tokens of the English message.

### What the model does without my documents

- Question: "Will there be good catch near Dhanushkodi tomorrow?"
- Result: MeenMitra said it was not sure about tomorrow's catch and did not invent a prediction.
- Off-topic question: "Who won the 2011 cricket world cup?"
- Result: MeenMitra declined in one sentence.
- A document-based question about the scientific name of Indian mackerel exposed an accuracy issue.
- Expected answer: `Rastrelliger kanagurta`.
- Production answer: `Scomberomorus guttatus`.
- Result: The production answer was incorrect for Indian mackerel.

### Fallback and circuit breaker

- Production primary/fallback test: Groq answered after fallback; provider `groq`, model `openai/gpt-oss-20b`.
- Production fallback response latency: 1,527 ms.
- Production response metadata: `fallback_used: true`, `attempts: 1`.
- Local testing verified Groq fallback and circuit-breaker behaviour.
- Circuit breaker failure threshold: 3 consecutive failures.
- Exact log question number at which Gemini error messages stopped: not recorded in the available evidence.

### The bill

- Latest production `/v1/usage?days=7` response: 59 calls, 25 errors, 24 fallbacks, 9,088 input tokens, 6,894 output tokens, total estimated cost Rs 0.4146.
- Individual production chat test cost: Rs 0.009348.
- Average cost per answered question: not calculated because the usage response does not provide a separate successful-call count.

### One thing that went wrong today, and how I fixed it

- The default Gemini model encountered HTTP 503 and ReadTimeout errors.
- Restored `gemini-3.5-flash-lite` in `.env`.
- Verified a successful Gemini response without fallback locally.
- Verified Groq fallback and circuit-breaker behaviour locally.
- Production streaming worked, but the Indian mackerel scientific-name answer was incorrect. This remains an answer-quality issue to investigate.

## D09 · Prompt versions compared

<!-- prompts:start -->

| Prompt version | Correct | Accuracy | Invalid replies | Avg tokens in |
|---|---|---|---|---|
| classify_v1 | 13/20 | 65% | 0 | 48 |
| classify_v2 | 20/20 | 100% | 0 | 255 |
| classify_v3 | 20/20 | 100% | 0 | 392 |
| classify_v4 | 20/20 | 100% | 0 | 404 |

<!-- prompts:end -->

### D09 · Test-set label correction

- Corrected test-set line 10 from docs to personal.
- Reason: doc\QUESTIONS.md explicitly marks yesterday's sardine price at Rameswaram market as unanswerable and absent from the documents.
- This corrects the expected label; it does not represent a prompt improvement.


### D09 · Prompts and structured output

- My best router prompt: classify_v__ with ___ / 20
- What I changed in v4, and what happened to the score:
- The question my best version still gets wrong (line, wanted, got), and why I think so:
- A label in my test set that I changed after seeing the results (or "none"):
- Input tokens per question: v1 ___ , best version ___ . Is the extra accuracy worth it?

### My contract (DocMeta)

- Fields I kept from my project card:
- Fields I deleted, and why they make no sense per document:
- The field I tightened, and how:

### Extraction run

- Prompt version: extract_v__ · documents: ___ ok, ___ repaired, ___ failed (of ___ parsed)
- Not finished? Why, and how many are left:
- Most common failure reason, and what I did about it:
- A record that was valid but wrong (document, field, what it said, what is true):
- Cost at list price: Rs ___ in total, Rs ___ per document

### One thing that went wrong today, and how I fixed it
