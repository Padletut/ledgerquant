"""Decision times for a replay and the evidence label of each one.

Labels (architecture, Section 5.2):

- `CONTAMINATED`: on or before the latest training data cutoff of the variant's
  models. Only for debugging the pipeline; never used to rank variants.
- `DEVELOPMENT`: after every cutoff and before the holdout.
- `HOLDOUT`: the shared holdout window, used once per chosen variant.
- `AFTER_HOLDOUT`: later data, kept for a future holdout or prospective use.

A plan refuses holdout and contaminated times unless they are asked for
explicitly, and refuses a model profile without a recorded training cutoff.
"""

from datetime import date, datetime, timedelta, timezone

HOLDOUT = (date(2026, 9, 1), date(2026, 10, 9))  # [start, end)
DECISION_HOURS = range(7, 21)  # 07:00-20:00 UTC, the London and New York sessions


class PlanError(ValueError):
    pass


def decision_times(start: date, end: date, hours=DECISION_HOURS) -> list[datetime]:
    """Every listed hour on Monday-Friday in [start, end)."""
    times, day = [], start
    while day < end:
        if day.weekday() < 5:
            times.extend(datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc) for hour in hours)
        day += timedelta(days=1)
    return times


def label(at: datetime, latest_cutoff: date) -> str:
    day = at.astimezone(timezone.utc).date()
    if day <= latest_cutoff:
        return "CONTAMINATED"
    if HOLDOUT[0] <= day < HOLDOUT[1]:
        return "HOLDOUT"
    if day >= HOLDOUT[1]:
        return "AFTER_HOLDOUT"
    return "DEVELOPMENT"


def plan(start: date, end: date, profiles, *, allow_holdout: bool = False,
         allow_contaminated: bool = False, hours=DECISION_HOURS) -> list[tuple[datetime, str]]:
    cutoffs = [profile.training_data_cutoff for profile in profiles]
    if not profiles or any(cutoff is None for cutoff in cutoffs):
        raise PlanError("every model profile in a replay needs a training_data_cutoff")
    latest = max(cutoffs)
    planned = [(at, label(at, latest)) for at in decision_times(start, end, hours)]
    labels = {name for _, name in planned}
    if "HOLDOUT" in labels and not allow_holdout:
        raise PlanError("the plan reaches into the holdout; pass allow_holdout for the one final evaluation")
    if "CONTAMINATED" in labels and not allow_contaminated:
        raise PlanError(f"the plan includes days on or before the training cutoff {latest}; "
                        "pass allow_contaminated for pipeline debugging only")
    return planned
