# Capacity plan: MeenMitra

Full corpus target: 2,000 additional CMFRI items and relevant notifications, targeting 10,000+ pages.

<!-- generated:start -->

*Generated: 2026-11-23T17:31:57.039269+00:00*

## Measured corpus and planning assumptions

- Current files measured: **345**
- Current measured/estimated pages: **1,388**
- Current extracted text: **2,459,289 characters**
- Full target: **10,000 pages**
- Estimated target text: **17,718,220 characters**
- Estimated target tokens (4 characters/token): **4,429,555**
- Chunk size / overlap: **700 / 100 tokens**
- Estimated chunks: **7,383**

## Storage and embedding estimates

| Measure | Estimate |
|---|---:|
| Current downloaded files | 50.84 MiB |
| Projected raw corpus at target size | 366.28 MiB |
| Embedding API cost at $0.15/million tokens | $0.6644 (about 63.12) |
| Vector storage (768 dimensions, float32) | 21.63 MiB |
| Extracted text storage (1.2 bytes/character estimate) | 20.28 MiB |

## Limitations

- Page counts for HTML and text are character-based approximations, not printed-page counts.
- The text estimate is based on extractable text in the current corpus; scanned PDFs may contain less text than their visual page count suggests.
- Embedding price, vector dimensions, chunk size, overlap, and storage multipliers are planning assumptions, not measured provider bills.
- Raw file projection assumes the current average file size remains representative as the corpus grows.

<!-- generated:end -->

## What I conclude

1. **Is embedding cost a problem?** The estimated one-time embedding cost for the 10,000-page target is approximately $0.66 (INR 63.12), using the assumed rate of $0.15 per million tokens. This appears manageable for the initial corpus. Actual cost depends on the selected embedding provider, model and pricing.

2. **Do vectors and text fit in my free Postgres?** The estimated vector storage is 21.63 MiB and extracted-text storage is 20.28 MiB, approximately 41.91 MiB combined. The projected raw files require another 366.28 MiB, but these files should remain outside PostgreSQL. I cannot confirm whether the database fits the free plan until I check the actual database storage quota and current usage.

3. **Which number is least certain, and how can I measure it better?** The estimated page and token counts are the least certain. HTML and text page counts are approximations, and scanned PDFs may not provide extractable text. I can improve accuracy by measuring more documents, checking extraction quality and comparing estimated tokens with actual embedding usage.

4. **What changes if the corpus grows 10 times?** If the 10,000-page target grows to 100,000 pages and document characteristics remain similar, raw storage, extracted text, vector storage and embedding cost would each grow approximately ten times. That means about 3.57 GiB of raw files, 202.8 MiB of extracted text, 216.3 MiB of vectors and $6.64 in estimated embedding cost. These are projections, not guaranteed measurements.
