"""Play a business forward in time, one month per call.

Time itself changes the data, with or without a plan:
- the as-of date moves one month, so the CR gets closer to expiry and history grows;
- the 12-month revenue window drops its oldest month and adds a new one. By default the
  new month repeats the same month last year (the business's own seasonality); while the
  owner works on STEADY_REVENUE it is the trailing average instead.

Then each step in progress gets its effect: ongoing steps every month until done,
one-off steps when their duration has passed. Everything is deterministic.
"""

from __future__ import annotations

import calendar
from datetime import date
from statistics import mean

from ..engine import FinancialSnapshot, Policy
from .models import PlanStep
from .remedies import CATALOG


def add_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def pass_time(s: FinancialSnapshot, steady_revenue: bool) -> FinancialSnapshot:
    rev = list(s.monthly_revenue_sar)
    new = round(mean(rev), 2) if steady_revenue else rev[0]
    return s.model_copy(update={
        "as_of": add_month(s.as_of),
        "operating_months": s.operating_months + 1,
        "monthly_revenue_sar": rev[1:] + [new],
    })


def start_step(s: FinancialSnapshot, step: PlanStep, month: int) -> FinancialSnapshot:
    """Begin a step (after approval, or right away for the agent's own steps).
    A one-off step with no duration takes effect immediately."""
    remedy = CATALOG[step.remedy]
    step.status, step.started_month = "in_progress", month
    if remedy.done_when is None and step.duration_months == 0:
        s = remedy.on_done(s, step.params)
        step.status, step.done_month = "done", month
    return s


def advance_month(s: FinancialSnapshot, steps: list[PlanStep], month: int, policy: Policy) -> FinancialSnapshot:
    """Move from journey month `month` to `month + 1`; returns the new snapshot and
    updates step statuses in place."""
    running = [st for st in steps if st.status == "in_progress"]
    s = pass_time(s, steady_revenue=any(st.remedy == "STEADY_REVENUE" for st in running))
    now = month + 1
    for st in running:
        remedy = CATALOG[st.remedy]
        if remedy.done_when is not None:
            if remedy.monthly:
                s = remedy.monthly(s, st.params)
            if remedy.done_when(s, policy, st.params):
                st.status, st.done_month = "done", now
        elif now - (st.started_month or 0) >= st.duration_months:
            s = remedy.on_done(s, st.params)
            st.status, st.done_month = "done", now
    return s
