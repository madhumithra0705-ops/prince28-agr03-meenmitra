MeenMitra --- Engineering Notes (Days 1--4)
Consolidated project notes for the first four development days. This
document separates implementation work from verified command output.
Where an exact Day 1 transcript was not retained, the notes describe
the repository foundation without inventing terminal results.

Project overview
MeenMitra is a fisheries information backend intended to help fishers in
Tamil Nadu find information about fishing-ban periods, gear regulations,
fish species, and welfare schemes. It aims to connect local Tamil fish
names with scientific names and relevant fisheries information.

Current backend stack: Python 3.12, uv, FastAPI, PostgreSQL,
SQLAlchemy, Alembic, Docker Compose, Redis, pytest, pytest-cov, Poe the
Poet, Ruff, and pre-commit.
D01 · Project foundation
Goal
Establish the Python project foundation and a maintainable structure for
the MeenMitra backend.
Project setup
- Python project managed with uv.
- Application package: src/meenmitra/.
- Configuration is managed through environment-based settings.
- Project dependencies and task commands are declared in
  pyproject.toml.
- Local configuration is kept outside source control; .env.example
  documents the expected environment variables.
Application configuration
The application settings include:
- app_name
- app_env (local, ci, or production)
- log_level
- data_file
APP_ENV is intentionally required rather than silently defaulted.
Invalid values are rejected during settings validation.
Repository conventions
- Application code lives under src/meenmitra/.
- Tests live under tests/.
- Data fixtures live under data/.
- Ruff is used for linting and formatting.
- Poe tasks provide repeatable project commands.
Evidence note: The current repository confirms this foundation, but
an exact Day 1 terminal transcript and Day 1 test count were not
retained in the available notes. No unverified command output is claimed
here.
D02 · FastAPI service foundation
Goal
Build a small FastAPI service with clear boundaries between
configuration, request handling, data access, errors, and logging.
Application structure
The service foundation includes:
- config.py --- validated application settings.
- logging_setup.py --- structured JSON logging and request-ID
  context.
- store.py --- initial in-memory record store loaded from
  data/sample_records.json.
- api/main.py --- application factory and lifespan setup.
- api/deps.py --- FastAPI dependency injection.
- api/middleware.py --- request IDs, request timing, and
  unexpected-error handling.
- api/errors.py --- consistent RFC 9457-style problem responses.
- api/routes/health.py --- /health and /ready.
- api/routes/documents.py --- document listing, search, pagination,
  and lookup.
API behaviour
- GET /health is the liveness endpoint. It reports whether the
  process is running and does not depend on the database.
- GET /ready reports whether the service is ready to serve traffic.
- GET /v1/documents supports search and pagination.
- GET /v1/documents/{doc_id} returns a document or a structured 404
  response.
- Invalid request parameters are handled as validation errors.
- Responses carry an X-Request-ID; a supplied request ID is reused,
  otherwise one is generated.
- Unexpected request failures are logged and converted into a
  controlled 500 response.
Initial data-store design
The first RecordStore loads JSON records and requires each record to
have an id. It supports readiness, search, and lookup. Keeping this
behind the API dependency layer allowed the backing store to be replaced
with PostgreSQL later without changing the endpoint contract.

Evidence note: The FastAPI skeleton and its implementation details
are preserved in the development instructions. Exact Day 2 test totals
and complete terminal transcripts were not retained, so they are not
stated here.
D03 · PostgreSQL, migrations, and data loading
Database integration
The in-memory store was replaced by PostgreSQL-backed persistence. The
backend uses SQLAlchemy models and sessions, with Alembic managing
schema changes.

Key database work:
- PostgreSQL database and session configuration.
- SQLAlchemy document and page models.
- Alembic migration history.
- JSONB metadata storage and a GIN index.
- SHA-256 document fingerprints.
- Document descriptive fields and timestamps.
- Repository-layer database operations.
- A repeatable data loader.
Migration verification
The earlier migration downgrade/upgrade check produced:
uv run alembic downgrade -1

Successfully downgraded from c32d6f697003 to a009a85f761c.
uv run alembic current

a009a85f761c
uv run alembic upgrade head

