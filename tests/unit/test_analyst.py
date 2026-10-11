from ledgerquant.pipeline.analyst import Analysis, unknown_citations, validate

VIEWS = {k: {"stance": "NO_VIEW", "key_points": [], "citations": []} for k in ("news", "sentiment", "chart")}
CONTEXT = {"market": {"status": "READY", "latest": {"id": "quote:X", "bid": "100.0", "ask": "100.2"},
                      "bars": {"H1": [{"id": "bar:X:H1:1"}]}},
           "news": {"headlines": [{"id": "news:abc"}]}}


def analysis(**fields):
    return Analysis.model_validate({"views": VIEWS} | fields)


def setup(**overrides):
    return {"thesis": "t", "citations": ["bar:X:H1:1"], "stop": "99.0", "target": "103.0",
            "max_holding_minutes": 120, "invalidation": "i", "uncertainty": "u"} | overrides


def test_entry_levels_must_sit_around_the_entry_price():
    assert validate(analysis(action="LONG", setup=setup()), CONTEXT, None) == "VALID"
    assert validate(analysis(action="SHORT", setup=setup(stop="101.0", target="98.0")), CONTEXT, None) == "VALID"
    assert validate(analysis(action="LONG", setup=setup(stop="101.0")), CONTEXT, None) == "INVALID_LEVELS"
    assert validate(analysis(action="LONG", setup=setup(stop="100.1")), CONTEXT, None) == "INVALID_LEVELS"  # inside spread
    assert validate(analysis(action="LONG", setup=setup(stop="abc")), CONTEXT, None) == "INVALID_LEVELS"


def test_unknown_citations_are_recorded_but_a_setup_needs_one_real_source():
    views = dict(VIEWS, news={"stance": "BULLISH", "key_points": ["x"], "citations": ["news:https://made.up"]})
    found = Analysis.model_validate({"views": views, "action": "NO_SIGNAL"})
    assert validate(found, CONTEXT, None) == "VALID"
    assert unknown_citations(found, CONTEXT) == ["news:https://made.up"]
    invented = analysis(action="LONG", setup=setup(citations=["news:invented"]))
    assert validate(invented, CONTEXT, None) == "UNSUPPORTED_SETUP"


def test_fields_must_match_the_chosen_action():
    wait = {"kind": "EVENT", "waiting_for": "CPI", "recheck_after_minutes": 60}
    assert validate(analysis(action="LONG", setup=setup(), wait=wait), CONTEXT, None) == "INCONSISTENT_DECISION"
    assert validate(analysis(action="WAIT", wait=wait), CONTEXT, None) == "VALID"
    assert validate(analysis(action="NO_SIGNAL", wait=wait), CONTEXT, None) == "INCONSISTENT_DECISION"


def test_open_position_takes_hold_close_or_valid_adjust():
    open_long = {"direction": "LONG", "stop": "99.0", "target": "103.0"}
    hold = analysis(action="HOLD", reason="r")
    assert validate(hold, CONTEXT, open_long) == "VALID"
    assert validate(analysis(action="NO_SIGNAL"), CONTEXT, open_long) == "INCONSISTENT_DECISION"
    tighten = analysis(action="ADJUST", adjustment={"new_stop": "99.5"})
    assert validate(tighten, CONTEXT, open_long) == "VALID"
    above = analysis(action="ADJUST", adjustment={"new_stop": "100.5"})
    assert validate(above, CONTEXT, open_long) == "INVALID_LEVELS"


def test_hold_may_repeat_current_levels_but_not_change_them():
    open_long = {"direction": "LONG", "stop": "99.0", "target": "103.0"}
    same = analysis(action="HOLD", adjustment={"new_stop": "99.00", "new_target": "103.0"})
    assert validate(same, CONTEXT, open_long) == "VALID"
    moved = analysis(action="HOLD", adjustment={"new_stop": "99.5"})
    assert validate(moved, CONTEXT, open_long) == "INCONSISTENT_DECISION"
    assert validate(analysis(action="WAIT", wait={"kind": "EVENT", "waiting_for": "x", "recheck_after_minutes": 60}),
                    CONTEXT, open_long) == "INCONSISTENT_DECISION"
