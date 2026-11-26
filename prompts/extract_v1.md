You read one document from MeenMitra's collection and fill in a small record about it.

What MeenMitra does:
Answers fishers' questions on ban periods, gear rules, fish species and welfare schemes, linking local Tamil fish names to scientific names.

Rules:
- Reply with one JSON object and nothing else: no explanation, no Markdown fences.
- Use only information stated in the document.
- If the document does not specify the year, use null.
- If a list field has no relevant values, use [].
- summary: one or two plain sentences, at most 300 characters.
- topics: 1 to 6 short topics.
- Every list must contain short values, with at most 8 values.
- Use only the allowed doc_kind, language and regulation values defined below.
- year must be between 1950 and 2027, or null.
- Each list value must contain 1 to 80 characters.
- summary must contain at least 20 characters.

What each field means:
- doc_kind: the type of document, such as guideline, rule, notice, list, report, faq, form, tutorial, reference or other.
- year: the year the document was published or the rule came into force, or null if not stated.
- language: the main language of the document (en, ta, hi or other).
- summary: a short description of what the document contains.
- topics: 1 to 6 short subject labels describing the document.
- species_scientific: scientific names of the fish species mainly covered by the document.
- local_name_tamil: Tamil local names of the fish species mentioned in the document.
- topic: specific subjects covered by the document, such as fishing bans, gear rules or welfare schemes.
- region: geographical areas that the document applies to or mentions.
- regulation: regulation categories covered by the document. Use only: mesh_size, minimum_legal_size, fishing_ban, licensing, gear_restriction, protected_species or other.
