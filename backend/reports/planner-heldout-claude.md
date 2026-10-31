# Agent planner vs rule planner: heldout (20 businesses, brain claude)

## approve_all

| | rules | agent |
|---|---|---|
| ready | 19/20 | 19/20 |
| mean months when ready | 0.63 | 0.63 |
| mean owner steps | 1.25 | 0.95 |
| outcomes | {'ready': 19, 'not_reachable': 1} | {'ready': 19, 'not_reachable': 1} |

Agent planning rounds: {'compared': 17, 'verdicts': {'better': 10, 'same': 5, 'worse': 2}, 'valid_first_try': 17, 'valid_after_feedback': 0, 'plan_used': 14}

Different outcome: 0 journeys


## decline_one

| | rules | agent |
|---|---|---|
| ready | 12/20 | 11/20 |
| mean months when ready | 0.67 | 0.64 |
| mean owner steps | 0.8 | 0.7 |
| outcomes | {'ready': 12, 'owner_declined': 7, 'not_reachable': 1} | {'ready': 11, 'owner_declined': 8, 'not_reachable': 1} |

Agent planning rounds: {'compared': 25, 'verdicts': {'better': 12, 'same': 11, 'worse': 2}, 'valid_first_try': 25, 'valid_after_feedback': 0, 'plan_used': 14}

Different outcome: 1 journeys

- heldout-014: rules ready, agent owner_declined (commercial_bank_sme)
