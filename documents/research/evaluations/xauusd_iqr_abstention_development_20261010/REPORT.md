# XAUUSD abstention: synthetic-order development measurement

**Status:** retrospective, development-exposed quote proxy. No actual orders,
fills, broker-net payoff, independent validation, or 2021 quote outcomes.

The measurement rules in the [design](DESIGN.json) were written before the
first computation. After inspecting that computation, numeric fields were
added for the already stated thresholds without changing their values or the
rules, and the result was recomputed. The final design's SHA-256 is
`77ea7cfdb4c0d39a7415f3112ebf54b0f715f4f04f424819e30285fb97743d0f`.
The [machine-readable result](../../../data/measurements/xauusd-iqr-abstention-development-v1.json)
contains all six selected 2020 dates and the source case hash. The evaluator
rechecked each broker export against its manifest and recomputed the existing
quote-quality cases before scoring the new policies. No 2021 export was read.

This is an **operator-defined child question** of the [agent's exploratory
draft](../xauusd_quote_quality_followup_v3_20261010/REPORT.md). It retains
the high-IQR abstention action but changes the payoff from the draft's
unobservable comparison of *realized fills* for taken and skipped orders to
15-minute quote-only round-trip P/L for a synthetic order population. It does
not measure the draft's actual execution-cost or adverse-fill outcomes. The
parent draft and Critic review remain unchanged.

## Orders that would otherwise be taken

There is no recorded XAUUSD strategy or order-intent stream for these dates.
The operator confirmed the synthetic reference as the population for this
development study. It is **not** a claim about trades LedgerQuant or the broker
actually made. At each 15-minute anchor
from 08:30 through 15:45 UTC on each selected date, it intends one marketable
one-ounce XAUUSD trade. It buys when the latest pre-anchor midquote exceeds the
latest midquote strictly before the prior 15-minute boundary, sells when it is
lower, and generates no order on a tie. It closes 15 minutes after the anchor.
The same eligible intents are used for all policies; missing or stale entry,
exit, or signal quotes make an anchor ineligible before any policy comparison.

For a taken long, quote-only round-trip value is `exit bid − entry ask`; for a
taken short, it is `entry bid − exit ask`. Entry and exit use the first quote
at or after their scheduled times, at most five seconds late. This crosses
the quoted spread, but it does not establish that a real market order would
have filled at that price. Commission, financing, slippage and price impact
remain unmeasured.

For a skipped intent, executed P/L is zero. Its **unobserved alternative** is
the quote-based take value for that *same* intent. Thus the overlay's estimated
increment over taking everything is the negative sum of the take values of
the skipped intents. It includes foregone gains as well as avoided losses;
there is no invented “realized fill” for a skipped order.

The IQR rule skips when prior-30-minute spread IQR exceeds 0.085 USD/oz. The
simple baseline skips when the preceding completed 15-minute spread p95 exceeds
0.245 USD/oz. Both thresholds are medians of already inspected 2020
development features. They are development choices, not independently selected
parameters. The rule uses historical event times because actual 2020
`available_at` is unknown; this is **not** historical decision replay.

## Measured quote proxy

All values below are summed USD **per one-ounce synthetic intent**, with zero
additional non-spread cost. The six dates are selected development dates, not
a representative sample of trading days.

| 2020 date | Eligible intents | IQR skips | Take all | IQR overlay | Simple spread baseline | IQR minus baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 11 Feb | 30 | 0 | +9.59 | +9.59 | +9.59 | 0.00 |
| 14 Apr | 30 | 30 | −25.82 | 0.00 | 0.00 | 0.00 |
| 9 Jun | 30 | 29 | −15.98 | −2.11 | −3.64 | +1.53 |
| 11 Aug | 30 | 30 | −21.82 | 0.00 | 0.00 | 0.00 |
| 13 Oct | 30 | 1 | +21.51 | +22.24 | +22.49 | −0.25 |
| 8 Dec | 30 | 0 | −22.55 | −22.55 | −20.68 | −1.87 |
| **Total** | **180** | **90** | **−55.07** | **+7.17** | **+7.76** | **−0.59** |

All 180 scheduled anchors produced eligible synthetic intents. The IQR rule
skipped 90 and took 90; the simple spread baseline also skipped 90 and took
90. IQR exceeded taking all by 62.24 USD/oz across these fixed one-ounce
intents, but trailed the simpler baseline by 0.59 USD/oz. At the **day** level,
IQR beat that baseline once, trailed twice and tied three times. Fifteen-minute
intents within a date are not independent evidence.

If every taken intent incurs an additional round-trip cost `c` USD/oz, a
policy's net proxy is its table value minus `c × taken intents`. The IQR and
simple spread policies each took 90 intents, so any equal flat `c` cancels in
their comparison. State-dependent slippage and broker execution may change
their ranking; neither is observed here.

## Interpretation and next gate

The synthetic order population makes the abstention payoff measurable as a
quote-based counterfactual. The 2020 result gives **no evidence of incremental
value over the simpler spread rule** and cannot establish a profitable CFD
strategy. The apparent gain over taking every momentum intent is heavily
driven by two dates on which both filters skipped all intents. These are
selected, previously inspected development dates, and the reference strategy
was defined after earlier quote-quality results were known.

Before an economic claim, LedgerQuant needs a real or prospectively registered
order-intent population, decision-time quote availability, broker execution
and cost evidence, and a frozen counterfactual method. A separate independent
review must decide whether this weak candidate merits a 2021 evaluation;
this measurement did not consume those quote outcomes. No execution is
authorized by this study.