Successfully upgraded from a009a85f761c to c32d6f697003.
At that stage, the migration history was:
a009a85f761c -> c32d6f697003 (head), add gin index on metadata
<base> -> a009a85f761c, create documents and pages
Later migrations extended the schema with source_url, SHA-256, and
descriptive/timestamp fields. The final migration run recorded during
the Docker Compose build applied these revisions:
Running upgrade  -> a009a85f761c, create documents and pages
Running upgrade a009a85f761c -> c32d6f697003, add gin index on metadata
Running upgrade c32d6f697003 -> 924078ec9bae, add source_url to documents
Running upgrade 924078ec9bae -> 4e9ce3848267, add sha256 to documents
Running upgrade 4e9ce3848267 -> ee3b0a666077, add document descriptive and timestamp fields
Loader idempotency
The loader was run repeatedly against the same dataset:

Run 1 --- initial load
records=20 inserted=20 updated=0 unchanged=0
Run 2 --- same data loaded again
records=20 inserted=0 updated=0 unchanged=20
Run 3 --- after editing one record
records=20 inserted=0 updated=1 unchanged=19
The loader uses SHA-256 fingerprints to identify changed records.
Unchanged records are skipped; changed records are updated.
JSONB query plan
Command:
uv run python scripts/explain.py sha256 6070e0c336534abd3c0d6275d196072e663a473549432698f84b2d8327bc2f78
Normal planner:
Seq Scan on documents  (cost=0.00..10.25 rows=1 width=634) (actual time=0.494..0.494 rows=1.00 loops=1)
Rows Removed by Filter: 19
Execution Time: 0.523 ms
With sequential scan disabled:
Bitmap Heap Scan on documents  (cost=12.80..16.82 rows=1 width=634) (actual time=1.874..1.875 rows=1.00 loops=1)
  -> Bitmap Index Scan on ix_documents_metadata_gin  (cost=0.00..12.80 rows=1 width=0) (actual time=1.830..1.831 rows=1.00 loops=1)
Execution Time: 1.933 ms
Interpretation: The table had only 20 records, so PostgreSQL
estimated a sequential scan to be cheaper than an index lookup. For a
larger table and a selective JSONB filter, the planner may choose the
GIN index when its estimated cost is lower.
SHA-256 support
The database migration adds a SHA-256 field to documents. The API
returns the sha256 field and supports filtering documents by SHA-256.

Migration command:
uv run alembic upgrade head
D04 · Docker, Compose, tests, and delivery
Docker image
The Dockerfile uses a multi-stage build and runs the application as the
non-root app user. .dockerignore keeps unnecessary files out of the
build context.

Image evidence:
IMAGE           ID             DISK USAGE   CONTENT SIZE
meenmitra:dev   8e469890d750   300MB        70MB
The image is under the 400 MB target.

Non-root verification:
docker run --rm meenmitra:dev id
uid=999(app) gid=999(app) groups=999(app)
Build-cache evidence:
- Initial build time: 19.2 seconds.
- Cache-test rebuild time: 15.3 seconds.
- The dependency-install step
  uv sync --locked --no-install-project --no-dev was reported as
  CACHED.
- The temporary /health docstring change used for the cache check
  was reverted.
Docker Compose stack
The Compose stack contains:
- db --- PostgreSQL with pgvector.
- redis --- Redis.
- migrate --- one-shot Alembic migration service.
- api --- FastAPI application.
The observed stack status:
NAME                  IMAGE                    SERVICE   STATUS
meenmitra-api-1       meenmitra-api             api       Up (healthy)
meenmitra-db-1        pgvector/pgvector:pg17    db        Up (healthy)
meenmitra-migrate-1   meenmitra-migrate        migrate   Exited (0)
meenmitra-redis-1     redis:7-alpine            redis     Up (healthy)
Clean-clone verification
A clean clone was created in a separate directory. The stack was built
and started from that clone using:
docker compose up --build -d
The API, database, and Redis reached healthy/running states, and the
migration service exited successfully. The clean-clone stack was then
taken down and the temporary clone removed.

The original project stack was also restarted successfully.
Migration repeatability after restart
After docker compose down (without -v) and docker compose up -d,
the migration logs ended with:
records=20 inserted=0 updated=0 unchanged=20
This confirms the existing records were not duplicated or unnecessarily
updated on restart.
Liveness and readiness
When PostgreSQL was stopped:
curl.exe -s localhost:8000/health
{"status":"ok","app":"meenmitra","env":"local"}
The readiness response body was:
{"status":"not_ready","checks":{"database":false}}
The later explicit HTTP-status verification confirmed:
HTTP/1.1 503 Service Unavailable
{"status":"not_ready","checks":{"database":false}}
After restarting PostgreSQL:
docker compose start db
curl.exe -i localhost:8000/ready
HTTP/1.1 200 OK
{"status":"ready","checks":{"database":true}}
Interpretation: The load balancer should stop routing traffic to an
instance that is not ready. The API process remains alive, and
restarting the API would not fix a database outage.
Tests and coverage
Unit tests:
uv run poe test
Poe => pytest tests/unit
18 passed in 0.81s
An earlier run recorded:
18 passed in 1.04s
Integration tests:
uv run poe test-integration
7 passed in 6.71s
Coverage:
Unit-only coverage: 81%
Combined unit + integration coverage: 95%
Combined coverage run:
TOTAL                               262     10     28      4    95%
12 files skipped due to complete coverage.
25 passed in 5.65s
Two meaningful uncovered error-handling paths were identified:
- src/meenmitra/api/deps.py, lines 38--39: database connection
  failure handling used by readiness checks.
