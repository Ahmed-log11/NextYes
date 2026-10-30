# NextYes

An AI agent that takes a small business from a financing rejection to an approval: it diagnoses why a lender would decline, builds a plan, executes what it can, re-assesses, and submits the application once the business is ready.

## Status

- [x] **Chunk 1 — Readiness engine.** Deterministic scoring of a business against a lender policy.
- [x] **Chunk 2a — Synthetic businesses.** 63 seeded businesses with planted issues and ground truth.
- [x] **Chunk 2b — Business documents.** 6–7 bilingual PDFs per business, consistent with its true data.
- [x] **Chunk 2c — Difficulty levels.** The same documents at three levels: clean, realistic, hard.
- [x] **Chunk 3 — Document extraction.** PDF text reader, model reading (Haiku, tool use, cached), snapshot assembly in Python, field-level evaluation.
- [ ] Chunk 4 — Agent (LangGraph), tools and guardrails
- [ ] Chunk 5 — Evaluation harness and baselines
- [ ] Chunk 6 — API
- [ ] Chunk 7 — Web app

## Key design decision

The language model never decides readiness. A rule engine scores the business against a lender policy written in YAML; the model extracts, explains, plans and talks. Results are therefore explainable and identical for identical inputs.

## Quick start

```bash
make install
make test      # 492 tests
make assess    # score the demo bakery supplier against both lenders
make data      # generate the 63 synthetic businesses
make docs      # render their PDF documents at all three levels
```

## Layout

```
backend/
  app/engine/
    models.py     FinancialSnapshot, Finding, Assessment
    finance.py    instalment, DSCR, max affordable amount, SME size class
    rules.py      check functions, registered by name
    policy.py     loads lender policies from YAML
    engine.py     assess(snapshot, policy) -> Assessment
    cli.py        python -m app.engine.cli <snapshot.json> [--policy ...]
  policies/
    commercial_bank_sme.yaml       typical bank criteria
    digital_lender_invoice.yaml    typical digital invoice-backed lender
  app/synth/
    profiles.py   sector archetypes, cities, invented business names (EN + AR)
    issues.py     plantable issues; each code matches a policy rule id
    generator.py  make_business(id, seed, issues) -> SyntheticBusiness
    dataset.py    builds dev (40), heldout (20), demo (3)
    ledger.py     expands a business into document content (transactions, facilities, aging...)
    variants.py   difficulty levels: wording pools (dev / held-out disjoint), bank layouts, missing, scans, conflicts
    documents.py  renders bilingual PDFs (fpdf2 + HarfBuzz shaping, DejaVu Sans font)
  app/extract/
    pdf_text.py   reads a business's PDFs into layout text; python -m app.extract.pdf_text <folder>
    schemas.py    one tool (JSON schema) + instructions per document type
    llm.py        Anthropic reader (text, or page images for scans), disk cache, call log
    assemble.py   readings -> FinancialSnapshot; all arithmetic, conflicts, self-checks
    oracle.py     perfect reader from the ledger: pipeline ceiling + planted mistakes for tests
    evaluate.py   field accuracy and verdict agreement per split / level -> reports/
  data/<split>/<business_id>/
    business.json   meta (name, sector, city, planted issues) + true snapshot
    truth.json      expected engine result per lender policy
    documents/<level>/  bank_statement, cr_certificate, credit_report, receivables_aging,
                        tax_compliance, financing_application, income_statement (if available),
                        noise.json (what this level injected)
  examples/bakery_supplier.json
  tests/test_engine.py
  tests/test_synth.py
  tests/test_pdf_text.py
  tests/test_variants.py
  tests/test_extract.py
```

## Extraction

The model reads; Python counts. Each document is read with one forced tool call (a JSON schema per document type), so the answer is structured and validated. For the bank statement the model returns every line with a category (revenue, opex, debt service, owner funds, personal, other) and Python sums them. The CR certificate is read first so the bank reader knows the owner's name: a transfer from the owner is the owner's money, not revenue.

Nothing is guessed. A missing document leaves its fields unresolved and no snapshot is built; the result lists what to request. Conflicting documents are reported, and the authoritative one wins (CR for dates, bank statement for revenue). Self-checks catch misreading: the statement must reconcile (opening + lines = closing), cover all 12 months, and its instalments must match the credit report.

```bash
cd backend
python -m app.extract.assemble data/demo/demo-bakery-supplier/documents/realistic   # one business, Haiku
python -m app.extract.evaluate --split dev --level all --reader oracle             # ceiling, no API key
python -m app.extract.evaluate --split dev --level realistic --reader haiku        # real accuracy
```

Needs `ANTHROPIC_API_KEY` in `backend/.env` for the Haiku reader. Answers are cached in `backend/cache/llm/` (key = model + prompt version + prompt + document), so re-runs are free and identical; commit the cache to let others reproduce the numbers without a key.

## Synthetic data

Every business starts healthy, then the generator plants issues from a catalog whose codes match the policy rule ids, so the ground truth is checkable: a test asserts that for all 63 businesses the bank policy reports exactly the planted issues. The held-out set uses different seeds and only issue combinations that never occur in dev, and is not opened during development. Six businesses have no issues, to measure false alarms.

Each business is then expanded into documents a lender would actually receive. The bank statement lists transactions without category labels, includes non-revenue items (owner capital injections, personal spending when accounts are mixed), and must be read and classified to recover monthly revenue and operating margin. A test checks, for all 63 businesses, that the documents reproduce the true data exactly, so any error measured later belongs to the agent, not the data. Every document is marked SIMULATED and uses invented issuers.

### Difficulty levels

The numbers never change between levels, only how they are presented, so the truth is the same at every level and any drop in accuracy is caused by presentation alone.

| Level | What changes |
|---|---|
| clean | One bank layout, 12 fixed bilingual wordings |
| realistic | Three bank layouts (debit/credit, one signed amount column, right-to-left Arabic); many wordings incl. abbreviations and Arabic-only rows; individual customers whose transfers look like the owner's (resolvable only via the owner on the CR); ~30% of businesses miss one required document |
| hard | Realistic + 1–2 documents scanned (image only, rotated, noisy) + documents that contradict each other (application vs CR on operating history; income statement revenue inflated vs the bank statement) |

Held-out businesses use wording that never appears in dev. `noise.json` records what was injected, so evaluation can check the agent requested missing documents and flagged each conflict.

## Lender policies

Each rule cites its public source. Rules marked `assumption: true` state a criterion the source gives without a number (for example "registration not close to expiry"), so the threshold is ours. Swapping the policy file changes the verdict without touching code.

Sources: [Lendo — Business financing requirements in Saudi Arabia](https://www.lendo.sa/en/blog/business-financing-requirements-in-saudi-arabia) · [Qoyod — SME financing in Saudi Arabia 2026](https://www.qoyod.com/en/reports/saudi-sme-financing-2026/)
