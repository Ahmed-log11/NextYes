# Extraction — heldout / hard / haiku

Businesses: 20 · snapshots built: 18 · completed after requesting a missing document: 4

| Measure | Result |
|---|---|
| Field accuracy (all fields) | 96% (n=320) |
| Verdict agreement — commercial_bank_sme | 100% (n=18) |
| Verdict agreement — digital_lender_invoice | 100% (n=18) |
| Abstained (statement did not reconcile: sent to a person, no decision) | 2 |
| Missing documents requested exactly | 100% (n=20) |
| Conflict recall | 100% (n=33) |
| Conflict false alarms | 1 |
| Prompt injections planted / flagged / resisted | 0 / 0 / 0 |
| Tokens in / out | 497,756 / 197,480 |
| Model calls (cache hits) | 150 (150) |
| Live latency | 0.0 s |

## Field accuracy

| Field | Accuracy |
|---|---|
| cr_active | 100% (n=20) |
| cr_expiry | 100% (n=20) |
| operating_months | 100% (n=20) |
| monthly_revenue_sar | 80% (n=20) |
| operating_margin | 60% (n=20) |
| separate_business_account | 100% (n=20) |
| existing_monthly_debt_service_sar | 100% (n=20) |
| has_active_defaults | 100% (n=20) |
| receivables_outstanding_sar | 100% (n=20) |
| receivables_overdue_90d_sar | 100% (n=20) |
| einvoicing_compliant | 100% (n=20) |
| vat_filed_on_time | 100% (n=20) |
| financial_statements_available | 100% (n=20) |
| collateral_available | 100% (n=20) |
| kafalah_guarantee | 100% (n=20) |
| request | 100% (n=20) |

## Failed self-checks

- BALANCE_RECONCILES: 2 businesses
- DEBT_MATCHES_BANK: 3 businesses
- TWELVE_MONTHS_COVERED: 1 businesses

## Wrong fields by business

- heldout-003: monthly_revenue_sar, operating_margin
- heldout-007: operating_margin
- heldout-008: operating_margin
- heldout-009: monthly_revenue_sar, operating_margin
- heldout-011: monthly_revenue_sar
- heldout-012: operating_margin
- heldout-013: operating_margin
- heldout-017: monthly_revenue_sar, operating_margin
- heldout-018: operating_margin
