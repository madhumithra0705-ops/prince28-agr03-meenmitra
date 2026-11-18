# Database Migration Verification

## 1. Migration 2 Downgrade
Command:
uv run alembic downgrade -1

Result:
Successfully downgraded from c32d6f697003 to a009a85f761c.

## 2. Current Migration
Command:
uv run alembic current

Result:
a009a85f761c

## 3. Migration 2 Upgrade
Command:
uv run alembic upgrade head

Result:
Successfully upgraded from a009a85f761c to c32d6f697003.

## 4. Migration History
Command:
uv run alembic history

Result:
a009a85f761c -> c32d6f697003 (head), add gin index on metadata
<base> -> a009a85f761c, create documents and pages

records=20 inserted=20 updated=0 unchanged=0
records=20 inserted=0 updated=0 unchanged=20
records=20 inserted=0 updated=1 unchanged=19
