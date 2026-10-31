# Extraction — heldout / realistic / haiku

Businesses: 20 · snapshots built: 20 · completed after requesting a missing document: 6

| Measure | Result |
|---|---|
| Field accuracy (all fields) | 99% (n=320) |
| Verdict agreement — commercial_bank_sme | 95% (n=20) |
| Verdict agreement — digital_lender_invoice | 95% (n=20) |
| Abstained (statement did not reconcile: sent to a person, no decision) | 0 |
| Missing documents requested exactly | 100% (n=20) |
| Conflict recall | n/a |
| Conflict false alarms | 1 |
| Prompt injections planted / flagged / resisted | 0 / 0 / 0 |
| Tokens in / out | 382,239 / 172,641 |
| Model calls (cache hits) | 138 (34) |
| Live latency | 454.20000000000005 s |

## Field accuracy

| Field | Accuracy |
|---|---|
| cr_active | 100% (n=20) |
| cr_expiry | 100% (n=20) |
| operating_months | 100% (n=20) |
| monthly_revenue_sar | 90% (n=20) |
| operating_margin | 90% (n=20) |
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

## Wrong fields by business

- heldout-015: monthly_revenue_sar, operating_margin
- heldout-016: monthly_revenue_sar, operating_margin
