
# MeenMitra

MeenMitra helps fishers find information about fishing ban periods, gear regulations, fish species and welfare schemes. It connects local Tamil fish names with scientific names and relevant fisheries information.

**Status:** Backend foundation implemented with FastAPI, PostgreSQL, Docker, database migrations and automated tests.

## Who it's for

Fishing boat owners and fishers in Tamil Nadu who need accessible information about fishing rules, ban periods, fish species and government welfare schemes.

## The problem

Fisheries information is spread across scientific publications, government regulations and scheme documents. Fishers often use local Tamil names, while official resources may use scientific names.

MeenMitra aims to connect these different sources.

## Data sources

- CMFRI publications: http://eprints.cmfri.org.in/
- Tamil Nadu Fisheries Department: https://www.fisheries.tn.gov.in/
- PMMSY guidelines: https://pmmsy.dof.gov.in/

Check the licence and usage terms of individual documents before redistribution.

## Current backend

- FastAPI application with REST API endpoints.
- PostgreSQL database integration.
- SQLAlchemy models and Alembic migrations.
- JSONB metadata filtering with a GIN index.
- SHA-256 document fingerprint support.
- Idempotent document loading.
- Docker Compose setup for the API and database.
- Health and readiness endpoints.
- Unit and PostgreSQL integration tests.

## Run locally

Install dependencies:

```bash
uv sync
```

Create the environment file:

```powershell
copy .env.example .env
```

Start the application:

```bash
uv run uvicorn meenmitra.api.main:create_app --factory --reload
```

Open the API documentation:

http://localhost:8000/docs

## Docker

Start services:

```bash
docker compose up --build -d
```

Stop services:

```bash
docker compose down
```

## Available tasks

Run tasks using Poe:

```bash
uv run poe
```

Available tasks:

- `uv run poe dev`
- `uv run poe lint`
- `uv run poe test`
- `uv run poe cov`
- `uv run poe migrate`
- `uv run poe seed`
- `uv run poe test-integration`

Integration tests require the PostgreSQL test database configuration.

## Checks

Run lint:

```bash
uv run poe lint
```

Run unit tests:

```bash
uv run poe test
```

Run coverage:

```bash
uv run poe cov
```

## Project goal

Build a reliable fisheries information system that helps fishers access accurate, understandable and locally relevant information.


## Run locally in one command

You need Docker Desktop running. From a fresh clone:

```bash
docker compose up --build
