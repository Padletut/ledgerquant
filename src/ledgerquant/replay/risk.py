"""Deterministic checks on an agent's proposal against the user's limits (a precursor to the Risk Engine).

A check either accepts a proposal as given or rejects it with a reason. It never
changes the proposal: a stop, target or horizon is the agent's, and a proposal
that does not fit the limits is sent back, not adjusted.
"""


def check_entry(setup: dict, limits: dict, market_times: dict) -> str | None:
    """None when the entry fits the limits, otherwise the reason it is rejected."""
    if limits.get("close_before_weekend") and setup["expected_horizon_hours"] > market_times["hours_to_weekend_close"]:
        return "HORIZON_EXCEEDS_WEEKEND_CLOSE"
    return None


def rejection_feedback(reason: str, setup: dict, market_times: dict) -> dict:
    """What the agent is told when its proposal is rejected."""
    return {"rejected_action": "entry", "reason": reason,
            "proposed_expected_horizon_hours": setup["expected_horizon_hours"],
            "hours_to_weekend_close": market_times["hours_to_weekend_close"],
            "note": "The proposal was not opened and was not changed. Give a new analysis for the same time."}
