# Engineering notes: MeenMitra

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

**Current migration**

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

### 3. EXPLAIN for JSONB sha256 filter

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

The table contains only 20 records, so scanning the table directly is estimated to be cheaper.

Using an index would add extra lookup overhead for this small table.

**When would it switch to GIN index?**

For a larger table and a selective JSONB filter, PostgreSQL may choose the GIN index when its estimated cost is lower.
### 4. SHA-256 column verification

**Migration**

Command:
```text
uv run alembic upgrade head

The API returns the `sha256` field and supports filtering documents by SHA-256.
### 4. SHA-256 column verification

**Migration**

Command:
```text
uv run alembic upgrade head

The API returns the sha256 field and supports filtering documents by SHA-256.

## Migration 2: GIN index on metadata

Proof the escape route works: downgrade -1, check, upgrade head, history.

```
(inga terminal output paste pannunga)
```
