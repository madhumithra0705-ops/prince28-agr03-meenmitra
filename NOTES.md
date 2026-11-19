
# Engineering Notes: MeenMitra

## D03 · PostgreSQL

### 1. Database migration verification

**Migration 2 downgrade**

Command:

```text
uv run alembic downgrade -1
```

Result:

```text
Successfully downgraded from c32d6f697003 to a009a85f761c.
```

**Current migration after downgrade**

Command:

```text
uv run alembic current
```

Result:

```text
a009a85f761c
```

**Migration 2 upgrade**

Command:

```text
uv run alembic upgrade head
```

Result:

```text
Successfully upgraded from a009a85f761c to c32d6f697003.
```

**Migration history**

Command:

```text
uv run alembic history
```

Result:

```text
a009a85f761c -> c32d6f697003 (head), add gin index on metadata
<base> -> a009a85f761c, create documents and pages
```

### 2. Loader idempotency verification

**Run 1: Initial load**

```text
records=20 inserted=20 updated=0 unchanged=0
```

**Run 2: Same data loaded again**

```text
records=20 inserted=0 updated=0 unchanged=20
```

**Run 3: After editing one record**

```text
records=20 inserted=0 updated=1 unchanged=19
```

The loader uses SHA-256 fingerprints to detect changes. Unchanged records are skipped, while changed records are updated.

### 3. EXPLAIN for JSONB SHA-256 filter

Command:

```text
uv run python scripts/explain.py sha256 6070e0c336534abd3c0d6275d196072e663a473549432698f84b2d8327bc2f78
```

**Normal planner:**

```text
Seq Scan on documents  (cost=0.00..10.25 rows=1 width=634) (actual time=0.494..0.494 rows=1.00 loops=1)
Rows Removed by Filter: 19
Execution Time: 0.523 ms
```

**With sequential scan disabled:**

```text
Bitmap Heap Scan on documents  (cost=12.80..16.82 rows=1 width=634) (actual time=1.874..1.875 rows=1.00 loops=1)
  -> Bitmap Index Scan on ix_documents_metadata_gin  (cost=0.00..12.80 rows=1 width=0) (actual time=1.830..1.831 rows=1.00 loops=1)
Execution Time: 1.933 ms
```

**Why did the planner choose Seq Scan?**

The table contains only 20 records, so scanning the table directly is estimated to be cheaper. Using an index would add extra lookup overhead for this small table.

**When would it switch to the GIN index?**

For a larger table and a selective JSONB filter, PostgreSQL may choose the GIN index when its estimated cost is lower.

### 4. SHA-256 column verification

The database migration adds SHA-256 support to documents.

The API returns the `sha256` field and supports filtering documents by SHA-256.

Migration command:

```text
uv run alembic upgrade head
```

### 5. Docker: non-root user and build cache

- Non-root check: `docker run --rm meenmitra:dev id`
- Result: `uid=999(app) gid=999(app) groups=999(app)`
- Initial build time: 19.2 seconds.
- Cache-test rebuild time: 15.3 seconds.
- Dependency step `uv sync --locked --no-install-project --no-dev` was `CACHED`.
- Temporary `/health` docstring change was reverted after the test.

### 6. Docker: database failure and automatic recovery

1. **API liveness while database was stopped**

   Command:

   ```text
   curl.exe -s localhost:8000/health
   ```

   Output:

   ```json
   {"status":"ok","app":"meenmitra","env":"local"}
   ```

2. **Readiness while database was stopped**

   Command:

   ```text
   curl.exe -s localhost:8000/ready
   ```

   Output:

   ```json
   {"status":"not_ready","checks":{"database":false}}
   ```

3. **Database restarted**

   Command:

   ```text
   docker compose start db
   ```

   Output:

   ```text
   Container meenmitra-db-1 Started
   ```

4. **Readiness after database recovery**

   Command:

   ```text
   curl.exe -s localhost:8000/ready
   ```

   Output:

   ```json
   {"status":"ready","checks":{"database":true}}
   ```

**Result:** The API recovered automatically after PostgreSQL restarted. No API restart was needed.
## Run locally in one command

You need Docker Desktop running. From a fresh clone:

```bash
docker compose up --build

## D04 · Docker, Compose and tests

### The image

```text
IMAGE           ID             DISK USAGE   CONTENT SIZE
meenmitra:dev   8e469890d750   300MB        70MB

docker run --rm meenmitra:dev id
uid=999(app) gid=999(app) groups=999(app)

docker compose ps -a

NAME                  IMAGE                    SERVICE   STATUS
meenmitra-api-1       meenmitra-api             api       Up (healthy)
meenmitra-db-1        pgvector/pgvector:pg17    db        Up (healthy)
meenmitra-migrate-1   meenmitra-migrate        migrate   Exited (0)
meenmitra-redis-1     redis:7-alpine            redis     Up (healthy)

First migration:
records=20 inserted=20 updated=0 unchanged=0

After down + up:
records=20 inserted=0 updated=0 unchanged=20

db stopped:  /health → {"status":"ok","app":"meenmitra","env":"local"}
db stopped:  /ready  → {"status":"not_ready","checks":{"database":false}}
db started:  /ready  → {"status":"ready","checks":{"database":true}}

uv run poe test              → 18 passed in 1.04s
uv run poe test-integration  → 7 passed in 6.71s

coverage TOTAL, unit only    → 81%
coverage TOTAL, with integration tests → 95%

Two uncovered areas:
deps.py lines 38–39: database failure handling; important for readiness checks.
middleware.py lines 22–24: unexpected request error handling; important for clean HTTP 500 responses.