- src/meenmitra/api/middleware.py, lines 22--24: unexpected
  request-error handling that returns a controlled HTTP 500 response.
These are defensive failure paths. The manual readiness check verified
database failure/recovery, but it does not count as pytest coverage.
Tooling and documentation
- Makefile added for convenient project commands.
- Poe tasks include development, lint, unit tests, coverage,
  migrations, seeding, and integration tests.
- README includes Run locally in one command with
  docker compose up --build.
- .gitignore includes coverage output paths.
Pre-commit and GitHub delivery
All hooks passed on the feature branch, including:
trim trailing whitespace       Passed
fix end of files               Passed
check yaml                     Passed
check toml                     Passed
check for added large files    Passed
detect private key             Passed
ruff check                     Passed
ruff format                    Passed
Detect secrets                 Passed
The feature branch was pushed:
feat/day-04-docker-tests
Commit:
29d4dc1 docs: run locally in one command, task runner, day 4 notes
Pull request title:
feat: docker, compose stack and unit/integration tests
The pull request was merged into main, the remote feature branch was
deleted, and the local branch was updated successfully with:
git switch main
git pull
Current verified outcome
- FastAPI backend foundation implemented.
- PostgreSQL persistence and migrations implemented.
- Loader idempotency verified.
- JSONB/GIN query-plan behaviour inspected.
- Docker image is 300 MB disk usage (70 MB content size), below the
  400 MB target.
- Container runs as non-root app.
- Compose stack and clean-clone startup verified.
- /ready returns HTTP 503 when the database is stopped and HTTP 200
  after recovery.
- Unit tests: 18 passed.
- Integration tests: 7 passed.
- Coverage: 81% unit-only and 95% combined.
- D04 changes merged into main.


## D05 · CI/CD and going live

- Live URL: https://meenmitra.onrender.com
- CI run for PR #5: https://github.com/madhumithra0705-ops/prince28-agr03-meenmitra/actions/runs/44701211052
- First successful automatic deployment (CD #2): https://github.com/madhumithra0705-ops/prince28-agr03-meenmitra/actions/runs/44716701716
- CD workflow duration: 50 seconds.
- Exact merge-click and smoke-test completion timestamps were not retained, so merge-to-live lead time is not recorded.

### Smoke test output from the first successful automatic CD run

```text
ok   /health -> 200, version 2ced9003b6a2bdaad30294e094bc0dba2d5b4b98
ok   /ready -> 200 {'status': 'ready', 'checks': {'database': True}}
ok   /v1/documents?limit=1 -> 200
Smoke test passed
```

### Rollback drill

- Rolled back to SHA `6f358e162533bb6c19a2388420372e543508639f`.
  - Approximate elapsed time: 3 minutes.
- Rollback CD run: https://github.com/madhumithra0705-ops/prince28-agr03-meenmitra/actions/runs/44733280814
- Rolled forward to SHA `4450cf04b26da7ec0603166faf13a39b7cbab781`.
  - Approximate elapsed time: 3 minutes.
- Roll-forward CD run: https://github.com/madhumithra0705-ops/prince28-agr03-meenmitra/actions/runs/44733769105

**Why was keeping the newer database schema safe during rollback?**

The rollback workflow skips migrations and changes only the deployed application image.
The newer schema is backward-compatible with the older application version for this rollback.

### Where my secrets live

- Neon connection string: GitHub Secret `DATABASE_URL` and Render environment. Not in Git or the Docker image.
- Render deploy hook: GitHub Secret `RENDER_DEPLOY_HOOK` only.

### Monitoring

- UptimeRobot checks `/health` every 5 minutes.
- Email alerts are configured.
- One thing that would make my live app faster on its first request: Use an always-on hosting instance to avoid cold-start delays on the free instance.
