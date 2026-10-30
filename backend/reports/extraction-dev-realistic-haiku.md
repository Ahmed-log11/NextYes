# Extraction — dev / realistic / haiku

Businesses: 40 · snapshots built: 39 · completed after requesting a missing document: 9

| Measure | Result |
|---|---|
| Field accuracy (all fields) | 99% (n=640) |
| Verdict agreement — commercial_bank_sme | 100% (n=39) |
| Verdict agreement — digital_lender_invoice | 100% (n=39) |
| Abstained (statement did not reconcile: sent to a person, no decision) | 1 |
| Missing documents requested exactly | 100% (n=40) |
| Conflict recall | n/a |
| Conflict false alarms | 2 |
| Prompt injections planted / flagged / resisted | 0 / 0 / 0 |
| Tokens in / out | 803,243 / 369,475 |
| Model calls (cache hits) | 289 (289) |
| Live latency | 0.0 s |

## Field accuracy

| Field | Accuracy |
|---|---|
| cr_active | 100% (n=40) |
| cr_expiry | 100% (n=40) |
| operating_months | 100% (n=40) |
| monthly_revenue_sar | 95% (n=40) |
| operating_margin | 90% (n=40) |
| separate_business_account | 100% (n=40) |
| existing_monthly_debt_service_sar | 100% (n=40) |
| has_active_defaults | 100% (n=40) |
| receivables_outstanding_sar | 100% (n=40) |
| receivables_overdue_90d_sar | 100% (n=40) |
| einvoicing_compliant | 100% (n=40) |
| vat_filed_on_time | 100% (n=40) |
| financial_statements_available | 100% (n=40) |
| collateral_available | 100% (n=40) |
| kafalah_guarantee | 100% (n=40) |
| request | 100% (n=40) |

## Failed self-checks

- BALANCE_RECONCILES: 1 businesses
- TWELVE_MONTHS_COVERED: 1 businesses

## Wrong fields by business

- dev-018: monthly_revenue_sar, operating_margin
- dev-026: operating_margin
- dev-028: operating_margin
- dev-031: monthly_revenue_sar, operating_margin
