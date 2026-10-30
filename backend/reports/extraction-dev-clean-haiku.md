# Extraction — dev / clean / haiku

Businesses: 40 · snapshots built: 40 · completed after requesting a missing document: 0

| Measure | Result |
|---|---|
| Field accuracy (all fields) | 100% (n=640) |
| Verdict agreement — commercial_bank_sme | 100% (n=40) |
| Verdict agreement — digital_lender_invoice | 100% (n=40) |
| Abstained (statement did not reconcile: sent to a person, no decision) | 0 |
| Missing documents requested exactly | 100% (n=40) |
| Conflict recall | n/a |
| Conflict false alarms | 0 |
| Prompt injections planted / flagged / resisted | 0 / 0 / 0 |
| Tokens in / out | 781,736 / 341,841 |
| Model calls (cache hits) | 283 (235) |
| Live latency | 909.3 s |

## Field accuracy

| Field | Accuracy |
|---|---|
| cr_active | 100% (n=40) |
| cr_expiry | 100% (n=40) |
| operating_months | 100% (n=40) |
| monthly_revenue_sar | 100% (n=40) |
| operating_margin | 98% (n=40) |
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

## Wrong fields by business

- dev-032: operating_margin
