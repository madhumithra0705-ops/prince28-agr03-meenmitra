# MeenMitra

Answers fishers' questions on ban periods, gear rules, fish species and welfare schemes, linking local Tamil fish names to scientific names.

**Status:** Day 1 foundation (FastAPI skeleton, quality gates). Live URL from Day 5.

## Who it's for

Fishing boat owner in Rameswaram planning trips who wants to know ban periods, mesh-size rules, welfare schemes and species information.

## The problem

Information is split between scientific papers (Latin names), regulations and scheme documents, and fishers use local Tamil names like 'vanjiram' for seer fish.

## Data sources

CMFRI publications (species, stock assessments, advisories), Tamil Nadu Marine Fishing Regulation Act 1983 and rules, ban notifications, Tamil Nadu fisheries schemes, PMMSY guidelines.

- http://eprints.cmfri.org.in/
- https://www.fisheries.tn.gov.in/
- https://pmmsy.dof.gov.in/
- Terms: CMFRI eprints are open access (check each item's licence); government documents public.

## Hardest problem (my interview story)

Name mapping across languages: local Tamil names must map to scientific names through a dictionary you build, so a question about 'vanjiram' finds papers on Scomberomorus commerson and the right regulations.

## Signature feature

Fish card: type a local name and see the scientific name, season, rules and recent CMFRI notes.

## Target metric

Correct species mapping for 95%+ of 60 local names; rules answers correct for 90%+ of 30 questions.

## Run it locally

```bash
uv sync
cp .env.example .env   # Windows: copy .env.example .env
uv run uvicorn meenmitra.api.main:create_app --factory --reload
```

Then open http://localhost:8000/docs

## Checks

```bash
uv run pytest
uv run ruff check .
```
