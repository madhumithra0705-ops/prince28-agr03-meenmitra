# Ingestion report

<!-- generated:start -->
_Generated 27 Nov 2026 12:05 from the database._

| What | Count |
|---|---|
| Documents in the database | 147 |
| Pages | 1092 |
| Tokens of text (characters ÷ 4) | 556,563 |
| Files the parser gave up on | 0 |
| Documents with an extracted record | 147 |
| Documents whose extraction failed | 0 |

| Queue | Count |
|---|---|
| Ingest jobs started | 6 |
| Items finished (done or skipped) | 80 |
| Items that needed more than one try | 12 |
| Items in the dead-letter list | 10 |

Model calls for extraction: 276 · tokens in 407,249 · tokens out 39,022 · cost at list price Rs 19.89

Last job `749b0e33fe8147f4bb521e325192151b`: 10 requested, 10 ok, 0 failed, 4.6 minutes.

Dead-letter list by stage: gave up after 3 tries 10
<!-- generated:end -->

## What I learnt

1. I learnt how document ingestion extracts text and pages and stores the results in the database.
2. I learnt that failed items can be retried, and the retry job can succeed even when the original dead-letter records remain.
3. I learnt that actual page and token counts help us compare our capacity estimates with real ingestion results.
