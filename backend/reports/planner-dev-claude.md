# Agent planner vs rule planner: dev (40 businesses, brain claude)

## approve_all

| | rules | agent |
|---|---|---|
| ready | 40/40 | 40/40 |
| mean months when ready | 0.4 | 0.4 |
| mean owner steps | 1.23 | 0.88 |
| outcomes | {'ready': 40} | {'ready': 40} |

Agent planning rounds: {'compared': 27, 'verdicts': {'same': 14, 'better': 13}, 'valid_first_try': 27, 'valid_after_feedback': 0, 'plan_used': 27}

Different outcome: 0 journeys


## decline_one

| | rules | agent |
|---|---|---|
| ready | 27/40 | 28/40 |
| mean months when ready | 0.48 | 0.61 |
| mean owner steps | 0.82 | 0.78 |
| outcomes | {'ready': 27, 'owner_declined': 13} | {'ready': 28, 'owner_declined': 12} |

Agent planning rounds: {'compared': 40, 'verdicts': {'same': 19, 'better': 19, 'worse': 2}, 'valid_first_try': 40, 'valid_after_feedback': 0, 'plan_used': 28}

Different outcome: 1 journeys

- dev-029: rules owner_declined, agent ready (digital_lender_invoice)
