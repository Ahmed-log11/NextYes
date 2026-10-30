# NextYes

An AI agent that takes a small business from a financing rejection to an approval: it diagnoses why a lender would decline, builds a plan, executes what it can, re-assesses, and submits the application once the business is ready.

## Status

- [x] **Chunk 1 — Readiness engine.** Deterministic scoring of a business against a lender policy.
- [ ] Chunk 2 — Synthetic businesses and documents
- [ ] Chunk 3 — Document extraction
- [ ] Chunk 4 — Agent (LangGraph), tools and guardrails
- [ ] Chunk 5 — Evaluation harness and baselines
- [ ] Chunk 6 — API
- [ ] Chunk 7 — Web app

## Key design decision

The language model never decides readiness. A rule engine scores the business against a lender policy written in YAML; the model extracts, explains, plans and talks. Results are therefore explainable and identical for identical inputs.

## Quick start

```bash
make install
make test      # 36 tests
make assess    # score the demo bakery supplier against both lenders
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
  examples/bakery_supplier.json
  tests/test_engine.py
```

## Lender policies

Each rule cites its public source. Rules marked `assumption: true` state a criterion the source gives without a number (for example "registration not close to expiry"), so the threshold is ours. Swapping the policy file changes the verdict without touching code.

Sources: [Lendo — Business financing requirements in Saudi Arabia](https://www.lendo.sa/en/blog/business-financing-requirements-in-saudi-arabia) · [Qoyod — SME financing in Saudi Arabia 2026](https://www.qoyod.com/en/reports/saudi-sme-financing-2026/)
